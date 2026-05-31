"""Typed graph containers for the ontology visualization.

Each container is self-contained: one Cypher query fills all fields.
No secondary queries are needed to resolve members, edges, or nested objects.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from codegraph.nodes import CompoundNode, MemberNode, NamespaceNode


@dataclass
class GraphEdge:
    """A directed relationship between two nodes in a subgraph."""

    source_qualified_name: str
    target_qualified_name: str
    predicate: str  # UPPERCASE Neo4j rel type
    mechanism: str = ""
    position: int | None = None
    name: str = ""
    display_name: str = ""


@dataclass
class CompoundGraph:
    """Self-contained payload for one :Compound node.

    One Cypher query returns the compound, all its members (via COMPOSES),
    nested compounds (via COMPOSES → nested classes), and all non-COMPOSES
    edges in and out.
    """

    node: CompoundNode
    members: list[MemberNode] = field(default_factory=list)
    nested: list[CompoundGraph] = field(default_factory=list)
    edges_out: list[GraphEdge] = field(default_factory=list)
    edges_in: list[GraphEdge] = field(default_factory=list)


@dataclass
class NamespaceGraph:
    """Self-contained payload for one :Namespace node and its contents.

    Recursively descends one level. ``compounds`` includes classes,
    structs, interfaces, and enums owned by this namespace (via
    COMPOSES from Namespace→Compound).
    """

    node: NamespaceNode
    compounds: list[CompoundGraph] = field(default_factory=list)
    namespaces: list[NamespaceGraph] = field(default_factory=list)


@dataclass
class OntologyGraph:
    """Top-level graph for the ontology visualization page.

    Contains all namespaces (with their compounds), unparented compounds
    (no owning namespace), and cross-cutting edges (between namespaces
    or unparented compounds).
    """

    namespaces: list[NamespaceGraph] = field(default_factory=list)
    compounds: list[CompoundGraph] = field(default_factory=list)
    edges: list[GraphEdge] = field(default_factory=list)

    def to_raw(self) -> dict:
        """Flatten the typed hierarchy into the raw dict shape consumed by
        ``format_ontology_graph()``.

        Returns ``{"nodes": [...], "edges": [...]}`` where each node is a
        flat dict of Neo4j properties and each edge has ``source``,
        ``target``, and ``type`` keys.
        """
        nodes: list[dict] = []
        edges: list[dict] = []
        seen_qns: set[str] = set()

        def _add_node(model) -> None:
            d = model.model_dump()
            qn = d.get("qualified_name", "")
            if qn and qn not in seen_qns:
                seen_qns.add(qn)
                nodes.append(d)

        def _add_edge(ge: GraphEdge) -> None:
            edges.append(
                {
                    "source": ge.source_qualified_name,
                    "target": ge.target_qualified_name,
                    "type": ge.predicate,
                    "mechanism": ge.mechanism,
                    "position": ge.position,
                    "name": ge.name,
                    "display_name": ge.display_name,
                }
            )

        def _walk_namespace(nsg: NamespaceGraph) -> None:
            _add_node(nsg.node)
            for cg in nsg.compounds:
                _walk_compound(cg)
            for child_ns in nsg.namespaces:
                _walk_namespace(child_ns)

        def _walk_compound(cg: CompoundGraph) -> None:
            _add_node(cg.node)
            for m in cg.members:
                _add_node(m)
            for nested in cg.nested:
                _walk_compound(nested)
            for ge in cg.edges_out:
                _add_edge(ge)
            for ge in cg.edges_in:
                _add_edge(ge)

        for nsg in self.namespaces:
            _walk_namespace(nsg)
        for cg in self.compounds:
            _walk_compound(cg)
        for ge in self.edges:
            _add_edge(ge)

        return {"nodes": nodes, "edges": edges}
