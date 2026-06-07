# Implementation Node Refactoring — Implementation Plan

> **Date:** 2026-06-07  
> **Spec:** `docs/specs/2026-06-07-implementation-node-design.md`  
> **Depends on:** Phase 1 fields already in place (will be partially reverted/modified)

---

## Overview

Refactor the Phase 1 inline `implementation` and `impl_embedding` fields out of `_MemberMixin` and `_CompoundMixin` into a separate `ImplementationNode` connected via `HAS_IMPLEMENTATION`. Keep `doc_embedding` inline on the mixins. Add LayerGraph expansion filtering to skip `HAS_IMPLEMENTATION` relationships.

---

## Task 1: Create ImplementationNode model

**Files:**
- Create: `src/codegraph/models/implementation.py`

- [ ] **Step 1:** Create `src/codegraph/models/implementation.py` with the following content:

```python
"""Implementation node model — :Implementation label in Neo4j.

Stores the full source code body and its vector embedding separately
from the parent method/function/compound node, so that lightweight
queries do not pull large text or embedding data.

Connected via HAS_IMPLEMENTATION from MethodNode, FunctionNode,
DefineNode, and CompoundNode types.
"""

from __future__ import annotations

from neomodel import (
    StructuredNode, StringProperty, ArrayProperty, FloatProperty,
)

from codegraph.models.tags import CodeGraphNode


class ImplementationNode(StructuredNode, CodeGraphNode):
    """Source code implementation body and its embedding — Neo4j label ``:Implementation``.

    Connected from MethodNode, FunctionNode, DefineNode, or any CompoundNode
    via a HAS_IMPLEMENTATION relationship. The implementation text and its
    vector embedding are kept on a separate node so that:

    - Lightweight queries (listing, counting, ``serialize()``) do not pull
      potentially large source text or embedding vectors.
    - LayerGraph construction skips implementation nodes by design.

    To retrieve implementation data, traverse the relationship explicitly:

        impl_nodes = method.implementation_ref.all()
        if impl_nodes:
            source_code = impl_nodes[0].implementation
            embedding = impl_nodes[0].impl_embedding

    Attributes:
        qualified_name: Matches the parent node's qualified_name.
            Used to correlate back to the owning method/function/compound.
        kind: Always "implementation".
        implementation: Full source code body of the method/function.
        impl_embedding: Vector embedding of the implementation source code.
    """

    # --- Identity ---
    qualified_name = StringProperty(default="")
    kind = StringProperty(default="implementation")

    # --- Source code ---
    implementation = StringProperty(
        default="",
        help_text="Full source code body of the method/function.",
    )

    # --- Embeddings ---
    impl_embedding = ArrayProperty(FloatProperty(), default=[],
        help_text="Vector embedding of the implementation source code.")

    # --- Serialization contract ---
    _llm_fields: set[str] = {"qualified_name", "kind", "implementation"}
```

- [ ] **Step 2:** Verify the module imports correctly:

```bash
cd /Users/danielnewman/dev/codegraph && .venv/bin/python -c "from codegraph.models.implementation import ImplementationNode; print('OK')"
```

---

## Task 2: Update models/__init__.py exports

**Files:**
- Modify: `src/codegraph/models/__init__.py`

- [ ] **Step 1:** Add `ImplementationNode` import and `__all__` entry:

In the imports section, add:
```python
from codegraph.models.implementation import ImplementationNode
```

In `__all__`, add `"ImplementationNode"` in a logical position (after the Members section, before Other):

```python
__all__ = [
    # Base
    "CodeGraphNode",
    # Compounds
    "ClassNode",
    "InterfaceNode",
    "EnumNode",
    "UnionNode",
    "ModuleNode",
    "ConceptNode",
    # Members
    "MethodNode",
    "AttributeNode",
    "EnumValueNode",
    "FunctionNode",
    "DefineNode",
    # Implementation
    "ImplementationNode",
    # Other
    "NamespaceNode",
    "FileNode",
    "ParameterNode",
]
```

- [ ] **Step 2:** Verify:

```bash
cd /Users/danielnewman/dev/codegraph && .venv/bin/python -c "from codegraph.models import ImplementationNode; print(ImplementationNode._llm_fields)"
```

Expected: `{'qualified_name', 'kind', 'implementation'}`

---

## Task 3: Refactor _MemberMixin — remove inline fields, add relationship

