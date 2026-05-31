# Ticketing System — Neomodel Migration Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Update the ticketing system to match codegraph's neomodel migration — replace imports from `codegraph.neo4j` and `codegraph.nodes` with neomodel equivalents.

**Architecture:** The ticketing system extends codegraph's node models with ticketing-specific fields (specialization, implementation_status). These thin subclasses switch from Pydantic `BaseModel` to neomodel `StructuredNode`. The design repository's raw Cypher writes are replaced with neomodel `.save()` calls. `ClassDiagram.to_neo4j()` call signature changes from returning lists to persisting internally.

**Tech Stack:** Python 3.12, neomodel>=5.0, pydantic>=2.0, codegraph (updated)

---

## File Structure

**Modify (all in `/Users/danielnewman/dev/ticketing_system/`):**
- `backend/db/neo4j/connection.py` — delete the re-export shim
- `backend/db/neo4j/__init__.py` — remove codegraph.neo4j imports, add neomodel config
- `backend/db/neo4j/models/nodes/compound.py` — switch base class from Pydantic to neomodel
- `backend/db/neo4j/models/nodes/member.py` — switch base class from Pydantic to neomodel
- `backend/db/neo4j/models/nodes/__init__.py` — update NamespaceNode import
- `backend/db/neo4j/repositories/design.py` — rewrite writes to use neomodel `.save()`
- `backend/ticketing_agent/mcp_server.py` — replace Neo4jConnection with neomodel config
- `backend/codebase/schemas.py` — update imports
- `backend/requirements/services/persistence.py` — update imports
- `backend/design_data/transforms.py` — update ClassDiagram.to_neo4j() callers
- `backend/design_data/repository.py` — update ClassDiagram.to_neo4j() callers
- Various agent design modules — update ClassDiagram.to_neo4j() callers
- `pyproject.toml` — remove codegraph[neo4j] extra if it exists, add neomodel
- `tests/` — update neo4j connection setup

---

### Task 1: Update dependencies and add neomodel config

**Files:**
- Modify: `pyproject.toml`
- Modify: `backend/db/neo4j/connection.py`
- Modify: `backend/db/neo4j/__init__.py`

- [ ] **Step 1: Add neomodel to dependencies**

In `pyproject.toml`, add `"neomodel>=5.0"` and update the codegraph dependency to the new version:

```toml
dependencies = [
    "codegraph>=0.2.0",  # updated — uses neomodel internally
    "neomodel>=5.0",
    # ... other deps
]
```

- [ ] **Step 2: Create neomodel config setup**

Replace `backend/db/neo4j/connection.py` — delete the re-export shim, add neomodel config:

```python
"""Neomodel connection configuration for the ticketing system.

Replaces the old codegraph.neo4j re-export shim.
Import this module before any neomodel model class is imported.
"""

import os
from neomodel import config

NEO4J_URI = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.environ.get("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD", "")

_bolt_host = NEO4J_URI.replace("bolt://", "")
config.DATABASE_URL = f"bolt://{NEO4J_USER}:{NEO4J_PASSWORD}@{_bolt_host}"
```

- [ ] **Step 3: Update backend/db/neo4j/__init__.py**

Remove the old `from codegraph.neo4j import ...` block. The connection details now come from local `config.DATABASE_URL`:

