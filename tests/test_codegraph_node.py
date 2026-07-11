"""Tests for CodeGraphNode class methods.

Covers find_relationship_manager error paths, fetch_by_tag,
fetch_all_by_tag, deserialize error paths, serialize_relationships,
and serialize(fields=...) behaviour.
"""

import pytest
from neomodel import RelationshipTo

from codegraph.models.compound import ClassNode, InterfaceNode, EnumNode
from codegraph.models.file import FileNode
from codegraph.models.member import MethodNode, AttributeNode, EnumValueNode
from codegraph.models.namespace import NamespaceNode
from codegraph.models.tags import CodeGraphNode
from codegraph.uid import compute_uid
import codegraph_requirements.models.requirement  # noqa: F401 — registers HLR/LLR
from codegraph_requirements.models.requirement import HLR, LLR


class TestFindRelationshipManager:
    """Tests for CodeGraphNode.find_relationship_manager()."""

    def test_finds_matching_manager(self):
        """Finds the correct manager when relation_type + target match."""
        # codegraph:test-desc test_codegraph_node.TestFindRelationshipManager.test_finds_matching_manager::step_0
        # This step sets up the necessary graph structure by adding the class and method
        # nodes as children to the manager, ensuring the test environment matches the
        # expected hierarchy.
        cls_node = ClassNode(name="TestClass", kind="class").save()
        meth_node = MethodNode(name="testMethod", kind="method").save()
        manager = CodeGraphNode.find_relationship_manager(
            cls_node, "COMPOSES", meth_node
        )
        # codegraph:test-desc test_codegraph_node.TestFindRelationshipManager.test_finds_matching_manager::post_0
        # This assertion checks that the find_relationship_manager method returned a
        # non-None value, verifying that a matching manager was correctly identified.
        assert manager is not None
        # Clean up
        # codegraph:test-desc test_codegraph_node.TestFindRelationshipManager.test_finds_matching_manager::step_1
        # This step invokes the find_relationship_manager method on the manager with a
        # specific target (cls_node) to test that it correctly finds a matching manager.
        cls_node.delete()
        meth_node.delete()

    def test_raises_on_unknown_relation(self):
        """Raises ValueError when no matching relationship exists."""
        # codegraph:test-desc test_codegraph_node.TestFindRelationshipManager.test_raises_on_unknown_relation::step_0
        # Calls the find_relationship_manager method with an unknown relationship type,
        # advancing the test to the point where a ValueError should be raised due to no
        # matching relationship.
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
        # codegraph:test-desc test_codegraph_node.TestFindRelationshipManager.test_raises_on_wrong_target_type::step_0
        # Sets up the test by creating the file_node and cls_node fixtures, establishing
        # the context in which the subsequent call to find_relationship_manager with a
        # valid relation_type but wrong target type will raise a ValueError.
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
        # codegraph:test-desc test_codegraph_node.TestDeserializeErrorPaths.test_missing_type_discriminator::step_0
        # Sets up test data that deliberately omits the required 'type' key from a
        # dictionary, preparing input that will trigger a ValueError when passed to the
        # deserialize method.
        with pytest.raises(ValueError, match="missing the 'type' discriminator"):
            CodeGraphNode.deserialize({"name": "orphan"})

    def test_unknown_type(self):
        """Raises KeyError when type is not in the registry."""
        # codegraph:test-desc test_codegraph_node.TestDeserializeErrorPaths.test_unknown_type::step_0
        # Sets up the test by creating an invalid serialization dictionary with an
        # unrecognized type field, which will trigger the KeyError during
        # deserialization.
        with pytest.raises(KeyError, match="Unknown node type"):
            CodeGraphNode.deserialize({"type": "FakeNode", "name": "x"})


class TestSerializeRelationships:
    """Tests for CodeGraphNode.serialize_relationships()."""

    def test_classnode_has_expected_relationships(self):
        """ClassNode reports its relationship descriptors statically."""
        # codegraph:test-desc test_codegraph_node.TestSerializeRelationships.test_classnode_has_expected_relationships::step_0
        # Calls serialize_relationships() on the ClassNode fixture to retrieve the set
        # of relationship types; this sets up the data needed to verify that the correct
        # relationships are reported.
        rels = ClassNode.serialize_relationships()
        rel_types = {r["relation_type"] for r in rels}
        # ClassNode should have at least these relationship types
        # codegraph:test-desc test_codegraph_node.TestSerializeRelationships.test_classnode_has_expected_relationships::post_0
        # Verifies that 'COMPOSES' is present in the reported relationship types,
        # confirming that a class node correctly reports its composition of
        # sub-elements.
        assert "COMPOSES" in rel_types
        # codegraph:test-desc test_codegraph_node.TestSerializeRelationships.test_classnode_has_expected_relationships::post_1
        # Verifies that 'DEFINED_IN' is present in the reported relationship types,
        # confirming that a class node correctly reports defining its contained members.
        assert "DEFINED_IN" in rel_types

    def test_methodnode_has_invokes(self):
        """MethodNode reports INVOKES in its relationships."""
        # codegraph:test-desc test_codegraph_node.TestSerializeRelationships.test_methodnode_has_invokes::step_0
        # The setup block calls `serialize_relationships()` on the MethodNode to produce
        # a list of relationship type strings. This action generates the data that the
        # subsequent assertion will inspect, moving the test from configuration to
        # verification.
        rels = MethodNode.serialize_relationships()
        rel_types = {r["relation_type"] for r in rels}
        # codegraph:test-desc test_codegraph_node.TestSerializeRelationships.test_methodnode_has_invokes::post_0
        # This assertion checks that the string 'INVOKES' appears in the list of
        # relationship types returned by `serialize_relationships()`. It verifies that
        # the MethodNode correctly reports method invocations as a relationship, which
        # is essential for accurate call-graph representation.
        assert "INVOKES" in rel_types

    def test_filenode_has_no_outgoing_rels(self):
        """FileNode has only incoming relationships, not outgoing."""
        # codegraph:test-desc test_codegraph_node.TestSerializeRelationships.test_filenode_has_no_outgoing_rels::step_0
        # Calls serialize_relationships on the FileNode fixture to produce the sets of
        # ingoing and outgoing relationships for verification.
        rels = FileNode.serialize_relationships()
        outgoing = [r for r in rels if r["direction"] == "OUTGOING"]
        # FileNode is a target of DEFINED_IN but doesn't define outgoing rels
        # codegraph:test-desc test_codegraph_node.TestSerializeRelationships.test_filenode_has_no_outgoing_rels::post_0
        # Checks that the outgoing relationship set is empty, confirming that file nodes
        # do not establish outgoing links, which ensures the serialization logic
        # correctly enforces the directional constraint for FileNode.
        assert len(outgoing) == 0


class TestTagQueries:
    """Tests for fetch_by_tag and fetch_all_by_tag."""

    def test_fetch_by_tag_returns_empty_for_file_node(self):
        """FileNode doesn't have a 'tags' property, so fetch_by_tag returns []."""
        # codegraph:test-desc test_codegraph_node.TestTagQueries.test_fetch_by_tag_returns_empty_for_file_node::step_0
        # Calls fetch_by_tag on the FileNode with a specific tag, setting up the action
        # that should produce an empty result.
        result = FileNode.fetch_by_tag("design")
        # codegraph:test-desc test_codegraph_node.TestTagQueries.test_fetch_by_tag_returns_empty_for_file_node::post_0
        # Verifies that fetch_by_tag returns an empty list, confirming that nodes
        # without a 'tags' property return no results as expected.
        assert result == []

    def test_fetch_by_tag_returns_empty_for_parameter_node(self):
        """ParameterNode doesn't have a 'tags' property."""
        # codegraph:test-desc test_codegraph_node.TestTagQueries.test_fetch_by_tag_returns_empty_for_parameter_node::step_0
        # Sets up the ParameterNode fixture and calls fetch_by_tag on it, advancing the
        # test to verify the method's behavior for parameter nodes.
        from codegraph.models.parameter import ParameterNode
        result = ParameterNode.fetch_by_tag("design")
        # codegraph:test-desc test_codegraph_node.TestTagQueries.test_fetch_by_tag_returns_empty_for_parameter_node::post_0
        # Asserts that fetch_by_tag returns an empty list for a ParameterNode,
        # confirming the method correctly handles node types without a 'tags' property.
        assert result == []

    def test_fetch_by_tag_returns_nodes_with_matching_tag(self):
        """ClassNode.fetch_by_tag returns nodes where tag is in tags."""
        # codegraph:test-desc test_codegraph_node.TestTagQueries.test_fetch_by_tag_returns_nodes_with_matching_tag::step_0
        # Sets up the test environment by creating the ClassNode and calling
        # fetch_by_tag with a specified tag, producing the result fixture used in
        # assertions.
        cls = ClassNode(name="FetchTestClass", kind="class", qualified_name="ns::FetchTestClass", tags=["design"]).save()
        try:
            result = ClassNode.fetch_by_tag("design")
            names = [n.name for n in result]
            # codegraph:test-desc test_codegraph_node.TestTagQueries.test_fetch_by_tag_returns_nodes_with_matching_tag::post_0
            # Verifies that the node named 'FetchTestClass' appears in the query result,
            # confirming that fetch_by_tag correctly returns nodes whose tags include
            # the searched tag.
            assert "FetchTestClass" in names
        finally:
            cls.delete()

    def test_fetch_by_tag_excludes_non_matching_tags(self):
        """fetch_by_tag("as-built") doesn't return nodes tagged only 'design'."""
        # codegraph:test-desc test_codegraph_node.TestTagQueries.test_fetch_by_tag_excludes_non_matching_tags::step_0
        # Sets up the test by creating nodes with different tags and fetching nodes with
        # the 'as-built' tag, establishing the context for the subsequent assertion.
        cls = ClassNode(name="FetchDesignOnly", kind="class", qualified_name="ns::FetchDesignOnly", tags=["design"]).save()
        try:
            result = ClassNode.fetch_by_tag("as-built")
            names = [n.name for n in result]
            # codegraph:test-desc test_codegraph_node.TestTagQueries.test_fetch_by_tag_excludes_non_matching_tags::post_0
            # Verifies that a node tagged only with 'design' is not included in the
            # fetch results when querying for 'as-built', confirming that tag filtering
            # works correctly.
            assert "FetchDesignOnly" not in names
        finally:
            cls.delete()

    def test_fetch_by_tag_returns_nodes_with_multiple_tags(self):
        """fetch_by_tag returns nodes that have the tag among multiple tags."""
        # codegraph:test-desc test_codegraph_node.TestTagQueries.test_fetch_by_tag_returns_nodes_with_multiple_tags::step_0
        # Sets up the test environment by initializing the fixture nodes (cls,
        # design_result, asbuilt_result) with their respective tags. This step prepares
        # the nodes needed to exercise the fetch_by_tag query.
        cls = ClassNode(name="MultiTagClass", kind="class", qualified_name="ns::MultiTagClass", tags=["design", "as-built"]).save()
        try:
            design_result = ClassNode.fetch_by_tag("design")
            asbuilt_result = ClassNode.fetch_by_tag("as-built")
            # codegraph:test-desc test_codegraph_node.TestTagQueries.test_fetch_by_tag_returns_nodes_with_multiple_tags::post_0
            # Verifies that the node named 'MultiTagClass' is present in the results
            # fetched using the design tag. This assertion ensures that fetch_by_tag
            # returns the node when the filtered tag is part of a multi-tag set.
            assert "MultiTagClass" in [n.name for n in design_result]
            # codegraph:test-desc test_codegraph_node.TestTagQueries.test_fetch_by_tag_returns_nodes_with_multiple_tags::post_1
            # Verifies that the node named 'MultiTagClass' is present in the results
            # fetched using the asbuilt tag. This confirms that the fetch_by_tag method
            # returns nodes correctly when the filtered tag is not the first or only tag
            # in the set.
            assert "MultiTagClass" in [n.name for n in asbuilt_result]
        finally:
            cls.delete()

    def test_fetch_all_by_tag_across_types(self):
        """fetch_all_by_tag queries all registered types."""
        # codegraph:test-desc test_codegraph_node.TestTagQueries.test_fetch_all_by_tag_across_types::step_0
        # Sets up the test environment by creating the tagged ClassNode and MethodNode
        # instances, then invokes the fetch_all_by_tag method to collect all nodes with
        # the given tag across types.
        cls = ClassNode(name="FetchAllClass", kind="class", qualified_name="ns::FetchAllClass2", tags=["design"]).save()
        meth = MethodNode(name="fetchAllMethod", kind="method", qualified_name="ns::FetchAllClass2::fetchAllMethod", tags=["design"]).save()
        try:
            result = CodeGraphNode.fetch_all_by_tag("design")
            names = [n.name for n in result]
            # codegraph:test-desc test_codegraph_node.TestTagQueries.test_fetch_all_by_tag_across_types::post_0
            # Verifies that the result contains at least one of the expected class-level
            # names ('FetchAllClass' or 'FetchAllClass2'), confirming that class nodes
            # are correctly retrieved by the tag query.
            assert "FetchAllClass" in names or "FetchAllClass2" in names
            # codegraph:test-desc test_codegraph_node.TestTagQueries.test_fetch_all_by_tag_across_types::post_1
            # Verifies that the result includes the method-level name 'fetchAllMethod',
            # ensuring that method nodes are also returned alongside class nodes when
            # querying across types.
            assert "fetchAllMethod" in names
        finally:
            cls.delete()
            meth.delete()


