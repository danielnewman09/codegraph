"""TemplatePack resolution + rendering tests (spec D3, R2).

Pins: per-node-type directory resolution (kind → _decl fallback →
default), D11 kind aliasing, custom pack override, degradation to the
explicit ``default.j2`` TODO marker, and the normalized deterministic
output contract.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from codegraph.codegen.pack import (
    KIND_ALIASES,
    KIND_ALIASES_BY_TYPE,
    PACK_SKIPPED,
    TemplatePack,
    builtin_pack_dir,
)


@pytest.fixture
def pack():
    return TemplatePack(language="cpp")


class TestResolve:
    def test_kind_file(self, pack):
        assert pack.resolve("ClassNode", "class") == "ClassNode/class.j2"

    def test_kind_variant_file(self, pack):
        assert pack.resolve("ClassNode", "struct") == "ClassNode/struct.j2"

    def test_decl_fallback_for_member_kinds(self, pack):
        """MethodNode kind='method' has no method.j2 — the _decl form wins."""
        assert pack.resolve("MethodNode", "method") == "MethodNode/method_decl.j2"
        assert pack.resolve("FunctionNode", "function") == "FunctionNode/function_decl.j2"

    def test_decl_variant_explicit(self, pack):
        assert pack.resolve("MethodNode", "method", variant="defn") == (
            "MethodNode/method_defn.j2"
        )

    def test_enum_kind_alias(self, pack):
        assert KIND_ALIASES["enum_value"] == "enumvalue"
        assert pack.resolve("EnumValueNode", "enum_value") == (
            "EnumValueNode/enumvalue.j2"
        )

    def test_as_built_kind_aliases(self, pack):
        """Doxygen as-built exports carry memberdef kinds — methods are
        kind="function", attributes kind="variable".  These must alias to
        the pack's design vocabulary or every as-built member degrades to
        an "unsupported" TODO stub (D6 default.j2)."""
        assert KIND_ALIASES_BY_TYPE["MethodNode"]["function"] == "method"
        assert KIND_ALIASES_BY_TYPE["AttributeNode"]["variable"] == "attribute"
        assert pack.resolve("MethodNode", "function") == "MethodNode/method_decl.j2"
        assert pack.resolve("MethodNode", "function", variant="defn") == (
            "MethodNode/method_defn.j2"
        )
        assert pack.resolve("AttributeNode", "variable") == (
            "AttributeNode/attribute.j2"
        )
        # typedef stays a distinct kind — not aliased to attribute.
        assert pack.resolve("AttributeNode", "typedef") == "AttributeNode/typedef.j2"
        # Defensive symmetry: a design "method"-kind FunctionNode resolves.
        assert pack.resolve("FunctionNode", "method") == "FunctionNode/function_decl.j2"

    def test_node_default_fallback(self, pack):
        # A bogus kind falls back to the node default, then pack default.
        assert pack.resolve("ClassNode", "bogus_kind") == "default.j2"

    def test_pack_level_default_degrades_unknown_types(self, pack):
        """The pack-level default.j2 catches everything (D6: explicit TODO)."""
        assert pack.resolve("NoSuchNode", "x") == "default.j2"

    def test_missing_everything_raises(self, tmp_path: Path):
        """Custom pack without even a default.j2 must raise explicitly."""
        (tmp_path / "ClassNode").mkdir()
        (tmp_path / "ClassNode" / "class.j2").write_text("x", encoding="utf-8")
        custom = TemplatePack(language="cpp", directory=tmp_path)
        with pytest.raises(FileNotFoundError):
            custom.resolve("NoSuchNode", "x")


class TestCustomPack:
    def test_directory_override(self, tmp_path: Path):
        (tmp_path / "ClassNode").mkdir()
        (tmp_path / "ClassNode" / "class.j2").write_text(
            "custom {{ node.name }}", encoding="utf-8"
        )
        custom = TemplatePack(language="cpp", directory=tmp_path)
        ctx = {"type": "ClassNode", "kind": "class", "name": "Widget"}
        assert custom.render_node(ctx).strip() == "custom Widget"

    def test_missing_pack_dir_raises(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            TemplatePack(language="cpp", directory=tmp_path / "nope")

    def test_builtin_pack_dir_exists(self):
        assert (builtin_pack_dir("cpp") / "file_header.j2").is_file()


class TestRenderNode:
    def test_method_decl(self, pack):
        text = pack.render_node({
            "type": "MethodNode",
            "kind": "method",
            "name": "apply",
            "declaration": "MigrationResult apply()",
            "brief": "Applies migrations.",
            "detailed": "",
            "uid": "",
        })
        assert text == "/// Applies migrations.\nMigrationResult apply();"

    def test_unknown_type_degrades_explicitly(self, pack):
        """D6: unknown node types render an explicit TODO, never nothing."""
        text = pack.render_node({"type": "WidgetNode", "kind": "x"})
        assert "TODO(codegen): unsupported WidgetNode" in text

    def test_skipped_marker(self, pack):
        text = pack.environment.get_template("_skipped.j2").render(
            node={"type": "HLR", "qualified_name": "HLR X"}, pack=pack
        )
        assert "skipped: HLR" in text


class TestDeterminism:
    def test_source_fragment_renders_verbatim_inside_namespace(self, pack):
        fragment = {
            "type": "SourceFragmentNode",
            "kind": "unassigned_source_fragment",
            "text": "#pragma clang diagnostic push\n",
        }
        assert pack.render_node(fragment) == "#pragma clang diagnostic push"

    def test_render_is_byte_stable(self, pack):
        ctx = {
            "type": "ClassNode",
            "kind": "class",
            "name": "Widget",
            "qualified_name": "ns::Widget",
            "uid": "abc",
            "brief": "A widget.",
            "sections": [
                {
                    "access": "public",
                    "members": [
                        {"type": "MethodNode", "kind": "method", "name": "go",
                         "declaration": "void go()", "brief": "", "detailed": "",
                         "uid": ""},
                    ],
                },
            ],
            "template_params": [],
            "bases": [],
            "interfaces": [],
        }
        file_ctx = {
            "type": "FileNode", "kind": "header", "path": "include/ns/Widget.hpp",
            "guard": "INCLUDE_NS_WIDGET_HPP", "language": "cpp", "includes": [],
            "forward_decls": [], "namespaces": [{"name": "ns", "blocks": [ctx],
            "namespaces": []}], "blocks": [],
        }
        a = pack.render_file(file_ctx)
        b = pack.render_file(file_ctx)
        assert a == b
        assert a.endswith("\n")
        assert "\n\n\n" not in a  # normalized blank lines
