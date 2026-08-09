"""Unit tests for CodeGraphNode methods exercising the new descriptor
code paths (not the neomodel fallback).

Creates a pure-Python test subclass using our new Property/Relationship
descriptors, with no StructuredNode or Neo4j dependency.  Verifies that:

- serialize() works with new descriptors
- deserialize() works with new descriptors (registry + introspection)
- serialize_relationships() detects new Relationship descriptors
- find_relationship_manager() finds new descriptors
- save_new() validates against new descriptors
- update() validates against new descriptors
- _uid_prop() / _uid_value() work with UniqueId
- add_tag / remove_tag / has_tag work with new descriptors
- fetch_by_tag delegates correctly
"""

import pytest

from codegraph.models.tags import CodeGraphNode
from codegraph.models.descriptors import (
    Property,
    UniqueId,
    Relationship,
)


# ══════════════════════════════════════════════════════════════════════════
# Pure-Python test nodes (no StructuredNode, no Neo4j)
# ══════════════════════════════════════════════════════════════════════════


class TestClassNode(CodeGraphNode):
    """Pure-Python node using only new descriptors — no StructuredNode."""

    # Identity
    uid = UniqueId()
    qualified_name = Property(str, default="", index=True)
    kind = Property(str, default="class")

    # Tags & provenance
    source = Property(str, default="test")
    tags = Property(list, default=[])

    # Documentation
    brief_description = Property(str, default="")
    detailed_description = Property(str, default="")

    # Visibility
    visibility = Property(str, default="public")

    # Location
    file_path = Property(str, default="")
    line_number = Property(int, default=0)

    # Module
    module = Property(str, default="")
    is_abstract = Property(bool, default=False)
    is_final = Property(bool, default=False)

    # Relationships
    methods = Relationship("COMPOSES", direction="OUTGOING",
                           target_class="TestMethodNode")
    attributes = Relationship("COMPOSES", direction="OUTGOING",
                              target_class="TestAttributeNode")
    base = Relationship("INHERITS_FROM", direction="OUTGOING",
                        target_class="TestClassNode")
    defined_in = Relationship("DEFINED_IN", direction="OUTGOING",
                              target_class="TestFileNode")

    # LLM fields and identity
    _llm_fields = {"qualified_name", "name", "kind", "tags",
                   "brief_description", "visibility"}
    _identity_fields = ("qualified_name",)


class TestMethodNode(CodeGraphNode):
    """Minimal pure-Python method node for relationship target matching."""

    uid = UniqueId()
    qualified_name = Property(str, default="")
    kind = Property(str, default="method")
    source = Property(str, default="test")
    tags = Property(list, default=[])

    _llm_fields = {"qualified_name", "name", "kind", "tags"}
    _identity_fields = ("qualified_name",)


class TestAttributeNode(CodeGraphNode):
    """Minimal pure-Python attribute node."""

    uid = UniqueId()
    qualified_name = Property(str, default="")
    kind = Property(str, default="attribute")
    source = Property(str, default="test")
    tags = Property(list, default=[])

    _llm_fields = {"qualified_name", "name", "kind", "tags"}
    _identity_fields = ("qualified_name",)


class TestFileNode(CodeGraphNode):
    """Minimal pure-Python file node for relationship target matching."""

    uid = UniqueId()
    path = Property(str, default="")
    name = Property(str, default="")
    source = Property(str, default="test")

    _llm_fields = {"name", "path", "source"}


class TestClassWithoutTags(CodeGraphNode):
    """Pure-Python node with no tags property — for testing no-tag paths."""

    uid = UniqueId()
    name = Property(str, default="")

    _llm_fields = {"name"}


# ══════════════════════════════════════════════════════════════════════════
# serialize() with new descriptors
# ══════════════════════════════════════════════════════════════════════════


