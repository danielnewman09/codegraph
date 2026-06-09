"""Tests for CodeGraphNode class methods.

Covers find_relationship_manager error paths, fetch_by_layer,
fetch_all_by_layer, deserialize error paths, serialize_relationships,
and serialize(fields=...) behaviour.
"""

import pytest
from neomodel import RelationshipTo

from codegraph.models.compound import ClassNode, InterfaceNode, EnumNode
from codegraph.models.file import FileNode
from codegraph.models.member import MethodNode, AttributeNode, EnumValueNode
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


class TestDeserializeErrorPaths:
    """Tests for CodeGraphNode.deserialize() error handling."""

    def test_missing_type_discriminator(self):
        """Raises ValueError when 'type' key is missing."""
        with pytest.raises(ValueError, match="missing the 'type' discriminator"):
            CodeGraphNode.deserialize({"name": "orphan"})

    def test_unknown_type(self):
        """Raises KeyError when type is not in the registry."""
        with pytest.raises(KeyError, match="Unknown node type"):
            CodeGraphNode.deserialize({"type": "FakeNode", "name": "x"})


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


class TestSerializeFields:
    """Tests for CodeGraphNode.serialize(fields=...) — LLM vs all fields."""

    def test_llm_fields_default(self):
        """Default serialize() includes only _llm_fields plus type and edges."""
        node = ClassNode(name="Widget", kind="class", qualified_name="ns::Widget")
        result = node.serialize()
        # _llm_fields for ClassNode: qualified_name, name, kind,
        # brief_description, base_classes, visibility
        llm = ClassNode._llm_fields
        for field in llm:
            assert field in result, f"LLM field '{field}' missing from default serialize()"
        assert result["type"] == "ClassNode"
        assert "edges" in result

    def test_llm_fields_excludes_non_llm(self):
        """Default serialize() omits properties not in _llm_fields."""
        node = ClassNode(
            name="Widget",
            kind="class",
            qualified_name="ns::Widget",
            layer="design",
            module="mymod",
            is_abstract=True,
        )
        result = node.serialize()
        # These are NOT in _llm_fields for ClassNode
        assert "module" not in result
        assert "is_abstract" not in result
        assert "layer" not in result
        assert "detailed_description" not in result
        assert "file_path" not in result

    def test_all_fields_includes_everything(self):
        """serialize(fields='all') includes every defined property."""
        node = ClassNode(
            name="Widget",
            kind="class",
            qualified_name="ns::Widget",
            layer="design",
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
        assert result["type"] == "ClassNode"
        # LLM fields are present
        for field in ClassNode._llm_fields:
            assert field in result, f"LLM field '{field}' missing from serialize(fields='all')"
        # Non-LLM fields are also present
        assert "module" in result
        assert "is_abstract" in result
        assert "layer" in result
        assert "detailed_description" in result
        assert "file_path" in result
        assert "line_number" in result
        assert "source" in result
        assert "source_type" in result
        # Value checks
        assert result["module"] == "mymod"
        assert result["is_abstract"] is True
        assert result["layer"] == "design"
        assert result["line_number"] == 42

    def test_all_fields_has_more_keys_than_llm(self):
        """serialize(fields='all') returns more keys than the default."""
        node = ClassNode(name="A", kind="class", qualified_name="ns::A")
        llm_result = node.serialize()
        all_result = node.serialize(fields="all")
        # 'type' and 'edges' are in both, so we strip them for comparison
        llm_data_keys = {k for k in llm_result if k not in {"type", "edges"}}
        all_data_keys = {k for k in all_result if k not in {"type", "edges"}}
        assert all_data_keys > llm_data_keys, (
            f"fields='all' should have more data keys than fields='llm'. "
            f"all: {sorted(all_data_keys)}, llm: {sorted(llm_data_keys)}"
        )

    def test_llm_fields_on_file_node(self):
        """FileNode.serialize() includes _llm_fields but omits non-LLM fields."""
        node = FileNode(name="test.h", path="/src/test.h")
        result = node.serialize()
        # FileNode _llm_fields is {name, path, source}
        assert "path" in result
        assert "name" in result
        assert "source" in result
        # refid and language are NOT in _llm_fields
        assert "refid" not in result
        assert "language" not in result

    def test_all_fields_on_file_node_includes_refid(self):
        """FileNode.serialize(fields='all') includes refid (the uid)."""
        node = FileNode(name="test.h", path="/src/test.h")
        result = node.serialize(fields="all")
        assert "refid" in result
        assert result["refid"] is not None

    def test_unsaved_node_has_empty_edges(self):
        """Unsaved nodes always have an empty edges list regardless of fields."""
        node = ClassNode(name="Ghost", kind="class", qualified_name="ns::Ghost")
        assert node.serialize()["edges"] == []
        assert node.serialize(fields="all")["edges"] == []


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


class TestWalkComposes:
    """Tests for CodeGraphNode.walk_composes()."""

    def test_walk_composes_returns_methods_and_attributes(self):
        """ClassNode.walk_composes() returns composed methods and attributes."""
        cls = ClassNode(name="MyClass", kind="class", qualified_name="ns::MyClass").save()
        meth = MethodNode(name="draw", kind="method", qualified_name="ns::MyClass::draw").save()
        attr = AttributeNode(name="x", kind="attribute", qualified_name="ns::MyClass::x").save()
        try:
            cls.methods.connect(meth)
            cls.attributes.connect(attr)
            children = cls.walk_composes()
            child_names = {c.name for c in children}
            assert "draw" in child_names
            assert "x" in child_names
        finally:
            cls.methods.disconnect(meth)
            cls.attributes.disconnect(attr)
            meth.delete()
            attr.delete()
            cls.delete()

    def test_walk_composes_returns_empty_for_leaf_nodes(self):
        """MethodNode.walk_composes() returns empty list."""
        meth = MethodNode(name="leaf", kind="method", qualified_name="ns::leaf").save()
        try:
            children = meth.walk_composes()
            assert children == []
        finally:
            meth.delete()

    def test_walk_composes_namespace_returns_classes(self):
        """NamespaceNode.walk_composes() returns composed classes."""
        ns = NamespaceNode(name="myns", kind="namespace", qualified_name="myns").save()
        cls = ClassNode(name="NSClass", kind="class", qualified_name="myns::NSClass").save()
        try:
            ns.classes.connect(cls)
            children = ns.walk_composes()
            assert len(children) == 1
            assert children[0].name == "NSClass"
        finally:
            ns.classes.disconnect(cls)
            cls.delete()
            ns.delete()


class TestSerializeNested:
    """Tests for CodeGraphNode.serialize(nested=True)."""

    def test_nested_includes_composes_key(self):
        """serialize(nested=True) includes composed children under 'composes'."""
        cls = ClassNode(name="NestedClass", kind="class", qualified_name="ns::NestedClass").save()
        meth = MethodNode(name="run", kind="method", qualified_name="ns::NestedClass::run").save()
        try:
            cls.methods.connect(meth)
            result = cls.serialize(nested=True)
            assert "composes" in result
            assert len(result["composes"]) == 1
            assert result["composes"][0]["type"] == "MethodNode"
            assert result["composes"][0]["name"] == "run"
        finally:
            cls.methods.disconnect(meth)
            meth.delete()
            cls.delete()

    def test_nested_removes_composes_from_edges(self):
        """COMPOSES edges are removed from edges when nested=True."""
        cls = ClassNode(name="EdgeClass", kind="class", qualified_name="ns::EdgeClass").save()
        meth = MethodNode(name="doIt", kind="method", qualified_name="ns::EdgeClass::doIt").save()
        try:
            cls.methods.connect(meth)
            # nested=False (default) should include COMPOSES in edges
            flat = cls.serialize()
            composes_edges = [e for e in flat["edges"] if e["relation_type"] == "COMPOSES"]
            assert len(composes_edges) >= 1, "COMPOSES should appear in flat edges"

            # nested=True should NOT include COMPOSES in edges
            nested = cls.serialize(nested=True)
            composes_in_edges = [e for e in nested["edges"] if e["relation_type"] == "COMPOSES"]
            assert len(composes_in_edges) == 0, "COMPOSES should not appear in nested edges"
        finally:
            cls.methods.disconnect(meth)
            meth.delete()
            cls.delete()

    def test_nested_includes_uid_property(self):
        """serialize(nested=True) includes uid property for roundtrip resolution."""
        cls = ClassNode(name="UidClass", kind="class", qualified_name="ns::UidClass").save()
        try:
            result = cls.serialize(nested=True)
            # ClassNode uid is qualified_name, which is in _llm_fields so already present
            assert "qualified_name" in result
        finally:
            cls.delete()

    def test_nested_includes_uid_for_file_node(self):
        """FileNode.serialize(nested=True) includes refid even though it's not in _llm_fields."""
        f = FileNode(name="uidtest.h", path="/src/uidtest.h").save()
        try:
            result = f.serialize(nested=True)
            # FileNode has no COMPOSES relationships, but nested=True still ensures uid
            assert "refid" in result
        finally:
            f.delete()

    def test_nested_recursive(self):
        """serialize(nested=True) recursively includes children's children."""
        ns = NamespaceNode(name="recns", kind="namespace", qualified_name="recns").save()
        cls = ClassNode(name="RecClass", kind="class", qualified_name="recns::RecClass").save()
        meth = MethodNode(name="go", kind="method", qualified_name="recns::RecClass::go").save()
        try:
            ns.classes.connect(cls)
            cls.methods.connect(meth)

            result = ns.serialize(nested=True)
            assert "composes" in result
            class_child = next(c for c in result["composes"] if c["type"] == "ClassNode")
            assert "composes" in class_child
            method_grandchild = next(c for c in class_child["composes"] if c["type"] == "MethodNode")
            assert method_grandchild["name"] == "go"
        finally:
            cls.methods.disconnect(meth)
            ns.classes.disconnect(cls)
            meth.delete()
            cls.delete()
            ns.delete()

    def test_nested_fields_propagates_to_children(self):
        """fields='all' propagates to recursively serialized children."""
        cls = ClassNode(name="FieldsClass", kind="class", qualified_name="ns::FieldsClass", module="mymod").save()
        meth = MethodNode(name="doFields", kind="method", qualified_name="ns::FieldsClass::doFields").save()
        try:
            cls.methods.connect(meth)

            llm_result = cls.serialize(nested=True)
            all_result = cls.serialize(nested=True, fields="all")

            # In LLM mode, the child should omit non-LLM fields
            meth_llm = next(c for c in llm_result["composes"] if c["type"] == "MethodNode")
            assert "name" in meth_llm

            # In all mode, the child should include non-LLM fields
            meth_all = next(c for c in all_result["composes"] if c["type"] == "MethodNode")
            assert "name" in meth_all
            # 'layer' is not a MethodNode llm field
            assert "layer" in meth_all
        finally:
            cls.methods.disconnect(meth)
            meth.delete()
            cls.delete()

    def test_nested_no_composes_for_leaf_nodes(self):
        """Leaf nodes (no COMPOSES edges) have no 'composes' key."""
        meth = MethodNode(name="leafNested", kind="method", qualified_name="ns::leafNested").save()
        try:
            result = meth.serialize(nested=True)
            assert "composes" not in result
            assert result["type"] == "MethodNode"
            assert result["name"] == "leafNested"
        finally:
            meth.delete()

    def test_nested_unsaved_node(self):
        """Unsaved nodes serialize with nested=True but no composes and empty edges."""
        node = ClassNode(name="Unsaved", kind="class", qualified_name="ns::Unsaved")
        result = node.serialize(nested=True)
        assert result["type"] == "ClassNode"
        assert result["edges"] == []
        # No composes since the node isn't saved (no relationships to walk)
        assert "composes" not in result

    def test_flat_mode_unchanged(self):
        """serialize(nested=False) produces identical output to the old serialize()."""
        cls = ClassNode(name="FlatClass", kind="class", qualified_name="ns::FlatClass").save()
        meth = MethodNode(name="flatMethod", kind="method", qualified_name="ns::FlatClass::flatMethod").save()
        try:
            cls.methods.connect(meth)
            # Default (nested=False)
            default_result = cls.serialize()
            explicit_result = cls.serialize(nested=False)
            # Same keys
            assert default_result.keys() == explicit_result.keys()
            # COMPOSES edges should be present in flat mode
            composes = [e for e in default_result["edges"] if e["relation_type"] == "COMPOSES"]
            assert len(composes) >= 1
        finally:
            cls.methods.disconnect(meth)
            meth.delete()
            cls.delete()

    def test_nested_preserves_non_composes_edges(self):
        """Non-COMPOSES edges are preserved in both nested and flat modes."""
        cls = ClassNode(name="EdgeTest", kind="class", qualified_name="ns::EdgeTest").save()
        iface = InterfaceNode(name="IEdgeTest", kind="interface", qualified_name="ns::IEdgeTest").save()
        meth = MethodNode(name="edgeRun", kind="method", qualified_name="ns::EdgeTest::edgeRun").save()
        try:
            cls.realizes.connect(iface)
            cls.methods.connect(meth)

            # nested=True: COMPOSES removed, REALIZES preserved
            nested = cls.serialize(nested=True)
            nested_rels = {e["relation_type"] for e in nested["edges"]}
            assert "COMPOSES" not in nested_rels
            assert "REALIZES" in nested_rels

            # nested=False: both present
            flat = cls.serialize(nested=False)
            flat_rels = {e["relation_type"] for e in flat["edges"]}
            assert "COMPOSES" in flat_rels
            assert "REALIZES" in flat_rels
        finally:
            cls.realizes.disconnect(iface)
            cls.methods.disconnect(meth)
            iface.delete()
            meth.delete()
            cls.delete()

    def test_nested_enum_composes_values(self):
        """EnumNode.serialize(nested=True) inlines enum value children."""
        enum = EnumNode(name="Color", kind="enum", qualified_name="ns::Color").save()
        red = EnumValueNode(name="RED", kind="enumvalue", qualified_name="ns::Color::RED").save()
        blue = EnumValueNode(name="BLUE", kind="enumvalue", qualified_name="ns::Color::BLUE").save()
        try:
            enum.values.connect(red)
            enum.values.connect(blue)

            result = enum.serialize(nested=True)
            assert "composes" in result
            assert len(result["composes"]) == 2
            value_names = {c["name"] for c in result["composes"]}
            assert "RED" in value_names
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
        cls = ClassNode.save_new(name="CreateTestClass", kind="class", qualified_name="ns::CreateTestClass")
        try:
            assert hasattr(cls, "element_id_property")
            assert cls.name == "CreateTestClass"
            assert cls.kind == "class"
            assert cls.qualified_name == "ns::CreateTestClass"
        finally:
            cls.delete()

    def test_create_with_optional_fields(self):
        """save_new() accepts all declared properties including optional ones."""
        cls = ClassNode.save_new(
            name="CreateFullClass",
            kind="class",
            qualified_name="ns::CreateFullClass",
            brief_description="A full class",
            layer="design",
            module="mymod",
        )
        try:
            assert cls.brief_description == "A full class"
            assert cls.layer == "design"
            assert cls.module == "mymod"
        finally:
            cls.delete()

    def test_create_rejects_unknown_properties(self):
        """save_new() raises ValueError for undeclared property names."""
        with pytest.raises(ValueError, match="Unknown property"):
            ClassNode.save_new(
                name="BadClass",
                kind="class",
                qualified_name="ns::BadClass",
                nonexistent_field="oops",
            )

    def test_create_file_node(self):
        """save_new() works for FileNode (UniqueIdProperty auto-generates refid)."""
        f = FileNode.save_new(name="create_test.h", path="/src/create_test.h")
        try:
            assert hasattr(f, "element_id_property")
            assert f.name == "create_test.h"
            assert f.path == "/src/create_test.h"
            assert f.refid is not None
        finally:
            f.delete()

    def test_create_namespace_node(self):
        """save_new() works for NamespaceNode."""
        ns = NamespaceNode.save_new(name="create_ns", kind="namespace", qualified_name="create_ns")
        try:
            assert hasattr(ns, "element_id_property")
            assert ns.name == "create_ns"
        finally:
            ns.delete()

    def test_create_returns_saved_instance(self):
        """save_new() returns a node that is already persisted."""
        meth = MethodNode.save_new(name="createMethod", kind="method", qualified_name="ns::createMethod")
        try:
            assert hasattr(meth, "element_id_property")
            # Can be retrieved from DB
            found = MethodNode.nodes.get(qualified_name="ns::createMethod")
            assert found.name == "createMethod"
        finally:
            meth.delete()

    def test_create_enum_with_values(self):
        """save_new() works for EnumNode, then connect EnumValueNodes."""
        enum = EnumNode.save_new(name="Color", kind="enum", qualified_name="ns::Color")
        red = EnumValueNode.save_new(name="RED", kind="enumvalue", qualified_name="ns::Color::RED")
        blue = EnumValueNode.save_new(name="BLUE", kind="enumvalue", qualified_name="ns::Color::BLUE")
        try:
            enum.values.connect(red)
            enum.values.connect(blue)
            children = enum.walk_composes()
            assert len(children) == 2
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
        cls = ClassNode.save_new(name="DeleteTestClass", kind="class", qualified_name="ns::DeleteTestClass")
        qname = cls.qualified_name
        # Confirm it exists
        assert ClassNode.nodes.get_or_none(qualified_name=qname) is not None
        cls.delete()
        # Confirm it's gone
        assert ClassNode.nodes.get_or_none(qualified_name=qname) is None

    def test_delete_marks_as_deleted(self):
        """delete() marks the node as deleted."""
        cls = ClassNode.save_new(name="DeleteMarkClass", kind="class", qualified_name="ns::DeleteMarkClass")
        cls.delete()
        assert cls.deleted is True

    def test_delete_unsaved_raises(self):
        """delete() raises ValueError on unsaved nodes."""
        node = ClassNode(name="UnsavedDelete", kind="class", qualified_name="ns::UnsavedDelete")
        with pytest.raises(ValueError, match="Cannot delete unsaved"):
            node.delete()

    def test_delete_disconnects_non_composes_relationships(self):
        """delete() disconnects non-COMPOSES relationships before deletion."""
        cls = ClassNode.save_new(name="DeleteRelClass", kind="class", qualified_name="ns::DeleteRelClass")
        dep = ClassNode.save_new(name="DeleteDepClass", kind="class", qualified_name="ns::DeleteDepClass")
        try:
            cls.depends_on.connect(dep)
            # Confirm relationship exists
            assert dep in cls.depends_on.all()
        finally:
            cls.delete()
        # After deletion, dep still exists but the relationship is gone
        assert dep in ClassNode.nodes.filter(qualified_name="ns::DeleteDepClass")
        dep.delete()

    def test_delete_with_incoming_composes(self):
        """delete() on a child does not cascade to the parent."""
        ns = NamespaceNode.save_new(name="delete_ns", kind="namespace", qualified_name="delete_ns")
        cls = ClassNode.save_new(name="DeleteNSClass", kind="class", qualified_name="delete_ns::DeleteNSClass")
        try:
            ns.classes.connect(cls)
            # Confirm relationship exists
            assert cls in ns.classes.all()
        finally:
            cls.delete()
        # After deletion, the namespace still exists but the relationship is gone
        assert ns in NamespaceNode.nodes.filter(qualified_name="delete_ns")
        ns.delete()

    def test_create_delete_lifecycle(self):
        """Full lifecycle: save_new(), update(), delete()."""
        cls = ClassNode.save_new(
            name="LifecycleClass",
            kind="class",
            qualified_name="ns::LifecycleClass",
            brief_description="Initial",
        )
        try:
            assert cls.brief_description == "Initial"
            cls.update(brief_description="Updated")
            assert cls.brief_description == "Updated"
        finally:
            cls.delete()
        assert ClassNode.nodes.get_or_none(qualified_name="ns::LifecycleClass") is None

    # ── Cascade delete ────────────────────────────────────────────────

    def test_delete_cascades_to_composed_children(self):
        """delete() cascades to nodes reachable via outgoing COMPOSES."""
        ns = NamespaceNode.save_new(name="cascade_ns", kind="namespace", qualified_name="cascade_ns")
        cls = ClassNode.save_new(name="CascadeClass", kind="class", qualified_name="cascade_ns::CascadeClass")
        ns.classes.connect(cls)
        # Deleting namespace should cascade-delete the composed class
        ns.delete()
        assert NamespaceNode.nodes.get_or_none(qualified_name="cascade_ns") is None
        assert ClassNode.nodes.get_or_none(qualified_name="cascade_ns::CascadeClass") is None

    def test_delete_cascades_recursively(self):
        """delete() cascades through multiple COMPOSES levels."""
        ns = NamespaceNode.save_new(name="deep_ns", kind="namespace", qualified_name="deep_ns")
        cls = ClassNode.save_new(name="DeepClass", kind="class", qualified_name="deep_ns::DeepClass")
        meth = MethodNode.save_new(name="deepMethod", kind="method", qualified_name="deep_ns::DeepClass::deepMethod")
        ns.classes.connect(cls)
        cls.methods.connect(meth)
        # Deleting namespace cascades: ns -> cls -> meth
        ns.delete()
        assert NamespaceNode.nodes.get_or_none(qualified_name="deep_ns") is None
        assert ClassNode.nodes.get_or_none(qualified_name="deep_ns::DeepClass") is None
        assert MethodNode.nodes.get_or_none(qualified_name="deep_ns::DeepClass::deepMethod") is None

    def test_delete_cascade_with_enum_values(self):
        """delete() cascades from EnumNode to its EnumValueNodes."""
        enum = EnumNode.save_new(name="CascadeColor", kind="enum", qualified_name="ns::CascadeColor")
        red = EnumValueNode.save_new(name="CASCADE_RED", kind="enumvalue", qualified_name="ns::CascadeColor::CASCADE_RED")
        blue = EnumValueNode.save_new(name="CASCADE_BLUE", kind="enumvalue", qualified_name="ns::CascadeColor::CASCADE_BLUE")
        enum.values.connect(red)
        enum.values.connect(blue)
        enum.delete()
        assert EnumNode.nodes.get_or_none(qualified_name="ns::CascadeColor") is None
        assert EnumValueNode.nodes.get_or_none(qualified_name="ns::CascadeColor::CASCADE_RED") is None
        assert EnumValueNode.nodes.get_or_none(qualified_name="ns::CascadeColor::CASCADE_BLUE") is None

    def test_delete_cascade_preserves_non_composes_neighbors(self):
        """delete() only cascades to COMPOSES children, not other relationships."""
        cls_a = ClassNode.save_new(name="CascadeA", kind="class", qualified_name="ns::CascadeA")
        cls_b = ClassNode.save_new(name="CascadeB", kind="class", qualified_name="ns::CascadeB")
        meth = MethodNode.save_new(name="cascadeMethod", kind="method", qualified_name="ns::CascadeA::cascadeMethod")
        cls_a.methods.connect(meth)
        cls_a.depends_on.connect(cls_b)  # non-COMPOSES relationship
        cls_a.delete()
        # meth was composed by cls_a, so it gets cascade-deleted
        assert MethodNode.nodes.get_or_none(qualified_name="ns::CascadeA::cascadeMethod") is None
        # cls_b was referenced (DEPENDS_ON), not composed, so it survives
        assert ClassNode.nodes.get_or_none(qualified_name="ns::CascadeB") is not None
        cls_b.delete()


class TestSaveNewImpl:
    """Tests for CodeGraphNode._save_new() static method."""

    def test_save_new_impl(self):
        """CodeGraphNode._save_new(ClassNode, ...) works directly."""
        cls = CodeGraphNode._save_new(ClassNode, name="StaticCreateClass", kind="class", qualified_name="ns::StaticCreateClass")
        try:
            assert hasattr(cls, "element_id_property")
            assert cls.name == "StaticCreateClass"
        finally:
            cls.delete()

    def test_save_new_impl_rejects_unknown(self):
        """CodeGraphNode._save_new() validates properties."""
        with pytest.raises(ValueError, match="Unknown property"):
            CodeGraphNode._save_new(ClassNode, name="BadClass", kind="class",
                                qualified_name="ns::BadClass", bogus="nope")

    def test_save_new_matches_impl(self):
        """save_new() and _save_new() produce equivalent results."""
        a = ClassNode.save_new(name="DelegateA", kind="class", qualified_name="ns::DelegateA")
        b = CodeGraphNode._save_new(ClassNode, name="DelegateB", kind="class", qualified_name="ns::DelegateB")
        try:
            assert hasattr(a, "element_id_property")
            assert hasattr(b, "element_id_property")
            assert a.name == "DelegateA"
            assert b.name == "DelegateB"
        finally:
            a.delete()
            b.delete()
