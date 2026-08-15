/* Codegraph Explorer — namespace header + dropdown tree, diagram↔code
   toggle, and a requirements/tests tabbed panel. */

"use strict";

const $ = (id) => document.getElementById(id);
const api = (path) => fetch(path).then((r) => r.json());

// ── Metadata ─────────────────────────────────────────────────────────────

api("/api/meta").then((m) => {
  $("meta").textContent = `${m.source} · ${(m.tags || []).join(", ")}`;
  $("footer-source").textContent =
    `source: ${m.source || "—"} · deterministic graph export, no LLM enrichment`;
});

// ── State ────────────────────────────────────────────────────────────────

const state = {
  nsPath: [],          // namespace drill path (root view when empty)
  children: {},        // qname -> children payload
  selected: null,      // { qname, kind, name } of the current selection
  view: "diagram",     // "diagram" | "code"
  codeFiles: [],       // [{ path, language, text }]
  activeFile: 0,
  codeEditable: false,
  coverage: null,      // last /coverage payload
  tests: [],           // flattened test list for the Tests tab
  reqTab: "requirements",
};

const GLYPHS = {
  NamespaceNode: "▸", ModuleNode: "▸",
  ClassNode: "▢",
  HLR: "§", LLR: "§",
};

function glyphFor(node) {
  return GLYPHS[node.kind] || "•";
}
function isNamespace(node) {
  return node.kind === "NamespaceNode" || node.kind === "ModuleNode";
}

// ── Tree rendering ───────────────────────────────────────────────────────

function showHeader(nsName, canGoUp) {
  $("ns-header").classList.remove("hidden");
  $("ns-name").textContent = nsName;
  $("ns-up").style.visibility = canGoUp ? "visible" : "hidden";
}

function hideHeader() {
  $("ns-header").classList.add("hidden");
}

// Root view: the namespace list (searchable). Clicking a namespace
// pins it as the header and reveals its dropdown.
function renderRoots(roots) {
  hideHeader();
  const tree = $("tree");
  tree.innerHTML = "";
  $("tree-empty").style.display = roots.length ? "none" : "block";
  for (const node of roots) {
    tree.appendChild(namespaceRow(node));
  }
}

function namespaceRow(node) {
  const row = document.createElement("div");
  row.className = "tree-row";
  row.dataset.qname = node.qname;
  const glyph = document.createElement("span");
  glyph.className = "glyph";
  glyph.textContent = glyphFor(node);
  const name = document.createElement("span");
  name.className = "name";
  name.textContent = node.name;
  row.append(glyph, name);
  row.addEventListener("click", () => pinNamespace(node));
  return row;
}

// Pin *node* (a namespace) as the header; load its dropdown + diagram.
function pinNamespace(node) {
  state.nsPath.push(node.qname);
  renderLevel(node.qname);
}

function goUp() {
  if (!state.nsPath.length) return;
  state.nsPath.pop();
  state.selected = null;
  if (state.nsPath.length) {
    renderLevel(state.nsPath[state.nsPath.length - 1]);
  } else {
    api("/api/namespaces").then((r) => renderRoots(r.namespaces));
  }
}

function renderLevel(nsQname) {
  showHeader(nsQname, state.nsPath.length >= 1);
  const tree = $("tree");
  tree.innerHTML = '<div class="muted" style="padding:0.6rem 0.4rem">…</div>';

  const load = state.children[nsQname] || api(`/api/node/${encodeURIComponent(nsQname)}/children`);
  load.then((payload) => {
    state.children[nsQname] = payload;
    tree.innerHTML = "";

    const sub = payload.namespaces || [];
    const classes = payload.classes || [];
    const reqs = payload.requirements || [];

    for (const n of sub) tree.appendChild(namespaceRow(n));

    if (classes.length) {
      tree.appendChild(sectionLabel("classes"));
      for (const c of classes) tree.appendChild(classRow(c));
    }

    if (reqs.length) {
      tree.appendChild(sectionLabel("requirements"));
      for (const r of reqs) tree.appendChild(requirementRow(r));
    }

    if (!sub.length && !classes.length && !reqs.length) {
      tree.innerHTML = '<div class="muted" style="padding:0.6rem 0.4rem">empty namespace</div>';
    }
  });

  // the namespace itself is a valid target: show its as-built diagram
  selectNamespace(nsQname);
}

function sectionLabel(text) {
  const h = document.createElement("div");
  h.className = "pane-label";
  h.textContent = text;
  return h;
}

