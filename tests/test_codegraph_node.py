"""Tests for CodeGraphNode class methods.

Covers find_relationship_manager error paths, fetch_by_layer,
fetch_all_by_layer, from_json error paths, and serialize_relationships.
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


class TestFromJsonErrorPaths:
    """Tests for CodeGraphNode.from_json() error handling."""

    def test_missing_type_discriminator(self):
        """Raises ValueError when 'type' key is missing."""
        with pytest.raises(ValueError, match="missing the 'type' discriminator"):
            CodeGraphNode.from_json({"name": "orphan"})

    def test_unknown_type(self):
        """Raises KeyError when type is not in the registry."""
        with pytest.raises(KeyError, match="Unknown node type"):
            CodeGraphNode.from_json({"type": "FakeNode", "name": "x"})


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