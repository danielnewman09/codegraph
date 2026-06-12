"""PlantUML export for CodeGraphNode graphs.

Translates a :class:`LayerGraph` into PlantUML class-diagram syntax.
Produces clean, readable diagrams with no JSON metadata blobs.

Node-type mapping
-----------------
========================  =======================
CodeGraphNode type        PlantUML element
========================  =======================
NamespaceNode             ``package``
ClassNode                 ``class``
InterfaceNode             ``interface``
EnumNode                  ``enum``
UnionNode                 ``class \u003c\u003cunion\u003e\u003e``
ModuleNode                ``package \u003c\u003cmodule\u003e\u003e``
ConceptNode               ``class \u003c\u003cconcept\u003e\u003e``
MethodNode                method inside parent
AttributeNode              field inside parent
EnumValueNode              constant inside parent
FunctionNode              ``class \u003c\u003cfunction\u003e\u003e``
DefineNode                ``class \u003c\u003cdefine\u003e\u003e``
FileNode                  ``note``
========================  =======================

Relationship mapping
--------------------
========================  ========================  =================
CodeGraph predicate       PlantUML arrow            Direction
========================  ========================  =================
COMPOSES                  nesting / ``*--``         parent \u2192 child
INHERITS_FROM             ``\u003c|--``                  child \u2192 parent
REALIZES                  ``..|\u003e``                  class \u2192 interface
DEPENDS_ON                ``..\u003e``                   dependent \u2192 dep
REFERENCES                ``--\u003e``                   referrer \u2192 referent
INVOKES                   ``..\u003e``                   caller \u2192 callee
HAS_ARGUMENT              ``..\u003e``                   method \u2192 type
RETURNS                   ``..\u003e``                   method \u2192 type
DEFINED_IN                ``..\u003e``                   node \u2192 file
ASSOCIATES                ``--\u003e``                   source \u2192 target
AGGREGATES                ``o--``                   whole \u2192 part
TEMPLATE_PARAM            ``..\u003e``                   template \u2192 param
SPECIALIZES               ``\u003c|--``                  spec \u2192 generic
ENFORCES_CONCEPT          ``..\u003e``                   param \u2192 concept
IMPLEMENTS                ``..|\u003e``                  class \u2192 interface
========================  ========================  =================

Convenience function
---------------------
``export_plantuml`` wraps the class-based API.
"""

from __future__ import annotations

from codegraph.graph import CompositeEntry, LayerGraph
from codegraph.models.tags import CodeGraphNode

# ── Constants ────────────────────────────────────────────────────────────

# Node type → PlantUML keyword
_NODE_TYPE_TO_PLANTUML: dict[str, str] = {
    "NamespaceNode": "package",
    "ClassNode": "class",
    "InterfaceNode": "interface",
    "EnumNode": "enum",
    "UnionNode": "class",
    "ModuleNode": "package",
    "ConceptNode": "class",
    "MethodNode": "class",
    "FunctionNode": "class",
    "DefineNode": "class",
    "AttributeNode": "class",
    "EnumValueNode": "class",
    "FileNode": "note",
}

# Node types that get a PlantUML stereotype
_NODE_TYPE_TO_STEREOTYPE: dict[str, str] = {
    "UnionNode": "union",
    "ModuleNode": "module",
    "ConceptNode": "concept",
    "MethodNode": "method",
    "FunctionNode": "function",
    "DefineNode": "define",
    "AttributeNode": "attribute",
    "EnumValueNode": "enumValue",
}

# Relationship type → PlantUML arrow
_REL_TYPE_TO_ARROW: dict[str, str] = {
    "INHERITS_FROM": "<|--",
    "REALIZES": "..|>",
    "COMPOSES": "*--",
    "DEPENDS_ON": "..>",
    "REFERENCES": "-->",
    "INVOKES": "..>",
    "HAS_ARGUMENT": "..>",
    "RETURNS": "..>",
    "DEFINED_IN": "..>",
    "ASSOCIATES": "-->",
    "AGGREGATES": "o--",
    "TEMPLATE_PARAM": "..>",
    "SPECIALIZES": "<|--",
    "ENFORCES_CONCEPT": "..>",
    "IMPLEMENTS": "..|>",
}

