# Neomodel Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace custom Neo4j driver management and Pydantic node models with neomodel OGM, keeping the Pydantic design layer intact.

**Architecture:** Node models become neomodel `StructuredNode` subclasses with relationship descriptors. A new repository layer bridges the Pydantic design layer to neomodel persistence. `ClassDiagram.to_neo4j()` persists internally via repositories instead of returning raw lists.

**Tech Stack:** Python 3.12, neomodel>=5.0, neo4j (driver), pydantic>=2.0, pytest

---

## File Structure

**Create:**
- `src/codegraph/config.py` — neomodel connection setup
- `src/codegraph/models/__init__.py` — re-exports
- `src/codegraph/models/compound.py` — CompoundNode (neomodel)
- `src/codegraph/models/member.py` — MemberNode (neomodel)
- `src/codegraph/models/namespace.py` — NamespaceNode (neomodel)
- `src/codegraph/models/file.py` — FileNode (neomodel)
- `src/codegraph/models/parameter.py` — ParameterNode (neomodel)
- `src/codegraph/repositories/__init__.py` — re-exports
- `src/codegraph/repositories/compound.py` — CompoundRepository
- `src/codegraph/repositories/member.py` — MemberRepository
- `src/codegraph/repositories/namespace.py` — NamespaceRepository
- `src/codegraph/repositories/file.py` — FileRepository
- `src/codegraph/repositories/parameter.py` — ParameterRepository
- `tests/test_models.py` — unit tests for neomodel models
- `tests/test_repositories.py` — unit tests for repositories
- `tests/conftest.py` — neomodel test connection fixture

**Modify:**
- `pyproject.toml` — add neomodel dependency
- `src/codegraph/__init__.py` — update exports
- `src/codegraph/designs/__init__.py` — rewrite to_neo4j()/from_neo4j()
- `src/codegraph/graph/__init__.py` — update imports
- `tests/test_class_diagram_neo4j.py` — update imports, add persistence test
- `tests/test_public_api.py` — update imports

**Delete:**
- `src/codegraph/nodes/__init__.py`
- `src/codegraph/nodes/compound_node.py`
- `src/codegraph/nodes/member_node.py`
- `src/codegraph/nodes/namespace_node.py`
- `src/codegraph/nodes/file_node.py`
- `src/codegraph/nodes/parameter_node.py`
- `src/codegraph/neo4j/connection.py`
- `src/codegraph/neo4j/__init__.py`
- `tests/test_nodes.py` (replaced by test_models.py + test_repositories.py)

---

### Task 1: Add neomodel dependency and create config

**Files:**
- Modify: `pyproject.toml`
- Create: `src/codegraph/config.py`

- [ ] **Step 1: Add neomodel to pyproject.toml**

In `pyproject.toml`, add `"neomodel>=5.0"` to the `dependencies` list:

```toml
dependencies = [
    "pydantic>=2.0",
    "neo4j",
    "neomodel>=5.0",
]
```

- [ ] **Step 2: Install neomodel**

```bash
cd /Users/danielnewman/dev/codegraph && .venv/bin/pip install neomodel>=5.0
```

- [ ] **Step 3: Create config.py**

Create `src/codegraph/config.py`:

```python
"""Neomodel connection configuration.

Set ``config.DATABASE_URL`` from environment variables before any
neomodel model class is imported. Import this module first.
"""

import os
from neomodel import config

NEO4J_URI = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.environ.get("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD", "")

# neomodel expects "bolt://user:password@host:port"
_bolt_host = NEO4J_URI.replace("bolt://", "")
config.DATABASE_URL = f"bolt://{NEO4J_USER}:{NEO4J_PASSWORD}@{_bolt_host}"
```

- [ ] **Step 4: Verify config imports**

```bash
cd /Users/danielnewman/dev/codegraph && .venv/bin/python -c "from codegraph.config import NEO4J_URI, NEO4J_USER; print('OK:', NEO4J_URI)"
```

Expected: `OK: bolt://localhost:7687` (or whatever NEO4J_URI env var is set to)

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml src/codegraph/config.py
git commit -m "feat: add neomodel dependency and connection config"
```

---

### Task 2: Create neomodel CompoundNode model

**Files:**
- Create: `src/codegraph/models/__init__.py`
- Create: `src/codegraph/models/compound.py`

- [ ] **Step 1: Create models/__init__.py stub**

```python
"""Neomodel node models for the codebase graph."""
```

- [ ] **Step 2: Create compound.py model**

`src/codegraph/models/compound.py`:

```python
"""Compound node model (:Compound label in Neo4j)."""

from neomodel import (
    StructuredNode, StringProperty, IntegerProperty, BooleanProperty,
    ArrayProperty, UniqueIdProperty, RelationshipTo, RelationshipFrom,
)


class CompoundNode(StructuredNode):
    """A compound entity — class, struct, interface, enum, etc."""

    qualified_name = UniqueIdProperty()
    name = StringProperty(default="")
    kind = StringProperty(required=True)
    layer = StringProperty(default="design")
    component_id = IntegerProperty()
    refid = StringProperty(default="")
    brief_description = StringProperty(default="")
    detailed_description = StringProperty(default="")
    base_classes = ArrayProperty(StringProperty(), default=[])
    file_path = StringProperty(default="")
    line_number = IntegerProperty()
    source = StringProperty(default="")
    is_final = BooleanProperty(default=False)
    is_abstract = BooleanProperty(default=False)

    # Relationships
    members = RelationshipTo('codegraph.models.member.MemberNode', 'COMPOSES')
    parent_namespace = RelationshipFrom('codegraph.models.namespace.NamespaceNode', 'COMPOSES')
    base = RelationshipTo('CompoundNode', 'GENERALIZES')
    derived = RelationshipFrom('CompoundNode', 'GENERALIZES')
