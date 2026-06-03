# LayerGraph Implementation Plan

## Overview

This plan implements the `LayerGraph` feature as described in
`docs/specs/2025-06-03-layer-graph-design.md`. Changes are organized into
7 sequential steps. Each step is self-contained and testable. All 28 existing
tests must continue to pass after every step.

**Constraint:** Do NOT commit anything.

---

## Step 1: Add `_node_category` and `find_relationship_manager` to `CodeGraphNode`

**File:** `src/codegraph/models/tags.py`

Add two things to the `CodeGraphNode` class:

### 1a. `_node_category` class attribute

```python
_node_category: str = ""
# Values: "compound" | "member" | "namespace" | "file" | "parameter"
```

This is a class-level string. It defaults to `""` so that `CodeGraphNode` itself
and the mixins (`_CompoundMixin`, `_MemberMixin`) remain blank. Each concrete
subclass overrides it (done in Step 2).

### 1b. `find_relationship_manager` class method

Move `_find_relationship_manager()` from `src/codegraph/loaders.py` into
`CodeGraphNode` as a class method. The logic is identical — it inspects
`RelationshipTo`/`RelationshipFrom` descriptors on the source node's MRO to
find the manager matching both `relation_type` and the target node's class.

```python
@classmethod
def find_relationship_manager(cls, source, relation_type: str, target):
    """Find the relationship manager on *source* matching both
    *relation_type* and the class of *target*.

    Returns the relationship manager attribute (e.g. ``source.methods``).
    Raises ``ValueError`` if no matching manager is found.
    """
    from neomodel import RelationshipTo, RelationshipFrom

    target_cls = type(target)
    for klass in type(source).__mro__:
        for name, val in vars(klass).items():
            if isinstance(val, (RelationshipTo, RelationshipFrom)):
                if val.definition["relation_type"] != relation_type:
                    continue
                rel_target = val.definition.get("model") or val._raw_class
                if rel_target == target_cls:
                    return getattr(source, name)
                if isinstance(rel_target, str) and (
                    rel_target == target_cls.__name__
                    or rel_target.endswith(f".{target_cls.__name__}")
                ):
                    return getattr(source, name)
    raise ValueError(
        f"No '{relation_type}' relationship from "
        f"{type(source).__name__} to {target_cls.__name__}"
    )
```

### 1c. `fetch_by_layer` class method

```python
@classmethod
def fetch_by_layer(cls, layer: str) -> list["CodeGraphNode"]:
    """Fetch all persisted instances of this type matching the given layer.

    Uses neomodel's ``.nodes.filter(layer=layer)``. Returns an empty list
    for types that don't have a ``layer`` property (FileNode, ParameterNode).
    """
    if "layer" not in cls.defined_properties():
        return []
    return list(cls.nodes.filter(layer=layer))
```

### 1d. `fetch_all_by_layer` class method

```python
@classmethod
def fetch_all_by_layer(cls, layer: str) -> list["CodeGraphNode"]:
    """Iterate the _registry, call fetch_by_layer on each, return a flat list
    of all nodes matching the layer across all registered types."""
    result: list[CodeGraphNode] = []
    for node_cls in cls._registry.values():
        result.extend(node_cls.fetch_by_layer(layer))
    return result
```

**Verification:** Run all 28 tests. They should still pass since we're only
adding new attributes/methods, not changing existing behavior.

---

## Step 2: Add `_node_category` to all concrete node subclasses

Add `_node_category = "..."` to each concrete subclass:

**File:** `src/codegraph/models/compound.py`
- `ClassNode._node_category = "compound"`
- `InterfaceNode._node_category = "compound"`
- `EnumNode._node_category = "compound"`
- `UnionNode._node_category = "compound"`
- `ModuleNode._node_category = "compound"`

**File:** `src/codegraph/models/member.py`
- `MethodNode._node_category = "member"`
- `AttributeNode._node_category = "member"`
- `EnumValueNode._node_category = "member"`
- `FunctionNode._node_category = "member"`
- `DefineNode._node_category = "member"`

