# Implementation Plan: Nested `to_json` / `from_json` for LayerGraph

## Overview

Rewrite `LayerGraph.to_json()` to produce nested output where COMPOSES children
are inlined under a `composes` key, and extend `from_json()` to accept both the
new nested format and the existing flat format. Add tests for the new behavior.

## Step 1: Rewrite `to_json()` in `src/codegraph/graph/__init__.py`

Replace the current flat walk with a recursive serializer that respects the
`CompositeEntry` tree structure.

**Current code:**
```python
def to_json(self) -> list[dict]:
    return [entry.node.serialize() for entry in self._all_entries()]
```

**New implementation — add a `_serialize_entry` helper:**

```python
def _serialize_entry(self, entry: CompositeEntry) -> dict:
    """Recursively serialize a CompositeEntry and its composed children.

    Produces a nested dict where composed children appear under a
    ``composes`` key and COMPOSES edges are removed from the ``edges``
    array.
    """
    serialized = entry.node.serialize()

    # Remove COMPOSES edges from the flat edges list
    edges = [e for e in serialized.get("edges", []) if e["relation_type"] != "COMPOSES"]
    serialized["edges"] = edges

    # Inline composed children under "composes"
    if entry.children:
        composes = []
        for type_children in entry.children.values():
            for child_entry in type_children.values():
                composes.append(self._serialize_entry(child_entry))
        serialized["composes"] = composes

    return serialized

def to_json(self) -> list[dict]:
    """Serialize the graph as a nested JSON-compatible list of dicts.

    Root entries are serialized recursively. Composed children appear
    under a ``composes`` key on their parent and do not appear as
    top-level entries. COMPOSES edges are excluded from the ``edges``
    array since the nesting represents them explicitly.
    """
    return [self._serialize_entry(entry) for entry in self.entries.values()]
```

**Key behaviors:**
- Only root entries appear at the top level (already the case in `self.entries`)
- Each entry's `edges` array has COMPOSES edges filtered out
- Each entry with children gets a `composes` key containing a flat list of
  recursively serialized child entries
- Entries with no children omit the `composes` key entirely

## Step 2: Extend `from_json()` to accept nested format

Add format detection and a recursive parser for the `composes` key.

**Detection:** Check if any entry in the data list has a `composes` key.

**Nested format path — add `_parse_nested_entry`:**

```python
@classmethod
def _parse_nested_entry(cls, data: dict, key_to_entry: dict, uid_to_key: dict,
                        child_keys: set) -> CompositeEntry:
    """Parse a single entry from the nested format.

    Recursively builds CompositeEntry instances from ``composes``
    children. Edges in ``edges`` are non-COMPOSES only and stored
    as references.
    """
    node = CodeGraphNode.from_json(data)
    entry = CompositeEntry(node=node)

    # Build uid → key mapping
    uid = node._uid_value()
    key = cls._node_key(data)
    if uid:
        uid_to_key[uid] = key

    # Register in the global index
    key_to_entry[key] = entry

    # Process composes children recursively
    for child_data in data.get("composes", []):
        child_entry = cls._parse_nested_entry(child_data, key_to_entry, uid_to_key, child_keys)
        child_key = cls._node_key(child_data)
        child_type = child_data["type"]
        if child_type not in entry.children:
            entry.children[child_type] = {}
        entry.children[child_type][child_key] = child_entry
        child_keys.add(child_key)

    # Process non-COMPOSES edges as references
    for edge in data.get("edges", []):
        target_key = edge.get("target_local_id")
        if target_key is None and "target_uid" in edge:
            target_key = uid_to_key.get(edge["target_uid"])
        if target_key is None:
            continue
        entry.references.append((edge["relation_type"], target_key, edge["target_type"]))

    return entry
```

**Updated `from_json`:**

```python
@classmethod
def from_json(cls, data: list[dict]) -> "LayerGraph":
    # Detect format: nested if any entry has a "composes" key
    has_nested = any("composes" in entry for entry in data)

    if has_nested:
        return cls._from_json_nested(data)

    # ... existing flat-format logic unchanged ...
```