```python
"""Neo4j data access — repositories and raw queries."""

from backend.db.neo4j.connection import NEO4J_PASSWORD, NEO4J_URI, NEO4J_USER
from backend.db.neo4j.queries import (
    fetch_codebase_compounds,
    fetch_dependency_compounds,
    fetch_design_dependency_links,
    fetch_design_graph,
    fetch_hlr_subgraph,
    fetch_neighbourhood_graph,
    fetch_node_detail,
)
from backend.db.neo4j.repositories import DesignRepository, RequirementRepository, VerificationRepository
from backend.db.neo4j.models.nodes import CompoundNode, MemberNode, NamespaceNode
from backend.db.neo4j.models.edges import CodebaseEdge
from backend.db.neo4j.repositories.models import HLRNode, LLRNode, VerificationMethodNode, ConditionNode, ActionNode
from backend.db.neo4j.constraints import ensure_ticketing_constraints

__all__ = [
    "NEO4J_URI",
    "NEO4J_USER",
    "NEO4J_PASSWORD",
    # Repositories
    "DesignRepository",
    "RequirementRepository",
    "VerificationRepository",
    "CompoundNode",
    "MemberNode",
    "NamespaceNode",
    "CodebaseEdge",
    "HLRNode",
    "LLRNode",
    "VerificationMethodNode",
    "ConditionNode",
    "ActionNode",
    # Queries
    "fetch_codebase_compounds",
    "fetch_dependency_compounds",
    "fetch_design_dependency_links",
    "fetch_design_graph",
    "fetch_hlr_subgraph",
    "fetch_neighbourhood_graph",
    "fetch_node_detail",
    # Constraints
    "ensure_ticketing_constraints",
]
```

- [ ] **Step 4: Verify imports**

```bash
cd /Users/danielnewman/dev/ticketing_system && .venv/bin/python -c "
import os; os.environ['NEO4J_PASSWORD'] = 'skip'
from backend.db.neo4j import NEO4J_URI, NEO4J_USER
print('OK:', NEO4J_URI)
"
```

Expected: `OK: bolt://localhost:7687`

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml backend/db/neo4j/connection.py backend/db/neo4j/__init__.py
git commit -m "feat: replace codegraph.neo4j imports with neomodel config"
```

---

### Task 2: Migrate ticketing node models to neomodel

**Files:**
- Modify: `backend/db/neo4j/models/nodes/compound.py`
- Modify: `backend/db/neo4j/models/nodes/member.py`
- Modify: `backend/db/neo4j/models/nodes/__init__.py`

- [ ] **Step 1: Rewrite compound.py as neomodel subclass**

The old file extended `codegraph.nodes.CompoundNode` (Pydantic). The new codegraph's `CompoundNode` is now a neomodel `StructuredNode`. Ticketing extensions become additional neomodel properties:

```python
"""CompoundNode — :Compound in Neo4j.

Ticketing-system extensions on top of ``codegraph.models.CompoundNode``.
All core fields (qualified_name, kind, layer, component_id, etc.)
are inherited from the codegraph neomodel model.
"""

from codegraph.models.compound import CompoundNode as BaseCompoundNode
from neomodel import StringProperty, BooleanProperty


class CompoundNode(BaseCompoundNode):
    """A compound entity with ticketing-system extensions."""

    specialization = StringProperty(default="")
    is_intercomponent = BooleanProperty(default=False)
    implementation_status = StringProperty(default="designed")
    test_file = StringProperty(default="")
```

- [ ] **Step 2: Rewrite member.py as neomodel subclass**

```python
"""MemberNode — :Member in Neo4j.

Thin subclass of codegraph.models.MemberNode for import compatibility
and the ``extra: "ignore"`` model config.
"""

from codegraph.models.member import MemberNode as BaseMemberNode


class MemberNode(BaseMemberNode):
    """A member entity with ticketing-system compatibility."""
    pass
```

- [ ] **Step 3: Update models/nodes/__init__.py**

```python
"""Ticketing-system node models for Neo4j."""

from backend.db.neo4j.models.nodes.compound import CompoundNode
from backend.db.neo4j.models.nodes.member import MemberNode
from codegraph.models.namespace import NamespaceNode

