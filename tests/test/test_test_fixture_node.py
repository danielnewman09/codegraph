"""Tests for TestFixtureNode — test-local variable tracking."""

import os
import json
import pytest
from unittest.mock import patch, MagicMock

from neomodel import RelationshipTo, RelationshipFrom, StringProperty, ArrayProperty

from codegraph.models.test import TestFixtureNode, TestNode, AssertionNode, TestStepNode
from codegraph.constants import TAGS, NODE_KINDS, TEST_KIND_SET, DEFAULT_PREDICATES
from codegraph.uid import compute_uid
from codegraph.graph import LayerGraph


class TestTestFixtureNodeFields:
    """Foundation: TestFixtureNode has the expected fields and defaults."""

    def test_field_kind_defaults_to_test_fixture(self):
        node = TestFixtureNode(
            name="engine",
            qualified_name="tests::test_ops::engine",
        )
        assert node.kind == "test_fixture"

    def test_field_name_is_required(self):
        node = TestFixtureNode(
            name="engine",
            qualified_name="tests::test_ops::engine",
        )
        assert node.name == "engine"

    def test_field_type_signature_defaults_to_empty(self):
        node = TestFixtureNode(
            name="engine",
            qualified_name="tests::test_ops::engine",
        )
        assert node.type_signature == ""

    def test_field_description_defaults_to_empty(self):
        node = TestFixtureNode(
            name="engine",
            qualified_name="tests::test_ops::engine",
        )
        assert node.description == ""

    def test_field_tags_is_array(self):
        node = TestFixtureNode(
            name="engine",
            qualified_name="tests::test_ops::engine",
        )
        assert node.tags == []

    def test_field_uid_computed_from_qualified_name(self):
        node = TestFixtureNode(
            name="engine",
            qualified_name="tests::test_ops::engine",
        )
        expected = compute_uid("tests::test_ops::engine")
        assert node._compute_uid() == expected

    def test_field_doc_embedding_defaults_to_empty(self):
        node = TestFixtureNode(
            name="engine",
            qualified_name="tests::test_ops::engine",
        )
        assert node.doc_embedding == []

    def test_all_fields_set(self):
        node = TestFixtureNode(
            name="engine",
            qualified_name="tests::test_ops::engine",
            kind="test_fixture",
            type_signature="CalculatorEngine",
            description="Direct instance of CalculatorEngine.",
            tags=["as-built"],
        )
        assert node.name == "engine"
        assert node.qualified_name == "tests::test_ops::engine"
        assert node.kind == "test_fixture"
        assert node.type_signature == "CalculatorEngine"
        assert node.description == "Direct instance of CalculatorEngine."
        assert node.tags == ["as-built"]

    def test_kind_is_in_test_kind_set(self):
        assert "test_fixture" in TEST_KIND_SET
        assert "test_fixture" in {k for k, _ in NODE_KINDS}

    def test_not_in_tags_vocabulary(self):
        """TestFixtureNode is a node type, not a tag — it should not be in TAGS."""
        assert "test_fixture" not in TAGS


class TestTestFixtureNodeRelationships:
    """TestFixtureNode declares the expected relationship descriptors."""

    def test_has_defined_in_relationship(self):
        assert hasattr(TestFixtureNode, "defined_in")
        r = TestFixtureNode.defined_in
        assert r.definition["relation_type"] == "DEFINED_IN"

    def test_has_checked_by_relationship(self):
        assert hasattr(TestFixtureNode, "checked_by")
        r = TestFixtureNode.checked_by
        assert r.definition["relation_type"] == "CHECKED_BY"

    def test_of_type_relationships_exist(self):
        """OF_TYPE is declared per target type (codegraph pattern)."""
        for suffix in ["class", "enum", "interface", "union", "namespace"]:
            attr = f"of_type_{suffix}"
            assert hasattr(TestFixtureNode, attr), f"missing {attr}"
            r = getattr(TestFixtureNode, attr)
            assert r.definition["relation_type"] == "OF_TYPE"

    def test_serialize_relationships_includes_of_type(self):
        rels = TestFixtureNode.serialize_relationships()
        of_type = [r for r in rels if r["relation_type"] == "OF_TYPE"]
        assert len(of_type) >= 5  # class, enum, interface, union, namespace

    def test_serialize_relationships_includes_checked_by(self):
        rels = TestFixtureNode.serialize_relationships()
        checked = [r for r in rels if r["relation_type"] == "CHECKED_BY"]
        assert len(checked) == 1

    def test_serialize_relationships_includes_defined_in(self):
        rels = TestFixtureNode.serialize_relationships()
        defined = [r for r in rels if r["relation_type"] == "DEFINED_IN"]
        assert len(defined) == 1


