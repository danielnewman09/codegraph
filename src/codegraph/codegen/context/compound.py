"""Context builders for compound node types (mirrors models/compound.py).

Addresses: ``CompoundNode`` (abstract base — dispatch by kind),
``ClassNode`` (kinds: class / struct / type_parameter), ``InterfaceNode``,
``EnumNode``, ``UnionNode``, ``ConceptNode``, ``ModuleNode``.

Compound context contract (spec's render-context section): ``type``,
``kind``, ``name``, ``qualified_name``, ``visibility``,
``brief``/``detailed``, ``is_final``, ``is_abstract``, ``template_params``
(TEMPLATE_PARAM refs), ``bases`` (INHERITS_FROM), ``interfaces``
(REALIZES), ``sections`` (COMPOSES children grouped by visibility,
declaration order), ``file_path``/``line_number``.  Enum adds ``values``;
concept carries ``initializer``.
"""

from __future__ import annotations

import re

from codegraph.codegen.context import base, member
from codegraph.codegen import typeref

#: Compound node types this module addresses (mirrors models/compound.py;
#: consumed by the BUILDERS registry + completeness gate).
NODE_TYPES: tuple[str, ...] = (
    "CompoundNode",  # abstract base — dispatch by kind
    "ClassNode",
    "InterfaceNode",
    "EnumNode",
    "UnionNode",
    "ConceptNode",
    "ModuleNode",
)


def build_context(entry, state) -> dict | None:
    """Build the compound context dict for *entry*.

    Args:
        entry: CompositeEntry whose node is a compound type.
        state: BuildState (reference resolution).

    Returns:
        Compound context dict, or ``None`` for unknown compound kinds.
    """
    node_type = type(entry.node).__name__
    if node_type == "EnumNode":
        return _build_enum(entry, state)
    if node_type == "ConceptNode":
        return _build_concept(entry, state)
    if node_type in ("ClassNode", "InterfaceNode", "UnionNode",
                     "CompoundNode", "ModuleNode"):
        return _build_class_like(entry, state)
    return None


def _build_child(child_entry, state, *, parent_name: str, parent_qname: str) -> dict | None:
    """Build a composed child context (member or nested compound)."""
    child_type = type(child_entry.node).__name__
    if child_type in base.MEMBER_TYPES:
        return member.build_context(
            child_entry, state, parent_name=parent_name, parent_qname=parent_qname
        )
    if child_type in base.COMPOUND_TYPES:
        return build_context(child_entry, state)
    return None


def _build_class_like(entry, state) -> dict:
    node = entry.node
    node_type = type(node).__name__
    kind = node.kind or "class"
    parent_qname = node.qualified_name or ""

    spec = _spec_info(entry)
    name = (spec["base"] if spec else node.name) or ""

    sections: list[dict] = []
    for visibility, items in base.bucket_by_visibility(base.ordered_children(entry)):
        members: list[dict] = []
        for child_type, _key, child in items:
            ctx = _build_child(
                child, state, parent_name=name, parent_qname=parent_qname
            )
            if ctx is not None:
                members.append(ctx)
        sections.append({"access": visibility, "members": members})

    return {
        "type": node_type,
        "kind": kind,
        "name": name,
        "qualified_name": node.qualified_name or "",
        "uid": node.uid or "",
        "visibility": base.normalize_visibility(node.visibility),
        "brief": node.brief_description or "",
        "detailed": node.detailed_description or "",
        "is_final": bool(getattr(node, "is_final", False)),
        "is_abstract": bool(getattr(node, "is_abstract", False)),
        "template_params": _template_params(entry, state) or (spec["params"] if spec else []),
        "template_args": spec["args"] if spec else "",
        "bases": _bases(entry, state),
        "interfaces": _interfaces(entry, state),
        "forward_decls": _forward_decls(entry, state),
        "sections": sections,
        "file_path": node.file_path or "",
        "line_number": node.line_number or 0,
    }


def _spec_info(entry) -> dict | None:
    """Template-specialization info for a compound, best-effort (Phase 2).

    The graph carries no TEMPLATE_PARAM edges (both pipelines drop them
    from serialized exports), but specialization compounds appear with
    the arguments baked into the qname
    (``cpp_sqlite::IsForeignKeyT< ForeignKey< T > >``).  We derive:

    - ``base`` — the class name without the ``<...>`` (``IsForeignKeyT``),
    - ``args`` — the normalized argument list (``<ForeignKey<T>>``),
    - ``params`` — free variables in the args, as ``typename`` slots
      (``T``), so the output is valid partial-specialization C++.

    Constraints (``template <ValidTransferObject T>``) are not derivable
    from the args — a documented degradation (D6-style).
    """
    qn = entry.node.qualified_name or ""
    parts = typeref.scope_parts(qn)
    last = parts[-1] if parts else qn
    open_idx = last.find("<")
    if open_idx == -1:
        return None
    base = last[:open_idx].strip()
    args = last[open_idx:]
    free = typeref.free_template_vars(args)
    params = [
        {"kind": "typename", "name": v, "default": "", "concept": ""}
        for v in free
    ]
    return {
        "base": base,
        "args": typeref.normalize_declaration(args),
        "params": params,
    }


