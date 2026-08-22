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
from enum import Enum

from codegraph.graph import CompositeEntry, LayerGraph
from codegraph.models.tags import CodeGraphNode


# ── Graph view mode ────────────────────────────────────────────────────


class GraphView(Enum):
    """View mode for PlantUML export.

    Attributes:
        FULL: Everything — all nodes, all members, all dependency edges.
        COLLAPSED: Full source code, but external dependencies (std,
            boost, spdlog, sqlite3) are collapsed into simple package
            declarations for a cleaner high-level view.  File nodes and
            file-reference edges are omitted.
        PUBLIC_API: Public API surface only.  Collapses external
            dependencies like COLLAPSED, but also hides private
            members, test scaffolding, concept nodes, and file nodes,
            and drops file-reference edges.  Shows only the
            public-facing classes, public members, and public functions.
        DESIGN_API: Design-layer view.  Shows the architectural design
            (classes, structs, enums, methods, attributes) and hides
            test scaffolding — TestNode, AssertionNode, TestStepNode,
            TestFixtureNode, and LiteralNode nodes are omitted along
            with their edges.
    """

    FULL = "full"
    COLLAPSED = "collapsed"
    PUBLIC_API = "public_api"
    DESIGN_API = "design_api"

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

# Matches a queued relationship-arrow line: ``SOURCE <arrow> TARGET : label``.
# Used to drop arrows whose endpoint was filtered out of the view (see
# ``PlantUMLExporter._arrow_endpoints_emitted``).
_ARROW_LINE_RE = re.compile(
    r"^(\S+)\s+(?:\.\.>|<\|--|\*--|\.\.\|>|-->|o--)\s+(\S+)"
)

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

# Structural relationships never rendered as arrows: nesting types plus
# TEMPLATE_PARAM (compound → template-parameter slot).  Type parameters
# are not emitted as standalone elements — the template parameter list
# is already visible in the member signature line — so a TEMPLATE_PARAM
# arrow would point at an element that doesn't exist in the diagram.
_STRUCTURAL_REL_TYPES: set[str] = _NESTING_REL_TYPES | {"TEMPLATE_PARAM"}

#: Node types that are design/test scaffolding, not architecture.
#: PUBLIC_API and DESIGN_API hide these by TYPE (the design agent may tag
#: them ``design``, so a tag-based filter is not reliable).
_SCAFFOLDING_TYPES: frozenset[str] = frozenset({
    "TestNode", "TestStepNode", "AssertionNode", "TestFixtureNode",
    "LiteralNode", "HLR", "LLR",
})

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


def _short_display_name(node) -> str:
    """Return the short display name for a node.

    If ``node.name`` equals ``node.qualified_name`` (common when the
    markdown importer can't split on ``::`` for Python-style dotted
    names), extract the last segment as the short name.
    """
    name = getattr(node, "name", "") or ""
    qname = getattr(node, "qualified_name", "") or ""
    if name == qname and ("." in qname or "::" in qname):
        # Split on the last separator (prefer ::, fall back to .)
        if "::" in qname:
            return qname.rsplit("::", 1)[-1]
        return qname.rsplit(".", 1)[-1]
    return name


def _escape_quoted_label(value: str) -> str:
    """Escape arbitrary text for a double-quoted PlantUML label.

    Node names can originate from source literals and therefore contain
    quotes, backslashes, and physical line breaks.  Emitting those bytes
    directly terminates or splits the PlantUML declaration.  Keep each
    declaration on one source line and let PlantUML render control
    characters through its escape syntax.
    """
    return (value.replace("\\", "\\\\")
                 .replace('"', '\\"')
                 .replace("\r\n", "\\n")
                 .replace("\r", "\\n")
                 .replace("\n", "\\n")
                 .replace("\t", "\\t"))


def _sanitize_alias(name: str) -> str:
    """Convert a qualified name to a valid PlantUML alias.

    Replaces ``::`` with ``__`` and special characters (spaces,
    dots, parentheses, angle brackets, braces, commas, slashes,
    equals, asterisks, ampersands) with ``_``.  The result is a
    valid PlantUML identifier usable in ``as alias`` clauses and
    arrow source/target references.

    Curly braces are structurally significant in PlantUML (they open
    and close element bodies), so a signature default like
    ``event_handlers = {}`` must NOT leak ``{}`` into an alias —
    PlantUML would read ``{`` as the start of a class body and fail
    with a syntax error.

    Args:
        name: A qualified name (e.g. ``calc::CalculatorEngine``).

    Returns:
        A sanitized alias (e.g. ``calc__CalculatorEngine``).
    """
    # Replace :: first (namespace separator → double underscore)
    sanitized = name.replace("::", "__")
    # PlantUML aliases are identifiers, so source-derived text must not leak
    # control characters, backslashes, punctuation, or operators into them.
    sanitized = re.sub(r"[^A-Za-z0-9_]", "_", sanitized)
    # Collapse consecutive underscores from special-char runs
    # (e.g. "foo(())bar"  →  "foo___bar"  → "foo_bar").
    # We must NOT collapse __ from namespace separators though.
    # Strategy: only collapse runs of 3+ underscores, then strip
    # trailing/leading underscores from special-char runs.
    while "___" in sanitized:
        sanitized = sanitized.replace("___", "__")
    return sanitized.strip("_")


def _visibility_prefix(visibility: str) -> str:
    """Convert a visibility string to a PlantUML prefix character.

    Args:
        visibility: One of ``"public"``, ``"private"``, ``"protected"``,
            or empty string (defaults to public).

    Returns:
        The PlantUML visibility prefix (``+``, ``-``, ``#``).
    """
    return _VISIBILITY_MAP.get(visibility, "+")


def _short_display_name(node) -> str:
    """Return a compact display name for a node.

    When ``name`` equals ``qualified_name`` (e.g. a design node where
    the importer set both to the same FQN), extract just the short
    name.  Otherwise return ``name`` as-is.
    """
    name = getattr(node, "name", "")
    qn = getattr(node, "qualified_name", "")
    if not name or not qn:
        return name or qn or ""
    if name == qn and "." in qn:
        return qn.rsplit(".", 1)[-1]
    if name == qn and "::" in qn:
        return qn.rsplit("::", 1)[-1]
    return name


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


