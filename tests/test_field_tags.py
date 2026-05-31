"""Tests for LlmSerializable — serialize/deserialize contract."""
import pytest
from abc import abstractmethod
from codegraph.models.tags import LlmSerializable


class TestLlmSerializable:
    def test_serialize_must_be_implemented(self):
        """Subclasses that don't implement serialize() can't be instantiated."""

        class BadNode(LlmSerializable):
            pass

        with pytest.raises(TypeError):
            BadNode()  # Missing abstract method serialize

    def test_deserialize_must_be_implemented(self):
        """Subclasses that don't implement deserialize() can't be instantiated."""

        class BadNode(LlmSerializable):
            def serialize(self) -> dict:
                return {}

        with pytest.raises(TypeError):
            BadNode()  # Missing abstract method deserialize

    def test_metaclass_is_node_meta_subclass(self):
        """The combined metaclass is a subclass of NodeMeta so neomodel works."""
        from neomodel.sync_.node import NodeMeta
        assert issubclass(type(LlmSerializable), NodeMeta)

    def test_metaclass_is_abc_meta_subclass(self):
        """The combined metaclass is a subclass of ABCMeta for @abstractmethod."""
        from abc import ABCMeta
        assert issubclass(type(LlmSerializable), ABCMeta)
