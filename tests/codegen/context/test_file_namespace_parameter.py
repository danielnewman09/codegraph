"""FileNode / NamespaceNode / ParameterNode context builder tests."""

from __future__ import annotations

from codegraph.codegen.context import file as file_builder
from codegraph.codegen.context import namespace as namespace_builder
from codegraph.codegen.context import parameter as parameter_builder


class TestFileNode:
    def test_file_scalars(self, make_state, find_entry):
        graph, state = make_state([{
            "type": "FileNode",
            "name": "DataAccessObject.hpp",
            "path": "include/cpp_sqlite/DataAccessObject.hpp",
            "include_guard": "DATA_ACCESS_OBJECT_HPP",
            "include_directives": ["<vector>", '"Widget.hpp"'],
            "namespace_leading_blank_lines": 1,
            "namespace_trailing_blank_lines": 1,
            "language": "C++",  # legacy Doxygen casing — must normalize
            "source": "test",
            "tags": ["as-built"],
        }])
        ctx = file_builder.build_context(find_entry(graph, type_name="FileNode"), state)
        assert ctx["path"] == "include/cpp_sqlite/DataAccessObject.hpp"
        assert ctx["guard"] == "DATA_ACCESS_OBJECT_HPP"
        assert ctx["language"] == "cpp"  # normalize_language('C++') → cpp
        assert ctx["includes"] == ["<vector>", '"Widget.hpp"']
        assert ctx["namespace_leading_blank_lines"] == 1
        assert ctx["namespace_trailing_blank_lines"] == 1
        assert ctx["forward_decls"] == []

    def test_includes_from_references(self, make_state, find_entry):
        graph, state = make_state([
            {
                "type": "FileNode",
                "name": "main.hpp",
                "path": "include/app/main.hpp",
                "language": "cpp",
                "source": "test",
                "tags": ["as-built"],
                "edges": [
                    {"relation_type": "INCLUDES", "target_uid": "include/lib/base.hpp",
                     "target_type": "FileNode"},
                ],
            },
            {
                "type": "FileNode",
                "name": "base.hpp",
                "path": "include/lib/base.hpp",
                "language": "cpp",
                "source": "test",
                "tags": ["as-built"],
            },
        ])
        ctx = file_builder.build_context(find_entry(graph, type_name="FileNode", name="main.hpp"), state)
        assert ctx["includes"] == ['"include/lib/base.hpp"']


class TestNamespaceNode:
    def test_namespace_with_compound_blocks(self, make_state, find_entry):
        graph, state = make_state([{
            "type": "NamespaceNode",
            "name": "cpp_sqlite",
            "qualified_name": "cpp_sqlite",
            "kind": "namespace",
            "source": "test",
            "tags": ["design"],
            "composes": [
                {
                    "type": "ClassNode",
                    "name": "MigrationManager",
                    "qualified_name": "cpp_sqlite::MigrationManager",
                    "kind": "class",
                    "source": "test",
                    "tags": ["design"],
                },
            ],
        }])
        ctx = namespace_builder.build_context(find_entry(graph, type_name="NamespaceNode"), state)
        assert ctx["name"] == "cpp_sqlite"
        assert [b["type"] for b in ctx["blocks"]] == ["ClassNode"]
        assert ctx["blocks"][0]["name"] == "MigrationManager"

    def test_nested_namespace(self, make_state, find_entry):
        graph, state = make_state([{
            "type": "NamespaceNode",
            "name": "app",
            "qualified_name": "app",
            "kind": "namespace",
            "source": "test",
            "tags": ["design"],
            "composes": [{
                "type": "NamespaceNode",
                "name": "inner",
                "qualified_name": "app::inner",
                "kind": "namespace",
                "source": "test",
                "tags": ["design"],
            }],
        }])
        ctx = namespace_builder.build_context(find_entry(graph, type_name="NamespaceNode"), state)
        assert ctx["blocks"][0]["type"] == "NamespaceNode"
        assert ctx["blocks"][0]["name"] == "inner"


class TestParameterNode:
    def test_parameter_context(self, make_state, find_entry):
        graph, state = make_state([{
            # ParameterNode serialization uses the ``node_type``
            # discriminator so its C++ ``type`` property survives.
            "node_type": "ParameterNode",
            "name": "x",
            "type": "const std::string&",
            "default_value": "\"hello\"",
            "position": 2,
            "member_refid": "cpp_sqlite::apply",
            "source": "test",
            "tags": ["as-built"],
        }])
        ctx = parameter_builder.build_context(find_entry(graph, type_name="ParameterNode"), state)
        assert ctx["name"] == "x"
        assert ctx["type"] == "const std::string&"
        assert ctx["default_value"] == '"hello"'
        assert ctx["position"] == 2
