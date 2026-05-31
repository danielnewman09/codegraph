# Doxygen Dependency Parser — Neomodel Migration Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Update the Doxygen Dependency Parser to match codegraph's neomodel migration — node model imports change from Pydantic to neomodel, and the Neo4j backend replaces raw Cypher writes with neomodel `.save()` calls or codegraph repositories.

**Architecture:** The parser constructs `ParseResult` dataclasses containing lists of node model instances. The Neo4j backend (`neo4j_backend.py`) currently serializes these to dicts and runs raw Cypher `MERGE` statements. After migration, node instances are neomodel objects and can be persisted with `.save()` or bulk-saved through codegraph repositories.

**Tech Stack:** Python 3.12, neomodel>=5.0, codegraph (updated), neo4j (driver)

---

## File Structure

**Modify (all in `/Users/danielnewman/dev/Doxygen-Dependency-Parser/`):**
- `pyproject.toml` — add neomodel dependency, update codegraph
- `src/doxygen_index/parser.py` — update node model imports
- `src/doxygen_index/neo4j_backend.py` — replace raw Cypher writes with neomodel `.save()`
- `src/doxygen_index/cppreference/__init__.py` — update NamespaceNode import
- `src/doxygen_index/cppreference/page_parser.py` — update node model imports
- `tests/test_parser.py` — update imports

---

### Task 1: Update dependencies

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add neomodel and update codegraph**

```toml
dependencies = [
    "codegraph>=0.2.0",  # updated — uses neomodel internally
    "neomodel>=5.0",
    # ... other deps (lxml, etc.)
]
```

- [ ] **Step 2: Install updated dependencies**

```bash
cd /Users/danielnewman/dev/Doxygen-Dependency-Parser && .venv/bin/pip install --upgrade codegraph neomodel>=5.0
```

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml
git commit -m "feat: add neomodel dependency and update codegraph"
```

---

### Task 2: Update node model imports in parser.py

**Files:**
- Modify: `src/doxygen_index/parser.py`

- [ ] **Step 1: Update imports**

The parser constructs `CompoundNode`, `FileNode`, `MemberNode`, `NamespaceNode`, `ParameterNode` instances. These are now neomodel classes:

```python
# Old
from codegraph import CompoundNode, FileNode, MemberNode, NamespaceNode, ParameterNode

# New — same import path works since codegraph re-exports from codegraph.models
from codegraph import CompoundNode, FileNode, MemberNode, NamespaceNode, ParameterNode
```

The import path doesn't change — `codegraph` re-exports the neomodel models from `__init__.py`. However, the constructors change slightly (neomodel's `StructuredNode.__init__` vs Pydantic's `BaseModel.__init__`). Pydantic accepted extra kwargs (ignored by default), neomodel may not. Review the parser to ensure it only passes valid field names.

- [ ] **Step 2: Verify ParseResult structure**

`ParseResult` is a dataclass with lists of neomodel instances. This still works — dataclasses don't care about the type of their fields. No change needed to `ParseResult`.

- [ ] **Step 3: Verify imports**

```bash
cd /Users/danielnewman/dev/Doxygen-Dependency-Parser && .venv/bin/python -c "
import os; os.environ['NEO4J_PASSWORD'] = 'skip'
from codegraph.config import config  # must import before models
from codegraph import CompoundNode, FileNode, MemberNode, NamespaceNode, ParameterNode
n = NamespaceNode(qualified_name='test', kind='namespace')
print('NamespaceNode created:', n.qualified_name)
"
```

Expected: `NamespaceNode created: test`

- [ ] **Step 4: Commit**

```bash
git add src/doxygen_index/parser.py
git commit -m "refactor: update node model imports for neomodel"
```

---

### Task 3: Update cppreference imports

**Files:**
- Modify: `src/doxygen_index/cppreference/__init__.py`
- Modify: `src/doxygen_index/cppreference/page_parser.py`

- [ ] **Step 1: Update __init__.py**

```python
# Old
from codegraph import NamespaceNode

# New — same path, different underlying class
from codegraph import NamespaceNode
```

No code change needed — the import stays the same.

- [ ] **Step 2: Update page_parser.py**

```python
# Old
from codegraph import CompoundNode, FileNode, MemberNode, ParameterNode

# New — same path
from codegraph import CompoundNode, FileNode, MemberNode, ParameterNode
```

Same — no code change, just verify constructors don't pass unknown fields.

- [ ] **Step 3: Commit**

```bash
git add src/doxygen_index/cppreference/
git commit -m "refactor: verify cppreference imports work with neomodel models"
```

---

### Task 4: Rewrite Neo4j backend to use neomodel .save()

**Files:**
- Modify: `src/doxygen_index/neo4j_backend.py`

This is the biggest change. The backend currently serializes node instances to dicts with `.model_dump()` and runs raw Cypher `MERGE` statements. Replace with neomodel `.save()`.

- [ ] **Step 1: Add neomodel config setup**

Add at the top of `neo4j_backend.py`:

```python
"""Neo4j backend — ingests ParseResult into Neo4j using neomodel."""

import os
from neomodel import config as neomodel_config, db, install_all_labels
```

- [ ] **Step 2: Rewrite `ensure_schema()`**

```python
def ensure_schema(driver, database: str = "neo4j") -> None:
    """Create constraints and indexes via neomodel's install_labels."""
    # neomodel handles constraint creation based on model definitions
    install_all_labels()
    print("Schema ensured via neomodel install_all_labels().")
