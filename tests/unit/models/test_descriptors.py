"""Unit tests for codegraph.models.descriptors — Property, UniqueId,
Relationship, PropertyRegistry, find_relationship_descriptor, uid_prop_name.

These tests are pure Python — no Neo4j backend needed.
"""

import pytest

from codegraph.models.descriptors import (
    Property,
    UniqueId,
    DateTimeProperty,
    Relationship,
    PropertyRegistry,
    find_relationship_descriptor,
    uid_prop_name,
)


# ══════════════════════════════════════════════════════════════════════════
# Fixtures: test classes using the new descriptors
# ══════════════════════════════════════════════════════════════════════════


class _BaseNode:
    """Base class using new descriptors (no StructuredNode)."""

    uid = UniqueId()
    source = Property(str, default="")


class _ConcreteNode(_BaseNode):
    name = Property(str, default="unnamed")
    count = Property(int, default=0)
    active = Property(bool, default=False)
    tags = Property(list, default=[])
    methods = Relationship("COMPOSES", direction="OUTGOING",
                           target_class="MethodNode")
    parent = Relationship("COMPOSES", direction="INCOMING",
                          target_class="NamespaceNode")


class _OverrideNode(_BaseNode):
    """Overrides a base property with a different default."""
    source = Property(str, default="override_default")


class _ReadonlyNode:
    """Node with no UniqueId — for testing uid_prop_name None case."""
    name = Property(str, default="")


# ══════════════════════════════════════════════════════════════════════════
# Property descriptor
# ══════════════════════════════════════════════════════════════════════════


class TestProperty:
    """Tests for the Property data descriptor."""

    def test_default_value(self):
        """Returns the declared default when not set."""
        node = _ConcreteNode()
        assert node.name == "unnamed"
        assert node.count == 0
        assert node.active is False

    def test_set_and_get(self):
        """Setting a value stores it; getting returns it."""
        node = _ConcreteNode()
        node.name = "hello"
        node.count = 42
        assert node.name == "hello"
        assert node.count == 42

    def test_delete(self):
        """Deleting a property falls back to default."""
        node = _ConcreteNode()
        node.name = "temp"
        del node.name
        assert node.name == "unnamed"

    def test_class_access_returns_descriptor(self):
        """Accessing on the class returns the descriptor itself."""
        assert isinstance(_ConcreteNode.name, Property)
        assert _ConcreteNode.name.name == "name"
        assert _ConcreteNode.name.python_type is str

    def test_independent_instances(self):
        """Values are per-instance, not shared."""
        a = _ConcreteNode()
        b = _ConcreteNode()
        a.name = "alpha"
        b.name = "beta"
        assert a.name == "alpha"
        assert b.name == "beta"

    def test_required_flag(self):
        """required=True is stored on the descriptor."""
        p = Property(str, required=True)
        assert p.required is True
        assert not p.required == False

    def test_index_flag(self):
        """index=True is stored on the descriptor."""
        p = Property(str, index=True)
        assert p.index is True

    def test_help_text(self):
        """help_text is stored on the descriptor."""
        p = Property(str, help_text="A description")
        assert p.help_text == "A description"

    def test_repr(self):
        """__repr__ includes name, type, required, index."""
        p = Property(int, required=True, index=True)
        p.__set_name__(_ConcreteNode, "myprop")
        r = repr(p)
        assert "myprop" in r
        assert "int" in r
        assert "required=True" in r
        assert "index=True" in r


class TestDateTimeProperty:
    """Tests for the DateTimeProperty descriptor."""

    def test_type_is_datetime(self):
        """python_type is datetime."""
        dt = DateTimeProperty()
        from datetime import datetime
        assert dt.python_type is datetime

    def test_default_none(self):
        """Default is None."""
        class WithDt:
            created = DateTimeProperty()

        node = WithDt()
        assert node.created is None


# ══════════════════════════════════════════════════════════════════════════
# UniqueId descriptor
# ══════════════════════════════════════════════════════════════════════════


class TestUniqueId:
    """Tests for the UniqueId descriptor."""

    def test_lazy_generation(self):
        """First access generates a UUID string."""
        node = _BaseNode()
        uid = node.uid
        assert isinstance(uid, str)
        assert len(uid) == 36  # standard UUID format
        assert uid.count("-") == 4

    def test_cached_after_first_access(self):
        """Second access returns the same value."""
        node = _BaseNode()
        first = node.uid
        second = node.uid
        assert first == second

    def test_unique_per_instance(self):
        """Each instance gets a different UUID."""
        a = _BaseNode()
        b = _BaseNode()
        assert a.uid != b.uid

    def test_class_access_returns_descriptor(self):
        """Accessing on the class returns the UniqueId descriptor."""
        assert isinstance(_BaseNode.uid, UniqueId)


