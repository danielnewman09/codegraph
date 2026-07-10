"""Markdown export and import for CodeGraphNode graphs.

Export translates a :class:`LayerGraph` into a human-readable Markdown
document with text-based descriptions.  By default only the public API
is shown — private/protected members are hidden unless
``public_only=False``.

Import parses Markdown back into a :class:`LayerGraph` using
heading-level nesting — same qualified-name derivation as PlantUML.

Format
------
::

    # codegraph: design

    ## Namespace: `calc`
    Calculation engine module

    ### Class: `calc::CalculatorEngine`
    The core calculator engine class that performs arithmetic operations.

    **Public methods:**
    - `add` — Performs addition
    - `validateInput` — Validates user input

    **Public attributes:**
    - `precision` — Calculation precision

    **Implements:** `calc::ICalculator`

    ### Interface: `calc::ICalculator`
    Calculator interface contract.

    **Public methods:**
    - `calculate` — Core calculation operation

    ### Enum: `calc::Operation`
    An enumeration of supported arithmetic operations.

    **Values:**
    - `ADD` — Addition operation
    - `SUBTRACT` — Subtraction operation

    ## File Notes
    - `calculator_engine.h`

    ## Relationships
    - `calc::CalculatorEngine` → `calc::CalculatorResult` **depends_on**
    - `ui::CalculatorWindow` → `calc::CalculatorEngine` **depends_on**

Import design
-------------
Qualified names come from heading text directly — no nesting derivation.
A ``### Class: `calc::CalculatorEngine` `` creates a ClassNode with
``qualified_name="calc::CalculatorEngine"`` and ``name="CalculatorEngine"``.
``INHERITS_FROM`` and ``REALIZES`` / ``IMPLEMENTS`` relations are parsed
from inline ``**Inherits from:**`` / ``**Implements:**`` lines.  All other
relationships are parsed from the ``## Relationships`` section.
"""

from __future__ import annotations

import re

from codegraph.graph import CompositeEntry, LayerGraph
from codegraph.models.tags import CodeGraphNode
from codegraph.export.plantuml import PlantUMLParseError, ParseDiagnostic

# ── Constants ────────────────────────────────────────────────────────────

# Markdown heading keyword → CodeGraphNode type name
_KEYWORD_TO_NODE_TYPE: dict[str, str] = {
    "namespace": "NamespaceNode",
    "class": "ClassNode",
    "interface": "InterfaceNode",
    "enum": "EnumNode",
    "function": "FunctionNode",
    "module": "ModuleNode",
    "union": "UnionNode",
    "concept": "ConceptNode",
    "note": "FileNode",
    "component": "Component",
    "hlr": "HLR",
    "llr": "LLR",
    "test": "TestNode",
    "assertion": "AssertionNode",
    "teststep": "TestStepNode",
    "testfixture": "TestFixtureNode",
    "attribute": "AttributeNode",
    "literal": "LiteralNode",
}

# Node type → default kind
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
    "AttributeNode": "attribute",
    "LiteralNode": "literal",
}

# Relationship types skipped in the Relationships section (handled by nesting)
_NESTING_REL_TYPES: set[str] = {"COMPOSES", "DEFINED_IN", "HAS_IMPLEMENTATION"}

# Node types whose children nest as members
_MEMBER_TYPES: set[str] = {"MethodNode", "AttributeNode", "EnumValueNode"}

# Relationship types shown as inline properties (not in Relationships section)
_INLINE_REL_TYPES: dict[str, str] = {
    "INHERITS_FROM": "Inherits from",
    "REALIZES": "Implements",
    "IMPLEMENTS": "Implements",
}

# Relationship label → type (import)
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

# Fields excluded from markdown output
_NON_HUMAN_READABLE: set[str] = {"refid", "doc_embedding", "component_id"}

# Fields already captured by the heading or description text —
# not emitted as `- key: value` property lines.
_HEADING_FIELDS: set[str] = {"name", "description", "brief_description"}