```

- [ ] **Step 3: Verify the model class can be defined (no DB needed for class def)**

```bash
cd /Users/danielnewman/dev/codegraph && .venv/bin/python -c "
import os; os.environ['NEO4J_PASSWORD'] = 'skip'
from codegraph.config import config
from codegraph.models.compound import CompoundNode
print('CompoundNode defined OK, fields:', [p for p in dir(CompoundNode) if not p.startswith('_')])
"
```

Expected: `CompoundNode defined OK, fields: [...]`

- [ ] **Step 4: Commit**

```bash
git add src/codegraph/models/
git commit -m "feat: add neomodel CompoundNode model"
```

---

### Task 3: Create neomodel MemberNode, NamespaceNode, FileNode, ParameterNode

**Files:**
- Create: `src/codegraph/models/member.py`
- Create: `src/codegraph/models/namespace.py`
- Create: `src/codegraph/models/file.py`
- Create: `src/codegraph/models/parameter.py`

- [ ] **Step 1: Create member.py**

```python
"""Member node model (:Member label in Neo4j)."""

from neomodel import (
    StructuredNode, StringProperty, IntegerProperty, BooleanProperty,
    UniqueIdProperty, RelationshipFrom,
)


class MemberNode(StructuredNode):
    """A member entity — method, variable, define, enumvalue, function."""

    qualified_name = UniqueIdProperty()
    name = StringProperty(default="")
    kind = StringProperty(required=True)
    layer = StringProperty(default="design")
    component_id = IntegerProperty()
    refid = StringProperty(default="")
    compound_refid = StringProperty(default="")
    brief_description = StringProperty(default="")
    detailed_description = StringProperty(default="")
    type_signature = StringProperty(default="")
    definition = StringProperty(default="")
    argsstring = StringProperty(default="")
    file_path = StringProperty(default="")
    line_number = IntegerProperty()
    source = StringProperty(default="")
    protection = StringProperty(default="")
    is_static = BooleanProperty(default=False)
    is_const = BooleanProperty(default=False)
    is_constexpr = BooleanProperty(default=False)
    is_virtual = BooleanProperty(default=False)
    is_inline = BooleanProperty(default=False)
    is_explicit = BooleanProperty(default=False)

    # Relationships
    parent_compound = RelationshipFrom('codegraph.models.compound.CompoundNode', 'COMPOSES')
```

- [ ] **Step 2: Create namespace.py**

```python
"""Namespace node model (:Namespace label in Neo4j)."""

from neomodel import (
    StructuredNode, StringProperty, IntegerProperty, UniqueIdProperty,
    RelationshipTo,
)


class NamespaceNode(StructuredNode):
    """A namespace entity — namespace, package, or module."""

    qualified_name = UniqueIdProperty()
    name = StringProperty(default="")
    kind = StringProperty(default="namespace")
    layer = StringProperty(default="design")
    component_id = IntegerProperty()
    refid = StringProperty(default="")
    description = StringProperty(default="")
    source = StringProperty(default="")

    # Relationships
    compounds = RelationshipTo('codegraph.models.compound.CompoundNode', 'COMPOSES')
```

- [ ] **Step 3: Create file.py**

```python
"""File node model (:File label in Neo4j)."""

from neomodel import StructuredNode, StringProperty, UniqueIdProperty


class FileNode(StructuredNode):
    """A source file in the codebase."""

    refid = UniqueIdProperty()
    name = StringProperty(default="")
    path = StringProperty(default="")
    language = StringProperty(default="")
    source = StringProperty(default="")
```

- [ ] **Step 4: Create parameter.py**

```python
"""Parameter node model (:Parameter label in Neo4j)."""

from neomodel import StructuredNode, StringProperty, IntegerProperty


class ParameterNode(StructuredNode):
    """A function/method parameter."""

    # No UniqueIdProperty — parameters don't have a natural single key.
    # Use a composite lookup (position + member_refid) in the repository.
    position = IntegerProperty(required=True)
    name = StringProperty(required=True)
    type = StringProperty(default="")
    default_value = StringProperty(default="")
    member_refid = StringProperty(default="")
```

- [ ] **Step 5: Update models/__init__.py exports**

```python
"""Neomodel node models for the codebase graph."""

from codegraph.models.compound import CompoundNode
from codegraph.models.member import MemberNode
from codegraph.models.namespace import NamespaceNode
from codegraph.models.file import FileNode
from codegraph.models.parameter import ParameterNode

__all__ = [
    "CompoundNode",
    "MemberNode",
    "NamespaceNode",
    "FileNode",
    "ParameterNode",
]
```

- [ ] **Step 6: Verify all models import**

```bash
cd /Users/danielnewman/dev/codegraph && .venv/bin/python -c "
import os; os.environ['NEO4J_PASSWORD'] = 'skip'
from codegraph.config import config
from codegraph.models import CompoundNode, MemberNode, NamespaceNode, FileNode, ParameterNode
print('All models imported OK')
"
```

Expected: `All models imported OK`

- [ ] **Step 7: Commit**

```bash
git add src/codegraph/models/
git commit -m "feat: add neomodel MemberNode, NamespaceNode, FileNode, ParameterNode models"
```

---

### Task 4: Create test fixture and model tests

**Files:**
- Create: `tests/conftest.py`
- Create: `tests/test_models.py`

- [ ] **Step 1: Create conftest.py with neomodel test setup**

```python
"""Pytest fixtures for neomodel tests.

Requires a running Neo4j instance. Set NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD
environment variables, or defaults to bolt://localhost:7687 with neo4j/neo4j.
"""

import pytest
from neomodel import config, db, install_all_labels


@pytest.fixture(scope="session", autouse=True)
def setup_neomodel():
    """Configure neomodel for the test session and ensure labels exist."""
    import os

    uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
    user = os.environ.get("NEO4J_USER", "neo4j")
    password = os.environ.get("NEO4J_PASSWORD", "neo4j")

    host = uri.replace("bolt://", "")
    config.DATABASE_URL = f"bolt://{user}:{password}@{host}"

    # Install labels (creates constraints/indexes)
    install_all_labels()


@pytest.fixture(autouse=True)
def clear_db():
    """Wipe all nodes and relationships before each test for isolation."""
    db.cypher_query("MATCH (n) DETACH DELETE n")
    yield
```

- [ ] **Step 2: Create test_models.py — CompoundNode tests**

```python
"""Tests for neomodel node models."""
import pytest
from neomodel import DoesNotExist, RequiredProperty

from codegraph.models.compound import CompoundNode
from codegraph.models.member import MemberNode
from codegraph.models.namespace import NamespaceNode
from codegraph.models.file import FileNode
from codegraph.models.parameter import ParameterNode


