"""Tests for CodeGraphNode.update() — kwargs-based property update with Neo4j persistence."""

import pytest
from codegraph.models.compound import ClassNode


class TestUpdateValidation:
    """Tests for validation behaviour when calling update()."""

    def test_update_unsaved_node_raises(self):
        """update() on an unsaved node raises ValueError."""
        node = ClassNode(qualified_name="test::Unsaved", name="Unsaved", kind="class")
        with pytest.raises(ValueError, match="Cannot update unsaved"):
            node.update(name="new_name")

    def test_update_unknown_property_raises(self):
        """update() with an undeclared property key raises ValueError."""
        node = ClassNode(qualified_name="test::UnknownProp", name="UnknownProp", kind="class")
        node.save()
        with pytest.raises(ValueError, match="Unknown propert"):
            node.update(nonexistent_field="oops")

    def test_update_unknown_property_lists_valid(self):
        """The error message lists valid properties when unknown keys are given."""
        node = ClassNode(qualified_name="test::ErrMsg", name="ErrMsg", kind="class")
        node.save()
        with pytest.raises(ValueError, match="Valid properties:") as exc_info:
            node.update(bogus1="x", bogus2="y")
        msg = str(exc_info.value)
        assert "bogus1" in msg
        assert "bogus2" in msg


class TestUpdatePersistence:
    """Tests for update() persisting changes to Neo4j."""

    def test_update_single_field(self):
        """update() with one field sets the attribute and persists it."""
        node = ClassNode(
            qualified_name="test::SingleField",
            name="SingleField",
            kind="class",
            brief_description="original",
        )
        node.save()

        result = node.update(brief_description="updated")

        # Attribute set on the instance
        assert node.brief_description == "updated"

        # Refresh from DB to confirm persistence
        refreshed = ClassNode.nodes.get(qualified_name="test::SingleField")
        assert refreshed.brief_description == "updated"

        # Returns self for chaining
        assert result is node

    def test_update_multiple_fields(self):
        """update() with multiple fields persists all changes."""
        node = ClassNode(
            qualified_name="test::MultiField",
            name="MultiField",
            kind="class",
            brief_description="orig",
            visibility="private",
        )
        node.save()

        node.update(brief_description="new desc", visibility="public")

        refreshed = ClassNode.nodes.get(qualified_name="test::MultiField")
        assert refreshed.brief_description == "new desc"
        assert refreshed.visibility == "public"

    def test_update_returns_self_for_chaining(self):
        """update() returns the node instance, enabling method chaining."""
        node = ClassNode(
            qualified_name="test::Chain",
            name="Chain",
            kind="class",
        )
        node.save()

        result = node.update(name="Chained")
        assert result is node
        assert isinstance(result, ClassNode)

    def test_update_preserves_unchanged_fields(self):
        """update() only mutates the specified fields."""
        node = ClassNode(
            qualified_name="test::Preserve",
            name="Preserve",
            kind="class",
            brief_description="keep me",
            visibility="private",
        )
        node.save()

        node.update(visibility="public")

        refreshed = ClassNode.nodes.get(qualified_name="test::Preserve")
        assert refreshed.brief_description == "keep me"
        assert refreshed.visibility == "public"
        assert refreshed.name == "Preserve"

    def test_update_base_class_fields(self):
        """update() can modify fields defined on CodeGraphNode (name, source)."""
        node = ClassNode(
            qualified_name="test::BaseFields",
            name="BaseFields",
            kind="class",
            source="original",
        )
        node.save()

        node.update(name="NewName", source="updated_source")

        refreshed = ClassNode.nodes.get(qualified_name="test::BaseFields")
        assert refreshed.name == "NewName"
        assert refreshed.source == "updated_source"