__all__ = ["CompoundNode", "MemberNode", "NamespaceNode"]
```

- [ ] **Step 4: Verify imports**

```bash
cd /Users/danielnewman/dev/ticketing_system && .venv/bin/python -c "
import os; os.environ['NEO4J_PASSWORD'] = 'skip'
from backend.db.neo4j.models.nodes import CompoundNode, MemberNode, NamespaceNode
print('All models OK')
"
```

Expected: `All models OK`

- [ ] **Step 5: Commit**

```bash
git add backend/db/neo4j/models/nodes/
git commit -m "refactor: migrate ticketing node models to neomodel base classes"
```

---

### Task 3: Update design repository writes to use neomodel .save()

**Files:**
- Modify: `backend/db/neo4j/repositories/design.py`

The design repository currently uses raw Cypher via `session.run()` to insert nodes. After migration, writes use neomodel `.save()`. **Reads (queries)** can stay as raw Cypher for now — only writes change.

- [ ] **Step 1: Locate all write methods in design.py**

Find methods that execute `CREATE`, `MERGE`, `SET`, or `DELETE` Cypher. These need to change. Pure Cypher reads (MATCH...RETURN without modification) can stay.

Key write methods likely include (review the file):
- `save_node()` or equivalent — replace with `node.save()`
- `delete_node()` — replace with `node.delete()`
- `clear_design_layer()` — replace with repositories' `delete_all_design_layer()`

- [ ] **Step 2: Rewrite node creation/save to use .save()**

For any method that creates or updates nodes via Cypher, replace with neomodel. Example:

```python
# Before (raw Cypher):
def save_compound(self, compound: CompoundNode):
    session.run("""
        MERGE (c:Compound {qualified_name: $qn})
        SET c += $props
    """, qn=compound.qualified_name, props=compound.model_dump())

# After (neomodel):
def save_compound(self, compound: CompoundNode):
    compound.save()
```

- [ ] **Step 3: Update clear/delete methods**

```python
# Before:
def clear_design_layer(self):
    session.run("MATCH (c:Compound {layer: 'design'}) DETACH DELETE c")
    session.run("MATCH (m:Member {layer: 'design'}) DETACH DELETE m")

# After (using codegraph repositories):
from codegraph.repositories.compound import CompoundRepository
from codegraph.repositories.member import MemberRepository

def clear_design_layer(self):
    CompoundRepository().delete_all_design_layer()
    MemberRepository().delete_all_design_layer()
```

- [ ] **Step 4: Commit**

```bash
git add backend/db/neo4j/repositories/design.py
git commit -m "refactor: replace raw Cypher writes with neomodel .save() in design repo"
```

---

### Task 4: Update ClassDiagram.to_neo4j() callers

**Files to search and update:**
- `backend/design_data/transforms.py`
- `backend/design_data/repository.py`
- `backend/ticketing_agent/design/design_oo.py`
- `backend/ticketing_agent/design/design_hlr.py`
- `backend/ticketing_agent/design/design_per_hlr.py`
- `backend/ticketing_agent/design_verify/combined_loop.py`
- `backend/ticketing_agent/tools/design_verify/draft_design.py`
- `backend/ticketing_agent/tools/design_verify/dispatcher.py`
- `backend/ticketing_agent/tools/design_verify/validate_design.py`
- `backend/ticketing_agent/tools/helpers/design_validation.py`
- `backend/pipeline/sync_hooks.py`

- [ ] **Step 1: Find all callers of to_neo4j()**

```bash
grep -rn "to_neo4j()" backend/ --include="*.py" | grep -v __pycache__
```

- [ ] **Step 2: Update each caller**

The old pattern:
```python
compounds, members, edges = diagram.to_neo4j()
# ... then manually insert into Neo4j
```

The new pattern:
```python
diagram.to_neo4j()  # persists internally, returns None
```

Remove any subsequent manual insert loops that are now handled internally.

- [ ] **Step 3: Update transforms.py specifically**

`class_diagram_from_oo_design()` enriches a ClassDiagram by computing qualified_names. After this enrichment, the diagram is typically saved to Neo4j. The save step should change from returning lists to persisting internally. If `transforms.py` itself calls `to_neo4j()`, update that call. If it only enriches and returns, no change needed.

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "refactor: update ClassDiagram.to_neo4j() callers for new internal-save API"
```

---

### Task 5: Update remaining codegraph imports

**Files:**
- Modify: `backend/ticketing_agent/mcp_server.py`
- Modify: `backend/codebase/schemas.py`
- Modify: `backend/requirements/services/persistence.py`
- Modify: `backend/codebase/type_parser.py`

