"""Context builders for member node types (mirrors models/member.py).

Addresses: ``MemberNode`` (abstract base — dispatch by kind),
``MethodNode``, ``FunctionNode``, ``AttributeNode`` (kinds: attribute /
typedef), ``EnumValueNode``, ``DefineNode``.

Member context contract (spec's render-context section, plus the
``declaration`` key from plan §3.1): ``type``, ``kind``, ``name``,
``qualified_name``, ``role`` (constructor / destructor / operator /
method / function), ``declaration`` (signature reconciliation, R3),
``return_type``, ``params``, ``const``/``static``/``virtual``/
``explicit``/``constexpr``/``inline``, ``body``, ``visibility``,
``brief``/``detailed``, ``file_path``/``line_number``.
Attribute adds ``type`` (for kind=attribute) or ``declaration`` (for
kind=typedef); enumvalue adds ``initializer``; define carries
``definition``.

Strings are authoritative, flags are hints (D8): ``const``/``virtual``/
… in the member context are derived from the *declaration* string, not
from the (unreliable) stored booleans.
"""

from __future__ import annotations

from codegraph.codegen import signature, typeref
from codegraph.codegen.context import base

#: Member node types this module addresses (mirrors models/member.py;
#: consumed by the BUILDERS registry + completeness gate).
NODE_TYPES: tuple[str, ...] = (
    "MemberNode",  # abstract base — dispatch by kind
    "MethodNode",
    "FunctionNode",
    "AttributeNode",
    "EnumValueNode",
    "DefineNode",
)


def build_context(entry, state, *, parent_name: str = "", parent_qname: str = "") -> dict | None:
    """Build the member context dict for *entry*.

    Args:
        entry: CompositeEntry whose node is a member type.
        state: BuildState (skip counting, reference resolution).
        parent_name: Owning compound's name — enables constructor-role
            detection (spec member-naming rules).
        parent_qname: Owning compound's qualified name — used to strip
            the redundant scope prefix from typedef definitions
            (``using cpp_sqlite::Foo::type = T`` → ``using type = T``).

    Returns:
        Member context dict, or ``None`` for unknown member kinds.
    """
    node_type = type(entry.node).__name__
    if node_type in ("MethodNode", "FunctionNode", "MemberNode"):
        return _build_callable(entry, state, parent_name=parent_name)
    if node_type == "AttributeNode":
        return _build_attribute(entry, state, parent_qname=parent_qname)
    if node_type == "EnumValueNode":
        return _build_enum_value(entry, state)
    if node_type == "DefineNode":
        return _build_define(entry, state)
    return None


def _flags_from_node(node) -> dict:
    """Stored booleans — hints only, applied when the string lacks them."""
    return {
        "is_virtual": bool(getattr(node, "is_virtual", False)),
        "is_static": bool(getattr(node, "is_static", False)),
        "is_constexpr": bool(getattr(node, "is_constexpr", False)),
        "is_explicit": bool(getattr(node, "is_explicit", False)),
        "is_inline": bool(getattr(node, "is_inline", False)),
        "is_const": bool(getattr(node, "is_const", False)),
    }


def _role(name: str, parent_name: str) -> str:
    """Member role from the spec's derivation rules (name-based)."""
    if name.startswith("~"):
        return "destructor"
    if name.startswith("operator"):
        return "operator"
    if parent_name and name == parent_name:
        return "constructor"
    return "method"


def _resolve_body(entry, state) -> str | None:
    """Body text for a callable, in priority order:

    1. the node's own ``body`` property (the implementation export —
       captured at parse time from the source file's Doxygen body line
       range, signature line included);
    2. a HAS_IMPLEMENTATION reference to an ImplementationNode.
    """
    own = getattr(entry.node, "body", "") or ""
    if own:
        return own
    if state is None:
        return None
    for relation_type, target_key, _target_type in entry.references:
        if relation_type == "HAS_IMPLEMENTATION":
            target = state.flat.get(target_key)
            if target is not None:
                impl = getattr(target.node, "implementation", "") or ""
                return impl or None
    return None