class TestCompoundNode:
    def test_create_and_save(self):
        c = CompoundNode(qualified_name="calc::Calculator", kind="class")
        c.save()
        retrieved = CompoundNode.nodes.get(qualified_name="calc::Calculator")
        assert retrieved.qualified_name == "calc::Calculator"
        assert retrieved.kind == "class"
        assert retrieved.name == ""
        assert retrieved.layer == "design"
        assert retrieved.is_final is False

    def test_unique_id_enforced(self):
        c1 = CompoundNode(qualified_name="calc::Calc", kind="class").save()
        c2 = CompoundNode(qualified_name="calc::Calc", kind="struct")
        # neomodel UniqueIdProperty uses MERGE; saving with same id updates
        c2.save()
        assert CompoundNode.nodes.filter(qualified_name="calc::Calc").all()[0].kind == "struct"

    def test_kind_required(self):
        with pytest.raises(RequiredProperty):
            CompoundNode().save()

    def test_full_creation(self):
        c = CompoundNode(
            qualified_name="calc::Calculator",
            name="Calculator",
            kind="class",
            layer="as-built",
            refid="classcalc_1_1Calculator",
            brief_description="A simple calculator",
            detailed_description="Performs arithmetic.",
            base_classes=["BaseCalc"],
            file_path="/src/calculator.h",
            line_number=42,
            source="msd",
            is_final=True,
            is_abstract=False,
        ).save()
        retrieved = CompoundNode.nodes.get(qualified_name="calc::Calculator")
        assert retrieved.name == "Calculator"
        assert retrieved.brief_description == "A simple calculator"
        assert retrieved.base_classes == ["BaseCalc"]
        assert retrieved.file_path == "/src/calculator.h"
        assert retrieved.line_number == 42
        assert retrieved.is_final is True

    def test_base_classes_default(self):
        c = CompoundNode(qualified_name="calc::Foo", kind="class").save()
        retrieved = CompoundNode.nodes.get(qualified_name="calc::Foo")
        assert retrieved.base_classes == []
```

- [ ] **Step 3: Run compound tests**

```bash
cd /Users/danielnewman/dev/codegraph && .venv/bin/python -m pytest tests/test_models.py::TestCompoundNode -v
```

Expected: All 4 tests pass (requires running Neo4j)

- [ ] **Step 4: Add MemberNode tests to test_models.py**

```python
class TestMemberNode:
    def test_create_and_save(self):
        m = MemberNode(qualified_name="calc::Calculator::add", kind="method")
        m.save()
        retrieved = MemberNode.nodes.get(qualified_name="calc::Calculator::add")
        assert retrieved.kind == "method"
        assert retrieved.is_static is False

    def test_kind_required(self):
        with pytest.raises(RequiredProperty):
            MemberNode().save()

    def test_full_creation(self):
        m = MemberNode(
            qualified_name="calc::Calculator::add",
            name="add",
            kind="method",
            layer="as-built",
            type_signature="int",
            argsstring="(int a, int b)",
            protection="public",
            is_const=True,
            is_virtual=False,
            is_inline=True,
        ).save()
        retrieved = MemberNode.nodes.get(qualified_name="calc::Calculator::add")
        assert retrieved.type_signature == "int"
        assert retrieved.argsstring == "(int a, int b)"
        assert retrieved.protection == "public"
        assert retrieved.is_const is True
        assert retrieved.is_inline is True

    def test_all_boolean_flags_default_false(self):
        m = MemberNode(qualified_name="calc::Foo::bar", kind="method").save()
        retrieved = MemberNode.nodes.get(qualified_name="calc::Foo::bar")
        assert retrieved.is_static is False
        assert retrieved.is_const is False
        assert retrieved.is_constexpr is False
        assert retrieved.is_virtual is False
        assert retrieved.is_inline is False
        assert retrieved.is_explicit is False
```

- [ ] **Step 5: Add NamespaceNode, FileNode, ParameterNode tests**

```python
class TestNamespaceNode:
    def test_create_and_save(self):
        n = NamespaceNode(qualified_name="std::chrono")
        n.save()
        retrieved = NamespaceNode.nodes.get(qualified_name="std::chrono")
        assert retrieved.kind == "namespace"
        assert retrieved.layer == "design"

    def test_full_creation(self):
        n = NamespaceNode(
            qualified_name="std::chrono",
            name="chrono",
            kind="namespace",
            layer="dependency",
            description="C++ chrono library",
            source="stdlib",
        ).save()
        retrieved = NamespaceNode.nodes.get(qualified_name="std::chrono")
        assert retrieved.name == "chrono"
        assert retrieved.description == "C++ chrono library"


class TestFileNode:
    def test_create_and_save(self):
        f = FileNode(refid="file_abc123")
        f.save()
        retrieved = FileNode.nodes.get(refid="file_abc123")
        assert retrieved.name == ""
        assert retrieved.path == ""

    def test_full_creation(self):
        f = FileNode(
            refid="file_abc123",
            name="main.cpp",
            path="/src/main.cpp",
            language="C++",
            source="msd",
        ).save()
        retrieved = FileNode.nodes.get(refid="file_abc123")
        assert retrieved.name == "main.cpp"
        assert retrieved.path == "/src/main.cpp"


class TestParameterNode:
    def test_create_and_save(self):
        p = ParameterNode(position=0, name="x")
        p.save()
        # Parameters don't have a UniqueIdProperty, so we filter
        results = ParameterNode.nodes.filter(position=0, name="x").all()
        assert len(results) == 1
        assert results[0].type == ""

    def test_full_creation(self):
        p = ParameterNode(
            position=1,
            name="epsilon",
            type="double",
            default_value="1e-6",
            member_refid="method_ref_123",
        ).save()
        results = ParameterNode.nodes.filter(position=1, name="epsilon").all()
        assert len(results) == 1
        assert results[0].type == "double"
        assert results[0].default_value == "1e-6"
        assert results[0].member_refid == "method_ref_123"
```

- [ ] **Step 6: Run full model test suite**

```bash
cd /Users/danielnewman/dev/codegraph && .venv/bin/python -m pytest tests/test_models.py -v
```

Expected: All tests pass

- [ ] **Step 7: Commit**

```bash
git add tests/conftest.py tests/test_models.py
git commit -m "test: add neomodel model tests with DB fixture"
```

---

### Task 5: Create Repository layer

**Files:**
- Create: `src/codegraph/repositories/__init__.py`
- Create: `src/codegraph/repositories/compound.py`
- Create: `src/codegraph/repositories/member.py`
- Create: `src/codegraph/repositories/namespace.py`
- Create: `src/codegraph/repositories/file.py`
- Create: `src/codegraph/repositories/parameter.py`

- [ ] **Step 1: Create repositories/__init__.py**

```python
"""Repository layer — bridges design Pydantic models to neomodel persistence."""

