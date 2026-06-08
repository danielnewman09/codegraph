"""Tests for CodeGraphNode class methods.

Covers find_relationship_manager error paths, fetch_by_layer,
fetch_all_by_layer, deserialize error paths, serialize_relationships,
and serialize(fields=...) behaviour.
"""

import pytest
from neomodel import RelationshipTo

from codegraph.models.compound import ClassNode, InterfaceNode
from codegraph.models.file import FileNode
from codegraph.models.member import MethodNode, AttributeNode
from codegraph.models.namespace import NamespaceNode
from codegraph.models.tags import CodeGraphNode


class TestFindRelationshipManager:
    """Tests for CodeGraphNode.find_relationship_manager()."""

    def test_finds_matching_manager(self):
        """Finds the correct manager when relation_type + target match."""
        cls_node = ClassNode(name="TestClass", kind="class").save()
        meth_node = MethodNode(name="testMethod", kind="method").save()
        manager = CodeGraphNode.find_relationship_manager(
            cls_node, "COMPOSES", meth_node
        )
        assert manager is not None
        # Clean up
        cls_node.delete()
        meth_node.delete()

    def test_raises_on_unknown_relation(self):
        """Raises ValueError when no matching relationship exists."""
        cls_node = ClassNode(name="BadClass", kind="class").save()
        meth_node = MethodNode(name="BadMethod", kind="method").save()
        with pytest.raises(ValueError, match="No 'NONEXISTENT' relationship"):
            CodeGraphNode.find_relationship_manager(
                cls_node, "NONEXISTENT", meth_node
            )
        cls_node.delete()
        meth_node.delete()

    def test_raises_on_wrong_target_type(self):
        """Raises ValueError for a valid relation_type but wrong target type."""
        cls_node = ClassNode(name="WrongTarget", kind="class").save()
        file_node = FileNode(name="wrongfile", path="/wrong.h").save()
        # COMPOSES exists on ClassNode but targets MethodNode/AttributeNode/
        # NamespaceNode, not FileNode
        with pytest.raises(ValueError, match="No 'COMPOSES' relationship"):
            CodeGraphNode.find_relationship_manager(
                cls_node, "COMPOSES", file_node
            )
        cls_node.delete()
        file_node.delete()


class TestDeserializeErrorPaths:
    """Tests for CodeGraphNode.deserialize() error handling."""

    def test_missing_type_discriminator(self):
        """Raises ValueError when 'type' key is missing."""
        with pytest.raises(ValueError, match="missing the 'type' discriminator"):
            CodeGraphNode.deserialize({"name": "orphan"})

    def test_unknown_type(self):
        """Raises KeyError when type is not in the registry."""
        with pytest.raises(KeyError, match="Unknown node type"):
            CodeGraphNode.deserialize({"type": "FakeNode", "name": "x"})


class TestSerializeRelationships:
    """Tests for CodeGraphNode.serialize_relationships()."""

    def test_classnode_has_expected_relationships(self):
        """ClassNode reports its relationship descriptors statically."""
        rels = ClassNode.serialize_relationships()
        rel_types = {r["relation_type"] for r in rels}
        # ClassNode should have at least these relationship types
        assert "COMPOSES" in rel_types
        assert "DEFINED_IN" in rel_types

    def test_methodnode_has_invokes(self):
        """MethodNode reports INVOKES in its relationships."""
        rels = MethodNode.serialize_relationships()
        rel_types = {r["relation_type"] for r in rels}
        assert "INVOKES" in rel_types

    def test_filenode_has_no_outgoing_rels(self):
        """FileNode has only incoming relationships, not outgoing."""
        rels = FileNode.serialize_relationships()
        outgoing = [r for r in rels if r["direction"] == "OUTGOING"]
        # FileNode is a target of DEFINED_IN but doesn't define outgoing rels
        assert len(outgoing) == 0


class TestLayerQueries:
    """Tests for fetch_by_layer and fetch_all_by_layer."""

    def test_fetch_by_layer_returns_empty_for_file_node(self):
        """FileNode doesn't have a 'layer' property, so fetch_by_layer returns []."""
        result = FileNode.fetch_by_layer("design")
        assert result == []

    def test_fetch_by_layer_returns_empty_for_parameter_node(self):
        """ParameterNode doesn't have a 'layer' property."""
        from codegraph.models.parameter import ParameterNode
        result = ParameterNode.fetch_by_layer("design")
        assert result == []

    def test_fetch_by_layer_returns_nodes_with_matching_layer(self):
        """ClassNode.fetch_by_layer returns nodes where layer matches."""
        # Create and save a ClassNode with layer="design"
        cls = ClassNode(name="FetchTestClass", kind="class", layer="design").save()
        try:
            result = ClassNode.fetch_by_layer("design")
            names = [n.name for n in result]
            assert "FetchTestClass" in names
        finally:
            cls.delete()

    def test_fetch_by_layer_excludes_other_layers(self):
        """fetch_by_layer("as-built") doesn't return design-layer nodes."""
        cls = ClassNode(name="FetchDesignOnly", kind="class", layer="design").save()
        try:
            result = ClassNode.fetch_by_layer("as-built")
            names = [n.name for n in result]
            assert "FetchDesignOnly" not in names
        finally:
            cls.delete()

    def test_fetch_all_by_layer_across_types(self):
        """fetch_all_by_layer queries all registered types."""
        cls = ClassNode(name="FetchAllClass", kind="class", layer="design").save()
        meth = MethodNode(name="fetchAllMethod", kind="method", layer="design").save()
        try:
            result = CodeGraphNode.fetch_all_by_layer("design")
            names = [n.name for n in result]
            assert "FetchAllClass" in names
            assert "fetchAllMethod" in names
        finally:
            cls.delete()
            meth.delete()