# ══════════════════════════════════════════════════════════════════════════
# Relationship descriptor
# ══════════════════════════════════════════════════════════════════════════


class TestRelationship:
    """Tests for the Relationship descriptor."""

    def test_metadata(self):
        """Descriptor stores name, relation_type, direction, target_class."""
        rel = _ConcreteNode.methods
        assert isinstance(rel, Relationship)
        assert rel.name == "methods"
        assert rel.relation_type == "COMPOSES"
        assert rel.direction == "OUTGOING"
        assert rel.target_class == "MethodNode"

    def test_incoming_direction(self):
        """INCOMING direction is stored correctly."""
        rel = _ConcreteNode.parent
        assert rel.direction == "INCOMING"
        assert rel.relation_type == "COMPOSES"
        assert rel.target_class == "NamespaceNode"

    def test_instance_access_returns_manager(self):
        """Accessing a Relationship on an instance returns a RelationshipManager.

        The manager delegates traversal/mutation to the active backend,
        keeping existing ``.all()`` / ``.connect()`` call sites working.
        """
        node = _ConcreteNode()
        manager = node.methods
        from codegraph.models.descriptors import RelationshipManager
        assert isinstance(manager, RelationshipManager)
        assert manager._rel.relation_type == "COMPOSES"

    def test_instance_access_raises(self):
        """Backward-compat alias for the pre-migration test id.

        Pre-migration, instance access to a ``Relationship`` raised
        ``AttributeError``.  Since the ``RelationshipManager`` shim,
        it returns a backend-delegating manager instead.  Kept under
        the old name so CI/test scripts referencing
        ``test_instance_access_raises`` still resolve.
        """
        self.test_instance_access_returns_manager()

    def test_invalid_direction(self):
        """Invalid direction raises ValueError."""
        with pytest.raises(ValueError, match="direction must be"):
            Relationship("X", direction="SIDEWAYS", target_class="Foo")

    def test_target_class_as_type(self):
        """target_class can be a Python type, not just a string."""

        class OtherNode:
            pass

        class NodeWithTypeRef:
            methods = Relationship("COMPOSES", direction="OUTGOING",
                                   target_class=OtherNode)

        assert NodeWithTypeRef.methods.target_class is OtherNode

    def test_repr(self):
        """__repr__ is human-readable."""
        r = repr(_ConcreteNode.methods)
        assert "methods" in r
        assert "COMPOSES" in r
        assert "OUTGOING" in r
        assert "MethodNode" in r


# ══════════════════════════════════════════════════════════════════════════
# PropertyRegistry
# ══════════════════════════════════════════════════════════════════════════