from codegraph.repositories.compound import CompoundRepository
from codegraph.repositories.member import MemberRepository
from codegraph.repositories.namespace import NamespaceRepository
from codegraph.repositories.file import FileRepository
from codegraph.repositories.parameter import ParameterRepository

__all__ = [
    "CompoundRepository",
    "MemberRepository",
    "NamespaceRepository",
    "FileRepository",
    "ParameterRepository",
]
```

- [ ] **Step 2: Create compound.py repository**

```python
"""Repository for CompoundNode persistence."""

from codegraph.models.compound import CompoundNode
from codegraph.models.member import MemberNode


class CompoundRepository:
    """CRUD operations for :class:`CompoundNode` backed by neomodel."""

    def save(self, node: CompoundNode) -> CompoundNode:
        """Persist a compound. Uses MERGE semantics via UniqueIdProperty."""
        return node.save()

    def get(self, qualified_name: str) -> CompoundNode | None:
        """Look up by qualified_name. Returns None if not found."""
        return CompoundNode.nodes.get_or_none(qualified_name=qualified_name)

    def find_by_layer(self, layer: str) -> list[CompoundNode]:
        """Return all compounds in a given layer."""
        return list(CompoundNode.nodes.filter(layer=layer))

    def bulk_save(self, nodes: list[CompoundNode]) -> list[CompoundNode]:
        """Persist multiple compounds."""
        return [node.save() for node in nodes]

    def delete_all_design_layer(self) -> int:
        """Remove all design-layer compounds. Returns count deleted."""
        nodes = list(CompoundNode.nodes.filter(layer="design"))
        count = len(nodes)
        for n in nodes:
            n.delete()
        return count

    def delete_by_qualified_name(self, qualified_name: str) -> bool:
        """Delete a single compound by qualified_name. Returns True if found."""
        node = CompoundNode.nodes.get_or_none(qualified_name=qualified_name)
        if node:
            node.delete()
            return True
        return False

    def connect_member(self, compound_qn: str, member_qn: str) -> None:
        """Create a COMPOSES edge from compound to member."""
        c = CompoundNode.nodes.get(qualified_name=compound_qn)
        m = MemberNode.nodes.get(qualified_name=member_qn)
        c.members.connect(m)

    def connect_base(self, child_qn: str, parent_qn: str) -> None:
        """Create a GENERALIZES edge from child to parent compound."""
        child = CompoundNode.nodes.get(qualified_name=child_qn)
        parent = CompoundNode.nodes.get(qualified_name=parent_qn)
        child.base.connect(parent)

    def get_members(self, qualified_name: str) -> list[MemberNode]:
        """Return all members owned by this compound via COMPOSES."""
        c = CompoundNode.nodes.get(qualified_name=qualified_name)
        return list(c.members.all())
```

- [ ] **Step 3: Create member.py repository**

```python
"""Repository for MemberNode persistence."""

from codegraph.models.member import MemberNode


class MemberRepository:
    """CRUD operations for :class:`MemberNode` backed by neomodel."""

    def save(self, node: MemberNode) -> MemberNode:
        return node.save()

    def get(self, qualified_name: str) -> MemberNode | None:
        return MemberNode.nodes.get_or_none(qualified_name=qualified_name)

    def find_by_layer(self, layer: str) -> list[MemberNode]:
        return list(MemberNode.nodes.filter(layer=layer))

    def bulk_save(self, nodes: list[MemberNode]) -> list[MemberNode]:
        return [node.save() for node in nodes]

    def delete_all_design_layer(self) -> int:
        nodes = list(MemberNode.nodes.filter(layer="design"))
        count = len(nodes)
        for n in nodes:
            n.delete()
        return count

    def delete_by_qualified_name(self, qualified_name: str) -> bool:
        node = MemberNode.nodes.get_or_none(qualified_name=qualified_name)
        if node:
            node.delete()
            return True
        return False
```

- [ ] **Step 4: Create namespace.py repository**

```python
"""Repository for NamespaceNode persistence."""

from codegraph.models.namespace import NamespaceNode
from codegraph.models.compound import CompoundNode


class NamespaceRepository:
    """CRUD operations for :class:`NamespaceNode` backed by neomodel."""

    def save(self, node: NamespaceNode) -> NamespaceNode:
        return node.save()

    def get(self, qualified_name: str) -> NamespaceNode | None:
        return NamespaceNode.nodes.get_or_none(qualified_name=qualified_name)

    def find_by_layer(self, layer: str) -> list[NamespaceNode]:
        return list(NamespaceNode.nodes.filter(layer=layer))

    def bulk_save(self, nodes: list[NamespaceNode]) -> list[NamespaceNode]:
        return [node.save() for node in nodes]

    def connect_compound(self, namespace_qn: str, compound_qn: str) -> None:
        """Create a COMPOSES edge from namespace to compound."""
        ns = NamespaceNode.nodes.get(qualified_name=namespace_qn)
        c = CompoundNode.nodes.get(qualified_name=compound_qn)
        ns.compounds.connect(c)
```

- [ ] **Step 5: Create file.py repository**

```python
"""Repository for FileNode persistence."""

from codegraph.models.file import FileNode


class FileRepository:
    """CRUD operations for :class:`FileNode` backed by neomodel."""

    def save(self, node: FileNode) -> FileNode:
        return node.save()

    def get(self, refid: str) -> FileNode | None:
        return FileNode.nodes.get_or_none(refid=refid)

    def bulk_save(self, nodes: list[FileNode]) -> list[FileNode]:
        return [node.save() for node in nodes]
```

- [ ] **Step 6: Create parameter.py repository**

```python
"""Repository for ParameterNode persistence."""

from codegraph.models.parameter import ParameterNode