class TestSerializeFields:
    """Tests for CodeGraphNode.serialize(fields=...) — LLM vs all fields."""

    def test_llm_fields_default(self):
        """Default serialize() includes only _llm_fields plus type and edges."""
        node = ClassNode(name="Widget", kind="class", qualified_name="ns::Widget")
        result = node.serialize()
        # _llm_fields for ClassNode: qualified_name, name, kind,
        # brief_description, base_classes, visibility
        llm = ClassNode._llm_fields
        for field in llm:
            assert field in result, f"LLM field '{field}' missing from default serialize()"
        assert result["type"] == "ClassNode"
        assert "edges" in result

    def test_llm_fields_excludes_non_llm(self):
        """Default serialize() omits properties not in _llm_fields."""
        node = ClassNode(
            name="Widget",
            kind="class",
            qualified_name="ns::Widget",
            layer="design",
            module="mymod",
            is_abstract=True,
        )
        result = node.serialize()
        # These are NOT in _llm_fields for ClassNode
        assert "module" not in result
        assert "is_abstract" not in result
        assert "layer" not in result
        assert "detailed_description" not in result
        assert "file_path" not in result

    def test_all_fields_includes_everything(self):
        """serialize(fields='all') includes every defined property."""
        node = ClassNode(
            name="Widget",
            kind="class",
            qualified_name="ns::Widget",
            layer="design",
            module="mymod",
            is_abstract=True,
            is_final=False,
            brief_description="A test class",
            detailed_description="Detailed info",
            file_path="/src/widget.h",
            line_number=42,
            source="testproj",
            source_type="doxygen",
        )
        result = node.serialize(fields="all")
        assert result["type"] == "ClassNode"
        # LLM fields are present
        for field in ClassNode._llm_fields:
            assert field in result, f"LLM field '{field}' missing from serialize(fields='all')"
        # Non-LLM fields are also present
        assert "module" in result
        assert "is_abstract" in result
        assert "layer" in result
        assert "detailed_description" in result
        assert "file_path" in result
        assert "line_number" in result
        assert "source" in result
        assert "source_type" in result
        # Value checks
        assert result["module"] == "mymod"
        assert result["is_abstract"] is True
        assert result["layer"] == "design"
        assert result["line_number"] == 42

    def test_all_fields_has_more_keys_than_llm(self):
        """serialize(fields='all') returns more keys than the default."""
        node = ClassNode(name="A", kind="class", qualified_name="ns::A")
        llm_result = node.serialize()
        all_result = node.serialize(fields="all")
        # 'type' and 'edges' are in both, so we strip them for comparison
        llm_data_keys = {k for k in llm_result if k not in {"type", "edges"}}
        all_data_keys = {k for k in all_result if k not in {"type", "edges"}}
        assert all_data_keys > llm_data_keys, (
            f"fields='all' should have more data keys than fields='llm'. "
            f"all: {sorted(all_data_keys)}, llm: {sorted(llm_data_keys)}"
        )

    def test_llm_fields_on_file_node(self):
        """FileNode.serialize() includes _llm_fields but omits non-LLM fields."""
        node = FileNode(name="test.h", path="/src/test.h")
        result = node.serialize()
        # FileNode _llm_fields is {name, path, source}
        assert "path" in result
        assert "name" in result
        assert "source" in result
        # refid and language are NOT in _llm_fields
        assert "refid" not in result
        assert "language" not in result

    def test_all_fields_on_file_node_includes_refid(self):
        """FileNode.serialize(fields='all') includes refid (the uid)."""
        node = FileNode(name="test.h", path="/src/test.h")
        result = node.serialize(fields="all")
        assert "refid" in result
        assert result["refid"] is not None

    def test_unsaved_node_has_empty_edges(self):
        """Unsaved nodes always have an empty edges list regardless of fields."""
        node = ClassNode(name="Ghost", kind="class", qualified_name="ns::Ghost")
        assert node.serialize()["edges"] == []
        assert node.serialize(fields="all")["edges"] == []


class TestUidAccessors:
    """Tests for _uid_prop and _uid_value."""

    def test_uid_prop_for_class_node(self):
        """ClassNode has qualified_name as UniqueIdProperty."""
        assert ClassNode._uid_prop() == "qualified_name"

    def test_uid_prop_for_file_node(self):
        """FileNode has refid as UniqueIdProperty."""
        assert FileNode._uid_prop() == "refid"

    def test_uid_value_returns_stored_uid(self):
        """_uid_value returns the auto-generated uid after save."""
        cls = ClassNode(name="UidTestClass", kind="class").save()
        try:
            uid = cls._uid_value()
            assert uid is not None
            assert isinstance(uid, str)
            assert len(uid) > 0
        finally:
            cls.delete()

    def test_uid_value_for_unsaved_file_node(self):
        """FileNode gets auto-generated refid even before explicit save."""
        f = FileNode(name="unsaved.h")
        uid = f._uid_value()
        # UniqueIdProperty auto-generates a value on instantiation
        assert uid is not None
        assert isinstance(uid, str)
        assert len(uid) > 0