class TestTestFixtureNodeTestData:
    """Deserialization from JSON test data fixtures."""

    def test_deserialize_from_minimal_json(self):
        data = {
            "name": "engine",
            "qualified_name": "tests::test_ops::engine",
            "kind": "test_fixture",
            "type_signature": "CalculatorEngine",
            "tags": ["as-built"],
        }
        node = TestFixtureNode(**data)
        assert node.name == "engine"
        assert node.type_signature == "CalculatorEngine"

    def test_deserialize_from_full_fixture_json(self):
        path = os.path.join(
            os.path.dirname(__file__), "..", "data", "test_fixture_node_full.json"
        )
        with open(path) as f:
            data = json.load(f)
        # Remove non-field keys before constructing
        fields = {k: v for k, v in data.items() if k != "edges"}
        node = TestFixtureNode(**fields)
        assert node.name == "widget"
        assert node.qualified_name == "tests::test_widget_ops::test_create_widget::widget"
        assert node.kind == "test_fixture"
        assert node.type_signature == "Widget"
        assert node.tags == ["as-built"]


class TestTestNodeComposesTestFixtureNode:
    """TestNode now composes TestFixtureNode alongside AssertionNode/TestStepNode."""

    def test_testnode_has_fixtures_relationship(self):
        assert hasattr(TestNode, "fixtures")
        r = TestNode.fixtures
        assert r.definition["relation_type"] == "COMPOSES"

    def test_serialize_relationships_includes_fixtures(self):
        rels = TestNode.serialize_relationships()
        composes = [r for r in rels if r["relation_type"] == "COMPOSES"]
        targets = {r["target"] for r in composes}
        assert "codegraph.models.test.TestFixtureNode" in targets


class TestAssertionNodeCheckedBy:
    """AssertionNode has incoming CHECKED_BY from TestFixtureNode."""

    def test_assertionnode_has_checked_by_fixtures(self):
        assert hasattr(AssertionNode, "checked_by_fixtures")
        r = AssertionNode.checked_by_fixtures
        assert r.definition["relation_type"] == "CHECKED_BY"


class TestTestStepNodeDefinedFixtures:
    """TestStepNode has incoming DEFINED_IN from TestFixtureNode."""

    def test_teststepnode_has_defined_fixtures(self):
        assert hasattr(TestStepNode, "defined_fixtures")
        r = TestStepNode.defined_fixtures
        assert r.definition["relation_type"] == "DEFINED_IN"


