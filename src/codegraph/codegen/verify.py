"""Round-trip verification — export → parse → diff (D7, two-tier).

Tier 1 (Phase 1) — compound-level identity subset
    ``design_compounds ⊆ as_built_compounds`` by **qualified name**.
    uid equality is source-dependent (uids hash ``source`` — the design
    graph is ``markdown-import``, the parse is the project name), so the
    stable cross-graph identity is the qualified name.  Compounds are
    unambiguous: no argsstring in their identity.

    The design-side set excludes what codegen provably does not emit:
    - ``std::``-prefixed library references (never synthesized as files);
    - template-slot compounds (``<`` in the qualified name — the
      design fixture's ``IsVector< std::vector< T, Allocator > >`` etc.
      render inline in ``template<...>`` clauses, never as files);
    - duplicate-uid placements (D9: a struct nested in a parent AND
      peering under the namespace — the emitted code resolves the
      placement one way, so the qname may legitimately differ in the
      parse; reported as ``ambiguous`` drift, not asserted).

Tier 2 (Phase 2) — exact method uids
    Method-level equality by **canonical signature key**
    ``(scope, name) → (canonical params, canonical qualifiers)``.
    Design declarations come from ``type_signature`` (full or
    decl-minus-qualifiers encoding); as-built from ``argsstring`` + the
    qname suffix the parse glues on (``apply()``, ``getVersion(())``).
    ``signature.canonical_argsstring`` / ``canonical_qualifiers``
    normalize spacing, param names, defaults, and ``= default`` vs
    ``=default`` so the degraded design encoding matches doxygen's.
    Canonicalization is used **only** for diffing — never for storage
    or uid hashing.  Missing methods are drift; the round-trip test
    asserts them empty.

The ``verify`` CLI subcommand (``codegraph-codegen verify``) runs the
loop: codegen a design graph → write tree → doxygen-index parse → load
as-built → compare.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from codegraph.codegen.signature import (
    args_qualifiers,
    canonical_argsstring,
    canonical_qualifiers,
    split_argsstring,
    split_declaration,
)

#: Compound kinds verified by Tier 1.
_COMPOUND_KINDS = frozenset({
    "ClassNode", "InterfaceNode", "EnumNode", "UnionNode", "ConceptNode",
})


@dataclass
class VerifyReport:
    """Result of a round-trip uid diff.

    Attributes:
        tier: ``1`` or ``2``.
        missing: Design compounds (of the verified kinds) absent from
            the as-built graph — the Tier-1 drift; asserted empty by the
            round-trip test.
        extra: As-built compounds not in the design (informational —
            the generated tree carries real C++ scoping).
        ambiguous: Design compounds excluded from the assert because
            their uid occurs at multiple nesting depths (D9 placement —
            informational).
        template_slots: Design compounds excluded because they are
            template slots (never emitted — informational).
        kinds_checked: The compound kinds included in ``missing``/``extra``.
        missing_methods: Tier 2 — design methods absent from the
            as-built graph (or with a non-matching canonical signature),
            as ``scope::name`` — asserted empty by the round-trip test.
        extra_methods: Tier 2 — as-built methods not in the design
            (informational — the parse adds real scoping).
        drift_methods: Tier 2 — methods present on both sides with
            differing canonical signatures (informational).
    """

    tier: int = 1
    missing: list[str] = field(default_factory=list)
    extra: list[str] = field(default_factory=list)
    ambiguous: list[str] = field(default_factory=list)
    template_slots: list[str] = field(default_factory=list)
    kinds_checked: frozenset[str] = _COMPOUND_KINDS
    missing_methods: list[str] = field(default_factory=list)
    extra_methods: list[str] = field(default_factory=list)
    drift_methods: list[str] = field(default_factory=list)

    def summarize(self) -> str:
        parts = [f"tier {self.tier}", f"missing={len(self.missing)}"]
        if self.extra:
            parts.append(f"extra={len(self.extra)}")
        if self.ambiguous:
            parts.append(f"ambiguous={len(self.ambiguous)}")
        if self.template_slots:
            parts.append(f"slots={len(self.template_slots)}")
        if self.missing_methods:
            parts.append(f"methods_missing={len(self.missing_methods)}")
        if self.extra_methods:
            parts.append(f"methods_extra={len(self.extra_methods)}")
        if self.drift_methods:
            parts.append(f"methods_drift={len(self.drift_methods)}")
        return "; ".join(parts)


def _compound_qnames(graph, kinds: frozenset[str]) -> set[str]:
    """Qualified names of compound nodes in *graph* with the given kinds."""
    qnames: set[str] = set()
    for entry in graph._all_entries():
        if type(entry.node).__name__ not in kinds:
            continue
        qn = getattr(entry.node, "qualified_name", "") or ""
        if qn:
            qnames.add(qn)
    return qnames


def _uid_counts(graph) -> dict[str, int]:
    counts: dict[str, int] = {}
    for entry in graph._all_entries():
        uid = getattr(entry.node, "uid", None)
        if uid:
            counts[uid] = counts.get(uid, 0) + 1
    return counts


def _method_scope(qualified_name: str, name: str) -> str:
    """Enclosing scope of a method from its stored qualified name.

    Strips the trailing parenthesized args suffix the parse glues on
    (``apply()``, ``getVersion(())``) and the final ``::name`` segment,
    so both encodings key to the enclosing compound:

    ``cpp_sqlite::Migration::getVersion(())`` + ``getVersion`` →
    ``cpp_sqlite::Migration``.
    """
    qn = qualified_name.strip()
    m = re.search(r"\(.*\)$", qn)
    if m:
        qn = qn[:m.start()].strip()
    if name and qn.endswith("::" + name):
        qn = qn[: -(len(name) + 2)]
    return qn


def _method_signature(node) -> tuple[str, str] | None:
    """Canonical (params, qualifiers) for one method node.

    Design: ``type_signature`` carries the full or decl-minus-qualifiers
    declaration (``'void up(Transaction& txn)'``) — split it; fall back
    to the degraded argsstring when it holds the params.  As-built:
    ``type_signature`` is return-type-only and ``argsstring`` holds the
    params + trailing qualifiers.

    Returns ``None`` when the node carries no signature at all.
    """
    ts = (getattr(node, "type_signature", "") or "").strip()
    args = (getattr(node, "argsstring", "") or "").strip()

    if "(" in ts:
        parts = split_declaration(ts)
        params = canonical_argsstring(
            "(" + ", ".join(
                (p.get("type", "") + (" " + p["name"] if p.get("name") else ""))
                for p in parts.params
            ) + ")" if parts.params else "()"
        )
        quals = canonical_qualifiers(parts.qualifiers)
    elif args:
        params = canonical_argsstring(args)
        quals = canonical_qualifiers(args_qualifiers(args))
    else:
        return None
    return params, quals


def _method_keys(graph) -> dict[tuple[str, str], tuple[str, str]]:
    """Canonical method keys of *graph*: ``(scope, name) → (params, quals)``."""
    keys: dict[tuple[str, str], tuple[str, str]] = {}
    for entry in graph._all_entries():
        if type(entry.node).__name__ != "MethodNode":
            continue
        node = entry.node
        name = (getattr(node, "name", "") or "").strip()
        qn = getattr(node, "qualified_name", "") or ""
        if not name or not qn:
            continue
        sig = _method_signature(node)
        if sig is None:
            continue
        keys[(_method_scope(qn, name), name)] = sig
    return keys


def verify(
    design_graph,
    as_built_graph,
    *,
    tier: int = 1,
    kinds: frozenset[str] | None = None,
) -> VerifyReport:
    """Diff *design_graph* against *as_built_graph* (Tier 1 by default).

    Args:
        design_graph: The design LayerGraph (codegen input).
        as_built_graph: The LayerGraph parsed back from generated code.
        tier: 1 (compound qname subset) or 2 (canonical method uids).
        kinds: Compound kinds to verify (default: class/interface/enum/
            union/concept).

    Returns:
        VerifyReport; for Tier 1 ``missing == []`` is the pass
        criterion, for Tier 2 ``missing_methods == []``.
    """
    if tier == 2:
        return _verify_tier2(design_graph, as_built_graph)
    if tier != 1:
        raise NotImplementedError(f"unknown verification tier: {tier}")

    kinds = kinds or _COMPOUND_KINDS
    design = _compound_qnames(design_graph, kinds)
    as_built = _compound_qnames(as_built_graph, kinds)

    template_slots = sorted(
        qn for qn in design if "<" in qn or qn.startswith("std::")
    )
    design = design - set(template_slots)

    # D9: duplicate-uid placements are ambiguous — exclude from the assert.
    dup_uids = {uid for uid, count in _uid_counts(design_graph).items() if count > 1}
    ambiguous: set[str] = set()
    if dup_uids:
        uid_to_qname: dict[str, str] = {}
        for entry in design_graph._all_entries():
            uid = getattr(entry.node, "uid", None)
            qn = getattr(entry.node, "qualified_name", "") or ""
            if uid in dup_uids and qn:
                uid_to_qname[uid] = qn
        ambiguous = set(uid_to_qname.values()) & design
        design = design - ambiguous

    return VerifyReport(
        tier=1,
        missing=sorted(design - as_built),
        extra=sorted(as_built - design),
        ambiguous=sorted(ambiguous),
        template_slots=template_slots,
        kinds_checked=frozenset(kinds),
    )


def _verify_tier2(design_graph, as_built_graph) -> VerifyReport:
    """Tier 2: design method uids ⊆ as-built by canonical signature.

    Both graphs carry 13 methods in the golden loop; the key
    ``(scope, name) → (canonical params, canonical qualifiers)``
    reconciles the design's decl-minus-qualifiers ``type_signature``
    with the parse's argsstring + glued qname suffix.
    """
    design = _method_keys(design_graph)
    as_built = _method_keys(as_built_graph)

    missing: list[str] = []
    drift: list[str] = []
    for key in sorted(design):
        label = "::".join(key)
        if key not in as_built:
            missing.append(label)
        elif as_built[key] != design[key]:
            drift.append(label)
    extra = sorted(set(as_built) - set(design))

    return VerifyReport(
        tier=2,
        missing_methods=missing,
        extra_methods=["::".join(k) for k in extra],
        drift_methods=drift,
    )


__all__ = ["VerifyReport", "verify"]
