/* Codegraph Explorer — namespace header + dropdown tree, two panels,
   zoomable SVG. */

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
  // namespace drill path (root view when empty)
  nsPath: [],
  children: {},     // qname -> children payload
  selected: null,   // selected class qname
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
function isRequirement(node) {
  return node.kind === "HLR" || node.kind === "LLR";
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
  state.selected = null;
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
  showHeader(nsQname, state.nsPath.length > 1);
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
      const h = sectionLabel("classes");
      tree.appendChild(h);
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
  markSelected(nsQname);
  $("breadcrumb").textContent = nsQname;
  $("selection-info").textContent = "namespace — as-built view";
  loadScope(nsQname);
}

function selectClass(node) {
  state.selected = node.qname;
  markSelected(node.qname);
  $("breadcrumb").textContent = node.qname;
  $("selection-info").textContent =
    node.requirements !== undefined
      ? `${node.requirements} requirement(s) · ${node.tests} test(s) validate this class`
      : "";
  // two windows in parallel
  loadScope(node.qname);
  loadCoverage(node.qname);
}

function selectRequirement(node) {
  markSelected(node.qname);
  $("breadcrumb").textContent = node.qname;
  $("selection-info").textContent =
    `requirement · ${node.test_count} test(s)`;
  $("req-body").innerHTML = "";
  const hint = document.createElement("div");
  hint.className = "canvas-empty muted";
  hint.textContent =
    `Select a class beneath this requirement to see its tests in detail.`;
  $("req-body").appendChild(hint);
}

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

// ── Requirements & tests window ──────────────────────────────────────────

function loadCoverage(qname) {
  api(`/api/node/${encodeURIComponent(qname)}/coverage`).then((data) => {
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
  });
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