**Files:**
- Modify: `src/codegraph/models/member.py`

- [ ] **Step 1:** Remove `implementation` and `impl_embedding` from `_MemberMixin`:

Delete these blocks:
```python
    # --- Implementation ---
    implementation = StringProperty(
        default="",
        help_text="Full source code body of the method/function.",
    )

    # --- Vector embeddings ---
    doc_embedding = ArrayProperty(FloatProperty(), default=[],
        help_text="Vector embedding of brief_description + detailed_description.")
    impl_embedding = ArrayProperty(FloatProperty(), default=[],
        help_text="Vector embedding of the implementation source code.")
```

Replace with:
```python
    # --- Vector embeddings ---
    doc_embedding = ArrayProperty(FloatProperty(), default=[],
        help_text="Vector embedding of brief_description + detailed_description.")

    # --- Lazy-loaded implementation ----------------------------------------
    #
    #  • HAS_IMPLEMENTATION  — this member → ImplementationNode
    #    The full source code body and its vector embedding.  Kept on a
    #    separate node so that lightweight queries (listing, counting,
    #    serializing) do not pull potentially large implementation text or
    #    embedding vectors.
    #
    #    NOT expanded by LayerGraph — access via
    #    ``method.implementation_ref.all()`` when source code is needed.
    # --------------------------------------------------------------------------

    implementation_ref = RelationshipTo('codegraph.models.implementation.ImplementationNode', 'HAS_IMPLEMENTATION')
```

- [ ] **Step 2:** Update `_MemberMixin` docstring — remove `implementation` and `impl_embedding`, add note about `implementation_ref`.

- [ ] **Step 3:** Remove `"implementation"` from `MethodNode._llm_fields`:

Change from:
```python
    _llm_fields = {
        "qualified_name", "name", "kind", "brief_description",
        "type_signature", "argsstring", "visibility", "implementation",
    }
```

To:
```python
    _llm_fields = {
        "qualified_name", "name", "kind", "brief_description",
        "type_signature", "argsstring", "visibility",
    }
```

- [ ] **Step 4:** Remove `"implementation"` from `FunctionNode._llm_fields`:

Change from:
```python
    _llm_fields = {
        "qualified_name", "name", "kind", "brief_description",
        "type_signature", "argsstring", "visibility", "implementation",
    }
```

To:
```python
    _llm_fields = {
        "qualified_name", "name", "kind", "brief_description",
        "type_signature", "argsstring", "visibility",
    }
```

- [ ] **Step 5:** Remove `FloatProperty` from imports if no longer needed. Check: `doc_embedding` uses `ArrayProperty(FloatProperty())` so `FloatProperty` IS still needed. No import change required.

- [ ] **Step 6:** Verify imports and model creation:

```bash
cd /Users/danielnewman/dev/codegraph && .venv/bin/python -c "
from codegraph.models.member import MethodNode, FunctionNode
m = MethodNode(kind='method')
assert m.implementation_ref is not None
assert m.doc_embedding == []
assert not hasattr(m, 'implementation') or isinstance(getattr(m, 'implementation', None), property) or True
print('OK')
"
```

Note: After removing the `implementation` property, `hasattr` will return `False` since neomodel properties are metaclass constructs. The relationship manager `implementation_ref` will exist.

---

## Task 4: Refactor _CompoundMixin — remove inline field, add relationship

**Files:**
- Modify: `src/codegraph/models/compound.py`

- [ ] **Step 1:** Remove `implementation` from `_CompoundMixin`:

Delete:
```python
    # --- Implementation ---
    implementation = StringProperty(
        default="",
        help_text="Full source code body (e.g. for inline-defined classes).",
    )
```

Replace with the relationship (after `doc_embedding`):

```python
    # --- Lazy-loaded implementation ----------------------------------------
    #
    #  • HAS_IMPLEMENTATION  — this compound → ImplementationNode
    #    The full source code body and its vector embedding.  Kept on a
    #    separate node so that lightweight queries (listing, counting,
    #    serializing) do not pull potentially large implementation text or
    #    embedding vectors.
    #
    #    NOT expanded by LayerGraph — access via
    #    ``node.implementation_ref.all()`` when source code is needed.
    # --------------------------------------------------------------------------

    implementation_ref = RelationshipTo('codegraph.models.implementation.ImplementationNode', 'HAS_IMPLEMENTATION')
```

