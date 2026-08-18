"""Unit tests for ImplementationNode model."""

import json
from pathlib import Path

from codegraph.models.implementation import ImplementationNode
from codegraph.models.tags import CodeGraphNode


def _key_parented(node):
    """Compute a canonical key for a parent-relative node (WP A)."""
    from codegraph.identity import IdentityScope, resolve_identity_for

    scope = IdentityScope.repository("codegraph-suite", "codegraph")
    node.canonical_key = resolve_identity_for(
        node, scope, parents={"parent_callable_key": "parent"}
    ).key()
    return node

class TestImplementationNodeModel:
    """Test ImplementationNode creation and field defaults."""

    # codegraph:test-desc implementation.test_implementation_node.TestImplementationNodeModel.test_kind_defaults_to_implementation
    # Verifies that an ImplementationNode, when created without explicit arguments,
    # defaults its 'kind' attribute to 'implementation' to ensure the node correctly
    # represents its intended role in the code graph.
    def test_kind_defaults_to_implementation(self):
        # codegraph:test-desc implementation.test_implementation_node.TestImplementationNodeModel.test_kind_defaults_to_implementation::step_0
        # Instantiates the ImplementationNode, providing the fixture object that will be
        # inspected for its default kind attribute.
        node = ImplementationNode(source="test",)
        # codegraph:test-desc implementation.test_implementation_node.TestImplementationNodeModel.test_kind_defaults_to_implementation::post_0
        # Asserts that the node's 'kind' attribute equals 'implementation', confirming
        # the default value is correctly set as expected.
        assert node.kind == "implementation"

    def test_canonical_key_deterministic(self):
        """canonical_key is deterministic given a parent (WP A)."""
        # codegraph:test-desc implementation.test_implementation_node.TestImplementationNodeModel.test_canonical_key_deterministic::step_0
        # An ImplementationNode's key is derived from (parent_callable_key, kind)
        # under a fixed scope — no random component.
        from codegraph.identity import IdentityScope, resolve_identity_for

        scope = IdentityScope.repository("codegraph-suite", "codegraph")
        parents = {"parent_callable_key": "parent"}

        def key_for():
            return resolve_identity_for(
                ImplementationNode(
                    qualified_name="Widget::draw",
                    kind="implementation",
                    source="test",
                ),
                scope, parents=parents,
            ).key()

        k1 = key_for()
        k2 = key_for()
        # codegraph:test-desc implementation.test_implementation_node.TestImplementationNodeModel.test_canonical_key_deterministic::post_0
        # The key is deterministic and versioned (cg:v1).
        assert k1 == k2
        assert k1.startswith("cg:v1:")
        assert "implementation" in k1

    def test_qualified_name_explicit_set(self):
        """qualified_name can be explicitly set to match the parent member."""
        # codegraph:test-desc implementation.test_implementation_node.TestImplementationNodeModel.test_qualified_name_explicit_set::step_0
        # Sets the qualified_name on the node object to an explicit value representing a
        # parent member name, preparing the test to verify that the node accepts and
        # stores this manual assignment.
        node = ImplementationNode(qualified_name="Widget::draw", source="test",)
        # codegraph:test-desc implementation.test_implementation_node.TestImplementationNodeModel.test_qualified_name_explicit_set::post_0
        # Asserts that the node's qualified_name matches the explicitly set value,
        # confirming that the ImplementationNode allows manual overrides of its derived
        # qualified name to align with parent or custom naming requirements.
        assert node.qualified_name == "Widget::draw"

    # codegraph:test-desc implementation.test_implementation_node.TestImplementationNodeModel.test_implementation_default_empty
    # Verifies that a newly created ImplementationNode instance has an empty default
    # state (e.g., no children, empty content), ensuring the constructor initializes the
    # node correctly.
    def test_implementation_default_empty(self):
        # codegraph:test-desc implementation.test_implementation_node.TestImplementationNodeModel.test_implementation_default_empty::step_0
        # Sets up the test by instantiating an ImplementationNode without any arguments,
        # establishing the baseline state for the subsequent assertion.
        node = ImplementationNode(source="test",)
        # codegraph:test-desc implementation.test_implementation_node.TestImplementationNodeModel.test_implementation_default_empty::post_0
        # Asserts that the ImplementationNode's children list is empty, confirming that
        # a default node starts with no sub-nodes, which is essential for ensuring
        # correct initialization behavior.
        assert node.implementation == ""

    # codegraph:test-desc implementation.test_implementation_node.TestImplementationNodeModel.test_impl_embedding_default_empty
    # This test verifies that a newly created ImplementationNode has an empty
    # impl_embedding list by default, ensuring the model initializes correctly and no
    # extraneous embeddings are present.
    def test_impl_embedding_default_empty(self):
        # codegraph:test-desc implementation.test_implementation_node.TestImplementationNodeModel.test_impl_embedding_default_empty::step_0
        # Initializes an ImplementationNode without any additional setup, establishing a
        # clean baseline for verifying default attribute values.
        node = ImplementationNode(source="test",)
        # codegraph:test-desc implementation.test_implementation_node.TestImplementationNodeModel.test_impl_embedding_default_empty::post_0
        # This assertion confirms that the newly created node's impl_embedding is an
        # empty list, validating the default initialization logic of the
        # ImplementationNode model.
        assert node.impl_embedding == []

    # codegraph:test-desc implementation.test_implementation_node.TestImplementationNodeModel.test_implementation_stored
    # Verifies that an ImplementationNode can be stored and retrieved correctly,
    # ensuring the node's attributes and relationships are persisted as expected in the
    # model.
    def test_implementation_stored(self):
        # codegraph:test-desc implementation.test_implementation_node.TestImplementationNodeModel.test_implementation_stored::step_0
        # Sets up the test by performing the necessary actions to store the node,
        # preparing it for subsequent assertions.
        node = ImplementationNode(
            qualified_name="Widget::draw",
            implementation="void draw() { render(); }",
        source="test",)
        # codegraph:test-desc implementation.test_implementation_node.TestImplementationNodeModel.test_implementation_stored::post_0
        # Asserts that the stored node's attribute equals the expected value, confirming
        # that the node was persisted correctly and maintains data integrity.
        assert node.implementation == "void draw() { render(); }"

    # codegraph:test-desc implementation.test_implementation_node.TestImplementationNodeModel.test_impl_embedding_stored
    # Verifies that an ImplementationNode correctly stores and returns its embedding
    # vector, ensuring that the model can persist and retrieve embedding data essential
    # for downstream processing.
    def test_impl_embedding_stored(self):
        # codegraph:test-desc implementation.test_implementation_node.TestImplementationNodeModel.test_impl_embedding_stored::step_0
        # Sets up the test by creating a new ImplementationNode and assigning it the
        # embedding [0.1, 0.2, 0.3] to prepare for the assertion.
        node = ImplementationNode(
            qualified_name="Widget::draw",
            impl_embedding=[0.1, 0.2, 0.3],
        source="test",)
        # codegraph:test-desc implementation.test_implementation_node.TestImplementationNodeModel.test_impl_embedding_stored::post_0
        # Asserts that the embedding stored in the ImplementationNode exactly matches
        # the expected list [0.1, 0.2, 0.3], confirming that the embedding is correctly
        # persisted in the model.
        assert node.impl_embedding == [0.1, 0.2, 0.3]

    # codegraph:test-desc implementation.test_implementation_node.TestImplementationNodeModel.test_llm_fields_include_implementation
    # Verifies that the implementation node includes the required LLM fields, ensuring
    # the model provides all fields needed by the LLM interface.
    def test_llm_fields_include_implementation(self):
        # codegraph:test-desc implementation.test_implementation_node.TestImplementationNodeModel.test_llm_fields_include_implementation::post_0
        # Asserts that the LLM field name is present in the implementation node's
        # fields, which confirms the node exposes the necessary information for LLM
        # integration.
        assert "implementation" in ImplementationNode._llm_fields

    # codegraph:test-desc implementation.test_implementation_node.TestImplementationNodeModel.test_llm_fields_include_qualified_name
    # Verifies that the LLM response fields generated by the ImplementationNodeModel
    # include the 'qualified_name' attribute, ensuring that downstream processing can
    # uniquely identify each node by its fully qualified name.
    def test_llm_fields_include_qualified_name(self):
        # codegraph:test-desc implementation.test_implementation_node.TestImplementationNodeModel.test_llm_fields_include_qualified_name::post_0
        # Verifies that the 'qualified_name' is present in the LLM fields. This ensures
        # that the model's LLM output includes the required identifier, which is
        # critical for traceability and downstream processing.
        assert "qualified_name" in ImplementationNode._llm_fields

    # codegraph:test-desc implementation.test_implementation_node.TestImplementationNodeModel.test_llm_fields_exclude_embedding
    # Verifies that the implementation node model's LLM fields exclude any embedding
    # field, ensuring that embedding data is not mistakenly included in LLM-specific
    # processing.
    def test_llm_fields_exclude_embedding(self):
        # codegraph:test-desc implementation.test_implementation_node.TestImplementationNodeModel.test_llm_fields_exclude_embedding::post_0
        # Verify that the word 'embedding' is not present in the list of field names
        # retrieved from the LLM, ensuring that embedding fields are excluded from
        # LLM-related outputs as required by the model specification.
        assert "impl_embedding" not in ImplementationNode._llm_fields

    # codegraph:test-desc implementation.test_implementation_node.TestImplementationNodeModel.test_serialize_includes_implementation
    # Verifies that the serialization of an ImplementationNode correctly includes all
    # relevant data, ensuring that the output of CompositeEntry.serialize accurately
    # represents the node's state for persistence or transmission.
    def test_serialize_includes_implementation(self):
        # codegraph:test-desc implementation.test_implementation_node.TestImplementationNodeModel.test_serialize_includes_implementation::step_0
        # Calls the serialize() method on the ImplementationNode to produce a serialized
        # representation of the node, setting up the data that will be checked for
        # correctness.
        node = ImplementationNode(
            qualified_name="Widget::draw",
            implementation="void draw() { render(); }",
        source="test",)
        serialized = _key_parented(node).serialize()
        # codegraph:test-desc implementation.test_implementation_node.TestImplementationNodeModel.test_serialize_includes_implementation::post_0
        # Confirms that the key 'implementation' exists in the serialized output,
        # ensuring that the serialization process includes the implementation content
        # alongside other node metadata.
        assert "implementation" in serialized
        # codegraph:test-desc implementation.test_implementation_node.TestImplementationNodeModel.test_serialize_includes_implementation::post_1
        # Confirms that the value of serialized['implementation'] exactly matches the
        # original code snippet 'void draw() { render(); }', verifying that the
        # implementation content is preserved accurately during serialization.
        assert serialized["implementation"] == "void draw() { render(); }"

    # codegraph:test-desc implementation.test_implementation_node.TestImplementationNodeModel.test_serialize_excludes_embedding
    # Verifies that the serialization of an ImplementationNode omits the embedding
    # field, ensuring that exported data does not include internal or large vector
    # representations which are irrelevant for downstream consumers and can reduce
    # payload size.
    def test_serialize_excludes_embedding(self):
        # codegraph:test-desc implementation.test_implementation_node.TestImplementationNodeModel.test_serialize_excludes_embedding::step_0
        # Calls the serialize method on the node fixture to produce a serialized
        # representation of the ImplementationNode, which is then checked for the
        # exclusion of the embedding field.
        node = ImplementationNode(
            qualified_name="Widget::draw",
            impl_embedding=[0.1, 0.2, 0.3],
        source="test",)
        serialized = _key_parented(node).serialize()
        # codegraph:test-desc implementation.test_implementation_node.TestImplementationNodeModel.test_serialize_excludes_embedding::post_0
        # Verifies that the serialized output does not contain the 'impl_embedding' key,
        # confirming that the ImplementationNode.serialize method correctly excludes the
        # embedding data as required.
        assert "impl_embedding" not in serialized

    # codegraph:test-desc implementation.test_implementation_node.TestImplementationNodeModel.test_deserialize_with_implementation
    # This test verifies that the deserialize method of LayerGraph correctly
    # reconstructs a graph from serialized data, ensuring data integrity and consistency
    # in the graph's structure during serialization round-trips.
    def test_deserialize_with_implementation(self):
        # codegraph:test-desc implementation.test_implementation_node.TestImplementationNodeModel.test_deserialize_with_implementation::step_0
        # Sets up the test environment by initializing the node fixture, preparing it
        # for deserialization. This step ensures the test has the necessary data to
        # exercise the `deserialize` entry point.
        data = {
            "type": "ImplementationNode",
            "qualified_name": "Widget::draw",
            "kind": "implementation",
            "implementation": "void draw() { render(); }",
        }
        node = CodeGraphNode.deserialize(data)
        # codegraph:test-desc implementation.test_implementation_node.TestImplementationNodeModel.test_deserialize_with_implementation::post_0
        # Verifies that the result of the deserialization is an instance of
        # `ImplementationNode`. This confirms that the deserialization process correctly
        # reconstructs a node of the expected type, which is essential for type safety
        # and correct behavior.
        assert isinstance(node, ImplementationNode)
        # codegraph:test-desc implementation.test_implementation_node.TestImplementationNodeModel.test_deserialize_with_implementation::post_1
        # Checks that the deserialized `ImplementationNode` has an appropriate equality
        # relationship with the original node, ensuring that the transformation
        # preserves the node's core data. This is critical for data integrity after
        # serialization/deserialization.
        assert node.implementation == "void draw() { render(); }"

    def test_fixture_roundtrip(self):
        """Verify implementation_node_full.json deserializes correctly."""
        # codegraph:test-desc implementation.test_implementation_node.TestImplementationNodeModel.test_fixture_roundtrip::step_0
        # Deserializes the test fixture JSON file using the LayerGraph.deserialize
        # method to produce the node fixture, setting up the object that will be
        # verified against the original data.
        with open(Path(__file__).resolve().parent / "data" / "implementation_node_full.json") as f:
            data = json.load(f)
        node = CodeGraphNode.deserialize(data)
        # codegraph:test-desc implementation.test_implementation_node.TestImplementationNodeModel.test_fixture_roundtrip::post_0
        # Confirms that the deserialized object is an instance of ImplementationNode,
        # validating that the deserialization process correctly identifies the node
        # type.
        assert isinstance(node, ImplementationNode)
        # codegraph:test-desc implementation.test_implementation_node.TestImplementationNodeModel.test_fixture_roundtrip::post_1
        # Asserts that the node's implementation field matches the original fixture
        # data, confirming that the implementation content is correctly preserved during
        # deserialization.
        assert node.implementation == data["implementation"]
        # codegraph:test-desc implementation.test_implementation_node.TestImplementationNodeModel.test_fixture_roundtrip::post_2
        # Verifies that the node's impl_embedding attribute matches the original data
        # from the JSON fixture, ensuring that embedded representation data is preserved
        # during deserialization.
        assert node.impl_embedding == data["impl_embedding"]
        # codegraph:test-desc implementation.test_implementation_node.TestImplementationNodeModel.test_fixture_roundtrip::post_3
        # Checks that the node's qualified_name equals the expected value from the
        # fixture data, ensuring the node's identity attribute is accurately
        # reconstructed.
        assert node.qualified_name == data["qualified_name"]

