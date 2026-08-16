"""Context builder for FileNode (mirrors models/file.py).

File context contract (spec's render-context section): ``type``,
``path``, ``guard`` (computed via ``signature.compute_guard``),
``language`` (normalized lowercase via ``normalize_language``),
``includes`` (INCLUDES references), ``forward_decls`` (Phase 2:
DEPENDS_ON), ``namespaces`` (nesting blocks — filled by the
``CodegenContextBuilder`` orchestrator, empty here) and ``blocks``
(top-level non-namespaced contexts, as-built files only).
"""

from __future__ import annotations

from codegraph.codegen import signature
from codegraph.codegen.context import base
from codegraph.constants import normalize_language

#: Node types this module addresses (mirrors models/file.py).
NODE_TYPES: tuple[str, ...] = ("FileNode",)


def build_context(entry, state) -> dict | None:
    """Build the file-level scalar context dict for *entry*."""
    node = entry.node
    path = node.path or ""
    includes: list[str] = list(getattr(node, "include_directives", []) or [])
    if not includes and state is not None:
        for relation_type, target_key, _target_type in entry.references:
            if relation_type != "INCLUDES":
                continue
            # Prefer the include spelling captured at parse time (the
            # INCLUDES edge's metadata — ``include`` = the ``<includes>``
            # element text, ``local`` = quotes vs angle brackets), falling
            # back to the target FileNode path.
            attrs = entry.edge_attrs.get((relation_type, target_key), {})
            spelling = attrs.get("include") or ""
            if spelling:
                if attrs.get("local") and not spelling.startswith('"'):
                    includes.append(f'"{spelling}"')
                elif not attrs.get("local") and not spelling.startswith("<"):
                    includes.append(f"<{spelling}>")
                else:
                    includes.append(spelling)
                continue
            target = state.flat.get(target_key)
            if target is not None:
                # INCLUDES targets are FileNodes — prefer their path.
                name = (
                    getattr(target.node, "path", "")
                    or getattr(target.node, "name", "")
                    or base.resolve_display_name(state, target_key)
                )
            else:
                name = base.resolve_display_name(state, target_key)
            if name:
                includes.append(_include_form(name))
    return {
        "type": "FileNode",
        "path": path,
        "guard": (
            getattr(node, "include_guard", "")
            or (signature.compute_guard(path) if path else "")
        ),
        "language": normalize_language(node.language or "cpp") or "cpp",
        "includes": includes,
        "namespace_leading_blank_lines": (
            getattr(node, "namespace_leading_blank_lines", 0) or 0
        ),
        "namespace_trailing_blank_lines": (
            getattr(node, "namespace_trailing_blank_lines", 0) or 0
        ),
        "namespace_name": getattr(node, "namespace_name", "") or "",
        "namespace_regions": list(getattr(node, "namespace_regions", []) or []),
        "leading_blank_lines": getattr(node, "leading_blank_lines", 0) or 0,
        "include_directive_lines": list(
            getattr(node, "include_directive_lines", []) or []
        ),
        "guard_leading_blank_lines": (
            getattr(node, "guard_leading_blank_lines", 0) or 0
        ),
        "forward_decls": [],
        "namespaces": [],
        "blocks": [],
    }


def _include_form(name: str) -> str:
    """Phase 1 include rendering: quote bare names, keep existing form."""
    name = name.strip()
    if name.startswith("<") or name.startswith('"'):
        return name
    return f'"{name}"'
