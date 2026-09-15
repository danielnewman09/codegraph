from __future__ import annotations

from codegraph_index.contracts import Availability, ExtractionResult, IndexRequest
from codegraph_index.service import AdapterRegistry


class FakeAdapter:
    name = "fake"
    version = "test"
    languages = frozenset({"fake"})

    def available(self, request):
        return Availability(True)

    def extract(self, request):
        from codegraph.graph import LayerGraph

        return ExtractionResult(LayerGraph(tags=frozenset({"as-built"})))


def test_registry_selects_by_language_without_importing_toolchains() -> None:
    registry = AdapterRegistry((FakeAdapter(),))
    assert registry.select("FAKE").name == "fake"
    assert registry.select("python") is None