# Lazy-import mapping for node types defined in external packages.
# The importer triggers these imports on first encounter so that the
# CodeGraphNode registry contains the class before deserialization.
_LAZY_IMPORTS: dict[str, str] = {
    "HLR": "codegraph_requirements.models.requirement",
    "LLR": "codegraph_requirements.models.requirement",
    "Component": "codegraph_project.models.component",
}


# ── Markdown Exporter ────────────────────────────────────────────────────


class MarkdownExporter:
    """Export a :class:`LayerGraph` to human-readable Markdown.

    By default, only the public API is shown (members with
    ``visibility`` unset or ``"public"``).  Set ``public_only=False``
    to include private and protected members.

    ``INHERITS_FROM`` and ``REALIZES`` / ``IMPLEMENTS`` relations
    appear as inline ``**Inherits from:**`` / ``**Implements:**``
    lines.  All other relationship types are collected in the
    ``## Relationships`` section.

    Args:
        graph: The :class:`LayerGraph` to export.
        fields: Which property fields to include.
            ``"llm"`` (default) — text-based with descriptions.
            ``"all"`` — every defined property as ``- key: value`` lines.
        public_only: If ``True`` (default), hide non-public members.
        leaf_types: Optional set of ``CodeGraphNode`` type name strings
            (e.g. ``{"LLR"}``, ``{"TestNode"}``) at which the exporter
            stops recursing into children.  Nodes of these types are
            rendered with their heading + description but their children
            are NOT emitted.  Use ``{"LLR"}`` to generate a
            requirements-only document (no tests, assertions, or steps).
            Defaults to empty set (full recursion — current behaviour).
    """

    def __init__(self, graph: LayerGraph, fields: str = "llm",
                 public_only: bool = True,
                 leaf_types: frozenset[str] = frozenset()):
        self.graph = graph
        self.fields = fields
        self.public_only = public_only
        self.leaf_types = leaf_types
        self._rel_lines: list[str] = []
        self._file_names: list[str] = []

    def export(self) -> str:
        """Return the Markdown representation as a string."""
        lines: list[str] = []

        tags_str = ", ".join(sorted(self.graph.tags))
        lines.append(f"# codegraph: {tags_str}")
        lines.append("")

        for entry in self.graph.entries.values():
            lines.extend(self._emit_entry(entry, depth=2))

        if self._file_names:
            lines.append("## File Notes")
            for name in self._file_names:
                lines.append(f"- `{name}`")
            lines.append("")

        if self._rel_lines:
            lines.append("## Relationships")
            lines.extend(self._rel_lines)
            lines.append("")

        return "\n".join(lines).rstrip() + "\n"

    # ── Element emission ──────────────────────────────────────────────

    def _emit_entry(self, entry: CompositeEntry, depth: int = 2) -> list[str]:
        """Recursively emit a CompositeEntry as Markdown.

        Delegates heading and description to
        :meth:`CodeGraphNode.to_markdown`.  The exporter handles
        member lists, inline relationships, and child recursion.
        """
        node = entry.node

        # Nodes that don't produce headings (FileNode) — queue and skip
        if not node.markdown_is_heading():
            self._file_names.append(node.name)
            return []

        # Heading + description from the model
        lines = node.to_markdown(depth)

        # Body section (methods/attributes or enum values)
        body_type = node.markdown_body_type()
        if body_type == "enum":
            lines.extend(self._emit_enum_body(entry))
        elif body_type == "compound":
            lines.extend(self._emit_compound_body(entry))

        # Inline relationships (Inherits from / Implements)
        lines.extend(self._emit_inline_rels(entry))

        # Extra properties (namespace, tags, etc.)
        lines.extend(self._emit_properties(entry))

        # Recurse into non-member children (classes inside namespaces, etc.)
        # Skip recursion if this node type is a leaf
        node_type_name = type(node).__name__
        if node_type_name in self.leaf_types:
            return lines

        for child_type, type_children in entry.children.items():
            if child_type not in _MEMBER_TYPES:
                for child_entry in type_children.values():
                    lines.extend(self._emit_entry(child_entry, depth + 1))

        lines.append("")
        return lines

    def _emit_compound_body(self, entry: CompositeEntry) -> list[str]:
        """Emit public API section for a class / interface / function."""
        lines: list[str] = []
        api_grouped = self._collect_api_members(entry)
        if api_grouped:
            for section_label, member_list in api_grouped:
                lines.append(section_label)
                for child_entry in member_list:
                    lines.append(self._format_api_list_item(child_entry))
        return lines

    def _emit_enum_body(self, entry: CompositeEntry) -> list[str]:
        """Emit enum value list."""
        if "EnumValueNode" in entry.children:
            lines = ["**Values:**"]
            for child_entry in entry.children["EnumValueNode"].values():
                lines.append(self._format_enum_value_item(child_entry))
            return lines
        return []

    def _emit_namespace(self, entry: CompositeEntry, depth: int = 2) -> list[str]:
        """Emit a namespace heading with description and nested children."""
        node = entry.node
        qname = getattr(node, "qualified_name", None) or node.name
        lines: list[str] = []

        lines.append(f"{'#' * depth} Namespace: `{qname}`")
        lines.extend(self._emit_description(node))
        lines.append("")

        for child_type, type_children in entry.children.items():
            if child_type not in _MEMBER_TYPES:
                for child_entry in type_children.values():
                    lines.extend(self._emit_entry(child_entry, depth + 1))

        return lines

    # ── Public API ───────────────────────────────────────────────────────

    def _collect_api_members(
        self, entry: CompositeEntry,
    ) -> list[tuple[str, list[CompositeEntry]]]:
        """Collect public member entries grouped by type.

        Returns a list of ``(section_label, [entries])`` tuples.
        """
        result: list[tuple[str, list[CompositeEntry]]] = []

        for member_type, label in [
            ("MethodNode", "**Public methods:**"),
            ("AttributeNode", "**Public attributes:**"),
        ]:
            if member_type not in entry.children:
                continue
            members = []
            for child_entry in entry.children[member_type].values():
                vis = getattr(child_entry.node, "visibility", "")
                if self.public_only and vis not in ("", "public"):
                    continue
                members.append(child_entry)
            if members:
                result.append((label, members))

        return result

    def _format_api_list_item(self, entry: CompositeEntry) -> str:
        """Format a public member as ``- `add(int a, int b): int` — description``.

        Always includes the full signature (args + return type for methods,
        type for attributes) in the default ``fields="llm"`` mode.
        """
        node = entry.node
        name = node.name
        brief = getattr(node, "brief_description", "") or ""

        node_type = type(node).__name__
        if node_type == "MethodNode":
            args = getattr(node, "argsstring", "()")
            ret = getattr(node, "type_signature", "")
            display = f"{name}{args}"
            if ret:
                display += f": {ret}"
        elif node_type == "AttributeNode":
            t = getattr(node, "type_signature", "")
            display = f"{name}: {t}" if t else name
        else:
            display = name

        line = f"- `{display}`"
        if brief:
            line += f" — {brief}"
        return line

    def _format_enum_value_item(self, entry: CompositeEntry) -> str:
        """Format an enum value as ``- `VALUE` — description``."""
        node = entry.node
        name = node.name
        brief = getattr(node, "brief_description", "") or ""
        line = f"- `{name}`"
        if brief:
            line += f" — {brief}"
        return line

    # ── Inline relationships ────────────────────────────────────────────

    def _emit_inline_rels(self, entry: CompositeEntry) -> list[str]:
        """Emit ``**Inherits from:**`` / ``**Implements:**`` for known rel types.

        Other relationship types are queued to the Relationships section.
        """
        lines: list[str] = []
        for rel_type, target_key, target_type in entry.references:
            if rel_type in _NESTING_REL_TYPES:
                continue
            label = _INLINE_REL_TYPES.get(rel_type)
            display_key = self.graph.resolve_target_name(target_key)
            if label:
                lines.append(f"**{label}:** `{display_key}`")
            else:
                source_qname = getattr(entry.node, "qualified_name", None) or entry.node.name
                target_type_str = f" ({target_type})" if target_type else ""
                self._rel_lines.append(
                    f"- `{source_qname}` → `{display_key}` **{rel_type.lower()}**{target_type_str}"
                )
        return lines

    # ── Extra properties ──────────────────────────────────────────────

    def _emit_properties(self, entry: CompositeEntry) -> list[str]:
        """Emit ``- key: value`` lines for _llm_fields not captured elsewhere.

        The heading already carries ``name``, and the description text
        carries ``description`` / ``brief_description``.  Any remaining
        ``_llm_fields`` (e.g. ``namespace`` on Component, ``tags``) are
        emitted as property lines so that import can restore them.

        ``tags`` is serialised as a comma-separated list.
        """
        node = entry.node
        lines: list[str] = []
        llm_fields = getattr(type(node), "_llm_fields", set())
        props = type(node).defined_properties()
        for key in sorted(llm_fields):
            if key in _HEADING_FIELDS or key in _NON_HUMAN_READABLE:
                continue
            if key not in props:
                continue
            value = getattr(node, key, None)
            if value is None or value == "" or value == []:
                continue
            if key == "tags":
                tags_list = list(value) if value else []
                if tags_list:
                    lines.append(f"- tags: {', '.join(tags_list)}")
            else:
                lines.append(f"- {key}: {value}")
        return lines


