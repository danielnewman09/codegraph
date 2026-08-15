"""Explorer query layer — namespace tree, class scope, coverage.

Backend-agnostic: every query function works against a
:class:`GraphSource`, a thin protocol that returns plain dicts.  The
demo implementation wraps any :class:`LayerGraph`
(:class:`LayerGraphSource`); a live-backend implementation
(``bulk_load_by_tag`` / repository queries) can be added later without
touching the API layer.

Reuses the exact same test→class matching as the PlantUML and Markdown
exporters (:mod:`codegraph.export.verification`) and the condition
renderer (:mod:`codegraph.export.coverage`) — the tree badges, the
scoped SVG, and the coverage narration can never disagree.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from codegraph.export.coverage import _render_condition, _truncate
from codegraph.export.verification import compute_verification_scope
from codegraph.graph import LayerGraph

# Node kinds surfaced in the tree (strictly: namespaces, classes,
# requirements — no members, no test scaffolding, no internal tags).
_TREE_NAMESPACE_TYPES = frozenset({"NamespaceNode", "ModuleNode"})
# Only ClassNode-labeled objects appear in the tree's class list
# (no interfaces, enums, concepts, functions, defines — per direction).
_TREE_CLASS_TYPES = frozenset({"ClassNode"})
_REQUIREMENT_TYPES = frozenset({"HLR", "LLR"})

# Internal scaffolding never shown in the UI (test nodes, steps,
# assertions, literals, root orphan stubs).
_SKIP_TYPES = frozenset({
    "TestNode", "TestStepNode", "AssertionNode", "TestFixtureNode",
    "LiteralNode", "ParameterNode", "FileNode",
})


class GraphSource(Protocol):
    """Query surface the server exposes.  Implementations return plain
    dicts (JSON-serializable)."""

    def meta(self) -> dict:
        """Project metadata: name, tags, counts."""

    def namespaces(self, query: str) -> list[dict]:
        """Root namespace summaries, optionally filtered by *query*."""

    def children(self, qname: str) -> dict:
        """One level of the tree for *qname*: ``{namespaces, classes,
        requirements}``."""

    def scope(self, qname: str) -> dict:
        """Class-scoped PlantUML text for *qname* (``{"puml": str}``)."""

    def coverage(self, qname: str) -> dict:
        """Verification scope for *qname*: requirements + tests +
        derived conditions (``{"requirements": [...], "counts": {...}}``)."""


# ── LayerGraph-backed source (fixture / live backend load) ─────────────────


@dataclass
class LayerGraphSource:
    """A :class:`GraphSource` over an in-memory :class:`LayerGraph`."""

    graph: LayerGraph
    source_name: str = "LayerGraph"

    # ---- helpers -----------------------------------------------------

    def _entry(self, qname: str):
        for entry in self.graph._all_entries():
            e_qn = getattr(entry.node, "qualified_name", None) or entry.node.name
            if e_qn == qname:
                return entry
        return None

    def _summary(self, entry) -> dict:
        node = entry.node
        qn = getattr(node, "qualified_name", None) or node.name
        name = getattr(node, "name", "") or qn
        if name == qn and "::" in qn:
            name = qn.rsplit("::", 1)[-1]
        return {
            "qname": qn,
            "name": name,
            "kind": type(node).__name__,
        }

    def _tree_children(self, entry) -> list:
        """Non-member children of *entry*, in tree order."""
        out: list = []
        for type_children in entry.children.values():
            for child_entry in type_children.values():
                node_type = type(child_entry.node).__name__
                if node_type in _TREE_NAMESPACE_TYPES | _TREE_CLASS_TYPES:
                    out.append(child_entry)
        return out

    # ---- verification scope helpers --------------------------------

    def _scopes(self) -> dict[str, object]:
        """Verification scope per tree class, cached."""
        if not hasattr(self, "_scopes_cache"):
            cache: dict[str, object] = {}
            for entry in self.graph._all_entries():
                node_type = type(entry.node).__name__
                if node_type not in _TREE_CLASS_TYPES:
                    continue
                qn = getattr(entry.node, "qualified_name", None) or entry.node.name
                allowed = {qn}
                try:
                    cache[qn] = compute_verification_scope(
                        self.graph, qn, allowed
                    )
                except ValueError:
                    continue
            self._scopes_cache = cache
        return self._scopes_cache

    def _requirements_for_namespace(self, ns_qname: str) -> list[dict]:
        """Requirements (HLR/LLR) whose verification scope touches this
        namespace or its classes."""
        entry = self._entry(ns_qname)
        if entry is None:
            return []
        class_qnames: list[str] = [
            (getattr(e.node, "qualified_name", None) or e.node.name)
            for e in self._tree_children(entry)
            if type(e.node).__name__ in _TREE_CLASS_TYPES
        ]
        req_map: dict[str, dict] = {}
        for cq in class_qnames:
            scope = self._scopes().get(cq)
            if scope is None:
                continue
            for req_qname in scope.reqs:
                req_entry = self._entry(req_qname)
                if req_entry is None:
                    continue
                node = req_entry.node
                req_map.setdefault(req_qname, {
                    "qname": req_qname,
                    "name": getattr(node, "name", "") or req_qname,
                    "kind": type(node).__name__,
                    "description": _truncate(
                        getattr(node, "description", "") or "", 160
                    ),
                    "test_count": sum(
                        1 for t in scope.tests
                        if scope.parents.get(t) == req_qname
                    ),
                })
        return sorted(req_map.values(), key=lambda r: r["qname"])

    # ---- GraphSource -------------------------------------------------

    def meta(self) -> dict:
        tags = sorted(self.graph.tags)
        counts: dict[str, int] = {}
        for entry in self.graph._all_entries():
            t = type(entry.node).__name__
            counts[t] = counts.get(t, 0) + 1
        return {
            "source": self.source_name,
            "tags": tags,
            "counts": counts,
        }

    def namespaces(self, query: str = "") -> list[dict]:
        out: list[dict] = []
        for entry in self.graph.entries.values():
            node_type = type(entry.node).__name__
            if node_type not in _TREE_NAMESPACE_TYPES:
                continue
            qn = getattr(entry.node, "qualified_name", None) or entry.node.name
            if query and query.lower() not in qn.lower():
                continue
            out.append(self._summary(entry))
        return sorted(out, key=lambda n: n["qname"])

    def children(self, qname: str) -> dict:
        entry = self._entry(qname)
        if entry is None:
            return {
                "qname": qname,
                "parent": None,
                "namespaces": [], "classes": [], "requirements": [],
            }
        namespaces: list[dict] = []
        classes: list[dict] = []
        for child in self._tree_children(entry):
            if type(child.node).__name__ in _TREE_NAMESPACE_TYPES:
                namespaces.append(self._summary(child))
            else:
                classes.append(self._summary(child))
        # badge counts per class from verification scopes
        for cls in classes:
            scope = self._scopes().get(cls["qname"])
            cls["requirements"] = len(scope.reqs) if scope else 0
            cls["tests"] = len(scope.tests) if scope else 0
        requirements = self._requirements_for_namespace(qname)
        namespaces.sort(key=lambda n: n["qname"])
        classes.sort(key=lambda c: c["name"])
        return {
            "qname": qname,
            "parent": self._parent_of(qname),
            "namespaces": namespaces,
            "classes": classes,
            "requirements": requirements,
        }

    def _parent_of(self, qname: str) -> str | None:
        """Parent namespace of *qname* (COMPOSES parent that is a
        namespace), for the tree's "up" navigation."""
        for entry in self.graph._all_entries():
            for type_children in entry.children.values():
                for child_entry in type_children.values():
                    cq = (
                        getattr(child_entry.node, "qualified_name", None)
                        or child_entry.node.name
                    )
                    if cq == qname and type(entry.node).__name__ in (
                        "NamespaceNode", "ModuleNode"
                    ):
                        return (
                            getattr(entry.node, "qualified_name", None)
                            or entry.node.name
                        )
        return None

    def scope(self, qname: str) -> dict:
        """Rendered view for *qname*: class-scoped diagram (class +
        1-hop neighbours, NO test/requirement scaffolding — those live
        in the requirements & tests panel) for classes, namespace-scoped
        as-built view for namespaces."""
        from codegraph.export.plantuml import (
            GraphView, export_plantuml,
        )
        entry = self._entry(qname)
        if entry is None:
            return {"puml": "", "error": f"{qname!r} not found in graph"}
        if type(entry.node).__name__ in _TREE_NAMESPACE_TYPES:
            # namespace view: the namespace's own subtree, externals
            # collapsed into packages
            sub = LayerGraph(
                tags=self.graph.tags, entries={qname: entry}
            )
            try:
                puml = export_plantuml(sub, view=GraphView.COLLAPSED)
            except Exception as exc:  # noqa: BLE001 — endpoint must not 500 on odd data
                return {"puml": "", "error": f"render failed: {exc}"}
            return {"puml": puml}
        try:
            puml = export_plantuml(
                self.graph,
                view="full",
                scope_class=qname,
                include_verification=False,
            )
        except ValueError:
            return {"puml": "", "error": f"scope class {qname!r} not found"}
        return {"puml": puml}

    def coverage(self, qname: str) -> dict:
        from codegraph.export.plantuml import PlantUMLExporter
        try:
            allowed = PlantUMLExporter(
                self.graph, scope_class=qname
            ).scoped_allowed_classes()
        except ValueError:
            return {"requirements": [], "counts": {"requirements": 0, "tests": 0}}
        scope = compute_verification_scope(self.graph, qname, allowed)

        requirements: list[dict] = []
        grouped: set[str] = set()
        for req_qname in sorted(scope.reqs):
            # only requirement nodes that directly own tests (LLRs) or
            # wrap them (HLRs) — include those with tests beneath them
            owns_tests = any(
                scope.parents.get(t) == req_qname for t in scope.tests
            )
            req_entry = self._entry(req_qname)
            if req_entry is None or not owns_tests:
                continue
            tests: list[dict] = []
            for test_qname in sorted(scope.tests):
                if scope.parents.get(test_qname) != req_qname:
                    continue
                grouped.add(test_qname)
                test_entry = self._entry(test_qname)
                if test_entry is None:
                    continue
                tests.append(self._test_payload(test_entry))
            requirements.append({
                "qname": req_qname,
                "name": getattr(req_entry.node, "name", "") or req_qname,
                "description": getattr(req_entry.node, "description", "") or "",
                "tests": tests,
            })

        # As-built graphs have no HLR/LLR nodes — tests hang directly
        # off namespaces/roots.  Group them under a synthetic
        # "Tests" section so the panel still surfaces them.
        ungrouped = [
            t for t in scope.tests
            if t not in grouped
            and (scope.parents.get(t) not in scope.reqs)
        ]
        if ungrouped:
            tests: list[dict] = []
            for test_qname in sorted(ungrouped):
                test_entry = self._entry(test_qname)
                if test_entry is None:
                    continue
                tests.append(self._test_payload(test_entry))
            requirements.append({
                "qname": "",
                "name": "Tests (no requirement)",
                "description": "",
                "tests": tests,
            })
        return {
            "class": {"qname": qname, "name": qname.rsplit("::", 1)[-1]},
            "requirements": requirements,
            "counts": {
                "requirements": len(requirements),
                "tests": len(scope.tests),
            },
        }

    def _test_payload(self, test_entry) -> dict:
        node = test_entry.node
        steps: list[dict] = []
        for step in sorted(
            test_entry.children.get("TestStepNode", {}).values(),
            key=lambda e: getattr(e.node, "order", 0),
        ):
            steps.append({
                "name": step.node.name,
                "description": getattr(step.node, "description", "") or "",
            })
        assertions: list[dict] = []
        for a in sorted(
            test_entry.children.get("AssertionNode", {}).values(),
            key=lambda e: getattr(e.node, "order", 0),
        ):
            assertions.append({
                "name": a.node.name,
                "condition": _render_condition(self.graph, a),
            })
        return {
            "qname": getattr(node, "qualified_name", None) or node.name,
            "name": getattr(node, "name", "") or "",
            "description": getattr(node, "description", "") or "",
            "steps": steps,
            "assertions": assertions,
        }