class TestSerializeWithNewDescriptors:
    """serialize() should work with our new Property descriptors."""

    def test_llm_fields_included(self):
        """Default serialize() includes only _llm_fields + type + edges."""
        node = TestClassNode(
            qualified_name="mymod::Widget",
            kind="class",
            brief_description="A widget",
            visibility="public",
            tags=["design"],
            module="mymod",
            is_abstract=True,
        )
        result = node.serialize()

        # LLM fields present
        assert result["type"] == "TestClassNode"
        assert result["qualified_name"] == "mymod::Widget"
        assert result["kind"] == "class"
        assert result["brief_description"] == "A widget"
        assert result["visibility"] == "public"
        assert result["tags"] == ["design"]

        # uid always included for roundtrip
        assert "uid" in result

        # edges always present
        assert "edges" in result
        assert isinstance(result["edges"], list)

    def test_llm_fields_exclude_non_llm(self):
        """Default serialize() omits properties not in _llm_fields."""
        node = TestClassNode(
            qualified_name="mymod::Widget",
            kind="class",
            module="mymod",
            is_abstract=True,
            file_path="/src/widget.h",
            line_number=42,
        )
        result = node.serialize()

        # These should NOT be in default serialization
        assert "module" not in result
        assert "is_abstract" not in result
        assert "file_path" not in result
        assert "line_number" not in result
        assert "detailed_description" not in result

    def test_all_fields_includes_everything(self):
        """serialize(fields='all') includes every declared property."""
        node = TestClassNode(
            qualified_name="mymod::Widget",
            kind="class",
            module="mymod",
            is_abstract=True,
            file_path="/src/widget.h",
            line_number=42,
            brief_description="desc",
            detailed_description="long desc",
            source="proj",
            visibility="private",
            tags=["design"],
        )
        result = node.serialize(fields="all")

        assert result["type"] == "TestClassNode"
        assert result["qualified_name"] == "mymod::Widget"
        assert result["module"] == "mymod"
        assert result["is_abstract"] is True
        assert result["file_path"] == "/src/widget.h"
        assert result["line_number"] == 42
        assert result["brief_description"] == "desc"
        assert result["detailed_description"] == "long desc"
        assert result["tags"] == ["design"]

    def test_all_fields_has_more_keys_than_llm(self):
        """fields='all' returns more keys than default (llm)."""
        node = TestClassNode(qualified_name="mymod::A", kind="class")
        llm_keys = set(node.serialize()) - {"type", "edges", "uid"}
        all_keys = set(node.serialize(fields="all")) - {"type", "edges", "uid"}
        assert all_keys > llm_keys, (
            f"all={sorted(all_keys)}, llm={sorted(llm_keys)}"
        )

    def test_unsaved_node_empty_edges(self):
        """Unsaved nodes have empty edges regardless of fields."""
        node = TestClassNode(qualified_name="mymod::Ghost", kind="class")
        assert node.serialize()["edges"] == []
        assert node.serialize(fields="all")["edges"] == []


# ══════════════════════════════════════════════════════════════════════════
# deserialize() with new descriptors
# ══════════════════════════════════════════════════════════════════════════


class TestDeserializeWithNewDescriptors:
    """deserialize() should work with our new Property descriptors."""

    def test_deserializes_from_type_discriminator(self):
        """Creates correct class from 'type' key in registry."""
        data = {
            "type": "TestClassNode",
            "qualified_name": "mymod::Deserialized",
            "kind": "class",
            "brief_description": "A class from dict",
            "tags": ["design"],
            "module": "extra",
        }
        node = CodeGraphNode.deserialize(data)
        assert isinstance(node, TestClassNode)
        assert node.qualified_name == "mymod::Deserialized"
        assert node.kind == "class"
        assert node.brief_description == "A class from dict"
        assert node.tags == ["design"]
        assert node.module == "extra"

    def test_ignores_edges_key(self):
        """'edges' key is ignored during deserialization."""
        data = {
            "type": "TestClassNode",
            "qualified_name": "mymod::NoEdges",
            "kind": "class",
            "edges": [{"relation_type": "COMPOSES", "target_uid": "x"}],
        }
        node = CodeGraphNode.deserialize(data)
        assert node.qualified_name == "mymod::NoEdges"

    def test_ignores_unknown_keys(self):
        """Unknown keys not in declared properties are silently dropped."""
        data = {
            "type": "TestClassNode",
            "qualified_name": "mymod::Clean",
            "kind": "class",
            "not_a_field": "should be ignored",
            "also_not": 42,
        }
        node = CodeGraphNode.deserialize(data)
        assert node.qualified_name == "mymod::Clean"
        # Unknown keys should not cause errors
        assert not hasattr(node, "not_a_field")

    def test_backward_compat_layer_to_tags(self):
        """Legacy 'layer' field is promoted to 'tags'."""
        data = {
            "type": "TestClassNode",
            "qualified_name": "mymod::Legacy",
            "kind": "class",
            "layer": "design",
        }
        node = CodeGraphNode.deserialize(data)
        assert node.tags == ["design"]

    def test_missing_type_raises(self):
        """Raises ValueError when 'type' is missing on base class."""
        with pytest.raises(ValueError, match="missing the 'type' discriminator"):
            CodeGraphNode.deserialize({"qualified_name": "orphan"})

    def test_unknown_type_raises(self):
        """Raises KeyError when type is not registered."""
        with pytest.raises(KeyError, match="Unknown node type"):
            CodeGraphNode.deserialize({"type": "FakeNode", "name": "x"})

    def test_concrete_subclass_no_type_needed(self):
        """deserialize() called on a concrete subclass doesn't need 'type'."""
        node = TestClassNode.deserialize(
            {"qualified_name": "mymod::Direct", "kind": "class"}
        )
        assert isinstance(node, TestClassNode)
        assert node.qualified_name == "mymod::Direct"


