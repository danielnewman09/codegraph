"""Contract and import-isolation gates for ``codegraph_index``."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from codegraph_index.contracts import (
    ChangeSet,
    EntityRef,
    IndexDelta,
    IndexFinding,
    IndexMode,
    IndexRequest,
    RelationshipRef,
)


def test_index_request_is_immutable_and_normalized() -> None:
    request = IndexRequest(
        project_root="/tmp/project",
        project_id="project",
        repository_id="repo",
        source="repo-source",
        language="PYTHON",
        input_paths=["src"],
        adapter_options={"flag": True},
    )

    assert request.language == "python"
    assert request.input_paths == (Path("src"),)
    assert request.adapter_options["flag"] is True
    with pytest.raises((AttributeError, TypeError)):
        request.source = "other"  # type: ignore[misc]
    with pytest.raises(TypeError):
        request.adapter_options["new"] = True  # type: ignore[index]


def test_delta_ordering_and_summary_are_deterministic() -> None:
    a = EntityRef("cg:v1:a", "ClassNode", "source", "a")
    b = EntityRef("cg:v1:b", "ClassNode", "source", "b")
    relation = RelationshipRef("cg:v1:a", "COMPOSES", "cg:v1:b")
    findings = (IndexFinding("DUPLICATE", ("cg:v1:b",)),)
    delta = IndexDelta(
        entities=ChangeSet(created=(b, a), ambiguous=findings),
        relationships=ChangeSet(created=(relation,)),
    )

    assert delta.entities.created == (a, b)
    assert delta.summary() == {
        "entities_created": 2,
        "entities_matched": 0,
        "entities_changed": 0,
        "entities_deleted": 0,
        "entities_ambiguous": 1,
        "relationships_created": 1,
        "relationships_matched": 0,
        "relationships_changed": 0,
        "relationships_deleted": 0,
        "relationships_ambiguous": 0,
        "ambiguous": 1,
    }


def test_contract_import_does_not_load_compatibility_or_optional_modules() -> None:
    source_root = Path(__file__).resolve().parents[2] / "src"
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; from codegraph_index.contracts import IndexRequest; "
                "assert not any(k.startswith('doxygen_index') for k in sys.modules); "
                "assert 'codegraph_index.doxygen' not in sys.modules; "
                "print(IndexRequest.__name__)"
            ),
        ],
        env={"PYTHONPATH": str(source_root)},
        check=True,
        capture_output=True,
        text=True,
    )
    assert completed.stdout.strip() == "IndexRequest"


def test_base_import_survives_optional_toolchain_blocking() -> None:
    source_root = Path(__file__).resolve().parents[2] / "src"
    script = """
import builtins
import sys

blocked = {"bs4", "requests", "lxml", "llm_caller", "openai"}
real_import = builtins.__import__

def guarded_import(name, *args, **kwargs):
    if name.split(".", 1)[0] in blocked:
        raise ImportError(f"blocked optional dependency: {name}")
    return real_import(name, *args, **kwargs)

builtins.__import__ = guarded_import
from codegraph_index import IndexRequest
from codegraph_index.adapters.python import PythonExtractionAdapter
assert IndexRequest.__name__ == "IndexRequest"
assert PythonExtractionAdapter().name == "python-ast"
assert not any(name.startswith("doxygen_index") for name in sys.modules)
"""
    subprocess.run(
        [sys.executable, "-c", script],
        env={"PYTHONPATH": str(source_root)},
        check=True,
        capture_output=True,
        text=True,
    )


def test_indexing_package_does_not_embed_backend_drivers_or_raw_queries() -> None:
    package_root = Path(__file__).resolve().parents[2] / "src" / "codegraph_index"
    forbidden = ("execute_raw(", "GraphDatabase", "from neo4j", "import neo4j")
    for path in package_root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert not any(token in text for token in forbidden), path
