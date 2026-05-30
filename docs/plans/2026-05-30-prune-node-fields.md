# Prune Redundant Node Fields Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove redundant `description` field from CompoundNode and MemberNode, and remove unneeded `protection` field from CompoundNode (both already covered by `brief_description`/`detailed_description`; protection at compound level is rarely meaningful).

**Architecture:** Direct field deletions across two model files and corresponding test cleanup. No new files or restructures — pure pruning.

**Tech Stack:** Python 3.12, Pydantic v2, pytest

---

### Task 1: Remove fields from CompoundNode model

**Files:**
- Modify: `src/codegraph/nodes/compound_node.py`
- Test: `tests/test_nodes.py`

- [ ] **Step 1: Remove `description` and `protection` from CompoundNode**

Edit `src/codegraph/nodes/compound_node.py` — remove both `description` and `protection` field declarations (including their `#:` doc comments).

```python
# Remove this block (description):
    #: Full description (plain text or Markdown).
    description: str = ""

# Remove this block (protection):
    #: Access specifier / visibility for the compound's top-level
    #: declaration context. One of ``"public"``, ``"private"``,
    #: ``"protected"``, or ``""`` (unknown / default).
    protection: Literal["public", "private", "protected", ""] = ""
```

- [ ] **Step 2: Run tests to confirm failures**

Run: `pytest tests/test_nodes.py::TestCompoundNode -v`
Expected: FAIL — tests referencing `description` and `protection` will fail with ValidationError (extra fields) or unexpected keyword arguments.

- [ ] **Step 3: Update CompoundNode tests — remove `description` and `protection`**

Edit `tests/test_nodes.py` in the `TestCompoundNode` class:

1. `test_minimal_creation` (line ~133-135): Remove assertions for `c.description` and `c.protection`
2. `test_full_creation` (line ~151-172): Remove `description` and `protection` kwargs from construction and their assertions
3. `test_model_dump_roundtrip` (line ~208-215): Remove `description` and `protection` kwargs

After edits, `test_minimal_creation` should look like:

```python
    def test_minimal_creation(self):
        c = CompoundNode(qualified_name="calc::Calculator", kind="class")
        assert c.qualified_name == "calc::Calculator"
        assert c.name == ""
        assert c.kind == "class"
        assert c.layer == "design"
        assert c.refid == ""
        assert c.brief_description == ""
        assert c.detailed_description == ""
        assert c.base_classes == []
        assert c.file_path == ""
        assert c.line_number is None
        assert c.source == ""
        assert c.is_final is False
        assert c.is_abstract is False
```

`test_full_creation` construction:

```python
    def test_full_creation(self):
        c = CompoundNode(
            qualified_name="calc::Calculator",
            name="Calculator",
            kind="class",
            layer="as-built",
            refid="classcalc_1_1Calculator",
            brief_description="A simple calculator class",
            detailed_description="Performs arithmetic operations with precision tracking.",
            base_classes=["BaseCalc", "IPrintable"],
            file_path="/src/calculator.h",
            line_number=42,
            source="msd",
            is_final=True,
            is_abstract=False,
        )
        assert c.name == "Calculator"
        assert c.layer == "as-built"
        assert c.refid == "classcalc_1_1Calculator"
        assert c.brief_description == "A simple calculator class"
        assert c.detailed_description == "Performs arithmetic operations with precision tracking."
        assert c.base_classes == ["BaseCalc", "IPrintable"]
        assert c.file_path == "/src/calculator.h"
        assert c.line_number == 42
        assert c.source == "msd"
        assert c.is_final is True
        assert c.is_abstract is False
```

`test_model_dump_roundtrip` construction:

```python
    def test_model_dump_roundtrip(self):
        c = CompoundNode(
            qualified_name="calc::Calculator",
            name="Calculator",
            kind="class",
            layer="as-built",
            refid="ref123",
            brief_description="brief",
            detailed_description="detailed",
            base_classes=["Base"],
            file_path="/src/calc.h",
            line_number=42,
            source="msd",
            is_final=False,
            is_abstract=True,
        )
        data = c.model_dump()
        c2 = CompoundNode.model_validate(data)
        assert c == c2
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_nodes.py::TestCompoundNode -v`
Expected: All 8 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/codegraph/nodes/compound_node.py tests/test_nodes.py
git commit -m "refactor: remove description and protection from CompoundNode"
```

---

### Task 2: Remove `description` from MemberNode model

**Files:**
- Modify: `src/codegraph/nodes/member_node.py`
- Test: `tests/test_nodes.py`

- [ ] **Step 1: Remove `description` from MemberNode**

Edit `src/codegraph/nodes/member_node.py` — remove the `description` field declaration and its `#:` doc comment.

