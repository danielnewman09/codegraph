from __future__ import annotations

from pathlib import Path

from codegraph.graph import CompositeEntry, LayerGraph
from codegraph_index.contracts import Availability, ExtractionResult, IndexMode, IndexRequest
from codegraph_index.service import IndexService


class FakeAdapter:
    name = "fake"
    version = "test"
    languages = frozenset({"fake"})

    def available(self, request):
        return Availability(True)

    def extract(self, request):
        return ExtractionResult(LayerGraph(tags=frozenset({"as-built"})))


class FakePersistence:
    def __init__(self):
        self.calls = []

    def inventory(self, source):
        from codegraph_index.inventory import Inventory

        return Inventory()

    def apply(self, graph, delta):
        self.calls.append((graph, delta))


class InvalidGraphAdapter(FakeAdapter):
    name = "invalid"
    languages = frozenset({"invalid"})

    def extract(self, request):
        del request
        class InvalidNode:
            source = "source"

        return ExtractionResult(
            LayerGraph(
                tags=frozenset({"as-built"}),
                entries={"invalid": CompositeEntry(node=InvalidNode())},
            )
        )


def test_extract_only_does_not_persist():
    persistence = FakePersistence()
    request = IndexRequest(
        Path("."), "project", "repo", "source", "fake", (Path("src"),),
        mode=IndexMode.EXTRACT_ONLY,
    )
    result = IndexService((FakeAdapter(),), persistence).index(request)
    assert result.success is True
    assert result.persisted is False
    assert persistence.calls == []


def test_service_persists_only_after_adapter_selection_and_extraction():
    persistence = FakePersistence()
    request = IndexRequest(
        Path("."), "project", "repo", "source", "fake", (Path("src"),),
    )
    result = IndexService((FakeAdapter(),), persistence).index(request)
    assert result.success is True
    assert result.persisted is True
    assert len(persistence.calls) == 1


def test_inventory_failure_is_structured_and_does_not_persist():
    persistence = FakePersistence()
    request = IndexRequest(
        Path("."), "project", "repo", "source", "invalid", (Path("src"),),
    )

    result = IndexService((InvalidGraphAdapter(),), persistence).index(request)

    assert result.success is False
    assert result.persisted is False
    assert result.diagnostics[0].code == "INVALID_INVENTORY"
    assert result.delta.summary()["ambiguous"] == 1
    assert persistence.calls == []