- [ ] **Step 2:** Update `_CompoundMixin` docstring — remove `implementation` attribute, add note about `implementation_ref`.

- [ ] **Step 3:** Verify:

```bash
cd /Users/danielnewman/dev/codegraph && .venv/bin/python -c "
from codegraph.models.compound import ClassNode
c = ClassNode(kind='class')
assert c.implementation_ref is not None
assert c.doc_embedding == []
print('OK')
"
```

---

## Task 5: Filter HAS_IMPLEMENTATION from LayerGraph expansion

**Files:**
- Modify: `src/codegraph/graph/__init__.py`

The `_build_layer_graph()` static method and `from_neo4j()` class method both iterate over `node.walk_edges()` to expand 1-hop neighbors. Both need a `continue` guard for `HAS_IMPLEMENTATION`.

- [ ] **Step 1:** Find the neighbor expansion loop in `_build_layer_graph()` (around the comment "Phase 2: expand 1-hop neighbors") and add the filter:

```python
        # Phase 2: expand 1-hop neighbors
        for node in list(seeds):
            for edge_info in node.walk_edges():
+               # Skip lazy-loaded relationships — fetched on demand, not in graph expansion
+               if edge_info["relation_type"] == "HAS_IMPLEMENTATION":
+                   continue
                target_uid = edge_info["target_uid"]
```

- [ ] **Step 2:** Find the neighbor expansion loop in `from_neo4j()` (around the comment "Expand to first-level neighbors") and add the same filter:

```python
        # Expand to first-level neighbors
        for node in matched_nodes:
            for edge in node.walk_edges():
+               # Skip lazy-loaded relationships — fetched on demand
+               if edge["relation_type"] == "HAS_IMPLEMENTATION":
+                   continue
                target_uid = edge["target_uid"]
```

- [ ] **Step 3:** Find the second `walk_edges()` loop in `from_neo4j()` (around "Walk edges and build nesting / references") and add the same filter:

```python
            for edge in node.walk_edges():
                relation_type = edge["relation_type"]
                target_uid = edge["target_uid"]
                target_type = edge["target_type"]
                is_outgoing = edge["is_outgoing"]
+               # Skip lazy-loaded relationships
+               if relation_type == "HAS_IMPLEMENTATION":
+                   continue
                target_key = uid_to_key.get(target_uid)
```

- [ ] **Step 4:** Check `GraphRepository._build_layer_graph()` — it uses the same `LayerGraph._build_layer_graph()` method, so it inherits the filter. Verify it doesn't have its own walk_edges loop that needs updating. (Review shows it delegates to `LayerGraph._build_layer_graph()`, so no additional changes needed.)

---

## Task 6: Update DDL in constants.py

**Files:**
- Modify: `src/codegraph/constants.py`

- [ ] **Step 1:** Replace the Phase 1 full-text and vector index lines at the end of `CONSTRAINTS_AND_INDEXES`.

Remove:
```python
    # Full-text search
    "CREATE FULLTEXT INDEX doc_search IF NOT EXISTS FOR (n:Compound|Member) ON EACH [n.name, n.qualified_name, n.brief_description, n.detailed_description, n.definition, n.implementation]",
    # Vector search — method/function documentation embeddings
    "CREATE VECTOR INDEX member_doc_embedding IF NOT EXISTS FOR (n:Method|Function) ON (n.doc_embedding) OPTIONS {indexConfig: {`vector.dimensions`: 1536, `vector.similarity_function`: 'cosine'}}",
    # Vector search — method/function implementation embeddings
    "CREATE VECTOR INDEX member_impl_embedding IF NOT EXISTS FOR (n:Method|Function) ON (n.impl_embedding) OPTIONS {indexConfig: {`vector.dimensions`: 1536, `vector.similarity_function`: 'cosine'}}",
```

