"""PlantUML export and import for CodeGraphNode graphs.

Export translates a :class:`LayerGraph` into PlantUML class-diagram
syntax.  Import parses PlantUML back into a :class:`LayerGraph` using
nesting-based qualified name derivation — no alias parsing required.

Node-type mapping
-----------------
========================  =======================
CodeGraphNode type        PlantUML element
========================  =======================
NamespaceNode             ``package``
ClassNode                 ``class``
InterfaceNode             ``interface``
EnumNode                  ``enum``
UnionNode                 ``class <<union>>``
ModuleNode                ``package <<module>>``
ConceptNode               ``class <<concept>>``
MethodNode                method inside parent
AttributeNode              field inside parent
EnumValueNode              constant inside parent
FunctionNode              ``class <<function>>``
DefineNode                ``class <<define>>``
FileNode                  ``note``
========================  =======================

Relationship mapping
--------------------
========================  ========================  =================
CodeGraph predicate       PlantUML arrow            Direction
========================  ========================  =================
COMPOSES                  nesting / ``*--``         parent → child
INHERITS_FROM             ``<|--``                  child → parent
REALIZES                  ``..|>``                  class → interface
DEPENDS_ON                ``..>``                   dependent → dep
REFERENCES                ``-->``                   referrer → referent
INVOKES                   ``..>``                   caller → callee
HAS_ARGUMENT              ``..>``                   method → type
RETURNS                   ``..>``                   method → type
DEFINED_IN                ``..>``                   node → file
ASSOCIATES                ``-->``                   source → target
AGGREGATES                ``o--``                   whole → part
TEMPLATE_PARAM            ``..>``                   template → param
SPECIALIZES               ``<|--``                  spec → generic
ENFORCES_CONCEPT          ``..>``                   param → concept
IMPLEMENTS                ``..|>``                  class → interface
========================  ========================  =================

Import design
-------------
Qualified names are derived from nesting, not from ``as alias`` text.
A class ``"CalculatorEngine"`` inside package ``"calc"`` becomes
``calc::CalculatorEngine``.  Arrow targets are resolved by deriving
aliases from qualified names via ``_sanitize_alias`` — the same
convention the exporter uses.

Convenience functions
---------------------
``export_plantuml`` and ``import_plantuml`` wrap the class-based API.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from codegraph.graph import CompositeEntry, LayerGraph
from codegraph.models.tags import CodeGraphNode

# ── Diagnostics ────────────────────────────────────────────────────────


class PlantUMLParseError(Exception):
    """Raised when PlantUML import encounters structural errors in strict mode.

    Attributes:
        diagnostics: List of :class:`ParseDiagnostic` instances that
            triggered the error.
    """

    def __init__(self, diagnostics: list["ParseDiagnostic"]) -> None:
        self.diagnostics = diagnostics
        lines = ["PlantUML parse errors:"]
        for d in diagnostics:
            lines.append(f"  line {d.line}: [{d.severity}] {d.message}")
        super().__init__("\n".join(lines))


@dataclass
class ParseDiagnostic:
    """A single parse issue found during PlantUML import.

    Attributes:
        line: 1-based line number in the PlantUML source.
        severity: ``"error"`` or ``"warning"``.
        message: Human-readable description of the issue.
    """

    line: int
    severity: str  # "error" or "warning"
    message: str

    def __str__(self) -> str:
        return f"line {self.line}: [{self.severity}] {self.message}"


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

# (PlantUML keyword, stereotype or None) → CodeGraphNode type name
_PLANTUML_TO_NODE_TYPE: dict[tuple[str, str | None], str] = {
    ("package", None): "NamespaceNode",
    ("package", "module"): "ModuleNode",
    ("class", None): "ClassNode",
    ("class", "union"): "UnionNode",
    ("class", "concept"): "ConceptNode",
    ("class", "function"): "FunctionNode",
    ("class", "define"): "DefineNode",
    ("class", "method"): "MethodNode",
    ("class", "attribute"): "AttributeNode",
    ("interface", None): "InterfaceNode",
    ("enum", None): "EnumNode",
    ("note", None): "FileNode",
}

# Node type → default kind string (for CompoundNode / MemberNode)
_NODE_TYPE_TO_KIND: dict[str, str] = {
    "NamespaceNode": "namespace",
    "ModuleNode": "module",
    "ClassNode": "class",
    "UnionNode": "union",
    "ConceptNode": "concept",
    "FunctionNode": "function",
    "DefineNode": "define",
    "InterfaceNode": "interface",
    "EnumNode": "enum",
    "MethodNode": "method",
    "AttributeNode": "attribute",
    "EnumValueNode": "enumvalue",
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

# PlantUML arrow → default relationship type (used when label is absent)
_ARROW_TO_REL_TYPE: dict[str, str] = {
    "<|--": "INHERITS_FROM",
    "..|>": "REALIZES",
    "*--": "COMPOSES",
    "..>": "DEPENDS_ON",
    "-->": "REFERENCES",
    "o--": "AGGREGATES",
}

# Arrow label → relationship type (takes precedence over arrow default)
_LABEL_TO_REL_TYPE: dict[str, str] = {
    "realizes": "REALIZES",
    "implements": "IMPLEMENTS",
    "inherits_from": "INHERITS_FROM",
    "depends_on": "DEPENDS_ON",
    "invokes": "INVOKES",
    "has_argument": "HAS_ARGUMENT",
    "returns": "RETURNS",
    "defined_in": "DEFINED_IN",
    "associates": "ASSOCIATES",
    "aggregates": "AGGREGATES",
    "template_param": "TEMPLATE_PARAM",
    "specializes": "SPECIALIZES",
    "enforces_concept": "ENFORCES_CONCEPT",
    "references": "REFERENCES",
    "composes": "COMPOSES",
}

# Visibility mapping
_VISIBILITY_MAP: dict[str, str] = {
    "public": "+",
    "private": "-",
    "protected": "#",
    "": "+",
}

# Reverse visibility mapping
_PREFIX_TO_VISIBILITY: dict[str, str] = {
    "+": "public",
    "-": "private",
    "#": "protected",
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

# Known PlantUML keywords that start element declarations
_ELEMENT_KEYWORDS = ("package", "class", "interface", "enum", "note")

# Arrow patterns to try when parsing (longest/most-specific first)
_ARROW_PATTERNS: list[str] = [
    "..|>",
    "<|--",
    "-->",
    "..>",
    "o--",
    "*--",
]


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
            lines.append(f'{prefix}{keyword} "{display_name}" as {alias} <<{stereotype}>> {{')
        else:
            lines.append(f'{prefix}{keyword} "{display_name}" as {alias} {{')

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
        lines.append(f'{prefix}{keyword} "{display_name}" as {alias}{stereo} {{')

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
        lines.append(f'{prefix}enum "{display_name}" as {alias} {{')

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
        lines.append(f'{prefix}note "{display_name}" as {alias}')
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


# ── PlantUML Importer ────────────────────────────────────────────────────


class PlantUMLImporter:
    """Import PlantUML class-diagram text into a :class:`LayerGraph`.

    Parses PlantUML elements and derives qualified names from the
    nesting structure — no alias parsing required.  A class
    ``"CalculatorEngine"`` inside ``package "calc"`` becomes
    ``calc::CalculatorEngine``.  Arrow targets are resolved using the
    same ``_sanitize_alias`` convention the exporter uses.

    The resulting LayerGraph contains the core structure:
    NamespaceNodes, CompoundNodes, MemberNodes, and their
    relationships.  Metadata (source, component_id, etc.) is not
    preserved — the graph is rebuilt from the diagram structure.

    Diagnostics are collected during parsing and available on the
    ``diagnostics`` attribute after :meth:`import_plantuml` returns.
    Set ``strict=True`` to raise :class:`PlantUMLParseError` on any
    error-level diagnostics.

    Args:
        tags: Tags to apply to every imported node.
            Defaults to ``frozenset({"design"})``.
        strict: If ``True``, raise :class:`PlantUMLParseError` when
            any error-level diagnostic is recorded.  Defaults to
            ``False`` (collect diagnostics but still return the graph).
    """

    def __init__(self, tags: frozenset[str] | None = None,
                 strict: bool = False):
        self._tags = list(tags) if tags else ["design"]
        self._strict = strict
        self.diagnostics: list[ParseDiagnostic] = []

    def import_plantuml(self, text: str) -> LayerGraph:
        """Parse PlantUML text and return a :class:`LayerGraph`.

        Walks the diagram line by line, tracking nesting via braces.
        Element declarations (``package``, ``class``, ``interface``,
        ``enum``, ``note``) push to a nesting stack; closing braces pop.
        Qualified names are derived by joining ancestor names with
        ``::``.

        Arrow lines are resolved after all elements have been parsed,
        mapping aliases back to qualified names.

        Parse issues are collected in :attr:`diagnostics`.  If
        ``strict=True`` was set at construction, any error-level
        diagnostic raises :class:`PlantUMLParseError` before returning.

        Args:
            text: Complete PlantUML text (including ``@startuml`` /
                ``@enduml`` wrappers, which are skipped).

        Returns:
            A :class:`LayerGraph` containing the parsed nodes and
            relationships.

        Raises:
            PlantUMLParseError: In strict mode, when any error-level
                diagnostic is recorded.
        """
        # Reset diagnostics for each call
        self.diagnostics = []

        lines = text.split("\n")

        # Parsing state
        stack: list[tuple[str, str, CompositeEntry]] = []
        # Each stack entry: (qualified_name, node_type_name, entry)

        root_entries: dict[str, CompositeEntry] = {}
        alias_to_qname: dict[str, str] = {}
        qname_to_entry: dict[str, CompositeEntry] = {}
        pending_arrows: list[tuple[str, str, str, str, int]] = []
        # Each arrow: (source_alias, arrow, target_alias, label, line_no)

        for line_no, line in enumerate(lines, start=1):
            stripped = line.strip()

            # Skip empty lines, directives, skinparam, comments
            if (not stripped
                    or stripped.startswith("@")
                    or stripped.startswith("'")
                    or stripped.startswith("skinparam")
                    or stripped.startswith("/")):
                continue

            # Closing brace: pop from stack
            if stripped == "}":
                if not stack:
                    self._diag(line_no, "error",
                               "Unexpected '}' — no open element to close")
                else:
                    stack.pop()
                continue

            # ── Element declaration ──────────────────────────────────
            elem = self._try_parse_element(stripped)
            if elem is not None:
                keyword, name, stereotype, has_body = elem

                if not name:
                    self._diag(line_no, "error",
                               f"Element declaration missing name: "
                               f"{stripped!r}")
                    continue

                # Unknown stereotype warning
                if stereotype and (keyword, stereotype) not in _PLANTUML_TO_NODE_TYPE:
                    self._diag(line_no, "warning",
                               f"Unknown stereotype <<{stereotype}>> on "
                               f"{keyword} — falling back to default node type")

                node_type = self._resolve_node_type(keyword, stereotype)
                qname = self._derive_qualified_name(name, stack)

                node = self._create_node(node_type, name, qname)
                entry = CompositeEntry(node=node)

                # Register alias (derived from qualified name)
                alias_to_qname[_sanitize_alias(qname)] = qname
                qname_to_entry[qname] = entry

                # Add to parent or root
                if stack:
                    parent_entry = stack[-1][2]
                    if node_type not in parent_entry.children:
                        parent_entry.children[node_type] = {}
                    parent_entry.children[node_type][qname] = entry
                else:
                    root_entries[qname] = entry

                # Push to stack if element opens a body
                if has_body:
                    stack.append((qname, node_type, entry))

                continue

            # ── Member line ──────────────────────────────────────────
            if stack:
                parent_qname, parent_type, parent_entry = stack[-1]
                member = self._try_parse_member(stripped, parent_type)
                if member is not None:
                    m_type, m_name, m_vis, m_type_sig, m_args = member
                    m_qname = parent_qname + "::" + m_name

                    node = self._create_member_node(
                        m_type, m_name, m_qname, m_vis, m_type_sig, m_args,
                    )
                    m_entry = CompositeEntry(node=node)

                    alias_to_qname[_sanitize_alias(m_qname)] = m_qname
                    qname_to_entry[m_qname] = m_entry

                    if m_type not in parent_entry.children:
                        parent_entry.children[m_type] = {}
                    parent_entry.children[m_type][m_qname] = m_entry

                    continue

            # ── Arrow line ────────────────────────────────────────────
            arrow = self._try_parse_arrow(stripped)
            if arrow is not None:
                src_alias, arrow_sym, tgt_alias, label = arrow
                pending_arrows.append((src_alias, arrow_sym, tgt_alias, label, line_no))
                continue

            # ── Unrecognized line ──────────────────────────────────────
            # Inside a body, an unrecognized line is suspicious
            if stack:
                self._diag(line_no, "warning",
                           f"Unrecognized line inside "
                           f"{stack[-1][1]}: {stripped!r}")
            else:
                self._diag(line_no, "warning",
                           f"Unrecognized line: {stripped!r}")

        # ── Unclosed braces ──────────────────────────────────────────
        for qname, node_type, _ in stack:
            self._diag(len(lines), "warning",
                       f"Unclosed element: {node_type} {qname!r} — "
                       "missing closing '}'")

        # ── Resolve arrows ───────────────────────────────────────────
        for src_alias, arrow_sym, tgt_alias, label, arrow_line in pending_arrows:
            src_qname = alias_to_qname.get(src_alias)
            tgt_qname = alias_to_qname.get(tgt_alias)

            if src_qname is None:
                self._diag(arrow_line, "error",
                           f"Arrow source alias {src_alias!r} not found "
                           f"— no matching element")
                continue
            if tgt_qname is None:
                self._diag(arrow_line, "error",
                           f"Arrow target alias {tgt_alias!r} not found "
                           f"— no matching element")
                continue

            src_entry = qname_to_entry.get(src_qname)
            if src_entry is None:
                continue

            rel_type = self._resolve_rel_type(arrow_sym, label)
            tgt_type = self._resolve_target_type(tgt_qname, qname_to_entry)

            # Warn on unknown arrow label
            if label:
                key = label.strip().lower().replace(" ", "_")
                if key not in _LABEL_TO_REL_TYPE and arrow_sym in _ARROW_TO_REL_TYPE:
                    self._diag(arrow_line, "warning",
                               f"Unknown arrow label {label!r} — using "
                               f"arrow default {_ARROW_TO_REL_TYPE[arrow_sym]}")

            src_entry.references.append((rel_type, tgt_qname, tgt_type))

        # ── Strict mode: raise on errors ────────────────────────────
        if self._strict:
            errors = [d for d in self.diagnostics if d.severity == "error"]
            if errors:
                raise PlantUMLParseError(errors)

        return LayerGraph(tags=frozenset(self._tags), entries=root_entries)

    def _diag(self, line: int, severity: str, message: str) -> None:
        """Record a parse diagnostic."""
        self.diagnostics.append(ParseDiagnostic(line=line, severity=severity,
                                                message=message))

    # ── Element parsing ──────────────────────────────────────────────

    @staticmethod
    def _try_parse_element(line: str) -> tuple[str, str, str | None, bool] | None:
        """Try to parse a PlantUML element declaration line.

        Returns ``(keyword, name, stereotype_or_None, has_body)`` or
        ``None`` if the line is not an element declaration.

        Handles quoted names (``"name"``) and optional ``as alias``,
        ``<<stereotype>>``, and trailing ``{``.
        """
        for kw in _ELEMENT_KEYWORDS:
            if line.startswith(kw) and (len(line) == len(kw) or line[len(kw)] in ' "'):
                rest = line[len(kw):].strip()

                # Extract name from quotes or bare word
                name, rest = _extract_name(rest)
                if not name:
                    continue

                # Skip optional "as alias"
                if rest.startswith("as "):
                    # Skip alias token (one word or quoted)
                    rest = rest[3:].strip()
                    if rest.startswith('"'):
                        _, rest = _extract_name(rest)
                    else:
                        parts = rest.split(None, 1)
                        rest = parts[1] if len(parts) > 1 else ""

                # Check for stereotype
                stereotype = None
                if rest.startswith("<<"):
                    end = rest.find(">>", 2)
                    if end >= 0:
                        stereotype = rest[2:end]
                        rest = rest[end + 2:].strip()

                # Check for opening brace
                has_body = "{" in rest

                return (kw, name, stereotype, has_body)

        return None

    @staticmethod
    def _resolve_node_type(keyword: str, stereotype: str | None) -> str:
        """Map a PlantUML keyword + stereotype to a CodeGraphNode type name."""
        key = (keyword, stereotype)
        if key in _PLANTUML_TO_NODE_TYPE:
            return _PLANTUML_TO_NODE_TYPE[key]
        # Fallback defaults
        defaults = {
            "package": "NamespaceNode",
            "class": "ClassNode",
            "interface": "InterfaceNode",
            "enum": "EnumNode",
            "note": "FileNode",
        }
        return defaults.get(keyword, "ClassNode")

    @staticmethod
    def _derive_qualified_name(name: str,
                               stack: list[tuple[str, str, CompositeEntry]]) -> str:
        """Derive a qualified name from the element name and nesting stack.

        Joins ancestor qualified names with ``::``.  For example,
        a class ``"CalculatorEngine"`` inside package ``"calc"`` becomes
        ``calc::CalculatorEngine``.
        """
        if stack:
            return stack[-1][0] + "::" + name
        return name

    # ── Member parsing ───────────────────────────────────────────────

    @staticmethod
    def _try_parse_member(line: str, parent_type: str) -> tuple[str, str, str, str, str] | None:
        """Try to parse a member line inside a compound element.

        Returns ``(node_type, name, visibility, type_signature, argsstring)``
        or ``None``.

        For EnumNode parents, all members are enum values.
        For ClassNode / InterfaceNode, members are methods (if they
        have parentheses) or attributes (if they don't).
        """
        stripped = line.strip()
        if not stripped:
            return None

        # Enum values: bare identifiers (typically UPPER_CASE)
        if parent_type == "EnumNode":
            if re.match(r"^[A-Za-z_]\w*$", stripped):
                return ("EnumValueNode", stripped, "", "", "")
            return None

        # Visibility prefix
        visibility = ""
        if stripped[0] in "+-#":
            visibility = _PREFIX_TO_VISIBILITY.get(stripped[0], "")
            stripped = stripped[1:].strip()

        if not stripped:
            return None

        # Method: has parentheses
        paren_start = stripped.find("(")
        if paren_start >= 0:
            name = stripped[:paren_start].strip()
            paren_end = stripped.rfind(")")
            if paren_end < 0:
                paren_end = len(stripped) - 1
            argsstring = stripped[paren_start:paren_end + 1]
            rest = stripped[paren_end + 1:].strip()
            type_signature = ""
            if rest.startswith(":"):
                type_signature = rest[1:].strip()
            return ("MethodNode", name, visibility, type_signature, argsstring)

        # Attribute: has colon (type annotation)
        colon_pos = stripped.find(":")
        if colon_pos >= 0:
            name = stripped[:colon_pos].strip()
            type_signature = stripped[colon_pos + 1:].strip()
            return ("AttributeNode", name, visibility, type_signature, "")

        # Bare name: treat as attribute without type
        if re.match(r"^[A-Za-z_]\w*$", stripped):
            return ("AttributeNode", stripped, visibility, "", "")

        return None

    # ── Arrow parsing ────────────────────────────────────────────────

    @staticmethod
    def _try_parse_arrow(line: str) -> tuple[str, str, str, str] | None:
        """Try to parse a relationship arrow line.

        Returns ``(source_alias, arrow, target_alias, label)`` or
        ``None``.  The label may be an empty string if absent.
        """
        stripped = line.strip()

        for arrow in _ARROW_PATTERNS:
            pattern = f" {arrow} "
            if pattern in stripped:
                parts = stripped.split(pattern, 1)
                source = parts[0].strip()
                rest = parts[1].strip()

                label = ""
                if " : " in rest:
                    target, label = rest.split(" : ", 1)
                    target = target.strip()
                    label = label.strip()
                else:
                    target = rest

                return (source, arrow, target, label)

        return None

    # ── Node creation ─────────────────────────────────────────────────

    def _create_node(self, node_type: str, name: str,
                     qname: str) -> CodeGraphNode:
        """Create a CodeGraphNode instance via :meth:`CodeGraphNode.deserialize`."""
        data: dict = {
            "type": node_type,
            "name": name,
            "qualified_name": qname,
            "tags": list(self._tags),
        }
        kind = _NODE_TYPE_TO_KIND.get(node_type)
        if kind:
            data["kind"] = kind
        if node_type == "FileNode":
            data["path"] = name
        return CodeGraphNode.deserialize(data)

    def _create_member_node(self, node_type: str, name: str, qname: str,
                           visibility: str, type_signature: str,
                           argsstring: str) -> CodeGraphNode:
        """Create a member (Method/Attribute/EnumValue) CodeGraphNode."""
        data: dict = {
            "type": node_type,
            "name": name,
            "qualified_name": qname,
            "tags": list(self._tags),
        }
        kind = _NODE_TYPE_TO_KIND.get(node_type)
        if kind:
            data["kind"] = kind
        if visibility:
            data["visibility"] = visibility
        if type_signature:
            data["type_signature"] = type_signature
        if argsstring:
            data["argsstring"] = argsstring
        return CodeGraphNode.deserialize(data)

    # ── Relationship resolution ────────────────────────────────────────

    @staticmethod
    def _resolve_rel_type(arrow: str, label: str) -> str:
        """Resolve a relationship type from arrow symbol and label.

        Label takes precedence over arrow symbol when present.
        """
        if label:
            key = label.strip().lower().replace(" ", "_")
            if key in _LABEL_TO_REL_TYPE:
                return _LABEL_TO_REL_TYPE[key]
        if arrow in _ARROW_TO_REL_TYPE:
            return _ARROW_TO_REL_TYPE[arrow]
        return "DEPENDS_ON"  # safe default

    @staticmethod
    def _resolve_target_type(target_qname: str,
                             qname_to_entry: dict[str, CompositeEntry]) -> str:
        """Look up the node type name for a target qualified name."""
        entry = qname_to_entry.get(target_qname)
        if entry is not None:
            return type(entry.node).__name__
        return "ClassNode"  # default


# ── Shared string helpers ────────────────────────────────────────────────


def _extract_name(text: str) -> tuple[str, str]:
    """Extract a PlantUML element name and return (name, rest).

    Handles quoted names (``"name"``) and bare-word names.
    """
    text = text.strip()
    if text.startswith('"'):
        end = text.find('"', 1)
        if end < 0:
            return (text[1:], "")
        return (text[1:end], text[end + 1:].strip())
    # Bare word
    parts = text.split(None, 1)
    if not parts:
        return ("", "")
    return (parts[0], parts[1] if len(parts) > 1 else "")


# ── Convenience functions ─────────────────────────────────────────────────


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


def import_plantuml(text: str, tags: frozenset[str] | None = None,
                    strict: bool = False) -> LayerGraph:
    """Import PlantUML class-diagram text into a :class:`LayerGraph`.

    Qualified names are derived from the nesting structure (no alias
    parsing needed).  Arrow targets are resolved using the same
    ``_sanitize_alias`` convention the exporter uses.

    Parse issues are collected as diagnostics.  Set ``strict=True``
    to raise :class:`PlantUMLParseError` on any error-level issue.
    For programmatic access to diagnostics (even in non-strict mode),
    use the :class:`PlantUMLImporter` class directly.

    Args:
        text: Complete PlantUML text (``@startuml`` / ``@enduml`` are
            optional and will be skipped if present).
        tags: Tags to apply to every imported node.
            Defaults to ``frozenset({"design"})``.
        strict: If ``True``, raise :class:`PlantUMLParseError` when
            any error-level diagnostic is recorded.

    Returns:
        A :class:`LayerGraph` containing the parsed nodes and
        relationships.

    Raises:
        PlantUMLParseError: In strict mode, when structural errors are
            found in the PlantUML input.
    """
    return PlantUMLImporter(tags=tags, strict=strict).import_plantuml(text)