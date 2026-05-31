# Atomize Models Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the two-layer Pydantic+neomodel architecture with atomized neomodel models as the single source of truth.

**Architecture:** Pydantic design models and repositories are deleted. neomodel `StructuredNode` subclasses — `ClassNode`, `InterfaceNode`, `EnumNode`, `UnionNode`, `ModuleNode`, `MethodNode`, `AttributeNode`, `EnumValueNode`, `FunctionNode`, `DefineNode` — become canonical. Each gets its own Neo4j label. A `LlmSerializable` ABC (with metaclass combining `NodeMeta` + `ABCMeta`) provides `serialize()`/`deserialize()`. `ClassDiagram` becomes a plain dataclass snapshot container with `from_layer()`.

**Tech Stack:** neomodel (StructuredNode), Python ABC (ABCMeta), dataclasses, pytest

---

### Task 1: LlmSerializable ABC with neomodel-compatible metaclass

**Files:**
- Create: `src/codegraph/models/tags.py`
- Test: `tests/test_field_tags.py` (rewrite)

- [ ] **Step 1: Write the failing test**

```python
"""Tests for LlmSerializable — serialize/deserialize contract."""
import pytest
from abc import abstractmethod
from codegraph.models.tags import LlmSerializable


class TestLlmSerializable:
    def test_serialize_must_be_implemented(self):
        """Subclasses that don't implement serialize() can't be instantiated."""

        class BadNode(LlmSerializable):
            pass

        with pytest.raises(TypeError):
            BadNode()  # Missing abstract method serialize

    def test_deserialize_must_be_implemented(self):
        """Subclasses that don't implement deserialize() can't be instantiated."""

        class BadNode(LlmSerializable):
            def serialize(self) -> dict:
                return {}

        with pytest.raises(TypeError):
            BadNode()  # Missing abstract method deserialize

    def test_metaclass_is_node_meta_subclass(self):
        """The combined metaclass is a subclass of NodeMeta so neomodel works."""
        from neomodel.sync_.node import NodeMeta
        assert issubclass(type(LlmSerializable), NodeMeta)

    def test_metaclass_is_abc_meta_subclass(self):
        """The combined metaclass is a subclass of ABCMeta for @abstractmethod."""
        from abc import ABCMeta
        assert issubclass(type(LlmSerializable), ABCMeta)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /Users/danielnewman/dev/codegraph && .venv/bin/python -m pytest tests/test_field_tags.py -v
```
Expected: ImportError or ModuleNotFoundError (file doesn't exist yet).

- [ ] **Step 3: Implement LlmSerializable**

```python
"""LlmSerializable ABC — contract for LLM-facing serialization on neomodel nodes.

Uses a combined metaclass (ABCMeta + NodeMeta) so that subclasses can
inherit from both StructuredNode and LlmSerializable without metaclass
conflicts.
"""

from __future__ import annotations

from abc import ABC, ABCMeta, abstractmethod
from neomodel.sync_.node import NodeMeta


class _LlmSerializableMeta(NodeMeta, ABCMeta):
    """Combined metaclass: NodeMeta for neomodel properties, ABCMeta for @abstractmethod."""


class LlmSerializable(ABC, metaclass=_LlmSerializableMeta):
    """Abstract base for neomodel nodes that can serialize for LLM consumption.

    Subclasses must:
    - Declare ``_llm_fields`` as a class-level ``set[str]`` of field names
    - Implement ``serialize()`` to return only those fields
    - Implement ``deserialize()`` to hydrate from LLM-provided dicts
    """

    _llm_fields: set[str] = set()

    @abstractmethod
    def serialize(self) -> dict:
        """Return a dict of only LLM-visible fields."""
        ...

    @classmethod
    @abstractmethod
    def deserialize(cls, data: dict) -> "LlmSerializable":
        """Instantiate a node from LLM-provided dict data."""
        ...
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd /Users/danielnewman/dev/codegraph && .venv/bin/python -m pytest tests/test_field_tags.py -v
```
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add src/codegraph/models/tags.py tests/test_field_tags.py
git commit -m "feat: add LlmSerializable ABC with neomodel-compatible metaclass"
```

---

### Task 2: CompoundMixin — abstract base for compound nodes

**Files:**
- Modify: `src/codegraph/models/compound.py` (full rewrite)
- Test: `tests/test_models.py` (start rewriting)

- [ ] **Step 1: Write failing tests for CompoundMixin**

```python
"""Tests for atomized neomodel models."""
import pytest
from neomodel import RequiredProperty, UniqueProperty

from codegraph.models.compound import ClassNode, InterfaceNode, EnumNode, UnionNode, ModuleNode
from codegraph.models.member import MethodNode, AttributeNode, EnumValueNode, FunctionNode, DefineNode


class TestCompoundMixin:
    """Common behavior shared by all compound types."""

    def test_common_fields_present_on_class(self):
        c = ClassNode(qualified_name="calc::Calculator", kind="class")
        c.save()
        retrieved = ClassNode.nodes.get(qualified_name="calc::Calculator")
        assert retrieved.name == ""
        assert retrieved.layer == "design"
        assert retrieved.brief_description == ""
        assert retrieved.detailed_description == ""
        assert retrieved.file_path == ""
        assert retrieved.line_number is None
        assert retrieved.source == ""

    def test_qualified_name_is_unique_across_kinds(self):
        ClassNode(qualified_name="calc::Foo", kind="class").save()
        with pytest.raises(UniqueProperty):
            InterfaceNode(qualified_name="calc::Foo", kind="interface").save()

    def test_kind_is_required(self):
        with pytest.raises(RequiredProperty):
            ClassNode().save()

    def test_serialize_filters_to_llm_fields(self):
        c = ClassNode(
            qualified_name="calc::Calc", name="Calc", kind="class",
            brief_description="A calculator", file_path="/src/calc.h",
            line_number=42, source="msd",
        )
        result = c.serialize()
        assert "qualified_name" in result
        assert "name" in result
        assert "kind" in result
        assert "brief_description" in result
        assert "file_path" not in result
        assert "line_number" not in result
        assert "source" not in result

    def test_deserialize_ignores_extra_keys(self):
        data = {
            "qualified_name": "calc::Calc",
            "name": "Calc",
            "kind": "class",
            "layer": "design",
            "alien_field": "should be dropped",
        }
        node = ClassNode.deserialize(data)
        assert node.qualified_name == "calc::Calc"
        assert node.name == "Calc"
        assert node.kind == "class"
        assert not hasattr(node, "alien_field")
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /Users/danielnewman/dev/codegraph && .venv/bin/python -m pytest tests/test_models.py::TestCompoundMixin -v
```
Expected: ImportError (ClassNode, InterfaceNode, etc. not yet defined).

- [ ] **Step 3: Implement CompoundMixin and ClassNode**

```python
"""Compound node models — ClassNode, InterfaceNode, EnumNode, UnionNode, ModuleNode.

Each compound kind gets its own neomodel class, Neo4j label, and
kind-specific fields. Common fields are shared via ``CompoundMixin``
(an abstract neomodel base with ``__abstract_node__ = True``).
"""

from __future__ import annotations

from neomodel import (
    StructuredNode, StringProperty, IntegerProperty, BooleanProperty,
    ArrayProperty, UniqueIdProperty, RelationshipTo, RelationshipFrom,
)

from codegraph.models.tags import LlmSerializable


class _CompoundMixin(StructuredNode, LlmSerializable):
    """Common fields and serialization for all compound node types.

    Subclasses set ``__abstract_node__ = True`` is *not* needed here
    because each subclass declares its own label via its class name.
    The shared fields are inherited into each subclass.
    """

    # --- Identity ---
    qualified_name = UniqueIdProperty()
    name = StringProperty(default="")
    kind = StringProperty(required=True)

    # --- Layer & provenance ---
    layer = StringProperty(default="design")
    component_id = IntegerProperty()
    refid = StringProperty(default="")
    source = StringProperty(default="")
    source_type = StringProperty(default="")

    # --- Documentation ---
    brief_description = StringProperty(default="")
    detailed_description = StringProperty(default="")

    # --- Location ---
    file_path = StringProperty(default="")
    line_number = IntegerProperty()

    # --- Definition ---
    definition = StringProperty(default="")

    # --- Serialization contract ---
    _llm_fields: set[str] = {"qualified_name", "name", "kind", "brief_description"}

    def serialize(self) -> dict:
        props = dict(self.__properties__)
        return {k: props[k] for k in self._llm_fields if k in props}

    @classmethod
    def deserialize(cls, data: dict) -> "_CompoundMixin":
        return cls(**{k: v for k, v in data.items()
                      if k in cls.defined_properties()})


class ClassNode(_CompoundMixin):
    """Class or struct — Neo4j label ``:Class``."""

    kind = StringProperty(default="class", required=True)
    module = StringProperty(default="")
    base_classes = ArrayProperty(StringProperty(), default=[])
    is_final = BooleanProperty(default=False)
    is_abstract = BooleanProperty(default=False)

    _llm_fields = {"qualified_name", "name", "kind", "brief_description", "base_classes"}

    # Relationships
    methods = RelationshipTo('codegraph.models.member.MethodNode', 'COMPOSES')
    attributes = RelationshipTo('codegraph.models.member.AttributeNode', 'COMPOSES')
    base = RelationshipTo('ClassNode', 'GENERALIZES')
    derived = RelationshipFrom('ClassNode', 'GENERALIZES')
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd /Users/danielnewman/dev/codegraph && .venv/bin/python -m pytest tests/test_models.py::TestCompoundMixin -v
```
Expected: FAIL — ImportError for missing member models (MethodNode, AttributeNode). We'll stub them next.

**Note:** The tests will fail on import because `ClassNode` references `MethodNode` and `AttributeNode` in its relationship descriptors. This is expected — those models don't exist yet. We'll fix this in Task 8 after member models are created.

- [ ] **Step 5: Temporarily stub member models so ClassNode can import**

Create a minimal stub in `src/codegraph/models/member.py` (will be rewritten fully in Tasks 8-12):

```python
"""Member node models — stubs for compound relationship imports."""

from neomodel import StructuredNode, StringProperty, UniqueIdProperty


class MethodNode(StructuredNode):
    qualified_name = UniqueIdProperty()
    name = StringProperty(default="")
    kind = StringProperty(default="method")

class AttributeNode(StructuredNode):
    qualified_name = UniqueIdProperty()
    name = StringProperty(default="")
    kind = StringProperty(default="attribute")

class EnumValueNode(StructuredNode):
    qualified_name = UniqueIdProperty()
    name = StringProperty(default="")
    kind = StringProperty(default="enumvalue")

class FunctionNode(StructuredNode):
    qualified_name = UniqueIdProperty()
    name = StringProperty(default="")
    kind = StringProperty(default="function")

class DefineNode(StructuredNode):
    qualified_name = UniqueIdProperty()
    name = StringProperty(default="")
    kind = StringProperty(default="define")
```

- [ ] **Step 6: Run test again**

```bash
cd /Users/danielnewman/dev/codegraph && .venv/bin/python -m pytest tests/test_models.py::TestCompoundMixin -v
```
Expected: PASS (4 tests)

- [ ] **Step 7: Commit**

```bash
git add src/codegraph/models/compound.py src/codegraph/models/member.py tests/test_models.py
git commit -m "feat: add CompoundMixin base and ClassNode with member stubs"
```

---

### Task 3: InterfaceNode model

**Files:**
- Modify: `src/codegraph/models/compound.py` (add InterfaceNode)
- Test: `tests/test_models.py` (add TestInterfaceNode)

- [ ] **Step 1: Write failing test**

```python
class TestInterfaceNode:
    def test_create_and_save(self):
        iface = InterfaceNode(
            qualified_name="io::IPrintable",
            name="IPrintable",
            kind="interface",
            module="io",
            brief_description="Printable contract",
            is_abstract=True,
        )
        iface.save()
        retrieved = InterfaceNode.nodes.get(qualified_name="io::IPrintable")
        assert retrieved.kind == "interface"
        assert retrieved.name == "IPrintable"
        assert retrieved.module == "io"
        assert retrieved.is_abstract is True

    def test_has_no_attributes_relationship(self):
        """InterfaceNode should NOT have an 'attributes' descriptor."""
        iface = InterfaceNode(qualified_name="io::IFoo", kind="interface").save()
        assert not hasattr(iface, "attributes")

    def test_has_methods_relationship(self):
        """InterfaceNode has a 'methods' descriptor for MethodNodes."""
        iface = InterfaceNode(qualified_name="io::IBar", kind="interface").save()
        assert hasattr(iface, "methods")

    def test_default_module_empty(self):
        iface = InterfaceNode(qualified_name="io::IBaz", kind="interface").save()
        assert iface.module == ""

    def test_serialize_only_llm_fields(self):
        iface = InterfaceNode(
            qualified_name="io::IPrintable", name="IPrintable", kind="interface",
            brief_description="Printable", module="io", file_path="/src/io.h",
            line_number=10,
        )
        result = iface.serialize()
        assert result == {
            "qualified_name": "io::IPrintable",
            "name": "IPrintable",
            "kind": "interface",
            "brief_description": "Printable",
        }
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /Users/danielnewman/dev/codegraph && .venv/bin/python -m pytest tests/test_models.py::TestInterfaceNode -v
```
Expected: FAIL (InterfaceNode not defined).

- [ ] **Step 3: Add InterfaceNode to compound.py**

```python
class InterfaceNode(_CompoundMixin):
    """Interface or abstract base — Neo4j label ``:Interface``."""

    kind = StringProperty(default="interface", required=True)
    module = StringProperty(default="")
    is_abstract = BooleanProperty(default=True)

    _llm_fields = {"qualified_name", "name", "kind", "brief_description"}

    # Relationships — methods only, no attributes
    methods = RelationshipTo('codegraph.models.member.MethodNode', 'COMPOSES')
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd /Users/danielnewman/dev/codegraph && .venv/bin/python -m pytest tests/test_models.py::TestInterfaceNode -v
```
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add src/codegraph/models/compound.py tests/test_models.py
git commit -m "feat: add InterfaceNode model"
```

---

### Task 4: EnumNode model

**Files:**
- Modify: `src/codegraph/models/compound.py` (add EnumNode)
- Test: `tests/test_models.py` (add TestEnumNode)

- [ ] **Step 1: Write failing test**

```python
class TestEnumNode:
    def test_create_and_save(self):
        enum = EnumNode(
            qualified_name="color::Color", name="Color", kind="enum",
            module="color", brief_description="RGB color enum",
        )
        enum.save()
        retrieved = EnumNode.nodes.get(qualified_name="color::Color")
        assert retrieved.kind == "enum"
        assert retrieved.name == "Color"
        assert retrieved.module == "color"

    def test_values_relationship(self):
        enum = EnumNode(qualified_name="color::RGB", kind="enum").save()
        assert hasattr(enum, "values")

    def test_no_methods_attributes_on_enum(self):
        enum = EnumNode(qualified_name="color::X", kind="enum").save()
        assert not hasattr(enum, "methods")
        assert not hasattr(enum, "attributes")

    def test_serialize_llm_fields(self):
        enum = EnumNode(
            qualified_name="color::Color", name="Color", kind="enum",
            brief_description="RGB", module="color", file_path="/src/color.h",
        )
        result = enum.serialize()
        assert "qualified_name" in result
        assert "brief_description" in result
        assert "file_path" not in result
        assert "module" not in result
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /Users/danielnewman/dev/codegraph && .venv/bin/python -m pytest tests/test_models.py::TestEnumNode -v
```
Expected: FAIL (EnumNode not defined).

- [ ] **Step 3: Add EnumNode to compound.py**

```python
class EnumNode(_CompoundMixin):
    """Enum type — Neo4j label ``:Enum``."""

    kind = StringProperty(default="enum", required=True)
    module = StringProperty(default="")

    _llm_fields = {"qualified_name", "name", "kind", "brief_description"}

    # Relationships
    values = RelationshipTo('codegraph.models.member.EnumValueNode', 'COMPOSES')
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd /Users/danielnewman/dev/codegraph && .venv/bin/python -m pytest tests/test_models.py::TestEnumNode -v
```
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add src/codegraph/models/compound.py tests/test_models.py
git commit -m "feat: add EnumNode model"
```

---

### Task 5: UnionNode and ModuleNode models

**Files:**
- Modify: `src/codegraph/models/compound.py` (add UnionNode, ModuleNode)
- Test: `tests/test_models.py` (add tests)

- [ ] **Step 1: Write failing tests**

```python
class TestUnionNode:
    def test_create_and_save(self):
        u = UnionNode(qualified_name="data::Variant", name="Variant",
                       kind="union", module="data")
        u.save()
        retrieved = UnionNode.nodes.get(qualified_name="data::Variant")
        assert retrieved.kind == "union"
        assert retrieved.module == "data"

    def test_serialize_only_llm_fields(self):
        u = UnionNode(qualified_name="data::V", name="V", kind="union",
                       brief_description="A variant", module="data",
                       file_path="/src/data.h")
        result = u.serialize()
        assert "qualified_name" in result
        assert "brief_description" in result
        assert "file_path" not in result


class TestModuleNode:
    def test_create_and_save(self):
        m = ModuleNode(qualified_name="calc", name="calc", kind="module")
        m.save()
        retrieved = ModuleNode.nodes.get(qualified_name="calc")
        assert retrieved.kind == "module"
        assert retrieved.name == "calc"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /Users/danielnewman/dev/codegraph && .venv/bin/python -m pytest tests/test_models.py::TestUnionNode tests/test_models.py::TestModuleNode -v
```
Expected: FAIL (not defined).

- [ ] **Step 3: Add UnionNode and ModuleNode to compound.py**

```python
class UnionNode(_CompoundMixin):
    """C/C++ union type — Neo4j label ``:Union``."""

    kind = StringProperty(default="union", required=True)
    module = StringProperty(default="")

    _llm_fields = {"qualified_name", "name", "kind", "brief_description"}


class ModuleNode(_CompoundMixin):
    """Module or logical namespace — Neo4j label ``:Module``.

    Not a direct member of ClassDiagram; module names are derived
    from compound qualified names during ``from_layer()``.
    """

    kind = StringProperty(default="module", required=True)

    _llm_fields = {"qualified_name", "name", "kind", "brief_description"}
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd /Users/danielnewman/dev/codegraph && .venv/bin/python -m pytest tests/test_models.py::TestUnionNode tests/test_models.py::TestModuleNode -v
```
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add src/codegraph/models/compound.py tests/test_models.py
git commit -m "feat: add UnionNode and ModuleNode models"
```

---

### Task 6: MethodNode and AttributeNode models

**Files:**
- Modify: `src/codegraph/models/member.py` (replace stubs with full MethodNode, AttributeNode)
- Test: `tests/test_models.py` (add member tests)

- [ ] **Step 1: Write failing tests**

```python
class TestMethodNode:
    def test_create_and_save(self):
        m = MethodNode(qualified_name="calc::Calculator::add", kind="method")
        m.save()
        retrieved = MethodNode.nodes.get(qualified_name="calc::Calculator::add")
        assert retrieved.kind == "method"
        assert retrieved.name == ""
        assert retrieved.is_static is False
        assert retrieved.is_virtual is False
        assert retrieved.is_const is False

    def test_full_creation(self):
        m = MethodNode(
            qualified_name="calc::Calculator::add", name="add", kind="method",
            type_signature="int", argsstring="(int a, int b)",
            protection="public", is_const=True, is_virtual=False,
            is_inline=True, brief_description="Adds two numbers",
            layer="as-built",
        ).save()
        retrieved = MethodNode.nodes.get(qualified_name="calc::Calculator::add")
        assert retrieved.type_signature == "int"
        assert retrieved.argsstring == "(int a, int b)"
        assert retrieved.protection == "public"
        assert retrieved.is_const is True
        assert retrieved.is_inline is True
        assert retrieved.brief_description == "Adds two numbers"

    def test_serialize_llm_fields(self):
        m = MethodNode(
            qualified_name="calc::Calc::add", name="add", kind="method",
            type_signature="int", argsstring="(int a, int b)",
            brief_description="Adds", protection="public", file_path="/src/c.h",
        )
        result = m.serialize()
        assert "qualified_name" in result
        assert "type_signature" in result
        assert "argsstring" in result
        assert "brief_description" in result
        assert "protection" not in result
        assert "file_path" not in result

    def test_kind_required(self):
        with pytest.raises(RequiredProperty):
            MethodNode().save()


class TestAttributeNode:
    def test_create_and_save(self):
        a = AttributeNode(qualified_name="calc::Calculator::count", kind="attribute")
        a.save()
        retrieved = AttributeNode.nodes.get(qualified_name="calc::Calculator::count")
        assert retrieved.kind == "attribute"
        assert retrieved.is_static is False

    def test_full_creation(self):
        a = AttributeNode(
            qualified_name="calc::Calculator::count", name="count",
            kind="attribute", type_signature="int", protection="private",
            is_static=True, is_const=False,
        ).save()
        retrieved = AttributeNode.nodes.get(qualified_name="calc::Calculator::count")
        assert retrieved.type_signature == "int"
        assert retrieved.protection == "private"
        assert retrieved.is_static is True

    def test_serialize_llm_fields(self):
        a = AttributeNode(
            qualified_name="calc::Calc::count", name="count", kind="attribute",
            type_signature="int", brief_description="Counter", protection="private",
        )
        result = a.serialize()
        assert "qualified_name" in result
        assert "name" in result
        assert "type_signature" in result
        assert "protection" not in result
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /Users/danielnewman/dev/codegraph && .venv/bin/python -m pytest tests/test_models.py::TestMethodNode tests/test_models.py::TestAttributeNode -v
```
Expected: Some tests may pass (stubs exist), but tests for specific fields like `is_const`, `type_signature`, `protection`, `serialize()` will FAIL.

- [ ] **Step 3: Implement MethodNode and AttributeNode**

Replace the entire contents of `src/codegraph/models/member.py`:

```python
"""Member node models — MethodNode, AttributeNode, EnumValueNode, FunctionNode, DefineNode.

Each member kind gets its own neomodel class and Neo4j label. Common fields
are shared via a ``_MemberMixin`` abstract base.
"""

from __future__ import annotations

from neomodel import (
    StructuredNode, StringProperty, IntegerProperty, BooleanProperty,
    UniqueIdProperty, RelationshipFrom,
)

from codegraph.models.tags import LlmSerializable


class _MemberMixin(StructuredNode, LlmSerializable):
    """Common fields and serialization for all member node types."""

    # --- Identity ---
    qualified_name = UniqueIdProperty()
    name = StringProperty(default="")
    kind = StringProperty(required=True)

    # --- Layer & provenance ---
    layer = StringProperty(default="design")
    component_id = IntegerProperty()
    refid = StringProperty(default="")
    compound_refid = StringProperty(default="")
    source = StringProperty(default="")

    # --- Documentation ---
    brief_description = StringProperty(default="")
    detailed_description = StringProperty(default="")

    # --- Location ---
    file_path = StringProperty(default="")
    line_number = IntegerProperty()

    # --- Definition ---
    definition = StringProperty(default="")

    # --- Serialization ---
    _llm_fields: set[str] = {
        "qualified_name", "name", "kind", "brief_description",
        "type_signature",
    }

    def serialize(self) -> dict:
        props = dict(self.__properties__)
        return {k: props[k] for k in self._llm_fields if k in props}

    @classmethod
    def deserialize(cls, data: dict) -> "_MemberMixin":
        return cls(**{k: v for k, v in data.items()
                      if k in cls.defined_properties()})


class MethodNode(_MemberMixin):
    """Function or method — Neo4j label ``:Method``."""

    kind = StringProperty(default="method", required=True)
    type_signature = StringProperty(default="")
    argsstring = StringProperty(default="")
    protection = StringProperty(default="")
    is_static = BooleanProperty(default=False)
    is_const = BooleanProperty(default=False)
    is_constexpr = BooleanProperty(default=False)
    is_virtual = BooleanProperty(default=False)
    is_inline = BooleanProperty(default=False)
    is_explicit = BooleanProperty(default=False)

    _llm_fields = {
        "qualified_name", "name", "kind", "brief_description",
        "type_signature", "argsstring",
    }

    # Relationships
    parent_compound = RelationshipFrom('codegraph.models.compound.ClassNode', 'COMPOSES')
    parent_interface = RelationshipFrom('codegraph.models.compound.InterfaceNode', 'COMPOSES')


class AttributeNode(_MemberMixin):
    """Member variable / data attribute — Neo4j label ``:Attribute``."""

    kind = StringProperty(default="attribute", required=True)
    type_signature = StringProperty(default="")
    protection = StringProperty(default="")
    is_static = BooleanProperty(default=False)
    is_const = BooleanProperty(default=False)

    _llm_fields = {
        "qualified_name", "name", "kind", "brief_description",
        "type_signature",
    }

    # Relationships
    parent_compound = RelationshipFrom('codegraph.models.compound.ClassNode', 'COMPOSES')


# Stubs for next tasks — will be replaced
class EnumValueNode(StructuredNode):
    qualified_name = UniqueIdProperty()
    name = StringProperty(default="")
    kind = StringProperty(default="enumvalue")


class FunctionNode(StructuredNode):
    qualified_name = UniqueIdProperty()
    name = StringProperty(default="")
    kind = StringProperty(default="function")


class DefineNode(StructuredNode):
    qualified_name = UniqueIdProperty()
    name = StringProperty(default="")
    kind = StringProperty(default="define")
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd /Users/danielnewman/dev/codegraph && .venv/bin/python -m pytest tests/test_models.py::TestMethodNode tests/test_models.py::TestAttributeNode -v
```
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add src/codegraph/models/member.py tests/test_models.py
git commit -m "feat: add MethodNode and AttributeNode models"
```

---

### Task 7: EnumValueNode, FunctionNode, DefineNode models

**Files:**
- Modify: `src/codegraph/models/member.py` (replace stubs)
- Test: `tests/test_models.py` (add tests)

- [ ] **Step 1: Write failing tests**

```python
class TestEnumValueNode:
    def test_create_and_save(self):
        v = EnumValueNode(qualified_name="color::Color::RED", kind="enumvalue")
        v.save()
        retrieved = EnumValueNode.nodes.get(qualified_name="color::Color::RED")
        assert retrieved.kind == "enumvalue"
        assert retrieved.name == ""

    def test_serialize_llm_fields(self):
        v = EnumValueNode(qualified_name="c::C::R", name="RED",
                           kind="enumvalue", brief_description="Red channel",
                           file_path="/src/c.h")
        result = v.serialize()
        assert "qualified_name" in result
        assert "name" in result
        assert "brief_description" in result
        assert "file_path" not in result


class TestFunctionNode:
    def test_create_and_save(self):
        f = FunctionNode(qualified_name="util::log", kind="function")
        f.save()
        retrieved = FunctionNode.nodes.get(qualified_name="util::log")
        assert retrieved.kind == "function"

    def test_full_creation(self):
        f = FunctionNode(
            qualified_name="util::log", name="log", kind="function",
            type_signature="void", argsstring="(const char* msg)",
            file_path="/src/util.h",
        ).save()
        retrieved = FunctionNode.nodes.get(qualified_name="util::log")
        assert retrieved.type_signature == "void"
        assert retrieved.argsstring == "(const char* msg)"

    def test_serialize_llm_fields(self):
        f = FunctionNode(qualified_name="util::log", name="log", kind="function",
                          type_signature="void", argsstring="(const char* msg)",
                          brief_description="Logs a message", file_path="/src/util.h")
        result = f.serialize()
        assert "qualified_name" in result
        assert "type_signature" in result
        assert "brief_description" in result
        assert "file_path" not in result


class TestDefineNode:
    def test_create_and_save(self):
        d = DefineNode(qualified_name="CONFIG::MAX_SIZE", kind="define")
        d.save()
        retrieved = DefineNode.nodes.get(qualified_name="CONFIG::MAX_SIZE")
        assert retrieved.kind == "define"

    def test_full_creation(self):
        d = DefineNode(
            qualified_name="CONFIG::MAX_SIZE", name="MAX_SIZE",
            kind="define", definition="#define MAX_SIZE 1024",
        ).save()
        retrieved = DefineNode.nodes.get(qualified_name="CONFIG::MAX_SIZE")
        assert retrieved.definition == "#define MAX_SIZE 1024"

    def test_serialize_llm_fields(self):
        d = DefineNode(qualified_name="C::MAX", name="MAX", kind="define",
                        brief_description="Max value", definition="#define MAX 100")
        result = d.serialize()
        assert "qualified_name" in result
        assert "name" in result
        assert "brief_description" in result
        assert "definition" not in result
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /Users/danielnewman/dev/codegraph && .venv/bin/python -m pytest tests/test_models.py::TestEnumValueNode tests/test_models.py::TestFunctionNode tests/test_models.py::TestDefineNode -v
```
Expected: Some fail (stubs lack `serialize()`, specific properties).

- [ ] **Step 3: Replace stubs in member.py with full implementations**

Replace the stub classes at the bottom of `src/codegraph/models/member.py`:

```python
class EnumValueNode(_MemberMixin):
    """Enum constant value — Neo4j label ``:EnumValue``."""

    kind = StringProperty(default="enumvalue", required=True)

    _llm_fields = {"qualified_name", "name", "kind", "brief_description"}

    # Relationships
    parent_enum = RelationshipFrom('codegraph.models.compound.EnumNode', 'COMPOSES')


class FunctionNode(_MemberMixin):
    """Free function (not a method) — Neo4j label ``:Function``."""

    kind = StringProperty(default="function", required=True)
    type_signature = StringProperty(default="")
    argsstring = StringProperty(default="")

    _llm_fields = {
        "qualified_name", "name", "kind", "brief_description",
        "type_signature", "argsstring",
    }


class DefineNode(_MemberMixin):
    """Preprocessor macro / define — Neo4j label ``:Define``."""

    kind = StringProperty(default="define", required=True)

    _llm_fields = {"qualified_name", "name", "kind", "brief_description"}
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd /Users/danielnewman/dev/codegraph && .venv/bin/python -m pytest tests/test_models.py::TestEnumValueNode tests/test_models.py::TestFunctionNode tests/test_models.py::TestDefineNode -v
```
Expected: PASS (8 tests)

- [ ] **Step 5: Commit**

```bash
git add src/codegraph/models/member.py tests/test_models.py
git commit -m "feat: add EnumValueNode, FunctionNode, DefineNode models"
```

---

### Task 8: Update models/__init__.py exports

**Files:**
- Modify: `src/codegraph/models/__init__.py`

- [ ] **Step 1: Update exports**

```python
"""Neomodel node models for the codebase graph."""

from codegraph.models.compound import (
    ClassNode, InterfaceNode, EnumNode, UnionNode, ModuleNode,
)
from codegraph.models.member import (
    MethodNode, AttributeNode, EnumValueNode, FunctionNode, DefineNode,
)
from codegraph.models.namespace import NamespaceNode
from codegraph.models.file import FileNode
from codegraph.models.parameter import ParameterNode

__all__ = [
    # Compounds
    "ClassNode",
    "InterfaceNode",
    "EnumNode",
    "UnionNode",
    "ModuleNode",
    # Members
    "MethodNode",
    "AttributeNode",
    "EnumValueNode",
    "FunctionNode",
    "DefineNode",
    # Other
    "NamespaceNode",
    "FileNode",
    "ParameterNode",
]
```

- [ ] **Step 2: Verify imports work**

```bash
cd /Users/danielnewman/dev/codegraph && .venv/bin/python -c "from codegraph.models import ClassNode, InterfaceNode, EnumNode, UnionNode, ModuleNode, MethodNode, AttributeNode, EnumValueNode, FunctionNode, DefineNode, NamespaceNode, FileNode, ParameterNode; print('All imports OK')"
```
Expected: `All imports OK`

- [ ] **Step 3: Commit**

```bash
git add src/codegraph/models/__init__.py
git commit -m "feat: update models/__init__.py with atomized exports"
```

---

### Task 9: ClassDiagram dataclass

**Files:**
- Create: `src/codegraph/diagram.py`
- Test: `tests/test_class_diagram_neo4j.py` (rewrite)

- [ ] **Step 1: Write failing tests**

```python
"""Tests for ClassDiagram dataclass container."""
import pytest
from dataclasses import dataclass

from codegraph.diagram import ClassDiagram
from codegraph.models.compound import ClassNode, InterfaceNode, EnumNode


class TestClassDiagram:
    def test_init_with_empty_lists(self):
        diagram = ClassDiagram()
        assert diagram.module_names == []
        assert diagram.classes == []
        assert diagram.interfaces == []
        assert diagram.enums == []
        assert diagram._entity_index == {}

    def test_init_populates_entity_index(self):
        c = ClassNode(qualified_name="calc::Calculator", kind="class")
        iface = InterfaceNode(qualified_name="io::IPrintable", kind="interface")
        enum = EnumNode(qualified_name="color::Color", kind="enum")

        diagram = ClassDiagram(
            classes=[c],
            interfaces=[iface],
            enums=[enum],
        )
        assert diagram.get_entity("calc::Calculator") is c
        assert diagram.get_entity("io::IPrintable") is iface
        assert diagram.get_entity("color::Color") is enum
        assert diagram.get_entity("nonexistent") is None

    def test_module_names_derived_in_from_layer(self):
        """module_names is derived from qualified names in from_layer()."""
        # This test needs a DB. We'll test with pre-saved nodes.
        ClassNode(qualified_name="calc::Calculator", kind="class",
                  name="Calculator").save()
        InterfaceNode(qualified_name="io::IPrintable", kind="interface",
                       name="IPrintable").save()

        diagram = ClassDiagram.from_layer("design")
        assert "calc" in diagram.module_names
        assert "io" in diagram.module_names

    def test_from_layer_returns_empty_for_no_matches(self):
        diagram = ClassDiagram.from_layer("nonexistent_layer")
        assert diagram.classes == []
        assert diagram.interfaces == []
        assert diagram.enums == []
        assert diagram.module_names == []

    def test_to_summary_counts(self):
        c1 = ClassNode(qualified_name="a::A", kind="class")
        c2 = ClassNode(qualified_name="b::B", kind="class")
        iface = InterfaceNode(qualified_name="c::C", kind="interface")
        enum = EnumNode(qualified_name="d::D", kind="enum")

        diagram = ClassDiagram(
            classes=[c1, c2],
            interfaces=[iface],
            enums=[enum],
        )
        summary = diagram.to_summary()
        assert summary["classes"] == 2
        assert summary["interfaces"] == 1
        assert summary["enums"] == 1

    def test_to_class_lookup(self):
        c = ClassNode(qualified_name="calc::Calculator", kind="class",
                      name="Calculator")
        diagram = ClassDiagram(classes=[c])
        lookup = diagram.to_class_lookup()
        assert lookup == {"Calculator": "calc::Calculator"}

    def test_classes_in_module(self):
        c1 = ClassNode(qualified_name="calc::Calc", kind="class", module="calc")
        c2 = ClassNode(qualified_name="calc::Adder", kind="class", module="calc")
        c3 = ClassNode(qualified_name="io::Printer", kind="class", module="io")

        diagram = ClassDiagram(classes=[c1, c2, c3])
        calc_classes = diagram.classes_in_module("calc")
        assert len(calc_classes) == 2
        assert c3 not in calc_classes

    def test_from_layer_smoke(self):
        """Quick smoke test: from_layer returns a ClassDiagram."""
        diagram = ClassDiagram.from_layer("design")
        assert isinstance(diagram, ClassDiagram)
        assert hasattr(diagram, "classes")
        assert hasattr(diagram, "interfaces")
        assert hasattr(diagram, "enums")
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /Users/danielnewman/dev/codegraph && .venv/bin/python -m pytest tests/test_class_diagram_neo4j.py -v
```
Expected: ImportError (ClassDiagram not defined).

- [ ] **Step 3: Implement ClassDiagram**

```python
"""ClassDiagram — typed snapshot container for a scoped design graph.

Reads atomized neomodel nodes from Neo4j for a given layer and presents
them as typed lists with O(1) entity lookup.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from codegraph.models.compound import ClassNode, InterfaceNode, EnumNode


@dataclass
class ClassDiagram:
    """Complete class diagram for a query scope.

    A lightweight dataclass container that holds typed lists of neomodel
    node instances. No persistence — nodes handle their own ``.save()``.
    """

    module_names: list[str] = field(default_factory=list)
    classes: list[ClassNode] = field(default_factory=list)
    interfaces: list[InterfaceNode] = field(default_factory=list)
    enums: list[EnumNode] = field(default_factory=list)

    _entity_index: dict[str, ClassNode | InterfaceNode | EnumNode] = field(
        default_factory=dict, init=False, repr=False,
    )

    def __post_init__(self) -> None:
        self._entity_index = {}
        for cls in self.classes:
            self._entity_index[cls.qualified_name] = cls
        for iface in self.interfaces:
            self._entity_index[iface.qualified_name] = iface
        for enum in self.enums:
            self._entity_index[enum.qualified_name] = enum

    # -- Factory --

    @classmethod
    def from_layer(cls, layer: str) -> "ClassDiagram":
        """Build a ClassDiagram from all design entities in a given layer.

        Queries :Class, :Interface, :Enum labels where ``layer`` matches,
        and derives module names from qualified names.
        """
        classes = list(ClassNode.nodes.filter(layer=layer))
        interfaces = list(InterfaceNode.nodes.filter(layer=layer))
        enums = list(EnumNode.nodes.filter(layer=layer))

        seen_modules: set[str] = set()
        module_names: list[str] = []

        for node in (*classes, *interfaces, *enums):
            if "::" in node.qualified_name:
                module = node.qualified_name.rsplit("::", 1)[0]
                if module and module not in seen_modules:
                    seen_modules.add(module)
                    module_names.append(module)

        return cls(
            module_names=module_names,
            classes=classes,
            interfaces=interfaces,
            enums=enums,
        )

    # -- Query --

    def get_entity(self, qualified_name: str) -> ClassNode | InterfaceNode | EnumNode | None:
        """Look up any entity by fully-qualified name. O(1)."""
        return self._entity_index.get(qualified_name)

    def classes_in_module(self, module: str) -> list[ClassNode]:
        """Return all classes belonging to the given module."""
        return [c for c in self.classes if c.module == module]

    # -- Transformations --

    def to_summary(self) -> dict:
        """Return a high-level summary of the diagram's contents."""
        attributes_count = 0
        methods_count = 0
        for c in self.classes:
            attributes_count += len(c.attributes.all()) if hasattr(c, 'attributes') else 0
            methods_count += len(c.methods.all()) if hasattr(c, 'methods') else 0

        return {
            "classes": len(self.classes),
            "interfaces": len(self.interfaces),
            "enums": len(self.enums),
            "attributes": attributes_count,
            "methods": methods_count,
        }

    def to_verification_dicts(self) -> list[dict]:
        """Convert the diagram into a list of dicts suitable for verification."""
        results = []

        for cls_node in self.classes:
            attrs = []
            if hasattr(cls_node, 'attributes'):
                attrs = [
                    {
                        "name": a.name,
                        "qualified_name": a.qualified_name,
                        "kind": "attribute",
                        "visibility": a.protection or "",
                        "type_signature": a.type_signature or "",
                        "description": a.brief_description or "",
                    }
                    for a in cls_node.attributes.all()
                ]
            meths = []
            if hasattr(cls_node, 'methods'):
                meths = [
                    {
                        "name": m.name,
                        "qualified_name": m.qualified_name,
                        "kind": "method",
                        "visibility": m.protection or "",
                        "type_signature": m.type_signature or "",
                        "argsstring": m.argsstring or "",
                        "description": m.brief_description or "",
                    }
                    for m in cls_node.methods.all()
                ]
            results.append({
                "qualified_name": cls_node.qualified_name,
                "kind": cls_node.kind,
                "description": cls_node.brief_description or "",
                "attributes": sorted(attrs, key=lambda x: x["name"]),
                "methods": sorted(meths, key=lambda x: x["name"]),
                "relationships": [],
            })

        for iface_node in self.interfaces:
            meths = []
            if hasattr(iface_node, 'methods'):
                meths = [
                    {
                        "name": m.name,
                        "qualified_name": m.qualified_name,
                        "kind": "method",
                        "visibility": m.protection or "",
                        "type_signature": m.type_signature or "",
                        "argsstring": m.argsstring or "",
                        "description": m.brief_description or "",
                    }
                    for m in iface_node.methods.all()
                ]
            results.append({
                "qualified_name": iface_node.qualified_name,
                "kind": iface_node.kind,
                "description": iface_node.brief_description or "",
                "attributes": [],
                "methods": sorted(meths, key=lambda x: x["name"]),
                "relationships": [],
            })

        return sorted(results, key=lambda x: x["qualified_name"])

    def to_draft_lookup(self) -> dict[str, dict]:
        """Build a flat lookup table of all entities in the diagram."""
        lookup: dict[str, dict] = {}
        for cls_node in self.classes:
            lookup[cls_node.qualified_name] = {
                "qualified_name": cls_node.qualified_name,
                "kind": "class",
                "description": cls_node.brief_description or "",
                "source": "draft",
            }
            if hasattr(cls_node, 'attributes'):
                for a in cls_node.attributes.all():
                    lookup[a.qualified_name] = {
                        "qualified_name": a.qualified_name,
                        "kind": "attribute",
                        "description": a.brief_description or "",
                        "source": "draft",
                    }
            if hasattr(cls_node, 'methods'):
                for m in cls_node.methods.all():
                    lookup[m.qualified_name] = {
                        "qualified_name": m.qualified_name,
                        "kind": "method",
                        "description": m.brief_description or "",
                        "source": "draft",
                    }
        for iface_node in self.interfaces:
            lookup[iface_node.qualified_name] = {
                "qualified_name": iface_node.qualified_name,
                "kind": "interface",
                "description": iface_node.brief_description or "",
                "source": "draft",
            }
            if hasattr(iface_node, 'methods'):
                for m in iface_node.methods.all():
                    lookup[m.qualified_name] = {
                        "qualified_name": m.qualified_name,
                        "kind": "method",
                        "description": m.brief_description or "",
                        "source": "draft",
                    }
        for enum_node in self.enums:
            lookup[enum_node.qualified_name] = {
                "qualified_name": enum_node.qualified_name,
                "kind": "enum",
                "description": enum_node.brief_description or "",
                "source": "draft",
            }
        return lookup

    def to_class_lookup(self) -> dict[str, str]:
        """Build a simple name → qualified_name lookup."""
        lookup: dict[str, str] = {}
        for cls_node in self.classes:
            lookup[cls_node.name] = cls_node.qualified_name
        for iface_node in self.interfaces:
            lookup[iface_node.name] = iface_node.qualified_name
        for enum_node in self.enums:
            lookup[enum_node.name] = enum_node.qualified_name
        return lookup
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd /Users/danielnewman/dev/codegraph && .venv/bin/python -m pytest tests/test_class_diagram_neo4j.py -v
```
Expected: PASS (at least tests that don't need DB data). `from_layer` tests pass if DB has data.

- [ ] **Step 5: Commit**

```bash
git add src/codegraph/diagram.py tests/test_class_diagram_neo4j.py
git commit -m "feat: add ClassDiagram dataclass with from_layer()"
```

---

### Task 10: Delete designs/ and repositories/ submodules

**Files:**
- Delete: `src/codegraph/designs/` (entire directory)
- Delete: `src/codegraph/repositories/` (entire directory)

- [ ] **Step 1: Remove the directories**

```bash
cd /Users/danielnewman/dev/codegraph
rm -rf src/codegraph/designs/
rm -rf src/codegraph/repositories/
```

- [ ] **Step 2: Verify no imports reference them**

```bash
cd /Users/danielnewman/dev/codegraph && grep -r "from codegraph.designs" src/ || echo "No design imports found"
cd /Users/danielnewman/dev/codegraph && grep -r "from codegraph.repositories" src/ || echo "No repository imports found"
```
Expected: Both commands output "No ... imports found" (we haven't updated all imports yet — if any remain, we'll fix in Task 12).

- [ ] **Step 3: Commit**

```bash
git rm -r src/codegraph/designs/ src/codegraph/repositories/
git commit -m "refactor: remove designs/ and repositories/ submodules"
```

---

### Task 11: Clean up edges.py and constants.py

**Files:**
- Modify: `src/codegraph/edges.py` (delete CodebaseEdge, keep only predicate constants)
- Modify: `src/codegraph/constants.py` (add predicates if not already there)

- [ ] **Step 1: Check what's in edges.py that needs to move**

`CodebaseEdge` goes away. `PREDICATES`, `PREDICATE_TO_REL_TYPE`, `DEFAULT_PREDICATES` are already declared in `constants.py`. The `edges.py` file also declares them. Let's check for duplication.

```bash
cd /Users/danielnewman/dev/codegraph && grep -n "PREDICATES\|PREDICATE_TO_REL_TYPE\|DEFAULT_PREDICATES" src/codegraph/edges.py
```

- [ ] **Step 2: Remove CodebaseEdge from edges.py, keep it as a predicate-only module or delete it**

Since `constants.py` already has `PREDICATES`, `PREDICATE_TO_REL_TYPE`, and `DEFAULT_PREDICATES`, `edges.py` is fully redundant. Delete it:

```bash
rm src/codegraph/edges.py
```

- [ ] **Step 3: Verify constants.py has all needed predicate exports**

```bash
cd /Users/danielnewman/dev/codegraph && grep "PREDICATES\|PREDICATE_TO_REL_TYPE\|DEFAULT_PREDICATES" src/codegraph/constants.py
```
Expected: Should show all three are defined in constants.py (they already are).

- [ ] **Step 4: Commit**

```bash
git rm src/codegraph/edges.py
git commit -m "refactor: delete edges.py (predicates already in constants.py)"
```

---

### Task 12: Update graph/ type annotations

**Files:**
- Modify: `src/codegraph/graph/__init__.py`

- [ ] **Step 1: Update imports and type annotations**

The current imports reference `CompoundNode` and `MemberNode`. Change to use the new atomized models:

```python
"""Typed graph containers for the ontology visualization.

Each container is self-contained: one Cypher query fills all fields.
No secondary queries are needed to resolve members, edges, or nested objects.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from codegraph.models.compound import ClassNode, InterfaceNode, EnumNode, UnionNode
from codegraph.models.member import MethodNode, AttributeNode, EnumValueNode
from codegraph.models.namespace import NamespaceNode

# Union type for any compound node
CompoundNodeType = ClassNode | InterfaceNode | EnumNode | UnionNode
# Union type for any member node
MemberNodeType = MethodNode | AttributeNode | EnumValueNode


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
    """Self-contained payload for one compound node.

    One Cypher query returns the compound, all its members (via COMPOSES),
    nested compounds (via COMPOSES → nested classes), and all non-COMPOSES
    edges in and out.
    """

    node: CompoundNodeType
    members: list[MemberNodeType] = field(default_factory=list)
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


# OntologyGraph stays the same — the to_raw() method uses __properties__
# which every StructuredNode has, no logic changes needed.
@dataclass
class OntologyGraph:
    """Top-level graph for the ontology visualization page."""

    namespaces: list[NamespaceGraph] = field(default_factory=list)
    compounds: list[CompoundGraph] = field(default_factory=list)
    edges: list[GraphEdge] = field(default_factory=list)

    def to_raw(self) -> dict:
        """Flatten the typed hierarchy into the raw dict shape."""
        nodes: list[dict] = []
        edges: list[dict] = []
        seen_qns: set[str] = set()

        def _add_node(model) -> None:
            d = dict(model.__properties__)
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
```

- [ ] **Step 2: Verify imports work**

```bash
cd /Users/danielnewman/dev/codegraph && .venv/bin/python -c "from codegraph.graph import CompoundGraph, NamespaceGraph, OntologyGraph, GraphEdge; print('All graph imports OK')"
```
Expected: `All graph imports OK`

- [ ] **Step 3: Commit**

```bash
git add src/codegraph/graph/__init__.py
git commit -m "refactor: update graph/ type annotations for atomized models"
```

---

### Task 13: Update public API exports (__init__.py)

**Files:**
- Modify: `src/codegraph/__init__.py`

- [ ] **Step 1: Rewrite __init__.py**

```python
"""Codegraph — shared Neo4j codebase graph data model.

Provides atomized neomodel Node models (Class, Interface, Enum, Union, Module,
Method, Attribute, EnumValue, Function, Define, Namespace, File, Parameter),
graph containers (CompoundGraph, NamespaceGraph, OntologyGraph, GraphEdge),
and constants (kinds, layers, predicates, schema DDL, language specializations).
"""

from codegraph.config import NEO4J_PASSWORD, NEO4J_URI, NEO4J_USER
from codegraph.constants import (
    COMPOUND_KINDS,
    CONSTRAINTS_AND_INDEXES,
    DEFAULT_PREDICATES,
    LANGUAGE_SPECIALIZATIONS,
    LAYERS,
    MEMBER_KINDS,
    NAMESPACE_KINDS,
    NODE_KIND_KEYS,
    NODE_KINDS,
    PREDICATES,
    PREDICATE_TO_REL_TYPE,
    SOURCE_TYPE_KEYS,
    SOURCE_TYPES,
    SUPPORTED_LANGUAGES,
    TYPE_KINDS,
    UNCLASSIFIED_KINDS,
    VALUE_KINDS,
    VISIBILITY_CHOICES,
    valid_specializations,
)
from codegraph.diagram import ClassDiagram
from codegraph.graph import CompoundGraph, GraphEdge, NamespaceGraph, OntologyGraph
from codegraph.models import (
    ClassNode,
    InterfaceNode,
    EnumNode,
    UnionNode,
    ModuleNode,
    MethodNode,
    AttributeNode,
    EnumValueNode,
    FunctionNode,
    DefineNode,
    NamespaceNode,
    FileNode,
    ParameterNode,
)

__all__ = [
    # Nodes (neomodel, atomized)
    "ClassNode",
    "InterfaceNode",
    "EnumNode",
    "UnionNode",
    "ModuleNode",
    "MethodNode",
    "AttributeNode",
    "EnumValueNode",
    "FunctionNode",
    "DefineNode",
    "NamespaceNode",
    "FileNode",
    "ParameterNode",
    # ClassDiagram
    "ClassDiagram",
    # Graph containers
    "CompoundGraph",
    "GraphEdge",
    "NamespaceGraph",
    "OntologyGraph",
    # Config
    "NEO4J_URI",
    "NEO4J_USER",
    "NEO4J_PASSWORD",
    # Constants
    "COMPOUND_KINDS",
    "CONSTRAINTS_AND_INDEXES",
    "DEFAULT_PREDICATES",
    "LANGUAGE_SPECIALIZATIONS",
    "LAYERS",
    "MEMBER_KINDS",
    "NAMESPACE_KINDS",
    "NODE_KIND_KEYS",
    "NODE_KINDS",
    "PREDICATES",
    "PREDICATE_TO_REL_TYPE",
    "SOURCE_TYPE_KEYS",
    "SOURCE_TYPES",
    "SUPPORTED_LANGUAGES",
    "TYPE_KINDS",
    "UNCLASSIFIED_KINDS",
    "VALUE_KINDS",
    "VISIBILITY_CHOICES",
    "valid_specializations",
]
```

- [ ] **Step 2: Verify all imports work**

```bash
cd /Users/danielnewman/dev/codegraph && .venv/bin/python -c "
from codegraph import (
    ClassNode, InterfaceNode, EnumNode, UnionNode, ModuleNode,
    MethodNode, AttributeNode, EnumValueNode, FunctionNode, DefineNode,
    NamespaceNode, FileNode, ParameterNode,
    ClassDiagram, CompoundGraph, GraphEdge, NamespaceGraph, OntologyGraph,
    NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD,
    PREDICATES, COMPOUND_KINDS,
)
print('All public API imports OK')
"
```
Expected: `All public API imports OK`

- [ ] **Step 3: Commit**

```bash
git add src/codegraph/__init__.py
git commit -m "refactor: update public API exports for atomized models"
```

---

### Task 14: Delete old test files and verify full suite passes

**Files:**
- Delete: `tests/test_designs_compound.py`
- Delete: `tests/test_designs_edges.py`
- Delete: `tests/test_designs_member.py`
- Delete: `tests/test_designs_namespace.py`
- Delete: `tests/test_repositories.py`
- Delete: `tests/test_codegraph_edge_description.py`
- Delete: `tests/test_edges.py`
- Modify: `tests/test_public_api.py` (update removed exports)
- Modify: `tests/conftest.py` (if it references old models)

- [ ] **Step 1: Delete old test files**

```bash
cd /Users/danielnewman/dev/codegraph
git rm tests/test_designs_compound.py tests/test_designs_edges.py \
       tests/test_designs_member.py tests/test_designs_namespace.py \
       tests/test_repositories.py tests/test_codegraph_edge_description.py \
       tests/test_edges.py
```

- [ ] **Step 2: Check conftest.py for old model references**

```bash
grep -n "CompoundNode\|MemberNode\|designs\|CodebaseEdge" tests/conftest.py || echo "No old references"
```

If references found, update to import atomized models instead.

- [ ] **Step 3: Update test_public_api.py**

Replace references to removed exports:

```python
"""Test public API surface."""
import codegraph


def test_public_api_imports():
    """Verify key symbols are importable from codegraph."""
    assert codegraph.ClassNode is not None
    assert codegraph.InterfaceNode is not None
    assert codegraph.EnumNode is not None
    assert codegraph.MethodNode is not None
    assert codegraph.AttributeNode is not None
    assert codegraph.ClassDiagram is not None
    assert codegraph.PREDICATES is not None
    assert codegraph.CompoundGraph is not None
```

- [ ] **Step 4: Run full test suite**

```bash
cd /Users/danielnewman/dev/codegraph && .venv/bin/python -m pytest tests/ -v
```
Expected: All tests PASS. Any failures investigated and fixed.

- [ ] **Step 5: Commit**

```bash
git add tests/
git commit -m "test: delete old tests, update test_public_api for atomized models"
```

---

### Task 15: Run full test suite and final verification

- [ ] **Step 1: Run all tests**

```bash
cd /Users/danielnewman/dev/codegraph && .venv/bin/python -m pytest tests/ -v
```

- [ ] **Step 2: Verify no dangling imports of deleted modules**

```bash
cd /Users/danielnewman/dev/codegraph && grep -r "from codegraph.designs\|from codegraph.repositories\|CodebaseEdge\|CompoundNode\|MemberNode" src/ tests/ || echo "No stale references found"
```

- [ ] **Step 3: Commit any final fixes**

```bash
git add -A
git commit -m "chore: final cleanup and import verification"
```