def _build_callable(entry, state, *, parent_name: str = "") -> dict:
    node = entry.node
    node_type = type(node).__name__
    name = node.name or ""
    ts = getattr(node, "type_signature", "") or ""
    args = getattr(node, "argsstring", "") or ""

    # R3 rule 1: full-declaration encoding (contains '(' or a leading
    # specifier) is emitted verbatim — covers both the committed fixture
    # and the pipeline copy's declaration-minus-qualifiers variant.
    # R3 rule 2: return-type-only encoding is reconstructed with stored
    # flags applied only when the string lacks the keyword.
    # Phase 2 (TypeRef): reconstructed as-built declarations are
    # normalized (``Database &db`` → ``Database& db``); verbatim design
    # declarations are untouched.
    if signature.is_full_declaration(ts):
        declaration = ts.strip()
    else:
        declaration = signature.reconstruct_declaration(
            ts, name, args, flags=_flags_from_node(node)
        )
        declaration = typeref.normalize_declaration(declaration)
    parts = signature.split_declaration(declaration)

    is_method = node_type == "MethodNode"
    body = _resolve_body(entry, state)
    body_start = getattr(node, "body_start", 0) or 0
    body_end = getattr(node, "body_end", 0) or 0
    end_line = getattr(node, "end_line", 0) or 0
    decl_file = getattr(node, "file_path", "") or ""
    body_file = getattr(node, "body_file", "") or ""
    # An in-class body is contiguous with its declaration: the body lives in
    # the declaration file and its owned span already covers it (the parser
    # only extends ``end_line`` to ``body_end`` for contiguous bodies).
    # Such bodies render inside the class, not as an out-of-line definition.
    body_inline = bool(body) and body_file in ("", decl_file) and body_end <= end_line
    definition = getattr(node, "definition", "") or ""
    definition_scoped = ""
    if body_start > 0 and body_end > 0 and definition:
        definition_scoped = signature.out_of_line_definition(
            definition, args, ""
        )
    return {
        "type": node_type,
        "kind": node.kind or ("method" if is_method else "function"),
        "name": name,
        "qualified_name": node.qualified_name or "",
        "uid": node.uid or "",
        "role": _role(name, parent_name) if is_method else "function",
        "declaration": declaration,
        "return_type": parts.return_type,
        "params": _build_params(entry, state, declaration),
        "template_declarations": list(
            getattr(node, "template_declarations", []) or []
        ),
        "const": "const" in parts.qualifiers,
        "static": "static" in parts.leading,
        "virtual": "virtual" in parts.leading,
        "explicit": "explicit" in parts.leading,
        "constexpr": "constexpr" in parts.leading,
        "inline": "inline" in parts.leading,
        "nodiscard": bool(getattr(node, "is_nodiscard", False)),
        "body": body,
        "body_inline": body_inline,
        "has_body": bool(body or (body_start > 0 and body_end > 0)),
        "body_file": body_file,
        "definition_scoped": definition_scoped,
        "visibility": base.normalize_visibility(node.visibility),
        "brief": node.brief_description or "",
        "detailed": node.detailed_description or "",
        "source_documentation": getattr(node, "source_documentation", "") or "",
        "file_path": node.file_path or "",
        "line_number": node.line_number or 0,
        "start_line": getattr(node, "start_line", 0) or 0,
        "end_line": end_line,
    }