**Add `_from_json_nested` classmethod:**

```python
@classmethod
def _from_json_nested(cls, data: list[dict]) -> "LayerGraph":
    """Deserialize from the nested JSON format (entries with composes key)."""
    key_to_entry: dict[str, CompositeEntry] = {}
    uid_to_key: dict[str, str] = {}
    child_keys: set[str] = set()
    layer: Layer = "design"

    for entry_data in data:
        cls._parse_nested_entry(entry_data, key_to_entry, uid_to_key, child_keys)
        if layer == "design" and "layer" in entry_data:
            layer = entry_data["layer"]

    root_entries = {
        key: entry for key, entry in key_to_entry.items()
        if key not in child_keys
    }
    return cls(layer=layer, entries=root_entries)
```

**Note:** Reference targets may reference nodes that aren't yet in the global
index when processing children deeply. This is fine — `_parse_nested_entry`
processes `composes` recursively first, so by the time a top-level entry
processes its `edges`, all children are already in `key_to_entry`. For
cross-tree references (e.g., DEPENDS_ON pointing to another root), the
second-pass via `_from_json_nested` processes top-level entries sequentially,
so by the time we reference a target, it may or may not be indexed yet. This
is acceptable because `references` stores `(relation_type, target_key, target_type)`
tuples resolved later (e.g., in `to_neo4j` via `_flat_index`).

## Step 3: Add `TestToJsonNested` class to `tests/test_layer_graph.py`

```python
class TestToJsonNested:
    """Tests for LayerGraph.to_json() nested output format."""

    def test_no_composes_in_edges(self):
        """COMPOSES edges should not appear in any entry's edges array."""
        with open(FIXTURE) as f:
            data = json.load(f)
        graph = LayerGraph.from_json(data)
        graph.to_neo4j()
        output = graph.to_json()

        for entry in output:
            for edge in entry.get("edges", []):
                assert edge["relation_type"] != "COMPOSES"

    def test_composes_key_present_for_parents(self):
        """Entries that compose children should have a composes key."""
        with open(FIXTURE) as f:
            data = json.load(f)
        graph = LayerGraph.from_json(data)
        graph.to_neo4j()
        output = graph.to_json()

        # NamespaceNode "calc" composes CalculatorEngine, CalculatorResult
        calc_entry = next(e for e in output if e.get("name") == "calc")
        assert "composes" in calc_entry
        assert len(calc_entry["composes"]) == 2

        # CalculatorEngine composes methods + attribute
        engine_entry = next(
            c for c in calc_entry["composes"] if c.get("name") == "CalculatorEngine"
        )
        assert "composes" in engine_entry

        # FileNode has no children — no composes key
        file_entry = next(e for e in output if e.get("type") == "FileNode")
        assert "composes" not in file_entry

    def test_composed_children_not_at_root(self):
        """Composed children should not appear as top-level entries."""
        with open(FIXTURE) as f:
            data = json.load(f)
        graph = LayerGraph.from_json(data)
        graph.to_neo4j()
        output = graph.to_json()

        root_names = {e.get("name") for e in output}
        # "add" is composed by CalculatorEngine — not at root
        assert "add" not in root_names
        # "precision" is composed by CalculatorEngine — not at root
        assert "precision" not in root_names
        # "calc" namespace IS at root
        assert "calc" in root_names

    def test_output_written_to_file(self):
        """to_json output should be persistable and re-loadable."""
        with open(FIXTURE) as f:
            data = json.load(f)
        graph = LayerGraph.from_json(data)
        graph.to_neo4j()
        output = graph.to_json()

        FIXTURE_DIR.mkdir(exist_ok=True)
        out_path = FIXTURE_DIR / "layer_graph_export.json"
        with open(out_path, "w") as f:
            json.dump(output, f, indent=2)

        # Verify we can roundtrip via from_json
        with open(out_path) as f:
            loaded = json.load(f)
        restored = LayerGraph.from_json(loaded)
        assert _count_all_entries(restored) == _count_all_entries(graph)
```

