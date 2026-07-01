"""Component-level requirements decomposition and PlantUML visualization.

Provides a higher-level view of a codebase than the class-by-class
:class:`~.plantuml.PlantUMLExporter`.  Identifies major business components
(typically top-level namespaces or subsystem modules) and their business-level
requirements, then renders them as a PlantUML component diagram with
requirement annotations.

Integrates with the existing exporter family:

- :func:`export_component_plantuml` — standalone high-level component
  diagram with requirement notes.
- :func:`enrich_plantuml` — takes an existing PlantUML class diagram and
  wraps it with component-boundary annotations and requirement notes,
  reusing the existing :class:`~.plantuml.PlantUMLExporter` output.

Usage
-----

    from codegraph.export.component_decomposition import (
        ComponentDecomposition, export_component_plantuml, enrich_plantuml,
    )
    from codegraph.export.plantuml import export_plantuml

    # Build a LayerGraph from a Neo4j query (as the tools do)
    graph = repo.get_by_tag("as-built")

    # Standalone component diagram
    puml = export_component_plantuml(graph)
    print(puml)

    # Or: enrich an existing class diagram
    class_puml = export_plantuml(graph)
    enriched = enrich_plantuml(class_puml, graph)
    print(enriched)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from codegraph.graph import LayerGraph, CompositeEntry


# ── Data classes ──────────────────────────────────────────────────────────


@dataclass
class RequirementInfo:
    """A single business-level requirement for a component.

    Attributes:
        id: Short identifier (e.g. ``"REQ-01"``).
        description: Human-readable requirement description.
        rationale: Why this requirement exists (derived from code structure).
        evidence: Code-node name snippets that demonstrate this requirement.
    """

    id: str
    description: str
    rationale: str = ""
    evidence: list[str] = field(default_factory=list)


@dataclass
class ComponentInfo:
    """A high-level business component identified in the codebase.

    Attributes:
        name: Human-readable component name (short form).
        qualified_name: Fully qualified name in the codegraph.
        description: What this component does at the business level.
        requirements: Business requirements this component fulfills.
        key_classes: Most important class/entity names in this component.
        dependencies: Other component qualified names this one depends on.
    """

    name: str
    qualified_name: str
    description: str = ""
    requirements: list[RequirementInfo] = field(default_factory=list)
    key_classes: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)


# ── Component decomposition ────────────────────────────────────────────────


#: Node types treated as compound business entities.
_COMPOUND_TYPES: set[str] = {
    "ClassNode",
    "InterfaceNode",
    "EnumNode",
    "UnionNode",
    "ConceptNode",
    "FunctionNode",
}

#: Node types treated as namespace/package containers.
_NAMESPACE_TYPES: set[str] = {
    "NamespaceNode",
    "ModuleNode",
}


class ComponentDecomposition:
    """Decompose a :class:`LayerGraph` into high-level business components.

    Components are identified from top-level namespaces and standalone
    compound nodes.  Requirements are derived from class/method descriptions,
    structural relationships, and naming patterns.

    Args:
        graph: The :class:`LayerGraph` to decompose.
        min_component_size: Minimum number of child entities a namespace
            must contain to be promoted to a component (avoids trivial
            single-entity components).  Defaults to 2.
    """

    def __init__(self, graph: LayerGraph, min_component_size: int = 2) -> None:
        self.graph = graph
        self.min_component_size = max(min_component_size, 1)
        self._components: dict[str, ComponentInfo] = {}

    # ── Public API ─────────────────────────────────────────────────────

    def decompose(self) -> dict[str, ComponentInfo]:
        """Run the full decomposition pipeline.

        Returns:
            Dict mapping component qualified name → :class:`ComponentInfo`.
        """
        self._components.clear()

        self._identify_namespace_components()
        self._identify_standalone_components()
        self._derive_all_requirements()
        self._map_all_dependencies()

        return self._components

    def component_entries(self) -> list[ComponentInfo]:
        """Return components sorted by importance.

        Importance is a heuristic based on entity count and requirement
        count — larger components with more responsibilities appear first.
        """
        if not self._components:
            self.decompose()
        return sorted(
            self._components.values(),
            key=lambda c: len(c.key_classes) + len(c.requirements),
            reverse=True,
        )

    # ── Identification ──────────────────────────────────────────────────

    def _identify_namespace_components(self) -> None:
        """Promote namespaces/mods to components — roots + deeply nested."""
        visited: set[str] = set()
        stack: list[CompositeEntry] = list(
            self.graph.entries.values()
        )
        while stack:
            entry = stack.pop()
            qname = entry.node.qualified_name
            if qname in visited:
                continue
            visited.add(qname)

            node_type = type(entry.node).__name__
            if node_type in _NAMESPACE_TYPES:
                entity_count = self._entity_count(entry)
                if entity_count >= self.min_component_size:
                    self._components[qname] = ComponentInfo(
                        name=entry.node.name,
                        qualified_name=qname,
                        description=self._derive_description(entry),
                        key_classes=self._collect_key_classes(entry),
                    )

            # Recurse into nested namespace/module children
            for ns_type in _NAMESPACE_TYPES:
                if ns_type in entry.children:
                    stack.extend(entry.children[ns_type].values())

    def _identify_standalone_components(self) -> None:
        """Treat standalone compound nodes as singletons."""
        for qname, entry in self.graph.entries.items():
            node_type = type(entry.node).__name__
            if node_type in _COMPOUND_TYPES and qname not in self._components:
                self._components[qname] = ComponentInfo(
                    name=entry.node.name,
                    qualified_name=qname,
                    description=self._derive_description(entry),
                    key_classes=[qname],
                )

    # ── Requirement derivation ──────────────────────────────────────────

    def _derive_all_requirements(self) -> None:
        for comp in self._components.values():
            self._derive_requirements(comp)

    def _derive_requirements(self, comp: ComponentInfo) -> None:
        entry = self._find_entry(comp.qualified_name)
        if entry is None:
            return

        node = entry.node
        node_type = type(node).__name__
        next_id = 1

        # P1 — Domain entities
        has_compounds = any(ct in entry.children for ct in _COMPOUND_TYPES)
        if has_compounds:
            comp.requirements.append(
                RequirementInfo(
                    id=f"REQ-{next_id:02d}",
                    description=f"Manage {comp.name} domain entities and lifecycle",
                    rationale="Defines domain model classes/interfaces",
                    evidence=self._find_evidence(entry, _COMPOUND_TYPES),
                )
            )
            next_id += 1

        # P2 — Persistence / storage
        storage_patterns = ("store", "repo", "db", "persist", "connect", "driver")
        has_storage = self._has_pattern(entry, storage_patterns)
        if has_storage:
            comp.requirements.append(
                RequirementInfo(
                    id=f"REQ-{next_id:02d}",
                    description=f"Persist and retrieve {comp.name} data",
                    rationale="Contains storage/repository/driver layer",
                    evidence=self._find_pattern_evidence(entry, storage_patterns),
                )
            )
            next_id += 1

        # P3 — Public API / interface
        if "InterfaceNode" in entry.children:
            comp.requirements.append(
                RequirementInfo(
                    id=f"REQ-{next_id:02d}",
                    description=f"Expose {comp.name} as a stable public API",
                    rationale="Defines interfaces for external consumers",
                    evidence=self._find_evidence(entry, {"InterfaceNode"}),
                )
            )
            next_id += 1

        # P4 — Export / serialization / I/O
        io_patterns = ("export", "import", "serial", "format",
                       "render", "write", "parse", "load", "dump")
        has_io = self._has_pattern(entry, io_patterns)
        if has_io:
            comp.requirements.append(
                RequirementInfo(
                    id=f"REQ-{next_id:02d}",
                    description=f"Support {comp.name} data import/export and I/O",
                    rationale="Contains serialization/IO logic",
                    evidence=self._find_pattern_evidence(entry, io_patterns),
                )
            )
            next_id += 1

        # P5 — Query / lookup
        query_patterns = ("query", "lookup", "search", "find", "fetch", "get_by",
                          "discovery", "explore")
        has_query = self._has_pattern(entry, query_patterns)
        if has_query:
            comp.requirements.append(
                RequirementInfo(
                    id=f"REQ-{next_id:02d}",
                    description=f"Provide query and discovery for {comp.name}",
                    rationale="Contains query/lookup/search logic",
                    evidence=self._find_pattern_evidence(entry, query_patterns),
                )
            )
            next_id += 1

        # P6 — Tools / agent interface
        agent_patterns = ("tool", "agent", "dispatch", "dispatch_tool",
                          "tool_input", "handler")
        has_agent = self._has_pattern(entry, agent_patterns)
        if has_agent:
            comp.requirements.append(
                RequirementInfo(
                    id=f"REQ-{next_id:02d}",
                    description=f"Expose {comp.name} as agent-accessible tools",
                    rationale="Contains agent-tool dispatch infrastructure",
                    evidence=self._find_pattern_evidence(entry, agent_patterns),
                )
            )
            next_id += 1

        # Fallback — structural existence
        if not comp.requirements:
            comp.requirements.append(
                RequirementInfo(
                    id="REQ-01",
                    description=f"Provide {comp.name} core functionality",
                    rationale="Component identified from codebase structure",
                    evidence=[comp.name],
                )
            )

    # ── Dependency mapping ──────────────────────────────────────────────

    def _map_all_dependencies(self) -> None:
        for comp_qname, comp in self._components.items():
            entry = self._find_entry(comp_qname)
            if entry is None:
                continue

            deps: set[str] = set()
            for _rel_type, target_key, _target_type in entry.references:
                # Also check children's references
                pass  # handled in the loop below

            # Collect all references (entry + children)
            all_refs: list[tuple[str, str]] = [
                (r[0], r[1]) for r in entry.references
            ]
            for child_type, type_children in entry.children.items():
                for child_entry in type_children.values():
                    all_refs.extend(
                        (r[0], r[1]) for r in child_entry.references
                    )

            for _rel_type, target_key in all_refs:
                target_name = self.graph.resolve_target_name(target_key)
                # Match target to a known component
                for other_qname in self._components:
                    if other_qname == comp_qname:
                        continue
                    if (target_name.startswith(other_qname + "::")
                            or target_name == other_qname):
                        deps.add(other_qname)

            comp.dependencies = sorted(deps)

    # ── Helpers ─────────────────────────────────────────────────────────

    def _find_entry(self, qualified_name: str) -> CompositeEntry | None:
        """Find a CompositeEntry by its node's qualified_name.

        Searches roots and recursively into children, since
        :attr:`LayerGraph.entries` is keyed by UID not qualified name.
        """
        stack: list[CompositeEntry] = list(
            self.graph.entries.values()
        )
        while stack:
            entry = stack.pop()
            if entry.node.qualified_name == qualified_name:
                return entry
            for type_children in entry.children.values():
                stack.extend(type_children.values())
        return None

    @staticmethod
    def _entity_count(entry: CompositeEntry) -> int:
        """Count non-member entities within an entry's children."""
        return sum(
            len(type_children)
            for child_type, type_children in entry.children.items()
            if child_type not in {"MethodNode", "AttributeNode",
                                  "EnumValueNode"}
        )

    @staticmethod
    def _derive_description(entry: CompositeEntry) -> str:
        node = entry.node
        desc = getattr(node, "description", "") or ""
        if desc:
            return desc

        parts: list[str] = []
        node_type = type(node).__name__

        # Count and characterise children
        compound_count = sum(
            len(tc) for ct, tc in entry.children.items()
            if ct in _COMPOUND_TYPES
        )
        if compound_count:
            parts.append(f"{compound_count} entities")

        ns_count = sum(
            len(tc) for ct, tc in entry.children.items()
            if ct in _NAMESPACE_TYPES
        )
        if ns_count:
            parts.append(f"{ns_count} sub-packages")

        if entry.references:
            parts.append(f"{len(entry.references)} dependencies")

        return "; ".join(parts) if parts else node.name

    @staticmethod
    def _collect_key_classes(entry: CompositeEntry) -> list[str]:
        """Collect key class/interface/enum qualified names within an entry."""
        key_classes: list[str] = []
        for child_type in _COMPOUND_TYPES:
            if child_type in entry.children:
                key_classes.extend(
                    child.node.qualified_name
                    for child in entry.children[child_type].values()
                )

        # Recurse into nested namespaces
        for ns_type in _NAMESPACE_TYPES:
            if ns_type in entry.children:
                for child_entry in entry.children[ns_type].values():
                    key_classes.extend(
                        ComponentDecomposition._collect_key_classes(child_entry)
                    )

        return sorted(key_classes)

    @staticmethod
    def _find_evidence(entry: CompositeEntry,
                       types: set[str]) -> list[str]:
        evidence: list[str] = []
        for child_type in types:
            for child_entry in entry.children.get(child_type, {}).values():
                evidence.append(child_entry.node.name)
        return evidence[:5]

    @staticmethod
    def _find_pattern_evidence(entry: CompositeEntry,
                               patterns: tuple[str, ...]) -> list[str]:
        evidence: list[str] = []
        for _child_type, type_children in entry.children.items():
            for child_entry in type_children.values():
                qn = child_entry.node.qualified_name.lower()
                if any(p in qn for p in patterns):
                    evidence.append(child_entry.node.name)
        return evidence[:5]

    @staticmethod
    def _has_pattern(entry: CompositeEntry,
                     patterns: tuple[str, ...]) -> bool:
        """Check whether entry or any child qualified name matches a pattern."""
        for _child_type, type_children in entry.children.items():
            for child_entry in type_children.values():
                if any(p in child_entry.node.qualified_name.lower() for p in patterns):
                    return True
        return False