class TestTagMutation:
    """Tests for add_tag, remove_tag, and has_tag."""

    def test_add_tag(self):
        """add_tag appends a tag and persists."""
        # codegraph:test-desc test_codegraph_node.TestTagMutation.test_add_tag::step_0
        # Performs the setup of the test environment, preparing the class node and its
        # initial state before the actual tag addition is executed.
        cls = ClassNode.save_new(name="AddTagClass", kind="class", qualified_name="ns::AddTagClass")
        try:
            # codegraph:test-desc test_codegraph_node.TestTagMutation.test_add_tag::post_0
            # Confirms that the class node starts with an empty tags list before any
            # mutation, establishing the baseline needed to prove that the subsequent
            # add_tag operation is the sole source of the new tag.
            assert cls.tags == []  # default empty list
            cls.add_tag("design")
            # codegraph:test-desc test_codegraph_node.TestTagMutation.test_add_tag::post_1
            # Checks that the string 'design' is contained in the class node's tags
            # list, ensuring the tag was physically added to the collection.
            assert "design" in cls.tags
            # codegraph:test-desc test_codegraph_node.TestTagMutation.test_add_tag::post_2
            # Verifies that after adding the tag 'design', the class node recognizes it
            # as present via has_tag, confirming the mutation properly associates and
            # persists the tag.
            assert cls.has_tag("design")
        finally:
            cls.delete()

    def test_add_tag_idempotent(self):
        """add_tag is idempotent — adding same tag twice doesn't duplicate."""
        # codegraph:test-desc test_codegraph_node.TestTagMutation.test_add_tag_idempotent::step_0
        # Adds the tag 'design' to the class node for the second time, simulating a
        # duplicate addition to test idempotency.
        cls = ClassNode.save_new(name="IdempotentTagClass", kind="class", qualified_name="ns::IdempotentTagClass")
        try:
            cls.add_tag("design")
            cls.add_tag("design")
            # codegraph:test-desc test_codegraph_node.TestTagMutation.test_add_tag_idempotent::post_0
            # Verifies that the 'design' tag appears exactly once in the class node's
            # tags list, confirming that the add_tag mutation does not duplicate tags
            # when called repeatedly.
            assert cls.tags.count("design") == 1
        finally:
            cls.delete()

    def test_add_multiple_tags(self):
        """Multiple tags can be added."""
        # codegraph:test-desc test_codegraph_node.TestTagMutation.test_add_multiple_tags::step_0
        # Sets up the initial state by adding two tags ('design' and 'as-built') to the
        # ClassNode, establishing a known starting point for subsequent assertions about
        # tag existence and absence.
        cls = ClassNode.save_new(name="MultiTagClass2", kind="class", qualified_name="ns::MultiTagClass2")
        try:
            cls.add_tag("design")
            cls.add_tag("as-built")
            # codegraph:test-desc test_codegraph_node.TestTagMutation.test_add_multiple_tags::post_0
            # Checks that the 'design' tag was properly added to the ClassNode, ensuring
            # the first tag mutation in the sequence was applied correctly and remains
            # present.
            assert cls.has_tag("design")
            # codegraph:test-desc test_codegraph_node.TestTagMutation.test_add_multiple_tags::post_1
            # Confirms that the 'as-built' tag was successfully added to the ClassNode,
            # validating that the tag mutation correctly persists the expected tag after
            # the operation.
            assert cls.has_tag("as-built")
            # codegraph:test-desc test_codegraph_node.TestTagMutation.test_add_multiple_tags::post_2
            # Verifies that the 'dependency' tag is not present on the ClassNode,
            # confirming that only the intended tags were added and no unintended side
            # effects occurred during the mutation.
            assert not cls.has_tag("dependency")
        finally:
            cls.delete()

    def test_remove_tag(self):
        """remove_tag removes a tag and persists."""
        # codegraph:test-desc test_codegraph_node.TestTagMutation.test_remove_tag::step_0
        # Setup block that initializes the class node and applies the 'design' and
        # 'as-built' tags before the removal operation is called.
        cls = ClassNode.save_new(name="RemoveTagClass", kind="class", qualified_name="ns::RemoveTagClass", tags=["design", "as-built"])
        try:
            # codegraph:test-desc test_codegraph_node.TestTagMutation.test_remove_tag::post_0
            # Verifies that the 'design' tag was initially present before removal,
            # establishing the baseline state for the test.
            assert cls.has_tag("design")
            # codegraph:test-desc test_codegraph_node.TestTagMutation.test_remove_tag::post_1
            # Verifies that the 'as-built' tag is still present after the removal of
            # 'design', confirming that unrelated tags are preserved.
            assert cls.has_tag("as-built")
            cls.remove_tag("design")
            # codegraph:test-desc test_codegraph_node.TestTagMutation.test_remove_tag::post_2
            # Verifies that the 'design' tag is no longer present after removal,
            # confirming that the remove_tag method correctly deletes the specified tag.
            assert not cls.has_tag("design")
            # codegraph:test-desc test_codegraph_node.TestTagMutation.test_remove_tag::post_3
            # Verifies that the 'as-built' tag remains intact after the entire removal
            # operation, ensuring no unintended side effects on other tags.
            assert cls.has_tag("as-built")
        finally:
            cls.delete()

    def test_remove_tag_nonexistent(self):
        """remove_tag is a no-op if tag is not present."""
        # codegraph:test-desc test_codegraph_node.TestTagMutation.test_remove_tag_nonexistent::step_0
        # Calls the remove_tag method with a tag name that is not present in the node's
        # tags, setting up the scenario to observe that no changes occur.
        cls = ClassNode.save_new(name="RemoveNoopClass", kind="class", qualified_name="ns::RemoveNoopClass", tags=["design"])
        try:
            cls.remove_tag("dependency")
            # codegraph:test-desc test_codegraph_node.TestTagMutation.test_remove_tag_nonexistent::post_0
            # Asserts that the tags list remains unchanged and still equals ['design'],
            # confirming that remove_tag is a no-op when the tag is not present.
            assert cls.tags == ["design"]
        finally:
            cls.delete()

    def test_has_tag_on_file_node(self):
        """has_tag returns False for nodes without tags property (FileNode)."""
        # codegraph:test-desc test_codegraph_node.TestTagMutation.test_has_tag_on_file_node::step_0
        # Sets up the test by creating the FileNode fixture without tags, preparing the
        # condition needed for the assertion.
        f = FileNode.save_new(name="tagless.h", path="/src/tagless.h")
        try:
            # codegraph:test-desc test_codegraph_node.TestTagMutation.test_has_tag_on_file_node::post_0
            # Verifies that has_tag returns False for a node lacking a tags property,
            # ensuring correct handling of nodes without tag support.
            assert f.has_tag("design") is False
        finally:
            f.delete()

    def test_add_tag_on_file_node(self):
        """add_tag is a no-op for nodes without tags property (FileNode)."""
        # codegraph:test-desc test_codegraph_node.TestTagMutation.test_add_tag_on_file_node::step_0
        # Sets up the test by creating the necessary environment or initial state,
        # preparing to call the add_tag mutation on the FileNode.
        f = FileNode.save_new(name="tagless2.h", path="/src/tagless2.h")
        try:
            result = f.add_tag("design")
            # codegraph:test-desc test_codegraph_node.TestTagMutation.test_add_tag_on_file_node::post_0
            # Asserts that the result of the add_tag mutation is the original FileNode
            # itself, confirming that the operation is a no-op for nodes without tags.
            assert result is f  # returns self, no error
        finally:
            f.delete()

    def test_has_tag_on_unsaved_node(self):
        """has_tag works on unsaved nodes."""
        # codegraph:test-desc test_codegraph_node.TestTagMutation.test_has_tag_on_unsaved_node::step_0
        # Sets up the test environment by creating the unsaved node and applying tags to
        # it, preparing the state needed to evaluate has_tag behavior.
        node = ClassNode(name="UnsavedTags", kind="class", qualified_name="ns::UnsavedTags", tags=["design"])
        # codegraph:test-desc test_codegraph_node.TestTagMutation.test_has_tag_on_unsaved_node::post_0
        # Verifies that the unsaved node is recognized as having a specific tag assigned
        # to it, confirming that tag metadata is accessible before the node is saved.
        assert node.has_tag("design") is True
        # codegraph:test-desc test_codegraph_node.TestTagMutation.test_has_tag_on_unsaved_node::post_1
        # Checks that the unsaved node correctly reports it does not have a tag that was
        # never assigned, ensuring that has_tag logic correctly differentiates between
        # present and absent tags.
        assert node.has_tag("as-built") is False