class TestTestFixtureNodeNeo4j:
    """Neo4j integration tests for TestFixtureNode."""

    def test_create_and_save_basic_fixture(self):
        node = TestFixtureNode(
            name="ns_node",
            qualified_name="tests::test_enum_composed::ns_node",
            kind="test_fixture",
            type_signature="NamespaceNode",
            description="A namespace fixture for calc namespace.",
            tags=["as-built"],
        ).save()
        assert node.element_id is not None
        fetched = TestFixtureNode.nodes.get(
            qualified_name="tests::test_enum_composed::ns_node"
        )
        assert fetched.name == "ns_node"
        assert fetched.type_signature == "NamespaceNode"

    def test_of_type_connects_to_class_node(self):
        from codegraph.models.compound import ClassNode

        type_def = ClassNode(
            name="Foo",
            kind="class",
            qualified_name="myapp::Foo",
            tags=["design"],
        ).save()

        fixture = TestFixtureNode(
            name="foo",
            qualified_name="tests::test_foo::foo",
            kind="test_fixture",
            type_signature="Foo",
            description="Instance of Foo class.",
            tags=["as-built"],
        ).save()

        fixture.of_type_class.connect(type_def)

        # Verify via raw Cypher
        from neomodel import db
        results, _ = db.cypher_query(
            "MATCH (f:TestFixtureNode)-[:OF_TYPE]->(t:ClassNode) "
            "WHERE elementId(f) = $fid "
            "RETURN t.qualified_name",
            {"fid": db.parse_element_id(fixture.element_id)},
        )
        assert len(results) == 1
        assert results[0][0] == "myapp::Foo"

    def test_defined_in_connects_to_test_step(self):
        """DEFINED_IN links fixture to the step where it is defined."""
        step = TestStepNode(
            name="step_0",
            qualified_name="tests::test_foo::test_create::step_0",
            kind="test_step",
            order=0,
            description="Create foo = Foo()",
            tags=["as-built"],
        ).save()

        fixture = TestFixtureNode(
            name="foo",
            qualified_name="tests::test_foo::test_create::foo",
            kind="test_fixture",
            type_signature="Foo",
            description="Instance created in step_0.",
            tags=["as-built"],
        ).save()

        fixture.defined_in.connect(step)

        from neomodel import db
        results, _ = db.cypher_query(
            "MATCH (f:TestFixtureNode)-[:DEFINED_IN]->(s:TestStepNode) "
            "WHERE elementId(f) = $fid "
            "RETURN s.qualified_name",
            {"fid": db.parse_element_id(fixture.element_id)},
        )
        assert len(results) == 1
        assert "test_foo::test_create::step_0" in results[0][0]

    def test_checked_by_connects_to_assertion(self):
        """CHECKED_BY links fixture to the assertion that checks it."""
        assertion = AssertionNode(
            name="post_0",
            qualified_name="tests::test_foo::test_create::post_0",
            kind="assertion",
            phase="post",
            order=0,
            operator="==",
            description="foo.name == 'test'",
            tags=["as-built"],
        ).save()

        fixture = TestFixtureNode(
            name="foo",
            qualified_name="tests::test_foo::test_create::foo",
            kind="test_fixture",
            type_signature="Foo",
            description="Instance checked in post_0.",
            tags=["as-built"],
        ).save()

        fixture.checked_by.connect(assertion)

        from neomodel import db
        results, _ = db.cypher_query(
            "MATCH (f:TestFixtureNode)-[:CHECKED_BY]->(a:AssertionNode) "
            "WHERE elementId(f) = $fid "
            "RETURN a.qualified_name",
            {"fid": db.parse_element_id(fixture.element_id)},
        )
        assert len(results) == 1
        assert "test_foo::test_create::post_0" in results[0][0]

    def test_composes_from_test_node(self):
        """TestNode composes TestFixtureNode alongside other children."""
        test = TestNode(
            name="test_create",
            qualified_name="tests::test_foo::test_create",
            kind="test",
            test_name="test_create",
            test_module="tests.test_foo",
            method="automated",
            description="Test fixture composition.",
            tags=["as-built"],
        ).save()

        fixture = TestFixtureNode(
            name="foo",
            qualified_name="tests::test_foo::test_create::foo",
            kind="test_fixture",
            type_signature="Foo",
            description="Instance created in the test.",
            tags=["as-built"],
        ).save()

        test.fixtures.connect(fixture)

        from neomodel import db
        results, _ = db.cypher_query(
            "MATCH (t:TestNode)-[:COMPOSES]->(f:TestFixtureNode) "
            "WHERE elementId(t) = $tid "
            "RETURN f.qualified_name",
            {"tid": db.parse_element_id(test.element_id)},
        )
        assert len(results) == 1
        assert results[0][0] == "tests::test_foo::test_create::foo"

    def test_primitive_type_no_of_type_edge(self):
        """For primitive types (dict, str, list), only type_signature is set."""
        fixture = TestFixtureNode(
            name="parents",
            qualified_name="tests::test_enum::parents",
            kind="test_fixture",
            type_signature="list[NamespaceNode]",
            description="Result of enum_node.parent_namespace.all().",
            tags=["as-built"],
        ).save()

        # type_signature captures the type without needing an OF_TYPE edge
        fetched = TestFixtureNode.nodes.get(
            qualified_name="tests::test_enum::parents"
        )
        assert fetched.type_signature == "list[NamespaceNode]"

        # No OF_TYPE edge should exist for primitives
        from neomodel import db
        results, _ = db.cypher_query(
            "MATCH (f:TestFixtureNode)-[:OF_TYPE]->(t) "
            "WHERE elementId(f) = $fid "
            "RETURN t",
            {"fid": db.parse_element_id(fixture.element_id)},
        )
        assert len(results) == 0


