"""Test ClassDiagram to_neo4j() / from_neo4j() round-trip."""
from codegraph.designs import ClassDiagram
from codegraph.designs.compound import ClassNode, InterfaceNode, EnumNode
from codegraph.designs.member import AttributeNode, MethodNode, EnumValueNode
from codegraph.designs.edges import Association
from codegraph.repositories.compound import CompoundRepository
from codegraph.repositories.member import MemberRepository


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


def test_to_neo4j_persists_internally():
    """to_neo4j() persists to Neo4j and returns None."""
    diagram = make_sample_diagram()
    diagram.to_neo4j()

    # Read back via repositories
    compounds = CompoundRepository().find_by_layer("design")
    members = MemberRepository().find_by_layer("design")

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


def test_from_neo4j_reconstructs_diagram():
    """Persist a diagram, then reconstruct it via from_neo4j()."""
    diagram = make_sample_diagram()
    diagram.to_neo4j()

    # Read back via from_neo4j() with no args (reads from DB)
    reconstructed = ClassDiagram.from_neo4j()

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

    # Associations are persisted as Neo4j relationships, not CodebaseEdge rows.
    # from_neo4j() without explicit edge lists does not reconstruct them yet.
    # This is tracked as a future enhancement.

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