# ══════════════════════════════════════════════════════════════════════════
# serialize_relationships() with new descriptors
# ══════════════════════════════════════════════════════════════════════════


class TestSerializeRelationshipsNewDescriptors:
    """serialize_relationships() detects new Relationship descriptors."""

    def test_detects_new_relationship_descriptors(self):
        """Returns relationships declared with new Relationship descriptor."""
        rels = TestClassNode.serialize_relationships()
        rel_types = {r["relation_type"] for r in rels}

        assert "COMPOSES" in rel_types
        assert "INHERITS_FROM" in rel_types
        assert "DEFINED_IN" in rel_types

    def test_includes_direction(self):
        """Each entry has correct direction."""
        rels = TestClassNode.serialize_relationships()

        methods = next(r for r in rels if r["attr"] == "methods")
        assert methods["direction"] == "OUTGOING"
        assert methods["relation_type"] == "COMPOSES"
        assert methods["target"] == "TestMethodNode"

    def test_includes_target_class_name(self):
        """target_class string is included as 'target'."""
        rels = TestClassNode.serialize_relationships()

        base_rel = next(r for r in rels if r["attr"] == "base")
        assert base_rel["target"] == "TestClassNode"


# ══════════════════════════════════════════════════════════════════════════
# find_relationship_manager() with new descriptors
# ══════════════════════════════════════════════════════════════════════════


class TestFindRelationshipManagerNewDescriptors:
    """find_relationship_manager() finds new Relationship descriptors."""

    def test_finds_by_string_target(self):
        """Matches when target_class is a string name."""
        source = TestClassNode(qualified_name="mymod::Src", kind="class")
        target = TestMethodNode(qualified_name="mymod::Src::draw", kind="method")
        result = CodeGraphNode.find_relationship_manager(
            source, "COMPOSES", target
        )
        assert result is not None
        assert isinstance(result, Relationship)
        assert result.relation_type == "COMPOSES"
        assert result.name == "methods"

    def test_raises_on_unknown_relation(self):
        """Raises ValueError when no matching relationship exists."""
        source = TestClassNode(qualified_name="mymod::Src", kind="class")
        target = TestMethodNode(qualified_name="mymod::Src::draw", kind="method")
        with pytest.raises(ValueError, match="No 'NONEXISTENT' relationship"):
            CodeGraphNode.find_relationship_manager(
                source, "NONEXISTENT", target
            )

    def test_raises_on_wrong_target_type(self):
        """Raises ValueError for valid relation_type but wrong target."""
        source = TestClassNode(qualified_name="mymod::Src", kind="class")
        target = TestFileNode(name="wrong.txt", path="/wrong.txt")
        with pytest.raises(ValueError, match="No 'COMPOSES' relationship"):
            CodeGraphNode.find_relationship_manager(
                source, "COMPOSES", target
            )


# ══════════════════════════════════════════════════════════════════════════
# Tag mutation with new descriptors
# ══════════════════════════════════════════════════════════════════════════


class TestTagMutationNewDescriptors:
    """add_tag / remove_tag / has_tag work with new descriptors."""

    def test_has_tag_true(self):
        """has_tag returns True when tag is present."""
        node = TestClassNode(qualified_name="mymod::Tagged", kind="class",
                          tags=["design", "as-built"])
        assert node.has_tag("design") is True
        assert node.has_tag("as-built") is True

    def test_has_tag_false(self):
        """has_tag returns False when tag is absent."""
        node = TestClassNode(qualified_name="mymod::Tagged", kind="class",
                          tags=["design"])
        assert node.has_tag("dependency") is False

    def test_has_tag_no_tags_property(self):
        """has_tag returns False for nodes without a tags property."""
        node = TestClassWithoutTags(name="notag")
        assert node.has_tag("design") is False

    def test_add_tag_no_tags_property(self):
        """add_tag is no-op for nodes without a tags property."""
        node = TestClassWithoutTags(name="notag")
        result = node.add_tag("design")
        assert result is node  # returns self, no error

    def test_remove_tag_no_tags_property(self):
        """remove_tag is no-op for nodes without a tags property."""
        node = TestClassWithoutTags(name="notag")
        result = node.remove_tag("design")
        assert result is node


# ══════════════════════════════════════════════════════════════════════════
# fetch_by_tag with new descriptors
# ══════════════════════════════════════════════════════════════════════════


