# Implementation Source Extraction — Implementation Plan

> **Date:** 2026-06-08  
> **Spec:** `danielnewman09/codegraph` Issue #2  
> **Repos involved:**
> - `danielnewman09/codegraph` (local: `/Users/danielnewman/dev/codegraph`) — data model changes
> - `danielnewman09/Doxygen-Dependency-Parser` (local: `/Users/danielnewman/dev/Doxygen-Dependency-Parser`) — parsing/ingestion changes

---

## Overview

Add `body_start` and `body_end` properties to `_MemberMixin`, then extend the Doxygen parser to extract implementation source code from those line ranges and create `ImplementationNode` instances connected via `HAS_IMPLEMENTATION`. Embeddings deferred to a later phase.

---

## Task 1: Add `body_start` and `body_end` to `_MemberMixin`

**Repo:** codegraph  
**File:** `src/codegraph/models/member.py`

- [ ] **Step 1:** Add two `IntegerProperty` fields to `_MemberMixin`, after the `line_number` field in the "Location" section:

```python
    # --- Location ---
    file_path = StringProperty(default="")
    line_number = IntegerProperty()
    body_start = IntegerProperty(
        default=0,
        help_text="Start line of the implementation body (from Doxygen bodystart). "
                  "0 or negative means no implementation body available.",
    )
    body_end = IntegerProperty(
        default=0,
        help_text="End line of the implementation body (from Doxygen bodyend). "
                  "0 or negative means no implementation body available.",
    )
```

- [ ] **Step 2:** Update the `_MemberMixin` docstring to include `body_start` and `body_end` in the attributes list.

- [ ] **Step 3:** Verify the model imports and creates correctly:

```bash
cd /Users/danielnewman/dev/codegraph && .venv/bin/python -c "
from codegraph.models.member import MethodNode, FunctionNode
m = MethodNode(kind='method')
assert hasattr(m, 'body_start')
assert m.body_start == 0
assert hasattr(m, 'body_end')
assert m.body_end == 0
print('OK')
"
```

- [ ] **Step 4:** Confirm that `_llm_fields` does NOT include `body_start` or `body_end`:

```bash
cd /Users/danielnewman/dev/codegraph && .venv/bin/python -c "
from codegraph.models.member import _MemberMixin, MethodNode, FunctionNode, AttributeNode, DefineNode
for cls in [_MemberMixin, MethodNode, FunctionNode, AttributeNode, DefineNode]:
    assert 'body_start' not in cls._llm_fields, f'{cls.__name__}._llm_fields contains body_start'
    assert 'body_end' not in cls._llm_fields, f'{cls.__name__}._llm_fields contains body_end'
print('OK - body_start/body_end not in _llm_fields')
"
```

---

## Task 2: Add `body_start`/`body_end` to member test fixtures

**Repo:** codegraph  
**Files:** `tests/data/method_node_full.json`, `tests/data/function_node_full.json`, `tests/data/attribute_node_full.json`, `tests/data/define_node_full.json`, `tests/data/enum_value_node_full.json`

- [ ] **Step 1:** Add `"body_start": 0` and `"body_end": 0` to each member fixture JSON file (default values). For `method_node_full.json`, use realistic values like `"body_start": 25` and `"body_end": 30` to test roundtrip.

- [ ] **Step 2:** Verify fixtures load and roundtrip correctly:

```bash
cd /Users/danielnewman/dev/codegraph && .venv/bin/python -c "
import json
from pathlib import Path
from codegraph.models.tags import CodeGraphNode

for f in Path('tests/data').glob('*_node_full.json'):
    data = json.loads(f.read_text())
    if data.get('type') in ('MethodNode', 'FunctionNode', 'AttributeNode', 'DefineNode', 'EnumValueNode'):
        node = CodeGraphNode.from_json(data)
        assert hasattr(node, 'body_start'), f'{data[\"type\"]} missing body_start'
        print(f'{data[\"type\"]}: body_start={node.body_start}, body_end={node.body_end}')
print('OK')
"
```

