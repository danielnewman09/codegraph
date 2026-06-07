# Embedding & Full-Text Search for Methods/Functions — Implementation Spec

> **Status:** Ready for Implementation  
> **Date:** 2026-06-06  
> **Depends on:** Plan `2026-06-06-embedding-and-fulltext-search.md`

---

## Scope

Add `implementation`, `doc_embedding`, and `impl_embedding` fields to method/function
nodes, expand full-text search, and add vector index DDL. Phase 1 (storage layer) only —
no embedding computation pipeline.

---

## Changes

### 1. `src/codegraph/models/member.py`

**Import line:** Add `ArrayProperty, FloatProperty` to the neomodel import.

```python
from neomodel import (
    StructuredNode, StringProperty, IntegerProperty, BooleanProperty,
    ArrayProperty, FloatProperty, UniqueIdProperty,
    RelationshipTo, RelationshipFrom,
)
```

**`_MemberMixin` docstring:** Update to document the three new fields.

```python
class _MemberMixin(StructuredNode, CodeGraphNode):
    """Common fields and serialization for all member node types.

    Attributes:
        qualified_name: Unique identifier for the member.
        kind: Node kind (e.g. "method", "attribute", "function").
        layer: Origin layer ("design", "as-built", "dependency").
        component_id: Component identifier for grouping.
        compound_refid: Reference ID of the parent compound.
        visibility: Access level (e.g. "public", "private").
        brief_description: Short human-readable description.
        detailed_description: Full human-readable description.
        file_path: Source file path where declared.
        line_number: Source line number where declared.
        definition: Source code definition text (signature only).
        implementation: Full source code body of the method/function.
        doc_embedding: Vector embedding of documentation text.
        impl_embedding: Vector embedding of implementation source code.
    """
```

**`_MemberMixin` fields:** Add three new properties after `definition`:

```python
    # --- Definition ---
    definition = StringProperty(default="")

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

**`MethodNode._llm_fields`:** Add `"implementation"`:

```python
    _llm_fields = {
        "qualified_name", "name", "kind", "brief_description",
        "type_signature", "argsstring", "visibility", "implementation",
    }
```

**`FunctionNode._llm_fields`:** Add `"implementation"`:

```python
    _llm_fields = {
        "qualified_name", "name", "kind", "brief_description",
        "type_signature", "argsstring", "visibility", "implementation",
    }
```

**`AttributeNode._llm_fields`:** No change (attributes don't typically have searchable implementation bodies).

**`EnumValueNode._llm_fields`:** No change.

**`DefineNode._llm_fields`:** No change (define macros are short, already in `definition`).

### 2. `src/codegraph/models/compound.py`

**Import line:** Add `FloatProperty` to the neomodel import.

```python
from neomodel import (
    StructuredNode, StringProperty, IntegerProperty, BooleanProperty,
    ArrayProperty, FloatProperty, UniqueIdProperty, RelationshipTo, RelationshipFrom,
)
```

**`_CompoundMixin` fields:** Add two fields after `definition`:

```python
    # --- Definition ---
    definition = StringProperty(default="")

    # --- Implementation ---
    implementation = StringProperty(
        default="",
        help_text="Full source code body (e.g. for inline-defined classes).",
    )

    # --- Vector embeddings ---
    doc_embedding = ArrayProperty(FloatProperty(), default=[],
        help_text="Vector embedding of brief_description + detailed_description.")
```

Note: `_CompoundMixin` gets `implementation` and `doc_embedding` but NOT `impl_embedding`
— classes/interfaces don't typically have a single implementation body the way methods do.

**`ClassNode._llm_fields`:** No change — class implementation is large and not typically needed in LLM context. Can be added later if desired.

### 3. `src/codegraph/constants.py`

Add vector index DDL statements and update the full-text index.

**Replace the full-text index line:**

Old:
```python
    "CREATE FULLTEXT INDEX doc_search IF NOT EXISTS FOR (n:Compound|Member) ON EACH [n.name, n.qualified_name, n.brief_description, n.detailed_description]",
```

New:
```python
    "CREATE FULLTEXT INDEX doc_search IF NOT EXISTS FOR (n:Compound|Member) ON EACH [n.name, n.qualified_name, n.brief_description, n.detailed_description, n.definition, n.implementation]",
```

**Add vector index statements at the end of `CONSTRAINTS_AND_INDEXES`:**

```python
    # Vector search — method/function documentation embeddings
    "CREATE VECTOR INDEX member_doc_embedding IF NOT EXISTS FOR (n:Method|Function) ON (n.doc_embedding) OPTIONS {indexConfig: {`vector.dimensions`: 1536, `vector.similarity_function`: 'cosine'}}",
    # Vector search — method/function implementation embeddings
    "CREATE VECTOR INDEX member_impl_embedding IF NOT EXISTS FOR (n:Method|Function) ON (n.impl_embedding) OPTIONS {indexConfig: {`vector.dimensions`: 1536, `vector.similarity_function`: 'cosine'}}",