class ParameterRepository:
    """CRUD operations for :class:`ParameterNode` backed by neomodel."""

    def save(self, node: ParameterNode) -> ParameterNode:
        return node.save()

    def find_by_member_refid(self, member_refid: str) -> list[ParameterNode]:
        return list(ParameterNode.nodes.filter(member_refid=member_refid))

    def bulk_save(self, nodes: list[ParameterNode]) -> list[ParameterNode]:
        return [node.save() for node in nodes]
```

- [ ] **Step 7: Commit**

```bash
git add src/codegraph/repositories/
git commit -m "feat: add repository layer for neomodel CRUD operations"
```

---

### Task 6: Create repository tests

**Files:**
- Create: `tests/test_repositories.py`

- [ ] **Step 1: Write repository tests**

```python
"""Tests for the repository layer."""
from codegraph.models.compound import CompoundNode
from codegraph.models.member import MemberNode
from codegraph.models.namespace import NamespaceNode
from codegraph.models.file import FileNode
from codegraph.models.parameter import ParameterNode
from codegraph.repositories.compound import CompoundRepository
from codegraph.repositories.member import MemberRepository
from codegraph.repositories.namespace import NamespaceRepository
from codegraph.repositories.file import FileRepository
from codegraph.repositories.parameter import ParameterRepository


class TestCompoundRepository:
    def test_save_and_get(self):
        repo = CompoundRepository()
        c = CompoundNode(qualified_name="calc::Calc", kind="class")
        repo.save(c)
        retrieved = repo.get("calc::Calc")
        assert retrieved is not None
        assert retrieved.kind == "class"

    def test_get_returns_none_for_missing(self):
        repo = CompoundRepository()
        assert repo.get("nonexistent::Foo") is None

    def test_find_by_layer(self):
        repo = CompoundRepository()
        CompoundNode(qualified_name="calc::A", kind="class", layer="design").save()
        CompoundNode(qualified_name="calc::B", kind="class", layer="as-built").save()
        CompoundNode(qualified_name="calc::C", kind="class", layer="design").save()

        design = repo.find_by_layer("design")
        assert len(design) == 2

    def test_bulk_save(self):
        repo = CompoundRepository()
        nodes = [
            CompoundNode(qualified_name="calc::X", kind="class"),
            CompoundNode(qualified_name="calc::Y", kind="struct"),
        ]
        saved = repo.bulk_save(nodes)
        assert len(saved) == 2
        assert repo.get("calc::X") is not None
        assert repo.get("calc::Y") is not None

    def test_delete_all_design_layer(self):
        repo = CompoundRepository()
        CompoundNode(qualified_name="calc::D", kind="class", layer="design").save()
        CompoundNode(qualified_name="calc::E", kind="class", layer="as-built").save()
        count = repo.delete_all_design_layer()
        assert count == 1
        assert repo.get("calc::D") is None
        assert repo.get("calc::E") is not None

    def test_connect_member(self):
        repo = CompoundRepository()
        member_repo = MemberRepository()
        c = CompoundNode(qualified_name="calc::Calc", kind="class").save()
        m = MemberNode(qualified_name="calc::Calc::add", kind="method").save()
        repo.connect_member("calc::Calc", "calc::Calc::add")
        members = repo.get_members("calc::Calc")
        assert len(members) == 1
        assert members[0].qualified_name == "calc::Calc::add"

    def test_connect_base(self):
        repo = CompoundRepository()
        child = CompoundNode(qualified_name="calc::Child", kind="class").save()
        parent = CompoundNode(qualified_name="calc::Parent", kind="class").save()
        repo.connect_base("calc::Child", "calc::Parent")
        # Verify via relationship traversal
        retrieved = repo.get("calc::Child")
        bases = list(retrieved.base.all())
        assert len(bases) == 1
        assert bases[0].qualified_name == "calc::Parent"


class TestMemberRepository:
    def test_save_and_get(self):
        repo = MemberRepository()
        m = MemberNode(qualified_name="calc::Foo::bar", kind="method")
        repo.save(m)
        retrieved = repo.get("calc::Foo::bar")
        assert retrieved is not None
        assert retrieved.kind == "method"

    def test_bulk_save(self):
        repo = MemberRepository()
        nodes = [
            MemberNode(qualified_name="calc::Foo::x", kind="variable"),
            MemberNode(qualified_name="calc::Foo::y", kind="variable"),
        ]
        repo.bulk_save(nodes)
        assert repo.get("calc::Foo::x") is not None
        assert repo.get("calc::Foo::y") is not None


class TestNamespaceRepository:
    def test_save_and_get(self):
        repo = NamespaceRepository()
        n = NamespaceNode(qualified_name="std")
        repo.save(n)
        retrieved = repo.get("std")
        assert retrieved is not None

    def test_connect_compound(self):
        repo = NamespaceRepository()
        ns = NamespaceNode(qualified_name="calc").save()
        c = CompoundNode(qualified_name="calc::Calc", kind="class").save()
        repo.connect_compound("calc", "calc::Calc")
        # Verify traversal
        retrieved = repo.get("calc")
        compounds = list(retrieved.compounds.all())
        assert len(compounds) == 1
        assert compounds[0].qualified_name == "calc::Calc"


class TestFileRepository:
    def test_save_and_get(self):
        repo = FileRepository()
        f = FileNode(refid="file_123")
        repo.save(f)
        retrieved = repo.get("file_123")
        assert retrieved is not None


class TestParameterRepository:
    def test_save_and_find(self):
        repo = ParameterRepository()
        p = ParameterNode(position=0, name="x", member_refid="ref_abc").save()
        results = repo.find_by_member_refid("ref_abc")
        assert len(results) == 1
        assert results[0].name == "x"
