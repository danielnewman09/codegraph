"""TemplatePack — language pack resolution (spec D3, R2).

A TemplatePack is a directory of ``.j2`` files + a resolution table.
The built-in ``cpp`` pack ships in the wheel; users override by
pointing at their own pack directory (``--pack <dir>``).

The pack layout mirrors ``src/codegraph/models/`` — **one directory per
node type**:

    templates/<lang>/<NodeType>/<kind>.j2
    templates/<lang>/<NodeType>/default.j2      # kind fallback
    templates/<lang>/default.j2                 # pack-level fallback
    templates/<lang>/_skipped.j2                # declared-skip marker

``resolve(node_type, kind)`` normalizes the kind via the D11 alias
table (``enum_value→enumvalue``, …) and returns the first matching
template path.  ``template_contract.md`` in the pack documents the
per-node-type context keys (the spec's render-context contract).
"""

from __future__ import annotations

import importlib.resources
from dataclasses import dataclass
from pathlib import Path

#: D11 kind-alias table (LLM-produced spellings → canonical).
KIND_ALIASES: dict[str, str] = {
    "enum_value": "enumvalue",
}

#: Node types that never get a per-type template directory — the pack
#: renders them via ``_skipped.j2`` (or omits them entirely).  Includes
#: declared-skip scaffolding types + abstract bases (dispatched by kind).
PACK_SKIPPED: frozenset[str] = frozenset({
    # declared skips (mirror context/ skip modules)
    "LiteralNode",
    "TestNode", "TestStepNode", "AssertionNode", "TestFixtureNode",
    "HLR", "LLR",
    "Component", "Dependency", "Language", "ProjectMeta",
    # abstract bases — resolved by concrete subclass directory
    "CompoundNode", "MemberNode",
})


@dataclass(frozen=True)
class TemplatePack:
    """A language pack.

    Attributes:
        language: Canonical language key (``"cpp"``).
        directory: Pack root (defaults to the builtin
            ``codegen/templates/<language>``).
    """

    language: str = "cpp"
    directory: Path | None = None

    @classmethod
    def builtin(cls, language: str = "cpp") -> "TemplatePack":
        """The pack shipped inside the wheel."""
        return cls(language=language)

    def resolve(self, node_type: str, kind: str = "") -> Path:
        """Resolve the template for *node_type* + *kind*.

        Order: ``<NodeType>/<kind>.j2`` → ``<NodeType>/default.j2`` →
        pack ``default.j2``.  Raises ``FileNotFoundError`` when no
        template exists (an explicit error, not silent output).
        """
        raise NotImplementedError("TemplatePack.resolve: Phase 1 render slice")


def builtin_pack_dir(language: str = "cpp") -> Path:
    """Absolute path of the builtin pack's template directory."""
    ref = importlib.resources.files("codegraph.codegen")
    return Path(ref.joinpath("templates", language))


__all__ = ["TemplatePack", "KIND_ALIASES", "PACK_SKIPPED", "builtin_pack_dir"]