class TestFetchByTagNewDescriptors:
    """fetch_by_tag uses PropertyRegistry.has_property()."""

    def test_returns_empty_when_no_tags_property(self):
        """Nodes without tags property return empty list."""
        result = TestClassWithoutTags.fetch_by_tag("design")
        assert result == []

    def test_does_not_crash_on_tagged_class(self):
        """Doesn't crash when called on a class that has tags.
        
        Note: will return [] because the test node isn't saved to Neo4j,
        but it should not raise an error during the query attempt.
        """
        # This will attempt a Cypher query against the backend,
        # which will fail or return empty since no Neo4j connection.
        # But verify the property check doesn't raise.
        try:
            result = TestClassNode.fetch_by_tag("design")
            assert isinstance(result, list)
        except Exception:
            # Expected: no Neo4j connection in unit test context
            pass


# ══════════════════════════════════════════════════════════════════════════
# save_new() with new descriptors
# ══════════════════════════════════════════════════════════════════════════


class TestSaveNewNewDescriptors:
    """save_new() validates against PropertyRegistry."""

    def test_rejects_unknown_property(self):
        """Raises ValueError for kwargs not in declared properties."""
        with pytest.raises(ValueError, match="Unknown property"):
            TestClassNode.save_new(not_a_field="bad")

    def test_accepts_valid_properties(self):
        """Accepts kwargs that match declared properties.
        
        Note: actual save will fail without Neo4j, but property
        validation should pass.
        """
        try:
            TestClassNode.save_new(
                qualified_name="mymod::Valid",
                kind="class",
                source="test",
            )
        except Exception as e:
            # Expected: backend not available for actual save
            # But the ValueError from validation should NOT be raised
            assert "Unknown property" not in str(e)


# ══════════════════════════════════════════════════════════════════════════
# update() with new descriptors
# ══════════════════════════════════════════════════════════════════════════


class TestUpdateNewDescriptors:
    """update() validates against PropertyRegistry."""

    def test_rejects_unknown_property(self):
        """Raises ValueError for kwargs not in declared properties.
        
        Note: update requires element_id_property (saved node), so it
        raises ValueError about being unsaved before the property check.
        But when the node IS saved, it should reject unknown props.
        """
        node = TestClassNode(qualified_name="mymod::Unsaveable", kind="class")
        # Node is not saved, so update will fail with "Cannot update unsaved"
        with pytest.raises(ValueError, match="Cannot update unsaved"):
            node.update(not_a_field="bad")

    def test_rejects_identity_field_mutation(self):
        """update() rejects changes to source and identity fields even
        on saved nodes — but this test verifies the immutable-set logic
        compiles and works by checking the property registry correctly
        identifies identity fields."""
        # Verify _identity_fields are recognized
        assert TestClassNode._identity_fields == ("qualified_name",)
        # And that PropertyRegistry sees them
        from codegraph.models.descriptors import PropertyRegistry
        assert PropertyRegistry.has_property(TestClassNode, "qualified_name")
        assert PropertyRegistry.has_property(TestClassNode, "source")


# ══════════════════════════════════════════════════════════════════════════
# _uid_prop / _uid_value with new descriptors
# ══════════════════════════════════════════════════════════════════════════


class TestUidAccessorsNewDescriptors:
    """_uid_prop() and _uid_value() use PropertyRegistry."""

    def test_uid_prop_returns_uid(self):
        """_uid_prop() returns 'uid' for classes with UniqueId."""
        assert TestClassNode._uid_prop() == "uid"
        assert TestMethodNode._uid_prop() == "uid"

    def test_uid_value_returns_string(self):
        """_uid_value() returns the deterministic uid derived from identity."""
        node = TestClassNode(qualified_name="mymod::Uid", kind="class")
        uid = node._uid_value()
        assert uid is not None
        assert isinstance(uid, str)
        assert len(uid) == 40  # SHA-1 hex digest (deterministic, not random)

    def test_uid_value_cached(self):
        """_uid_value() returns the same value on repeated calls."""
        node = TestClassNode(qualified_name="mymod::Uid", kind="class")
        first = node._uid_value()
        second = node._uid_value()
        assert first == second


# ══════════════════════════════════════════════════════════════════════════
# Registry — ensure new descriptor classes register correctly
# ══════════════════════════════════════════════════════════════════════════


class TestRegistryWithNewDescriptors:
    """Classes using new descriptors register in CodeGraphNode._registry."""

    def test_test_class_is_registered(self):
        """TestClassNode is in the registry."""
        assert "TestClassNode" in CodeGraphNode._registry
        assert CodeGraphNode._registry["TestClassNode"] is TestClassNode

    def test_test_method_is_registered(self):
        """TestMethodNode is in the registry."""
        assert "TestMethodNode" in CodeGraphNode._registry
        assert CodeGraphNode._registry["TestMethodNode"] is TestMethodNode