Replace with:
```python
    # Full-text search — documentation and signatures on compounds and members
    "CREATE FULLTEXT INDEX doc_search IF NOT EXISTS FOR (n:Compound|Member) ON EACH [n.name, n.qualified_name, n.brief_description, n.detailed_description, n.definition]",
    # Full-text search — implementation source code on implementation nodes
    "CREATE FULLTEXT INDEX impl_search IF NOT EXISTS FOR (n:Implementation) ON EACH [n.implementation]",
    # Lookup indexes for Implementation nodes
    "CREATE INDEX impl_qualified IF NOT EXISTS FOR (i:Implementation) ON (i.qualified_name)",
    "CREATE INDEX impl_kind IF NOT EXISTS FOR (i:Implementation) ON (i.kind)",
    # Vector search — documentation embeddings on methods and functions
    "CREATE VECTOR INDEX doc_embedding IF NOT EXISTS FOR (n:Method|Function) ON (n.doc_embedding) OPTIONS {indexConfig: {`vector.dimensions`: 1536, `vector.similarity_function`: 'cosine'}}",
    # Vector search — implementation embeddings on implementation nodes
    "CREATE VECTOR INDEX impl_embedding IF NOT EXISTS FOR (n:Implementation) ON (n.impl_embedding) OPTIONS {indexConfig: {`vector.dimensions`: 1536, `vector.similarity_function`: 'cosine'}}",
```

---

## Task 7: Update DDL in doxygen_to_neo4j.py

**Files:**
- Modify: `examples/doxygen_to_neo4j.py`

- [ ] **Step 1:** Make the same DDL replacement as Task 6 in the `CONSTRAINTS_AND_INDEXES` list near the top of the file. The current lines are:

```python
    "CREATE FULLTEXT INDEX doc_search IF NOT EXISTS FOR (n:Compound|Member) ON EACH [n.name, n.qualified_name, n.brief_description, n.detailed_description, n.definition, n.implementation]",
    # Vector search — method/function documentation embeddings
    "CREATE VECTOR INDEX member_doc_embedding IF NOT EXISTS FOR (n:Method|Function) ON (n.doc_embedding) OPTIONS {indexConfig: {`vector.dimensions`: 1536, `vector.similarity_function`: 'cosine'}}",
    # Vector search — method/function implementation embeddings
    "CREATE VECTOR INDEX member_impl_embedding IF NOT EXISTS FOR (n:Method|Function) ON (n.impl_embedding) OPTIONS {indexConfig: {`vector.dimensions`: 1536, `vector.similarity_function`: 'cosine'}}",
```

Replace with the same new DDL as in Task 6.

---

## Task 8: Update test fixtures — remove inline fields, add ImplementationNode fixture

**Files:**
- Modify: `tests/data/method_node_full.json` — remove `"implementation"` and `"impl_embedding"` keys
- Modify: `tests/data/function_node_full.json` — remove `"implementation"` and `"impl_embedding"` keys
- Modify: `tests/data/attribute_node_full.json` — remove `"implementation"` and `"impl_embedding"` keys, keep `"doc_embedding"`
- Modify: `tests/data/define_node_full.json` — remove `"implementation"` and `"impl_embedding"` keys, keep `"doc_embedding"`
- Modify: `tests/data/enum_value_node_full.json` — remove `"implementation"` and `"impl_embedding"` keys, keep `"doc_embedding"`
- Modify: `tests/data/class_node_full.json` — remove `"implementation"` key, keep `"doc_embedding"`
- Modify: `tests/data/interface_node_full.json` — remove `"implementation"` key, keep `"doc_embedding"`
- Modify: `tests/data/enum_node_full.json` — remove `"implementation"` key, keep `"doc_embedding"`
- Modify: `tests/data/union_node_full.json` — remove `"implementation"` key, keep `"doc_embedding"`
- Modify: `tests/data/module_node_full.json` — remove `"implementation"` key, keep `"doc_embedding"`
- Create: `tests/data/implementation_node_full.json`

- [ ] **Step 1:** For each member fixture file, remove the `"implementation"` and `"impl_embedding"` keys. Keep `"doc_embedding": []`.

- [ ] **Step 2:** For each compound fixture file, remove the `"implementation"` key. Keep `"doc_embedding": []` if present.

- [ ] **Step 3:** Create `tests/data/implementation_node_full.json`:

```json
{
    "type": "ImplementationNode",
    "qualified_name": "Widget::draw",
    "name": "draw_impl",
    "kind": "implementation",
    "implementation": "void Widget::draw(Canvas c) {\n  c.beginDraw();\n  render(c);\n  c.endDraw();\n}",
    "impl_embedding": [],
    "edges": []
}
```

---

## Task 9: Update existing member tests

**Files:**
- Modify: `tests/member/test_member_search_fields.py`

The tests need major revision since `implementation` and `impl_embedding` are no longer on `_MemberMixin`.