def _forward_decls(entry, state) -> list[dict]:
    """DEPENDS_ON targets → forward declarations (Phase 2).

    A class header forward-declares the classes it depends on so the
    header is self-contained for pointer/ref members.  Excluded:
    - non-class kinds (plain enums can't be forward-declared; concepts
      and std:: library references are never synthesized as files);
    - the class itself;
    - composed children (D9 nested-dups like MigrationManager's
      MigrationResult/SchemaVerificationResult are defined in this very
      header — forward-declaring them would be a redefinition).

    Same-namespace targets are emitted unqualified; cross-namespace
    targets keep their qualified name.  Ordered by name (R4).
    """
    decls: dict[str, dict] = {}
    if state is None:
        return []
    own_qn = entry.node.qualified_name or ""
    own_uid = getattr(entry.node, "uid", None)
    own_ns = own_qn.rsplit("::", 1)[0] if "::" in own_qn else ""

    # D9: composed children are defined in this header — never forward-
    # declared (their uid matches a DEPENDS_ON target).
    child_uids = {
        getattr(child.node, "uid", None)
        for _child_type, _key, child in base.ordered_children(entry)
    }

    for relation_type, target_key, _target_type in entry.references:
        if relation_type != "DEPENDS_ON":
            continue
        target = state.flat.get(target_key)
        if target is None:
            continue
        t = target.node
        t_uid = getattr(t, "uid", None)
        t_qn = getattr(t, "qualified_name", "") or ""
        t_kind = getattr(t, "kind", "") or "class"
        if t_kind not in ("class", "struct", "interface"):
            continue
        if t_uid in (own_uid, None) or t_uid in child_uids:
            continue
        if t_qn.startswith("std::") or not t_qn:
            continue
        t_ns = t_qn.rsplit("::", 1)[0] if "::" in t_qn else ""
        name = t_qn.rsplit("::", 1)[-1] if t_ns == own_ns else t_qn
        decls[name] = {"name": name, "kind": "struct" if t_kind == "struct" else "class"}
    return [decls[name] for name in sorted(decls)]


def _template_params(entry, state) -> list[dict]:
    """TEMPLATE_PARAM references → template parameter slots.

    Phase 1: name + kind only (the edge properties — position, defval —
    are not carried in LayerGraph references); ``default``/``concept``
    are Phase 2.
    """
    params: list[dict] = []
    if state is None:
        return params
    for relation_type, target_key, _target_type in entry.references:
        if relation_type != "TEMPLATE_PARAM":
            continue
        target = state.flat.get(target_key)
        if target is None:
            continue
        t = target.node
        params.append({
            "name": getattr(t, "name", "") or "",
            "kind": getattr(t, "kind", "") or "typename",
            "default": "",
            "concept": "",
        })
    return params


def _bases(entry, state) -> list[dict]:
    """INHERITS_FROM references → base list.

    Phase 1 default: ``access: "public"``, ``virtual: False`` — edge
    properties are Phase 2 (spec gap 4).
    """
    bases: list[dict] = []
    for relation_type, target_key, _target_type in entry.references:
        if relation_type != "INHERITS_FROM":
            continue
        bases.append({
            "name": base.resolve_display_name(state, target_key),
            "access": "public",
            "virtual": False,
        })
    return bases


def _interfaces(entry, state) -> list[dict]:
    """REALIZES references → interface list."""
    interfaces: list[dict] = []
    for relation_type, target_key, _target_type in entry.references:
        if relation_type != "REALIZES":
            continue
        interfaces.append({"name": base.resolve_display_name(state, target_key)})
    return interfaces


def _build_enum(entry, state) -> dict:
    node = entry.node
    values: list[dict] = []
    for child_type, _key, child in base.ordered_children(entry):
        if child_type == "EnumValueNode":
            ctx = member.build_context(child, state)
            if ctx is not None:
                values.append(ctx)
    return {
        "type": "EnumNode",
        "kind": node.kind or "enum",
        "name": node.name or "",
        "qualified_name": node.qualified_name or "",
        "uid": node.uid or "",
        "visibility": base.normalize_visibility(node.visibility),
        "brief": node.brief_description or "",
        "detailed": node.detailed_description or "",
        # ``enumerators`` (not ``values``) — ``node.values`` would resolve
        # to ``dict.values`` in Jinja2 templates.
        "enumerators": values,
        "file_path": node.file_path or "",
        "line_number": node.line_number or 0,
    }


def _build_concept(entry, state) -> dict:
    node = entry.node
    qn = node.qualified_name or ""
    initializer = node.initializer or ""
    ns_prefix = qn.rsplit("::", 1)[0] + "::" if "::" in qn else ""
    if ns_prefix:
        # The initializer stores the fully-qualified concept name
        # ("template<...> concept cpp_sqlite::Foo = ...").  Inside the
        # namespace the qualification is redundant AND confuses doxygen
        # (a qualified concept definition emits no compound — so the
        # concept would never round-trip).  Strip it.
        initializer = re.sub(
            rf"\bconcept\s+{re.escape(ns_prefix)}",
            "concept ",
            initializer,
            count=1,
        )
    return {
        "type": "ConceptNode",
        "kind": node.kind or "concept",
        "name": node.name or "",
        "qualified_name": qn,
        "uid": node.uid or "",
        "visibility": base.normalize_visibility(node.visibility),
        "brief": node.brief_description or "",
        "detailed": node.detailed_description or "",
        "initializer": initializer,
        "file_path": node.file_path or "",
        "line_number": node.line_number or 0,
    }