# Visibility mapping
_VISIBILITY_MAP: dict[str, str] = {
    "public": "+",
    "private": "-",
    "protected": "#",
    "": "+",
}

# Node types whose children are nested as members (not separate elements)
_MEMBER_TYPES: set[str] = {
    "MethodNode",
    "AttributeNode",
    "EnumValueNode",
}

# Relationship types that are represented by nesting (not arrows)
_NESTING_REL_TYPES: set[str] = {
    "COMPOSES",
    "DEFINED_IN",
    "HAS_IMPLEMENTATION",
}


# ── Helpers ──────────────────────────────────────────────────────────────


def _sanitize_alias(name: str) -> str:
    """Convert a qualified name to a valid PlantUML alias.

    Replaces ``::`` with ``__`` and spaces/dots with ``_``.

    Args:
        name: A qualified name (e.g. ``calc::CalculatorEngine``).

    Returns:
        A sanitized alias (e.g. ``calc__CalculatorEngine``).
    """
    return name.replace("::", "__").replace(" ", "_").replace(".", "_")


def _visibility_prefix(visibility: str) -> str:
    """Convert a visibility string to a PlantUML prefix character.

    Args:
        visibility: One of ``"public"``, ``"private"``, ``"protected"``,
            or empty string (defaults to public).

    Returns:
        The PlantUML visibility prefix (``+``, ``-``, ``#``).
    """
    return _VISIBILITY_MAP.get(visibility, "+")


def _format_method(name: str, visibility: str = "",
                   type_signature: str = "", argsstring: str = "") -> str:
    """Format a method as a PlantUML method line.

    Args:
        name: Method name.
        visibility: Access level (``"public"``, ``"private"``, etc.).
        type_signature: Return type string.
        argsstring: Argument signature string (including parens).

    Returns:
        A PlantUML method line like ``+add(a: int, b: int): int``.
    """
    prefix = _visibility_prefix(visibility)
    args = argsstring if argsstring else "()"
    ret = f": {type_signature}" if type_signature else ""
    return f"  {prefix}{name}{args}{ret}"


def _format_attribute(name: str, visibility: str = "",
                      type_signature: str = "") -> str:
    """Format an attribute as a PlantUML field line.

    Args:
        name: Attribute name.
        visibility: Access level.
        type_signature: Type string.

    Returns:
        A PlantUML field line like ``-precision: int``.
    """
    prefix = _visibility_prefix(visibility)
    typ = f": {type_signature}" if type_signature else ""
    return f"  {prefix}{name}{typ}"


def _format_enum_value(name: str) -> str:
    """Format an enum value as a PlantUML constant line.

    Args:
        name: Enum value name.

    Returns:
        A PlantUML enum constant line like ``RED``.
    """
    return f"  {name}"


# ── PlantUML Exporter ─────────────────────────────────────────────────────