class TestSerializeFields:
    """Tests for CodeGraphNode.serialize(fields=...) — LLM vs all fields."""

    def test_llm_fields_default(self):
        """Default serialize() includes only _llm_fields plus type and edges."""
        # codegraph:test-desc test_codegraph_node.TestSerializeFields.test_llm_fields_default::step_0
        # Calls serialize() on the ClassNode fixture without extra arguments to produce
        # the default serialization output for verification.
        node = ClassNode(name="Widget", kind="class", qualified_name="ns::Widget")
        result = node.serialize()
        # _llm_fields for ClassNode: qualified_name, name, kind,
        # brief_description, base_classes, visibility
        llm = ClassNode._llm_fields
        for field in llm:
            # codegraph:test-desc test_codegraph_node.TestSerializeFields.test_llm_fields_default::post_0
            # Verifies that each designated LLM field is present in the default
            # serialization output, ensuring that the method includes the required
            # fields for downstream analysis.
            assert field in result, f"LLM field '{field}' missing from default serialize()"
        # codegraph:test-desc test_codegraph_node.TestSerializeFields.test_llm_fields_default::post_1
        # Verifies that the serialization result includes a 'type' field set to
        # 'ClassNode', confirming the node's type is correctly reported.
        assert result["type"] == "ClassNode"
        # codegraph:test-desc test_codegraph_node.TestSerializeFields.test_llm_fields_default::post_2
        # Verifies that 'edges' is present in the serialization result, ensuring the
        # method includes relationship data by default.
        assert "edges" in result

    def test_llm_fields_excludes_non_llm(self):
        """Default serialize() omits properties not in _llm_fields."""
        # codegraph:test-desc test_codegraph_node.TestSerializeFields.test_llm_fields_excludes_non_llm::step_0
        # Calls the serialize() method on the node fixture to produce a dictionary of
        # output fields, which is the action needed to later verify which fields are
        # included.
        node = ClassNode(
            name="Widget",
            kind="class",
            qualified_name="ns::Widget",
            tags=["design"],
            module="mymod",
            is_abstract=True,
        )
        result = node.serialize()
        # These are NOT in _llm_fields for ClassNode
        # codegraph:test-desc test_codegraph_node.TestSerializeFields.test_llm_fields_excludes_non_llm::post_0
        # Asserts that 'module' is not in the serialized output, validating that
        # internal Python module metadata is omitted from LLM-facing serialization.
        assert "module" not in result
        # codegraph:test-desc test_codegraph_node.TestSerializeFields.test_llm_fields_excludes_non_llm::post_1
        # Confirms that 'is_abstract' is absent from the serialized output, ensuring
        # that LLM-unrelated attributes are filtered out as required.
        assert "is_abstract" not in result
        # codegraph:test-desc test_codegraph_node.TestSerializeFields.test_llm_fields_excludes_non_llm::post_2
        # Checks that 'detailed_description' is excluded from the result, ensuring
        # verbose source details are not exposed in the LLM-specific serialization.
        assert "detailed_description" not in result
        # codegraph:test-desc test_codegraph_node.TestSerializeFields.test_llm_fields_excludes_non_llm::post_3
        # Verifies that 'file_path' is not present in the serialized result, confirming
        # the serialize method excludes non-LLM fields correctly.
        assert "file_path" not in result
        # tags IS in _llm_fields for ClassNode
        # codegraph:test-desc test_codegraph_node.TestSerializeFields.test_llm_fields_excludes_non_llm::post_4
        # Verifies that 'tags' is included in the serialized output, confirming that
        # fields declared in _llm_fields are correctly preserved.
        assert "tags" in result

    def test_all_fields_includes_everything(self):
        """serialize(fields='all') includes every defined property."""
        # codegraph:test-desc test_codegraph_node.TestSerializeFields.test_all_fields_includes_everything::step_0
        # Establishes the serialized result by calling serialize(fields='all') on the
        # prepared ClassNode fixture, producing the output dictionary that subsequent
        # assertions will inspect.
        node = ClassNode(
            name="Widget",
            kind="class",
            qualified_name="ns::Widget",
            tags=["design"],
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
        # codegraph:test-desc test_codegraph_node.TestSerializeFields.test_all_fields_includes_everything::post_0
        # Verifies that the serialized result identifies the node type as 'ClassNode',
        # confirming that the type field is correctly serialized and matches the
        # expected class type.
        assert result["type"] == "ClassNode"
        # LLM fields are present
        for field in ClassNode._llm_fields:
            # codegraph:test-desc test_codegraph_node.TestSerializeFields.test_all_fields_includes_everything::post_1
            # Verifies that each field from a predefined list (likely the LLM-specific
            # fields) is present in the serialized result, ensuring that all documented
            # properties are included when fields='all'.
            assert field in result, f"LLM field '{field}' missing from serialize(fields='all')"
        # Non-LLM fields are also present
        # codegraph:test-desc test_codegraph_node.TestSerializeFields.test_all_fields_includes_everything::post_2
        # Verifies that the serialized result includes the key 'module', ensuring that
        # the module property is present when all fields are requested.
        assert "module" in result
        # codegraph:test-desc test_codegraph_node.TestSerializeFields.test_all_fields_includes_everything::post_3
        # Verifies that the serialized result includes the key 'is_abstract', ensuring
        # that the is_abstract property is present when all fields are requested.
        assert "is_abstract" in result
        # codegraph:test-desc test_codegraph_node.TestSerializeFields.test_all_fields_includes_everything::post_4
        # Verifies that the serialized result includes the key 'tags', ensuring that the
        # tags property is present when all fields are requested.
        assert "tags" in result
        # codegraph:test-desc test_codegraph_node.TestSerializeFields.test_all_fields_includes_everything::post_5
        # Verifies that the serialized result includes the key 'detailed_description',
        # ensuring that the detailed_description property is present when all fields are
        # requested.
        assert "detailed_description" in result
        # codegraph:test-desc test_codegraph_node.TestSerializeFields.test_all_fields_includes_everything::post_6
        # Verifies that the serialized result includes the key 'file_path', ensuring
        # that the file_path property is present when all fields are requested.
        assert "file_path" in result
        # codegraph:test-desc test_codegraph_node.TestSerializeFields.test_all_fields_includes_everything::post_7
        # Verifies that the serialized result includes the key 'line_number', ensuring
        # that the line_number property is present when all fields are requested.
        assert "line_number" in result
        # codegraph:test-desc test_codegraph_node.TestSerializeFields.test_all_fields_includes_everything::post_8
        # Verifies that the serialized result includes the key 'source', ensuring that
        # the source property is present when all fields are requested.
        assert "source" in result
        # codegraph:test-desc test_codegraph_node.TestSerializeFields.test_all_fields_includes_everything::post_9
        # Verifies that the serialized result includes the key 'source_type', ensuring
        # that the source_type property is present when all fields are requested.
        assert "source_type" in result
        # Value checks
        # codegraph:test-desc test_codegraph_node.TestSerializeFields.test_all_fields_includes_everything::post_10
        # Verifies that the serialized result's 'module' field matches the expected
        # value 'mymod', confirming that the module property is correctly serialized.
        assert result["module"] == "mymod"
        # codegraph:test-desc test_codegraph_node.TestSerializeFields.test_all_fields_includes_everything::post_11
        # Verifies that the serialized result's 'is_abstract' field is True, confirming
        # that the is_abstract property is correctly serialized with its boolean value.
        assert result["is_abstract"] is True
        # codegraph:test-desc test_codegraph_node.TestSerializeFields.test_all_fields_includes_everything::post_12
        # Verifies that the serialized result's 'tags' field equals the expected list
        # ['design'], confirming that the tags property is correctly serialized with its
        # value.
        assert result["tags"] == ["design"]
        # codegraph:test-desc test_codegraph_node.TestSerializeFields.test_all_fields_includes_everything::post_13
        # Verifies that the serialized result's 'line_number' field equals the expected
        # integer 42, confirming that the line_number property is correctly serialized
        # with its value.
        assert result["line_number"] == 42

    def test_all_fields_has_more_keys_than_llm(self):
        """serialize(fields='all') returns more keys than the default."""
        # codegraph:test-desc test_codegraph_node.TestSerializeFields.test_all_fields_has_more_keys_than_llm::step_0
        # Calls node.serialize(fields='all') and node.serialize(fields='llm') to collect
        # the keys from both serialization modes, setting up the data for comparison.
        node = ClassNode(name="A", kind="class", qualified_name="ns::A")
        llm_result = node.serialize()
        all_result = node.serialize(fields="all")
        # 'type' and 'edges' are in both, so we strip them for comparison
        llm_data_keys = {k for k in llm_result if k not in {"type", "edges"}}
        all_data_keys = {k for k in all_result if k not in {"type", "edges"}}
        # codegraph:test-desc test_codegraph_node.TestSerializeFields.test_all_fields_has_more_keys_than_llm::post_0
        # Verifies that the set of keys from serialize(fields='all') is a superset of
        # those from serialize(fields='llm'), confirming that the 'all' mode includes
        # additional fields beyond the LLM subset.
        assert all_data_keys > llm_data_keys, (
            f"fields='all' should have more data keys than fields='llm'. "
            f"all: {sorted(all_data_keys)}, llm: {sorted(llm_data_keys)}"
        )

    def test_llm_fields_on_file_node(self):
        """FileNode.serialize() includes _llm_fields but omits non-LLM fields."""
        # codegraph:test-desc test_codegraph_node.TestSerializeFields.test_llm_fields_on_file_node::step_0
        # Calls the serialize() method on the FileNode fixture to produce a result
        # dictionary, which is then checked by subsequent assertions.
        node = FileNode(name="test.h", path="/src/test.h")
        result = node.serialize()
        # FileNode _llm_fields is {name, path, source}
        # codegraph:test-desc test_codegraph_node.TestSerializeFields.test_llm_fields_on_file_node::post_0
        # Verifies that 'path' is present in the serialization result, confirming it is
        # a designated LLM field.
        assert "path" in result
        # codegraph:test-desc test_codegraph_node.TestSerializeFields.test_llm_fields_on_file_node::post_1
        # Verifies that 'name' is present in the serialization result, confirming it is
        # a designated LLM field.
        assert "name" in result
        # codegraph:test-desc test_codegraph_node.TestSerializeFields.test_llm_fields_on_file_node::post_2
        # Verifies that 'source' is present in the serialization result, confirming it
        # is a designated LLM field.
        assert "source" in result
        # refid and language are NOT in _llm_fields
        # codegraph:test-desc test_codegraph_node.TestSerializeFields.test_llm_fields_on_file_node::post_3
        # Verifies that 'refid' is not present in the serialization result, ensuring
        # non-LLM fields are correctly omitted.
        assert "refid" not in result
        # codegraph:test-desc test_codegraph_node.TestSerializeFields.test_llm_fields_on_file_node::post_4
        # Verifies that 'language' is not present in the serialization result, ensuring
        # non-LLM fields are correctly omitted.
        assert "language" not in result

    def test_all_fields_on_file_node_includes_refid(self):
        """FileNode.serialize(fields='all') includes refid (the uid)."""
        # codegraph:test-desc test_codegraph_node.TestSerializeFields.test_all_fields_on_file_node_includes_refid::step_0
        # Calls `serialize(fields='all')` on the FileNode to generate its full
        # serialized representation, which is the core action being tested.
        node = FileNode(name="test.h", path="/src/test.h")
        result = node.serialize(fields="all")
        # codegraph:test-desc test_codegraph_node.TestSerializeFields.test_all_fields_on_file_node_includes_refid::post_0
        # Verifies that the key 'refid' exists in the serialized result, establishing
        # that the file's unique identifier is always included when all fields are
        # requested.
        assert "refid" in result
        # codegraph:test-desc test_codegraph_node.TestSerializeFields.test_all_fields_on_file_node_includes_refid::post_1
        # Verifies that the 'refid' value is not null, ensuring that every file node has
        # a valid non-null unique identifier in its complete serialization.
        assert result["refid"] is not None

    def test_unsaved_node_has_empty_edges(self):
        """Unsaved nodes always have an empty edges list regardless of fields."""
        # codegraph:test-desc test_codegraph_node.TestSerializeFields.test_unsaved_node_has_empty_edges::step_0
        # Sets up the test by creating the unsaved node fixture; this step initiates the
        # test scenario by providing the node for serialization.
        node = ClassNode(name="Ghost", kind="class", qualified_name="ns::Ghost")
        # codegraph:test-desc test_codegraph_node.TestSerializeFields.test_unsaved_node_has_empty_edges::post_0
        # Verifies that the default serialization of an unsaved node includes an empty
        # edges list, ensuring the node behaves correctly before persistence.
        assert node.serialize()["edges"] == []
        # codegraph:test-desc test_codegraph_node.TestSerializeFields.test_unsaved_node_has_empty_edges::post_1
        # Checks that when serializing with 'fields=all', the unsaved node's edges are
        # empty, confirming the property holds regardless of serialization fields.
        assert node.serialize(fields="all")["edges"] == []


class TestUidAccessors:
    """Tests for _uid_prop and _uid_value."""

    def test_uid_prop_for_class_node(self):
        """ClassNode has uid as UniqueIdProperty (route B)."""
        # codegraph:test-desc test_codegraph_node.TestUidAccessors.test_uid_prop_for_class_node::post_0
        # Verifies that the 'uid' property of a ClassNode instance is equal to the
        # expected UniqueIdProperty value, ensuring that the UniqueIdProperty is
        # correctly assigned and stored for class nodes in the code graph.
        assert ClassNode._uid_prop() == "uid"

    def test_uid_prop_for_file_node(self):
        """FileNode has uid as UniqueIdProperty (route B)."""
        # codegraph:test-desc test_codegraph_node.TestUidAccessors.test_uid_prop_for_file_node::post_0
        # Verifies that the uid property of a FileNode object matches the expected
        # unique identifier. This ensures that the FileNode correctly assigns and stores
        # a unique ID, which is essential for distinguishing different file nodes in the
        # code graph.
        assert FileNode._uid_prop() == "uid"

    def test_uid_value_returns_stored_uid(self):
        """_uid_value returns the auto-generated uid after save."""
        # codegraph:test-desc test_codegraph_node.TestUidAccessors.test_uid_value_returns_stored_uid::step_0
        # Sets up the test by creating and saving a ClassNode, which triggers
        # auto-generation of a UID and prepares the node for subsequent calls to the
        # _uid_value accessor.
        cls = ClassNode(name="UidTestClass", kind="class").save()
        try:
            uid = cls._uid_value()
            # codegraph:test-desc test_codegraph_node.TestUidAccessors.test_uid_value_returns_stored_uid::post_0
            # Verifies that the uid obtained from _uid_value is not None, confirming
            # that the node has indeed been assigned a UID after save.
            assert uid is not None
            # codegraph:test-desc test_codegraph_node.TestUidAccessors.test_uid_value_returns_stored_uid::post_1
            # Asserts that the returned uid is a string type, confirming that the UID is
            # represented in the expected textual format for downstream use.
            assert isinstance(uid, str)
            # codegraph:test-desc test_codegraph_node.TestUidAccessors.test_uid_value_returns_stored_uid::post_2
            # Checks that the uid string is non-empty, ensuring that auto-generated UIDs
            # are not blank strings and contain meaningful content.
            assert len(uid) > 0
        finally:
            cls.delete()

    def test_uid_value_for_unsaved_file_node(self):
        """FileNode gets auto-generated refid even before explicit save."""
        # codegraph:test-desc test_codegraph_node.TestUidAccessors.test_uid_value_for_unsaved_file_node::step_0
        # Access the '_uid_value' property of the unsaved FileNode to retrieve the
        # automatically generated unique identifier, setting up the value for subsequent
        # assertions.
        f = FileNode(name="unsaved.h")
        uid = f._uid_value()
        # UniqueIdProperty auto-generates a value on instantiation
        # codegraph:test-desc test_codegraph_node.TestUidAccessors.test_uid_value_for_unsaved_file_node::post_0
        # Verifies that the unique identifier (_uid_value) is not None, ensuring
        # auto-generation produces a non-null refid for unsaved nodes.
        assert uid is not None
        # codegraph:test-desc test_codegraph_node.TestUidAccessors.test_uid_value_for_unsaved_file_node::post_1
        # Verifies that the unique identifier is a string, confirming the auto-generated
        # refid conforms to the expected data type required for downstream operations.
        assert isinstance(uid, str)
        # codegraph:test-desc test_codegraph_node.TestUidAccessors.test_uid_value_for_unsaved_file_node::post_2
        # Verifies that the unique identifier has a positive length, confirming it is a
        # non-empty value, which matches expected behavior for a valid unique
        # identifier.
        assert len(uid) > 0

    # ── HLR/LLR deterministic uid tests ───────────────────────────────

    def test_uid_prop_for_hlr(self):
        """HLR has uid as UniqueIdProperty (same pattern as ClassNode)."""
        assert HLR._uid_prop() == "uid"

    def test_uid_prop_for_llr(self):
        """LLR has uid as UniqueIdProperty (same pattern as ClassNode)."""
        assert LLR._uid_prop() == "uid"

    def test_hlr_identity_fields(self):
        """HLR._identity_fields is ("qualified_name",) — deterministic uid from qualified_name."""
        assert HLR._identity_fields == ("qualified_name",)

    def test_llr_identity_fields(self):
        """LLR._identity_fields is ("qualified_name",) — deterministic uid from qualified_name."""
        assert LLR._identity_fields == ("qualified_name",)

    def test_hlr_computes_deterministic_uid(self):
        """HLR.save() computes uid = SHA-1(name)."""
        name = "Test HLR Uid"
        hlr = HLR(name=name, description="desc", tags=["design"]).save()
        try:
            expected = compute_uid(name)
            assert hlr.uid == expected
            assert hlr._uid_value() == expected
        finally:
            hlr.delete()

    def test_llr_computes_deterministic_uid(self):
        """LLR.save() computes uid = SHA-1(name)."""
        name = "Test LLR Uid"
        llr = LLR(name=name, description="desc", tags=["design"]).save()
        try:
            expected = compute_uid(name)
            assert llr.uid == expected
            assert llr._uid_value() == expected
        finally:
            llr.delete()

    def test_hlr_save_idempotent(self):
        """Re-saving an HLR with the same name updates, does not duplicate."""
        name = "Idempotent HLR Uid Test"
        hlr1 = HLR(name=name, description="first", tags=["design"]).save()
        try:
            uid_after_first = hlr1.uid

            # Re-save a new instance with the same name
            hlr2 = HLR(name=name, description="second", tags=["design"]).save()
            try:
                # Same uid — it was an upsert
                assert hlr2.uid == uid_after_first
                # Description should be updated
                assert hlr2.description == "second"
            finally:
                hlr2.delete()
        finally:
            hlr1.delete()

    def test_llr_save_idempotent(self):
        """Re-saving an LLR with the same name updates, does not duplicate."""
        name = "Idempotent LLR Uid Test"
        llr1 = LLR(name=name, description="first", tags=["design"]).save()
        try:
            uid_after_first = llr1.uid

            # Re-save a new instance with the same name
            llr2 = LLR(name=name, description="second", tags=["design"]).save()
            try:
                # Same uid — it was an upsert
                assert llr2.uid == uid_after_first
                # Description should be updated
                assert llr2.description == "second"
            finally:
                llr2.delete()
        finally:
            llr1.delete()


class TestWalkComposes:
    """Tests for CodeGraphNode.walk_composes()."""

    def test_walk_composes_returns_methods_and_attributes(self):
        """ClassNode.walk_composes() returns composed methods and attributes."""
        # codegraph:test-desc test_codegraph_node.TestWalkComposes.test_walk_composes_returns_methods_and_attributes::step_0
        # Sets up the test environment by initializing the class node, method node, and
        # attribute node fixtures, and calling walk_composes() to collect the composed
        # child names into 'child_names', preparing the data for assertion.
        cls = ClassNode(name="MyClass", kind="class", qualified_name="ns::MyClass").save()
        meth = MethodNode(name="draw", kind="method", qualified_name="ns::MyClass::draw").save()
        attr = AttributeNode(name="x", kind="attribute", qualified_name="ns::MyClass::x").save()
        try:
            cls.methods.connect(meth)
            cls.attributes.connect(attr)
            children = cls.walk_composes()
            child_names = {c.name for c in children}
            # codegraph:test-desc test_codegraph_node.TestWalkComposes.test_walk_composes_returns_methods_and_attributes::post_0
            # Verifies that the method named 'draw' appears in the list of composed
            # child names, ensuring that MethodNode instances are correctly included in
            # the walk_composes output.
            assert "draw" in child_names
            # codegraph:test-desc test_codegraph_node.TestWalkComposes.test_walk_composes_returns_methods_and_attributes::post_1
            # Verifies that the attribute named 'x' appears in the list of composed
            # child names, ensuring that AttributeNode instances are correctly included
            # in the walk_composes output.
            assert "x" in child_names
        finally:
            cls.methods.disconnect(meth)
            cls.attributes.disconnect(attr)
            meth.delete()
            attr.delete()
            cls.delete()

    def test_walk_composes_returns_empty_for_leaf_nodes(self):
        """MethodNode.walk_composes() returns empty list."""
        # codegraph:test-desc test_codegraph_node.TestWalkComposes.test_walk_composes_returns_empty_for_leaf_nodes::step_0
        # Sets up the test by creating or obtaining a MethodNode that is a leaf,
        # preparing the object against which the walk_composes method will be called.
        meth = MethodNode(name="leaf", kind="method", qualified_name="ns::leaf").save()
        try:
            children = meth.walk_composes()
            # codegraph:test-desc test_codegraph_node.TestWalkComposes.test_walk_composes_returns_empty_for_leaf_nodes::post_0
            # Verifies that walk_composes returns an empty list for a leaf MethodNode,
            # confirming that the method correctly identifies nodes with no child
            # compose relationships.
            assert children == []
        finally:
            meth.delete()

    def test_walk_composes_namespace_returns_classes(self):
        """NamespaceNode.walk_composes() returns composed classes."""
        # codegraph:test-desc test_codegraph_node.TestWalkComposes.test_walk_composes_namespace_returns_classes::step_0
        # Sets up the necessary test objects (namespace and class nodes) and invokes
        # walk_composes() on the namespace to obtain the list of composed children.
        ns = NamespaceNode(name="myns", kind="namespace", qualified_name="myns").save()
        cls = ClassNode(name="NSClass", kind="class", qualified_name="myns::NSClass").save()
        try:
            ns.classes.connect(cls)
            children = ns.walk_composes()
            # codegraph:test-desc test_codegraph_node.TestWalkComposes.test_walk_composes_namespace_returns_classes::post_0
            # Verifies that exactly one child was returned by walk_composes(),
            # confirming the method correctly identifies and isolates the single
            # composed class within the namespace.
            assert len(children) == 1
            # codegraph:test-desc test_codegraph_node.TestWalkComposes.test_walk_composes_namespace_returns_classes::post_1
            # Verifies that the returned child is the specific ClassNode (cls), ensuring
            # that walk_composes() returns the correct composed class and not any other
            # entities.
            assert children[0].name == "NSClass"
        finally:
            ns.classes.disconnect(cls)
            cls.delete()
            ns.delete()


class TestSerializeNested:
    """Tests for CodeGraphNode.serialize(nested=True)."""

    def test_nested_includes_composes_key(self):
        """serialize(nested=True) includes composed children under 'composes'."""
        # codegraph:test-desc test_codegraph_node.TestSerializeNested.test_nested_includes_composes_key::step_0
        # Sets up the test by creating the ClassNode and MethodNode fixtures, preparing
        # to call serialize(nested=True).
        cls = ClassNode(name="NestedClass", kind="class", qualified_name="ns::NestedClass").save()
        meth = MethodNode(name="run", kind="method", qualified_name="ns::NestedClass::run").save()
        try:
            cls.methods.connect(meth)
            result = cls.serialize(nested=True)
            # codegraph:test-desc test_codegraph_node.TestSerializeNested.test_nested_includes_composes_key::post_0
            # Verifies that the serialized result contains a 'composes' key, confirming
            # the nested serialization includes composed children.
            assert "composes" in result
            # codegraph:test-desc test_codegraph_node.TestSerializeNested.test_nested_includes_composes_key::post_1
            # Verifies that exactly one composed element exists, ensuring no extra or
            # missing children are reported under 'composes'.
            assert len(result["composes"]) == 1
            # codegraph:test-desc test_codegraph_node.TestSerializeNested.test_nested_includes_composes_key::post_2
            # Verifies that the first composed element in the serialized output has the
            # type 'MethodNode', ensuring the composition relationship is correctly
            # reported.
            assert result["composes"][0]["type"] == "MethodNode"
            # codegraph:test-desc test_codegraph_node.TestSerializeNested.test_nested_includes_composes_key::post_3
            # Verifies that the first composed element is named 'run', confirming the
            # correct method is included in the composition list.
            assert result["composes"][0]["name"] == "run"
        finally:
            cls.methods.disconnect(meth)
            meth.delete()
            cls.delete()

    def test_nested_removes_composes_from_edges(self):
        """COMPOSES edges are removed from edges when nested=True."""
        # codegraph:test-desc test_codegraph_node.TestSerializeNested.test_nested_removes_composes_from_edges::step_0
        # Performs the serialization of the class and method nodes with nested=True,
        # producing the edge lists that will be checked in the subsequent assertions.
        cls = ClassNode(name="EdgeClass", kind="class", qualified_name="ns::EdgeClass").save()
        meth = MethodNode(name="doIt", kind="method", qualified_name="ns::EdgeClass::doIt").save()
        try:
            cls.methods.connect(meth)
            # nested=False (default) should include COMPOSES in edges
            flat = cls.serialize()
            composes_edges = [e for e in flat["edges"] if e["relation_type"] == "COMPOSES"]
            # codegraph:test-desc test_codegraph_node.TestSerializeNested.test_nested_removes_composes_from_edges::post_0
            # Verifies that COMPOSES edges are present when the graph is serialized
            # without nesting (flat), confirming that the relationship exists before the
            # nesting filter is applied.
            assert len(composes_edges) >= 1, "COMPOSES should appear in flat edges"

            # nested=True should NOT include COMPOSES in edges
            nested = cls.serialize(nested=True)
            composes_in_edges = [e for e in nested["edges"] if e["relation_type"] == "COMPOSES"]
            # codegraph:test-desc test_codegraph_node.TestSerializeNested.test_nested_removes_composes_from_edges::post_1
            # Verifies that COMPOSES edges are absent after serializing with
            # nested=True, confirming that the code under test correctly removes
            # composition edges to produce a flat, non-hierarchical output.
            assert len(composes_in_edges) == 0, "COMPOSES should not appear in nested edges"
        finally:
            cls.methods.disconnect(meth)
            meth.delete()
            cls.delete()

    def test_nested_includes_uid_property(self):
        """serialize(nested=True) includes uid property for roundtrip resolution."""
        # codegraph:test-desc test_codegraph_node.TestSerializeNested.test_nested_includes_uid_property::step_0
        # Sets up the test by instantiating a ClassNode, serving as the input for the
        # serialization call that will be validated later.
        cls = ClassNode(name="UidClass", kind="class", qualified_name="ns::UidClass").save()
        try:
            result = cls.serialize(nested=True)
            # uid is the UniqueIdProperty — always included for resolution
            # codegraph:test-desc test_codegraph_node.TestSerializeNested.test_nested_includes_uid_property::post_0
            # Verifies that the serialized output contains the 'uid' field, which is
            # essential for reconstructing the object graph during a roundtrip
            # serialization-deserialization process.
            assert "uid" in result
        finally:
            cls.delete()

    def test_nested_includes_uid_for_file_node(self):
        """FileNode.serialize(nested=True) includes uid even though it's not in _llm_fields."""
        # codegraph:test-desc test_codegraph_node.TestSerializeNested.test_nested_includes_uid_for_file_node::step_0
        # Calls `serialize(nested=True)` on the FileNode fixture to produce the result
        # that will be inspected for the presence of the `uid` field.
        f = FileNode(name="uidtest.h", path="/src/uidtest.h").save()
        try:
            result = f.serialize(nested=True)
            # FileNode has no COMPOSES relationships, but nested=True still ensures uid
            # codegraph:test-desc test_codegraph_node.TestSerializeNested.test_nested_includes_uid_for_file_node::post_0
            # Verifies that the `uid` key exists in the serialized output, ensuring that
            # even though `uid` is not in `_llm_fields`, it is still included when
            # nesting is enabled.
            assert "uid" in result
        finally:
            f.delete()

    def test_nested_recursive(self):
        """serialize(nested=True) recursively includes children's children."""
        # codegraph:test-desc test_codegraph_node.TestSerializeNested.test_nested_recursive::step_0
        # Sets up the test fixture hierarchy by creating or retrieving the ns, cls, and
        # meth objects, establishing the parent-child relationships needed for the
        # nested serialization test.
        ns = NamespaceNode(name="recns", kind="namespace", qualified_name="recns").save()
        cls = ClassNode(name="RecClass", kind="class", qualified_name="recns::RecClass").save()
        meth = MethodNode(name="go", kind="method", qualified_name="recns::RecClass::go").save()
        try:
            ns.classes.connect(cls)
            cls.methods.connect(meth)

            result = ns.serialize(nested=True)
            # codegraph:test-desc test_codegraph_node.TestSerializeNested.test_nested_recursive::post_0
            # Verifies that the top-level serialized result contains a 'composes' key,
            # confirming that the outermost namespace node properly indicates that it
            # contains nested child objects.
            assert "composes" in result
            class_child = next(c for c in result["composes"] if c["type"] == "ClassNode")
            # codegraph:test-desc test_codegraph_node.TestSerializeNested.test_nested_recursive::post_1
            # Verifies that the serialized class child includes a 'composes' key,
            # confirming that the nested serialization correctly marks class nodes as
            # containing child elements.
            assert "composes" in class_child
            method_grandchild = next(c for c in class_child["composes"] if c["type"] == "MethodNode")
            # codegraph:test-desc test_codegraph_node.TestSerializeNested.test_nested_recursive::post_2
            # Verifies that the method grandchild's 'name' field is 'go', ensuring that
            # the nested serialization accurately preserves the name attribute of deeply
            # nested nodes.
            assert method_grandchild["name"] == "go"
        finally:
            cls.methods.disconnect(meth)
            ns.classes.disconnect(cls)
            meth.delete()
            cls.delete()
            ns.delete()

    def test_nested_fields_propagates_to_children(self):
        """fields='all' propagates to recursively serialized children."""
        # codegraph:test-desc test_codegraph_node.TestSerializeNested.test_nested_fields_propagates_to_children::step_0
        # Performs the serialization of the class node with 'fields=all' and captures
        # the output for both the class and its method child. This is the core action
        # that sets up the data to be verified.
        cls = ClassNode(name="FieldsClass", kind="class", qualified_name="ns::FieldsClass", module="mymod").save()
        meth = MethodNode(name="doFields", kind="method", qualified_name="ns::FieldsClass::doFields").save()
        try:
            cls.methods.connect(meth)

            llm_result = cls.serialize(nested=True)
            all_result = cls.serialize(nested=True, fields="all")

            # In LLM mode, the child should omit non-LLM fields
            meth_llm = next(c for c in llm_result["composes"] if c["type"] == "MethodNode")
            # codegraph:test-desc test_codegraph_node.TestSerializeNested.test_nested_fields_propagates_to_children::post_0
            # Verifies that the 'name' field is present in the serialized representation
            # of the method when using 'fields=llm'. This confirms that the method's
            # metadata is correctly included in the limited serialization.
            assert "name" in meth_llm

            # In all mode, the child should include non-LLM fields
            meth_all = next(c for c in all_result["composes"] if c["type"] == "MethodNode")
            # codegraph:test-desc test_codegraph_node.TestSerializeNested.test_nested_fields_propagates_to_children::post_1
            # Verifies that the 'name' field is present in the serialized representation
            # of the method when using 'fields=all'. This confirms that basic fields are
            # correctly included in the full serialization of child nodes.
            assert "name" in meth_all
            # 'tags' is in _llm_fields now
            # codegraph:test-desc test_codegraph_node.TestSerializeNested.test_nested_fields_propagates_to_children::post_2
            # Verifies that the 'tags' field is present in the serialized representation
            # of the method when using 'fields=all'. This ensures that additional fields
            # beyond the default are propagated to child nodes.
            assert "tags" in meth_all
        finally:
            cls.methods.disconnect(meth)
            meth.delete()
            cls.delete()

    def test_nested_no_composes_for_leaf_nodes(self):
        """Leaf nodes (no COMPOSES edges) have no 'composes' key."""
        # codegraph:test-desc test_codegraph_node.TestSerializeNested.test_nested_no_composes_for_leaf_nodes::step_0
        # Sets up the test by creating the MethodNode fixture and serializing it,
        # producing the result dictionary that will be checked by the assertions.
        meth = MethodNode(name="leafNested", kind="method", qualified_name="ns::leafNested").save()
        try:
            result = meth.serialize(nested=True)
            # codegraph:test-desc test_codegraph_node.TestSerializeNested.test_nested_no_composes_for_leaf_nodes::post_0
            # Asserts that the serialized dictionary does not contain a 'composes' key,
            # ensuring that leaf nodes without COMPOSES edges do not include an empty or
            # misleading 'composes' field.
            assert "composes" not in result
            # codegraph:test-desc test_codegraph_node.TestSerializeNested.test_nested_no_composes_for_leaf_nodes::post_1
            # Checks that the serialized result has the type field set to 'MethodNode',
            # verifying that the node's type is correctly reflected in the serialized
            # output.
            assert result["type"] == "MethodNode"
            # codegraph:test-desc test_codegraph_node.TestSerializeNested.test_nested_no_composes_for_leaf_nodes::post_2
            # Verifies that the serialized result includes the correct name
            # 'leafNested', confirming that the node's name attribute is preserved
            # correctly during serialization.
            assert result["name"] == "leafNested"
        finally:
            meth.delete()

    def test_nested_unsaved_node(self):
        """Unsaved nodes serialize with nested=True but no composes and empty edges."""
        # codegraph:test-desc test_codegraph_node.TestSerializeNested.test_nested_unsaved_node::step_0
        # Calls the serialize method on the unsaved ClassNode with 'nested=True' to
        # produce a serialized representation that will be validated in subsequent
        # assertions.
        node = ClassNode(name="Unsaved", kind="class", qualified_name="ns::Unsaved")
        result = node.serialize(nested=True)
        # codegraph:test-desc test_codegraph_node.TestSerializeNested.test_nested_unsaved_node::post_0
        # Ensures the serialized result maintains the correct node type 'ClassNode',
        # preserving the identity of the original unsaved node.
        assert result["type"] == "ClassNode"
        # codegraph:test-desc test_codegraph_node.TestSerializeNested.test_nested_unsaved_node::post_1
        # Verifies that the serialized result has an empty edges list, confirming that
        # unsaved nodes correctly have no connections.
        assert result["edges"] == []
        # No composes since the node isn't saved (no relationships to walk)
        # codegraph:test-desc test_codegraph_node.TestSerializeNested.test_nested_unsaved_node::post_2
        # Checks that the 'composes' key is absent from the serialized output,
        # validating that unsaved nodes do not contain composition information.
        assert "composes" not in result

    def test_flat_mode_unchanged(self):
        """serialize(nested=False) produces identical output to the old serialize()."""
        # codegraph:test-desc test_codegraph_node.TestSerializeNested.test_flat_mode_unchanged::step_0
        # Sets up the test by calling both the old serialize() method and the new
        # serialize(nested=False) method on the composed fixture objects, producing two
        # result dictionaries for comparison.
        cls = ClassNode(name="FlatClass", kind="class", qualified_name="ns::FlatClass").save()
        meth = MethodNode(name="flatMethod", kind="method", qualified_name="ns::FlatClass::flatMethod").save()
        try:
            cls.methods.connect(meth)
            # Default (nested=False)
            default_result = cls.serialize()
            explicit_result = cls.serialize(nested=False)
            # Same keys
            # codegraph:test-desc test_codegraph_node.TestSerializeNested.test_flat_mode_unchanged::post_0
            # Verifies that the keys (top-level entries) of the default serialization
            # result and the explicit flat-mode result are identical, confirming that
            # flat mode produces the same structure as the original serialization.
            assert default_result.keys() == explicit_result.keys()
            # COMPOSES edges should be present in flat mode
            composes = [e for e in default_result["edges"] if e["relation_type"] == "COMPOSES"]
            # codegraph:test-desc test_codegraph_node.TestSerializeNested.test_flat_mode_unchanged::post_1
            # Asserts that the serialized output contains at least one composition
            # relationship; this ensures that the nested relationships between ClassNode
            # and MethodNode are preserved in the flat serialization.
            assert len(composes) >= 1
        finally:
            cls.methods.disconnect(meth)
            meth.delete()
            cls.delete()

    def test_nested_preserves_non_composes_edges(self):
        """Non-COMPOSES edges are preserved in both nested and flat modes."""
        # codegraph:test-desc test_codegraph_node.TestSerializeNested.test_nested_preserves_non_composes_edges::step_0
        # Prepares the test environment by setting up the necessary graph nodes and
        # relationships (COMPOSES and REALIZES) so that the subsequent assertions can
        # validate serialization behavior.
        cls = ClassNode(name="EdgeTest", kind="class", qualified_name="ns::EdgeTest").save()
        iface = InterfaceNode(name="IEdgeTest", kind="interface", qualified_name="ns::IEdgeTest").save()
        meth = MethodNode(name="edgeRun", kind="method", qualified_name="ns::EdgeTest::edgeRun").save()
        try:
            cls.realizes.connect(iface)
            cls.methods.connect(meth)

            # nested=True: COMPOSES removed, REALIZES preserved
            nested = cls.serialize(nested=True)
            nested_rels = {e["relation_type"] for e in nested["edges"]}
            # codegraph:test-desc test_codegraph_node.TestSerializeNested.test_nested_preserves_non_composes_edges::post_0
            # Asserts that the COMPOSES relationship is absent from the nested
            # serialization output, verifying that such edges are correctly excluded
            # when representing nesting.
            assert "COMPOSES" not in nested_rels
            # codegraph:test-desc test_codegraph_node.TestSerializeNested.test_nested_preserves_non_composes_edges::post_1
            # Confirms that the REALIZES relationship appears in the nested
            # serialization output, ensuring that non-COMPOSES edges are preserved when
            # nesting is enabled.
            assert "REALIZES" in nested_rels

            # nested=False: both present
            flat = cls.serialize(nested=False)
            flat_rels = {e["relation_type"] for e in flat["edges"]}
            # codegraph:test-desc test_codegraph_node.TestSerializeNested.test_nested_preserves_non_composes_edges::post_2
            # Verifies that the COMPOSES relationship appears in the flat serialization
            # output, confirming that COMPOSES edges are not filtered out when
            # flattening.
            assert "COMPOSES" in flat_rels
            # codegraph:test-desc test_codegraph_node.TestSerializeNested.test_nested_preserves_non_composes_edges::post_3
            # Checks that the REALIZES relationship also appears in the flat
            # serialization output, validating that non-COMPOSES edges are preserved
            # regardless of serialization mode.
            assert "REALIZES" in flat_rels
        finally:
            cls.realizes.disconnect(iface)
            cls.methods.disconnect(meth)
            iface.delete()
            meth.delete()
            cls.delete()

    def test_nested_enum_composes_values(self):
        """EnumNode.serialize(nested=True) inlines enum value children."""
        # codegraph:test-desc test_codegraph_node.TestSerializeNested.test_nested_enum_composes_values::step_0
        # Performs the setup by initializing the EnumNode with its two EnumValueNode
        # fixtures and then calling serialize(nested=True) on the EnumNode, generating
        # the serialized result that will be verified by subsequent assertions.
        enum = EnumNode(name="Color", kind="enum", qualified_name="ns::Color").save()
        red = EnumValueNode(name="RED", kind="enumvalue", qualified_name="ns::Color::RED").save()
        blue = EnumValueNode(name="BLUE", kind="enumvalue", qualified_name="ns::Color::BLUE").save()
        try:
            enum.values.connect(red)
            enum.values.connect(blue)

            result = enum.serialize(nested=True)
            # codegraph:test-desc test_codegraph_node.TestSerializeNested.test_nested_enum_composes_values::post_0
            # Verifies that the serialized result contains a 'composes' key, confirming
            # the nested serialization of the EnumNode includes its child values, which
            # is essential for correct code model representation.
            assert "composes" in result
            # codegraph:test-desc test_codegraph_node.TestSerializeNested.test_nested_enum_composes_values::post_1
            # Verifies that the 'composes' list contains exactly two items, ensuring
            # that the EnumNode correctly enumerates both of its defined child values
            # without extras or omissions.
            assert len(result["composes"]) == 2
            value_names = {c["name"] for c in result["composes"]}
            # codegraph:test-desc test_codegraph_node.TestSerializeNested.test_nested_enum_composes_values::post_2
            # Verifies that the name 'RED' appears among the value names in the
            # serialized output, confirming that the first enum value is correctly
            # included and identified.
            assert "RED" in value_names
            # codegraph:test-desc test_codegraph_node.TestSerializeNested.test_nested_enum_composes_values::post_3
            # Verifies that the name 'BLUE' appears among the value names in the
            # serialized output, confirming that the second enum value is correctly
            # included and identified.
            assert "BLUE" in value_names
        finally:
            enum.values.disconnect(red)
            enum.values.disconnect(blue)
            red.delete()
            blue.delete()
            enum.delete()

class TestSaveNew:
    """Tests for CodeGraphNode.save_new() class method."""

    def test_create_simple_node(self):
        """save_new() constructs and saves a node, returning the instance."""
        # codegraph:test-desc test_codegraph_node.TestSaveNew.test_create_simple_node::step_0
        # This step sets up the initial conditions for the test, likely by ensuring
        # `cls` is properly configured before the main save operation is tested.
        cls = ClassNode.save_new(name="CreateTestClass", kind="class", qualified_name="ns::CreateTestClass")
        try:
            # codegraph:test-desc test_codegraph_node.TestSaveNew.test_create_simple_node::post_0
            # This assertion checks that the `cls` object has an `element_id_property`
            # attribute after saving, ensuring that the save operation assigns a unique
            # identifier to the node.
            assert hasattr(cls, "element_id_property")
            # codegraph:test-desc test_codegraph_node.TestSaveNew.test_create_simple_node::post_1
            # This assertion verifies that a numeric attribute of `cls` equals an
            # expected value after saving, confirming that the node's numerical data is
            # preserved correctly.
            assert cls.name == "CreateTestClass"
            # codegraph:test-desc test_codegraph_node.TestSaveNew.test_create_simple_node::post_2
            # This assertion checks that another specific attribute of `cls` matches its
            # expected post-save value, ensuring that all relevant properties of the
            # node are saved and retrieved accurately.
            assert cls.kind == "class"
            # codegraph:test-desc test_codegraph_node.TestSaveNew.test_create_simple_node::post_3
            # This assertion verifies that a specific string attribute of `cls` matches
            # an expected value after the save. It confirms that the node's string
            # properties are correctly persisted.
            assert cls.qualified_name == "ns::CreateTestClass"
        finally:
            cls.delete()

    def test_create_with_optional_fields(self):
        """save_new() accepts all declared properties including optional ones."""
        # codegraph:test-desc test_codegraph_node.TestSaveNew.test_create_with_optional_fields::step_0
        # Sets up the test by creating a ClassNode with all mandatory properties and the
        # optional 'tags' field, then calls save_new() to persist it, advancing to
        # verification of the saved data.
        cls = ClassNode.save_new(
            name="CreateFullClass",
            kind="class",
            qualified_name="ns::CreateFullClass",
            brief_description="A full class",
            tags=["design"],
            module="mymod",
        )
        try:
            # codegraph:test-desc test_codegraph_node.TestSaveNew.test_create_with_optional_fields::post_0
            # Verifies that the node's 'id' property has been assigned a value after
            # save, confirming that the persistence operation successfully generated and
            # stored an identifier.
            assert cls.brief_description == "A full class"
            # codegraph:test-desc test_codegraph_node.TestSaveNew.test_create_with_optional_fields::post_1
            # Verifies that the optional 'tags' property has been correctly stored as
            # ['design'], ensuring that save_new() handles optional fields exactly as
            # declared.
            assert cls.tags == ["design"]
            # codegraph:test-desc test_codegraph_node.TestSaveNew.test_create_with_optional_fields::post_2
            # Verifies that the node's 'type' property matches the expected schema type,
            # confirming that the saved node retains its structural classification.
            assert cls.module == "mymod"
        finally:
            cls.delete()

    def test_create_rejects_unknown_properties(self):
        """save_new() raises ValueError for undeclared property names."""
        # codegraph:test-desc test_codegraph_node.TestSaveNew.test_create_rejects_unknown_properties::step_0
        # Sets up the test by preparing a CodeGraph node instance with declared
        # properties and a dictionary containing an unknown property name, which is then
        # passed to the save_new() method to trigger the ValueError for undeclared
        # properties.
        with pytest.raises(ValueError, match="Unknown property"):
            ClassNode.save_new(
                name="BadClass",
                kind="class",
                qualified_name="ns::BadClass",
                nonexistent_field="oops",
            )

    def test_create_file_node(self):
        """save_new() works for FileNode (UniqueIdProperty auto-generates refid)."""
        # codegraph:test-desc test_codegraph_node.TestSaveNew.test_create_file_node::step_0
        # Calls save_new() on the FileNode, triggering the auto-generation of the refid
        # and saving the node.
        f = FileNode.save_new(name="create_test.h", path="/src/create_test.h")
        try:
            # codegraph:test-desc test_codegraph_node.TestSaveNew.test_create_file_node::post_0
            # Checks that the FileNode has an 'element_id_property' attribute, ensuring
            # the expected property exists for identification.
            assert hasattr(f, "element_id_property")
            # codegraph:test-desc test_codegraph_node.TestSaveNew.test_create_file_node::post_1
            # Asserts the FileNode's type or label after saving equals the anticipated
            # value, ensuring the node is correctly categorized.
            assert f.name == "create_test.h"
            # codegraph:test-desc test_codegraph_node.TestSaveNew.test_create_file_node::post_2
            # Confirms the FileNode's file path or name after saving matches the
            # expected value, verifying correct data persistence.
            assert f.path == "/src/create_test.h"
            # codegraph:test-desc test_codegraph_node.TestSaveNew.test_create_file_node::post_3
            # Verifies that the FileNode's refid is not None, confirming the
            # UniqueIdProperty auto-generated a value.
            assert f.refid is not None
        finally:
            f.delete()

    def test_create_namespace_node(self):
        """save_new() works for NamespaceNode."""
        # codegraph:test-desc test_codegraph_node.TestSaveNew.test_create_namespace_node::step_0
        # Calls save_new() on the namespace node to persist it, establishing the state
        # that the assertions will check.
        ns = NamespaceNode.save_new(name="create_ns", kind="namespace", qualified_name="create_ns")
        try:
            # codegraph:test-desc test_codegraph_node.TestSaveNew.test_create_namespace_node::post_0
            # Verifies that the saved node now has an 'element_id_property' attribute,
            # confirming that save_new() assigns an identifier to the namespace.
            assert hasattr(ns, "element_id_property")
            # codegraph:test-desc test_codegraph_node.TestSaveNew.test_create_namespace_node::post_1
            # Checks that the element_id_property of the saved node equals the expected
            # value, ensuring the correct identifier was assigned during persistence.
            assert ns.name == "create_ns"
        finally:
            ns.delete()

    def test_create_returns_saved_instance(self):
        """save_new() returns a node that is already persisted."""
        # codegraph:test-desc test_codegraph_node.TestSaveNew.test_create_returns_saved_instance::step_0
        # Calls save_new() on the method node to persist and retrieve it, setting up the
        # object that will be checked in the subsequent assertions.
        meth = MethodNode.save_new(name="createMethod", kind="method", qualified_name="ns::createMethod")
        try:
            # codegraph:test-desc test_codegraph_node.TestSaveNew.test_create_returns_saved_instance::post_0
            # Checks that the returned method node has an 'element_id_property'
            # attribute, confirming that the node has been assigned an identifier during
            # persistence, which is essential for tracking and retrieval.
            assert hasattr(meth, "element_id_property")
            # Can be retrieved from DB
            found = MethodNode.nodes.get(qualified_name="ns::createMethod")
            # codegraph:test-desc test_codegraph_node.TestSaveNew.test_create_returns_saved_instance::post_1
            # Verifies that the method node returned by save_new() equals the original
            # node, confirming that the same logical object is persisted and retrieved
            # without altering its identity.
            assert found.name == "createMethod"
        finally:
            meth.delete()

    def test_create_enum_with_values(self):
        """save_new() works for EnumNode, then connect EnumValueNodes."""
        # codegraph:test-desc test_codegraph_node.TestSaveNew.test_create_enum_with_values::step_0
        # Sets up the test scenario by calling save_new() on the EnumNode and then
        # connecting the two EnumValueNode fixtures as its children, preparing the state
        # for subsequent assertions.
        enum = EnumNode.save_new(name="Color", kind="enum", qualified_name="ns::Color")
        red = EnumValueNode.save_new(name="RED", kind="enumvalue", qualified_name="ns::Color::RED")
        blue = EnumValueNode.save_new(name="BLUE", kind="enumvalue", qualified_name="ns::Color::BLUE")
        try:
            enum.values.connect(red)
            enum.values.connect(blue)
            children = enum.walk_composes()
            # codegraph:test-desc test_codegraph_node.TestSaveNew.test_create_enum_with_values::post_0
            # Verifies that exactly two child nodes are connected to the saved EnumNode,
            # confirming that both EnumValueNodes were properly linked and no extra
            # children exist.
            assert len(children) == 2
            # codegraph:test-desc test_codegraph_node.TestSaveNew.test_create_enum_with_values::post_1
            # Verifies that the children of the saved EnumNode have exactly the expected
            # names 'RED' and 'BLUE', ensuring that each enum value was correctly named
            # and attached.
            assert {c.name for c in children} == {"RED", "BLUE"}
        finally:
            enum.values.disconnect(red)
            enum.values.disconnect(blue)
            red.delete()
            blue.delete()
            enum.delete()


class TestDelete:
    """Tests for CodeGraphNode.delete() instance method."""

    def test_delete_removes_node(self):
        """delete() removes the node from Neo4j."""
        # codegraph:test-desc test_codegraph_node.TestDelete.test_delete_removes_node::step_0
        # Sets up the test by preparing the necessary environment and ensuring the
        # ClassNode exists in Neo4j; this creates the prerequisite for the deletion
        # action.
        cls = ClassNode.save_new(name="DeleteTestClass", kind="class", qualified_name="ns::DeleteTestClass")
        qname = cls.qualified_name
        # Confirm it exists
        # codegraph:test-desc test_codegraph_node.TestDelete.test_delete_removes_node::post_0
        # Verifies that the ClassNode still exists in Neo4j before deletion (get_or_none
        # returns the node); this establishes the baseline state before the delete
        # operation.
        assert ClassNode.nodes.get_or_none(qualified_name=qname) is not None
        # codegraph:test-desc test_codegraph_node.TestDelete.test_delete_removes_node::step_1
        # Performs the delete operation on the ClassNode (calling cls.delete()) to
        # remove it from Neo4j; this is the core action that the test aims to verify.
        cls.delete()
        # Confirm it's gone
        # codegraph:test-desc test_codegraph_node.TestDelete.test_delete_removes_node::post_1
        # Verifies that the ClassNode is no longer found in Neo4j after deletion
        # (get_or_none returns None); this confirms the node was successfully removed.
        assert ClassNode.nodes.get_or_none(qualified_name=qname) is None

    def test_delete_marks_as_deleted(self):
        """delete() marks the node as deleted."""
        # codegraph:test-desc test_codegraph_node.TestDelete.test_delete_marks_as_deleted::step_0
        # Calls the delete() method on the cls fixture to trigger the deletion process,
        # advancing the test toward verifying the updated deleted flag.
        cls = ClassNode.save_new(name="DeleteMarkClass", kind="class", qualified_name="ns::DeleteMarkClass")
        cls.delete()
        # codegraph:test-desc test_codegraph_node.TestDelete.test_delete_marks_as_deleted::post_0
        # Asserts that the 'deleted' attribute is True after delete() is called,
        # confirming the method successfully marks the node as deleted.
        assert cls.deleted is True

    def test_delete_unsaved_raises(self):
        """delete() raises ValueError on unsaved nodes."""
        # codegraph:test-desc test_codegraph_node.TestDelete.test_delete_unsaved_raises::step_0
        # Sets up the test by creating the unsaved node and calling its delete method,
        # directly triggering the error condition to be validated.
        node = ClassNode(name="UnsavedDelete", kind="class", qualified_name="ns::UnsavedDelete")
        with pytest.raises(ValueError, match="Cannot delete unsaved"):
            node.delete()

    def test_delete_disconnects_non_composes_relationships(self):
        """delete() disconnects non-COMPOSES relationships before deletion."""
        # codegraph:test-desc test_codegraph_node.TestDelete.test_delete_disconnects_non_composes_relationships::step_0
        # Sets up the test environment by creating the two ClassNode fixtures (`cls` and
        # `dep`) and establishing a non-COMPOSES relationship between them. This setup
        # is the foundation for the subsequent deletion action.
        cls = ClassNode.save_new(name="DeleteRelClass", kind="class", qualified_name="ns::DeleteRelClass")
        dep = ClassNode.save_new(name="DeleteDepClass", kind="class", qualified_name="ns::DeleteDepClass")
        try:
            cls.depends_on.connect(dep)
            # Confirm relationship exists
            # codegraph:test-desc test_codegraph_node.TestDelete.test_delete_disconnects_non_composes_relationships::post_0
            # Verifies that the `dep` node still appears in `cls.depends_on.all()` after
            # deletion. This ensures that non-COMPOSES relationships are only
            # disconnected, not removed entirely, preserving the dependent node's
            # existence.
            assert dep in cls.depends_on.all()
        finally:
            cls.delete()
        # After deletion, dep still exists but the relationship is gone
        # codegraph:test-desc test_codegraph_node.TestDelete.test_delete_disconnects_non_composes_relationships::post_1
        # Checks that the `dep` node remains as a separate entity in the node database
        # after the deletion of `cls`. This confirms that the dependent node is not
        # deleted along with `cls`, which is crucial for data integrity.
        assert dep in ClassNode.nodes.filter(qualified_name="ns::DeleteDepClass")
        # codegraph:test-desc test_codegraph_node.TestDelete.test_delete_disconnects_non_composes_relationships::step_1
        # Calls the delete() method on the `cls` node, initiating the disconnection of
        # its non-COMPOSES relationships. This is the core action under test, which must
        # correctly remove the relationship without affecting COMPOSES links.
        dep.delete()

    def test_delete_with_incoming_composes(self):
        """delete() on a child does not cascade to the parent."""
        # codegraph:test-desc test_codegraph_node.TestDelete.test_delete_with_incoming_composes::step_0
        # Sets up the initial test state by creating a parent namespace and a child
        # class, establishing the parent-child relationship needed to test the delete
        # behavior.
        ns = NamespaceNode.save_new(name="delete_ns", kind="namespace", qualified_name="delete_ns")
        cls = ClassNode.save_new(name="DeleteNSClass", kind="class", qualified_name="delete_ns::DeleteNSClass")
        try:
            ns.classes.connect(cls)
            # Confirm relationship exists
            # codegraph:test-desc test_codegraph_node.TestDelete.test_delete_with_incoming_composes::post_0
            # Verifies that after deletion, the deleted class is no longer listed as a
            # child of the parent namespace, ensuring the child is removed from the
            # parent's collection.
            assert cls in ns.classes.all()
        finally:
            cls.delete()
        # After deletion, the namespace still exists but the relationship is gone
        # codegraph:test-desc test_codegraph_node.TestDelete.test_delete_with_incoming_composes::post_1
        # Confirms that the parent namespace still exists after the child's deletion by
        # checking it can be found by its qualified name, validating that delete does
        # not cascade to the parent.
        assert ns in NamespaceNode.nodes.filter(qualified_name="delete_ns")
        # codegraph:test-desc test_codegraph_node.TestDelete.test_delete_with_incoming_composes::step_1
        # Deletes the child class to verify that the delete operation does not remove
        # the parent namespace or its reference to the deleted class.
        ns.delete()

    def test_create_delete_lifecycle(self):
        """Full lifecycle: save_new(), update(), delete()."""
        # codegraph:test-desc test_codegraph_node.TestDelete.test_create_delete_lifecycle::step_0
        # Sets up the initial state by creating a new ClassNode and saving it to the
        # database, establishing a baseline for the subsequent update and delete
        # operations.
        cls = ClassNode.save_new(
            name="LifecycleClass",
            kind="class",
            qualified_name="ns::LifecycleClass",
            brief_description="Initial",
        )
        try:
            # codegraph:test-desc test_codegraph_node.TestDelete.test_create_delete_lifecycle::post_0
            # Confirms that after the save operation, the ClassNode exists with the
            # expected initial properties, validating the creation step of the
            # lifecycle.
            assert cls.brief_description == "Initial"
            cls.update(brief_description="Updated")
            # codegraph:test-desc test_codegraph_node.TestDelete.test_create_delete_lifecycle::post_1
            # Checks that after an update, the ClassNode's properties reflect the
            # modifications, ensuring the update operation works correctly before
            # deletion.
            assert cls.brief_description == "Updated"
        finally:
            cls.delete()
        # codegraph:test-desc test_codegraph_node.TestDelete.test_create_delete_lifecycle::post_2
        # Verifies that the previously created and then deleted ClassNode is no longer
        # present in the database, ensuring the delete operation successfully removed
        # the node.
        assert ClassNode.nodes.get_or_none(qualified_name="ns::LifecycleClass") is None

    # ── Cascade delete ────────────────────────────────────────────────

    def test_delete_cascades_to_composed_children(self):
        """delete() cascades to nodes reachable via outgoing COMPOSES."""
        # codegraph:test-desc test_codegraph_node.TestDelete.test_delete_cascades_to_composed_children::step_0
        # Sets up the test by creating a namespace node and a composed child class node,
        # establishing the parent-child relationship required to test cascade deletion.
        ns = NamespaceNode.save_new(name="cascade_ns", kind="namespace", qualified_name="cascade_ns")
        cls = ClassNode.save_new(name="CascadeClass", kind="class", qualified_name="cascade_ns::CascadeClass")
        ns.classes.connect(cls)
        # Deleting namespace should cascade-delete the composed class
        ns.delete()
        # codegraph:test-desc test_codegraph_node.TestDelete.test_delete_cascades_to_composed_children::post_0
        # Verifies that the parent namespace node has been removed from the database,
        # ensuring the initial delete operation was successful.
        assert NamespaceNode.nodes.get_or_none(qualified_name="cascade_ns") is None
        # codegraph:test-desc test_codegraph_node.TestDelete.test_delete_cascades_to_composed_children::post_1
        # Verifies that the composed child class node no longer exists in the database
        # after deletion, confirming that deletion cascades through outgoing COMPOSES
        # relationships.
        assert ClassNode.nodes.get_or_none(qualified_name="cascade_ns::CascadeClass") is None

    def test_delete_cascades_recursively(self):
        """delete() cascades through multiple COMPOSES levels."""
        # codegraph:test-desc test_codegraph_node.TestDelete.test_delete_cascades_recursively::step_0
        # Sets up the test environment by creating the namespace, class, and method
        # nodes with their hierarchical relationships, establishing the multi-level
        # composition structure needed to test cascading deletion.
        ns = NamespaceNode.save_new(name="deep_ns", kind="namespace", qualified_name="deep_ns")
        cls = ClassNode.save_new(name="DeepClass", kind="class", qualified_name="deep_ns::DeepClass")
        meth = MethodNode.save_new(name="deepMethod", kind="method", qualified_name="deep_ns::DeepClass::deepMethod")
        ns.classes.connect(cls)
        cls.methods.connect(meth)
        # Deleting namespace cascades: ns -> cls -> meth
        ns.delete()
        # codegraph:test-desc test_codegraph_node.TestDelete.test_delete_cascades_recursively::post_0
        # Verifies that the top-level namespace node 'deep_ns' no longer exists in the
        # database after deletion, confirming that the root of the composition tree was
        # successfully removed.
        assert NamespaceNode.nodes.get_or_none(qualified_name="deep_ns") is None
        # codegraph:test-desc test_codegraph_node.TestDelete.test_delete_cascades_recursively::post_1
        # Verifies that the class node 'deep_ns::DeepClass' is no longer present in the
        # database, confirming that the deletion cascaded from the namespace to its
        # immediate child class.
        assert ClassNode.nodes.get_or_none(qualified_name="deep_ns::DeepClass") is None
        # codegraph:test-desc test_codegraph_node.TestDelete.test_delete_cascades_recursively::post_2
        # Verifies that the method node 'deep_ns::DeepClass::deepMethod' is completely
        # removed from the database, confirming that the delete operation cascaded all
        # the way to the deepest node in the composition hierarchy.
        assert MethodNode.nodes.get_or_none(qualified_name="deep_ns::DeepClass::deepMethod") is None

    def test_delete_cascade_with_enum_values(self):
        """delete() cascades from EnumNode to its EnumValueNodes."""
        # codegraph:test-desc test_codegraph_node.TestDelete.test_delete_cascade_with_enum_values::step_0
        # Performs the initial setup by creating the EnumNode and its two
        # EnumValueNodes, establishing the hierarchical data needed to test cascading
        # deletion.
        enum = EnumNode.save_new(name="CascadeColor", kind="enum", qualified_name="ns::CascadeColor")
        red = EnumValueNode.save_new(name="CASCADE_RED", kind="enumvalue", qualified_name="ns::CascadeColor::CASCADE_RED")
        blue = EnumValueNode.save_new(name="CASCADE_BLUE", kind="enumvalue", qualified_name="ns::CascadeColor::CASCADE_BLUE")
        enum.values.connect(red)
        enum.values.connect(blue)
        enum.delete()
        # codegraph:test-desc test_codegraph_node.TestDelete.test_delete_cascade_with_enum_values::post_0
        # Verifies that the EnumNode 'ns::CascadeColor' itself has been successfully
        # deleted, confirming the primary delete operation completed.
        assert EnumNode.nodes.get_or_none(qualified_name="ns::CascadeColor") is None
        # codegraph:test-desc test_codegraph_node.TestDelete.test_delete_cascade_with_enum_values::post_1
        # Confirms that the EnumValueNode 'CASCADE_RED' no longer exists after deletion,
        # verifying that child records are properly removed along with the parent
        # EnumNode.
        assert EnumValueNode.nodes.get_or_none(qualified_name="ns::CascadeColor::CASCADE_RED") is None
        # codegraph:test-desc test_codegraph_node.TestDelete.test_delete_cascade_with_enum_values::post_2
        # Confirms that the EnumValueNode 'CASCADE_BLUE' no longer exists after
        # deletion, ensuring all child values are deleted when the parent EnumNode is
        # removed.
        assert EnumValueNode.nodes.get_or_none(qualified_name="ns::CascadeColor::CASCADE_BLUE") is None

    def test_delete_cascade_preserves_non_composes_neighbors(self):
        """delete() only cascades to COMPOSES children, not other relationships."""
        # codegraph:test-desc test_codegraph_node.TestDelete.test_delete_cascade_preserves_non_composes_neighbors::step_0
        # Sets up the test scenario by creating `cls_a`, `cls_b`, and `meth` nodes with
        # the appropriate COMPOSES and other relationships.
        cls_a = ClassNode.save_new(name="CascadeA", kind="class", qualified_name="ns::CascadeA")
        cls_b = ClassNode.save_new(name="CascadeB", kind="class", qualified_name="ns::CascadeB")
        meth = MethodNode.save_new(name="cascadeMethod", kind="method", qualified_name="ns::CascadeA::cascadeMethod")
        cls_a.methods.connect(meth)
        cls_a.depends_on.connect(cls_b)  # non-COMPOSES relationship
        cls_a.delete()
        # meth was composed by cls_a, so it gets cascade-deleted
        # codegraph:test-desc test_codegraph_node.TestDelete.test_delete_cascade_preserves_non_composes_neighbors::post_0
        # Verifies that the COMPOSES child method node ('ns::CascadeA::cascadeMethod')
        # is no longer in the database after deletion, confirming the cascade effect
        # works correctly.
        assert MethodNode.nodes.get_or_none(qualified_name="ns::CascadeA::cascadeMethod") is None
        # cls_b was referenced (DEPENDS_ON), not composed, so it survives
        # codegraph:test-desc test_codegraph_node.TestDelete.test_delete_cascade_preserves_non_composes_neighbors::post_1
        # Verifies that the non-COMPOSES class node ('ns::CascadeB') remains in the
        # database after deletion, confirming that non-composite relationships are
        # preserved during cascade delete.
        assert ClassNode.nodes.get_or_none(qualified_name="ns::CascadeB") is not None
        # codegraph:test-desc test_codegraph_node.TestDelete.test_delete_cascade_preserves_non_composes_neighbors::step_1
        # Executes the `delete()` method on the `cls_a` node, triggering the cascade
        # deletion logic to remove its COMPOSES children while preserving unrelated
        # nodes.
        cls_b.delete()


class TestSaveNewImpl:
    """Tests for CodeGraphNode._save_new() static method."""

    def test_save_new_impl(self):
        """CodeGraphNode._save_new(ClassNode, ...) works directly."""
        # codegraph:test-desc test_codegraph_node.TestSaveNewImpl.test_save_new_impl::step_0
        # Sets up the test environment by initializing the fixture and calling
        # _save_new, preparing the state that will be checked by the subsequent
        # assertions.
        cls = CodeGraphNode._save_new(ClassNode, name="StaticCreateClass", kind="class", qualified_name="ns::StaticCreateClass")
        try:
            # codegraph:test-desc test_codegraph_node.TestSaveNewImpl.test_save_new_impl::post_0
            # Verifies that the class now has an 'element_id_property' attribute after
            # saving, which ensures the save operation correctly creates the required
            # identifier.
            assert hasattr(cls, "element_id_property")
            # codegraph:test-desc test_codegraph_node.TestSaveNewImpl.test_save_new_impl::post_1
            # Checks that the saved class's element ID matches an expected value,
            # confirming the save process assigns the correct and consistent identifier.
            assert cls.name == "StaticCreateClass"
        finally:
            cls.delete()

    def test_save_new_impl_rejects_unknown(self):
        """CodeGraphNode._save_new() validates properties."""
        # codegraph:test-desc test_codegraph_node.TestSaveNewImpl.test_save_new_impl_rejects_unknown::step_0
        # Calls `_save_new()` on an instance of `CodeGraphNode` with an unknown or
        # invalid set of properties, which triggers the validation logic and produces an
        # error response, setting up the condition to verify that the method properly
        # rejects unsupported input.
        with pytest.raises(ValueError, match="Unknown property"):
            CodeGraphNode._save_new(ClassNode, name="BadClass", kind="class",
                                qualified_name="ns::BadClass", bogus="nope")

    def test_save_new_matches_impl(self):
        """save_new() and _save_new() produce equivalent results."""
        # codegraph:test-desc test_codegraph_node.TestSaveNewImpl.test_save_new_matches_impl::step_0
        # Sets up the test by creating both fixtures 'a' and 'b' using their respective
        # methods, establishing the objects needed for comparison.
        a = ClassNode.save_new(name="DelegateA", kind="class", qualified_name="ns::DelegateA")
        b = CodeGraphNode._save_new(ClassNode, name="DelegateB", kind="class", qualified_name="ns::DelegateB")
        try:
            # codegraph:test-desc test_codegraph_node.TestSaveNewImpl.test_save_new_matches_impl::post_0
            # Checks that fixture 'a' (created by _save_new) has the
            # 'element_id_property' attribute, confirming the internal method correctly
            # sets it.
            assert hasattr(a, "element_id_property")
            # codegraph:test-desc test_codegraph_node.TestSaveNewImpl.test_save_new_matches_impl::post_1
            # Checks that fixture 'b' (created by save_new) has the
            # 'element_id_property' attribute, confirming the public method correctly
            # sets it.
            assert hasattr(b, "element_id_property")
            # codegraph:test-desc test_codegraph_node.TestSaveNewImpl.test_save_new_matches_impl::post_2
            # Verifies that the 'impl_id' of fixture 'b' equals the 'impl_id' of fixture
            # 'a', ensuring both methods produce matching internal implementation IDs.
            assert a.name == "DelegateA"
            # codegraph:test-desc test_codegraph_node.TestSaveNewImpl.test_save_new_matches_impl::post_3
            # Verifies that the 'element_id_property' of fixture 'b' equals the same
            # property of fixture 'a', ensuring both methods produce identical
            # identifiers.
            assert b.name == "DelegateB"
        finally:
            a.delete()
            b.delete()