```

- [ ] **Step 2: Run repository tests**

```bash
cd /Users/danielnewman/dev/codegraph && .venv/bin/python -m pytest tests/test_repositories.py -v
```

Expected: All tests pass

- [ ] **Step 3: Commit**

```bash
git add tests/test_repositories.py
git commit -m "test: add repository layer tests"
```

---

### Task 7: Update ClassDiagram.to_neo4j() and from_neo4j()

**Files:**
- Modify: `src/codegraph/designs/__init__.py`
- Modify: `tests/test_class_diagram_neo4j.py`

- [ ] **Step 1: Rewrite to_neo4j() to use internal save**

In `src/codegraph/designs/__init__.py`, replace the `to_neo4j` method. The old method returns `(compounds, members, edges)` lists. The new method persists directly:

```python
    def to_neo4j(self) -> None:
        """Persist the entire diagram to Neo4j via the repository layer.

        Creates CompoundNode and MemberNode neomodel instances, saves them,
        and wires up COMPOSES relationships. Associations are converted to
        CodebaseEdge instances and saved via the edge model (if neomodel-backed)
        or stored as Relationship edges via the compound repository.
        """
        from codegraph.models.compound import CompoundNode as NeoCompound
        from codegraph.models.member import MemberNode as NeoMember
        from codegraph.repositories.compound import CompoundRepository
        from codegraph.repositories.member import MemberRepository

        compound_repo = CompoundRepository()
        member_repo = MemberRepository()

        for cls in self.classes:
            compound = NeoCompound(
                qualified_name=cls.qualified_name,
                name=cls.name,
                kind=cls.kind,
                layer=cls.layer or "design",
                component_id=cls.component_id,
                brief_description=cls.description,
                file_path=cls.file_path or "",
                line_number=cls.line_number,
                is_final=cls.is_final,
                is_abstract=cls.is_abstract,
            )
            compound_repo.save(compound)

            for attr in cls.attributes:
                member = NeoMember(
                    qualified_name=attr.qualified_name,
                    name=attr.name,
                    kind="variable",
                    layer=attr.layer or "design",
                    component_id=attr.component_id,
                    brief_description=attr.description,
                    type_signature=attr.type_signature or "",
                )
                member_repo.save(member)
                compound_repo.connect_member(compound.qualified_name, member.qualified_name)

            for method in cls.methods:
                member = NeoMember(
                    qualified_name=method.qualified_name,
                    name=method.name,
                    kind="method",
                    layer=method.layer or "design",
                    component_id=method.component_id,
                    brief_description=method.description,
                    type_signature=method.type_signature or "",
                    argsstring=method.argsstring or "",
                    protection=method.visibility or "",
                    is_virtual=method.is_virtual,
                    is_static=method.is_static,
                    is_const=method.is_const,
                )
                member_repo.save(member)
                compound_repo.connect_member(compound.qualified_name, member.qualified_name)

        for iface in self.interfaces:
            compound = NeoCompound(
                qualified_name=iface.qualified_name,
                name=iface.name,
                kind=iface.kind,
                layer="design",
                component_id=iface.component_id,
                brief_description=iface.description,
                is_abstract=iface.is_abstract,
            )
            compound_repo.save(compound)

            for method in iface.methods:
                member = NeoMember(
                    qualified_name=method.qualified_name,
                    name=method.name,
                    kind="method",
                    layer="design",
                    component_id=method.component_id,
                    brief_description=method.description,
                    type_signature=method.type_signature or "",
                    argsstring=method.argsstring or "",
                    protection=method.visibility or "",
                    is_virtual=True,
                )
                member_repo.save(member)
                compound_repo.connect_member(compound.qualified_name, member.qualified_name)

        for enum in self.enums:
            compound = NeoCompound(
                qualified_name=enum.qualified_name,
                name=enum.name,
                kind=enum.kind,
                layer="design",
                component_id=enum.component_id,
                brief_description=enum.description,
            )
            compound_repo.save(compound)

            for val in enum.values:
                member = NeoMember(
                    qualified_name=val.qualified_name,
                    name=val.name,
                    kind="enumvalue",
                    layer="design",
                )
                member_repo.save(member)
                compound_repo.connect_member(compound.qualified_name, member.qualified_name)

        # Associations: create COMPOSES / GENERALIZES / AGGREGATES edges
        for assoc in self.associations:
            predicate = assoc.predicate.upper()
            if predicate == "GENERALIZES":
                compound_repo.connect_base(assoc.subject, assoc.object)
            # Additional predicate types can be wired up as needed
```

**Important:** The `to_neo4j` method signature changes from returning `tuple[list, list, list]` to returning `None`. Every caller must be updated.

- [ ] **Step 2: Rewrite from_neo4j() to read through repositories**

In `src/codegraph/designs/__init__.py`, replace the `from_neo4j` method:

```python
    @classmethod
    def from_neo4j(cls, compounds: list[CompoundNode] | None = None,
                   members: list[MemberNode] | None = None,
                   edges: list[CodebaseEdge] | None = None) -> ClassDiagram:
        """Reconstruct a class diagram from Neo4j.

        When called with specific lists, uses those (backward compat).
        When called with no arguments, reads all design-layer entities
        from Neo4j via the repository layer.
        """
        from codegraph.edges import CodebaseEdge
        from codegraph.repositories.compound import CompoundRepository
        from codegraph.repositories.member import MemberRepository

        from codegraph.models.compound import CompoundNode as NeoCompound
        from codegraph.models.member import MemberNode as NeoMember

        if compounds is None:
            compound_repo = CompoundRepository()
            compounds = compound_repo.find_by_layer("design")
        if members is None:
            member_repo = MemberRepository()
            members = member_repo.find_by_layer("design")
        if edges is None:
            edges = []

        _CLASS_KINDS = {"class", "struct", "template_class"}
        _INTERFACE_KINDS = {"interface", "abstract_class"}
        _ENUM_KINDS = {"enum", "enum_class"}

        # Build member index: parent_qn → [MemberNode]
        member_index: dict[str, list] = {}
        for m in members:
            parent = _extract_parent_qn(m.qualified_name)
            member_index.setdefault(parent, []).append(m)

        classes: list[ClassNode] = []
        interfaces: list[InterfaceNode] = []
        enums: list[EnumNode] = []
        module_names: list[str] = []

        for c in compounds:
            owned = member_index.get(c.qualified_name, [])
            module = _extract_module(c.qualified_name)

            if c.kind in _CLASS_KINDS:
                attrs = []; meths = []
                for m in owned:
                    if m.kind == "variable":
                        attrs.append(AttributeNode(
                            name=m.name, qualified_name=m.qualified_name,
                            kind="attribute", description=m.brief_description,
                            visibility=m.protection or "", type_signature=m.type_signature,
                            owner=c.qualified_name,
                            component_id=m.component_id, layer=m.layer))
                    elif m.kind == "method":
                        meths.append(MethodNode(
                            name=m.name, qualified_name=m.qualified_name,
                            kind="method", description=m.brief_description,
                            visibility=m.protection or "", type_signature=m.type_signature,
                            argsstring=m.argsstring or "", owner=c.qualified_name,
                            component_id=m.component_id, layer=m.layer,
                            is_virtual=m.is_virtual, is_static=m.is_static,
                            is_const=m.is_const))
                classes.append(ClassNode(
                    name=c.name, qualified_name=c.qualified_name,
                    kind="class", layer=c.layer, description=c.brief_description,
                    module=module, component_id=c.component_id,
                    file_path=c.file_path, line_number=c.line_number,
                    is_abstract=c.is_abstract, is_final=c.is_final,
                    attributes=attrs, methods=meths))
                if module and module not in module_names:
                    module_names.append(module)

            elif c.kind in _INTERFACE_KINDS:
                meths = []
                for m in owned:
                    if m.kind == "method":
                        meths.append(MethodNode(
                            name=m.name, qualified_name=m.qualified_name,
                            kind="method", description=m.brief_description,
                            visibility=m.protection or "", type_signature=m.type_signature,
                            argsstring=m.argsstring or "", owner=c.qualified_name,
                            component_id=m.component_id, layer=m.layer,
                            is_virtual=True))
                interfaces.append(InterfaceNode(
                    name=c.name, qualified_name=c.qualified_name,
                    kind="interface", layer=c.layer, description=c.brief_description,
                    is_abstract=c.is_abstract, module=module,
                    component_id=c.component_id, methods=meths))
                if module and module not in module_names:
                    module_names.append(module)

            elif c.kind in _ENUM_KINDS:
                vals = []
                for m in owned:
                    if m.kind == "enumvalue":
                        vals.append(EnumValueNode(
                            name=m.name, qualified_name=m.qualified_name,
                            kind="enum_value", owner=c.qualified_name))
                enums.append(EnumNode(
                    name=c.name, qualified_name=c.qualified_name,
                    kind="enum", layer=c.layer, description=c.brief_description,
                    module=module, component_id=c.component_id, values=vals))
                if module and module not in module_names:
                    module_names.append(module)

        associations = [
            Association(
                subject=e.subject_qualified_name,
                predicate=e.predicate,
                object=e.object_qualified_name,
                mechanism=e.mechanism,
                description=e.description,
            )
            for e in (edges or [])
        ]
        return cls(
            module_names=module_names, classes=classes,
            interfaces=interfaces, enums=enums,
            associations=associations,
        )
