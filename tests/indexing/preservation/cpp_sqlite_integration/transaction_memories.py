"""WP5.3 — the three Transaction slice memories.

Plan: ``docs/plans/2026-09-16-priority-5-transaction-golden-slice.md``.

The memories are the reviewed design rationale for the frozen Transaction
implementation surface.  They are *data*: this module reads them from
``fixtures/cpp-sqlite/transaction_slice/memories.toml``
(:func:`load_memory_definitions`), materializes them as the existing memory
node types under the slice's canonical identity scope
(:func:`materialize_memories`), and adds them to the slice's own
``LayerGraph`` (:func:`slice_graph_with_memories`).

Deliberate boundaries:

* No memory format is invented on the *graph* side.  The memories become
  ordinary entries of the same ``LayerGraph`` the code slice uses, so the
  flat portable document (WP5.2) carries them with no second snapshot
  format, and the WP5.2 fixpoint/edge-classification guarantees apply to
  them unchanged.
* Canonical keys are computed by the identity framework
  (:meth:`CodeGraphNode.resolve_canonical_key`) under the slice scope; nothing
  here authors a key, and a key that does not recompute from the node's own
  fields raises.
* Every ``links`` entry must resolve to a node of the indexed slice.  An
  unresolvable name raises :class:`MemoryFixtureError` instead of dropping the
  edge, so an authored typo can never look like a graph with fewer memories.
* ``MemoryGraph``'s own ``serialize()``/``deserialize()`` format is *not* used
  here: it carries one scalar ``linked_code_*`` target per memory and has no
  representation for a memory-to-memory edge, which is exactly the loss WP5.3
  step 6 forbids.  The general ``MemoryGraph`` code path is deliberately left
  untouched by this package.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Mapping, Sequence

from codegraph.graph import CompositeEntry, LayerGraph
from codegraph.identity import IdentityScope
from codegraph.identity.encoding import encode_segment
from codegraph_memory.models.base import MemoryNode
from codegraph_memory.models.constraint import ConstraintNode
from codegraph_memory.models.decision import DecisionNode
from codegraph_memory.models.rationale import RationaleNode

_HERE = Path(__file__).resolve().parent

#: The repository-reviewed memory input (WP5.3 step 1).
MEMORY_INPUT = (
    _HERE.parent / "fixtures" / "cpp-sqlite" / "transaction_slice"
    / "memories.toml"
)

#: The identity the as-built cpp-sqlite graph and the authored requirements
#: use; the memories must land in the same scope to share the graph.
SLICE_SCOPE = IdentityScope.repository("cpp-sqlite", "cpp-sqlite")

#: The canonical-key prefix of that scope, built by the identity encoder (the
#: memory keys are asserted to live inside it rather than trusting the input).
SLICE_KEY_PREFIX = (
    f"cg:v1:{encode_segment(SLICE_SCOPE.scope_kind)}:"
    f"{encode_segment(SLICE_SCOPE.scope_id)}:"
)

#: Memory type → (node class, relation type to code).
#:
#: The relation follows from the memory type, so an authored memory cannot
#: disagree with the frozen vocabulary.
MEMORY_KINDS: Mapping[str, tuple[type[MemoryNode], str]] = {
    "decision": (DecisionNode, "MOTIVATES"),
    "constraint": (ConstraintNode, "CONSTRAINS"),
    "rationale": (RationaleNode, "EXPLAINS"),
}

#: Memory-to-memory edges an input entry may declare: field → relation type.
MEMORY_TO_MEMORY_FIELDS: Mapping[str, str] = {
    "refines": "REFINES",
    "supersedes": "SUPERSEDES",
}

#: The three memories of the slice, by type.  A frozen characterization: the
#: plan names exactly these three, so a changed set fails this module.
FROZEN_MEMORY_TYPES: tuple[str, ...] = ("decision", "constraint", "rationale")

#: The fields the reviewed input must carry (WP5.3 step 1).
REQUIRED_FIELDS: tuple[str, ...] = (
    "type", "qualified_name", "content", "confidence", "tags", "source",
    "links",
)


#: Transport leaves carry their owner's qualified name, so they can never be
#: an authored link target and are excluded from the resolution index.
TRANSPORT_TYPE = "ImplementationNode"


class MemoryFixtureError(AssertionError):
    """The authored memory input or its resolution is inconsistent."""


@dataclass(frozen=True)
class MemoryDefinition:
    """One reviewed memory, exactly as authored (no derived fields)."""

    type: str
    qualified_name: str
    content: str
    confidence: float
    tags: tuple[str, ...]
    source: str
    links: tuple[str, ...]
    memory_links: Mapping[str, str]  # field name (e.g. "refines") → target qname


# ---------------------------------------------------------------------------
# Load — reviewed data only
# ---------------------------------------------------------------------------


def load_memory_definitions(
    path: Path = MEMORY_INPUT,
) -> tuple[MemoryDefinition, ...]:
    """Read the authored memories in file order.

    Raises:
        MemoryFixtureError: if the input is missing, malformed, or a
            definition lacks a required field or repeats an identity.
    """
    if not path.is_file():
        raise MemoryFixtureError(f"missing memory input: {path}")
    raw = tomllib.loads(path.read_text(encoding="utf-8"))
    entries = raw.get("memory")
    if not isinstance(entries, list) or not entries:
        raise MemoryFixtureError(f"{path}: expected a non-empty [[memory]] list")

    definitions: list[MemoryDefinition] = []
    seen_qnames: set[str] = set()
    for index, entry in enumerate(entries):
        where = f"{path.name}[{index}]"
        missing = [key for key in REQUIRED_FIELDS if key not in entry]
        if missing:
            raise MemoryFixtureError(f"{where}: missing {', '.join(missing)}")
        memory_type = entry["type"]
        if memory_type not in MEMORY_KINDS:
            raise MemoryFixtureError(
                f"{where}: unknown type {memory_type!r}; expected one of "
                f"{sorted(MEMORY_KINDS)}"
            )
        qualified_name = entry["qualified_name"]
        if qualified_name in seen_qnames:
            raise MemoryFixtureError(f"{where}: duplicate {qualified_name!r}")
        seen_qnames.add(qualified_name)
        if not entry["content"].strip():
            raise MemoryFixtureError(f"{where}: empty content")
        links = tuple(entry["links"])
        if not links:
            raise MemoryFixtureError(f"{where}: no linked code nodes")
        definitions.append(MemoryDefinition(
            type=memory_type,
            qualified_name=qualified_name,
            content=entry["content"],
            confidence=float(entry["confidence"]),
            tags=tuple(entry["tags"]),
            source=entry["source"],
            links=links,
            memory_links={
                field: entry[field]
                for field in MEMORY_TO_MEMORY_FIELDS
                if field in entry
            },
        ))

    types = tuple(definition.type for definition in definitions)
    if sorted(types) != sorted(FROZEN_MEMORY_TYPES):
        raise MemoryFixtureError(
            f"{path.name}: expected the frozen memory types "
            f"{sorted(FROZEN_MEMORY_TYPES)}, got {sorted(types)}"
        )
    return tuple(definitions)


# ---------------------------------------------------------------------------
# Materialize — framework identity, graph endpoints
# ---------------------------------------------------------------------------


def iter_entries(graph: LayerGraph) -> Iterator[CompositeEntry]:
    stack = list(graph.entries.values())
    while stack:
        entry = stack.pop()
        yield entry
        for by_type in entry.children.values():
            stack.extend(by_type.values())


def node_index(graph: LayerGraph) -> dict[str, CompositeEntry]:
    """Map ``qualified_name`` → entry for every node in *graph*.

    Raises:
        MemoryFixtureError: if two entries share a qualified name — the
            authored link would then be undefined, which is a fixture defect
            rather than a resolvable ambiguity.
    """
    index: dict[str, CompositeEntry] = {}
    for entry in iter_entries(graph):
        if type(entry.node).__name__ == TRANSPORT_TYPE:
            # An implementation leaf carries its owner's qualified name; an
            # authored link could never mean it, and letting it into the index
            # would make every owner name ambiguous.
            continue
        qname = getattr(entry.node, "qualified_name", "") or ""
        if not qname:
            continue
        if qname in index:
            raise MemoryFixtureError(
                f"qualified name {qname!r} is ambiguous in the slice graph "
                f"({type(index[qname].node).__name__} and "
                f"{type(entry.node).__name__})"
            )
        index[qname] = entry
    return index


def _materialize_node(definition: MemoryDefinition) -> MemoryNode:
    """Build the memory node and give it its framework-computed key."""
    node_cls, _relation_type = MEMORY_KINDS[definition.type]
    node = node_cls(
        qualified_name=definition.qualified_name,
        content=definition.content,
        confidence=definition.confidence,
        tags=list(definition.tags),
        source=definition.source,
    )
    # ``resolve_canonical_key`` computes on demand and never stores; storing
    # the computed value is what lets the entry key and every edge endpoint use
    # the same canonical identity as the rest of the slice.
    node.canonical_key = node.resolve_canonical_key(scope=SLICE_SCOPE)
    recomputed = node.resolve_canonical_key(scope=SLICE_SCOPE)
    if recomputed != node.canonical_key:
        raise MemoryFixtureError(
            f"{definition.qualified_name}: canonical key "
            f"{node.canonical_key!r} does not recompute from the node's own "
            f"fields ({recomputed!r})"
        )
    if not node.canonical_key.startswith(SLICE_KEY_PREFIX):
        raise MemoryFixtureError(
            f"{definition.qualified_name}: key {node.canonical_key!r} is "
            f"outside the slice scope {SLICE_KEY_PREFIX!r}"
        )
    return node


def materialize_memories(
    definitions: Sequence[MemoryDefinition],
    graph: LayerGraph,
) -> tuple[dict[str, CompositeEntry], tuple[tuple[str, str, str], ...]]:
    """Materialize *definitions* against the code nodes of *graph*.

    Returns:
        ``(entries, memory_edges)``: ``entries`` maps each canonical key to its
        :class:`CompositeEntry` (code references already attached) and
        ``memory_edges`` lists the ``(relation_type, source_key, target_key)``
        memory-to-memory edges.

    Raises:
        MemoryFixtureError: if a linked name does not resolve, if a
            memory-to-memory target is not one of the authored memories, or if
            the materialized identity is not in the slice scope.
    """
    by_qname = node_index(graph)

    entries: dict[str, CompositeEntry] = {}
    keys_by_qname: dict[str, str] = {}
    pending: list[tuple[CompositeEntry, str, str]] = []

    for definition in definitions:
        node = _materialize_node(definition)
        entry = CompositeEntry(node=node)
        code_relation = MEMORY_KINDS[definition.type][1]
        for target_qname in definition.links:
            target = by_qname.get(target_qname)
            if target is None:
                raise MemoryFixtureError(
                    f"{definition.qualified_name}: linked node "
                    f"{target_qname!r} is not in the slice graph"
                )
            entry.references.append(
                (code_relation, target.node.canonical_key,
                 type(target.node).__name__)
            )
        entries[node.canonical_key] = entry
        keys_by_qname[definition.qualified_name] = node.canonical_key
        for field, target_qname in definition.memory_links.items():
            pending.append((entry, field, target_qname))

    memory_edges: list[tuple[str, str, str]] = []
    for entry, field, target_qname in pending:
        target_key = keys_by_qname.get(target_qname)
        if target_key is None:
            raise MemoryFixtureError(
                f"{entry.node.qualified_name}: {field} target {target_qname!r} "
                f"is not one of the authored memories"
            )
        relation_type = MEMORY_TO_MEMORY_FIELDS[field]
        entry.references.append(
            (relation_type, target_key, type(entries[target_key].node).__name__)
        )
        memory_edges.append(
            (relation_type, entry.node.canonical_key, target_key)
        )

    return entries, tuple(memory_edges)


def slice_graph_with_memories(
    graph: LayerGraph,
    definitions: Sequence[MemoryDefinition],
) -> LayerGraph:
    """The slice graph plus the materialized memories.

    The slice graph is not mutated: the memories are merged into a copy through
    :meth:`LayerGraph.merge` — the same combine path used elsewhere — so the
    session-scoped slice graph stays exactly as indexed and the memories become
    ordinary entries of a graph with the same tags and shape.
    """
    entries, _memory_edges = materialize_memories(definitions, graph)
    combined = LayerGraph(
        tags=graph.tags,
        entries=dict(graph.entries),
        known_keys=graph.known_keys,
    )
    combined.merge(LayerGraph(tags=graph.tags, entries=entries))
    return combined