---

## Task 3: Add tests for `body_start`/`body_end` on member nodes

**Repo:** codegraph  
**File:** `tests/member/test_member_search_fields.py`

- [ ] **Step 1:** Add a new test class `TestMemberBodyLocation`:

```python
class TestMemberBodyLocation:
    """Test body_start and body_end fields on member nodes."""

    def test_method_body_start_default_zero(self):
        m = MethodNode(kind="method")
        assert m.body_start == 0

    def test_method_body_end_default_zero(self):
        m = MethodNode(kind="method")
        assert m.body_end == 0

    def test_method_body_start_stored(self):
        m = MethodNode(kind="method", body_start=25, body_end=30)
        assert m.body_start == 25
        assert m.body_end == 30

    def test_function_body_start_stored(self):
        f = FunctionNode(kind="function", body_start=100, body_end=120)
        assert f.body_start == 100
        assert f.body_end == 120

    def test_body_start_not_in_llm_fields(self):
        """body_start/body_end are extraction plumbing, not for LLM context."""
        for cls in [MethodNode, FunctionNode, AttributeNode, DefineNode]:
            assert "body_start" not in cls._llm_fields
            assert "body_end" not in cls._llm_fields

    def test_method_serialize_excludes_body_location(self):
        m = MethodNode(kind="method", body_start=25, body_end=30, name="draw")
        serialized = m.serialize()
        assert "body_start" not in serialized
        assert "body_end" not in serialized

    def test_deserialize_with_body_location(self):
        data = {
            "type": "MethodNode",
            "qualified_name": "Widget::draw",
            "name": "draw",
            "kind": "method",
            "body_start": 25,
            "body_end": 30,
        }
        node = CodeGraphNode.from_json(data)
        assert isinstance(node, MethodNode)
        assert node.body_start == 25
        assert node.body_end == 30

    def test_deserialize_without_body_location(self):
        """Old fixtures without body_start/body_end should default to 0."""
        data = {
            "type": "MethodNode",
            "qualified_name": "Widget::draw",
            "name": "draw",
            "kind": "method",
        }
        node = CodeGraphNode.from_json(data)
        assert node.body_start == 0
        assert node.body_end == 0
```

- [ ] **Step 2:** Run the new tests:

```bash
cd /Users/danielnewman/dev/codegraph && .venv/bin/python -m pytest tests/member/test_member_search_fields.py -v
```

---

## Task 4: Update `ImplementationNode` import in codegraph `__init__.py`

**Repo:** codegraph  
**File:** `src/codegraph/__init__.py`

- [ ] **Step 1:** Add `ImplementationNode` to the imports and `__all__` list so the Doxygen Dependency Parser can import it directly.

- [ ] **Step 2:** Verify:

```bash
cd /Users/danielnewman/dev/codegraph && .venv/bin/python -c "from codegraph import ImplementationNode; print(ImplementationNode._llm_fields)"
```

Expected output: `{'qualified_name', 'kind', 'implementation'}`

---

## Task 5: Extract `bodystart`/`bodyend` in the Doxygen parser

**Repo:** Doxygen-Dependency-Parser  
**File:** `src/doxygen_index/parser.py`

- [ ] **Step 1:** Update `parse_location()` to also extract `bodystart` and `bodyend` from the `<location>` element. Currently returns `(file_path, line_number)`. Change to return `(file_path, line_number, body_start, body_end)`:

```python
def parse_location(loc_elem: Optional[ET.Element]) -> tuple:
    """Extract location data from a Doxygen location element.

    Returns:
        (file_path, line_number, body_start, body_end)
        body_start/body_end are None if not present or -1 (meaning no body).
    """
    if loc_elem is None:
        return None, None, None, None
    file_path = loc_elem.get("file")
    line = loc_elem.get("line")
    bodystart = loc_elem.get("bodystart")
    bodyend = loc_elem.get("bodyend")
    body_start = int(bodystart) if bodystart and bodystart != "-1" else None
    body_end = int(bodyend) if bodyend and bodyend != "-1" else None
    return (
        file_path,
        int(line) if line else None,
        body_start,
        body_end,
    )
```