# ── PlantUML export ───────────────────────────────────────────────────────


def export_component_plantuml(
    graph: LayerGraph,
    decomposition: ComponentDecomposition | None = None,
    min_component_size: int = 2,
    detail_level: str = "high",
) -> str:
    """Generate a PlantUML **component diagram** with requirement annotations.

    Unlike :func:`~codegraph.export.plantuml.export_plantuml` which
    produces a detailed class-by-class diagram, this function produces
    a high-level component view showing:

    - Major business components as PlantUML ``package`` elements.
    - Business-level requirements as ``note`` annotations on each component.
    - Inter-component dependencies as ``-->`` arrows.

    Args:
        graph: The :class:`LayerGraph` to visualize.
        decomposition: Pre-computed decomposition (optional; computed if
            ``None``).
        min_component_size: Minimum entities for a namespace to be a
            component.  Ignored when *decomposition* is supplied.
        detail_level: ``"high"`` (components + notes only) or
            ``"medium"`` (also shows key class names inside packages).

    Returns:
        A complete PlantUML string enclosed in ``@startuml`` / ``@enduml``.
    """
    if decomposition is None:
        decomposition = ComponentDecomposition(graph, min_component_size)
        decomposition.decompose()

    lines: list[str] = []
    lines.append("@startuml")
    lines.append("' ── Component Diagram with Business Requirements ──")
    lines.append("")
    lines.append("skinparam packageStyle rectangle")
    lines.append("skinparam noteBackgroundColor LemonChiffon")
    lines.append("skinparam defaultFontSize 12")
    lines.append("")

    components = decomposition.component_entries()

    # Emit components
    for comp in components:
        alias = _sanitize_plantuml_alias(comp.qualified_name)

        lines.append(f'package "{comp.name}" as {alias} {{')

        if detail_level == "medium":
            if comp.key_classes:
                for cls_qname in comp.key_classes[:10]:
                    short = cls_qname.split("::")[-1]
                    lines.append(f'  class "{short}"')
            else:
                lines.append("  note as N_EMPTY : No major entities")
        elif detail_level == "high" and not comp.key_classes:
            lines.append(f"  ' {comp.description or comp.name}")

        lines.append("}")
        lines.append("")

    # Emit requirement notes
    for comp in components:
        alias = _sanitize_plantuml_alias(comp.qualified_name)
        if comp.requirements:
            lines.append(f"note right of {alias}")
            lines.append(f"  <b>{comp.name} — Requirements</b>")
            max_show = 8
            for req in comp.requirements[:max_show]:
                desc = req.description
                if len(desc) > 90:
                    desc = desc[:87] + "..."
                lines.append(f"  • [{req.id}] {desc}")
            if len(comp.requirements) > max_show:
                lines.append(
                    f"  • ... and {len(comp.requirements) - max_show} more"
                )
            lines.append("end note")
            lines.append("")

    # Emit inter-component dependencies
    if len(components) > 1:
        lines.append("' ── Inter-Component Dependencies ──")
        lines.append("")
        emitted: set[tuple[str, str]] = set()
        for comp in components:
            src_alias = _sanitize_plantuml_alias(comp.qualified_name)
            for dep_qname in comp.dependencies:
                key = (src_alias, dep_qname)
                if key in emitted:
                    continue
                emitted.add(key)
                dst_alias = _sanitize_plantuml_alias(dep_qname)
                lines.append(f"{src_alias} --> {dst_alias} : depends on")
        lines.append("")

    lines.append("@enduml")
    return "\n".join(lines)


