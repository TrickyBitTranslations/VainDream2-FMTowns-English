/* Vain Dream II translation browser.
   Static data (built by CI): data/script.json, data/status.json,
   data/suggestions.json. Submissions go through prefilled GitHub issues. */

const REPO = "TrickyBitTranslations/VainDream2-FMTowns-English";
const FILE_LABELS = {
  "VAIN_A_DAT.tsv": "Chapter A",
  "VAIN_B_DAT.tsv": "Chapter B",
  "VAIN_C_DAT.tsv": "Chapter C",
  "VAIN_S_DAT.tsv": "System / battle",
};

let SCRIPT = {}, STATUS = {}, SUGG = {};
let curFile = null;

async function boot() {
  const [s1, s2, s3] = await Promise.all([
    fetch("data/script.json").then(r => r.json()),
    fetch("data/status.json").then(r => r.json()),
    fetch("data/suggestions.json").then(r => r.json()).catch(() => ({})),
  ]);
  SCRIPT = s1; STATUS = s2; SUGG = s3;
  renderHeader();
  renderTabs();
  window.addEventListener("hashchange", route);
  document.getElementById("search").addEventListener("input", route);
  document.getElementById("only-untranslated").addEventListener("change", route);
  route();
}

function renderHeader() {
  const pct = STATUS.total ? (100 * STATUS.done / STATUS.total) : 0;
  document.getElementById("overall-bar").style.width = pct.toFixed(1) + "%";
  document.getElementById("overall-text").textContent =
    `${STATUS.done} / ${STATUS.total} lines translated (${pct.toFixed(1)}%)`;
}

function renderTabs() {
  const nav = document.getElementById("tabs");
  nav.innerHTML = "";
  for (const f of Object.keys(SCRIPT)) {
    const t = STATUS.files[f] || { lines: 0, done: 0 };
    const a = document.createElement("a");
    a.href = "#/" + f;
    a.dataset.file = f;
    a.innerHTML = `${FILE_LABELS[f] || f} <small>${t.done}/${t.lines}</small>`;
    nav.appendChild(a);
  }
}