- [ ] **Step 1: Update mcp_server.py**

Find and replace:
```python
# Old
from codegraph.neo4j import Neo4jConnection
from codegraph.neo4j import NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD

# New
from backend.db.neo4j.connection import NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD
```

Also update any `Neo4jConnection()` instantiation. If the MCP server uses it to verify connectivity or ensure constraints, replace with neomodel equivalents or remove (neomodel auto-connects).

- [ ] **Step 2: Update codebase/schemas.py**

```python
# Old
from codegraph.nodes import CompoundNode, MemberNode, NamespaceNode

# New
from codegraph.models import CompoundNode, MemberNode, NamespaceNode
```

Note: `codegraph.models` exports neomodel classes, not Pydantic. If `schemas.py` validates user input against Pydantic schemas, it may need to keep Pydantic imports. Check actual usage — if it uses `model_validate()` or `model_dump()`, those APIs don't exist on neomodel classes.

- [ ] **Step 3: Update persistence.py**

```python
# Old
from codegraph.nodes import NamespaceNode

# New
from codegraph.models import NamespaceNode
```

- [ ] **Step 4: Check type_parser.py**

The file re-exports `TypeRef` from `codegraph.type_parser`. This import should still work since `codegraph.type_parser` is not affected by the migration. No change needed if it's just a re-export.

- [ ] **Step 5: Commit**

```bash
git add backend/ticketing_agent/mcp_server.py backend/codebase/schemas.py backend/requirements/services/persistence.py
git commit -m "refactor: update remaining codegraph imports for neomodel migration"
```

---

### Task 6: Update tests and verify

**Files:**
- Modify: `tests/conftest.py`
- Modify: `tests/test_design_repository.py`
- Modify: `tests/test_persistence.py`
- Modify: any test files using `Neo4jConnection` or `codegraph.neo4j`

- [ ] **Step 1: Update test conftest for neomodel**

```python
"""Test fixtures for ticketing system with neomodel."""
import os
import pytest
from neomodel import config, db, install_all_labels


@pytest.fixture(scope="session", autouse=True)
def setup_neomodel():
    uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
    user = os.environ.get("NEO4J_USER", "neo4j")
    password = os.environ.get("NEO4J_PASSWORD", "neo4j")
    host = uri.replace("bolt://", "")
    config.DATABASE_URL = f"bolt://{user}:{password}@{host}"
    install_all_labels()


@pytest.fixture(autouse=True)
def clear_db():
    db.cypher_query("MATCH (n) DETACH DELETE n")
    yield
```

- [ ] **Step 2: Find tests using old imports**

```bash
grep -rn "Neo4jConnection\|codegraph.neo4j\|get_standalone_driver\|get_standalone_session" tests/ --include="*.py"
```

Update any hits to use neomodel config instead.

- [ ] **Step 3: Run existing test suite**

```bash
cd /Users/danielnewman/dev/ticketing_system && .venv/bin/python -m pytest tests/ -x -q
```

Expected: Tests pass or fail for reasons unrelated to the migration (fix any migration-related failures).

- [ ] **Step 4: Commit**

```bash
git add tests/conftest.py
git commit -m "test: update tests for neomodel migration"
```

---

### Task 7: Final verification

- [ ] **Step 1: Verify no stale imports**

```bash
grep -rn "codegraph.neo4j\|codegraph.nodes" backend/ --include="*.py" | grep -v __pycache__ | grep -v ".worktrees"
```

Expected: No results (all imports migrated)

- [ ] **Step 2: Full import chain test**

```bash
cd /Users/danielnewman/dev/ticketing_system && .venv/bin/python -c "
import os; os.environ['NEO4J_PASSWORD'] = 'skip'
from backend.db.neo4j import DesignRepository, CompoundNode, MemberNode, NamespaceNode
from backend.design_data import ClassDiagram
print('Full import chain OK')
"
```

- [ ] **Step 3: Commit**

```bash
git add -A
git commit -m "chore: final verification after neomodel migration"
```