```

**Migration note:** The `DROP INDEX doc_search IF EXISTS;` + recreate step must be
documented for existing deployments, since Neo4j doesn't support ALTER INDEX.

### 4. `examples/doxygen_to_neo4j.py`

Update the `CONSTRAINTS_AND_INDEXES` list (lines ~30-50) to match `constants.py`:
- Update `doc_search` to include `n.definition` and `n.implementation`
- Add vector index statements

### 5. Test fixture updates

**`tests/data/method_node_full.json`:** Add:

```json
"implementation": "void Widget::draw(Canvas c) {\n  c.beginDraw();\n  render(c);\n  c.endDraw();\n}",
"doc_embedding": [],
"impl_embedding": []
```

**`tests/data/function_node_full.json`:** Add:

```json
"implementation": "CalculatorResult compute(Operation op, double a, double b) {\n  switch (op) {\n    case ADD: return a + b;\n    case SUB: return a - b;\n    default: return CalculatorResult();\n  }\n}",
"doc_embedding": [],
"impl_embedding": []
```

**`tests/data/attribute_node_full.json`:** Add:

```json
"implementation": "",
"doc_embedding": [],
"impl_embedding": []
```

**`tests/data/define_node_full.json`:** Add:

```json
"implementation": "",
"doc_embedding": [],
"impl_embedding": []
```

**`tests/data/class_node_full.json`:** Add:

```json
"implementation": "",
"doc_embedding": []
```

Update all other compound fixture files similarly (`interface_node_full.json`, `enum_node_full.json`, `union_node_full.json`, `module_node_full.json`, `namespace_node_full.json`) with `"implementation": ""` and `"doc_embedding": []`.

### 6. New unit tests

Create `tests/member/test_member_search_fields.py`:

```python
"""Unit tests for implementation and embedding fields on member nodes."""

import json
from pathlib import Path

import pytest

from codegraph.models.member import MethodNode, FunctionNode, AttributeNode, DefineNode
from codegraph.models.tags import CodeGraphNode


DATA_DIR = Path(__file__).resolve().parent.parent / "data"


class TestMemberImplementationField:
    """Test the implementation StringProperty on member nodes."""

    def test_method_implementation_default_empty(self):
        m = MethodNode(kind="method")
        assert m.implementation == ""

    def test_method_implementation_stored(self):
        m = MethodNode(
            kind="method",
            name="draw",
            implementation="void draw() { render(); }",
        )
        assert m.implementation == "void draw() { render(); }"

    def test_function_implementation_default_empty(self):
        f = FunctionNode(kind="function")
        assert f.implementation == ""

    def test_function_implementation_stored(self):
        f = FunctionNode(
            kind="function",
            name="compute",
            implementation="int compute(int x) { return x * 2; }",
        )
        assert f.implementation == "int compute(int x) { return x * 2; }"

    def test_attribute_implementation_default_empty(self):
        a = AttributeNode(kind="attribute")
        assert a.implementation == ""

    def test_define_implementation_default_empty(self):
        d = DefineNode(kind="define")
        assert d.implementation == ""


class TestMemberEmbeddingFields:
    """Test embedding ArrayProperty fields on member nodes."""

    def test_method_doc_embedding_default_empty(self):
        m = MethodNode(kind="method")
        assert m.doc_embedding == []

    def test_method_impl_embedding_default_empty(self):
        m = MethodNode(kind="method")
        assert m.impl_embedding == []

    def test_method_doc_embedding_stored(self):
        m = MethodNode(kind="method", doc_embedding=[0.1, 0.2, 0.3])
        assert m.doc_embedding == [0.1, 0.2, 0.3]

    def test_method_impl_embedding_stored(self):
        m = MethodNode(kind="method", impl_embedding=[0.4, 0.5, 0.6])
        assert m.impl_embedding == [0.4, 0.5, 0.6]

    def test_function_embedding_fields_default(self):
        f = FunctionNode(kind="function")
        assert f.doc_embedding == []
        assert f.impl_embedding == []


class TestMemberLlmFields:
    """Test that implementation is in _llm_fields for MethodNode/FunctionNode
    but embeddings are not."""

    def test_method_llm_fields_include_implementation(self):
        assert "implementation" in MethodNode._llm_fields

    def test_function_llm_fields_include_implementation(self):
        assert "implementation" in FunctionNode._llm_fields

    def test_method_llm_fields_exclude_embeddings(self):
        assert "doc_embedding" not in MethodNode._llm_fields
        assert "impl_embedding" not in MethodNode._llm_fields

    def test_function_llm_fields_exclude_embeddings(self):
        assert "doc_embedding" not in FunctionNode._llm_fields
        assert "impl_embedding" not in FunctionNode._llm_fields

    def test_method_serialize_includes_implementation(self):
        m = MethodNode(
            kind="method",
            name="draw",
            implementation="void draw() { render(); }",
        )
        serialized = m.serialize()
        assert "implementation" in serialized
        assert serialized["implementation"] == "void draw() { render(); }"

    def test_method_serialize_excludes_embeddings(self):
        m = MethodNode(
            kind="method",
            name="draw",
            doc_embedding=[0.1, 0.2, 0.3],
            impl_embedding=[0.4, 0.5, 0.6],
        )
        serialized = m.serialize()
        assert "doc_embedding" not in serialized
        assert "impl_embedding" not in serialized

    def test_function_serialize_includes_implementation(self):
        f = FunctionNode(
            kind="function",
            name="compute",
            implementation="int compute(int x) { return x * 2; }",
        )
        serialized = f.serialize()
        assert "implementation" in serialized
        assert serialized["implementation"] == "int compute(int x) { return x * 2; }"

    def test_attribute_llm_fields_exclude_implementation(self):
        """AttributeNode does not include implementation in _llm_fields."""
        assert "implementation" not in AttributeNode._llm_fields

    def test_define_llm_fields_exclude_implementation(self):
        """DefineNode does not include implementation in _llm_fields."""
        assert "implementation" not in DefineNode._llm_fields


