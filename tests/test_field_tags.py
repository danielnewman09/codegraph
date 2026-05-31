"""Tests for LlmSerializable — serialize/deserialize contract."""
import pytest
from abc import ABCMeta

from neomodel import StringProperty, StructuredNode
from neomodel.sync_.node import NodeMeta

from codegraph.models.tags import LlmSerializable


class TestLlmSerializable:
    # —— Abstract method enforcement (pure ABC path) ——

    def test_cannot_instantiate_without_serialize(self):
        """Subclasses that don't implement serialize() can't be instantiated."""

        class BadNode(LlmSerializable):
            pass

        with pytest.raises(TypeError, match="serialize"):
            BadNode()

    def test_cannot_instantiate_without_deserialize(self):
        """Subclasses that don't implement deserialize() can't be instantiated."""

        class BadNode(LlmSerializable):
            def serialize(self) -> dict:
                return {}

        with pytest.raises(TypeError, match="deserialize"):
            BadNode()

    def test_llm_serializable_itself_cannot_be_instantiated(self):
        """LlmSerializable is abstract and cannot be instantiated directly."""
        with pytest.raises(TypeError, match="abstract"):
            LlmSerializable()

    def test_valid_subclass_can_be_instantiated(self):
        """A subclass that implements both methods can be instantiated and used."""

        class GoodNode(LlmSerializable):
            _llm_fields = {"name"}

            def serialize(self) -> dict:
                return {"name": "test"}

            @classmethod
            def deserialize(cls, data: dict):
                return cls()

        node = GoodNode()
        assert node.serialize() == {"name": "test"}
        assert isinstance(GoodNode.deserialize({}), GoodNode)

    def test_default_llm_fields_is_empty_set(self):
        """_llm_fields defaults to an empty set."""
        assert LlmSerializable._llm_fields == set()
        assert isinstance(LlmSerializable._llm_fields, set)

    # —— Metaclass lineage ——

    def test_metaclass_is_node_meta_subclass(self):
        """The combined metaclass is a subclass of NodeMeta so neomodel works."""
        assert issubclass(type(LlmSerializable), NodeMeta)

    def test_metaclass_is_abc_meta_subclass(self):
        """The combined metaclass is a subclass of ABCMeta for @abstractmethod."""
        assert issubclass(type(LlmSerializable), ABCMeta)

    # —— Neomodel integration ——

    def test_abstract_enforcement_with_structured_node(self):
        """@abstractmethod is enforced even when inheriting from StructuredNode."""

        class BadNeomodelNode(StructuredNode, LlmSerializable):
            name = StringProperty()
            # Missing serialize() and deserialize()

        with pytest.raises(TypeError, match="abstract"):
            BadNeomodelNode()

    def test_valid_neomodel_node_works(self):
        """A StructuredNode + LlmSerializable subclass works when both methods
        are implemented."""

        class GoodNeomodelNode(StructuredNode, LlmSerializable):
            name = StringProperty()
            _llm_fields = {"name"}

            def serialize(self) -> dict:
                return {"name": self.name}

            @classmethod
            def deserialize(cls, data: dict):
                return cls(name=data.get("name", ""))

        node = GoodNeomodelNode(name="hello")
        assert node.serialize() == {"name": "hello"}
        deserialized = GoodNeomodelNode.deserialize({"name": "world"})
        assert deserialized.name == "world"

    def test_reverse_inheritance_order_also_works(self):
        """Inheriting (LlmSerializable, StructuredNode) also enforces
        abstract methods."""

        class ReverseBadNode(LlmSerializable, StructuredNode):
            name = StringProperty()

        with pytest.raises(TypeError, match="abstract"):
            ReverseBadNode()