- [ ] **Step 2:** Update all call sites of `parse_location()`:

In `_parse_member()`:
```python
    loc = memberdef.find("location")
    file_path, line_number, body_start, body_end = parse_location(loc)
```

In `_parse_compound_file()`:
```python
    loc = compounddef.find("location")
    file_path, line_number, _, _ = parse_location(loc)
```

- [ ] **Step 3:** Pass `body_start` and `body_end` to member node constructors in `_parse_member()`. For `MethodNode`, `FunctionNode`, `DefineNode`, and other members, add `body_start=body_start or 0, body_end=body_end or 0`.

- [ ] **Step 4:** Verify the parser still works:

```bash
cd /Users/danielnewman/dev/Doxygen-Dependency-Parser && python -m pytest tests/test_parser.py -v
```

---

## Task 6: Add `ImplementationRef` dataclass and `implementations` list to `ParseResult`

**Repo:** Doxygen-Dependency-Parser  
**File:** `src/doxygen_index/parser.py`

- [ ] **Step 1:** Add `ImplementationRef` dataclass that links a member refid to an ImplementationNode:

```python
@dataclass
class ImplementationRef:
    """Association between a member and its extracted implementation source."""
    member_refid: str
    implementation: "ImplementationNode"
```

Add `ImplementationNode` to the codegraph imports at the top of the file.

- [ ] **Step 2:** Add `implementations` and `implementation_refs` fields to `ParseResult`:

```python
    implementations: list[ImplementationNode] = field(default_factory=list)
    implementation_refs: list[ImplementationRef] = field(default_factory=list)
```

- [ ] **Step 3:** Verify import works:

```bash
cd /Users/danielnewman/dev/Doxygen-Dependency-Parser && python -c "from doxygen_index.parser import ParseResult, ImplementationRef; print('OK')"
```

---

## Task 7: Implement `extract_implementations()` function

**Repo:** Doxygen-Dependency-Parser  
**File:** `src/doxygen_index/parser.py`

- [ ] **Step 1:** Add the `extract_implementations()` function after `_resolve_concept_constraints()`:

```python
def extract_implementations(
    result: ParseResult,
    source_base: Path | str | None = None,
) -> None:
    """Extract implementation source code from source files using body_start/body_end.

    For each member with body_start > 0 and body_end > 0, reads the
    source file and extracts lines body_start..body_end (inclusive),
    creates an ImplementationNode, and records the association.

    Members without implementation bodies (body_start == 0, body_end == 0,
    body_start < 0, or body_end < 0) are skipped.
    """
    if source_base is not None:
        source_base = Path(source_base)

    file_cache: dict[str, list[str] | None] = {}

    def _read_lines(file_path: str) -> list[str] | None:
        if file_path in file_cache:
            return file_cache[file_path]
        path = Path(file_path)
        if not path.is_absolute() and source_base is not None:
            path = source_base / path
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
            file_cache[file_path] = lines
            return lines
        except FileNotFoundError:
            print(f"  Warning: Source file not found for implementation extraction: {path}",
                  file=sys.stderr)
            file_cache[file_path] = None
            return None

    members_with_bodies: list[tuple[object, str]] = []
    for m in result.methods:
        if m.body_start > 0 and m.body_end > 0 and m.file_path:
            members_with_bodies.append((m, m.refid))
    for f in result.functions:
        if f.body_start > 0 and f.body_end > 0 and f.file_path:
            members_with_bodies.append((f, f.refid))
    for d in result.defines:
        if d.body_start > 0 and d.body_end > 0 and d.file_path:
            members_with_bodies.append((d, d.refid))

    if not members_with_bodies:
        return

    impl_count = 0
    skip_count = 0

    for member, refid in members_with_bodies:
        lines = _read_lines(member.file_path)
        if lines is None:
            skip_count += 1
            continue

        start = member.body_start - 1  # Convert to 0-based
        end = member.body_end            # 1-based inclusive

        if start < 0 or end > len(lines) or start >= end:
            skip_count += 1
            continue

        source_text = "".join(lines[start:end]).rstrip("\n")

        if not source_text.strip():
            skip_count += 1
            continue

        impl_node = ImplementationNode(
            qualified_name=member.qualified_name,
            kind="implementation",
            implementation=source_text,
            impl_embedding=[],
            source=member.source if hasattr(member, 'source') else "",
            layer=member.layer if hasattr(member, 'layer') else "dependency",
        )

        result.implementations.append(impl_node)
        result.implementation_refs.append(ImplementationRef(
            member_refid=refid,
            implementation=impl_node,
        ))
        impl_count += 1

    print(f"  Implementations extracted: {impl_count} (skipped: {skip_count})")
```

