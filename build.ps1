<#
.SYNOPSIS
  Build the English patch media for Vain Dream II (FM Towns).

.DESCRIPTION
  Needs your own copies of the game data in the repo root:

    Vain DreamII (1993)(Glodia)(Jp).img            (CD, raw 2352)
    Vain DreamII (1993)(Glodia)(Jp).cue/.ccd/.sub
    Vain DreamII (1993)(Glodia)(Jp)[SystemDisk].D88

  Default: rebuilds the CD image from the translations in script/*.tsv.
  -Full: also rebuilds the boot floppy (engine patches + name table);
         only needed when engine patches or name romanizations change.
  -Check: validate translations only; works WITHOUT the game data.
  -Release -Tag vX.Y: build, make xdelta patches, and publish a GitHub
         release. Needs xdelta3 and a logged-in gh. Notes are pulled from
         "Release-note:" trailers on commits since the last tag, so only
         commits that opt in show up - e.g. add this to a commit message:
             Release-note: All weapon and armor names are in English
  -Intro / -IntroFile: text to put at the top of the notes, above the
         commit notes. Handy when there are no Release-note: commits yet.

  TODO: probably add a CRC check for the input images

.EXAMPLE
  .\build.ps1 -Check     # validate your TSV edits (no game data needed)
  .\build.ps1            # build the [EN] CD image
  .\build.ps1 -Full      # floppy + CD
  .\build.ps1 -Release -Tag v1.0    # build + publish patches to GitHub
  .\build.ps1 -Release -Tag v1.0 -Intro "First playable release!"
  .\build.ps1 -Release -Tag v1.0 -IntroFile notes/v1.0.md
#>
param(
    [switch]$Full,
    [switch]$Check,
    [switch]$Release,
    [string]$Tag,
    [string]$Intro,
    [string]$IntroFile
)

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$env:PYTHONUTF8 = "1"

$env:PYTHONDONTWRITEBYTECODE = "1"
Get-ChildItem -Path $root -Recurse -Directory -Filter "__pycache__" -ErrorAction SilentlyContinue |
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

function Invoke-Step([string]$label, [scriptblock]$action) {
    Write-Host "== $label" -ForegroundColor Cyan
    & $action
    if ($LASTEXITCODE -ne 0) {
        Write-Host "BUILD FAILED at: $label" -ForegroundColor Red
        exit 1
    }
}

if ($Check) {
    Invoke-Step "check: validate translations (syntax, width, budgets)" {
        python (Join-Path $root "tools\reinsert.py") --check
    }
    Write-Host ""
    Write-Host "CHECK OK (nothing written)." -ForegroundColor Green
    exit 0
}

$img = Join-Path $root "Vain DreamII (1993)(Glodia)(Jp).img"
if (-not (Test-Path $img) -or (Get-Item $img).Length -lt 1MB) {
    Write-Host "Game data not found. Building needs the original disc/floppy" -ForegroundColor Red
    Write-Host "images in the repo root (see build.ps1 header / README)." -ForegroundColor Red
    Write-Host "Validation works without them:  .\build.ps1 -Check"
    exit 1
}

if (-not (Test-Path (Join-Path $root "floppy_files\DATA.BIN")) -or
    -not (Test-Path (Join-Path $root "floppy_files\MAIN.EXP"))) {
    Invoke-Step "bootstrap: extract MAIN.EXP + DATA.BIN from the floppy" {
        python (Join-Path $root "tools\extract_floppy.py") MAIN.EXP DATA.BIN
    }
}

Invoke-Step "refresh script/blockpack.json.gz (validation data)" {
    python (Join-Path $root "tools\make_blockpack.py")
}
# grow_build does it all: floppy (classifier + names + scene-table repoint) and
# CD (grown archives, relocating where needed).
Invoke-Step "build EN floppy + CD (unbounded; relocates archives as needed)" {
    python (Join-Path $root "tools\grow_build.py")
}
Invoke-Step "verify: engine patches landed in the built floppy" {
    python (Join-Path $root "tools\verify_patches.py")
}

Write-Host ""
Write-Host "BUILD OK." -ForegroundColor Green
Write-Host "  CD:     Vain DreamII (1993)(Glodia)(Jp) [EN].img (+ .cue/.ccd/.sub)"
Write-Host "  Floppy: Vain DreamII (1993)(Glodia)(Jp)[SystemDisk]_EN.D88"
Write-Host "  Boot the _EN.D88 floppy together with the [EN] CD image."

if (-not $Release) { exit 0 }

# --- release: xdelta patches + GitHub release ---
if (-not $Tag) {
    Write-Host "Release needs a tag:  .\build.ps1 -Release -Tag v1.0" -ForegroundColor Red
    exit 1
}
foreach ($t in "xdelta3", "gh") {
    if (-not (Get-Command $t -ErrorAction SilentlyContinue)) {
        Write-Host "$t not found (xdelta3: sudo apt-get install -y xdelta3)." -ForegroundColor Red
        exit 1
    }
}
& gh auth status 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "gh isn't logged in. Run: gh auth login   (or set GH_TOKEN)" -ForegroundColor Red
    exit 1
}

$B = "Vain DreamII (1993)(Glodia)(Jp)"
$jpImg = Join-Path $root "$B.img"
$enImg = Join-Path $root "$B [EN].img"
$jpD88 = Join-Path $root "${B}[SystemDisk].D88"
$enD88 = Join-Path $root "${B}[SystemDisk]_EN.D88"
$enCue = Join-Path $root "$B [EN].cue"

$dist = Join-Path $root "dist"
New-Item -ItemType Directory -Force -Path $dist | Out-Null
$cdPatch = Join-Path $dist "vd2-en-cd.xdelta"
$fdPatch = Join-Path $dist "vd2-en-floppy.xdelta"
# Release assets: GitHub strips spaces/brackets from asset names anyway, so ship the
# cue under that dotted name and repoint its FILE line to match - users don't rename
# anything, and gh's asset-arg globber won't choke on the '[EN]' brackets.
$freeName = ("$B [EN]" -replace '[^A-Za-z0-9]+', '.').Trim('.')
$cueOut = Join-Path $dist "$freeName.cue"

# patches carry only the changed bytes, not the game - safe to publish
Invoke-Step "patch: CD delta"     { & xdelta3 -e -f -s $jpImg $enImg $cdPatch }
Invoke-Step "patch: floppy delta" { & xdelta3 -e -f -s $jpD88 $enD88 $fdPatch }
# our cue, not game data - repoint FILE "...[EN].img" at the dotted release name
$cueText = (Get-Content -LiteralPath $enCue -Raw).Replace("$B [EN].img", "$freeName.img")
[System.IO.File]::WriteAllText($cueOut, $cueText, (New-Object System.Text.UTF8Encoding($false)))

$imgHash = (Get-FileHash -LiteralPath $jpImg -Algorithm SHA256).Hash.ToLower()
$d88Hash = (Get-FileHash -LiteralPath $jpD88 -Algorithm SHA256).Hash.ToLower()

# notes = "Release-note:" trailers since the previous tag (opt-in per commit)
& git fetch --tags --quiet 2>$null
$prev = (& git describe --tags --abbrev=0 2>$null)
$range = if ($prev) { "$prev..HEAD" } else { "HEAD" }
$notes = (& git log $range --format=%B) |
    Select-String -Pattern '^\s*Release-note:\s*(.+?)\s*$' |
    ForEach-Object { "- " + $_.Matches[0].Groups[1].Value } |
    Select-Object -Unique

# optional intro text at the top of the notes (-Intro string and/or -IntroFile)
$introText = $Intro
if ($IntroFile) {
    if (-not (Test-Path -LiteralPath $IntroFile)) {
        Write-Host "IntroFile not found: $IntroFile" -ForegroundColor Red
        exit 1
    }
    $fileText = (Get-Content -LiteralPath $IntroFile -Raw).TrimEnd()
    $introText = if ($introText) { "$introText`n`n$fileText" } else { $fileText }
}

$body = [System.Collections.Generic.List[string]]::new()
if ($introText) { $body.Add($introText); $body.Add("") }
if ($notes) {
    $body.Add("## What's new")
    $notes | ForEach-Object { $body.Add($_) }
    $body.Add("")
}
elseif (-not $introText) {
    $body.Add("## What's new")
    $body.Add("- (no Release-note: commits since $prev)")
    $body.Add("")
}
$body.Add("## Install")
$body.Add("Bring your own copy of the JP game, then patch it with an xdelta tool such as Delta Patcher:")
$body.Add("1. vd2-en-cd.xdelta applied to your '$B.img'")
$body.Add("2. vd2-en-floppy.xdelta applied to your '${B}[SystemDisk].D88'")
$body.Add("Name your patched CD image '$freeName.img' to match the included .cue (no spaces or brackets), and your .ccd/.sub the same way. Boot the patched floppy together with the CD in an FM Towns emulator (Tsugaru).")
$body.Add("")
$body.Add("## Patches apply to these JP files (SHA-256)")
$body.Add("$B.img  -  $imgHash")
$body.Add("${B}[SystemDisk].D88  -  $d88Hash")

$notesFile = Join-Path $dist "notes.md"
($body -join "`n") | Set-Content -LiteralPath $notesFile -Encoding utf8

Invoke-Step "publish: gh release $Tag" {
    & gh release create $Tag $cdPatch $fdPatch $cueOut --title $Tag --notes-file $notesFile
}
Write-Host ""
Write-Host "RELEASED $Tag" -ForegroundColor Green
Write-Host "  notes from Release-note: trailers ($range)"
exit 0
