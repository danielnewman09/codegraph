"""Shared fixtures for per-builder context tests.

Codegen context tests are pure Python (D2): they deserialize small
hand-built graph dicts into LayerGraphs (no backend) and call the
builders directly with a fresh BuildState.
"""

from __future__ import annotations

import pytest

from codegraph.codegen.context import BuildState
from codegraph.graph import LayerGraph
from codegraph.models.tags import CodeGraphNode


def key_document(data):
    """WP A/B: assign canonical keys to hand-built graph dicts before
    deserialize (canonical-only).  Parent-relative children use their
    parent's key; parents are resolved from the ``composes`` nesting.
    Mutates and returns *data*.
    """
    from codegraph.identity import IdentityScope, resolve_identity_for
    from codegraph.identity.registry import parent_relative_fields

    scope = IdentityScope.repository("codegraph-suite", "codegraph")

    def key_of(entry):
        node_type = entry.get("node_type") or entry.get("type") or ""
        if node_type not in CodeGraphNode._registry:
            node_type = entry.get("type") or ""
        qn = entry.get("qualified_name") or entry.get("name") or entry.get("path") or ""
        cls = CodeGraphNode._registry.get(node_type)
        if cls is None:
            return ""
        probe_kwargs = {}
        for ident_field in (
            "position", "start_line", "end_line", "kind",
            "argsstring", "operator", "phase", "order",
        ):
            if ident_field in entry and ident_field != "qualified_name":
                probe_kwargs[ident_field] = entry[ident_field]
        path_arg = entry.get("path") if entry.get("path") else qn
        probe = cls(
            qualified_name=qn,
            name=qn.rsplit("::", 1)[-1] if "::" in qn else qn,
            path=path_arg,
            source="test",
            **probe_kwargs,
        )
        parents = {}
        for f in parent_relative_fields(cls) or ():
            parents[f] = entry.get(f) or "cg:v1:root"
        return resolve_identity_for(probe, scope, parents=parents).key()

    def walk(entries, parent_key=None):
        for entry in entries:
            entry["canonical_key"] = key_of(entry)
            for child in entry.get("composes", []) or []:
                child["parent_key"] = entry["canonical_key"]
                walk([child])

    walk(data)

    # Rewrite edge refs: legacy ``target_uid`` (a hand-built local id OR
    # the target's qualified_name) → the target's canonical ``target_key``
    # (WP B).
    uid_to_key = {}
    qname_to_key = {}
    path_to_key = {}
    for entry in _iter_entries(data):
        legacy = entry.get("uid") or ""
        if legacy:
            uid_to_key[legacy] = entry["canonical_key"]
        qn = entry.get("qualified_name") or ""
        if qn:
            qname_to_key[qn] = entry["canonical_key"]
        path = entry.get("path") or ""
        if path:
            path_to_key[path] = entry["canonical_key"]
    for entry in _iter_entries(data):
        for edge in entry.get("edges", []) or []:
            ref = edge.get("target_uid") or edge.get("target_local_id") or ""
            key = uid_to_key.get(ref) or qname_to_key.get(ref) or path_to_key.get(ref)
            if not key and str(ref).startswith("cg:v1:"):
                key = ref  # already a canonical key
            if key:
                edge["target_key"] = key
                edge.pop("target_uid", None)
                edge.pop("target_local_id", None)
    return data


def _iter_entries(data):
    for entry in data:
        yield entry
        yield from _iter_entries(entry.get("composes", []) or [])


@pytest.fixture
def deserialize_graph():
    def _deserialize(data):
        return LayerGraph.deserialize(key_document(data))

    return _deserialize


@pytest.fixture
def make_state(deserialize_graph):
    def _make(data):
        graph = deserialize_graph(data)
        return graph, BuildState(graph=graph, flat=graph._flat_index())

    return _make


@pytest.fixture
def find_entry():
    def _find(graph, *, type_name=None, name=None):
        for entry in graph._all_entries():
            if type_name and type(entry.node).__name__ != type_name:
                continue
            if name and entry.node.name != name:
                continue
            return entry
        raise LookupError(f"entry not found: type={type_name} name={name}")

    return _find


def node_dict(**overrides):
    """Base serialized-node dict with identity fields pre-filled."""
    data = {
        "type": "ClassNode",
        "name": "Thing",
        "qualified_name": "ns::Thing",
        "kind": "class",
        "source": "test",
        "tags": ["design"],
    }
    data.update(overrides)
    return data
