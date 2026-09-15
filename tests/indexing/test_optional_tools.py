from __future__ import annotations

from pathlib import Path

from codegraph_index.adapters.cpp import CppExtractionAdapter
from codegraph_index.contracts import IndexRequest


def test_missing_doxygen_is_a_structured_availability_diagnostic(monkeypatch) -> None:
    monkeypatch.setattr("shutil.which", lambda name: None)
    request = IndexRequest(
        Path("."),
        "project",
        "repository",
        "source",
        "cpp",
        (Path("src"),),
    )

    availability = CppExtractionAdapter().available(request)

    assert availability.available is False
    assert [diagnostic.code for diagnostic in availability.diagnostics] == [
        "DOXYGEN_UNAVAILABLE"
    ]
