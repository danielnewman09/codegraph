"""Focused codegen tests for Priority-1 as-built fidelity rendering.

Work package 2/3 slices exercised without the full index→generate→compare
loop: in-class bodies render inside the class; blank-line separators are
derived from indexed span gaps; header-resident out-of-line bodies render at
their source position; namespace regions re-open around file-level content;
the empty namespace shell survives; as-built files never invent forward
declarations or includes.

These tests build small LayerGraphs directly (no doxygen) so the renderer
behavior is pinned independently of the parser.
"""

from __future__ import annotations

import json

from codegraph.codegen import generate
from codegraph.codegen.context import CodegenContextBuilder, BuildState
from codegraph.codegen.planner import FilePlanner
from codegraph.codegen.pack import TemplatePack
from codegraph.graph import LayerGraph
from tests.codegen.context.conftest import key_document as _kd

# TODO Move this into a conftest to avoid repetition
def _deser(data):
    return LayerGraph.deserialize(_kd(data))



def _gen(nodes: list[dict]) -> dict:
    graph = _deser(nodes)
    builder = CodegenContextBuilder()
    output = builder.build(graph, FilePlanner())
    pack = TemplatePack(language="cpp")
    pack.as_built = output.as_built
    return {
        path: pack.render_file(ctx)
        for path, ctx in output.files.items()
    }


def _file_node(path: str) -> dict:
    return {
        "type": "FileNode",
        "name": path.rsplit("/", 1)[-1],
        "path": path,
        "language": "C++",
        "source": "test",
        "tags": ["as-built"],
    }


class TestInClassBodies:
    def test_in_class_body_renders_inside_class(self):
        files = _gen([
            _file_node("src/A.hpp"),
            {
                "type": "ClassNode",
                "name": "A",
                "qualified_name": "ns::A",
                "kind": "class",
                "file_path": "src/A.hpp",
                "source": "test",
                "tags": ["as-built"],
                "composes": [
                    {
                        "type": "MethodNode",
                        "name": "get",
                        "qualified_name": "ns::A::get",
                        "kind": "method",
                        "type_signature": "int",
                        "argsstring": "() const",
                        "definition": "int ns::A::get",
                        "body": "int get() const\n{\n  return value_;\n}",
                        "body_start": 4,
                        "body_end": 7,
                        "body_file": "src/A.hpp",
                        "file_path": "src/A.hpp",
                        "line_number": 4,
                        "start_line": 4,
                        "end_line": 7,
                        "source": "test",
                        "tags": ["as-built"],
                    },
                ],
            },
        ])
        text = files["src/A.hpp"]
        # The in-class body renders verbatim inside the class (indented by
        # the class-body indent, which clang-format normalizes), never as a
        # standalone declaration.
        assert "int get() const\n        {\n          return value_;\n        }" in text
        assert "int get() const;" not in text


class TestBlankSeparators:
    def test_blank_line_derived_from_span_gap(self):
        files = _gen([
            _file_node("src/A.hpp"),
            {
                "type": "ClassNode",
                "name": "A",
                "qualified_name": "ns::A",
                "kind": "class",
                "file_path": "src/A.hpp",
                "start_line": 2,
                "end_line": 8,
                "source": "test",
                "tags": ["as-built"],
                "composes": [
                    {
                        "type": "AttributeNode",
                        "name": "x",
                        "qualified_name": "ns::A::x",
                        "kind": "attribute",
                        "type_signature": "int",
                        "file_path": "src/A.hpp",
                        "line_number": 4,
                        "start_line": 4,
                        "end_line": 4,
                        "source": "test",
                        "tags": ["as-built"],
                    },
                    {
                        "type": "AttributeNode",
                        "name": "y",
                        "qualified_name": "ns::A::y",
                        "kind": "attribute",
                        "type_signature": "int",
                        "file_path": "src/A.hpp",
                        "line_number": 6,
                        "start_line": 6,
                        "end_line": 6,
                        "source": "test",
                        "tags": ["as-built"],
                    },
                ],
            },
        ])
        text = files["src/A.hpp"]
        assert "int x;\n\n        int y;" in text, text