```

- [ ] **Step 3: Update test_class_diagram_neo4j.py**

Replace imports and add persistence tests. The existing `test_to_neo4j_roundtrip` and `test_from_neo4j_reconstructs_diagram` must be updated because `to_neo4j()` now returns `None` instead of lists:

```python
def test_to_neo4j_persists_internally():
    """to_neo4j() now saves directly to Neo4j (no return value)."""
    diagram = make_sample_diagram()
    diagram.to_neo4j()  # persists, returns None

    # Read back via from_neo4j() with no args (reads from DB)
    reconstructed = ClassDiagram.from_neo4j()

    assert len(reconstructed.classes) == 1
    assert reconstructed.classes[0].qualified_name == "calc::Calculator"
    assert len(reconstructed.classes[0].attributes) == 1
    assert len(reconstructed.classes[0].methods) == 1
    assert len(reconstructed.interfaces) == 1
    assert len(reconstructed.enums) == 1
```

Update the existing `test_to_neo4j_roundtrip` to read from DB after persist:

```python
def test_to_neo4j_roundtrip():
    """Round-trip: persist to Neo4j, read back via repositories."""
    diagram = make_sample_diagram()
    diagram.to_neo4j()  # persists to DB, returns None

    # Read back all design-layer nodes via repositories
    from codegraph.repositories.compound import CompoundRepository
    from codegraph.repositories.member import MemberRepository
    compounds = CompoundRepository().find_by_layer("design")
    members = MemberRepository().find_by_layer("design")

    assert len(compounds) == 3
    compound_map = {c.qualified_name: c for c in compounds}
    calc = compound_map["calc::Calculator"]
    assert calc.kind == "class"
    assert calc.name == "Calculator"
    assert calc.brief_description == "A simple calculator"

    iface = compound_map["calc::IPrintable"]
    assert iface.kind == "interface"
    assert iface.is_abstract is True

    op = compound_map["calc::Op"]
    assert op.kind == "enum"

    assert len(members) == 5
    member_map = {m.qualified_name: m for m in members}
    count = member_map["calc::Calculator::count"]
    assert count.kind == "variable"
    assert count.type_signature == "int"

    add_method = member_map["calc::Calculator::add"]
    assert add_method.kind == "method"
    assert add_method.type_signature == "int"

    add_enum = member_map["calc::Op::ADD"]
    assert add_enum.kind == "enumvalue"
```

Update `test_from_neo4j_reconstructs_diagram` similarly — persist then read back via `from_neo4j()` with the retrieved nodes:

```python
def test_from_neo4j_reconstructs_diagram():
    """Persist a diagram, then reconstruct it via from_neo4j()."""
    diagram = make_sample_diagram()
    diagram.to_neo4j()

    # Read back via from_neo4j() with no args (reads from DB)
    reconstructed = ClassDiagram.from_neo4j()

    assert len(reconstructed.classes) == 1
    cls = reconstructed.classes[0]
    assert cls.qualified_name == "calc::Calculator"
    assert cls.description == "A simple calculator"
    assert len(cls.attributes) == 1
    assert cls.attributes[0].name == "count"
    assert len(cls.methods) == 1
    assert cls.methods[0].name == "add"

    assert len(reconstructed.interfaces) == 1
    assert reconstructed.interfaces[0].qualified_name == "calc::IPrintable"
    assert len(reconstructed.interfaces[0].methods) == 1

    assert len(reconstructed.enums) == 1
    assert reconstructed.enums[0].qualified_name == "calc::Op"
    assert len(reconstructed.enums[0].values) == 2

    assert len(reconstructed.associations) == 1
    assert reconstructed.associations[0].subject == "calc::Calculator"

    entity = reconstructed.get_entity("calc::Calculator")
    assert entity is not None
    assert entity.qualified_name == "calc::Calculator"