**File:** `src/codegraph/models/namespace.py`
- `NamespaceNode._node_category = "namespace"`

**File:** `src/codegraph/models/file.py`
- `FileNode._node_category = "file"`

**File:** `src/codegraph/models/parameter.py`
- `ParameterNode._node_category = "parameter"`

**Note:** The `_node_category` attribute is set on each *concrete* class
(e.g. `ClassNode`), NOT on the mixins (`_CompoundMixin`, `_MemberMixin`).
The mixins are skipped by the registry (their names start with `_`), and
they shouldn't have a category because they're partial abstractions.

**Verification:** Run all 28 tests. No behavioral change — just metadata.

---

## Step 3: Add `LayerGraph` dataclass to `src/codegraph/graph/__init__.py`

Add the `LayerGraph` dataclass alongside the existing `CompoundGraph`,
`NamespaceGraph`, and `OntologyGraph`. Add the necessary imports.

### Imports to add

```python
from codegraph.models.tags import CodeGraphNode
```

### `LayerGraph` dataclass

```python
@dataclass
class LayerGraph:
    """A Python-only container for all nodes in a design view, filtered by layer.

    Nodes are keyed by a stable local identifier (name for most nodes,
    path for FileNode). Edges are stored as logical tuples for deferred
    persistence via ``to_neo4j()``.
    """

    layer: str  # "design" | "as-built" | "dependency"
    nodes: dict[str, CodeGraphNode] = field(default_factory=dict)
    edges: list[dict] = field(default_factory=list)

    @staticmethod
    def _node_key(obj) -> str:
        """Derive a stable local key from a node instance or raw dict.

        For dicts (raw JSON data), uses ``type`` and ``path``/``name``.
        For CodeGraphNode instances, uses ``path`` for FileNode, ``name``
        otherwise.
        """
        if isinstance(obj, dict):
            if obj.get("type") == "FileNode":
                return obj["path"]
            return obj["name"]
        # CodeGraphNode instance
        if obj.__class__.__name__ == "FileNode":
            return obj.path
        return obj.name

    @classmethod
    def from_json(cls, data: list[dict]) -> "LayerGraph":
        """Deserialize from a JSON array (as produced by ``to_json()``).

        Pure deserialization — no database interaction. Infers layer from
        the first node that has a ``layer`` field (fallback: ``"design"``).
        """
        nodes: dict[str, CodeGraphNode] = {}
        edges: list[dict] = []
        layer = "design"

        for node_data in data:
            node = CodeGraphNode.from_json(node_data)
            key = cls._node_key(node_data)
            nodes[key] = node

            # Collect logical edges for later persistence
            for edge in node_data.get("edges", []):
                edges.append({
                    "source_key": key,
                    "relation_type": edge["relation_type"],
                    "target_key": edge["target_local_id"],
                    "target_type": edge["target_type"],
                })

            # Infer layer from node data
            if layer == "design" and "layer" in node_data:
                layer = node_data["layer"]

        return cls(layer=layer, nodes=nodes, edges=edges)

    def to_neo4j(self) -> None:
        """Persist all nodes and edges to Neo4j.

        Saves each node, then connects all edges using
        ``CodeGraphNode.find_relationship_manager()``.
        """
        # Phase 1: Save all nodes
        for node in self.nodes.values():
            node.save()

        # Phase 2: Connect all edges
        for edge in self.edges:
            source = self.nodes[edge["source_key"]]
            target = self.nodes[edge["target_key"]]
            manager = CodeGraphNode.find_relationship_manager(
                source, edge["relation_type"], target
            )
            manager.connect(target)

    def to_json(self) -> list[dict]:
        """Serialize all nodes + edges to a JSON-compatible list of dicts.

        Each dict includes ``type``, properties, and ``edges``.
        Calls ``node.serialize()`` on each node (which includes live edges
        from Neo4j if the node has been saved).

        For nodes that have not been persisted to Neo4j, the ``edges``
        key will be an empty list.
        """
        return [node.serialize() for node in self.nodes.values()]

    @classmethod
    def from_neo4j(cls, layer: str) -> "LayerGraph":
        """Query Neo4j for all nodes where ``.layer == layer``, plus their
        first-level neighbors. Collect into a LayerGraph.

        This includes both endpoints of any edge touching a layer-matched
        node, even if the neighbor's layer is different.
        """
        # Fetch all layer-matched nodes
        matched_nodes = CodeGraphNode.fetch_all_by_layer(layer)

        nodes: dict[str, CodeGraphNode] = {}
        seen_uids: set[str] = set()

        # Add all layer-matched nodes
        for node in matched_nodes:
            key = cls._node_key(node)
            nodes[key] = node
            uid = node._uid_value()
            if uid:
                seen_uids.add(uid)

        # Expand to first-level neighbors
        for node in matched_nodes:
            edges = node.serialize_edges()
            for edge in edges:
                target_uid = edge["target_uid"]
                target_type = edge["target_type"]
                if target_uid not in seen_uids:
                    seen_uids.add(target_uid)
                    # Fetch neighbor from Neo4j by UID
                    target_cls = CodeGraphNode._registry.get(target_type)
                    if target_cls:
                        uid_prop = target_cls._uid_prop()
                        if uid_prop:
                            neighbor = target_cls.nodes.get_or_none(
                                **{uid_prop: target_uid}
                            )
                            if neighbor:
                                neighbor_key = cls._node_key(neighbor)
                                nodes[neighbor_key] = neighbor

        return cls(layer=layer, nodes=nodes)
```

