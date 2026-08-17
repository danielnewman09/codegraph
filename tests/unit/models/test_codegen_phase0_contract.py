"""Unit tests for the Phase 0 codegen model contract.

Pure Python — no backend.  Pins the model-surface changes codegen's
context builder will rely on:

- ``MethodNode`` / ``FunctionNode`` declare the ``HAS_PARAMETER``
  relationship (``has_parameters``) to ``ParameterNode``.
- ``EnumValueNode`` carries the Doxygen ``<initializer>`` value.
- Neither change disturbs deterministic uid computation.
"""

import pytest

from codegraph.models.member import (
    AttributeNode,
    EnumValueNode,
    FunctionNode,
    MethodNode,
)
from codegraph.models.parameter import ParameterNode


class TestHasParametersDescriptor:
    """MethodNode / FunctionNode → ParameterNode via HAS_PARAMETER."""

    @pytest.mark.parametrize("node_cls", [MethodNode, FunctionNode])
    def test_serialize_relationships_declares_has_parameters(self, node_cls):
        rels = node_cls.serialize_relationships()
        has_parameters = [
            r for r in rels if r["relation_type"] == "HAS_PARAMETER"
        ]
        assert len(has_parameters) == 1
        descriptor = has_parameters[0]
        assert descriptor["attr"] == "has_parameters"
        assert descriptor["direction"] == "OUTGOING"
        assert descriptor["target"].endswith("ParameterNode")

    @pytest.mark.parametrize("node_cls", [MethodNode, FunctionNode])
    def test_find_relationship_manager_resolves_parameter_target(self, node_cls):
        member = node_cls(name="f", qualified_name="ns::f", source="test")
        param = ParameterNode(position=0, source="test")
        manager = member.find_relationship_manager(
            member, "HAS_PARAMETER", param
        )
        assert manager.name == "has_parameters"
        assert manager.relation_type == "HAS_PARAMETER"

    def test_other_members_do_not_declare_has_parameters(self):
        # AttributeNode models composition, not parameters.
        rel_types = {
            r["relation_type"]
            for r in AttributeNode.serialize_relationships()
        }
        assert "HAS_PARAMETER" not in rel_types


class TestEnumValueInitializer:
    """EnumValueNode.initializer survives serialize/deserialize."""

    def test_initializer_is_declared_property(self):
        node = EnumValueNode(
            name="Red",
            qualified_name="palette::Color::Red",
            initializer="1 << 3",
            source="test",
        )
        assert node.initializer == "1 << 3"

    def test_initializer_in_full_serialization(self):
        from codegraph.identity import IdentityScope, identity_scope

        scope = IdentityScope.repository("codegraph-suite", "codegraph")
        with identity_scope(scope):
            node = EnumValueNode(
                name="Red",
                qualified_name="palette::Color::Red",
                initializer="1 << 3",
                source="test",
            )
            serialized = node.serialize(fields="all")
        assert serialized["initializer"] == "1 << 3"

    def test_initializer_roundtrip_via_deserialize(self):
        data = {
            "type": "EnumValueNode",
            "name": "Cancel",
            "qualified_name": "dlg::Result::Cancel",
            "source": "test",
            "initializer": "-1",
        }
        node = EnumValueNode.deserialize(data)
        assert isinstance(node, EnumValueNode)
        assert node.initializer == "-1"

    def test_initializer_defaults_to_empty(self):
        node = EnumValueNode(name="Implicit", source="test")
        assert node.initializer == ""

    def test_initializer_does_not_change_identity(self):
        """initializer is not an identity field — the canonical key is
        deterministic from (scope, qualified_name)."""
        from codegraph.identity import IdentityScope, resolve_identity_for

        scope = IdentityScope.repository("codegraph-suite", "codegraph")
        a = EnumValueNode(
            name="Red", qualified_name="palette::Color::Red", source="test"
        )
        b = EnumValueNode(
            name="Red",
            qualified_name="palette::Color::Red",
            initializer="1 << 3",
            source="test",
        )
        assert (
            resolve_identity_for(a, scope).key()
            == resolve_identity_for(b, scope).key()
        )

    def test_name_changes_identity(self):
        """Different names still produce different canonical keys."""
        from codegraph.identity import IdentityScope, resolve_identity_for

        scope = IdentityScope.repository("codegraph-suite", "codegraph")
        a = EnumValueNode(name="Red", qualified_name="palette::Color::Red",
                          source="test")
        b = EnumValueNode(name="Blue", qualified_name="palette::Color::Blue",
                          source="test")
        assert (
            resolve_identity_for(a, scope).key()
            != resolve_identity_for(b, scope).key()
        )