def _parent_qname(member_qname: str) -> str | None:
    """Strip the last ``::name(args)`` segment to get the parent
    compound's qualified name.

    Returns None if the string doesn't contain ``::`` (e.g. it's a
    free function or root-level type).
    """
    if "::" not in member_qname:
        return None
    idx = member_qname.rindex("::")
    return member_qname[:idx]


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
        view: The visualisation view mode (default :attr:`GraphView.FULL`).
            * ``FULL`` — all nodes, all members, all dependency edges.
            * ``COLLAPSED`` — full source code but external deps
              collapsed into packages; file nodes / file edges omitted.
            * ``PUBLIC_API`` — like COLLAPSED but also hides private
              members, test scaffolding, concept nodes, and file nodes.
              Shows only the public-facing API surface.
    """

    def __init__(self, graph: LayerGraph, fields: str = "llm",
                 view: GraphView = GraphView.FULL,
                 scope_class: str | None = None):
        self.graph = graph
        self.fields = fields
        self.view = view
        self.scope_class = scope_class
        self._aliases: dict[str, str] = {}      # qualified_name → alias
        self._rel_lines: list[str] = []           # arrow lines (emitted last)
        self._rel_set: set[str] = set()            # dedup set for arrow lines
        self._seen: set[str] = set()              # aliases already emitted
        # Compound children hoisted out of their parent's class body
        # (parent_alias, child_entry) — PlantUML cannot render
        # class-in-class, so they emit at top level with a *-- arrow.
        self._hoisted_compounds: list[tuple[str, CompositeEntry]] = []
        # When collapsing deps: mapping from collapsed alias → package alias
        self._collapsed_prefixes: dict[str, str] = {}
        # Set of aliases that should be skipped (collapsed into package)
        self._collapsed_keys: set[str] = set()
        # Node key (uid) → collapsed package prefix, for redirecting
        # edges whose target was collapsed by SOURCE rather than by
        # qname prefix (root-level external classes whose namespace
        # prefix was flattened away by doxygen).
        self._collapsed_key_prefix: dict[str, str] = {}
        # Mapping from member target_key → parent compound alias.
        # Used to redirect arrows targeting member nodes (which are
        # rendered inline) to the parent compound that IS a standalone
        # PlantUML element.
        self._member_parent_aliases: dict[str, str] = {}
        # Scoping: which classes and members to emit when scope_class
        # is set.  The target class shows ALL members; dependent
        # classes only show the members actually referenced.
        self._allowed_classes: set[str] = set()
        self._allowed_members: dict[str, set[str]] = {}
        # Canonical node keys carrying the "test" tag.
        # DESIGN_API hides these — they are test scaffolding, not
        # architectural design elements. The tag is set by the design
        # agent during node creation.
        self._test_tagged_keys: set[str] = self._build_test_tagged_keys()
        self._flat: dict | None = None            # cached flat entry index

    def _flat_index(self) -> dict:
        """Build the flat key → entry index once per export.

        ``resolve_target_name`` defaults to rebuilding the index per
        call (O(N) each) — over thousands of references that is
        quadratic and dominated integration-test runtime.  Cache it
        here and pass it to every resolution.
        """
        if self._flat is None:
            self._flat = self.graph._flat_index()
        return self._flat

    # ── Derived properties ────────────────────────────────────────────

    def _collapse_deps(self) -> bool:
        """True when external deps should be collapsed into packages."""
        if self.scope_class:
            return True  # scoped view always collapses externals
        return self.view in (GraphView.COLLAPSED, GraphView.PUBLIC_API)

    def _show_private(self) -> bool:
        """True when private members should be included."""
        if self.scope_class:
            return True  # scoped view shows all members
        return self.view != GraphView.PUBLIC_API

    def _show_files(self) -> bool:
        """True when file nodes and file edges should be included."""
        return False  # files never shown in scoped or collapsed/public

    def _show_concepts(self) -> bool:
        """True when concept nodes should be included."""
        if self.scope_class:
            return False  # concepts never shown in scoped view
        return self.view != GraphView.PUBLIC_API

    def _show_tests(self) -> bool:
        """True when test-tagged nodes should be included.

        PUBLIC_API and DESIGN_API hide any node carrying the ``"test"`` tag —
        TestNode, AssertionNode, TestStepNode, TestFixtureNode,
        and any AttributeNode/LiteralNode used as test fixtures.
        The ``"test"`` tag is set by the design agent during node
        creation, not inferred from node type.
        """
        return self.view not in (GraphView.PUBLIC_API, GraphView.DESIGN_API)

    def _build_test_tagged_keys(self) -> set[str]:
        """Build a precomputed set of node keys that carry the ``"test"`` tag.

        Called once during ``__init__`` so that reference filters can
        perform O(1) lookups instead of rebuilding the flat index."""
        keys: set[str] = set()
        for entry in self.graph._all_entries():
            tags = getattr(entry.node, "tags", []) or []
            if "test" in tags:
                keys.add(self.graph._node_key(entry.node))
        return keys

    def _target_has_tag(self, target_key: str, tag: str) -> bool:
        """Check whether the target node identified by *target_key*
        carries *tag*.

        Uses the precomputed ``_test_tagged_keys`` set for O(1) lookup
        when *tag* is ``"test"``; falls back to a flat-index walk for
        other tags (which is rare)."""
        if tag == "test":
            return target_key in self._test_tagged_keys
        flat = self.graph._flat_index()
        entry = flat.get(target_key)
        if entry is None:
            return False
        tags = getattr(entry.node, "tags", []) or []
        return tag in tags

    def _show_external(self) -> bool:
        """True when external dependency packages should be included."""
        if self.scope_class:
            return True  # scoped view always shows external packages
        return self.view != GraphView.PUBLIC_API

    # ── Scoped-view helpers ─────────────────────────────────────────

    def _is_scoped(self) -> bool:
        """True when we're exporting a class-scoped view."""
        return self.scope_class is not None

    def _entry_is_in_scope(self, entry: CompositeEntry) -> bool:
        """Check whether *entry* should be emitted in scoped mode.

        Namespaces are kept as long as any descendant qualifies;
        compounds must have their qualified name in
        ``_allowed_classes``.
        """
        node_type = type(entry.node).__name__
        qname = getattr(entry.node, "qualified_name", None) or entry.node.name
        if qname in self._allowed_classes:
            return True
        if node_type in ("NamespaceNode", "ModuleNode"):
            # emit namespace if any allowed class lives inside it
            return self._namespace_has_allowed_descendant(entry)
        return False

    def _namespace_has_allowed_descendant(self, entry: CompositeEntry) -> bool:
        """Walk children of a namespace entry to check for allowed descendants."""
        for child_type, type_children in entry.children.items():
            for child_entry in type_children.values():
                cqname = getattr(child_entry.node, "qualified_name", None) or ""
                if cqname in self._allowed_classes:
                    return True
                if self._namespace_has_allowed_descendant(child_entry):
                    return True
        return False

    # ── Class scoping ─────────────────────────────────────────────────

    def _compute_scope(self) -> None:
        """Populate ``_allowed_classes`` and ``_allowed_members`` by
        walking the scoped class's members and collecting every class
        and member they reference.

        The scoped class itself gets ALL members.  Dependent classes
        only show the specific members that are referenced.
        """
        if not self.scope_class:
            return

        target_entry = None
        for entry in self.graph._all_entries():
            if entry.node.qualified_name == self.scope_class:
                target_entry = entry
                break
        if target_entry is None:
            raise ValueError(
                f"Scope class {self.scope_class!r} not found in graph"
            )

        target_qname = target_entry.node.qualified_name
        self._allowed_classes.add(target_qname)

        # The scoped class's OWN relationships (INHERITS_FROM,
        # DEPENDS_ON, …) must also be allowed — e.g. its base class is
        # a legitimate 1-hop neighbour and should render as a real
        # element so the inheritance arrow resolves.  Without this, the
        # base appears only as a phantom arrow target.
        for rel_type, target_key, _target_type in target_entry.references:
            if rel_type == "DEFINED_IN":
                continue
            display = self.graph.resolve_target_name(
                target_key, flat=self._flat_index()
            )
            if not display:
                continue
            if _target_type in ("MethodNode", "AttributeNode"):
                parent_qname = _parent_qname(display)
                if parent_qname:
                    self._allowed_classes.add(parent_qname)
                    self._allowed_members.setdefault(
                        parent_qname, set()
                    ).add(display)
            elif _target_type in ("ClassNode", "EnumNode",
                                  "InterfaceNode", "UnionNode",
                                  "StructNode", "FunctionNode",
                                  "DefineNode"):
                self._allowed_classes.add(display)

        for member_type in ("MethodNode", "AttributeNode"):
            if member_type not in target_entry.children:
                continue
            for child_entry in target_entry.children[member_type].values():
                for rel_type, target_key, _target_type in child_entry.references:
                    if rel_type == "DEFINED_IN":
                        continue
                    display = self.graph.resolve_target_name(
                        target_key, flat=self._flat_index()
                    )
                    if not display:
                        continue
                    if display.startswith(target_qname + "::"):
                        continue
                    if _target_type in ("MethodNode", "AttributeNode"):
                        parent_qname = _parent_qname(display)
                        if parent_qname:
                            self._allowed_classes.add(parent_qname)
                            self._allowed_members.setdefault(
                                parent_qname, set()
                            ).add(display)
                    elif _target_type in ("ClassNode", "EnumNode",
                                          "InterfaceNode", "UnionNode",
                                          "StructNode", "FunctionNode",
                                          "DefineNode"):
                        self._allowed_classes.add(display)

    # ── Scoped class lookup ───────────────────────────────────────────

    def scoped_allowed_classes(self) -> set[str]:
        """Compute and return the class qnames in scope: the scoped
        class plus its 1-hop neighbours (bases, dependencies, referenced
        types).  Used by sibling exporters (e.g. coverage Markdown) that
        need the same test→class matching without emitting PlantUML.

        Raises:
            ValueError: When ``scope_class`` is not set or not found in
                the graph.
        """
        if not self.scope_class:
            raise ValueError("scope_class is required")
        self._compute_scope()
        return self._allowed_classes

    # ── export() ─────────────────────────────────────────────────────

    def _arrow_endpoints_emitted(self, line: str) -> bool:
        """Return True when both endpoints of a queued arrow were emitted
        as elements (their aliases are in ``_seen``).

        Arrows to filtered-out targets — 2-hop neighbours in
        ``scope_class`` mode, hidden private members in PUBLIC_API,
        anything collapsed or otherwise not emitted — would otherwise
        make PlantUML synthesize phantom nodes that float outside the
        namespace tree.  ``_seen`` is authoritative: it is populated by
        every element emission path (namespace/compound/enum emission,
        scoped-class member nodes, collapsed package declarations,
        hoisted compounds) before the arrow flush happens.
        """
        m = _ARROW_LINE_RE.match(line)
        if not m:
            return True  # not an arrow line — keep as-is
        return m.group(1) in self._seen and m.group(2) in self._seen

    def export(self) -> str:
        """Return the PlantUML representation as a string.

        Returns:
            A complete PlantUML class-diagram string enclosed in
            ``@startuml`` / ``@enduml``.
        """
        import os as _os
        def _dbg(msg: str) -> None:
            if _os.environ.get("CODEGRAPH_DEBUG") == "1":
                print(f"[DBG plantuml] {msg}", flush=True)

        lines: list[str] = ["@startuml"]

        # Compute scoped view: which classes and members to show
        _dbg("compute_scope...")
        self._compute_scope()
        _dbg("compute_scope done")

        # Style hints
        lines.append("skinparam classAttributeIconSize 0")
        lines.append("")

        # When collapsing dependency details, pre-compute which
        # entries get collapsed into simple package declarations.
        if self._collapse_deps():
            _dbg("build_collapsed_namespaces...")
            self._build_collapsed_namespaces()
            _dbg("build_collapsed_namespaces done")
            # In PUBLIC_API mode, external packages are hidden entirely.
            # In COLLAPSED mode, emit synthetic package declarations.
            if self._show_external():
                for prefix in sorted(self._collapsed_prefixes):
                    alias = self._collapsed_prefixes[prefix]
                    display = _sanitize_alias(prefix).strip("_")
                    lines.append(f'package "{display}" as {alias} {{')
                    lines.append("}")
                    self._seen.add(alias)
            lines.append("")

        # Pre-build the member→parent alias map before emitting any
        # elements.  This avoids order-dependency: a reference from
        # class A to class B's member must resolve to B's alias even
        # when A is emitted before B.
        #
        # When hiding private members, build the map from ALL members
        # (including private) so that arrows TARGETING a private
        # member can still redirect to the parent compound.
        _dbg("build_member_parent_map...")
        self._build_member_parent_map(include_private_members=True)
        _dbg("build_member_parent_map done")

        # Emit elements for root entries (depth-first)
        _dbg("emit entries...")
        for entry in self.graph.entries.values():
            lines.extend(self._emit_entry(entry, indent=0))
        _dbg(f"emit entries done: {len(self._rel_lines)} rel lines")

        # Emit compound children that were hoisted out of their parent's
        # class body (composition across compounds renders as *-- arrows,
        # never class-in-class nesting).
        _dbg("emit hoisted compounds...")
        for parent_alias, child_entry in self._hoisted_compounds:
            child_qn = (
                getattr(child_entry.node, "qualified_name", None)
                or child_entry.node.name
            )
            child_alias = _sanitize_alias(child_qn)
            if child_alias in self._seen:
                pass  # already emitted via another parent / the namespace
            else:
                child_lines = self._emit_entry(child_entry, indent=0)
                if not child_lines:
                    # Filtered out of this view — no arrow to a phantom.
                    continue
                lines.extend(child_lines)
            line = f"{parent_alias} *-- {child_alias} : composes"
            if line not in self._rel_set:
                self._rel_set.add(line)
                self._rel_lines.append(line)
        _dbg("emit hoisted compounds done")

        # Emit relationship arrows (sorted for deterministic output).
        # Arrows whose endpoint was filtered out of the view (e.g. a
        # 2-hop target in scoped mode) are dropped first — emitting
        # them would make PlantUML synthesize phantom nodes outside
        # the namespace tree.
        rel_lines = [
            line for line in self._rel_lines
            if self._arrow_endpoints_emitted(line)
        ]
        if rel_lines:
            lines.append("")
            lines.append("' ── Relationships ─────────────────────")
            _dbg("sort rel lines...")
            lines.extend(sorted(rel_lines))
            _dbg("sort rel lines done")

        lines.append("")
        lines.append("@enduml")
        return "\n".join(lines)

    def _build_member_parent_map(self,
                                  include_private_members: bool = True) -> None:
        """Pre-build ``_member_parent_aliases`` by walking the full
        composition tree before any emission.

        For every member (MethodNode, AttributeNode, EnumValueNode),
        records the alias of its parent compound.  This map is used
        during arrow emission to redirect member-targeted edges to
        the parent compound that IS a standalone PlantUML element.

        Must be called before any emission because the map is
        populated from the tree structure, not from emission order.

        Indexes by both UID hash and qualified name so lookups work
        regardless of how the reference stores its target_key.

        Args:
            include_private_members: When False, private members are
                excluded from the map.  The map should always be built
                with all members (including private) so that arrows
                targeting a hidden member can still resolve.  The
                *filtering* happens during emission, not during map
                construction.
        """
        for entry in self.graph._all_entries():
            node = entry.node
            qname = getattr(node, "qualified_name", None) or ""
            # When scoped, only build the map for classes in the scope
            if self.scope_class and qname not in self._allowed_classes:
                continue
            alias = _sanitize_alias(qname) if qname else ""
            for member_type in ("MethodNode", "AttributeNode"):
                if member_type in entry.children:
                    for child_entry in entry.children[member_type].values():
                        if not include_private_members:
                            vis = getattr(child_entry.node, "visibility", "")
                            if vis == "private":
                                continue
                        # When scoped, skip members not in the
                        # allowed set for non-target classes
                        if self.scope_class and qname != self.scope_class:
                            child_qn = getattr(
                                child_entry.node, "qualified_name", ""
                            )
                            allowed = self._allowed_members.get(qname, set())
                            if child_qn not in allowed:
                                continue
                        child_node = child_entry.node
                        self._member_parent_aliases[
                            child_node.canonical_key
                        ] = alias
                        child_qname = getattr(child_node, "qualified_name", None) or ""
                        if child_qname:
                            self._member_parent_aliases[child_qname] = alias
            # Also handle enum values
            if "EnumValueNode" in entry.children:
                for child_entry in entry.children["EnumValueNode"].values():
                    child_node = child_entry.node
                    self._member_parent_aliases[
                        child_node.canonical_key
                    ] = alias
                    child_qname = getattr(child_node, "qualified_name", None) or ""
                    if child_qname:
                        self._member_parent_aliases[child_qname] = alias

    # ── Collapsed-namespace support ───────────────────────────────────

    def _build_collapsed_namespaces(self) -> None:
        """Scan all entries and identify non-project namespaces to collapse.

        When *view* is :attr:`GraphView.COLLAPSED` or
        :attr:`GraphView.PUBLIC_API`, external dependencies
        are collapsed into simple package declarations.  The project
        namespace ``cpp_sqlite`` and root-level classes like
        ``DAOBase`` are emitted in full; everything else is collapsed
        into its top-level namespace prefix.

        Classification is by ``source`` attribute FIRST — a node tagged
        with an external library is external even when its qname lost
        the namespace prefix (doxygen flattens e.g.
        ``boost::utf8_codecvt_facet`` to ``utf8_codecvt_facet``, whose
        root-level members would otherwise leak into project views).
        Falls back to qname-prefix classification for untagged nodes.
        """
        project_prefix = "cpp_sqlite"
        # Known external libraries whose types we collapse into packages
        _KNOWN_EXTERNAL: set[str] = {
            "std", "boost", "spdlog", "sqlite3",
            "detail", "fmt", "mp_cond",
        }
        # Source labels that are definitively external libraries.
        _EXTERNAL_SOURCES: set[str] = {
            "std", "boost", "spdlog", "sqlite3",
            "detail", "fmt", "mp_cond", "cppreference",
        }
        # Root-level project names (no ::) that should NOT be collapsed
        _PROJECT_ROOTS: set[str] = {"DAOBase"}

        all_entries = list(self.graph._all_entries())
        for e in all_entries:
            node = e.node
            qn = getattr(node, "qualified_name", "") or ""
            if not qn:
                continue
            if qn == project_prefix or qn.startswith(project_prefix + "::"):
                continue

            if "::" in qn:
                prefix = qn.split("::", 1)[0]
            else:
                prefix = qn

            # Only collapse known external prefixes or root-level
            # external entries (sqlite3_* functions, etc.)
            if prefix not in _KNOWN_EXTERNAL and prefix not in _PROJECT_ROOTS:
                # Check if this is a root-level external function/class
                # (e.g. sqlite3_step, sqlite3_column_int64)
                name = getattr(node, "name", "") or qn
                found = False
                for ext in ("sqlite3",):
                    if name == ext or name.startswith(ext + "_"):
                        prefix = ext
                        found = True
                        break
                if not found:
                    # Qname didn't classify it — fall back to the node's
                    # SOURCE label.  Doxygen flattens some external
                    # classes to namespace-less qnames (e.g.
                    # ``boost::utf8_codecvt_facet`` →
                    # ``utf8_codecvt_facet``); the source attribute is
                    # the ground truth for those.
                    node_source = getattr(node, "source", "") or ""
                    if node_source in _EXTERNAL_SOURCES:
                        prefix = node_source
                    else:
                        continue  # Project type, don't collapse

            # Also skip project root-level entries
            if prefix in _PROJECT_ROOTS:
                continue

            if prefix not in self._collapsed_prefixes:
                self._collapsed_prefixes[prefix] = _sanitize_alias(prefix).strip("_")

            key = node.canonical_key
            if key:
                self._collapsed_keys.add(key)
                self._collapsed_key_prefix[key] = prefix

    def _collapsed_alias_for(self, target_key: str) -> str | None:
        """If *target_key* falls under a collapsed namespace, return
        the package alias to redirect to.  Returns None otherwise."""
        if not self._collapsed_prefixes:
            return None

        # Resolve the target key to a display name
        display = self.graph.resolve_target_name(
            target_key, flat=self._flat_index()
        )
        if not display or display == target_key:
            # The raw key is a collapsed entry — map it through the
            # uid→prefix table recorded at classification time (covers
            # root-level external classes collapsed by SOURCE).
            prefix = self._collapsed_key_prefix.get(target_key)
            if prefix:
                return self._collapsed_prefixes.get(prefix)
            return None

        # Check if display name starts with any collapsed prefix::
        for prefix, alias in self._collapsed_prefixes.items():
            if display == prefix or display.startswith(prefix + "::"):
                return alias
            # Also check root-level entries (no ::)
            if prefix == "sqlite3" and (display == "sqlite3"
                                         or display.startswith("sqlite3_")):
                return alias

        return None

    def _should_skip_entry(self, entry: CompositeEntry) -> bool:
        """Return True if *entry* belongs to a collapsed namespace."""
        if not self._collapsed_keys:
            return False
        key = entry.node.canonical_key
        return key in self._collapsed_keys if key else False

    def _entry_is_root(self, entry: CompositeEntry) -> bool:
        """True when *entry* is a top-level graph entry (not nested)."""
        return any(entry is root for root in self.graph.entries.values())

    # ── Element emission ──────────────────────────────────────────────

    def _emit_entry(self, entry: CompositeEntry, indent: int = 0) -> list[str]:
        """Recursively emit a CompositeEntry and its composed children.

        When *view* is :attr:`GraphView.COLLAPSED` or
        :attr:`GraphView.PUBLIC_API`, entries belonging to
        collapsed external namespaces are skipped entirely.

        Args:
            entry: The CompositeEntry to emit.
            indent: Current indentation level.

        Returns:
            A list of PlantUML lines.
        """
        # Skip entries that belong to collapsed external namespaces
        if self._should_skip_entry(entry):
            return []
        node = entry.node
        node_type = type(node).__name__

        # Skip type-parameter slots (kind='type_parameter', qname
        # ``type_param:<parent>:<pos>``): template scaffolding, not
        # diagram elements.  TEMPLATE_PARAM edges to them are
        # suppressed via _STRUCTURAL_REL_TYPES, and their outgoing
        # edges (e.g. ENFORCES_CONCEPT) are dropped with them since
        # references are emitted from the entry.
        if (
            getattr(node, "kind", "") == "type_parameter"
            or (getattr(node, "qualified_name", "") or "").startswith("type_param:")
        ):
            return []

        # Design/test scaffolding is hidden from PUBLIC_API/DESIGN_API by
        # node TYPE — the design agent may tag these ``design``, so the
        # legacy tag-based check below is not sufficient.
        if node_type in _SCAFFOLDING_TYPES and not self._show_tests():
            return []

        # Standalone members (root-level AttributeNode/MethodNode/…)
        # are test fixtures in design graphs — they exist only to feed
        # hidden assertions.  Hide them from DESIGN_API.
        if (
            node_type in _MEMBER_TYPES
            and not self._show_tests()
            and self._entry_is_root(entry)
        ):
            return []

        # Scoped-view: skip entries not in the allowed set.
        # Namespaces are kept if any descendant qualifies.
        if self._is_scoped() and not self._entry_is_in_scope(entry):
            return []

        # Skip file nodes and concept nodes in restricted view modes.
        # File nodes are skipped in COLLAPSED and PUBLIC_API; concept
        # nodes are skipped only in PUBLIC_API.
        if node_type == "FileNode" and not self._show_files():
            return []
        if node_type == "ConceptNode" and not self._show_concepts():
            return []
        if node_type in ("ParameterNode", "LiteralNode"):
            # Parameters and assertion literals are implementation/
            # verification detail, never standalone UML elements.  Raw
            # literals can also contain entire source snippets, making an
            # architectural diagram enormous and meaningless.
            return []
        tags = getattr(node, "tags", []) or []
        if "test" in tags and not self._show_tests():
            return []

        qname = getattr(node, "qualified_name", None) or node.name

        # When scoped to a class, only emit the scoped class and its
        # direct dependencies.  Namespaces are kept as containers only
        # when they hold a required child.
        if self.scope_class and qname not in self._allowed_classes:
            # Allow namespace packages — children are filtered inside
            if node_type in ("NamespaceNode", "ModuleNode"):
                pass
            else:
                return []

        prefix = "  " * indent

        # Get or create alias
        alias = _sanitize_alias(qname)
        self._aliases[qname] = alias

        # Emit references as arrows.  COMPOSES is normally represented by
        # nesting (children) and skipped; when a graph stores it as a flat
        # reference (e.g. markdown-imported scaffold designs where the
        # composed classes are top-level entries), the arrow renders so
        # the composition is not silently dropped from the diagram.
        for rel_type, target_key, target_type in entry.references:
            self._emit_reference(entry, rel_type, target_key, target_type)

        # Choose emission strategy by node type.
        # TestNode and HLR/LLR nodes with child elements use
        # "package" to avoid PlantUML nested-class-in-class
        # rendering errors (V1.2026.6 crashes on class{ class{ }}).
        if node_type in ("NamespaceNode", "ModuleNode", "TestNode",
                         "HLR", "LLR"):
            return self._emit_namespace(entry, alias, indent)
        elif node_type == "FileNode":
            return self._emit_file(entry, alias, indent)
        elif node_type == "EnumNode":
            return self._emit_enum(entry, alias, indent)
        else:
            # The scoped class renders as a normal compound (members
            # inline in the class body, member edges aggregated to the
            # class alias) — the earlier atomic per-member-node style
            # was too busy for visualisation.
            return self._emit_compound(entry, alias, indent)

    def _emit_namespace(self, entry: CompositeEntry, alias: str,
                        indent: int = 0) -> list[str]:
        """Emit a namespace (package) with nested children."""
        node = entry.node
        prefix = "  " * indent
        keyword = _NODE_TYPE_TO_PLANTUML.get(type(node).__name__, "package")
        stereotype = _NODE_TYPE_TO_STEREOTYPE.get(type(node).__name__)
        display_name = _escape_quoted_label(_short_display_name(node))

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
        display_name = _escape_quoted_label(_short_display_name(node))

        lines: list[str] = []
        stereo = f" <<{stereotype}>>" if stereotype else ""
        lines.append(f'{prefix}{keyword} "{display_name}" as {alias}{stereo} {{')

        # Emit member children (methods, attributes) inside the class body.
        # When showing private interface is disabled, skip private members.
        for member_type in ("MethodNode", "AttributeNode"):
            if member_type in entry.children:
                for child_entry in entry.children[member_type].values():
                    # Filter out private members in PUBLIC_API mode
                    if not self._show_private():
                        vis = getattr(child_entry.node, "visibility", "")
                        if vis == "private":
                            continue
                    # When scoped, dependent classes only show the
                    # members actually referenced — not all members.
                    if self.scope_class:
                        child_qname = getattr(
                            child_entry.node, "qualified_name", ""
                        )
                        parent_qname = getattr(node, "qualified_name", "")
                        if parent_qname != self.scope_class:
                            allowed = self._allowed_members.get(
                                parent_qname, set()
                            )
                            if child_qname not in allowed:
                                continue
                    lines.append(self._format_member_line(child_entry))
                    # Record this member's parent alias for redirecting
                    # arrows that target member nodes (which are never
                    # standalone PlantUML elements).
                    child_key = child_entry.node.canonical_key
                    if child_key:
                        self._member_parent_aliases[child_key] = alias
                    # Emit member-level references (INVOKES, DEPENDS_ON, etc.)
                    # as arrows from the owning compound.  The member itself
                    # is collapsed into the class body so its edges must
                    # originate from the class.  Deduplicate: multiple
                    # members may depend on the same target, but visually
                    # that's one edge.
                    for rel_type, target_key, target_type in child_entry.references:
                        if rel_type in _STRUCTURAL_REL_TYPES:
                            continue
                        # Skip references to node types hidden in
                        # the current view mode.
                        if target_type == "FileNode" and not self._show_files():
                            continue
                        if target_type == "ConceptNode" and not self._show_concepts():
                            continue
                        if target_type == "ParameterNode":
                            # Parameters are function-signature detail
                            # (rendered inside the member line), never
                            # standalone PlantUML elements.
                            continue
                        if target_type in _SCAFFOLDING_TYPES and not self._show_tests():
                            continue
                        if self._target_has_tag(target_key, "test") and not self._show_tests():
                            continue
                        # Redirect to collapsed namespace package if applicable
                        collapsed = self._collapsed_alias_for(target_key)
                        if collapsed:
                            # In PUBLIC_API mode, external dependency
                            # edges are dropped entirely.
                            if self.view == GraphView.PUBLIC_API:
                                continue
                            target_alias = collapsed
                        else:
                            display_key = self.graph.resolve_target_name(
                                target_key, flat=self._flat_index()
                            )
                            target_alias = _sanitize_alias(display_key) if display_key else ""
                            # If the target is a member type, redirect
                            # to the parent compound's alias — members
                            # are rendered inline and never standalone.
                            if target_type in _MEMBER_TYPES:
                                parent_alias = self._member_parent_aliases.get(target_key)
                                if parent_alias:
                                    target_alias = parent_alias
                        if not target_alias:
                            continue
                        arrow = _REL_TYPE_TO_ARROW.get(rel_type, "..>")
                        label = rel_type.lower()
                        line = f"{alias} {arrow} {target_alias} : {label}"
                        # Suppress self-referential arrows and arrows
                        # to collapsed members of the same compound
                        # (e.g. Database → Database::db_).  These are
                        # internal tracking edges, not meaningful
                        # external dependencies.
                        if (alias == target_alias
                                or target_alias.startswith(alias + "__")):
                            continue
                        # Deduplicate: same (source, target, label) tuple
                        # is only emitted once per compound.
                        if line not in self._rel_set:
                            self._rel_set.add(line)
                            self._rel_lines.append(line)

        # Emit non-member, non-namespace children as hoisted siblings.
        # PlantUML cannot render class-in-class (V1.2026.6 crashes on
        # ``class { class { } }``), so composed compounds/enums are
        # emitted at top level and linked with a ``*--`` composition
        # arrow instead of being nested inside the parent body.
        for child_type, type_children in entry.children.items():
            if child_type not in _MEMBER_TYPES and child_type != "NamespaceNode":
                if child_type not in ("MethodNode", "AttributeNode"):
                    for child_entry in type_children.values():
                        if child_type == "EnumValueNode":
                            lines.append(self._format_enum_value_line(child_entry))
                        else:
                            self._hoisted_compounds.append((alias, child_entry))

        lines.append(f"{prefix}}}")
        self._seen.add(alias)
        return lines

    def _emit_enum(self, entry: CompositeEntry, alias: str,
                   indent: int = 0) -> list[str]:
        """Emit an enum with its values."""
        node = entry.node
        prefix = "  " * indent
        display_name = _escape_quoted_label(_short_display_name(node))

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
        # Use the full file name (e.g. "DBBaseTransferObject.hpp") —
        # _short_display_name would strip "hpp" as a namespace segment
        # since dot-splitting can't distinguish extensions from
        # Python-style qualified names.
        display_name = _escape_quoted_label(node.name)

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

    def _is_nested_child(self, source_entry: CompositeEntry,
                         target_key: str) -> bool:
        """True when *target_key* resolves to a direct child of
        *source_entry* (composition already represented by nesting).

        COMPOSES references are skipped by the exporter because nesting
        normally represents them; this check lets flat-reference graphs
        (markdown imports) fall through to an arrow instead.
        """
        display = self.graph.resolve_target_name(
            target_key, flat=self._flat_index()
        )
        if not display:
            return False
        for type_children in source_entry.children.values():
            for child_entry in type_children.values():
                child_name = (
                    getattr(child_entry.node, "qualified_name", None)
                    or child_entry.node.name
                )
                if child_name == display:
                    return True
        return False

    def _emit_reference(self, source_entry: CompositeEntry, rel_type: str,
                       target_key: str, target_type: str = "") -> None:
        """Queue a relationship arrow for later emission.

        Args:
            source_entry: The entry owning the relationship.
            rel_type: The relationship type (e.g. ``"DEPENDS_ON"``).
            target_key: The target node key (qualified name or name).
            target_type: The target node type name (e.g. ``"MethodNode"``).
                When *target_type* is a member type (MethodNode,
                AttributeNode, EnumValueNode), the arrow is redirected
                to the parent compound's alias since members are
                rendered inline and are never standalone elements.
        """
        if rel_type in _STRUCTURAL_REL_TYPES:
            # COMPOSES is normally represented by nesting (children) and
            # gets no arrow.  But some graphs store COMPOSES as a flat
            # reference (e.g. markdown-imported scaffold designs, where
            # composed classes stay top-level entries).  Rendering the
            # ``*--`` composition arrow keeps those relationships visible
            # instead of silently dropping them.
            if rel_type == "COMPOSES" and not self._is_nested_child(
                source_entry, target_key
            ):
                pass
            else:
                return

        # Skip references to node types hidden in the current view mode.
        # FileNode targets are hidden in COLLAPSED and PUBLIC_API;
        # ConceptNode targets are hidden only in PUBLIC_API.
        if target_type == "FileNode" and not self._show_files():
            return
        if target_type == "ConceptNode" and not self._show_concepts():
            return
        if target_type == "ParameterNode":
            # Parameters are function-signature detail (rendered inside
            # the member line), never standalone PlantUML elements.
            return
        # Design/test scaffolding targets are hidden from
        # PUBLIC_API/DESIGN_API by TYPE (the agent may tag them ``design``)
        # — keep the legacy tag-based check as well for older data.
        if target_type in _SCAFFOLDING_TYPES and not self._show_tests():
            return
        if self._target_has_tag(target_key, "test") and not self._show_tests():
            return

        source_node = source_entry.node
        source_qname = getattr(source_node, "qualified_name", None) or source_node.name
        source_alias = self._aliases.get(source_qname) or _sanitize_alias(source_qname)

        # Check if the target falls under a collapsed namespace
        collapsed = self._collapsed_alias_for(target_key)
        if collapsed:
            # In PUBLIC_API mode, external dependency edges are
            # dropped entirely — the view shows only the project's
            # internal relationships.
            if self.view == GraphView.PUBLIC_API:
                return
            target_alias = collapsed
        else:
            display_key = self.graph.resolve_target_name(
                target_key, flat=self._flat_index()
            )
            target_alias = _sanitize_alias(display_key)
            # If the target is a member type (MethodNode, AttributeNode,
            # EnumValueNode), redirect the arrow to the parent compound's
            # alias.  Members are rendered inline inside their parent
            # class body and are never standalone PlantUML elements.
            if target_type in _MEMBER_TYPES:
                parent_alias = self._member_parent_aliases.get(target_key)
                if parent_alias:
                    target_alias = parent_alias

        arrow = _REL_TYPE_TO_ARROW.get(rel_type, "..>")
        label = rel_type.lower()
        line = f"{source_alias} {arrow} {target_alias} : {label}"

        # Suppress self-referential edges and edges to own members
        if (source_alias == target_alias
                or target_alias.startswith(source_alias + "__")):
            return
        if line not in self._rel_set:
            self._rel_set.add(line)
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
    relationships.  Source provenance is assigned from the ``source``
    argument so imported nodes get deterministic uids (required —
    random auto-generated uids are impossible).

    Diagnostics are collected during parsing and available on the
    ``diagnostics`` attribute after :meth:`import_plantuml` returns.
    Set ``strict=True`` to raise :class:`PlantUMLParseError` on any
    error-level diagnostics.

    Args:
        tags: Tags to apply to every imported node.
            Defaults to ``frozenset({"design"})``.
        source: Source provenance label for every imported node
            (required for deterministic uid computation).  Defaults to
            ``"plantuml-import"`` — mirroring the Markdown importer's
            ``"markdown-import"`` default.
        strict: If ``True``, raise :class:`PlantUMLParseError` when
            any error-level diagnostic is recorded.  Defaults to
            ``False`` (collect diagnostics but still return the graph).
    """

    def __init__(self, tags: frozenset[str] | None = None,
                 source: str = "plantuml-import",
                 strict: bool = False):
        self._tags = list(tags) if tags else ["design"]
        self._source = source
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

        # WP A: assign canonical keys to every imported node under the
        # ACTIVE identity scope (parent-relative children use their
        # parent's key).  Mirrors the markdown importer.
        self._assign_canonical_keys(root_entries)

        return LayerGraph(tags=frozenset(self._tags), entries=root_entries)

    def _assign_canonical_keys(self, root_entries: dict) -> None:
        """WP A: compute canonical keys for every node in the tree.

        Uses the active identity scope; when none is available the
        nodes are left unkeyed (saving such a graph raises
        ``IdentityError`` — canonical identity is mandatory).
        """
        from codegraph.identity import get_identity_scope, resolve_identity_for

        scope = get_identity_scope()
        if scope is None:
            return

        def walk(entries, parent_key=None):
            for entry in entries:
                node = entry.node
                t = type(node).__name__
                parents = {}
                if t == "LLR":
                    parents["parent_hlr_key"] = parent_key or "cg:v1:root"
                elif t in (
                    "TestNode", "TestFixtureNode",
                    "AssertionNode", "TestStepNode",
                ):
                    parents["parent_key"] = parent_key or "cg:v1:root"
                elif t in ("ParameterNode", "ImplementationNode"):
                    parents["parent_callable_key"] = parent_key or "cg:v1:root"
                elif t == "SourceFragmentNode":
                    parents["file_key"] = parent_key or "cg:v1:root"
                node.canonical_key = resolve_identity_for(
                    node, scope, parents=parents
                ).key()
                children = [
                    e
                    for type_children in entry.children.values()
                    for e in type_children.values()
                ]
                walk(children, node.canonical_key)

        walk(list(root_entries.values()))

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
            "source": self._source,
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
            "source": self._source,
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


def export_plantuml(graph: LayerGraph, fields: str = "llm",
                    view: GraphView = GraphView.FULL,
                    scope_class: str | None = None) -> str:
    """Export a :class:`LayerGraph` to PlantUML class-diagram syntax.

    Args:
        graph: The :class:`LayerGraph` to export.
        fields: Which property fields to include for each node.
            ``"llm"`` (default) — only ``_llm_fields``.
            ``"all"`` — every defined property.
        view: The visualisation view mode (default :attr:`GraphView.FULL`).
            * ``FULL`` — all nodes, all members, all dependency edges.
            * ``COLLAPSED`` — full source code but external deps
              collapsed into packages; file nodes / file edges omitted.
            * ``PUBLIC_API`` — like COLLAPSED but also hides private
              members, test scaffolding, concept nodes, and file nodes.
              Shows only the public-facing API surface.
        scope_class: When set (fully-qualified class name), emit only
            that class and its 1-hop neighbours.

    Returns:
        A complete PlantUML class-diagram string.
    """
    return PlantUMLExporter(
        graph, fields, view=view, scope_class=scope_class,
    ).export()


def import_plantuml(text: str, tags: frozenset[str] | None = None,
                    source: str = "plantuml-import",
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
        source: Source provenance label for every imported node
            (required for deterministic uid computation).  Defaults to
            ``"plantuml-import"``.  Pass the original graph's source
            (e.g. ``"calculator"``) to make round-trip uids match the
            source graph's uids.
        strict: If ``True``, raise :class:`PlantUMLParseError` when
            any error-level diagnostic is recorded.

    Returns:
        A :class:`LayerGraph` containing the parsed nodes and
        relationships.

    Raises:
        PlantUMLParseError: In strict mode, when structural errors are
            found in the PlantUML input.
    """
    return PlantUMLImporter(tags=tags, source=source, strict=strict).import_plantuml(text)