class PlantUMLExporter:
    """Export a :class:`LayerGraph` to PlantUML class-diagram syntax.

    Walks the composition tree of the graph, emitting PlantUML elements
    for each node.  COMPOSES relationships are represented by nesting
    (methods inside classes, classes inside packages).  All other
    relationship types are emitted as labelled arrows after the
    element definitions.

    Args:
        graph: The :class:`LayerGraph` to export.
        fields: Which property fields to include for each node.
            ``"llm"`` (default) — only ``_llm_fields``.
            ``"all"`` — every defined property.
    """

    def __init__(self, graph: LayerGraph, fields: str = "llm"):
        self.graph = graph
        self.fields = fields
        self._aliases: dict[str, str] = {}      # qualified_name → alias
        self._rel_lines: list[str] = []           # arrow lines (emitted last)
        self._seen: set[str] = set()              # aliases already emitted

    def export(self) -> str:
        """Return the PlantUML representation as a string.

        Returns:
            A complete PlantUML class-diagram string enclosed in
            ``@startuml`` / ``@enduml``.
        """
        lines: list[str] = ["@startuml"]

        # Style hints
        lines.append("skinparam classAttributeIconSize 0")
        lines.append("")

        # Emit elements for root entries (depth-first)
        for entry in self.graph.entries.values():
            lines.extend(self._emit_entry(entry, indent=0))

        # Emit relationship arrows
        if self._rel_lines:
            lines.append("")
            lines.append("' ── Relationships ─────────────────────")
            lines.extend(self._rel_lines)

        lines.append("")
        lines.append("@enduml")
        return "\n".join(lines)

    # ── Element emission ──────────────────────────────────────────────

    def _emit_entry(self, entry: CompositeEntry, indent: int = 0) -> list[str]:
        """Recursively emit a CompositeEntry and its composed children.

        COMPOSES children that are member types (MethodNode, AttributeNode,
        EnumValueNode) are inlined inside the parent element.  All other
        children (classes inside a namespace, etc.) are nested.

        Args:
            entry: The CompositeEntry to emit.
            indent: Current indentation level.

        Returns:
            A list of PlantUML lines.
        """
        node = entry.node
        node_type = type(node).__name__
        prefix = "  " * indent

        # Get or create alias
        qname = getattr(node, "qualified_name", None) or node.name
        alias = _sanitize_alias(qname)
        self._aliases[qname] = alias

        # Emit references (non-COMPOSES edges) as arrows
        for rel_type, target_key, target_type in entry.references:
            self._emit_reference(node, rel_type, target_key)

        # Choose emission strategy by node type
        if node_type == "NamespaceNode" or node_type == "ModuleNode":
            return self._emit_namespace(entry, alias, indent)
        elif node_type == "FileNode":
            return self._emit_file(entry, alias, indent)
        elif node_type == "EnumNode":
            return self._emit_enum(entry, alias, indent)
        else:
            return self._emit_compound(entry, alias, indent)

    def _emit_namespace(self, entry: CompositeEntry, alias: str,
                        indent: int = 0) -> list[str]:
        """Emit a namespace (package) with nested children."""
        node = entry.node
        prefix = "  " * indent
        keyword = _NODE_TYPE_TO_PLANTUML.get(type(node).__name__, "package")
        stereotype = _NODE_TYPE_TO_STEREOTYPE.get(type(node).__name__)
        display_name = node.name

        lines: list[str] = []
        if stereotype:
            lines.append(f"{prefix}{keyword} \"{display_name}\" as {alias} <<{stereotype}>> {{")
        else:
            lines.append(f"{prefix}{keyword} \"{display_name}\" as {alias} {{")

        # Emit non-member children (classes, interfaces, etc.)
        for child_type, type_children in entry.children.items():
            if child_type not in _MEMBER_TYPES:
                for child_entry in type_children.values():
                    lines.extend(self._emit_entry(child_entry, indent + 1))

        lines.append(f"{prefix}}}")
        self._seen.add(alias)
        return lines

    def _emit_compound(self, entry: CompositeEntry, alias: str,
                       indent: int = 0) -> list[str]:
        """Emit a class, interface, union, concept, etc."""
        node = entry.node
        node_type = type(node).__name__
        prefix = "  " * indent
        keyword = _NODE_TYPE_TO_PLANTUML.get(node_type, "class")
        stereotype = _NODE_TYPE_TO_STEREOTYPE.get(node_type)
        display_name = node.name

        lines: list[str] = []
        stereo = f" <<{stereotype}>>" if stereotype else ""
        lines.append(f"{prefix}{keyword} \"{display_name}\" as {alias}{stereo} {{")

        # Emit member children (methods, attributes) inside the class body
        for member_type in ("MethodNode", "AttributeNode"):
            if member_type in entry.children:
                for child_entry in entry.children[member_type].values():
                    lines.append(self._format_member_line(child_entry))

        # Emit non-member, non-namespace children nested
        for child_type, type_children in entry.children.items():
            if child_type not in _MEMBER_TYPES and child_type != "NamespaceNode":
                if child_type not in ("MethodNode", "AttributeNode"):
                    for child_entry in type_children.values():
                        if child_type == "EnumValueNode":
                            lines.append(self._format_enum_value_line(child_entry))
                        else:
                            lines.extend(self._emit_entry(child_entry, indent + 1))

        lines.append(f"{prefix}}}")
        self._seen.add(alias)
        return lines

    def _emit_enum(self, entry: CompositeEntry, alias: str,
                   indent: int = 0) -> list[str]:
        """Emit an enum with its values."""
        node = entry.node
        prefix = "  " * indent
        display_name = node.name

        lines: list[str] = []
        lines.append(f"{prefix}enum \"{display_name}\" as {alias} {{")

        # Emit enum values
        if "EnumValueNode" in entry.children:
            for child_entry in entry.children["EnumValueNode"].values():
                lines.append(self._format_enum_value_line(child_entry))

        lines.append(f"{prefix}}}")
        self._seen.add(alias)
        return lines

    def _emit_file(self, entry: CompositeEntry, alias: str,
                   indent: int = 0) -> list[str]:
        """Emit a file node as a note."""
        node = entry.node
        prefix = "  " * indent
        display_name = node.name

        lines: list[str] = []
        lines.append(f"{prefix}note \"{display_name}\" as {alias}")
        self._seen.add(alias)
        return lines

    # ── Member formatting ──────────────────────────────────────────────

    def _format_member_line(self, entry: CompositeEntry) -> str:
        """Format a method or attribute as a PlantUML member line."""
        node = entry.node
        node_type = type(node).__name__
        name = node.name
        visibility = getattr(node, "visibility", "")
        type_sig = getattr(node, "type_signature", "")

        if node_type == "MethodNode":
            args = getattr(node, "argsstring", "()")
            return _format_method(name, visibility, type_sig, args)
        elif node_type == "AttributeNode":
            return _format_attribute(name, visibility, type_sig)
        else:
            return f"  {_visibility_prefix(visibility)}{name}"

    def _format_enum_value_line(self, entry: CompositeEntry) -> str:
        """Format an enum value as a PlantUML constant line."""
        node = entry.node
        return _format_enum_value(node.name)

    # ── Reference (arrow) emission ─────────────────────────────────────

    def _emit_reference(self, source_node: CodeGraphNode, rel_type: str,
                       target_key: str) -> None:
        """Queue a relationship arrow for later emission.

        COMPOSES, DEFINED_IN, and HAS_IMPLEMENTATION are handled by
        nesting, not arrows.

        Args:
            source_node: The source node of the relationship.
            rel_type: The relationship type (e.g. ``"DEPENDS_ON"``).
            target_key: The target node key (qualified name or name).
        """
        if rel_type in _NESTING_REL_TYPES:
            return

        source_qname = getattr(source_node, "qualified_name", None) or source_node.name
        source_alias = self._aliases.get(source_qname) or _sanitize_alias(source_qname)
        target_alias = _sanitize_alias(target_key)

        arrow = _REL_TYPE_TO_ARROW.get(rel_type, "..>")
        label = rel_type.lower()

        line = f"{source_alias} {arrow} {target_alias} : {label}"
        self._rel_lines.append(line)


# ── Convenience function ─────────────────────────────────────────────────


def export_plantuml(graph: LayerGraph, fields: str = "llm") -> str:
    """Export a :class:`LayerGraph` to PlantUML class-diagram syntax.

    Args:
        graph: The :class:`LayerGraph` to export.
        fields: Which property fields to include for each node.
            ``"llm"`` (default) — only ``_llm_fields``.
            ``"all"`` — every defined property.

    Returns:
        A complete PlantUML class-diagram string.
    """
    return PlantUMLExporter(graph, fields).export()