**Verification:** Run all 28 tests. `LayerGraph` is new code, not yet called,
so existing tests should be unaffected.

---

## Step 4: Update `src/codegraph/__init__.py` exports

Replace the `load_graph` import and export with `LayerGraph`:

- Remove: `from codegraph.loaders import load_graph`
- Add: `from codegraph.graph import LayerGraph`
- Update `__all__`: remove `"load_graph"`, add `"LayerGraph"`

**Verification:** Run all 28 tests. The integration test still imports from
`codegraph.loaders` directly, so it's unaffected by the `__init__.py` change.

---

## Step 5: Update `tests/test_graph_integration.py` to use `LayerGraph`

Replace the `load_graph`-based test with `LayerGraph.from_json()` and
`LayerGraph.to_neo4j()`:

```python
"""Integration test: build the full Calculator graph from design_graph.json.

Uses ``LayerGraph`` to create all nodes and edges from the JSON fixture,
serialize the complete graph to a single JSON file, read it back, and
assert the graph roundtrips correctly.

Requires Neo4j (credentials loaded from .env via conftest.py).
"""

import json
from pathlib import Path

from codegraph.graph import LayerGraph
from codegraph.models.tags import CodeGraphNode

DATA_DIR = Path(__file__).resolve().parent / "data"
FIXTURE = DATA_DIR / "design_graph.json"
FIXTURE_DIR = Path(__file__).resolve().parent / "unit_test_data"

SKIP_FIELDS = {"qualified_name", "refid", "edges", "type"}


def test_graph_integration():
    with open(FIXTURE) as f:
        nodes_data = json.load(f)

    # Pure deserialization — no DB interaction
    graph = LayerGraph.from_json(nodes_data)

    assert len(graph.nodes) == len(nodes_data), (
        f"Expected {len(nodes_data)} nodes, got {len(graph.nodes)}"
    )

    # Explicit persistence
    graph.to_neo4j()

    # Serialize the entire graph to a single JSON file
    FIXTURE_DIR.mkdir(exist_ok=True)
    out_path = FIXTURE_DIR / "graph_integration.json"

    graph_serialized = graph.to_json()
    with open(out_path, "w") as f:
        json.dump(graph_serialized, f, indent=2)

    # Read it back and verify every node roundtrips
    with open(out_path) as f:
        loaded = json.load(f)

    assert len(loaded) == len(nodes_data)

    for original, roundtripped_data in zip(nodes_data, loaded):
        key = LayerGraph._node_key(original)
        saved = graph.nodes[key]

        assert roundtripped_data["type"] == original["type"], (
            f"{original['type']} {key}: "
            f"expected {original['type']!r}, got {roundtripped_data['type']!r}"
        )

        roundtripped = CodeGraphNode.from_json(roundtripped_data)
        original_fields = {k: v for k, v in saved.serialize().items() if k != "edges"}
        roundtripped_fields = {k: v for k, v in roundtripped.serialize().items() if k != "edges"}
        assert original_fields == roundtripped_fields, (
            f"Fields mismatch for {original['type']} '{key}':\n"
            f"  expected: {original_fields}\n"
            f"  actual:   {roundtripped_fields}"
        )

    # Every fixture edge exists in the live graph
    total_fixture_edges = 0
    for original in nodes_data:
        key = LayerGraph._node_key(original)
        saved = graph.nodes[key]
        for edge in original.get("edges", []):
            total_fixture_edges += 1
            target = graph.nodes[edge["target_local_id"]]
            found = [
                e for e in saved.serialize()["edges"]
                if e["relation_type"] == edge["relation_type"]
                and e["target_uid"] == target._uid_value()
            ]
            assert len(found) >= 1, (
                f"Missing edge: {type(saved).__name__} -[:{edge['relation_type']}]-> "
                f"{edge['target_type']} {edge['target_local_id']}"
            )

    total_live_edges = sum(
        len(n.serialize()["edges"]) for n in graph.nodes.values()
    )
    assert total_live_edges >= total_fixture_edges, (
        f"Live edges ({total_live_edges}) < fixture edges ({total_fixture_edges})"
    )


if __name__ == "__main__":
    test_graph_integration()
```

