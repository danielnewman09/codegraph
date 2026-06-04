# GraphRepository Implementation Plan

**Spec:** `docs/specs/2025-06-03-graph-repository-design.md`

## Overview

7 steps, each independently testable. Steps 1–2 add foundations to existing
code. Steps 3–5 build the core `GraphRepository` class. Step 6 optimizes
the builder's edge lookup. Step 7 adds tests.

---

## Step 1: Add `fetch_all_by_source()` to `CodeGraphNode`

**File:** `src/codegraph/models/tags.py`

Add a class method `fetch_all_by_source(source: str) -> list[CodeGraphNode]`
to `CodeGraphNode`, mirroring the existing `fetch_all_by_layer` pattern.

```python
@classmethod
def fetch_all_by_source(cls, source: str) -> list["CodeGraphNode"]:
    """Fetch all nodes across all registered types matching *source*.

    Iterates _registry, calling .nodes.filter(source=source) on each
    type that has a ``source`` property. Returns a flat list.
    """
    result: list[CodeGraphNode] = []
    for node_cls in cls._registry.values():
        if "source" in node_cls.defined_properties():
            result.extend(node_cls.nodes.filter(source=source))
    return result
```

Place after `fetch_all_by_layer`. No `fetch_by_source` instance method — the
logic is simple enough that a single `fetch_all_by_source` is sufficient.

---

## Step 2: Add `fetch_all_by_kind()` to `CodeGraphNode`

**File:** `src/codegraph/models/tags.py`

Add a class method `fetch_all_by_kind(kind: str, layer: str | None = None) -> list[CodeGraphNode]`
to `CodeGraphNode`, after `fetch_all_by_source`.

```python
@classmethod
def fetch_all_by_kind(cls, kind: str, layer: str | None = None) -> list["CodeGraphNode"]:
    """Fetch all nodes across all registered types matching *kind*.

    Optionally filter by *layer* as well. Only types that have a ``kind``
    property are queried. Returns a flat list.
    """
    result: list[CodeGraphNode] = []
    for node_cls in cls._registry.values():
        props = node_cls.defined_properties()
        if "kind" not in props:
            continue
        if layer is not None and "layer" not in props:
            continue
        filters = {"kind": kind}
        if layer is not None and "layer" in props:
            filters["layer"] = layer
        result.extend(node_cls.nodes.filter(**filters))
    return result
```

Key detail: FileNode and ParameterNode lack `kind` and are skipped. When
`layer` is provided, types without `layer` are also skipped. The `filters`
dict is built dynamically for the right `.nodes.filter()` call.

---

## Step 3: Create `GraphRepository` — builder and helpers

**File:** `src/codegraph/repository.py` (new)

Create the file with `GraphRepository` class, `_build_layer_graph`,
`_get_node_by_qualified_name`, and `_get_member_by_qualified_name`. No
public scope methods yet — those come in Step 4.