def _build_params(entry, state, declaration: str) -> list[dict]:
    """Structured param list for the member context (Phase 2).

    Prefers HAS_PARAMETER references (typed, positional — the graph's
    structured source of truth) and merges the declaration-derived
    defaults; falls back to the declaration's own param list when the
    graph carries no parameter links (R6).  Types are normalized via
    TypeRef (``Database &db`` → ``Database& db``).
    """
    arg_params = signature.split_declaration(declaration).params

    graph_params: list[dict] = []
    if state is not None:
        for relation_type, target_key, _target_type in entry.references:
            if relation_type != "HAS_PARAMETER":
                continue
            target = state.flat.get(target_key)
            if target is None:
                continue
            pnode = target.node
            graph_params.append({
                "name": getattr(pnode, "name", "") or "",
                "type": (getattr(pnode, "type", "") or "")
                or (getattr(pnode, "type_signature", "") or ""),
                "position": getattr(pnode, "position", None),
            })

    if graph_params:
        graph_params.sort(key=lambda p: (p["position"] is None, p["position"] or 0))
        # Fill defaults from the argsstring, matched by name (the graph's
        # default_value is empty on as-built exports; the argsstring
        # carries them).
        by_name = {
            p.get("name", ""): p.get("default", "")
            for p in arg_params if p.get("name")
        }
        params = [{
            "type": typeref.normalize_type(gp["type"]),
            "name": gp["name"],
            "default": by_name.get(gp["name"], "") or "",
        } for gp in graph_params]
        # Partial extraction (fewer graph params than the argsstring
        # declares) degrades to the argsstring version — never emit a
        # truncated param list.
        if arg_params and len(params) < len(arg_params):
            return [
                {**p, "type": typeref.normalize_type(p.get("type", ""))}
                for p in arg_params
            ]
        return params

    return [
        {**p, "type": typeref.normalize_type(p.get("type", ""))}
        for p in arg_params
    ]


def _build_attribute(entry, state, *, parent_qname: str = "") -> dict:
    node = entry.node
    kind = node.kind or "attribute"
    ctx: dict = {
        "type": "AttributeNode",
        "kind": kind,
        "name": node.name or "",
        "qualified_name": node.qualified_name or "",
        "visibility": base.normalize_visibility(node.visibility),
        "brief": node.brief_description or "",
        "detailed": node.detailed_description or "",
        "source_documentation": getattr(node, "source_documentation", "") or "",
        "file_path": node.file_path or "",
        "line_number": node.line_number or 0,
        "start_line": getattr(node, "start_line", 0) or 0,
        "end_line": getattr(node, "end_line", 0) or 0,
        "is_static": bool(getattr(node, "is_static", False)),
        "is_const": bool(getattr(node, "is_const", False)),
        "is_constexpr": bool(getattr(node, "is_constexpr", False)),
        "nodiscard": bool(getattr(node, "is_nodiscard", False)),
    }
    if kind == "typedef":
        definition = (node.definition or "").strip()
        if definition and parent_qname:
            # as-built typedefs carry the fully-scoped declaration
            # (``using cpp_sqlite::Foo< T >::type = T``) — strip the
            # owning compound's own scope so it renders as a member.
            scope = f"{parent_qname}::"
            for prefix in ("using ", ""):
                if definition.startswith(prefix + scope):
                    definition = prefix + definition[len(prefix) + len(scope):]
                    break
        ctx["declaration"] = (
            definition or f"using {node.name} = {node.type_signature}".strip()
        )
        ctx["type_signature"] = node.type_signature or ""
    else:
        # The verbatim source declaration (when captured) is the faithful
        # spelling — doxygen drops specifiers like ``inline`` on static
        # members.  Falls back to the structured reconstruction.
        verbatim = (node.declaration or "").strip()
        if verbatim:
            ctx["declaration"] = verbatim
        # ``type`` stays the node-type discriminator; the C++ type lives
        # under ``type_signature`` (mirrors the model field — avoids the
        # ParameterNode discriminator-clobbering bug).  Phase 2
        # (TypeRef): normalized for as-built spacing.
        ctx["type_signature"] = (
            typeref.normalize_type(node.type_signature or "")
            if (node.type_signature or "").strip() else ""
        )
        ctx["initializer"] = getattr(node, "initializer", "") or ""
    return ctx


def _build_enum_value(entry, state) -> dict:
    node = entry.node
    return {
        "type": "EnumValueNode",
        "kind": node.kind or "enumvalue",
        "name": node.name or "",
        "qualified_name": node.qualified_name or "",
        "initializer": node.initializer or "",
        "visibility": base.normalize_visibility(node.visibility),
    }


def _build_define(entry, state) -> dict:
    node = entry.node
    return {
        "type": "DefineNode",
        "kind": node.kind or "define",
        "name": node.name or "",
        "qualified_name": node.qualified_name or "",
        "definition": node.definition or "",
        "visibility": base.normalize_visibility(node.visibility),
    }
