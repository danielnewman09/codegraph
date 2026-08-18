"""Declared-skip builder tests — scaffolding renders nothing (D11).

Test scaffolding is Phase 3 (Catch2 export): ``TestNode`` /
``TestStepNode`` / ``AssertionNode`` now have real builders (see
``test_test.py``); ``LiteralNode``, ``HLR``/``LLR``, ``TestFixtureNode``
and the project types remain declared skips — their builders return
None and reasons are declared in SKIP_REASONS (the completeness gate
already asserts coverage).
"""

from __future__ import annotations

import pytest

from codegraph.codegen.context import BUILDERS, SKIP_REASONS

from codegraph.graph import LayerGraph
from tests.codegen.context.conftest import key_document as _kd


def _deser(data):
    return LayerGraph.deserialize(_kd(data))


SKIP_SAMPLE_DICTS = {
    "LiteralNode": {"type": "LiteralNode", "value": "30", "value_type": "int",
                    "qualified_name": "literal::30", "source": "test", "tags": ["design"]},
    "HLR": {"type": "HLR", "name": "Database Migration Manager",
            "qualified_name": "Database Migration Manager", "source": "test",
            "tags": ["design"]},
    "LLR": {"type": "LLR", "name": "llr_migration_apply",
            "qualified_name": "llr_migration_apply", "source": "test", "tags": ["design"]},
    "TestFixtureNode": {"type": "TestFixtureNode", "name": "f1", "qualified_name": "f1",
                        "source": "test", "tags": ["design"]},
    "Component": {"type": "Component", "name": "comp", "qualified_name": "comp",
                  "source": "test", "tags": ["design"]},
    "Dependency": {"type": "Dependency", "name": "dep", "qualified_name": "dep",
                   "source": "test", "tags": ["design"]},
    "Language": {"type": "Language", "name": "cpp", "qualified_name": "cpp",
                 "source": "test", "tags": ["design"]},
    "ProjectMeta": {"type": "ProjectMeta", "name": "proj", "qualified_name": "proj",
                    "source": "test", "tags": ["design"]},
}


class TestDeclaredSkips:
    @pytest.mark.parametrize("node_type", sorted(SKIP_SAMPLE_DICTS))
    def test_skip_builder_returns_none(self, node_type, deserialize_graph):
        from codegraph.graph import LayerGraph


        data = [SKIP_SAMPLE_DICTS[node_type]]
        graph = _deser(data)
        entry = next(iter(graph._all_entries()))
        builder = BUILDERS[node_type]
        assert builder(entry, None) is None

    @pytest.mark.parametrize("node_type", sorted(SKIP_SAMPLE_DICTS))
    def test_skip_reason_declared(self, node_type):
        assert node_type in SKIP_REASONS
        assert SKIP_REASONS[node_type].strip()

    def test_no_skip_for_codegen_relevant_types(self):
        for node_type in ("ClassNode", "MethodNode", "AttributeNode", "EnumNode",
                          "FileNode", "NamespaceNode"):
            assert node_type not in SKIP_REASONS

    def test_test_scaffolding_no_longer_skipped(self):
        """Phase 3: TestNode/TestStepNode/AssertionNode have real builders."""
        for node_type in ("TestNode", "TestStepNode", "AssertionNode"):
            assert node_type not in SKIP_REASONS
            assert node_type not in getattr(BUILDERS[node_type], "skip_reason", "")