class TestHeaderOutOfLineBody:
    def test_header_resident_body_renders_at_source_position(self):
        files = _gen([
            {
                **_file_node("src/A.hpp"),
                "namespace_regions": [
                    {"name": "ns", "open_line": 1, "close_line": 12,
                     "leading_blank_lines": 0, "trailing_blank_lines": 0},
                ],
                "namespace_leading_blank_lines": 1,
                "namespace_trailing_blank_lines": 0,
                "guard": "A_HPP",
                "guard_leading_blank_lines": 0,
            },
            {
                "type": "ClassNode",
                "name": "A",
                "qualified_name": "ns::A",
                "kind": "class",
                "file_path": "src/A.hpp",
                "start_line": 2,
                "end_line": 5,
                "source": "test",
                "tags": ["as-built"],
            },
            {
                "type": "MethodNode",
                "name": "run",
                "qualified_name": "ns::A::run",
                "kind": "method",
                "type_signature": "void",
                "argsstring": "()",
                "definition": "void ns::A::run",
                "file_path": "src/A.hpp",
                "line_number": 4,
                "start_line": 4,
                "end_line": 4,
                "body": "void A::run()\n{\n  work();\n}",
                "body_start": 8,
                "body_end": 11,
                "body_file": "src/A.hpp",
                "source": "test",
                "tags": ["as-built"],
            },
        ])
        text = files["src/A.hpp"]
        assert "void A::run()" in text
        assert "work();" in text


class TestNamespaceRegions:
    def test_reopened_namespace_renders_two_regions(self):
        files = _gen([
            {
                **_file_node("src/A.hpp"),
                "namespace_regions": [
                    {"name": "ns", "open_line": 1, "close_line": 4,
                     "leading_blank_lines": 0, "trailing_blank_lines": 0},
                    {"name": "ns", "open_line": 8, "close_line": 11,
                     "leading_blank_lines": 0, "trailing_blank_lines": 0},
                ],
                "include_directives": ["\"dep.hpp\""],
                "include_directive_lines": [7],
                "guard": "A_HPP",
                "guard_leading_blank_lines": 0,
            },
            {
                "type": "ClassNode",
                "name": "A",
                "qualified_name": "ns::A",
                "kind": "class",
                "file_path": "src/A.hpp",
                "start_line": 2,
                "end_line": 4,
                "source": "test",
                "tags": ["as-built"],
            },
            {
                "type": "SourceFragmentNode",
                "name": "src/A.hpp#6-6",
                "qualified_name": "src/A.hpp#6-6",
                "kind": "unassigned_source_fragment",
                "file_path": "src/A.hpp",
                "start_line": 6,
                "end_line": 6,
                "placement": "",
                "text": "// file-level comment\n",
                "source": "test",
                "tags": ["as-built"],
            },
        ])
        text = files["src/A.hpp"]
        # first region: class; file-level: comment + include; second region re-opens
        assert text.index("class A") < text.index("// file-level comment")
        assert text.index("// file-level comment") < text.index('#include "dep.hpp"')
        assert text.index('#include "dep.hpp"') < text.index("namespace ns {", text.index("namespace ns {") + 1)
        assert text.count("namespace ns {") == 2
        assert text.count("} // namespace ns") == 2


class TestEmptyNamespaceShell:
    def test_empty_namespace_shell_survives(self):
        files = _gen([
            {
                **_file_node("src/empty.cpp"),
                "kind": "source",
                "namespace_name": "ns",
                "namespace_leading_blank_lines": 2,
                "namespace_trailing_blank_lines": 2,
                "include_directives": ["\"a.hpp\""],
                "include_directive_lines": [1],
            },
        ])
        text = files["src/empty.cpp"]
        assert "namespace ns" in text
        assert "} // namespace ns" in text