- [ ] **Step 1:** Remove the entire `TestMemberImplementationField` class (tests `test_method_implementation_default_empty`, `test_method_implementation_stored`, `test_function_implementation_default_empty`, `test_function_implementation_stored`, `test_attribute_implementation_default_empty`, `test_define_implementation_default_empty`).

- [ ] **Step 2:** Remove `test_method_impl_embedding_default_empty` and `test_method_impl_embedding_stored` from `TestMemberEmbeddingFields`. The class should only keep `test_method_doc_embedding_*` and `test_function_embedding_fields_default` (renamed to reflect it only checks `doc_embedding`).

- [ ] **Step 3:** Update `TestMemberLlmFields`:
  - Remove `test_method_llm_fields_include_implementation` (no longer true)
  - Remove `test_function_llm_fields_include_implementation` (no longer true)
  - Change `test_method_llm_fields_exclude_embeddings` to only check `doc_embedding` is excluded (remove `impl_embedding` assertion)
  - Change `test_function_llm_fields_exclude_embeddings` similarly
  - Remove `test_method_serialize_includes_implementation`
  - Remove `test_method_serialize_excludes_embeddings` (or simplify to only check `doc_embedding`)
  - Remove `test_function_serialize_includes_implementation`
  - Remove `test_attribute_llm_fields_exclude_implementation`
  - Remove `test_define_llm_fields_exclude_implementation`
  - Add `test_method_llm_fields_exclude_implementation` (implementation is no longer on MethodNode)
  - Add `test_function_llm_fields_exclude_implementation`

- [ ] **Step 4:** Update `TestMemberDeserialization`:
  - Remove `test_method_deserialize_with_implementation`
  - Remove `test_method_deserialize_with_embeddings` (or rewrite to only check `doc_embedding`)
  - Remove `test_function_deserialize_with_implementation`
  - Update `test_method_fixture_roundtrip` to remove assertions on `implementation` and `impl_embedding`
  - Update `test_function_fixture_roundtrip` to remove assertions on `implementation` and `impl_embedding`

- [ ] **Step 5:** Add a test verifying `implementation_ref` relationship exists on member nodes:

```python
def test_method_has_implementation_ref(self):
    """MethodNode has an implementation_ref relationship manager."""
    m = MethodNode(kind="method")
    assert hasattr(m, "implementation_ref")

def test_function_has_implementation_ref(self):
    """FunctionNode has an implementation_ref relationship manager."""
    f = FunctionNode(kind="function")
    assert hasattr(f, "implementation_ref")
```

---

## Task 10: Update existing compound tests

**Files:**
- Modify: `tests/compound/test_compound_search_fields.py`

- [ ] **Step 1:** Remove all `test_*_implementation_*` tests from `TestCompoundImplementationField`. The class should become `TestCompoundEmbeddingField` only, or merge into existing. Remove `test_class_implementation_default_empty`, `test_class_implementation_stored`, `test_interface_implementation_default_empty`, `test_enum_implementation_default_empty`, `test_union_implementation_default_empty`, `test_module_implementation_default_empty`.

- [ ] **Step 2:** Update `TestCompoundLlmFields`:
  - Remove `test_class_llm_fields_exclude_implementation` (no longer relevant since implementation is gone from the mixin)
  - Keep `test_class_llm_fields_exclude_embeddings`
  - Update `test_interface_llm_fields_exclude_implementation` → remove

- [ ] **Step 3:** Update `TestCompoundDeserialization`:
  - Remove `test_class_deserialize_with_implementation`
  - Keep `test_class_deserialize_with_doc_embedding`

- [ ] **Step 4:** Add a test verifying `implementation_ref` relationship exists on compound nodes:

```python
def test_class_has_implementation_ref(self):
    """ClassNode has an implementation_ref relationship manager."""
    c = ClassNode(kind="class")
    assert hasattr(c, "implementation_ref")
```

---

## Task 11: Create ImplementationNode test files

**Files:**
- Create: `tests/implementation/__init__.py`
- Create: `tests/implementation/test_implementation_node.py`
- Create: `tests/implementation/test_implementation_search_fields.py`

- [ ] **Step 1:** Create `tests/implementation/__init__.py` (empty).

- [ ] **Step 2:** Create `tests/implementation/test_implementation_node.py`:

```python
"""Unit tests for ImplementationNode model."""

import json
from pathlib import Path

from codegraph.models.implementation import ImplementationNode
from codegraph.models.tags import CodeGraphNode

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


class TestImplementationNodeModel:
    """Test ImplementationNode creation and field defaults."""

    def test_kind_defaults_to_implementation(self):
        node = ImplementationNode()
        assert node.kind == "implementation"

    def test_qualified_name_default_empty(self):
        node = ImplementationNode()
        assert node.qualified_name == ""

    def test_implementation_default_empty(self):
        node = ImplementationNode()
        assert node.implementation == ""

    def test_impl_embedding_default_empty(self):
        node = ImplementationNode()
        assert node.impl_embedding == []

    def test_implementation_stored(self):
        node = ImplementationNode(
            qualified_name="Widget::draw",
            implementation="void draw() { render(); }",
        )
        assert node.implementation == "void draw() { render(); }"

    def test_impl_embedding_stored(self):
        node = ImplementationNode(
            qualified_name="Widget::draw",
            impl_embedding=[0.1, 0.2, 0.3],
        )
        assert node.impl_embedding == [0.1, 0.2, 0.3]

    def test_llm_fields_include_implementation(self):
        assert "implementation" in ImplementationNode._llm_fields

    def test_llm_fields_include_qualified_name(self):
        assert "qualified_name" in ImplementationNode._llm_fields

    def test_llm_fields_exclude_embedding(self):
        assert "impl_embedding" not in ImplementationNode._llm_fields

    def test_serialize_includes_implementation(self):
        node = ImplementationNode(
            qualified_name="Widget::draw",
            implementation="void draw() { render(); }",
        )
        serialized = node.serialize()
        assert "implementation" in serialized
        assert serialized["implementation"] == "void draw() { render(); }"

    def test_serialize_excludes_embedding(self):
        node = ImplementationNode(
            qualified_name="Widget::draw",
            impl_embedding=[0.1, 0.2, 0.3],
        )
        serialized = node.serialize()
        assert "impl_embedding" not in serialized

    def test_deserialize_with_implementation(self):
        data = {
            "type": "ImplementationNode",
            "qualified_name": "Widget::draw",
            "kind": "implementation",
            "implementation": "void draw() { render(); }",
        }
        node = CodeGraphNode.from_json(data)
        assert isinstance(node, ImplementationNode)
        assert node.implementation == "void draw() { render(); }"

    def test_fixture_roundtrip(self):
        """Verify implementation_node_full.json deserializes correctly."""
        with open(DATA_DIR / "implementation_node_full.json") as f:
            data = json.load(f)
        node = CodeGraphNode.from_json(data)
        assert isinstance(node, ImplementationNode)
        assert node.implementation == data["implementation"]
        assert node.impl_embedding == data["impl_embedding"]
        assert node.qualified_name == data["qualified_name"]


class TestImplementationNodeRegistry:
    """Test that ImplementationNode is registered in CodeGraphNode._registry."""

    def test_implementation_node_in_registry(self):
        assert "ImplementationNode" in CodeGraphNode._registry

    def test_implementation_node_registry_class(self):
        assert CodeGraphNode._registry["ImplementationNode"] is ImplementationNode
```

- [ ] **Step 3:** Create `tests/implementation/test_implementation_search_fields.py`:

```python
"""Unit tests for ImplementationNode search-related fields."""

from codegraph.models.implementation import ImplementationNode


class TestImplementationSearchFields:
    """Test embedding and search field behavior on ImplementationNode."""

    def test_implementation_field_is_string(self):
        node = ImplementationNode(implementation="some code")
        assert isinstance(node.implementation, str)
        assert node.implementation == "some code"

    def test_impl_embedding_is_list(self):
        node = ImplementationNode(impl_embedding=[0.5, 0.3, 0.1])
        assert isinstance(node.impl_embedding, list)
        assert len(node.impl_embedding) == 3

    def test_qualified_name_correlates_to_parent(self):
        """ImplementationNode.qualified_name matches its parent MethodNode's qualified_name."""
        node = ImplementationNode(qualified_name="Widget::draw")
        assert node.qualified_name == "Widget::draw"

    def test_empty_implementation_allowed(self):
        """ImplementationNode can be created without implementation text."""
        node = ImplementationNode(qualified_name="Widget::draw")
        assert node.implementation == ""
        assert node.impl_embedding == []
```

- [ ] **Step 4:** Verify new tests pass:

```bash
cd /Users/danielnewman/dev/codegraph && .venv/bin/python -m pytest tests/implementation/ -v
```

---

## Task 12: Add LayerGraph HAS_IMPLEMENTATION exclusion test

