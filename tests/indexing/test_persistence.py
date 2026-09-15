from __future__ import annotations

from pathlib import Path

from codegraph.backends.sqlite import SqliteBackend, SqliteConfig
from codegraph_index.contracts import IndexRequest
from codegraph_index.persistence import InMemoryPersistence, RepositoryPersistence
from codegraph_index.service import IndexService


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "python"


def test_sqlite_repository_persistence_is_idempotent(tmp_path):
    source_root = FIXTURE_ROOT
    database = tmp_path / "graph.sqlite3"
    config = SqliteConfig(path=str(database))
    backend = SqliteBackend(config)
    backend.initialize(config)

    request = IndexRequest(
        project_root=source_root,
        project_id="indexing-tests",
        repository_id="python-fixture",
        source="python-fixture",
        language="python",
        input_paths=(source_root,),
    )
    service = IndexService(persistence=RepositoryPersistence(backend))

    first = service.index(request)
    second = service.index(request)

    assert first.success is True
    assert first.persisted is True
    assert second.success is True
    assert second.persisted is True
    assert second.delta.is_empty is True
    assert len(second.delta.entities.matched) == len(first.delta.entities.created)
    assert len(second.delta.relationships.matched) == len(first.delta.relationships.created)


def test_memory_reconciliation_is_idempotent_and_source_scoped():
    persistence = InMemoryPersistence()
    service = IndexService(persistence=persistence)

    first = service.index(
        IndexRequest(
            FIXTURE_ROOT,
            "indexing-tests",
            "memory-repo",
            "source-a",
            "python",
            (FIXTURE_ROOT,),
        )
    )
    second = service.index(
        IndexRequest(
            FIXTURE_ROOT,
            "indexing-tests",
            "memory-repo",
            "source-a",
            "python",
            (FIXTURE_ROOT,),
        )
    )
    other_source = service.index(
        IndexRequest(
            FIXTURE_ROOT,
            "indexing-tests",
            "memory-repo",
            "source-b",
            "python",
            (FIXTURE_ROOT,),
        )
    )

    assert first.success and second.success and other_source.success
    assert second.delta.is_empty
    assert len(second.delta.entities.matched) == len(first.delta.entities.created)
    assert len(second.delta.relationships.matched) == len(first.delta.relationships.created)
    assert set(persistence.graphs) == {"source-a", "source-b"}
    assert persistence.graphs["source-a"] is not persistence.graphs["source-b"]