def enrich_plantuml(
    class_puml: str,
    graph: LayerGraph,
    decomposition: ComponentDecomposition | None = None,
    min_component_size: int = 2,
    note_position: str = "top",
) -> str:
    """Enrich an existing PlantUML **class diagram** with component boundaries
    and requirement notes.

    This function takes the output of
    :func:`~codegraph.export.plantuml.export_plantuml`, inserts component
    grouping comments, and adds requirement-note annotations pointing at the
    relevant packages.

    The result is a single PlantUML diagram that combines:

    - The original class-level detail from the existing exporter.
    - High-level component-boundary section headers.
    - Business-requirement notes attached to each component's package.

    Args:
        class_puml: PlantUML output from
            :func:`~codegraph.export.plantuml.export_plantuml`.
        graph: The same :class:`LayerGraph` used to generate *class_puml*.
        decomposition: Optional pre-computed decomposition.
        min_component_size: Minimum entity threshold for components.
        note_position: PlantUML note position — ``"top"``, ``"left"``,
            ``"right"``, or ``"bottom"``.  Defaults to ``"top"``.

    Returns:
        Enriched PlantUML string with ``@startuml`` / ``@enduml`` wrappers.
    """
    if decomposition is None:
        decomposition = ComponentDecomposition(graph, min_component_size)
        decomposition.decompose()

    components = decomposition.component_entries()
    if not components:
        return class_puml

    # Build a mapping: package alias → component info
    alias_map: dict[str, ComponentInfo] = {
        _sanitize_plantuml_alias(c.qualified_name): c
        for c in components
    }

    # Parse the class diagram to find package boundaries and insert notes
    enriched_lines: list[str] = []
    after_skinparam = False
    in_header = True

    for line in class_puml.split("\n"):
        # Track header boundary
        if in_header and not line.startswith("@") and not line.startswith("skinparam"):
            if line.strip():
                in_header = False
                after_skinparam = True

        # Insert component preamble after end of header
        if after_skinparam and not in_header:
            after_skinparam = False
            enriched_lines.append("")
            enriched_lines.append("' ── Component Annotations (auto-generated) ──")
            enriched_lines.append("")

            # Emit component notes
            for comp in components:
                alias = _sanitize_plantuml_alias(comp.qualified_name)
                note_id = f"N_{alias}"

                enriched_lines.append(f"note as {note_id}")
                enriched_lines.append(f"  <b>{comp.name}</b>")
                if comp.description:
                    enriched_lines.append(f"  {comp.description}")
                if comp.requirements:
                    enriched_lines.append("  ----")
                    enriched_lines.append("  <i>Requirements:</i>")
                    for req in comp.requirements[:5]:
                        desc = req.description
                        if len(desc) > 80:
                            desc = desc[:77] + "..."
                        enriched_lines.append(f"  • [{req.id}] {desc}")
                    if len(comp.requirements) > 5:
                        enriched_lines.append(
                            f"  • ... {len(comp.requirements) - 5} more"
                        )
                enriched_lines.append("end note")
                enriched_lines.append(f"{note_id} .. {alias}")
                enriched_lines.append("")

        enriched_lines.append(line)

    return "\n".join(enriched_lines)


# ── Helpers ───────────────────────────────────────────────────────────────


def _sanitize_plantuml_alias(name: str) -> str:
    """Convert a qualified name to a valid PlantUML alias.

    Same convention as the PlantUML exporter —
    replaces ``::`` with ``__`` and dots/spaces with ``_``.
    """
    return name.replace("::", "__").replace(" ", "_").replace(".", "_")
