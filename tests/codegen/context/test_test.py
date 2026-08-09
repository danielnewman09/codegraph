"""Test-export tests (Phase 3) — TestNode → Catch2 scaffolding.

The design pipeline emits test structure (test/step descriptions,
assertion operator + operands) but not step code, so generated tests
are honest scaffolding: TEST_CASE + documented TODO comments.
"""

from __future__ import annotations

import json
from pathlib import Path

from codegraph.codegen import generate
from codegraph.graph import LayerGraph

GOLDEN = Path(__file__).resolve().parent.parent / "golden" / "design_layergraph.json"

_SPLIT = json.loads(GOLDEN.read_text())


def _test_node(**overrides):
    data = {
        "type": "TestNode",
        "name": "test_thing",
        "qualified_name": "vm::ns::test_thing",
        "kind": "test",
        "description": "Verify the thing works.",
        "source": "test",
        "tags": ["design"],
    }
    data.update(overrides)
    return data


def _test_graph(children):
    """An HLR → LLR → TestNode graph (the design-pipeline arrangement)."""
    return LayerGraph.deserialize([{
        "type": "HLR", "name": "HLR", "qualified_name": "HLR",
        "source": "test", "tags": ["design"],
        "composes": [{
            "type": "LLR", "name": "llr_x", "qualified_name": "llr_x",
            "source": "test", "tags": ["design"],
            "composes": [_test_node(composes=children)],
        }],
    }])


class TestTestContext:
    def test_test_ctx_composes_steps_and_assertions(self):
        graph = _test_graph([
            {"type": "TestStepNode", "name": "s2", "qualified_name": "step::s2",
             "kind": "test_step", "description": "Second", "order": "1",
             "source": "test", "tags": ["design"]},
            {"type": "TestStepNode", "name": "s1", "qualified_name": "step::s1",
             "kind": "test_step", "description": "First", "order": "0",
             "source": "test", "tags": ["design"]},
            {"type": "AssertionNode", "name": "a1", "qualified_name": "cond::a1",
             "kind": "assertion", "operator": "==", "phase": "post",
             "source": "test", "tags": ["design"],
             "edges": [
                 {"relation_type": "LEFT_OPERAND", "target_type": "LiteralNode",
                  "target_uid": "lit-1"},
                 {"relation_type": "RIGHT_OPERAND", "target_type": "AttributeNode",
                  "target_uid": "attr-1"},
             ]},
        ])
        # literals/attrs resolve as operands
        test = next(e for e in graph._all_entries()
                    if type(e.node).__name__ == "TestNode")
        from codegraph.codegen.context import BuildState
        from codegraph.codegen.context import test as test_mod
        state = BuildState(graph=graph, flat=graph._flat_index())
        ctx = test_mod.build_context(test, state)
        assert ctx["name"] == "test_thing"
        assert [s["name"] for s in ctx["steps"]] == ["s1", "s2"]
        assert ctx["steps"][0]["description"] == "First"
        assert ctx["assertions"][0]["operator"] == "=="
        # operands resolve to '' (targets absent from this graph)
        assert ctx["assertions"][0]["left_operand"] == ""
        assert ctx["assertions"][0]["right_operand"] == ""

    def test_operands_resolve(self):
        """LEFT_OPERAND/RIGHT_OPERAND → value/name via the flat index."""
        graph = LayerGraph.deserialize([
            {"type": "LiteralNode", "name": "true", "value": "true",
             "qualified_name": "literal::true", "source": "test", "tags": ["design"],
             "uid": "lit-1"},
            {"type": "AttributeNode", "name": "error_state",
             "qualified_name": "MigrationManager::error_state",
             "source": "test", "tags": ["design"], "uid": "attr-1"},
            {"type": "AssertionNode", "name": "a1", "qualified_name": "cond::a1",
             "kind": "assertion", "operator": "is_true", "phase": "post",
             "source": "test", "tags": ["design"],
             "edges": [
                 {"relation_type": "LEFT_OPERAND", "target_type": "LiteralNode",
                  "target_uid": "lit-1"},
                 {"relation_type": "RIGHT_OPERAND", "target_type": "AttributeNode",
                  "target_uid": "attr-1"},
             ]},
        ])
        from codegraph.codegen.context import BuildState
        from codegraph.codegen.context import test as test_mod
        state = BuildState(graph=graph, flat=graph._flat_index())
        entry = next(e for e in graph._all_entries()
                     if type(e.node).__name__ == "AssertionNode")
        ctx = test_mod.build_context(entry, state)
        assert ctx["left_operand"] == "true"
        assert ctx["right_operand"] == "error_state"


class TestTestRender:
    def test_test_files_planned_and_rendered(self):
        result = generate(_SPLIT)
        test_files = {p: t for p, t in result.files.items() if p.startswith("tests/")}
        assert len(test_files) == 9
        text = test_files["tests/test_duplicate_version_rejected.cpp"]
        assert text.startswith("// GENERATED by codegraph-codegen")
        assert (
            'TEST_CASE("test_duplicate_version_rejected", '
            '"vm::migration_registration::test_duplicate_version_rejected")' in text
        )
        # steps documented by name + description; assertions by operator
        assert "reg_dup_invoke_register_second: Invoke register_migration" in text
        assert "Assertion (post): error_state == DuplicateVersionError" in text
        assert "TODO(codegen): test-step body" in text
        assert "TODO(codegen): assertion body" in text

    def test_deterministic(self):
        a = generate(_SPLIT)
        b = generate(_SPLIT)
        assert a.files == b.files

    def test_output_dir_writes_tests(self, tmp_path: Path):
        generate(_SPLIT, output_dir=tmp_path)
        assert (tmp_path / "tests/test_duplicate_version_rejected.cpp").is_file()