# ── Markdown Importer ─────────────────────────────────────────────────────


class MarkdownImporter:
    """Import Markdown class-diagram text into a :class:`LayerGraph`.

    Qualified names are read directly from heading text (e.g.
    ``### Class: `calc::CalculatorEngine` ``).  The ``name`` property
    is extracted from the last ``::`` segment.  Heading nesting is
    NOT used for qname derivation — the heading text is authoritative.

    Args:
        tags: Tags to apply to every imported node.
            Defaults to ``frozenset({"design"})``.
        strict: If ``True``, raise :class:`PlantUMLParseError` on errors.
    """

    def __init__(self, tags: frozenset[str] | None = None,
                 strict: bool = False):
        self._tags = list(tags) if tags else ["design"]
        self._strict = strict
        self.diagnostics: list[ParseDiagnostic] = []

    def import_markdown(self, text: str) -> LayerGraph:
        """Parse Markdown text and return a :class:`LayerGraph`."""
        self.diagnostics = []
        lines = text.split("\n")

        stack: list[tuple[str, str, CompositeEntry, int]] = []
        root_entries: dict[str, CompositeEntry] = {}
        qname_to_entry: dict[str, CompositeEntry] = {}
        pending_rels: list[tuple[str, str, str, str, int]] = []

        section: str | None = None
        # "methods", "attributes", "values", "files", "relationships"

        heading_re = re.compile(
            r'^(#{2,})\s+'
            r'(Namespace|Class|Interface|Enum|Function|Module|Union|Concept|Note'
            r'|Component|HLR|LLR|Test|Assertion|TestStep|TestFixture'
            r'|Attribute|Literal'
            r')'
            r':\s+`([^`]*)`'
        )

        # Inline property patterns
        inherits_re = re.compile(r'\*\*Inherits from:\*\*\s+`([^`]+)`')
        implements_re = re.compile(r'\*\*Implements:\*\*\s+`([^`]+)`')

        for line_no, line in enumerate(lines, start=1):
            stripped = line.strip()

            if not stripped:
                continue

            if stripped.startswith("# ") and not stripped.startswith("## "):
                continue

            # ── Heading ──────────────────────────────────────────────
            m = heading_re.match(stripped)
            if m:
                depth = len(m.group(1))
                keyword = m.group(2).lower()
                qname = m.group(3)
                name = qname.rsplit("::", 1)[-1] if "::" in qname else qname

                while stack and stack[-1][3] >= depth:
                    stack.pop()

                node_type = _KEYWORD_TO_NODE_TYPE.get(keyword)
                if node_type is None:
                    self._diag(line_no, "warning",
                               f"Unknown heading keyword: {keyword}")
                    continue

                node = self._create_node(node_type, name, qname)
                entry = CompositeEntry(node=node)
                qname_to_entry[qname] = entry

                if stack:
                    parent_entry = stack[-1][2]
                    if node_type not in parent_entry.children:
                        parent_entry.children[node_type] = {}
                    parent_entry.children[node_type][qname] = entry
                else:
                    root_entries[qname] = entry

                stack.append((qname, node_type, entry, depth))
                section = None
                continue

            # ── Inline properties ────────────────────────────────────
            if stack:
                mi = inherits_re.match(stripped)
                if mi:
                    pending_rels.append(
                        (stack[-1][0], mi.group(1), "INHERITS_FROM", "", line_no)
                    )
                    continue

                mi = implements_re.match(stripped)
                if mi:
                    pending_rels.append(
                        (stack[-1][0], mi.group(1), "REALIZES", "", line_no)
                    )
                    continue

            # ── Section markers ──────────────────────────────────────
            if stripped == "**Public methods:**" or stripped == "**Methods:**":
                section = "methods"
                continue
            if stripped == "**Public attributes:**" or stripped == "**Attributes:**":
                section = "attributes"
                continue
            if stripped == "**Values:**":
                section = "values"
                continue
            if stripped == "## File Notes":
                section = "files"
                continue
            if stripped == "## Relationships":
                section = "relationships"
                continue

            # ── Member / value / file lines ──────────────────────────
            if section == "methods" and stack:
                m = self._try_parse_member_line(stripped)
                if m is not None:
                    name, desc = m
                    self._add_member(stack, qname_to_entry, "MethodNode",
                                     name, "public", desc)
                    continue

            if section == "attributes" and stack:
                m = self._try_parse_member_line(stripped)
                if m is not None:
                    name, desc = m
                    self._add_member(stack, qname_to_entry, "AttributeNode",
                                     name, "public", desc)
                    continue

            if section == "values" and stack:
                m = self._try_parse_member_line(stripped)
                if m is not None:
                    self._add_member(stack, qname_to_entry, "EnumValueNode",
                                     m[0], "", m[1])
                    continue

            if section == "files":
                m = re.match(r'^-\s*`([^`]+)`\s*$', stripped)
                if m:
                    name = m.group(1)
                    self._create_file_entry(name, qname_to_entry, root_entries)
                    continue

            if section == "relationships":
                r = self._try_parse_relationship_line(stripped)
                if r is not None:
                    pending_rels.append((*r, line_no))
                    continue

            # ── Description / property line ─────────────────────────
            if stack and section is None:
                # Plain text after heading = description
                if not stripped.startswith("- ") and not stripped.startswith("`"):
                    # Set description on current node — use brief_description
                    # for compound nodes, or description for requirement/
                    # component nodes that don't have brief_description.
                    node = stack[-1][2].node
                    props = type(node).defined_properties()
                    if "brief_description" in props:
                        existing = getattr(node, "brief_description", "")
                        if not existing:
                            try:
                                setattr(node, "brief_description", stripped)
                            except AttributeError:
                                pass
                    elif "description" in props:
                        existing = getattr(node, "description", "")
                        if not existing:
                            try:
                                setattr(node, "description", stripped)
                            except AttributeError:
                                pass
                    continue

                # Property line: - key: value
                prop = self._try_parse_property(stripped)
                if prop is not None:
                    key, value = prop
                    self._apply_property(stack[-1][2].node, key, value)
                    continue

        # ── Resolve relationships ────────────────────────────────────
        for src_qname, tgt_qname, rel_type, tgt_type, rel_line in pending_rels:
            src_entry = qname_to_entry.get(src_qname)
            tgt_entry = qname_to_entry.get(tgt_qname)

            if src_entry is None:
                self._diag(rel_line, "error",
                           f"Relationship source {src_qname!r} not found")
                continue
            if tgt_entry is None:
                # Target not in this document — may be a cross-document
                # reference (e.g. tests → design-layer LLRs/classes).
                # Store the reference anyway; to_neo4j() will resolve
                # it via Neo4j lookup at persist time.
                self._diag(rel_line, "warning",
                           f"Relationship target {tgt_qname!r} not found "
                           f"in document — will attempt Neo4j lookup")
                src_entry.references.append((rel_type, tgt_qname, ""))
                continue

            tgt_type = tgt_type or type(tgt_entry.node).__name__
            src_entry.references.append((rel_type, tgt_qname, tgt_type))

        if self._strict:
            errors = [d for d in self.diagnostics if d.severity == "error"]
            if errors:
                raise PlantUMLParseError(errors)

        return LayerGraph(tags=frozenset(self._tags), entries=root_entries)

    # ── Diagnostics ──────────────────────────────────────────────────

    def _diag(self, line: int, severity: str, message: str) -> None:
        self.diagnostics.append(
            ParseDiagnostic(line=line, severity=severity, message=message)
        )

    # ── Member parsing ───────────────────────────────────────────────

    @staticmethod
    def _try_parse_member_line(
        line: str,
    ) -> tuple[str, str] | None:
        """Parse ``- `name` — description`` or ``- `name` ``.

        Returns ``(name, description)`` or ``None``.
        """
        m = re.match(r'^-\s*`([^`]+)`\s*—\s*(.+)$', line)
        if m:
            return (m.group(1).strip(), m.group(2).strip())
        m = re.match(r'^-\s*`([^`]+)`\s*$', line)
        if m:
            return (m.group(1).strip(), "")
        return None

    @staticmethod
    def _try_parse_relationship_line(
        line: str,
    ) -> tuple[str, str, str, str] | None:
        """Parse ``- `qname` → `qname` **label** (target_type)``."""
        m = re.match(
            r'^-\s*`([^`]+)`\s*→\s*`([^`]+)`\s*\*\*(\w+)\*\*\s*(?:\((\w+)\))?\s*$',
            line,
        )
        if m:
            source = m.group(1)
            target = m.group(2)
            label = m.group(3).lower().replace(" ", "_")
            rel_type = _LABEL_TO_REL_TYPE.get(label, label.upper())
            target_type = m.group(4) or ""
            return (source, target, rel_type, target_type)
        return None

    @staticmethod
    def _try_parse_property(line: str) -> tuple[str, str] | None:
        """Parse ``- key: value``."""
        if not line.startswith("- "):
            return None
        inner = line[2:].strip()
        if inner.startswith(">"):
            return None
        if ": " in inner:
            key, value = inner.split(": ", 1)
            return (key.strip(), value.strip())
        return None

    @staticmethod
    def _apply_property(node: CodeGraphNode, key: str, value: str) -> None:
        """Set property on node if it exists.

        For ``tags`` (an ArrayProperty), parses the comma-separated
        string into a list before assignment.
        """
        props = type(node).defined_properties()
        if key not in props:
            return
        if key == "tags":
            tag_list = [t.strip() for t in value.split(",") if t.strip()]
            setattr(node, key, tag_list)
        else:
            setattr(node, key, value)

    # ── Node creation ─────────────────────────────────────────────────

    def _create_node(self, node_type: str, name: str,
                     qname: str) -> CodeGraphNode:
        # Lazy-import model classes from external packages so that the
        # CodeGraphNode registry contains them before deserialization.
        if node_type in _LAZY_IMPORTS and node_type not in CodeGraphNode._registry:
            import importlib
            importlib.import_module(_LAZY_IMPORTS[node_type])

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
        node = CodeGraphNode.deserialize(data)

        # Initialize required StringProperty fields to empty string so
        # that ``to_neo4j()`` does not raise ``RequiredProperty`` during
        # ``deflate()``.  HLR, LLR, and Component all declare
        # ``description = StringProperty(required=True)`` — if the
        # description line is absent from the markdown (e.g. a heading
        # immediately followed by another heading), the property stays
        # ``None`` and ingestion fails.
        from neomodel import StringProperty
        for pname, prop in type(node).defined_properties().items():
            if not isinstance(prop, StringProperty):
                continue
            if not getattr(prop, "required", False):
                continue
            if getattr(node, pname, None) is None:
                setattr(node, pname, "")

        return node

    def _create_file_entry(
        self, name: str,
        qname_to_entry: dict[str, CompositeEntry],
        root_entries: dict[str, CompositeEntry],
    ) -> CompositeEntry:
        if name in qname_to_entry:
            return qname_to_entry[name]
        node = self._create_node("FileNode", name, name)
        entry = CompositeEntry(node=node)
        qname_to_entry[name] = entry
        if name not in root_entries:
            root_entries[name] = entry
        return entry

    def _add_member(
        self,
        stack: list[tuple[str, str, CompositeEntry, int]],
        qname_to_entry: dict[str, CompositeEntry],
        member_type: str,
        raw_identifier: str,
        visibility: str,
        brief_description: str,
    ) -> None:
        """Create a member node and add it as a child of the current parent.

        *raw_identifier* may be a bare name (``"add"``) or a full
        signature (``"add(int a, int b): int"``).  This method parses
        the signature components when present.
        """
        name = raw_identifier
        type_signature = ""
        argsstring = ""

        if member_type == "MethodNode":
            paren = raw_identifier.find("(")
            if paren >= 0:
                name = raw_identifier[:paren]
                end_paren = raw_identifier.rfind(")")
                if end_paren >= 0:
                    argsstring = raw_identifier[paren:end_paren + 1]
                    rest = raw_identifier[end_paren + 1:].strip()
                    if rest.startswith(":"):
                        type_signature = rest[1:].strip()
        elif member_type == "AttributeNode":
            colon = raw_identifier.find(":")
            if colon >= 0:
                name = raw_identifier[:colon].strip()
                type_signature = raw_identifier[colon + 1:].strip()

        parent_qname = stack[-1][0]
        parent_entry = stack[-1][2]
        qname = parent_qname + "::" + name

        data: dict = {
            "type": member_type,
            "name": name,
            "qualified_name": qname,
            "tags": list(self._tags),
        }
        kind = _NODE_TYPE_TO_KIND.get(member_type)
        if kind:
            data["kind"] = kind
        if visibility:
            data["visibility"] = visibility
        if type_signature:
            data["type_signature"] = type_signature
        if argsstring:
            data["argsstring"] = argsstring
        if brief_description:
            data["brief_description"] = brief_description

        node = CodeGraphNode.deserialize(data)
        entry = CompositeEntry(node=node)
        qname_to_entry[qname] = entry

        if member_type not in parent_entry.children:
            parent_entry.children[member_type] = {}
        parent_entry.children[member_type][qname] = entry