class TestAsBuiltNeverInvents:
    def test_forward_decls_not_invented_in_as_built(self):
        """Constraint 8: as-built generation renders what was indexed — a
        DEPENDS_ON edge must not synthesize a forward declaration absent
        from the source."""
        files = _gen([
            _file_node("src/A.hpp"),
            {
                "type": "ClassNode",
                "name": "A",
                "qualified_name": "ns::A",
                "kind": "class",
                "file_path": "src/A.hpp",
                "start_line": 2,
                "end_line": 5,
                "source": "test",
                "tags": ["as-built"],
                "edges": [
                    {"relation_type": "DEPENDS_ON", "target_type": "ClassNode",
                     "target_uid": "b-uid"},
                ],
            },
            {
                "type": "ClassNode",
                "name": "B",
                "qualified_name": "ns::B",
                "kind": "class",
                "file_path": "src/B.hpp",
                "start_line": 2,
                "end_line": 5,
                "source": "test",
                "tags": ["as-built"],
            },
        ])
        text = files["src/A.hpp"]
        assert "class B;" not in text

    def test_includes_come_from_the_index(self):
        """WP3.3 regression: as-built includes are the indexed ordered list —
        never inferred from graph relationships.  An INCLUDES edge to an
        unlisted target must not leak into the generated header."""
        files = _gen([
            {
                **_file_node("src/A.hpp"),
                "include_directives": ["<memory>", "", '"x.hpp"'],
                "include_directive_lines": [1, 0, 3],
                "guard": "A_HPP",
                "guard_leading_blank_lines": 0,
                "namespace_leading_blank_lines": 1,
                "namespace_trailing_blank_lines": 1,
            },
            {
                "type": "ClassNode",
                "name": "A",
                "qualified_name": "ns::A",
                "kind": "class",
                "file_path": "src/A.hpp",
                "start_line": 5,
                "end_line": 8,
                "source": "test",
                "tags": ["as-built"],
                "edges": [
                    {"relation_type": "INCLUDES", "target_type": "FileNode",
                     "target_uid": "b.hpp"},
                ],
            },
        ])
        text = files["src/A.hpp"]
        assert "#include <memory>" in text
        assert '#include "x.hpp"' in text
        # the INCLUDES edge target (b.hpp) is NOT invented
        assert "b.hpp" not in text
        # blank-line group separator preserved between the two groups
        assert "#include <memory>\n\n#include \"x.hpp\"" in text


class TestBaseSpelling:
    def test_source_spelled_bases_render(self):
        files = _gen([
            _file_node("src/E.hpp"),
            {
                "type": "ClassNode",
                "name": "E",
                "qualified_name": "ns::E",
                "kind": "class",
                "file_path": "src/E.hpp",
                "base_specifiers": ["public std::runtime_error"],
                "start_line": 2,
                "end_line": 4,
                "source": "test",
                "tags": ["as-built"],
            },
            {
                "type": "ClassNode",
                "name": "IsVector",
                "qualified_name": "ns::IsVector",
                "kind": "struct",
                "file_path": "src/E.hpp",
                "base_specifiers": ["std::false_type"],
                "start_line": 6,
                "end_line": 8,
                "source": "test",
                "tags": ["as-built"],
            },
        ])
        text = files["src/E.hpp"]
        assert "class E : public std::runtime_error" in text
        assert "struct IsVector : std::false_type" in text


class TestNestedEnumRender:
    def test_nested_enum_renders_inside_class(self):
        files = _gen([
            _file_node("src/W.hpp"),
            {
                "type": "ClassNode",
                "name": "W",
                "qualified_name": "ns::W",
                "kind": "class",
                "file_path": "src/W.hpp",
                "start_line": 2,
                "end_line": 10,
                "source": "test",
                "tags": ["as-built"],
                "composes": [
                    {
                        "type": "EnumNode",
                        "name": "Color",
                        "qualified_name": "ns::W::Color",
                        "kind": "enum",
                        "enum_class": True,
                        "underlying_type": "uint8_t",
                        "file_path": "src/W.hpp",
                        "start_line": 4,
                        "end_line": 8,
                        "visibility": "public",
                        "source": "test",
                        "tags": ["as-built"],
                        "composes": [
                            {
                                "type": "EnumValueNode",
                                "name": "RED",
                                "qualified_name": "ns::W::Color::RED",
                                "kind": "enumvalue",
                                "file_path": "src/W.hpp",
                                "start_line": 5,
                                "end_line": 5,
                                "source": "test",
                                "tags": ["as-built"],
                            },
                        ],
                    },
                ],
            },
        ])
        text = files["src/W.hpp"]
        assert "enum class Color : uint8_t" in text
        assert "RED" in text
        # the nested enum appears exactly once (inside the class only)
        assert text.count("enum class Color") == 1


class TestBuildStateAsBuilt:
    def test_as_built_detection_by_file_nodes(self):
        """As-built mode is FileNode-rooted provenance — a design graph
        tagged 'as-built' without FileNodes must not suppress forward decls."""
        design = _deser([
            {
                "type": "NamespaceNode",
                "name": "ns",
                "qualified_name": "ns",
                "source": "test",
                "tags": ["as-built", "design"],
                "composes": [
                    {
                        "type": "ClassNode",
                        "name": "A",
                        "qualified_name": "ns::A",
                        "kind": "class",
                        "source": "test",
                        "tags": ["as-built", "design"],
                    },
                ],
            },
        ])
        state = BuildState(graph=design, flat=design._flat_index())
        assert state.as_built is False


if __name__ == "__main__":
    import sys
    import pytest
    sys.exit(pytest.main([__file__, "-q"]))