```python
"""GraphRepository — data access layer for the codebase graph."""

from __future__ import annotations

from codegraph.graph import LayerGraph
from codegraph.models.compound import (
    ClassNode, InterfaceNode, EnumNode, UnionNode, ModuleNode,
)
from codegraph.models.member import (
    MethodNode, AttributeNode, EnumValueNode, FunctionNode, DefineNode,
)
from codegraph.models.namespace import NamespaceNode
from codegraph.models.tags import CodeGraphNode

_COMPOUND_TYPES = [ClassNode, InterfaceNode, EnumNode, UnionNode, ModuleNode]
_MEMBER_TYPES = [MethodNode, AttributeNode, EnumValueNode, FunctionNode, DefineNode]
_NAMESPACE_TYPES = [NamespaceNode]


class GraphRepository:
    """Data access layer for the codebase graph."""

    @staticmethod
    def _get_node_by_qualified_name(qualified_name: str) -> CodeGraphNode | None:
        """Search compound and namespace types by qualified_name.
        Returns first match or None."""
        for node_cls in _COMPOUND_TYPES + _NAMESPACE_TYPES:
            node = node_cls.nodes.get_or_none(qualified_name=qualified_name)
            if node is not None:
                return node
        return None

    @staticmethod
    def _get_member_by_qualified_name(qualified_name: str) -> CodeGraphNode | None:
        """Search member types by qualified_name.
        Returns first match or None."""
        for node_cls in _MEMBER_TYPES:
            node = node_cls.nodes.get_or_none(qualified_name=qualified_name)
            if node is not None:
                return node
        return None

    @staticmethod
    def _build_layer_graph(seeds: list[CodeGraphNode]) -> LayerGraph:
        """Build a LayerGraph from seed nodes plus 1-hop neighbors.

        1. Collect seed nodes keyed by _node_key.
        2. Expand 1-hop neighbors via serialize_edges().
        3. Collect edges where both endpoints are present.
        4. Infer layer from first seed with a 'layer' property.
        """
        nodes: dict[str, CodeGraphNode] = {}
        uid_to_key: dict[str, str] = {}

        # Phase 1: add seed nodes
        for node in seeds:
            key = LayerGraph._node_key(node)
            nodes[key] = node
            uid = node._uid_value()
            if uid:
                uid_to_key[uid] = key

        # Phase 2: expand 1-hop neighbors
        for node in list(seeds):
            for edge_info in node.serialize_edges():
                target_uid = edge_info["target_uid"]
                target_type = edge_info["target_type"]
                if target_uid not in uid_to_key:
                    target_cls = CodeGraphNode._registry.get(target_type)
                    if target_cls:
                        uid_prop = target_cls._uid_prop()
                        if uid_prop:
                            neighbor = target_cls.nodes.get_or_none(
                                **{uid_prop: target_uid}
                            )
                            if neighbor:
                                neighbor_key = LayerGraph._node_key(neighbor)
                                nodes[neighbor_key] = neighbor
                                uid_to_key[target_uid] = neighbor_key

        # Phase 3: collect edges where both endpoints are present
        edges: list[dict] = []
        keys_present = set(nodes.keys())
        for node in nodes.values():
            source_key = LayerGraph._node_key(node)
            for edge_info in node.serialize_edges():
                target_uid = edge_info["target_uid"]
                target_key = uid_to_key.get(target_uid)
                if target_key is not None and target_key in keys_present:
                    edges.append({
                        "source_key": source_key,
                        "relation_type": edge_info["relation_type"],
                        "target_key": target_key,
                        "target_type": edge_info["target_type"],
                    })

        # Phase 4: derive layer
        layer = "design"
        for node in seeds:
            if "layer" in type(node).defined_properties():
                layer = getattr(node, "layer", "design") or "design"
                break

        return LayerGraph(layer=layer, nodes=nodes, edges=edges)
```

**Design notes:**

- The `uid_to_key` map is built in Phase 1 & 2, enabling O(1) edge-target
  lookup in Phase 3. This avoids the O(n) scan per edge.
- Edge collection walks *all* collected nodes, not just seeds — edges between
  neighbors are included when both endpoints are present.
- `list(seeds)` in Phase 2 prevents mutation during iteration.

---

## Step 4: Add scope methods and `save_layer_graph`

**File:** `src/codegraph/repository.py`

Add the six public read methods and the write method to `GraphRepository`.

```python
    # ── Public: scope-based read methods ──────────────────────────────

    def get_by_layer(self, layer: str) -> LayerGraph:
        """Fetch all nodes in a layer plus their 1-hop neighbors."""
        seeds = CodeGraphNode.fetch_all_by_layer(layer)
        return self._build_layer_graph(seeds)

    def get_by_source(self, source: str) -> LayerGraph:
        """Fetch all nodes from a given source project plus neighbors."""
        seeds = CodeGraphNode.fetch_all_by_source(source)
        return self._build_layer_graph(seeds)

    def get_by_namespace(self, qualified_name: str) -> LayerGraph:
        """Fetch a namespace, its compounds, and their 1-hop neighbors."""
        ns = NamespaceNode.nodes.get_or_none(qualified_name=qualified_name)
        if ns is None:
            return LayerGraph(layer="design")
        seeds = [ns] + list(ns.compounds.all())
        return self._build_layer_graph(seeds)

    def get_by_compound(self, qualified_name: str) -> LayerGraph:
        """Fetch a compound node and its 1-hop neighbors."""
        compound = self._get_node_by_qualified_name(qualified_name)
        if compound is None:
            return LayerGraph(layer="design")
        return self._build_layer_graph([compound])

    def get_by_neighbourhood(self, qualified_name: str) -> LayerGraph:
        """Fetch a node of any type and its 1-hop neighbourhood."""
        node = self._get_node_by_qualified_name(qualified_name)
        if node is None:
            node = self._get_member_by_qualified_name(qualified_name)
        if node is None:
            return LayerGraph(layer="design")
        return self._build_layer_graph([node])

    def get_by_kind(self, kind: str, layer: str | None = None) -> LayerGraph:
        """Fetch all nodes of a given kind, optionally filtered by layer."""
        seeds = CodeGraphNode.fetch_all_by_kind(kind, layer=layer)
        return self._build_layer_graph(seeds)

    # ── Public: write method ──────────────────────────────────────────

    @staticmethod
    def save_layer_graph(graph: LayerGraph) -> None:
        """Persist a LayerGraph to Neo4j. Delegates to LayerGraph.to_neo4j()."""
        graph.to_neo4j()
```

