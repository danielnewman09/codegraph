"""Shared test-graph builder: a class under test with neighbours, an
unrelated class, and an LLR (optionally under an HLR) whose tests
reference the class under test via CALLEE / operand edges.

Used by the scoped-verification PlantUML tests and the coverage-Markdown
tests so both exporters are exercised against the same graph.
"""

from codegraph.graph import LayerGraph, CompositeEntry
from codegraph.models.compound import ClassNode
from codegraph.models.member import MethodNode, AttributeNode
from codegraph.models.namespace import NamespaceNode
from codegraph.models.test import TestNode, TestStepNode, AssertionNode
from codegraph_requirements.models.requirement import LLR, HLR


def make_scoped_verification_graph(with_hlr: bool = False) -> LayerGraph:
    """Build a small graph with a class under test, a neighbour, an
    unrelated class, and an LLR (optionally under an HLR) whose tests
    reference the class under test via CALLEE / operand edges."""
    engine = ClassNode(name="Engine", kind="class", source="test",
                       qualified_name="app::Engine", tags=["design"])
    tank = ClassNode(name="FuelTank", kind="class", source="test",
                     qualified_name="app::FuelTank", tags=["design"])
    other = ClassNode(name="Other", kind="class", source="test",
                      qualified_name="app::Other", tags=["design"])
    start = MethodNode(name="start", kind="method", source="test",
                       qualified_name="app::Engine::start", tags=["design"],
                       visibility="public", type_signature="void",
                       argsstring="()")
    speed = AttributeNode(name="speed", kind="attribute", source="test",
                          qualified_name="app::Engine::speed", tags=["design"],
                          visibility="private", type_signature="int")

    # Tests that validate Engine
    t_engine = TestNode(name="test_engine_starts", kind="test", source="test",
                        qualified_name="app::engine::test_engine_starts",
                        tags=["design"], test_name="test_engine_starts")
    step_start = TestStepNode(name="step_start_engine", kind="test_step",
                              source="test",
                              qualified_name="app::engine::test_engine_starts::step_start_engine",
                              tags=["design"], order=0)
    assert_speed = AssertionNode(name="assert_speed", kind="assertion",
                                 source="test",
                                 qualified_name="app::engine::test_engine_starts::assert_speed",
                                 tags=["design"], phase="post",
                                 description="engine speed is set")
    # Orphan-style operand target with a namespace-less owner qname
    # (MigrationManager::error_state style) — exercises short-name match.
    assert_orphan = AssertionNode(
        name="assert_orphan_state", kind="assertion", source="test",
        qualified_name="app::engine::test_engine_starts::assert_orphan_state",
        tags=["design"], phase="post",
        description="Engine::error_state cleared")

    # A test that validates an unrelated class — must be excluded
    t_other = TestNode(name="test_other", kind="test", source="test",
                       qualified_name="app::other::test_other",
                       tags=["design"], test_name="test_other")
    step_other = TestStepNode(name="step_other", kind="test_step", source="test",
                              qualified_name="app::other::test_other::step_other",
                              tags=["design"], order=0)

    step_start_entry = CompositeEntry(
        node=step_start,
        references=[("CALLEE", "app::Engine::start", "MethodNode")],
    )
    assert_speed_entry = CompositeEntry(
        node=assert_speed,
        references=[("LEFT_OPERAND", "app::Engine::speed", "AttributeNode")],
    )
    assert_orphan_entry = CompositeEntry(
        node=assert_orphan,
        references=[("LEFT_OPERAND", "Engine::error_state", "AttributeNode")],
    )
    t_engine_entry = CompositeEntry(
        node=t_engine,
        children={
            "TestStepNode": {step_start.qualified_name: step_start_entry},
            "AssertionNode": {
                assert_speed.qualified_name: assert_speed_entry,
                assert_orphan.qualified_name: assert_orphan_entry,
            },
        },
    )
    step_other_entry = CompositeEntry(
        node=step_other,
        references=[("CALLEE", "app::Other::start", "MethodNode")],
    )
    t_other_entry = CompositeEntry(
        node=t_other,
        children={"TestStepNode": {step_other.qualified_name: step_other_entry}},
    )

    engine_entry = CompositeEntry(
        node=engine,
        children={
            "MethodNode": {start.qualified_name: CompositeEntry(node=start)},
            "AttributeNode": {speed.qualified_name: CompositeEntry(node=speed)},
        },
        references=[("DEPENDS_ON", "app::FuelTank", "ClassNode")],
    )
    ns_entry = CompositeEntry(
        node=NamespaceNode(name="app", kind="namespace", source="test",
                           qualified_name="app", tags=["design"]),
        children={
            "ClassNode": {
                engine.qualified_name: engine_entry,
                tank.qualified_name: CompositeEntry(node=tank),
                other.qualified_name: CompositeEntry(node=other),
            },
        },
    )

    if with_hlr:
        llr = LLR(name="llr_engine", source="test",
                  qualified_name="llr_engine", tags=["design"])
        llr_entry = CompositeEntry(
            node=llr,
            children={"TestNode": {
                t_engine.qualified_name: t_engine_entry,
                t_other.qualified_name: t_other_entry,
            }},
        )
        hlr = HLR(name="hlr_engine", source="test",
                  qualified_name="hlr_engine", tags=["design"])
        hlr_entry = CompositeEntry(
            node=hlr,
            children={"LLR": {llr.qualified_name: llr_entry}},
        )
        entries = {"app": ns_entry, "hlr_engine": hlr_entry}
    else:
        llr = LLR(name="llr_engine", source="test",
                  qualified_name="llr_engine", tags=["design"])
        llr_entry = CompositeEntry(
            node=llr,
            children={"TestNode": {
                t_engine.qualified_name: t_engine_entry,
                t_other.qualified_name: t_other_entry,
            }},
        )
        entries = {"app": ns_entry, "llr_engine": llr_entry}

    return LayerGraph(tags=frozenset({"design"}), entries=entries)