```

- [ ] **Step 4: Run class diagram tests**

```bash
cd /Users/danielnewman/dev/codegraph && .venv/bin/python -m pytest tests/test_class_diagram_neo4j.py -v
```

Expected: All tests pass

- [ ] **Step 5: Commit**

```bash
git add src/codegraph/designs/__init__.py tests/test_class_diagram_neo4j.py
git commit -m "feat: migrate ClassDiagram.to_neo4j/from_neo4j to neomodel repositories"
```

---

### Task 8: Update __init__.py exports and graph module

**Files:**
- Modify: `src/codegraph/__init__.py`
- Modify: `src/codegraph/graph/__init__.py`
- Modify: `tests/test_public_api.py`

- [ ] **Step 1: Update codegraph/__init__.py exports**

Replace the node model imports (from `codegraph.nodes`) with neomodel model imports (from `codegraph.models`), and replace the neo4j connection imports with config imports:

```python
"""Codegraph — shared Neo4j codebase graph data model.

Provides neomodel Node models (File, Namespace, Compound, Member, Parameter),
edge definitions (CodebaseEdge), and constants (kinds, layers, predicates,
schema DDL, language specializations, semantic groupings).
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
from codegraph.edges import CodebaseEdge
from codegraph.graph import CompoundGraph, GraphEdge, NamespaceGraph, OntologyGraph
from codegraph.models import (
    CompoundNode,
    FileNode,
    MemberNode,
    NamespaceNode,
    ParameterNode,
)

__all__ = [
    # Nodes (neomodel)
    "CompoundNode",
    "FileNode",
    "MemberNode",
    "NamespaceNode",
    "ParameterNode",
    # Edges
    "CodebaseEdge",
    "PREDICATES",
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

- [ ] **Step 2: Update graph/__init__.py imports**

Change `from codegraph.nodes import CompoundNode, MemberNode, NamespaceNode` to `from codegraph.models import CompoundNode, MemberNode, NamespaceNode`.

- [ ] **Step 3: Update test_public_api.py**

Change:
```python
from codegraph import FileNode, NamespaceNode, CompoundNode, MemberNode, ParameterNode
```
to import from `codegraph.models` if the public API test still checks these are importable from `codegraph` (they are — `__init__.py` re-exports them).

The test `test_import_nodes` should remain the same since `__init__.py` re-exports all models.

- [ ] **Step 4: Verify full import chain**

```bash
cd /Users/danielnewman/dev/codegraph && .venv/bin/python -c "
import os; os.environ['NEO4J_PASSWORD'] = 'skip'
from codegraph import CompoundNode, MemberNode, NamespaceNode, FileNode, ParameterNode
from codegraph import CodebaseEdge, NEO4J_URI
print('Full public API imports OK')
"
```

Expected: `Full public API imports OK`

- [ ] **Step 5: Commit**

```bash
git add src/codegraph/__init__.py src/codegraph/graph/__init__.py tests/test_public_api.py
git commit -m "feat: update public API exports for neomodel migration"
```

---

### Task 9: Remove old nodes/ and neo4j/ modules

**Files:**
- Delete: `src/codegraph/nodes/` (entire directory)
- Delete: `src/codegraph/neo4j/` (entire directory)
- Delete: `tests/test_nodes.py` (replaced by test_models.py)
- Delete: `tests/test_edges.py` (if it tests pydantic edges that still exist — keep if needed)

- [ ] **Step 1: Remove old directories**

```bash
rm -rf src/codegraph/nodes/ src/codegraph/neo4j/ tests/test_nodes.py
```

Also remove `tests/test_codegraph_edge_description.py` if it imports from the removed modules. Check first:

```bash
grep -r "from codegraph.nodes\|from codegraph.neo4j" tests/
```

If `test_codegraph_edge_description.py` imports from removed modules, delete it too (CodebaseEdge is still in `codegraph.edges`, so it may be fine).

- [ ] **Step 2: Run all remaining tests**

```bash
cd /Users/danielnewman/dev/codegraph && .venv/bin/python -m pytest tests/ -v --ignore=tests/test_constants.py
```

Expected: All tests pass (excluding pre-existing test_constants.py failure)

- [ ] **Step 3: Commit**

```bash
git add -A
git commit -m "refactor: remove old Pydantic node models and neo4j connection module"
```

---

### Task 10: Final verification and cleanup

- [ ] **Step 1: Run the full test suite**

```bash
cd /Users/danielnewman/dev/codegraph && .venv/bin/python -m pytest tests/ -v 2>&1 | tail -30
```

Expected: Only the pre-existing `test_constants.py` failure remains. All other tests pass.

- [ ] **Step 2: Verify design layer still works (LLM serialization)**

```bash
cd /Users/danielnewman/dev/codegraph && .venv/bin/python -c "
from codegraph.designs import ClassDiagram, ClassNode, AttributeNode

cls = ClassNode(name='Calc', qualified_name='calc::Calc', module='calc',
    description='A calculator',
    attributes=[AttributeNode(name='result', qualified_name='calc::Calc::result',
        type_signature='int', description='The result')])
cd = ClassDiagram(classes=[cls])
d = cd.model_dump(tags={'llm'})
print('LLM dump:', d['classes'][0]['name'])
assert d['classes'][0]['name'] == 'Calc'
print('OK')
"
```

Expected: `LLM dump: Calc` then `OK`

- [ ] **Step 3: Verify repository round-trip (requires Neo4j)**

```bash
cd /Users/danielnewman/dev/codegraph && .venv/bin/python -c "
from codegraph.designs import ClassDiagram, ClassNode
from codegraph.repositories.compound import CompoundRepository

cd = ClassDiagram(classes=[
    ClassNode(name='Test', qualified_name='test::Test', kind='class')
])
cd.to_neo4j()

repo = CompoundRepository()
result = repo.get('test::Test')
assert result is not None
assert result.name == 'Test'
print('Round-trip OK')
"
```

Expected: `Round-trip OK`

- [ ] **Step 4: Verify no stale imports remain**

```bash
grep -r "codegraph.nodes" src/ tests/ && echo "STALE IMPORTS FOUND" || echo "No stale imports"
grep -r "codegraph.neo4j" src/ tests/ && echo "STALE IMPORTS FOUND" || echo "No stale imports"
```

Expected: `No stale imports` for both

- [ ] **Step 5: Commit final state**

```bash
git add -A
git commit -m "chore: final verification and cleanup after neomodel migration"
```