- [ ] **Step 2:** Call `extract_implementations()` in `parse_xml_dir()`, after `_resolve_concept_constraints(result)` and before `return result`.

- [ ] **Step 3:** Verify parser still works:

```bash
cd /Users/danielnewman/dev/Doxygen-Dependency-Parser && python -m pytest tests/test_parser.py -v
```

---

## Task 8: Persist `ImplementationNode`s and `HAS_IMPLEMENTATION` relationships

**Repo:** Doxygen-Dependency-Parser  
**File:** `src/doxygen_index/neo4j_backend.py`

- [ ] **Step 1:** Add `ImplementationNode` import and `ImplementationRef` import.

- [ ] **Step 2:** Add `ImplementationNode` cleanup to `clear_source()` — delete ImplementationNodes before members:

```python
        ("MATCH (impl:ImplementationNode {source: $src}) DETACH DELETE impl",
         {"src": source}),
```

- [ ] **Step 3:** Add `result.implementations` to the `batch_refs` / `batch_labels` loop in `write_result()`:

```python
    batch_refs: list[list] = [
        result.files, result.namespaces, result.classes,
        result.enums, result.unions, result.interfaces, result.concepts,
        result.methods, result.attributes, result.enum_values,
        result.defines, result.functions,
        result.implementations,  # <-- ADD
    ]
    batch_labels = [
        "Files", "Namespaces", "Classes", "Enums", "Unions",
        "Interfaces", "Concepts", "Methods", "Attributes", "EnumValues",
        "Defines", "Functions",
        "Implementations",  # <-- ADD
    ]
```

- [ ] **Step 4:** Add `_write_implementation_relationships()` function and call it in `write_result()`:

```python
def _write_implementation_relationships(result: ParseResult) -> None:
    """Create HAS_IMPLEMENTATION relationships from members to ImplementationNodes."""
    if not result.implementation_refs:
        print("  Relationships: HAS_IMPLEMENTATION (0 edges)")
        return

    member_by_refid: dict[str, object] = {}
    for node_list in [result.methods, result.attributes, result.enum_values,
                      result.defines, result.functions]:
        for node in node_list:
            member_by_refid[node.refid] = node

    impl_by_qname: dict[str, object] = {}
    for impl in result.implementations:
        impl_by_qname[impl.qualified_name] = impl

    success, failed = 0, 0
    for ref in result.implementation_refs:
        member = member_by_refid.get(ref.member_refid)
        impl = impl_by_qname.get(ref.implementation.qualified_name)
        if member is None or impl is None:
            failed += 1
            continue
        try:
            member.implementation_ref.connect(impl)
            success += 1
        except Exception as e:
            print(f"Warning: Could not connect HAS_IMPLEMENTATION for "
                  f"{ref.member_refid}: {e}", file=sys.stderr)
            failed += 1

    print(f"  Relationships: HAS_IMPLEMENTATION ({success} edges, {failed} failed)")
```

- [ ] **Step 5:** Add `ImplementationNode` cleanup to `clear_all()`.

- [ ] **Step 6:** Verify module imports correctly:

```bash
cd /Users/danielnewman/dev/Doxygen-Dependency-Parser && python -c "from doxygen_index.neo4j_backend import write_result; print('OK')"
```