function classRow(node) {
  const wrap = document.createElement("div");
  wrap.className = "tree-node";
  const row = document.createElement("div");
  row.className = "tree-row";
  row.dataset.qname = node.qname;
  const glyph = document.createElement("span");
  glyph.className = "glyph";
  glyph.textContent = glyphFor(node);
  const name = document.createElement("span");
  name.className = "name";
  name.textContent = node.name;
  row.append(glyph, name);
  if (node.requirements || node.tests) {
    const b = document.createElement("span");
    b.className = "badge";
    const parts = [];
    if (node.requirements) parts.push(`${node.requirements} req`);
    if (node.tests) parts.push(`${node.tests} tests`);
    b.textContent = parts.join(" · ");
    row.appendChild(b);
  }
  row.addEventListener("click", () => selectClass(node));
  wrap.appendChild(row);
  return wrap;
}

function requirementRow(node) {
  const wrap = document.createElement("div");
  wrap.className = "tree-node";
  const row = document.createElement("div");
  row.className = "tree-row";
  row.dataset.qname = node.qname;
  const glyph = document.createElement("span");
  glyph.className = "glyph";
  glyph.textContent = glyphFor(node);
  const name = document.createElement("span");
  name.className = "name";
  name.textContent = node.name;
  row.append(glyph, name);
  if (node.test_count) {
    const b = document.createElement("span");
    b.className = "badge";
    b.textContent = `${node.test_count} test${node.test_count === 1 ? "" : "s"}`;
    row.appendChild(b);
  }
  row.addEventListener("click", () => selectRequirement(node));
  wrap.appendChild(row);
  return wrap;
}

// ── Selection ────────────────────────────────────────────────────────────

function markSelected(qname) {
  document.querySelectorAll(".tree-row.selected").forEach((r) => {
    r.classList.remove("selected");
  });
  const row = document.querySelector(`.tree-row[data-qname="${cssEscape(qname)}"]`);
  if (row) row.classList.add("selected");
}

function selectNamespace(nsQname) {
  state.selected = { qname: nsQname, kind: "namespace", name: nsQname };
  markSelected(nsQname);
  setView("diagram");
  loadScope(nsQname);
  loadCode(nsQname);
  clearCoverage();
}

function selectClass(node) {
  state.selected = { qname: node.qname, kind: node.kind, name: node.name };
  markSelected(node.qname);
  setView("diagram");
  loadScope(node.qname);
  loadCode(node.qname);
  loadCoverage(node.qname);
}

function selectRequirement(node) {
  state.selected = { qname: node.qname, kind: node.kind, name: node.name };
  markSelected(node.qname);
  setTab("requirements");
  $("req-body").innerHTML = "";
  const hint = document.createElement("div");
  hint.className = "canvas-empty muted";
  hint.textContent =
    `Select a class beneath this requirement to see its tests in detail.`;
  $("req-body").appendChild(hint);
  $("test-body").innerHTML =
    '<div class="canvas-empty muted">Select a class to browse its tests.</div>';
}

// ── Diagram / code toggle ────────────────────────────────────────────────

function setView(view) {
  state.view = view;
  $("view-diagram").classList.toggle("active", view === "diagram");
  $("view-code").classList.toggle("active", view === "code");
  $("zoom-controls").style.display = view === "diagram" ? "" : "none";
  $("code-save").classList.toggle("hidden", view !== "code" || !state.codeEditable);
  $("code-canvas").classList.toggle("hidden", view !== "diagram");
  $("code-view").classList.toggle("hidden", view !== "code");
  if (view === "code") renderCodeFiles();
}

$("view-diagram").addEventListener("click", () => setView("diagram"));
$("view-code").addEventListener("click", () => setView("code"));

// ── Code window: zoomable SVG ────────────────────────────────────────────

let zoom = null;

function loadScope(qname) {
  api(`/api/node/${encodeURIComponent(qname)}/scope`).then((result) => {
    const canvas = $("code-canvas");
    canvas.innerHTML = "";
    if (result.error) {
      canvas.innerHTML = `<div class="canvas-empty muted">${escapeHtml(result.error)}</div>`;
      return;
    }
    if (!result.svg) {
      canvas.innerHTML = `<div class="canvas-empty muted">plantuml CLI not
        available — cannot render the diagram.</div>
        <pre class="muted" style="margin:1rem;font-size:0.72rem;overflow:auto">${escapeHtml(result.puml)}</pre>`;
      return;
    }
    const holder = document.createElement("div");
    holder.className = "zoom-holder";
    holder.innerHTML = result.svg;
    const svg = holder.querySelector("svg");
    if (!svg) {
      canvas.innerHTML = `<div class="canvas-empty muted">no svg</div>`;
      return;
    }
    canvas.appendChild(holder);
    zoom = attachZoom(holder, svg);
  });
}