**Key changes:**
- Import `LayerGraph` from `codegraph.graph` instead of `load_graph` from
  `codegraph.loaders`
- `from_json()` is pure deserialization, then `to_neo4j()` persists
- Use `graph.nodes` dict instead of raw `nodes` dict
- Use `LayerGraph._node_key()` instead of local `_node_key()`
- Remove local `_node_key()` function
- `graph.to_json()` replaces the manual serialize loop

**Verification:** Run all 28 tests, especially the integration test.

---

## Step 6: Retire `src/codegraph/loaders.py`

Since `load_graph()` and its helpers are now superseded by `LayerGraph`, we
can retire the file. The `find_relationship_manager` logic has moved to
`CodeGraphNode`, `_node_key` has moved to `LayerGraph._node_key()`, and
`load_graph`'s logic is now `LayerGraph.from_json()` + `.to_neo4j()`.

Delete `src/codegraph/loaders.py`.

**Verification:** Run all 28 tests. The integration test no longer imports
from `loaders.py`. No other files import from it.

---

## Step 7: Clean up `src/codegraph/__init__.py`

Remove the `load_graph` import line entirely (it was replaced by `LayerGraph`
in Step 4). Remove `"load_graph"` from `__all__` if still present.

Add a comment grouping for the new export:

```python
# Graph containers
"LayerGraph",
```

**Verification:** Run all 28 tests. Verify that `from codegraph import LayerGraph`
works without importing `loaders`.

---

## Risk and Rollback

Each step is reversible by reverting the changed files. The highest-risk
step is Step 3 (adding `LayerGraph`) because it's the most new code, but
it doesn't affect existing behavior until Step 5 switches the integration
test. If Step 5 fails, revert to the old `load_graph`-based test and debug
`LayerGraph` independently.

## Test Coverage

- Steps 1-2: Existing 28 tests continue to pass. No new tests needed
  (metadata only).
- Step 3: Existing 28 tests continue to pass. `LayerGraph` is add-only.
- Step 4: Import change only. 28 tests pass.
- Step 5: Integration test rewritten. Must pass. Other 27 tests unchanged.
- Steps 6-7: Cleanup. 28 tests pass.

Future test coverage for `from_neo4j()` and LayerGraph edge cases can be
added as separate unit tests after this plan is complete.