---

## Task 9: Add tests for `extract_implementations()`

**Repo:** Doxygen-Dependency-Parser  
**File:** `tests/test_parser.py`

- [ ] **Step 1:** Add `TestExtractImplementations` class with tests for:
  - Members with bodystart/bodyend get `body_start`/`body_end` populated
  - `extract_implementations()` creates `ImplementationNode`s for methods with bodies
  - ImplementationNode contains correct source text
  - ImplementationRef links member refid to ImplementationNode
  - Members without body locations get `body_start=0`, `body_end=0` and no implementation
  - Missing source files are skipped with a warning

- [ ] **Step 2:** Run the tests:

```bash
cd /Users/danielnewman/dev/Doxygen-Dependency-Parser && python -m pytest tests/test_parser.py -v -k "TestExtractImplementations"
```

---

## Task 10: Run full test suites and fix failures

**Repo:** Both

- [ ] **Step 1:** Run codegraph tests:

```bash
cd /Users/danielnewman/dev/codegraph && .venv/bin/python -m pytest tests/ -x -v
```

- [ ] **Step 2:** Run Doxygen Dependency Parser tests:

```bash
cd /Users/danielnewman/dev/Doxygen-Dependency-Parser && python -m pytest tests/ -x -v
```

- [ ] **Step 3:** Fix any import errors, test failures, or compatibility issues.

---

## Task 11: Commit codegraph changes

**Repo:** codegraph

- [ ] **Step 1:** Stage and commit:

```bash
cd /Users/danielnewman/dev/codegraph
git add src/codegraph/models/member.py \
       src/codegraph/__init__.py \
       tests/data/method_node_full.json \
       tests/data/function_node_full.json \
       tests/data/attribute_node_full.json \
       tests/data/define_node_full.json \
       tests/data/enum_value_node_full.json \
       tests/member/test_member_search_fields.py
git commit -m "feat: add body_start/body_end properties to _MemberMixin for implementation extraction

- Add body_start and body_end IntegerProperty fields to _MemberMixin
- Fields store Doxygen bodystart/bodyend line numbers for locating
  implementation source code
- Not included in _llm_fields (extraction plumbing, not LLM context)
- Source file resolved via existing DEFINED_IN → FileNode relationship
- Update member test fixtures and add body location tests"
```

---

## Task 12: Commit Doxygen Dependency Parser changes

**Repo:** Doxygen-Dependency-Parser

- [ ] **Step 1:** Stage and commit:

```bash
cd /Users/danielnewman/dev/Doxygen-Dependency-Parser
git add src/doxygen_index/parser.py \
       src/doxygen_index/neo4j_backend.py \
       tests/test_parser.py
git commit -m "feat: extract implementation source code from Doxygen body locations

- Parse bodystart/bodyend from <location> XML elements and store
  as body_start/body_end on member nodes
- Add ImplementationRef dataclass and implementations list to ParseResult
- Add extract_implementations() to read source files using body_start/body_end
  line ranges and create ImplementationNode instances
- Persist ImplementationNodes and HAS_IMPLEMENTATION relationships in
  neo4j_backend.py
- Clean up ImplementationNodes when clearing source data
- Embeddings deferred: impl_embedding stays empty"
```

---

## Task 13: Update codegraph dependency and verify end-to-end

**Repo:** Doxygen-Dependency-Parser

- [ ] **Step 1:** Verify that the codegraph version in the Doxygen Dependency Parser's virtual environment includes the new fields:

```bash
cd /Users/danielnewman/dev/Doxygen-Dependency-Parser && pip install -e /Users/danielnewman/dev/codegraph
```

- [ ] **Step 2:** Run the full test suite again to confirm everything works end-to-end:

```bash
cd /Users/danielnewman/dev/codegraph && .venv/bin/python -m pytest tests/ -x -q
cd /Users/danielnewman/dev/Doxygen-Dependency-Parser && python -m pytest tests/ -x -q
```