class TestImplementationNodeRegistry:
    """Test that ImplementationNode is registered in CodeGraphNode._registry."""

    # codegraph:test-desc implementation.test_implementation_node.TestImplementationNodeRegistry.test_implementation_node_in_registry
    # Verifies that an implementation node is correctly registered and present in the
    # registry, ensuring the registry maintains an accurate list of all implementation
    # nodes.
    def test_implementation_node_in_registry(self):
        # codegraph:test-desc implementation.test_implementation_node.TestImplementationNodeRegistry.test_implementation_node_in_registry::post_0
        # Verifies that the implementation node is included in the registry after the
        # test action, confirming that the node was correctly registered and is
        # discoverable.
        assert "ImplementationNode" in CodeGraphNode._registry

    # codegraph:test-desc implementation.test_implementation_node.TestImplementationNodeRegistry.test_implementation_node_registry_class
    # Verifies that the ImplementationNodeRegistry class initializes and behaves as
    # expected, ensuring the registry can correctly manage implementation nodes for
    # program reliability.
    def test_implementation_node_registry_class(self):
        # codegraph:test-desc implementation.test_implementation_node.TestImplementationNodeRegistry.test_implementation_node_registry_class::post_0
        # Verifies that the 'ImplementationNode' key in CodeGraphNode's registry maps
        # exactly to the ImplementationNode class, ensuring the registry correctly
        # stores and retrieves its registered subclass.
        assert CodeGraphNode._registry["ImplementationNode"] is ImplementationNode