<#
.SYNOPSIS
  Build the English patch media for Vain Dream II (FM Towns).

.DESCRIPTION
  Needs your own copies of the game data in the repo root (the game is
  distributed free by the developer at https://www.quarter-dev.info/v2/):

    Vain DreamII (1993)(Glodia)(Jp).img            (CD, raw 2352)
    Vain DreamII (1993)(Glodia)(Jp).cue/.ccd/.sub
    Vain DreamII (1993)(Glodia)(Jp)[SystemDisk].D88

  Default: rebuilds the CD image from the translations in script/*.tsv.
  -Full: also rebuilds the boot floppy (engine patches + name table);
         only needed when engine patches or name romanizations change.
  -Check: validate translations only; works WITHOUT the game data.

.EXAMPLE
  .\build.ps1 -Check     # validate your TSV edits (no game data needed)
  .\build.ps1            # build the [EN] CD image
  .\build.ps1 -Full      # floppy + CD
#>
param(
    [switch]$Full,
    [switch]$Check
)

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$env:PYTHONUTF8 = "1"

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

if ($Full) {
    Invoke-Step "floppy: engine patches (ASCII text class, half-width default)" {
        python (Join-Path $root "tools\patch_main_exp.py")
    }
    Invoke-Step "floppy: English name table" {
        python (Join-Path $root "tools\patch_names.py")
    }
}

Invoke-Step "cd: refresh script/blockpack.json.gz (validation data)" {
    python (Join-Path $root "tools\make_blockpack.py")
}
Invoke-Step "cd: reinsert translations from script/*.tsv (budget check)" {
    python (Join-Path $root "tools\reinsert.py")
}
Invoke-Step "cd: write patched image set" {
    python (Join-Path $root "tools\patch_cd.py")
}

Write-Host ""
Write-Host "BUILD OK." -ForegroundColor Green
Write-Host "  CD:     Vain DreamII (1993)(Glodia)(Jp) [EN].img (+ .cue/.ccd/.sub)"
if ($Full) {
    Write-Host "  Floppy: Vain DreamII (1993)(Glodia)(Jp)[SystemDisk]_EN.D88"
}
Write-Host "  Boot the _EN.D88 floppy together with the [EN] CD image."