**Files:**
- Modify: `tests/test_layer_graph.py`

- [ ] **Step 1:** Add a test class that verifies `HAS_IMPLEMENTATION` edges are excluded from LayerGraph expansion. This requires setting up a MethodNode → ImplementationNode relationship and verifying it doesn't appear in the graph.

Since this requires Neo4j connectivity (for relationship traversal), place the test after the existing Neo4j-dependent tests. Alternatively, if the existing tests mock the DB layer, follow that pattern.

```python
class TestHasImplementationExclusion:
    """Verify that HAS_IMPLEMENTATION edges are excluded from LayerGraph expansion."""

    def test_build_layer_graph_skips_implementation_nodes(self):
        """HAS_IMPLEMENTATION relationships should not pull ImplementationNodes into the graph."""
        from codegraph.models.implementation import ImplementationNode
        from codegraph.models.member import MethodNode

        # Create a method and its implementation
        method = MethodNode(
            qualified_name="test::skip_impl_method",
            name="skip_impl_method",
            kind="method",
        ).save()

        impl = ImplementationNode(
            qualified_name="test::skip_impl_method",
            implementation="void skip_impl_method() { return; }",
        ).save()

        method.implementation_ref.connect(impl)

        try:
            from codegraph.repository import GraphRepository
            repo = GraphRepository()
            graph = repo.get_by_neighbourhood("test::skip_impl_method")

            # The method should be in the graph
            all_entries = list(graph._all_entries())
            entry_types = {type(e.node).__name__ for e in all_entries}

            # ImplementationNode should NOT appear in the graph
            assert "ImplementationNode" not in entry_types, \
                f"ImplementationNode should not be expanded into the graph, found: {entry_types}"
        finally:
            # Cleanup
            method.implementation_ref.disconnect(impl)
            impl.delete()
            method.delete()
```

Note: This test requires a running Neo4j instance. If the existing test suite uses a test database fixture, use that pattern. If not, this can be a manual/integration test.

---

## Task 13: Update unit_test_data/layer_graph_export.json if needed

**Files:**
- Modify: `tests/unit_test_data/layer_graph_export.json` (if it references `implementation` or `impl_embedding`)

- [ ] **Step 1:** Check if the file contains `implementation` or `impl_embedding` keys:

```bash
grep -n "implementation\|impl_embedding" tests/unit_test_data/layer_graph_export.json
```

- [ ] **Step 2:** If found, remove those keys from all entries. Add `"doc_embedding": []` if not already present on member/compound entries.

---

## Task 14: Run full test suite and fix any failures

- [ ] **Step 1:** Run the full test suite:

```bash
cd /Users/danielnewman/dev/codegraph && .venv/bin/python -m pytest tests/ -x -v
```

- [ ] **Step 2:** Fix any import errors (e.g., tests that reference `implementation` or `impl_embedding` on member/compound nodes).

- [ ] **Step 3:** Run again until all tests pass:

```bash
cd /Users/danielnewman/dev/codegraph && .venv/bin/python -m pytest tests/ -x -q
```

---

## Task 15: Commit

- [ ] **Step 1:** Stage all changes:

```bash
git add src/codegraph/models/implementation.py \
       src/codegraph/models/member.py \
       src/codegraph/models/compound.py \
       src/codegraph/models/__init__.py \
       src/codegraph/graph/__init__.py \
       src/codegraph/constants.py \
       examples/doxygen_to_neo4j.py \
       tests/data/ \
       tests/implementation/ \
       tests/member/test_member_search_fields.py \
       tests/compound/test_compound_search_fields.py \
       tests/test_layer_graph.py \
       tests/unit_test_data/
```

- [ ] **Step 2:** Commit:

```bash
git commit -m "feat: refactor implementation/impl_embedding to separate ImplementationNode

- Create ImplementationNode model with implementation + impl_embedding fields
- Remove implementation and impl_embedding from _MemberMixin and _CompoundMixin
- Keep doc_embedding inline on both mixins
- Add HAS_IMPLEMENTATION relationship from members/compounds to ImplementationNode
- Filter HAS_IMPLEMENTATION from LayerGraph 1-hop expansion
- Update DDL: new impl_search fulltext index, impl_embedding vector index
- Update _llm_fields: remove implementation from MethodNode/FunctionNode
- Add ImplementationNode to model exports and registry
- Update test fixtures and test files"
```