```

Note: `install_all_labels()` must be called after all neomodel model classes have been imported.

- [ ] **Step 3: Rewrite `write_result()` to use neomodel**

The current approach loops through `ParseResult` fields, serializes to dicts, and runs Cypher. Replace with neomodel `.save()`:

```python
def write_result(driver, result: ParseResult, database: str = "neo4j") -> None:
    """Write a ParseResult to Neo4j using neomodel .save()."""
    # Configure neomodel to use the same driver/URL
    uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
    user = os.environ.get("NEO4J_USER", "neo4j")
    password = os.environ.get("NEO4J_PASSWORD", "msd-local-dev")
    host = uri.replace("bolt://", "")
    neomodel_config.DATABASE_URL = f"bolt://{user}:{password}@{host}"
    db.set_connection(neomodel_config.DATABASE_URL)

    _write_files(result)
    _write_namespaces(result)
    _write_compounds(result)
    _write_members(result)
    _write_parameters(result)
    _write_relationships(result)
    print("Write complete.")
```

- [ ] **Step 4: Rewrite individual write functions**

Replace each `_write_*` function:

```python
def _write_files(result: ParseResult):
    for f in result.files:
        f.save()
    print(f"  Files: {len(result.files)}")

def _write_namespaces(result: ParseResult):
    for n in result.namespaces:
        n.save()
    print(f"  Namespaces: {len(result.namespaces)}")

def _write_compounds(result: ParseResult):
    for c in result.compounds:
        c.save()
    print(f"  Compounds: {len(result.compounds)}")

def _write_members(result: ParseResult):
    for m in result.members:
        m.save()
    print(f"  Members: {len(result.members)}")

def _write_parameters(result: ParseResult):
    for p in result.parameters:
        p.save()
    print(f"  Parameters: {len(result.parameters)}")
```

- [ ] **Step 5: Rewrite relationship writes**

Relationships use neomodel's `RelationshipTo`/`RelationshipFrom` descriptors. For bulk operations, use the relationship `.connect()` method:

```python
def _write_relationships(result: ParseResult):
    # COMPOSES: Member → Compound via compound_refid
    compound_index = {c.refid: c for c in result.compounds if c.refid}
    for m in result.members:
        if m.compound_refid and m.compound_refid in compound_index:
            compound_index[m.compound_refid].members.connect(m)

    # DEFINED_IN: Entity → File
    file_index = {f.path: f for f in result.files if f.path}
    for c in result.compounds:
        if c.file_path and c.file_path in file_index:
            c.defined_in.connect(file_index[c.file_path])

    print("  Relationships: COMPOSES, DEFINED_IN")
```

**Note:** `CompoundNode` needs a `defined_in` relationship defined in the model. Since codegraph's `CompoundNode` may not have this, consider adding it or using raw Cypher just for relationships not defined in the model.

- [ ] **Step 6: Handle the clear methods**

The `clear_source()` and `clear_all()` methods can use `db.cypher_query()` for bulk deletes (neomodel's `.delete()` on individual nodes would be too slow for bulk operations):

```python
def clear_source(source: str):
    """Remove all nodes with a specific source label."""
    from neomodel import db
    db.cypher_query(
        "MATCH (n) WHERE n.source = $src DETACH DELETE n",
        {"src": source}
    )
    print(f"  Cleared existing '{source}' data from Neo4j.")

def clear_all():
    """Remove all codebase nodes and relationships."""
    from neomodel import db
    db.cypher_query("MATCH (n) DETACH DELETE n")
    print("  Cleared all codebase data from Neo4j.")
```

- [ ] **Step 7: Commit**

```bash
git add src/doxygen_index/neo4j_backend.py
git commit -m "refactor: replace raw Cypher writes with neomodel .save() in Neo4j backend"
```

---

### Task 5: Update tests

**Files:**
- Modify: `tests/test_parser.py`

- [ ] **Step 1: Update test imports**

The test imports `CompoundNode`, `FileNode`, etc. from `codegraph`. These are now neomodel classes. Update the test to import `config` first:

```python
# At the top of test_parser.py, or in conftest.py
import os
os.environ.setdefault('NEO4J_PASSWORD', 'test')

from codegraph.config import config  # ensures neomodel is configured
from codegraph import CompoundNode, FileNode, MemberNode, NamespaceNode, ParameterNode
```

- [ ] **Step 2: Run parser tests**

```bash
cd /Users/danielnewman/dev/Doxygen-Dependency-Parser && .venv/bin/python -m pytest tests/test_parser.py -v
```

Expected: Tests pass (may need Neo4j for full integration, but unit tests should pass without)

- [ ] **Step 3: Commit**

```bash
git add tests/test_parser.py
git commit -m "test: update parser tests for neomodel migration"
```

---

### Task 6: Final verification

- [ ] **Step 1: End-to-end smoke test**

```bash
cd /Users/danielnewman/dev/Doxygen-Dependency-Parser && .venv/bin/python -c "
import os; os.environ['NEO4J_PASSWORD'] = 'skip'
from codegraph.config import config
from codegraph import CompoundNode, FileNode

# Create and save a compound
f = FileNode(refid='test_file', name='test.cpp', path='/test.cpp', language='C++', source='test')
c = CompoundNode(qualified_name='test::Foo', kind='class', name='Foo', source='test')
print('Models created OK')
"
```

Expected: `Models created OK`

- [ ] **Step 2: Verify no Pydantic-only API usage**

The parser may use Pydantic-specific APIs like `.model_dump()`, `.model_validate()`, or `model_config`. Search for these:

```bash
grep -rn "model_dump\|model_validate\|model_config" src/doxygen_index/ --include="*.py"
```

If any found, replace with neomodel equivalents or adjust the logic.

- [ ] **Step 3: Commit**

```bash
git add -A
git commit -m "chore: final verification after neomodel migration"
```