**Notes:**

- `get_by_namespace` uses `.get_or_none` (not `.get`) to avoid raising
  `DoesNotExist`. Returns empty `LayerGraph` for consistency.
- All scope methods are instance methods (room for future state).
- `save_layer_graph` is `@staticmethod` since it's pure delegation.

---

## Step 5: Export `GraphRepository` from the package

**File:** `src/codegraph/__init__.py`

1. Add import: `from codegraph.repository import GraphRepository`
2. Add `"GraphRepository"` to `__all__`, grouped after `LayerGraph`:

```python
    # Graph container
    "LayerGraph",
    # Repository
    "GraphRepository",
```

---

## Step 6: Optimize `_build_layer_graph` edge lookup

**File:** `src/codegraph/repository.py`

This step is already incorporated into Step 3's implementation. The
`uid_to_key` dict provides O(1) lookups for target key resolution during
edge collection. No additional changes needed beyond what Step 3 provides.
This step exists in the plan as a checkpoint to verify the optimization
is in place and that the edge collection phase uses `uid_to_key` rather
than scanning `nodes.items()`.

**Verification:** Confirm that Phase 3 in `_build_layer_graph` uses
`uid_to_key.get(target_uid)` instead of iterating over `nodes.items()`.

---

## Step 7: Add integration tests

**File:** `tests/repository/__init__.py` (new, empty)
**File:** `tests/repository/test_graph_repository.py` (new)

Tests require Neo4j. The existing conftest handles db setup/teardown.

### Test structure

```
tests/repository/
    __init__.py
    test_graph_repository.py
        TestGetByLayer
            test_returns_layer_graph
            test_includes_design_nodes
            test_includes_neighbors
            test_empty_layer
        TestGetByNamespace
            test_returns_namespace_and_compounds
            test_missing_namespace_returns_empty
        TestGetByCompound
            test_returns_compound_and_neighbors
            test_missing_compound_returns_empty
        TestGetByNeighbourhood
            test_works_for_member
            test_works_for_compound
            test_missing_node_returns_empty
        TestGetBySource
            test_returns_source_nodes
            test_missing_source_returns_empty
        TestGetByKind
            test_returns_all_classes
            test_returns_methods
            test_without_layer_filter
        TestSaveLayerGraph
            test_roundtrip
        TestBuildLayerGraphEdges
            test_edges_connect_seed_nodes
```

### Key test fixture

```python
import json
from pathlib import Path
import pytest
from codegraph.repository import GraphRepository
from codegraph.graph import LayerGraph
from codegraph.models.compound import ClassNode
from codegraph.models.member import MethodNode
from codegraph.models.namespace import NamespaceNode

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
FIXTURE = DATA_DIR / "design_graph.json"

@pytest.fixture
def repo():
    return GraphRepository()

@pytest.fixture
def seeded_graph():
    """Seed Neo4j with the design_graph fixture and return the LayerGraph."""
    with open(FIXTURE) as f:
        data = json.load(f)
    graph = LayerGraph.from_json(data)
    graph.to_neo4j()
    return graph
```

All tests use the `seeded_graph` fixture to populate Neo4j, then query
via the `repo` fixture. Tests verify return types (always `LayerGraph`),
non-empty results, edge connectivity, and empty results for missing
queries.

---

## Step dependency summary

```
Step 1 (fetch_all_by_source)  ─┐
Step 2 (fetch_all_by_kind)    ─┤
                                ↓
Step 3 (repository.py — builder + helpers)
                                ↓
Step 4 (repository.py — scope methods + save)
                                ↓
Step 5 (package export)
                                ↓
Step 6 (verify edge lookup optimization)
                                ↓
Step 7 (integration tests)
```

Steps 1 and 2 are independent and can be done in either order. Steps 3–5
are sequential. Step 6 is a verification checkpoint. Step 7 requires all
prior steps to be complete.

After all steps, run `pytest tests/` to verify nothing is broken and the
new tests pass.