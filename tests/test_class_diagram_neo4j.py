"""Test ClassDiagram to_neo4j() / from_neo4j() round-trip."""
import pytest
from codegraph.designs import ClassDiagram
from codegraph.designs.compound import ClassNode, InterfaceNode, EnumNode
from codegraph.designs.member import AttributeNode, MethodNode, EnumValueNode
from codegraph.designs.edges import Association
from codegraph.nodes import CompoundNode, MemberNode
from codegraph.edges import CodebaseEdge


def make_sample_diagram() -> ClassDiagram:
    return ClassDiagram(
        classes=[
            ClassNode(
                name="Calculator",
                qualified_name="calc::Calculator",
                kind="class",
                description="A simple calculator",
                module="calc",
                attributes=[
                    AttributeNode(
                        name="count", qualified_name="calc::Calculator::count",
                        type_signature="int", visibility="private",
                        description="Operation counter",
                    )
                ],
                methods=[
                    MethodNode(
                        name="add", qualified_name="calc::Calculator::add",
                        type_signature="int", argsstring="(int a, int b)",
                        visibility="public", description="Add two numbers",
                    )
                ],
            )
        ],
        interfaces=[
            InterfaceNode(
                name="IPrintable", qualified_name="calc::IPrintable",
                kind="interface", module="calc",
                is_abstract=True,
                methods=[
                    MethodNode(
                        name="print", qualified_name="calc::IPrintable::print",
                        type_signature="void", argsstring="()",
                        visibility="public", is_virtual=True,
                    )
                ],
            )
        ],
        enums=[
            EnumNode(
                name="Op", qualified_name="calc::Op",
                kind="enum", module="calc",
                values=[
                    EnumValueNode(name="ADD", qualified_name="calc::Op::ADD"),
                    EnumValueNode(name="SUB", qualified_name="calc::Op::SUB"),
                ],
            )
        ],
        associations=[
            Association(
                subject="calc::Calculator",
                predicate="aggregates",
                object="calc::Matrix",
                mechanism="std::vector",
                description="Internal matrix storage",
            )
        ],
    )


def test_to_neo4j_roundtrip():
    diagram = make_sample_diagram()
    compounds, members, edges = diagram.to_neo4j()

    assert len(compounds) == 3
    compound_map = {c.qualified_name: c for c in compounds}
    calc = compound_map["calc::Calculator"]
    assert calc.kind == "class"
    assert calc.name == "Calculator"
    assert calc.brief_description == "A simple calculator"

    iface = compound_map["calc::IPrintable"]
    assert iface.kind == "interface"
    assert iface.is_abstract is True

    op = compound_map["calc::Op"]
    assert op.kind == "enum"

    assert len(members) == 5
    member_map = {m.qualified_name: m for m in members}
    count = member_map["calc::Calculator::count"]
    assert count.kind == "variable"
    assert count.type_signature == "int"

    add_method = member_map["calc::Calculator::add"]
    assert add_method.kind == "method"
    assert add_method.type_signature == "int"

    add_enum = member_map["calc::Op::ADD"]
    assert add_enum.kind == "enumvalue"

    assert len(edges) == 1
    edge = edges[0]
    assert edge.subject_qualified_name == "calc::Calculator"
    assert edge.predicate == "aggregates"
    assert edge.object_qualified_name == "calc::Matrix"
    assert edge.description == "Internal matrix storage"


def test_from_neo4j_reconstructs_diagram():
    diagram = make_sample_diagram()
    compounds, members, edges = diagram.to_neo4j()
    reconstructed = ClassDiagram.from_neo4j(compounds, members, edges)

    assert len(reconstructed.classes) == 1
    cls = reconstructed.classes[0]
    assert cls.qualified_name == "calc::Calculator"
    assert cls.description == "A simple calculator"
    assert len(cls.attributes) == 1
    assert cls.attributes[0].name == "count"
    assert len(cls.methods) == 1
    assert cls.methods[0].name == "add"

    assert len(reconstructed.interfaces) == 1
    assert reconstructed.interfaces[0].qualified_name == "calc::IPrintable"
    assert len(reconstructed.interfaces[0].methods) == 1

    assert len(reconstructed.enums) == 1
    assert reconstructed.enums[0].qualified_name == "calc::Op"
    assert len(reconstructed.enums[0].values) == 2

    assert len(reconstructed.associations) == 1
    assert reconstructed.associations[0].subject == "calc::Calculator"

    entity = reconstructed.get_entity("calc::Calculator")
    assert entity is not None
    assert entity.qualified_name == "calc::Calculator"


def test_class_diagram_llm_serialization():
    diagram = make_sample_diagram()
    dumped = diagram.model_dump(tags={"llm", "ticketing"})

    cls = dumped["classes"][0]
    assert cls["name"] == "Calculator"
    assert cls["qualified_name"] == "calc::Calculator"
    assert "file_path" not in cls
    assert "layer" not in cls
    assert cls["attributes"][0]["type_name"] == "int"
    assert cls["methods"][0]["return_type"] == "int"

    assoc = dumped["associations"][0]
    assert assoc["from_class"] == "calc::Calculator"
    assert assoc["to_class"] == "calc::Matrix"
    assert assoc["kind"] == "aggregates"