class TestMemberDeserialization:
    """Test that from_json/deserialize handles the new fields."""

    def test_method_deserialize_with_implementation(self):
        data = {
            "type": "MethodNode",
            "qualified_name": "Widget::draw",
            "name": "draw",
            "kind": "method",
            "implementation": "void draw() { render(); }",
        }
        node = CodeGraphNode.from_json(data)
        assert isinstance(node, MethodNode)
        assert node.implementation == "void draw() { render(); }"

    def test_method_deserialize_ignores_embeddings(self):
        """Embeddings are not in _llm_fields but ARE in defined_properties,
        so deserialize should still populate them from the data dict."""
        data = {
            "type": "MethodNode",
            "qualified_name": "Widget::draw",
            "name": "draw",
            "kind": "method",
            "doc_embedding": [0.1, 0.2, 0.3],
            "impl_embedding": [0.4, 0.5, 0.6],
        }
        node = CodeGraphNode.from_json(data)
        assert isinstance(node, MethodNode)
        assert node.doc_embedding == [0.1, 0.2, 0.3]
        assert node.impl_embedding == [0.4, 0.5, 0.6]

    def test_function_deserialize_with_implementation(self):
        data = {
            "type": "FunctionNode",
            "qualified_name": "calc::compute",
            "name": "compute",
            "kind": "function",
            "implementation": "int compute(int x) { return x * 2; }",
        }
        node = CodeGraphNode.from_json(data)
        assert isinstance(node, FunctionNode)
        assert node.implementation == "int compute(int x) { return x * 2; }"
```

Create `tests/compound/test_compound_search_fields.py`:

```python
"""Unit tests for implementation and embedding fields on compound nodes."""

import pytest

from codegraph.models.compound import ClassNode, InterfaceNode, EnumNode
from codegraph.models.tags import CodeGraphNode


class TestCompoundImplementationField:
    """Test the implementation and doc_embedding fields on compound nodes."""

    def test_class_implementation_default_empty(self):
        c = ClassNode(kind="class")
        assert c.implementation == ""

    def test_class_implementation_stored(self):
        c = ClassNode(kind="class", implementation="class Foo { int x; };")
        assert c.implementation == "class Foo { int x; };"

    def test_class_doc_embedding_default_empty(self):
        c = ClassNode(kind="class")
        assert c.doc_embedding == []

    def test_interface_implementation_default_empty(self):
        i = InterfaceNode(kind="interface")
        assert i.implementation == ""

    def test_enum_implementation_default_empty(self):
        e = EnumNode(kind="enum")
        assert e.implementation == ""
```

### 7. Update `_MemberMixin._llm_fields` base set

The base `_llm_fields` on `_MemberMixin` should NOT include `"implementation"` or
the embedding fields — those are opt-in per subclass:

```python
    # --- Serialization contract ---
    _llm_fields: set[str] = {
        "qualified_name", "name", "kind", "brief_description",
        "type_signature", "visibility",
    }
```

Only `MethodNode` and `FunctionNode` add `"implementation"` to their `_llm_fields`.

---

## Execution Order

1. `src/codegraph/models/member.py` — add import, fields, update `_llm_fields`
2. `src/codegraph/models/compound.py` — add import, fields
3. `src/codegraph/constants.py` — update full-text index, add vector index DDL
4. `examples/doxygen_to_neo4j.py` — sync DDL
5. `tests/data/*.json` — add new fields to fixtures
6. `tests/member/test_member_search_fields.py` — new test file
7. `tests/compound/test_compound_search_fields.py` — new test file
8. Run `pytest tests/` and verify all pass
9. Create migration note for existing deployments (drop/recreate `doc_search` index)

## Verification

```bash
# All existing tests still pass
.venv/bin/python -m pytest tests/ -x -q

# New test files pass
.venv/bin/python -m pytest tests/member/test_member_search_fields.py -v
.venv/bin/python -m pytest tests/compound/test_compound_search_fields.py -v

# Import smoke test
.venv/bin/python -c "from codegraph.models import MethodNode, FunctionNode, ClassNode; print('OK')"
```