function attachZoom(holder, svg) {
  const raf = window.requestAnimationFrame
    || ((cb) => setTimeout(cb, 16));
  const naturalW = parseFloat(svg.getAttribute("width")) || 800;
  const naturalH = parseFloat(svg.getAttribute("height")) || 600;
  svg.style.width = `${naturalW}px`;
  svg.style.height = `${naturalH}px`;
  svg.style.transformOrigin = "0 0";

  let scale = 1, tx = 0, ty = 0, dirty = false;

  function fit() {
    const cw = holder.clientWidth, ch = holder.clientHeight;
    if (!cw || !ch) return;
    scale = Math.min(cw / naturalW, ch / naturalH) * 0.97;
    tx = (cw - naturalW * scale) / 2;
    ty = (ch - naturalH * scale) / 2;
    apply();
  }

  function apply() {
    svg.style.transform = `translate(${tx}px, ${ty}px) scale(${scale})`;
  }

  function zoomAt(clientX, clientY, factor) {
    const rect = holder.getBoundingClientRect();
    const px = clientX - rect.left, py = clientY - rect.top;
    const next = Math.min(12, Math.max(0.02, scale * factor));
    tx = px - ((px - tx) * next) / scale;
    ty = py - ((py - ty) * next) / scale;
    scale = next;
    dirty = true;
    apply();
  }

  holder.addEventListener("wheel", (e) => {
    e.preventDefault();
    zoomAt(e.clientX, e.clientY, e.deltaY < 0 ? 1.18 : 1 / 1.18);
  }, { passive: false });

  let drag = null;
  holder.addEventListener("mousedown", (e) => {
    drag = { x: e.clientX, y: e.clientY };
    holder.classList.add("dragging");
    e.preventDefault();
  });
  window.addEventListener("mousemove", (e) => {
    if (!drag) return;
    tx += e.clientX - drag.x;
    ty += e.clientY - drag.y;
    drag = { x: e.clientX, y: e.clientY };
    dirty = true;
    apply();
  });
  window.addEventListener("mouseup", () => {
    drag = null;
    holder.classList.remove("dragging");
  });

  $("zoom-in").onclick = () => zoomAt(holder.clientWidth / 2, holder.clientHeight / 2, 1.4);
  $("zoom-out").onclick = () => zoomAt(holder.clientWidth / 2, holder.clientHeight / 2, 1 / 1.4);
  $("zoom-reset").onclick = () => { dirty = false; fit(); };

  window.addEventListener("resize", () => { if (!dirty) fit(); });
  raf(fit);
  return { reset: () => { dirty = false; fit(); } };
}

// ── Code window: editable codegen view ───────────────────────────────────

function loadCode(qname) {
  state.codeFiles = [];
  state.activeFile = 0;
  api(`/api/node/${encodeURIComponent(qname)}/code`).then((data) => {
    state.codeFiles = data.files || [];
    state.codeEditable = !!data.editable;
    if (data.error) {
      state.codeFiles = [];
      $("code-status").textContent = data.error;
    } else {
      $("code-status").textContent = "";
    }
    renderCodeFiles();
  });
}

function renderCodeFiles() {
  if (state.view !== "code") return;
  const list = $("code-files");
  list.innerHTML = "";
  const files = state.codeFiles;
  if (!state.selected) {
    $("code-editor").value = "";
    $("code-status").textContent = "Select a class or namespace first.";
    $("code-save").classList.add("hidden");
    return;
  }
  if (!files.length) {
    $("code-editor").value = "";
    $("code-status").textContent =
      state.codeStatus || "No generated source for this node.";
    return;
  }
  if (state.activeFile >= files.length) state.activeFile = 0;
  if (files.length > 1) {
    files.forEach((f, i) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "file-tab" + (i === state.activeFile ? " active" : "");
      btn.textContent = f.path.split("/").pop();
      btn.title = f.path;
      btn.addEventListener("click", () => { state.activeFile = i; renderCodeFiles(); });
      list.appendChild(btn);
    });
  }
  const f = files[state.activeFile];
  $("code-editor").value = f.text;
  $("code-status").textContent =
    `${f.path}${files.length > 1 ? ` · ${files.length} file(s)` : ""}` +
    (state.codeEditable ? "" : " · read-only (start with --project-dir)");
  $("code-save").classList.toggle("hidden", !state.codeEditable);
}