class TestLayerGraphTestFixtureNode:
    """LayerGraph integration tests for TestFixtureNode."""

    def test_layer_graph_deserializes_test_fixture(self):
        """LayerGraph.deserialize handles TestFixtureNode in both flat and nested formats."""
        data = [
            {
                "type": "TestFixtureNode",
                "qualified_name": "tests::test_engine::engine",
                "name": "engine",
                "kind": "test_fixture",
                "type_signature": "Engine",
                "description": "Engine instance for testing.",
                "tags": ["as-built"],
                "edges": [],
            }
        ]

        graph = LayerGraph.deserialize(data)
        entries = list(graph._all_entries())
        assert len(entries) == 1
        assert entries[0].node.__label__ == "TestFixtureNode"
        assert entries[0].node.name == "engine"

    def test_layer_graph_test_fixture_with_edges(self):
        """LayerGraph preserves OF_TYPE, CHECKED_BY, DEFINED_IN edges."""
        from codegraph.uid import compute_uid

        # All nodes must be in the graph data so that to_neo4j() can
        # resolve references via the flat index.  target_uid must be the
        # SHA-1 hash of the target node's qualified_name, and the target
        # data must include an explicit uid field so that _node_key()
        # uses the hash (not just the name).
        widget_uid = compute_uid("myapp::Widget")
        post0_uid = compute_uid("tests::test_w::post_0")
        arrange_uid = compute_uid("tests::test_w::arrange")

        data = [
            {
                "type": "ClassNode",
                "uid": widget_uid,
                "qualified_name": "myapp::Widget",
                "name": "Widget",
                "kind": "class",
                "tags": ["design"],
                "edges": [],
            },
            {
                "type": "AssertionNode",
                "uid": post0_uid,
                "qualified_name": "tests::test_w::post_0",
                "name": "post_0",
                "kind": "assertion",
                "phase": "post",
                "order": 0,
                "operator": "==",
                "description": "widget.name == 'test'",
                "tags": ["as-built"],
                "edges": [],
            },
            {
                "type": "TestStepNode",
                "uid": arrange_uid,
                "qualified_name": "tests::test_w::arrange",
                "name": "arrange",
                "kind": "test_step",
                "order": 0,
                "description": "Create widget = Widget(name='test')",
                "tags": ["as-built"],
                "edges": [],
            },
            {
                "type": "TestFixtureNode",
                "qualified_name": "tests::test_w::widget",
                "name": "widget",
                "kind": "test_fixture",
                "type_signature": "Widget",
                "description": "Widget instance.",
                "tags": ["as-built"],
                "edges": [
                    {"relation_type": "OF_TYPE", "target_uid": widget_uid, "target_type": "ClassNode"},
                    {"relation_type": "CHECKED_BY", "target_uid": post0_uid, "target_type": "AssertionNode"},
                    {"relation_type": "DEFINED_IN", "target_uid": arrange_uid, "target_type": "TestStepNode"},
                ],
            }
        ]

        graph = LayerGraph.deserialize(data)
        graph.to_neo4j()

        from neomodel import db
        results, _ = db.cypher_query(
            "MATCH (f:TestFixtureNode {qualified_name: 'tests::test_w::widget'})"
            "-[:OF_TYPE]->(t:ClassNode) "
            "RETURN t.qualified_name"
        )
        assert results[0][0] == "myapp::Widget"

    def test_layer_graph_nested_test_fixture(self):
        """LayerGraph handles TestFixtureNode nested under TestNode via composes."""
        data = [
            {
                "type": "TestNode",
                "qualified_name": "tests::test_w::test_create",
                "name": "test_create",
                "kind": "test",
                "test_name": "test_create",
                "test_module": "tests.test_w",
                "method": "automated",
                "description": "Creates a widget.",
                "tags": ["as-built"],
                "edges": [],
                "composes": [
                    {
                        "type": "TestFixtureNode",
                        "qualified_name": "tests::test_w::test_create::widget",
                        "name": "widget",
                        "kind": "test_fixture",
                        "type_signature": "Widget",
                        "description": "Widget instance.",
                        "tags": ["as-built"],
                        "edges": [],
                    }
                ],
            }
        ]

        graph = LayerGraph.deserialize(data)

        # The TestFixtureNode should be a composed child of the TestNode
        root = list(graph.entries.values())[0]
        assert root.node.__label__ == "TestNode"

        from neomodel import db
        graph.to_neo4j()

        results, _ = db.cypher_query(
            "MATCH (t:TestNode)-[:COMPOSES]->(f:TestFixtureNode) "
            "WHERE t.qualified_name = 'tests::test_w::test_create' "
            "RETURN f.qualified_name"
        )
        assert len(results) == 1
        assert results[0][0] == "tests::test_w::test_create::widget"