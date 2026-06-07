# Implementation Plan: `to_dict()` / `from_dict()` for CodeGraphNode, CompositeEntry, and LayerGraph

**Issue:** [#3 — Add to_dict() / from_dict() for full-fidelity dict round-tripping](https://github.com/danielnewman09/codegraph/issues/3)

**Date:** 2026-06-07

## Overview

Add `to_dict(fields="all")` / `from_dict()` methods to `CodeGraphNode`, `CompositeEntry`, and `LayerGraph` so external services can serialize and deserialize the true representation of objects. Refactor existing `serialize()`, `to_json()`, and `from_json()` to delegate to the new methods. Preserve backward compatibility throughout.

## Task ordering principle

Each task produces a commit with all tests passing. New tests are written before or alongside the implementation they test. Refactors that change existing methods happen last, after the new methods are battle-tested independently.

---

## Task 1: Add `CodeGraphNode.to_dict()` — node-level full-fidelity serialization

### What

Add `to_dict(fields="all")` instance method to `CodeGraphNode` in `src/codegraph/models/tags.py`.

### Implementation

```python
def to_dict(self, fields: str = "all") -> dict:
    """Return a dict representation of this node.

    Args:
        fields: "all" to include every defined property, "llm" to include
            only the properties listed in ``_llm_fields``.

    Returns:
        A dict with ``type`` discriminator, ``uid_prop`` value (if the
        node type has a UniqueIdProperty), and the selected property fields.
    """
    props = dict(self.__properties__)
    if fields == "llm":
        result = {k: props[k] for k in self._llm_fields if k in props}
    else:  # fields == "all"
        result = dict(props)

    # Always include the type discriminator
    result["type"] = type(self).__name__

    # Always include uid_prop for round-trip resolution, even in llm mode
    uid_prop = type(self)._uid_prop()
    if uid_prop and uid_prop not in result:
        uid_value = getattr(self, uid_prop, None)
        if uid_value is not None:
            result[uid_prop] = uid_value

    return result
```

Key behaviors:
- `fields="all"`: all `self.__properties__` + `type` + `uid_prop`
- `fields="llm"`: only `_llm_fields` subset + `type` + `uid_prop` (if not already in `_llm_fields`)
- Does NOT include `edges` — that's `CompositeEntry`/`LayerGraph`'s job
- `uid_prop` is always included (e.g., `refid` for `FileNode`) even when not in `_llm_fields`, because it's needed for round-trip target resolution

### Test

Create `tests/test_to_dict.py`:

- `test_to_dict_all_includes_all_properties`: Create a `ClassNode` with all fields set, call `to_dict(fields="all")`, assert every defined property is present in the output.
- `test_to_dict_llm_includes_only_llm_fields`: Create a `ClassNode`, call `to_dict(fields="llm")`, assert only `_llm_fields` keys are present plus `type`.
- `test_to_dict_all_includes_uid_prop_for_filenode`: Create a `FileNode`, call `to_dict(fields="all")`, assert `refid` is in the output.
- `test_to_dict_llm_includes_uid_prop_for_filenode`: Create a `FileNode`, call `to_dict(fields="llm")`, assert `refid` is in the output even though it's not in `_llm_fields`.
- `test_to_dict_all_includes_type_discriminator`: Assert `type` key is present and equals the class name.
- `test_to_dict_llm_includes_type_discriminator`: Same for `fields="llm"`.
- `test_to_dict_all_for_method_node`: Create a `MethodNode` with all fields set, verify all properties present.
- `test_to_dict_all_for_namespace_node`: Create a `NamespaceNode`, verify all properties present.
- `test_to_dict_all_for_implementation_node`: Create an `ImplementationNode`, verify all properties present.
- `test_to_dict_all_for_parameter_node`: Create a `ParameterNode`, verify all properties present (no `uid_prop` fallback to `name`).

No Neo4j required — these are pure in-memory tests.

---

## Task 2: Add `CodeGraphNode.from_dict()` — node-level deserialization

### What

Add `from_dict(data)` classmethod to `CodeGraphNode` in `src/codegraph/models/tags.py`.

### Implementation

```python
@classmethod
def from_dict(cls, data: dict) -> "CodeGraphNode":
    """Instantiate the correct subclass from a dict.

    Reads the ``type`` key to dispatch to the registered subclass,
    then calls ``deserialize()`` on that class. Identical to
    ``from_json()`` but named for clarity when working with dicts
    directly.

    Args:
        data: A dict with a ``type`` discriminator key and property fields.

    Returns:
        A new instance of the appropriate CodeGraphNode subclass.

    Raises:
        ValueError: If the ``type`` key is missing from data.
        KeyError: If the ``type`` is not in the registry.
    """
    type_name = data.get("type")
    if type_name is None:
        raise ValueError("Dict data is missing the 'type' discriminator")
    if type_name not in cls._registry:
        raise KeyError(
            f"Unknown node type '{type_name}'. "
            f"Registered types: {sorted(cls._registry.keys())}"
        )
    return cls._registry[type_name].deserialize(data)
```

Then refactor `from_json()` to delegate:

```python
@classmethod
def from_json(cls, data: dict) -> "CodeGraphNode":
    """Instantiate the correct subclass from a serialized dict.

    Alias for :meth:`from_dict`. Reads the ``type`` key to dispatch
    to the registered subclass.

    Args:
        data: A serialized dict with a ``type`` discriminator key.

    Returns:
        A new instance of the appropriate CodeGraphNode subclass.
    """
    return cls.from_dict(data)
```

### Test

Add to `tests/test_to_dict.py`:

- `test_from_dict_creates_class_node`: Build a dict with `type="ClassNode"` and fields, call `from_dict()`, assert the result is a `ClassNode` with correct field values.
- `test_from_dict_creates_method_node`: Same for `MethodNode`.
- `test_from_dict_creates_file_node`: Same for `FileNode` — verify `refid` is preserved.
- `test_from_dict_roundtrip_with_to_dict_all`: Create a node, call `to_dict(fields="all")`, then `from_dict()` on the result, assert all property values match.
- `test_from_dict_roundtrip_with_to_dict_llm`: Create a node, call `to_dict(fields="llm")`, then `from_dict()`, assert the LLM fields match (non-LLM fields will have defaults).
- `test_from_dict_missing_type_raises`: Assert `ValueError` when `type` key is missing.
- `test_from_dict_unknown_type_raises`: Assert `KeyError` when `type` is not in registry.
- `test_from_json_delegates_to_from_dict`: Verify `from_json()` produces the same result as `from_dict()`.

No Neo4j required — pure in-memory tests.

---

## Task 3: Add `CompositeEntry.to_dict()` — entry-level serialization

### What

Add `to_dict(fields="all")` instance method to `CompositeEntry` in `src/codegraph/graph/__init__.py`.

### Implementation

```python
def to_dict(self, fields: str = "all") -> dict:
    """Serialize this entry and its composed children to a dict.

    Args:
        fields: "all" for every defined property, "llm" for only
            ``_llm_fields`` properties.

    Returns:
        A dict with the serialized node, ``composes`` key containing
        nested children, and ``references`` key containing non-COMPOSES
        edge triples.
    """
    result = self.node.to_dict(fields=fields)

    # Inline composed children under "composes"
    if self.children:
        composes = []
        for type_children in self.children.values():
            for child_entry in type_children.values():
                composes.append(child_entry.to_dict(fields=fields))
        result["composes"] = composes

    # Include non-COMPOSES references as serializable triples
    if self.references:
        result["references"] = [
            [rel_type, target_key, target_type]
            for rel_type, target_key, target_type in self.references
        ]

    return result
```

Key behaviors:
- Calls `node.to_dict(fields=fields)` for the node data
- Adds `composes` key with recursive child entries
- Adds `references` key with `[rel_type, target_key, target_type]` lists
- `references` are stored as JSON-compatible lists (not tuples)
- No `edges` key — that's only in the legacy `serialize()` format

### Test

Add to `tests/test_layer_graph.py` (in a new `TestCompositeEntryToDict` class):

- `test_entry_to_dict_fields_all`: Create a simple `CompositeEntry` with a `ClassNode`, call `to_dict(fields="all")`, verify all `ClassNode` properties are present plus `type`.
- `test_entry_to_dict_fields_llm`: Same entry, call `to_dict(fields="llm")`, verify only `_llm_fields` are present plus `type`.
- `test_entry_to_dict_with_children`: Create a `NamespaceNode` entry with `ClassNode` children, call `to_dict()`, verify `composes` key contains the children.
- `test_entry_to_dict_with_references`: Create an entry with references (e.g., `DEFINED_IN`), verify `references` key contains `[rel_type, target_key, target_type]` lists.
- `test_entry_to_dict_without_children_or_references`: Entry with no children and no references, verify no `composes` or `references` keys (or empty/absent).

No Neo4j required.

---

## Task 4: Add `CompositeEntry.from_dict()` — entry-level deserialization

### What

Add `from_dict(data)` classmethod to `CompositeEntry` in `src/codegraph/graph/__init__.py`.

### Implementation

Support both nested format (`composes` key) and the legacy `references` format:

```python
@classmethod
def from_dict(cls, data: dict) -> "CompositeEntry":
    """Reconstruct a CompositeEntry from a dict produced by to_dict().

    Args:
        data: A dict with node properties, optional ``composes`` children,
            and optional ``references`` triples.

    Returns:
        A CompositeEntry with node, children, and references populated.
    """
    node = CodeGraphNode.from_dict(data)
    entry = cls(node=node)

    # Parse composes children recursively
    for child_data in data.get("composes", []):
        child_entry = cls.from_dict(child_data)
        child_type = child_data["type"]
        child_key = LayerGraph._node_key(child_data)
        if child_type not in entry.children:
            entry.children[child_type] = {}
        entry.children[child_type][child_key] = child_entry

    # Parse references from serializable list format
    for ref in data.get("references", []):
        entry.references.append((ref[0], ref[1], ref[2]))

    return entry
```

### Test

Add to `tests/test_layer_graph.py` (new `TestCompositeEntryFromDict` class):

- `test_from_dict_roundtrip_with_to_dict`: Create an entry, `to_dict()`, then `from_dict()` on result, verify node properties and structure match.
- `test_from_dict_with_children`: Dict with `composes` key, verify children are populated.
- `test_from_dict_with_references`: Dict with `references` key, verify references are tuples of `(rel_type, target_key, target_type)`.
- `test_from_dict_nested_children`: Two-level nesting (namespace → class → method), verify full tree reconstruction.

No Neo4j required.

---

## Task 5: Add `LayerGraph.to_dict()` — graph-level serialization

### What

Add `to_dict(fields="all")` instance method to `LayerGraph` in `src/codegraph/graph/__init__.py`.

### Implementation

```python
def to_dict(self, fields: str = "all") -> dict:
    """Serialize the graph as a dict with layer metadata and entries.

    Args:
        fields: "all" for every defined property, "llm" for only
            ``_llm_fields`` properties.

    Returns:
        A dict with ``layer`` and ``entries`` keys, where entries
        is a list of CompositeEntry dicts.
    """
    return {
        "layer": self.layer,
        "entries": [
            entry.to_dict(fields=fields)
            for entry in self.entries.values()
        ],
    }
```

### Test

Add to `tests/test_layer_graph.py` (new `TestLayerGraphToDict` class):

- `test_to_dict_fields_all`: Load fixture via `from_json`, call `to_dict(fields="all")`, verify `layer` key, verify all node types present, verify properties like `layer`, `component_id`, `file_path` etc. are in the output (which `serialize()` would omit).
- `test_to_dict_fields_llm`: Same, call `to_dict(fields="llm")`, verify LLM fields present but non-LLM fields absent.
- `test_to_dict_all_includes_all_properties`: Pick a `MethodNode` entry, verify `argsstring`, `is_static`, `component_id` are present with `fields="all"` and absent with `fields="llm"`.
- `test_to_dict_preserves_composition_structure`: Verify `composes` nesting matches `to_json()` output structure.
- `test_to_dict_roundtrip`: `from_json(fixture) → to_dict(fields="all") → from_dict() → to_dict(fields="all")`, verify the two dicts match.

No Neo4j required for these tests — use `from_json` with fixture data.

---

## Task 6: Add `LayerGraph.from_dict()` — graph-level deserialization

### What

Add `from_dict(data)` classmethod to `LayerGraph` in `src/codegraph/graph/__init__.py`. Supports both the new dict format (`{"layer": ..., "entries": [...]}`) and the legacy bare-list format for backward compatibility.

### Implementation

```python
@classmethod
def from_dict(cls, data) -> "LayerGraph":
    """Reconstruct a LayerGraph from a dict produced by to_dict().

    Also accepts a bare list of entry dicts (legacy from_json format)
    for backward compatibility.

    Args:
        data: Either a dict with ``layer`` and ``entries`` keys, or
            a list of entry dicts.

    Returns:
        A LayerGraph with entries, children, and references populated.
    """
    if isinstance(data, list):
        # Legacy bare-list format — delegate to existing from_json logic
        return cls._from_list(data)

    layer = data.get("layer", "design")
    entries_data = data.get("entries", [])

    # Build entries from dict format
    key_to_entry: dict[str, CompositeEntry] = {}
    uid_to_key: dict[str, str] = {}
    child_keys: set[str] = set()

    for entry_data in entries_data:
        entry = CompositeEntry.from_dict(entry_data)
        key = cls._node_key(entry_data)
        key_to_entry[key] = entry
        uid = entry.node._uid_value()
        if uid:
            uid_to_key[uid] = key
        # Track children
        for type_children in entry.children.values():
            for child_key in type_children:
                child_keys.add(child_key)

    # Resolve references using uid_to_key if needed
    # (CompositeEntry.from_dict already populates references from serialized triples)

    root_entries = {
        key: entry
        for key, entry in key_to_entry.items()
        if key not in child_keys
    }

    return cls(layer=layer, entries=root_entries)
```

Also add `_from_list()` private classmethod that handles the legacy bare-list format (both nested and flat), migrating the logic from `_from_json_nested` and `_from_json_flat`. This keeps `from_json()` working without code duplication.

### Test

Add to `tests/test_layer_graph.py` (new `TestLayerGraphFromDict` class):

- `test_from_dict_with_layer_and_entries`: Construct a `{"layer": "design", "entries": [...]}` dict from fixture data, call `from_dict()`, verify graph structure.
- `test_from_dict_bare_list_backward_compat`: Pass a bare list (the current `from_json` format) to `from_dict()`, verify it works identically to `from_json()`.
- `test_from_dict_roundtrip_all`: `from_json(fixture) → to_dict(fields="all") → from_dict() → to_dict(fields="all")`, verify full round-trip fidelity.
- `test_from_dict_roundtrip_llm`: Same with `fields="llm"`.
- `test_from_dict_preserves_all_properties`: After round-trip with `fields="all"`, verify that non-LLM properties like `component_id`, `file_path`, `detailed_description` survive.
- `test_from_dict_invalid_layer_raises`: Pass a dict with invalid layer, verify `ValueError`.

No Neo4j required.

---

## Task 7: Refactor `serialize()` to delegate to `to_dict()`

### What

Refactor `CodeGraphNode.serialize()` in `src/codegraph/models/tags.py` to use `to_dict(fields="llm")` internally, then add edges for persisted nodes.

### Implementation

```python
def serialize(self) -> dict:
    """Return the LLM-facing representation of this node.

    Includes a ``type`` discriminator, property fields (filtered by
    ``_llm_fields``), and, if the node has been saved to Neo4j, a list
    of relationship edges from ``serialize_edges()``.

    For unsaved nodes the ``edges`` key is an empty list.

    Returns:
        A dict with ``type``, property fields, and ``edges`` keys.
    """
    result = self.to_dict(fields="llm")
    if hasattr(self, "element_id_property"):
        result["edges"] = self.serialize_edges()
    else:
        result["edges"] = []
    return result
```

### Test

- Existing `serialize()` tests must continue to pass unchanged.
- Add one targeted test: `test_serialize_delegates_to_to_dict_llm`: Create a node, call `serialize()`, verify output matches `to_dict(fields="llm")` plus `edges`.
- Run the full existing serialization test suite (no changes expected).

No Neo4j required for the new test.

---

## Task 8: Refactor `LayerGraph._serialize_entry()` into `CompositeEntry.to_dict()`

### What

Refactor `LayerGraph._serialize_entry()` to delegate to `CompositeEntry.to_dict(fields="llm")`, then apply the uid-prop fixup and COMPOSES-edge removal that the current `_serialize_entry` does.

### Implementation

The current `_serialize_entry` does three things beyond what `CompositeEntry.to_dict(fields="llm")` does:
1. Ensures `uid_prop` is included (already handled by `to_dict`)
2. Removes COMPOSES edges from the `edges` array (but in `to_dict`, there are no `edges` — references are a separate key)
3. Nests children under `composes` (already handled by `CompositeEntry.to_dict`)

So `to_json()` can be simplified:

```python
def to_json(self) -> list[dict]:
    """Serialize the graph as a nested JSON-compatible list of dicts.

    Uses ``CompositeEntry.to_dict(fields="llm")`` for each root entry.
    Composed children appear under a ``composes`` key. Non-COMPOSES
    references are included as an ``edges`` key (using ``target_uid``
    format for persisted nodes or ``target_local_id`` for unpersisted).

    For nodes that have not been persisted to Neo4j, the ``edges``
    key will be an empty list.

    Returns:
        A list of serialized node dicts with nested composition.
    """
    return [self._json_serialize_entry(entry) for entry in self.entries.values()]
```

Where `_json_serialize_entry` transforms the `to_dict` output into the legacy `edges` format:

```python
def _json_serialize_entry(self, entry: CompositeEntry) -> dict:
    """Transform CompositeEntry.to_dict() output into the legacy to_json format.

    Converts ``references`` triples into ``edges`` dicts with
    ``relation_type``, ``target_type``, and ``target_local_id`` keys,
    and strips COMPOSES (already represented by nesting).
    """
    result = entry.to_dict(fields="llm")

    # Remove references key (converted to edges below)
    references = result.pop("references", [])

    # Remove composes from edges representation — composes is already
    # represented by nesting, and to_dict() doesn't include edges anyway.
    # The references from to_dict() become edges in the legacy format.
    edges = []
    for rel_type, target_key, target_type in references:
        edges.append({
            "relation_type": rel_type,
            "target_type": target_type,
            "target_local_id": target_key,
        })
    result["edges"] = edges

    return result
```

**Important:** For persisted nodes that have been saved to Neo4j, `serialize()` includes live edges from the database (via `serialize_edges()`). The `to_json()` path currently calls `_serialize_entry()` which calls `node.serialize()`. After refactoring, `_json_serialize_entry` calls `entry.to_dict(fields="llm")` which uses `node.to_dict()` — this does NOT include database edges. For persisted nodes, we need to also include edges from `serialize_edges()`. This means `_json_serialize_entry` must merge references from the `CompositeEntry` with edges from `serialize_edges()` for persisted nodes.

Actually, looking at the current code more carefully: `_serialize_entry` calls `node.serialize()` which includes edges from `serialize_edges()` for persisted nodes, then removes COMPOSES edges. But `CompositeEntry.references` already contains the non-COMPOSES relationship info. For persisted nodes, `serialize_edges()` includes COMPOSES edges too (which are then removed).

The cleanest approach: `to_json()` for persisted nodes should use `entry.references` (which contains non-COMPOSES edges) rather than `node.serialize_edges()`. This is already the case in `_from_json_flat` and `from_neo4j`. So `_json_serialize_entry` only needs to convert `entry.references` to the edge format, which is simpler than the current approach.

### Test

- Existing `TestToJsonNested` tests must continue to pass unchanged.
- Add `test_to_json_uses_to_dict_llm`: Load fixture, call `to_json()`, verify output has `type` and LLM fields, verify `references` is NOT in output (it's transformed to `edges`).

No Neo4j required for the structural check. Full round-trip tests with Neo4j use existing test infrastructure.

---

## Task 9: Refactor `LayerGraph.from_json()` to delegate to `from_dict()`

### What

Refactor `LayerGraph.from_json()` to call `from_dict()` internally, keeping the same public API and behavior.

### Implementation

```python
@classmethod
def from_json(cls, data: list[dict]) -> "LayerGraph":
    """Deserialize from a JSON array (as produced by ``to_json()``).

    Pure deserialization — no database interaction.  Infers layer from
    the first node that has a ``layer`` field (fallback: ``"design"``).

    Accepts two formats:
    - **Nested format**: entries with a ``composes`` key containing
      child nodes.
    - **Flat format**: all nodes as separate entries with ``edges``
      arrays containing COMPOSES and other relationship types.

    Args:
        data: A list of dicts, each a serialized node with ``type``,
            properties, and optionally ``edges`` and ``composes``.

    Returns:
        A LayerGraph containing the deserialized nodes.
    """
    return cls.from_dict(data)
```

This delegates to `from_dict()`, which handles the bare-list format by calling the existing `_from_json_nested` / `_from_json_flat` logic. The private methods `_from_json_nested`, `_from_json_flat`, `_parse_nested_entry`, and `_resolve_nested_references` remain for now — they'll be consolidated in Task 10.

### Test

- All existing `TestFromJson`, `TestFromJsonNested`, `TestRoundtrip` tests must pass unchanged.
- No new tests needed — `from_json()` is now a thin wrapper and existing coverage is sufficient.

---

## Task 10: Consolidate JSON import logic into `LayerGraph.from_dict()` and `CompositeEntry.from_dict()`

### What

This is the cleanup task. After all the refactoring, consolidate the legacy JSON import methods into the new `from_dict()` / `CompositeEntry.from_dict()` architecture. The private methods `_from_json_nested`, `_from_json_flat`, `_parse_nested_entry`, and `_resolve_nested_references` should be updated or removed where they duplicate logic now in `CompositeEntry.from_dict()`.

### Implementation

This is the most delicate refactor. The key insight is:

1. **Nested format** (entries with `composes` key): `CompositeEntry.from_dict()` already handles this natively — it parses `composes` recursively and `references` triples. The `_from_json_nested` path can be replaced by creating `CompositeEntry.from_dict()` instances and then resolving uid-based edge references.

2. **Flat format** (entries with `edges` arrays): This format uses `target_local_id` and `target_uid` in edges, which requires a two-pass approach (create all nodes first, then build relationships). This logic stays in `LayerGraph.from_dict()` / `_from_list()` but delegates node creation to `CompositeEntry.from_dict()`.

The refactored `from_dict()` should handle both formats:

```python
@classmethod
def from_dict(cls, data) -> "LayerGraph":
    # ... (see Task 6 implementation)
    if isinstance(data, list):
        return cls._from_list(data)
    # dict format...
```

Where `_from_list()` replaces `_from_json` as the private entry point for bare-list data, calling `CompositeEntry.from_dict()` for node creation and the existing resolve logic for flat/nested format detection.

**Key principle:** Don't remove `_from_json_nested` / `_from_json_flat` / `_parse_nested_entry` / `_resolve_nested_references` if they still contain unique logic for the flat `edges` format that `CompositeEntry.from_dict()` doesn't handle (i.e., `target_local_id`/`target_uid` resolution). Instead, have them call `CompositeEntry.from_dict()` for the node-creation part and handle the edge resolution themselves.

### Test

- Run ALL existing tests: `TestFromJson`, `TestFromJsonNested`, `TestRoundtrip`, `TestToJsonNested`, `TestFromNeo4j`, `TestNodeKey`, `TestLayerValidation`.
- All must pass unchanged.
- Add `test_from_dict_flat_format_with_edges`: Construct a flat-format dict (the `design_graph.json` format), call `from_dict()`, verify structure matches `from_json()`.
- Add `test_from_dict_nested_format_with_composes`: Construct a nested-format dict, call `from_dict()`, verify structure.

No Neo4j required for dict-format tests.

---

## Task 11: Run full test suite and fix any failures

### What

Run the entire test suite and verify all tests pass, including:
- All existing serialization/deserialization tests
- All new `to_dict`/`from_dict` tests
- Integration tests involving `from_json`, `to_json`, `from_neo4j`, `to_neo4j`
- Edge case tests for `ParameterNode` (no uid_prop), `FileNode` (refid uid), etc.

### Implementation

```bash
cd /Users/danielnewman/dev/codegraph
pytest --tb=short -q
```

Fix any failures. Common expected issues:
- Import mismatches if `from_json` was renamed
- Test fixtures that check for specific dict key presence/absence
- Round-trip tests that compare `serialize()` output

### Acceptance

All tests pass. No regressions in existing functionality.

---

## Summary of files to modify

| File | Changes |
|------|---------|
| `src/codegraph/models/tags.py` | Add `to_dict()`, `from_dict()`, refactor `serialize()` and `from_json()` |
| `src/codegraph/graph/__init__.py` | Add `CompositeEntry.to_dict()`, `CompositeEntry.from_dict()`, `LayerGraph.to_dict()`, `LayerGraph.from_dict()`, refactor `LayerGraph._serialize_entry()`, `LayerGraph.to_json()`, `LayerGraph.from_json()`, consolidate `_from_json_nested`/`_from_json_flat` |
| `tests/test_to_dict.py` | New file — all `CodeGraphNode.to_dict()`/`from_dict()` tests |
| `tests/test_layer_graph.py` | Add `TestCompositeEntryToDict`, `TestCompositeEntryFromDict`, `TestLayerGraphToDict`, `TestLayerGraphFromDict` classes |

## Backward compatibility guarantees

1. `serialize()` output is unchanged — it delegates to `to_dict(fields="llm")` and adds edges
2. `from_json()` behavior is unchanged — it delegates to `from_dict()`
3. `to_json()` output format is unchanged — it delegates to `CompositeEntry.to_dict(fields="llm")` with edge format conversion
4. All existing tests pass without modification
5. `from_dict()` accepts both new dict format (`{"layer": ..., "entries": [...]}`) and legacy bare-list format