class TestPropertyRegistry:
    """Tests for PropertyRegistry introspection."""

    def test_properties_of(self):
        """Returns all Property descriptors (including inherited)."""
        props = PropertyRegistry.properties_of(_ConcreteNode)
        assert "uid" in props
        assert "source" in props
        assert "name" in props
        assert "count" in props
        assert "tags" in props
        # Relationships are NOT in properties
        assert "methods" not in props
        assert "parent" not in props

    def test_relationships_of(self):
        """Returns all Relationship descriptors."""
        _, rels = PropertyRegistry.of(_ConcreteNode)
        assert "methods" in rels
        assert "parent" in rels
        # Properties are NOT in relationships
        assert "name" not in rels

    def test_of_returns_both(self):
        """of() returns (props, rels) tuple."""
        props, rels = PropertyRegistry.of(_ConcreteNode)
        assert isinstance(props, dict)
        assert isinstance(rels, dict)
        assert len(props) >= 5  # uid, source, name, count, active, tags
        assert len(rels) >= 2  # methods, parent

    def test_values_of(self):
        """Returns current property values from a live instance."""
        node = _ConcreteNode()
        node.name = "testname"
        node.source = "testsrc"
        values = PropertyRegistry.values_of(node)
        assert values["name"] == "testname"
        assert values["source"] == "testsrc"
        # Relationships are not in values
        assert "methods" not in values

    def test_has_property(self):
        """has_property checks base and derived classes."""
        assert PropertyRegistry.has_property(_ConcreteNode, "name") is True
        assert PropertyRegistry.has_property(_ConcreteNode, "source") is True  # inherited
        assert PropertyRegistry.has_property(_ConcreteNode, "nonexistent") is False

    def test_unique_id_name(self):
        """Returns the name of the UniqueId property."""
        assert PropertyRegistry.unique_id_name(_ConcreteNode) == "uid"

    def test_unique_id_name_none(self):
        """Returns None when no UniqueId exists."""
        assert PropertyRegistry.unique_id_name(_ReadonlyNode) is None

    def test_override_in_subclass(self):
        """Subclass override replaces base class property."""
        props = PropertyRegistry.properties_of(_OverrideNode)
        assert props["source"].default == "override_default"

    def test_neomodel_properties_not_detected(self):
        """PropertyRegistry only collects our Property descriptors.

        neomodel property types (StringProperty etc.) are not collected —
        the model layer no longer supports neomodel classes.
        """
        from neomodel import StructuredNode, StringProperty, UniqueIdProperty

        class NeoNode(StructuredNode):
            uid = UniqueIdProperty()
            name = StringProperty(default="")

        props, _ = PropertyRegistry.of(NeoNode)
        assert "uid" not in props
        assert "name" not in props

    def test_neomodel_relationships_not_detected(self):
        """PropertyRegistry does not collect neomodel relationship types."""
        from neomodel import StructuredNode, RelationshipTo

        class NeoRelNode(StructuredNode):
            owns = RelationshipTo("SomeTarget", "OWNS")

        _, rels = PropertyRegistry.of(NeoRelNode)
        assert rels == {}
        # The key test is that it doesn't crash on neomodel classes.
        assert isinstance(rels, dict)


# ══════════════════════════════════════════════════════════════════════════
# find_relationship_descriptor
# ══════════════════════════════════════════════════════════════════════════


class TestFindRelationshipDescriptor:
    """Tests for find_relationship_descriptor()."""

    def test_finds_by_string_target(self):
        """Matches when target_class is a string."""
        result = find_relationship_descriptor(
            _ConcreteNode, "COMPOSES", "MethodNode"
        )
        assert result is not None
        assert result.name == "methods"
        assert result.relation_type == "COMPOSES"

    def test_finds_incoming(self):
        """Matches INCOMING relationships."""
        result = find_relationship_descriptor(
            _ConcreteNode, "COMPOSES", "NamespaceNode"
        )
        assert result is not None
        assert result.name == "parent"
        assert result.direction == "INCOMING"

    def test_returns_none_for_unknown_relation(self):
        """Returns None when relation_type doesn't match."""
        result = find_relationship_descriptor(
            _ConcreteNode, "NONEXISTENT", "MethodNode"
        )
        assert result is None

    def test_returns_none_for_wrong_target(self):
        """Returns None when target doesn't match."""
        result = find_relationship_descriptor(
            _ConcreteNode, "COMPOSES", "WrongTarget"
        )
        assert result is None

    def test_neomodel_relationships_not_found(self):
        """find_relationship_descriptor ignores neomodel descriptors.

        The model layer is pure-Python now — neomodel relationship
        descriptors are not resolved.
        """
        from neomodel import StructuredNode, RelationshipTo

        class NeoFindRelNode(StructuredNode):
            owns = RelationshipTo("SomeTarget", "OWNS")

        result = find_relationship_descriptor(NeoFindRelNode, "OWNS", "SomeTarget")
        assert result is None


# ══════════════════════════════════════════════════════════════════════════
# uid_prop_name compat
# ══════════════════════════════════════════════════════════════════════════


class TestUidPropName:
    """Tests for uid_prop_name() compat function."""

    def test_returns_uid_for_new_descriptors(self):
        """Returns 'uid' for classes using new UniqueId descriptor."""
        assert uid_prop_name(_ConcreteNode) == "uid"

    def test_returns_none_when_no_uid(self):
        """Returns None for classes without UniqueId."""
        assert uid_prop_name(_ReadonlyNode) is None

    def test_returns_none_for_neomodel_classes(self):
        """Returns None for neomodel classes (no longer supported)."""
        from neomodel import StructuredNode, UniqueIdProperty

        class NeoUidNode(StructuredNode):
            uid = UniqueIdProperty()

        assert uid_prop_name(NeoUidNode) is None