function route() {
  const m = location.hash.match(/^#\/([^/]+)(?:\/(.+))?/);
  curFile = m ? decodeURIComponent(m[1]) : Object.keys(SCRIPT)[0];
  const block = m && m[2] ? decodeURIComponent(m[2]) : null;
  for (const a of document.querySelectorAll("#tabs a"))
    a.classList.toggle("active", a.dataset.file === curFile);
  const q = document.getElementById("search").value.trim().toLowerCase();
  const onlyUn = document.getElementById("only-untranslated").checked;
  if (q || onlyUn) renderSearch(q, onlyUn);
  else if (block) renderBlock(curFile, block);
  else renderBlocks(curFile);
}

function blockMeta(file, block) {
  const lines = SCRIPT[file][block];
  const real = lines.filter(l => !isEngineData(l));
  const done = real.filter(l => l.en).length;
  const b = (STATUS.budgets || {})[file + ":" + block];
  return { lines, real, done, budget: b };
}

function renderBlocks(file) {
  const el = document.getElementById("content");
  el.innerHTML = "";
  const grid = div("block-grid");
  for (const block of Object.keys(SCRIPT[file])) {
    const { real, done, budget } = blockMeta(file, block);
    const card = div("block-card");
    const pct = real.length ? (100 * done / real.length) : 0;
    card.innerHTML =
      `<h3>Scene ${esc(block)}</h3>
       <div class="progress sm"><div style="width:${pct}%"></div></div>
       <p>${done}/${real.length} lines` +
      (budget ? ` · ${budget.limit - budget.used} bytes free` : "") + `</p>`;
    card.addEventListener("click", () => location.hash = `#/${file}/${block}`);
    grid.appendChild(card);
  }
  el.appendChild(grid);
}

function renderBlock(file, block) {
  const el = document.getElementById("content");
  el.innerHTML = "";
  const { lines, real, done, budget } = blockMeta(file, block);
  const head = div("block-head");
  head.innerHTML =
    `<a href="#/${file}">← scenes</a>
     <h2>Scene ${esc(block)} <small>${done}/${real.length} translated` +
    (budget ? ` · ${budget.used}/${budget.limit} bytes (${budget.limit - budget.used} free)` : "") +
    `</small></h2>`;
  el.appendChild(head);
  el.appendChild(linesTable(file, block, lines));
}

function renderSearch(q, onlyUn) {
  const el = document.getElementById("content");
  el.innerHTML = "";
  const rows = [];
  for (const [block, lines] of Object.entries(SCRIPT[curFile])) {
    for (const l of lines) {
      if (onlyUn && (l.en || isEngineData(l))) continue;
      if (q && !(l.jp.toLowerCase().includes(q)
                 || enPlain(l.en).toLowerCase().includes(q)
                 || speakerName(l.sp).toLowerCase().includes(q)
                 || l.sp.toLowerCase().includes(q))) continue;
      rows.push({ block, l });
    }
  }
  const head = div("block-head");
  head.innerHTML = `<h2>${rows.length} matching lines <small>in ${FILE_LABELS[curFile] || curFile}</small></h2>`;
  el.appendChild(head);
  const byBlock = {};
  for (const r of rows) (byBlock[r.block] ??= []).push(r.l);
  for (const [block, ls] of Object.entries(byBlock).slice(0, 50)) {
    const h = document.createElement("h3");
    h.className = "scene-h";
    h.innerHTML = `<a href="#/${curFile}/${block}">Scene ${esc(block)}</a>`;
    el.appendChild(h);
    el.appendChild(linesTable(curFile, block, ls));
  }
}

/* Rows flagged by the data build as extraction noise that crossed into
   engine bytecode — shown dimmed, not translatable yet. */
function isEngineData(l) {
  return l.x === 1;
}

function linesTable(file, block, lines) {
  const table = document.createElement("table");
  table.className = "lines";
  const thead = document.createElement("tr");
  thead.className = "head";
  for (const [cls, label] of [["sp", "Speaker"], ["jp", "Japanese"],
                              ["en", "English"], ["act", ""]]) {
    const th = document.createElement("th");
    th.className = cls;
    th.textContent = label;
    thead.appendChild(th);
  }
  table.appendChild(thead);
  for (const l of lines) {
    const tr = document.createElement("tr");
    const sug = SUGG[file + ":" + block + " " + l.id] || [];
    const open = sug.filter(s => s.state === "open");
    const unsafe = isEngineData(l);
    tr.className = unsafe ? "unsafe" : (l.en ? "done" : "todo");
    tr.appendChild(td("sp", speakerName(l.sp)));
    tr.appendChild(td("jp", l.jp.replaceAll(/(\\n)+/g, "\n")));
    tr.appendChild(tdEnglish(l.en));
    const act = document.createElement("td");
    act.className = "act";
    if (unsafe) {
      const s = document.createElement("span");
      s.className = "engine";
      s.title = "This row overlaps engine data and can't be translated yet.";
      s.textContent = "engine data";
      act.appendChild(s);
      tr.appendChild(act);
      table.appendChild(tr);
      continue;
    }
    if (open.length) {
      const best = open.find(s => s.verdict === "valid") || open[0];
      const a = document.createElement("a");
      a.className = "sug " + best.verdict;
      a.href = `https://github.com/${REPO}/issues/${best.n}`;
      a.textContent = `${open.length} suggestion${open.length > 1 ? "s" : ""}`;
      a.title = "Open suggestion(s) for this line";
      act.appendChild(a);
    }
    const s = document.createElement("a");
    s.className = "suggest";
    s.href = suggestUrl(file, block, l);
    s.target = "_blank";
    s.rel = "noopener";
    s.textContent = l.en ? "Improve" : "Suggest";
    act.appendChild(s);
    tr.appendChild(act);
    table.appendChild(tr);
  }
  return table;
}

function suggestUrl(file, block, l) {
  const p = new URLSearchParams({
    template: "translation-suggestion.yml",
    title: `[tl] ${l.sp || "line"} ${block} ${l.id}`,
    file: file,
    line: `${block} ${l.id}`,
    original: l.jp,
  });
  return `https://github.com/${REPO}/issues/new?${p}`;
}

function speakerName(sp) {
  return (STATUS.speakers || {})[sp] || sp;
}

function enPlain(en) {
  return (en || "").replace(/\{([^}]+)\}/g,
    (_, k) => (STATUS.tokens || {})[k.toUpperCase()] || k);
}

/* English cell: \n -> line break, \p -> page divider, {NAME} -> highlighted
   name (the game renders tokens in a highlight color too). */
function tdEnglish(en) {
  const t = document.createElement("td");
  t.className = "en";
  if (!en) { t.textContent = "—"; return t; }
  for (const part of en.split(/(\{[^}]+\}|\\n|\\p)/)) {
    if (!part) continue;
    if (part === "\\n") t.appendChild(document.createElement("br"));
    else if (part === "\\p") {
      const d = document.createElement("span");
      d.className = "page-break";
      d.textContent = "— page —";
      t.appendChild(d);
    } else if (part.startsWith("{")) {
      const key = part.slice(1, -1).toUpperCase();
      const s = document.createElement("span");
      s.className = "tok";
      s.textContent = (STATUS.tokens || {})[key] || part;
      t.appendChild(s);
    } else {
      t.appendChild(document.createTextNode(part));
    }
  }
  return t;
}

function div(cls) { const d = document.createElement("div"); d.className = cls; return d; }
function td(cls, text) { const t = document.createElement("td"); t.className = cls; t.textContent = text; return t; }
function esc(s) { return s.replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c])); }

boot();