class TestParameterNodeSerialization:
    """ParameterNode's C++ ``type`` property must survive serialization.

    The node-kind discriminator normally occupies the ``"type"`` key in
    serialized dicts — which clobbered ParameterNode's C++ type string
    (``"double"`` became ``"ParameterNode"``).  ParameterNode now emits
    the discriminator under ``"node_type"`` so the C++ type round-trips.
    """

    @staticmethod
    def _keyed(param: ParameterNode) -> ParameterNode:
        """Compute the parameter's canonical key with an explicit parent
        context (a synthetic parent method key) — canonical identity is
        mandatory, and parent-relative children need their parent."""
        from codegraph.identity import IdentityScope, resolve_identity_for

        scope = IdentityScope.repository("codegraph-suite", "codegraph")
        parent_key = (
            "cg:v1:repository:codegraph-suite%2Fcodegraph:method:"
            "qualified_name=app%3A%3Aowner:canonical_signature=lang%3Acpp%7C%28%29"
        )
        param.canonical_key = resolve_identity_for(
            param, scope, parents={"parent_callable_key": parent_key}
        ).key()
        return param

    def test_serialize_uses_node_type_discriminator(self):
        param = self._keyed(ParameterNode(
            name="x", type="const std::string &", position=0, source="test"
        ))
        serialized = param.serialize(fields="all")
        assert serialized["node_type"] == "ParameterNode"
        assert serialized["type"] == "const std::string &"

    def test_serialize_llm_fields_preserves_type(self):
        param = self._keyed(ParameterNode(name="x", type="double", position=0,
                                          source="test"))
        serialized = param.serialize(fields="llm")
        assert serialized["node_type"] == "ParameterNode"
        assert serialized["type"] == "double"

    def test_roundtrip_preserves_cpp_type(self):
        param = self._keyed(ParameterNode(
            name="x",
            type="std::vector<SchemaMismatch>",
            position=2,
            default_value="{}",
            source="test",
        ))
        restored = ParameterNode.deserialize(param.serialize(fields="all"))
        assert isinstance(restored, ParameterNode)
        assert restored.name == "x"
        assert restored.type == "std::vector<SchemaMismatch>"
        assert restored.position == 2
        assert restored.default_value == "{}"

    def test_legacy_clobbered_dict_still_deserializes(self):
        """Old serialized dicts (``"type": "ParameterNode"``, C++ type
        already lost) must keep deserializing as ParameterNode."""
        legacy = {
            "type": "ParameterNode",
            "name": "y",
            "position": 1,
            "source": "test",
        }
        restored = ParameterNode.deserialize(legacy)
        assert isinstance(restored, ParameterNode)
        assert restored.name == "y"
        assert restored.position == 1

    def test_other_node_types_keep_type_discriminator(self):
        """Regression: non-colliding node types still use the ``type`` key."""
        from codegraph.identity import IdentityScope, identity_scope

        scope = IdentityScope.repository("codegraph-suite", "codegraph")
        with identity_scope(scope):
            method = MethodNode(
                name="f", qualified_name="ns::f", source="test"
            )
            serialized = method.serialize(fields="all")
        assert serialized["type"] == "MethodNode"
        assert "node_type" not in serialized
        restored = MethodNode.deserialize(serialized)
        assert isinstance(restored, MethodNode)