$("code-save").addEventListener("click", () => {
  if (!state.selected) return;
  // persist the current editor buffer before sending
  if (state.codeFiles[state.activeFile]) {
    state.codeFiles[state.activeFile].text = $("code-editor").value;
  }
  const files = state.codeFiles.map((f) => ({ path: f.path, text: f.text }));
  $("code-status").textContent = "re-indexing…";
  fetch(`/api/node/${encodeURIComponent(state.selected.qname)}/code`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ files }),
  })
    .then((r) => r.json())
    .then((res) => {
      if (res.error) {
        $("code-status").textContent = res.error;
        return;
      }
      const written = (res.written || []).filter((x) => x.ok);
      const total = (res.written || []).length;
      const idx = res.index || {};
      let msg = `wrote ${written.length}/${total} file(s)`;
      if (res.reloaded) msg += " · graph re-parsed & reloaded";
      else if (idx.exit_code && idx.exit_code !== 0) msg += " · re-index failed";
      if (idx.error) msg += ` · ${idx.error}`;
      $("code-status").textContent = msg;
      if (res.reloaded) {
        loadScope(state.selected.qname);
        loadCode(state.selected.qname);
      }
    });
});

// ── Requirements & tests panel ───────────────────────────────────────────

function setTab(tab) {
  state.reqTab = tab;
  $("tab-requirements").classList.toggle("active", tab === "requirements");
  $("tab-tests").classList.toggle("active", tab === "tests");
  $("req-body").classList.toggle("hidden", tab !== "requirements");
  $("test-body").classList.toggle("hidden", tab !== "tests");
  if (tab === "tests") renderTestsTab();
}

$("tab-requirements").addEventListener("click", () => setTab("requirements"));
$("tab-tests").addEventListener("click", () => setTab("tests"));

function clearCoverage() {
  state.coverage = null;
  state.tests = [];
  $("req-body").innerHTML =
    '<div class="canvas-empty muted">Namespaces have no requirement or test scope.</div>';
  $("test-body").innerHTML =
    '<div class="canvas-empty muted">Namespaces have no test scope.</div>';
}

function loadCoverage(qname) {
  api(`/api/node/${encodeURIComponent(qname)}/coverage`).then((data) => {
    state.coverage = data;
    state.tests = flattenTests(data);
    renderRequirements(data);
    renderTestsTab();
  });
}

function flattenTests(data) {
  const seen = new Set();
  const out = [];
  for (const req of data.requirements || []) {
    for (const t of req.tests || []) {
      if (t.qname && seen.has(t.qname)) continue;
      if (t.qname) seen.add(t.qname);
      out.push(t);
    }
  }
  return out;
}

function renderRequirements(data) {
  const body = $("req-body");
  body.innerHTML = "";
  if (!data.requirements.length) {
    body.innerHTML = `<div class="canvas-empty muted">No requirements or
      tests found for this class in the graph.</div>`;
    return;
  }
  for (const req of data.requirements) {
    body.appendChild(requirementCard(req));
  }
}

function renderTestsTab() {
  const body = $("test-body");
  body.innerHTML = "";
  if (!state.selected || state.selected.kind === "namespace") {
    body.innerHTML =
      '<div class="canvas-empty muted">Select a class to browse its tests.</div>';
    return;
  }
  if (!state.tests.length) {
    body.innerHTML =
      '<div class="canvas-empty muted">No tests found for this class.</div>';
    return;
  }
  for (const test of state.tests) {
    body.appendChild(testCard(test));
  }
}

function requirementCard(req) {
  const card = document.createElement("details");
  card.className = "req-card";
  card.open = true;
  const sum = document.createElement("summary");
  sum.textContent = `${req.name} — ${req.tests.length} test${req.tests.length === 1 ? "" : "s"}`;
  card.appendChild(sum);
  const desc = document.createElement("div");
  desc.className = "req-desc";
  desc.textContent = req.description;
  card.appendChild(desc);
  for (const test of req.tests) {
    card.appendChild(testBlock(test));
  }
  return card;
}