```python
# Remove this block:
    #: Full description (plain text or Markdown).
    description: str = ""
```

- [ ] **Step 2: Run tests to confirm failures**

Run: `pytest tests/test_nodes.py::TestMemberNode -v`
Expected: FAIL — tests referencing `description` will fail.

- [ ] **Step 3: Update MemberNode tests — remove `description`**

Edit `tests/test_nodes.py` in the `TestMemberNode` class:

1. `test_minimal_creation` (line ~233): Remove assertion for `m.description`
2. `test_full_creation` (line ~258): Remove `description` kwarg from construction
3. `test_model_dump_roundtrip` (line ~319): Remove `description` kwarg

After edits, `test_minimal_creation`:

```python
    def test_minimal_creation(self):
        m = MemberNode(qualified_name="calc::Calculator::add", kind="method")
        assert m.qualified_name == "calc::Calculator::add"
        assert m.name == ""
        assert m.kind == "method"
        assert m.layer == "design"
        assert m.refid == ""
        assert m.compound_refid == ""
        assert m.brief_description == ""
        assert m.detailed_description == ""
        assert m.type_signature == ""
        assert m.definition == ""
        assert m.argsstring == ""
        assert m.file_path == ""
        assert m.line_number is None
        assert m.source == ""
        assert m.protection == ""
        assert m.is_static is False
        assert m.is_const is False
        assert m.is_constexpr is False
        assert m.is_virtual is False
        assert m.is_inline is False
        assert m.is_explicit is False
```

`test_full_creation` construction — remove `description="Add two numbers",` line:

```python
    def test_full_creation(self):
        m = MemberNode(
            qualified_name="calc::Calculator::add",
            name="add",
            kind="method",
            layer="as-built",
            refid="classcalc_1_1Calculator_1a123",
            compound_refid="classcalc_1_1Calculator",
            brief_description="Addition operation",
            detailed_description="Adds two integers and returns the result.",
            type_signature="int",
            definition="int Calculator::add(int a, int b)",
            argsstring="(int a, int b)",
            file_path="/src/calculator.cpp",
            line_number=15,
            source="msd",
            protection="public",
            is_static=False,
            is_const=True,
            is_constexpr=False,
            is_virtual=False,
            is_inline=True,
            is_explicit=False,
        )
        assert m.name == "add"
        assert m.layer == "as-built"
        assert m.type_signature == "int"
        assert m.definition == "int Calculator::add(int a, int b)"
        assert m.argsstring == "(int a, int b)"
        assert m.compound_refid == "classcalc_1_1Calculator"
        assert m.protection == "public"
        assert m.is_const is True
        assert m.is_inline is True
```

`test_model_dump_roundtrip` construction — remove `description="desc",` line:

```python
    def test_model_dump_roundtrip(self):
        m = MemberNode(
            qualified_name="calc::Calculator::add",
            name="add",
            kind="method",
            layer="as-built",
            refid="ref123",
            compound_refid="compound_ref456",
            brief_description="brief",
            detailed_description="detailed",
            type_signature="int",
            definition="def",
            argsstring="(int a)",
            file_path="/src/calc.cpp",
            line_number=15,
            source="msd",
            protection="public",
            is_static=False,
            is_const=True,
            is_constexpr=False,
            is_virtual=False,
            is_inline=True,
            is_explicit=False,
        )
        data = m.model_dump()
        m2 = MemberNode.model_validate(data)
        assert m == m2
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_nodes.py::TestMemberNode -v`
Expected: All 7 tests PASS

- [ ] **Step 5: Run full test suite**

Run: `pytest tests/ -v`
Expected: All 64 tests PASS

- [ ] **Step 6: Commit**

```bash
git add src/codegraph/nodes/member_node.py tests/test_nodes.py
git commit -m "refactor: remove description from MemberNode"
```