## Step 4: Add `TestFromJsonNested` class

```python
class TestFromJsonNested:
    """Tests for LayerGraph.from_json() with nested (composes) format."""

    def test_creates_nodes_from_nested_data(self):
        """Nested format should produce same total entry count as flat format."""
        with open(FIXTURE) as f:
            flat_data = json.load(f)
        graph_flat = LayerGraph.from_json(flat_data)
        graph_flat.to_neo4j()
        nested_data = graph_flat.to_json()

        graph_nested = LayerGraph.from_json(nested_data)
        assert _count_all_entries(graph_nested) == _count_all_entries(graph_flat)

    def test_composes_children_nested(self):
        """COMPOSES from nested data should create nesting under parent."""
        with open(FIXTURE) as f:
            data = json.load(f)
        graph = LayerGraph.from_json(data)
        graph.to_neo4j()
        nested = graph.to_json()

        restored = LayerGraph.from_json(nested)
        engine = _find_entry(restored, "CalculatorEngine")
        assert engine is not None
        assert "MethodNode" in engine.children
        assert "AttributeNode" in engine.children

    def test_references_preserved(self):
        """Non-COMPOSES edges should be stored as references after nested parse."""
        with open(FIXTURE) as f:
            data = json.load(f)
        graph = LayerGraph.from_json(data)
        graph.to_neo4j()
        nested = graph.to_json()

        restored = LayerGraph.from_json(nested)
        engine = _find_entry(restored, "CalculatorEngine")
        assert engine is not None
        ref_types = {r[0] for r in engine.references}
        assert "REALIZES" in ref_types
        assert "DEPENDS_ON" in ref_types
        assert "DEFINED_IN" in ref_types
        assert "COMPOSES" not in ref_types
```

## Step 5: Update existing `TestRoundtrip.test_full_graph_roundtrip`

The existing roundtrip test writes to `graph_integration.json` using the old
flat format. After `to_json` changes, it will now produce nested output.
Update the assertion that checks `len(serialized) == len(data)` — the nested
output has fewer top-level entries (composed children are nested, not flat).

Replace:
```python
assert len(serialized) == len(data)
```
With:
```python
# Root entries only — composed children are nested, not flat
assert len(serialized) == len(graph.entries)
```

The `types_in_output` vs `types_in_input` assertion will still work because
nested output still has the same node types, just at different nesting levels.

The assertion `assert _count_all_entries(restored) == len(data)` should still
pass because `from_json` now accepts the nested format.

## Step 6: Verify `test_edge_persistence` is unaffected

This test reads `entry.node.serialize()["edges"]` on individual nodes. After
the change, `node.serialize()` still returns all edges including COMPOSES —
it's only `to_json()` that filters them. So this test is unaffected.

**Verification:** `serialize()` calls `serialize_edges()` which queries Neo4j
directly and returns all relationship types. The COMPOSES filtering only
happens inside `_serialize_entry`. Confirmed no change needed.

## Files modified

| File | Change |
|---|---|
| `src/codegraph/graph/__init__.py` | Add `_serialize_entry`; rewrite `to_json`; add `_from_json_nested` and `_parse_nested_entry`; update `from_json` with format detection |
| `tests/test_layer_graph.py` | Add `TestToJsonNested` class; Add `TestFromJsonNested` class; Update `TestRoundtrip.test_full_graph_roundtrip` for nested output |
| `tests/unit_test_data/layer_graph_export.json` | Created by `test_output_written_to_file` |

## Execution order

1. Implement `_serialize_entry` and update `to_json()` in `graph/__init__.py`
2. Implement `_from_json_nested`, `_parse_nested_entry`, and update `from_json()` format detection
3. Add `TestToJsonNested` tests
4. Add `TestFromJsonNested` tests
5. Update `TestRoundtrip.test_full_graph_roundtrip`
6. Run all tests to verify no regressions