# ── SVG rendering / validation ─────────────────────────────────────────────


#: Text markers that appear in the SVG page PlantUML emits when a diagram
#: has a syntax error or the Graphviz layout engine crashes.  A
#: ``plantuml -tsvg`` run can return exit code 0 in both cases — it renders
#: an *error page* instead of failing — so exit codes alone never catch a
#: broken diagram.
_PLANTUML_ERROR_MARKERS = (
    "Syntax Error",
    "Error line",
    "Assumed diagram type",
    "An error has occurred",
    "has crashed",
    "UnparsableGraphvizException",
)


def validate_plantuml_svg(svg_text: str) -> list[str]:
    """Sanity-check a PlantUML-generated SVG: well-formed XML, and a
    real diagram rather than a PlantUML error page.

    Naive checks — the file exists, contains ``<svg>``, or is over a
    size threshold — all pass on an error page, so a broken diagram
    (e.g. an alias leaking ``{}`` that PlantUML mis-parses) can ship
    silently.  This validator rejects error pages three ways:

      1. The text must parse as well-formed XML.
      2. It must not contain PlantUML error markers (syntax errors and
         Graphviz/layout crash pages).
      3. It must not render as a nearly-empty canvas (error pages
         for small diagrams are tiny; real diagrams draw boxes,
         arrows and labels and are never that small).

    Note: the ``<?plantuml-src ...?>`` processing instruction is NOT
    a reliable error signal — PlantUML embeds the compressed source
    in every SVG (it powers click-to-view-source), valid diagrams
    included.

    Args:
        svg_text: Contents of a ``.svg`` file produced by PlantUML.

    Returns:
        A list of problems; an empty list means the SVG is valid.
        Callers decide how to act (``assert not problems`` in tests,
        raise in render pipelines, etc.).
    """
    import xml.etree.ElementTree as ET

    problems: list[str] = []
    try:
        ET.fromstring(svg_text)
    except ET.ParseError as e:
        problems.append(f"SVG is not well-formed XML: {e}")

    for marker in _PLANTUML_ERROR_MARKERS:
        if marker in svg_text:
            problems.append(
                f"SVG is a PlantUML error page (contains {marker!r})"
            )

    if not problems and len(svg_text.strip()) < 1000:
        problems.append(
            "SVG is suspiciously small for a rendered diagram "
            f"({len(svg_text.strip())} bytes)"
        )

    return problems