# ── Convenience functions ─────────────────────────────────────────────────


def export_markdown(graph: LayerGraph, fields: str = "llm",
                    public_only: bool = True,
                    leaf_types: frozenset[str] = frozenset()) -> str:
    """Export a :class:`LayerGraph` to Markdown.

    Args:
        graph: The graph to export.
        fields: ``"llm"`` (default) — text-based with descriptions.
            ``"all"`` — all properties as key-value lines.
        public_only: If ``True`` (default), hide non-public members.
        leaf_types: Types at which to stop recursion (see
            :class:`MarkdownExporter`).  Use ``frozenset({"LLR"})``
            for a requirements-only document.

    Returns:
        A Markdown document string.
    """
    return MarkdownExporter(graph, fields=fields,
                           public_only=public_only,
                           leaf_types=leaf_types).export()


def import_markdown(text: str, tags: frozenset[str] | None = None,
                    strict: bool = False) -> LayerGraph:
    """Import Markdown text into a :class:`LayerGraph`.

    Args:
        text: Markdown document string.
        tags: Tags to apply to every imported node.
            Defaults to ``frozenset({"design"})``.
        strict: Raise :class:`PlantUMLParseError` on errors.

    Returns:
        A :class:`LayerGraph` containing the parsed graph.
    """
    return MarkdownImporter(tags=tags, strict=strict).import_markdown(text)