function testCard(test) {
  const card = document.createElement("div");
  card.className = "test-card";

  const head = document.createElement("div");
  head.className = "test-card-head";
  const name = document.createElement("span");
  name.className = "test-card-name";
  name.textContent = test.name;
  head.appendChild(name);

  const toggle = document.createElement("span");
  toggle.className = "mini-toggle";
  const bDesc = document.createElement("button");
  bDesc.type = "button";
  bDesc.className = "toggle active";
  bDesc.textContent = "Description";
  const bCode = document.createElement("button");
  bCode.type = "button";
  bCode.className = "toggle";
  bCode.textContent = "Code";
  toggle.append(bDesc, bCode);
  head.appendChild(toggle);
  card.appendChild(head);

  const body = document.createElement("div");
  body.className = "test-card-body";
  const desc = document.createElement("div");
  desc.className = "test-detail-desc";
  desc.appendChild(testBlock(test));
  const code = document.createElement("div");
  code.className = "test-detail-code hidden";
  const pre = document.createElement("pre");
  pre.className = "code-pre";
  pre.textContent = "loading generated test source…";
  code.appendChild(pre);
  body.append(desc, code);
  card.appendChild(body);

  bDesc.addEventListener("click", () => {
    bDesc.classList.add("active"); bCode.classList.remove("active");
    desc.classList.remove("hidden"); code.classList.add("hidden");
  });
  bCode.addEventListener("click", () => {
    bDesc.classList.remove("active"); bCode.classList.add("active");
    desc.classList.add("hidden"); code.classList.remove("hidden");
    if (!code.dataset.loaded) {
      code.dataset.loaded = "1";
      api(`/api/node/${encodeURIComponent(test.qname)}/code`).then((d) => {
        const files = d.files || [];
        pre.textContent = files.map((f) => f.text).join("\n")
          || (d.error || "(no generated source)");
      });
    }
  });

  return card;
}

function testBlock(test) {
  const t = document.createElement("div");
  t.className = "test";
  const title = document.createElement("div");
  title.className = "test-title";
  title.textContent = test.name;
  t.appendChild(title);
  if (test.description) {
    const d = document.createElement("div");
    d.className = "test-desc";
    d.textContent = test.description;
    t.appendChild(d);
  }
  const lists = document.createElement("div");
  lists.className = "test-lists";
  if (test.steps.length) {
    lists.appendChild(listBlock("steps", test.steps, (s) => s.description || s.name));
  }
  if (test.assertions.length) {
    lists.appendChild(listBlock("assertions", test.assertions, (a) => a.condition));
  }
  t.appendChild(lists);
  return t;
}

function listBlock(label, items, text) {
  const wrap = document.createElement("div");
  wrap.className = "sub";
  const lab = document.createElement("div");
  lab.className = "sub-label";
  lab.textContent = label;
  wrap.appendChild(lab);
  const ul = document.createElement("ul");
  for (const item of items) {
    const li = document.createElement("li");
    const txt = text(item);
    if (label === "assertions") {
      const code = document.createElement("span");
      code.className = "cond";
      code.textContent = txt;
      li.appendChild(code);
    } else if (txt !== item.name) {
      const snake = document.createElement("span");
      snake.className = "snake";
      snake.textContent = item.name + ": ";
      li.appendChild(snake);
      li.appendChild(document.createTextNode(txt));
    } else {
      li.textContent = txt;
    }
    ul.appendChild(li);
  }
  wrap.appendChild(ul);
  return wrap;
}

// ── Search ───────────────────────────────────────────────────────────────

let searchTimer = null;
$("search").addEventListener("input", (e) => {
  clearTimeout(searchTimer);
  const q = e.target.value.trim();
  searchTimer = setTimeout(() => {
    api(`/api/namespaces?q=${encodeURIComponent(q)}`).then((r) => {
      if (!state.nsPath.length) {
        renderRoots(r.namespaces);
      }
    });
  }, 250);
});

$("ns-up").addEventListener("click", goUp);

// ── Utils ────────────────────────────────────────────────────────────────

function escapeHtml(s) {
  const div = document.createElement("div");
  div.textContent = s;
  return div.innerHTML;
}

function cssEscape(s) {
  if (window.CSS && CSS.escape) return CSS.escape(s);
  return String(s).replace(/[^a-zA-Z0-9_-]/g, (c) => "\\" + c);
}

// boot: render root namespaces
api("/api/namespaces").then((r) => renderRoots(r.namespaces));