def render_plantuml_to_svg(puml_path, output_dir=None,
                           plantuml_bin: str = "plantuml",
                           timeout: int = 120,
                           env=None) -> Path:
    """Render a PlantUML file to SVG with the ``plantuml`` CLI and
    validate the result.

    PlantUML returns exit code 0 even on syntax errors (it emits an
    error-page SVG instead of failing), so a successful subprocess run
    is NOT proof the diagram rendered.  This helper runs the CLI and
    then validates the produced SVG with :func:`validate_plantuml_svg`,
    raising if the output is an error page — rendering bugs surface
    here instead of shipping a broken artifact.

    Args:
        puml_path: Path to the ``.puml`` file.
        output_dir: Directory for the rendered SVG (default: the
            ``.puml`` file's directory).
        plantuml_bin: PlantUML CLI executable (default ``plantuml``).
        timeout: Seconds to allow the render.
        env: Optional environment dict passed to the subprocess.

    Returns:
        Path to the rendered ``.svg``.

    Raises:
        FileNotFoundError: If the plantuml CLI is not on PATH, or the
            CLI produced no SVG.
        ValueError: If the SVG is a PlantUML error page / invalid.
    """
    import shutil
    import subprocess
    from pathlib import Path

    puml_path = Path(puml_path)
    exe = shutil.which(plantuml_bin)
    if exe is None:
        raise FileNotFoundError(
            f"plantuml CLI not found on PATH ({plantuml_bin!r})"
        )

    cmd = [exe, "-tsvg"]
    if output_dir is not None:
        cmd += ["-o", str(output_dir)]
    cmd.append(str(puml_path))
    # check=False is deliberate: PlantUML returns rc=0 even for syntax
    # errors — the SVG validation below is the real gate.
    subprocess.run(cmd, timeout=timeout, env=env, check=False)

    svg_path = Path(output_dir or puml_path.parent) / (puml_path.stem + ".svg")
    if not svg_path.exists():
        raise FileNotFoundError(f"SVG not generated at {svg_path}")

    problems = validate_plantuml_svg(svg_path.read_text(encoding="utf-8"))
    if problems:
        raise ValueError(
            f"Invalid PlantUML SVG at {svg_path}:\n  "
            + "\n  ".join(problems)
        )
    return svg_path
