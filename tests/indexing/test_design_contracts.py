from __future__ import annotations

import json
from pathlib import Path

from codegraph.backends.memory import InMemoryBackend
from codegraph.export.plantuml import GraphView, export_plantuml, import_plantuml
from codegraph.identity import IdentityScope, identity_scope
from codegraph_design.tools.dispatcher import DesignToolDispatcher


CONTRACT_DIAGRAM = (
    Path(__file__).resolve().parents[2]
    / "docs"
    / "plans"
    / "priority3-design"
    / "02-index-contracts.puml"
)
DESIGN_SCOPE = IdentityScope.repository("codegraph-suite", "codegraph-index")


def test_contract_diagram_validates_as_a_design_layergraph() -> None:
    with identity_scope(DESIGN_SCOPE):
        graph = import_plantuml(
            CONTRACT_DIAGRAM.read_text(),
            tags=frozenset({"design"}),
            source="codegraph-index-contracts",
            strict=True,
        )
        entries = graph.serialize()
        design_nodes = [entry for entry in entries if entry["qualified_name"] == "codegraph_index"]
        context_nodes = [entry for entry in entries if entry["qualified_name"] == "LayerGraph"]

        dispatcher = DesignToolDispatcher(
            repo=InMemoryBackend().graph,
            context_classes=context_nodes,
            component_namespace="codegraph_index",
        )
        validation = json.loads(
            dispatcher.dispatch("validate_design", {"nodes": design_nodes})
        )
        smells = json.loads(
            dispatcher.dispatch("check_design_smells", {"nodes": design_nodes})
        )
        produced = json.loads(
            dispatcher.dispatch("produce_oo_design", {"nodes": design_nodes})
        )

        assert validation["valid"] is True
        assert validation["errors"] == []
        assert smells["valid"] is True
        assert smells["summary"]["blocking"] == 0
        assert produced["stored"] is True
        assert export_plantuml(
            graph, fields="llm", view=GraphView.DESIGN_API
        ).rstrip() == CONTRACT_DIAGRAM.read_text().rstrip()
