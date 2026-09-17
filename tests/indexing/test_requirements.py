from __future__ import annotations

from pathlib import Path

from codegraph.graph import CompositeEntry, LayerGraph
from codegraph_index.contracts import Availability, ExtractionResult, IndexRequest
from codegraph_index.persistence import InMemoryPersistence
from codegraph_index.service import IndexService


class EmptyAdapter:
    name = "empty"
    version = "test"
    languages = frozenset({"empty"})

    def available(self, request):
        return Availability(True)

    def extract(self, request):
        return ExtractionResult(LayerGraph(tags=frozenset({"as-built"})))


class ClassCollisionAdapter:
    """Extracts a single ``ClassNode`` named ``R`` (``qualified_name=R``)."""

    name = "class-collision"
    version = "test"
    languages = frozenset({"class-collision"})

    def available(self, request):
        return Availability(True)

    def extract(self, request):
        from codegraph.identity import (
            IdentityScope,
            identity_scope,
            resolve_identity_for,
        )
        from codegraph.models import ClassNode

        scope = IdentityScope.repository(request.project_id, request.repository_id)
        with identity_scope(scope):
            node = ClassNode(name="R", qualified_name="R", source=request.source)
            node.canonical_key = resolve_identity_for(node, scope).key()
        return ExtractionResult(
            LayerGraph(
                tags=frozenset({"as-built"}),
                entries={node.canonical_key: CompositeEntry(node=node)},
            )
        )


def _request(tmp_path: Path, requirements_dir: Path) -> IndexRequest:
    return IndexRequest(
        project_root=tmp_path,
        project_id="requirements-tests",
        repository_id="fixture",
        source="fixture",
        language="empty",
        input_paths=(tmp_path,),
        requirements_dir=requirements_dir,
    )


def _write_requirement(
    root: Path,
    *,
    feature: str = "feature-a",
    hlr: str = "REQ-001",
    llr: str = "REQ-001.1",
    description: str = "The operation shall be deterministic.",
) -> Path:
    path = root / feature / "requirements.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "# codegraph: requirements\n\n"
        f"## HLR: `{hlr}`\n"
        "The system shall provide the operation.\n"
        "- status: accepted\n"
        f"### LLR: `{llr}`\n"
        f"{description}\n"
        "- status: proposed\n",
        encoding="utf-8",
    )
    return path


def _nodes(result, type_name: str):
    return [
        entry.node
        for entry in result.graph._all_entries()
        if type(entry.node).__name__ == type_name
    ]


def test_extracted_code_node_survives_qualified_name_collision_with_requirement(
    tmp_path,
):
    """A code ``ClassNode`` and an ``HLR`` may share a qualified name.

    Merging the requirement slice into the extracted graph must key on
    canonical identity, not the bare qualified name, so the collision keeps
    both nodes instead of silently discarding the requirement.
    """
    requirements_dir = tmp_path / "requirements"
    path = requirements_dir / "feature" / "requirements.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "# codegraph: requirements\n\n"
        "## HLR: `R`\n"
        "The system shall provide R.\n"
        "- status: accepted\n",
        encoding="utf-8",
    )
    request = IndexRequest(
        project_root=tmp_path,
        project_id="requirements-tests",
        repository_id="fixture",
        source="fixture",
        language="class-collision",
        input_paths=(tmp_path,),
        requirements_dir=requirements_dir,
    )

    result = IndexService((ClassCollisionAdapter(),)).index(request)

    assert result.success is True, [d.code for d in result.diagnostics]
    nodes = {
        (type(entry.node).__name__, entry.node.qualified_name)
        for entry in result.graph._all_entries()
    }
    assert nodes == {("ClassNode", "R"), ("HLR", "R")}


def test_unified_index_loads_only_authoritative_requirements_documents(tmp_path):
    requirements_dir = tmp_path / "requirements"
    _write_requirement(requirements_dir)
    (requirements_dir / "feature-a" / "feedback.md").write_text(
        "## HLR: `IGNORED`\nThis is a derived review artifact.\n",
        encoding="utf-8",
    )

    result = IndexService((EmptyAdapter(),)).index(_request(tmp_path, requirements_dir))

    assert result.success is True
    assert {node.qualified_name for node in _nodes(result, "HLR")} == {"REQ-001"}
    assert {node.qualified_name for node in _nodes(result, "LLR")} == {"REQ-001.1"}
    hlr = _nodes(result, "HLR")[0]
    llr = _nodes(result, "LLR")[0]
    assert hlr.status == "accepted"
    assert llr.status == "proposed"
    assert "requirements" in hlr.tags
    assert result.delta.summary()["entities_created"] == 2
    assert result.delta.summary()["relationships_created"] == 1


def test_requirement_status_survives_markdown_export_reload(tmp_path):
    from codegraph.export.markdown import export_markdown, import_markdown
    from codegraph.identity import IdentityScope, identity_scope

    requirements_dir = tmp_path / "requirements"
    _write_requirement(requirements_dir)
    request = _request(tmp_path, requirements_dir)
    result = IndexService((EmptyAdapter(),)).index(request)

    exported = export_markdown(result.graph, fields="all")
    with identity_scope(
        IdentityScope.repository(request.project_id, request.repository_id)
    ):
        restored = import_markdown(
            exported,
            tags=frozenset({"requirements"}),
            source=request.source,
            strict=True,
        )

    restored_nodes = [entry.node for entry in restored._all_entries()]
    restored_hlr = next(node for node in restored_nodes if type(node).__name__ == "HLR")
    restored_llr = next(node for node in restored_nodes if type(node).__name__ == "LLR")
    assert restored_hlr.status == "accepted"
    assert restored_llr.status == "proposed"


def test_acceptance_criteria_nodes_are_indexed_with_requirement_hierarchy(tmp_path):
    requirements_dir = tmp_path / "requirements"
    path = _write_requirement(requirements_dir)
    path.write_text(
        path.read_text(encoding="utf-8")
        + "#### Test: `acceptance::deterministic`\n"
        + "Verify deterministic behavior.\n"
        + "- method: automated\n"
        + "##### Assertion: `acceptance::deterministic::result`\n"
        + "- operator: ==\n"
        + "- phase: post\n",
        encoding="utf-8",
    )

    result = IndexService((EmptyAdapter(),)).index(_request(tmp_path, requirements_dir))

    assert result.success is True
    assert len(_nodes(result, "TestNode")) == 1
    assert len(_nodes(result, "AssertionNode")) == 1
    assert result.delta.summary()["entities_created"] == 4
    assert result.delta.summary()["relationships_created"] == 3


def test_requirements_reindex_reports_stable_change_rename_and_delete_deltas(tmp_path):
    requirements_dir = tmp_path / "requirements"
    path = _write_requirement(requirements_dir)
    persistence = InMemoryPersistence()
    service = IndexService((EmptyAdapter(),), persistence)
    request = _request(tmp_path, requirements_dir)

    first = service.index(request)
    unchanged = service.index(request)
    _write_requirement(
        requirements_dir, description="The operation shall be repeatable."
    )
    changed = service.index(request)
    _write_requirement(requirements_dir, llr="REQ-001.2")
    renamed = service.index(request)
    path.write_text(
        "# codegraph: requirements\n\n"
        "## HLR: `REQ-001`\nThe system shall provide the operation.\n"
        "- status: accepted\n",
        encoding="utf-8",
    )
    deleted = service.index(request)

    assert first.success and unchanged.success and changed.success
    assert renamed.success and deleted.success
    assert unchanged.delta.is_empty
    assert len(changed.delta.entities.changed) == 1
    assert len(renamed.delta.entities.created) == 1
    assert len(renamed.delta.entities.deleted) == 1
    assert len(renamed.delta.relationships.created) == 1
    assert len(renamed.delta.relationships.deleted) == 1
    assert len(deleted.delta.entities.deleted) == 1
    assert len(deleted.delta.relationships.deleted) == 1


def test_duplicate_requirement_identity_is_fatal_and_does_not_persist(tmp_path):
    requirements_dir = tmp_path / "requirements"
    _write_requirement(requirements_dir, feature="feature-a")
    _write_requirement(requirements_dir, feature="feature-b")
    persistence = InMemoryPersistence()

    result = IndexService((EmptyAdapter(),), persistence).index(
        _request(tmp_path, requirements_dir)
    )

    assert result.success is False
    assert result.persisted is False
    assert "DUPLICATE_REQUIREMENT_IDENTITY" in {
        diagnostic.code for diagnostic in result.diagnostics
    }
    assert persistence.graphs == {}


def test_conflicting_requirement_identity_is_reported(tmp_path):
    requirements_dir = tmp_path / "requirements"
    _write_requirement(requirements_dir, feature="feature-a")
    _write_requirement(
        requirements_dir,
        feature="feature-b",
        description="The operation shall have different behavior.",
    )

    result = IndexService((EmptyAdapter(),)).index(_request(tmp_path, requirements_dir))

    assert result.success is False
    assert "CONFLICTING_REQUIREMENT_IDENTITY" in {
        diagnostic.code for diagnostic in result.diagnostics
    }


def test_malformed_requirement_relationship_is_reported(tmp_path):
    requirements_dir = tmp_path / "requirements"
    path = _write_requirement(requirements_dir)
    path.write_text(
        path.read_text(encoding="utf-8")
        + "\n## Relationships\n"
        + "- `MISSING` → `REQ-001` **depends_on** (HLR)\n",
        encoding="utf-8",
    )

    result = IndexService((EmptyAdapter(),)).index(_request(tmp_path, requirements_dir))

    assert result.success is False
    assert "MALFORMED_REQUIREMENTS_DOCUMENT" in {
        diagnostic.code for diagnostic in result.diagnostics
    }


def test_legacy_sha1_target_is_dropped_with_structured_warning(tmp_path):
    requirements_dir = tmp_path / "requirements"
    path = _write_requirement(requirements_dir)
    path.write_text(
        path.read_text(encoding="utf-8")
        + "\n## Relationships\n"
        + "- `REQ-001` → `0123456789abcdef0123456789abcdef01234567` "
        + "**depends_on** (HLR)\n",
        encoding="utf-8",
    )

    result = IndexService((EmptyAdapter(),)).index(_request(tmp_path, requirements_dir))

    assert result.success is True
    assert "LEGACY_REQUIREMENT_REFERENCE_DROPPED" in {
        diagnostic.code for diagnostic in result.diagnostics
    }
    assert result.delta.summary()["relationships_created"] == 1


def test_nonexistent_canonical_reference_is_unresolved_and_not_persisted(tmp_path):
    """A well-formed canonical key for a missing endpoint must not persist.

    Accepting a ``cg:v1:`` target on syntax alone reported ``success=True``
    and ``relationships_created=1`` while SQLite stored no edge, because the
    endpoint could not be joined.  The edge must be omitted and the index
    run must fail with ``UNRESOLVED_REQUIREMENT_REFERENCE``.
    """
    from codegraph.backends.sqlite import SqliteBackend, SqliteConfig
    from codegraph.identity import IdentityScope, resolve_identity_for
    from codegraph_index.persistence import RepositoryPersistence
    from codegraph_requirements.models.requirement import HLR

    scope = IdentityScope.repository("requirements-tests", "fixture")
    missing = resolve_identity_for(
        HLR(name="ABSENT", qualified_name="ABSENT", source="fixture"), scope
    ).key()
    assert missing.startswith("cg:v1:")

    # Only one HLR, so the bogus dependency is the document's sole edge;
    # before the fix this reported ``relationships_created=1``.
    requirements_dir = tmp_path / "requirements"
    path = requirements_dir / "feature" / "requirements.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "# codegraph: requirements\n\n"
        "## HLR: `REQ-001`\n"
        "The system shall provide the operation.\n"
        "- status: accepted\n"
        "\n## Relationships\n"
        f"- `REQ-001` → `{missing}` **depends_on** (HLR)\n",
        encoding="utf-8",
    )

    config = SqliteConfig(path=str(tmp_path / "canonical.sqlite3"))
    backend = SqliteBackend(config)
    backend.initialize(config)
    result = IndexService(
        (EmptyAdapter(),), RepositoryPersistence(backend)
    ).index(_request(tmp_path, requirements_dir))

    assert result.success is False
    assert result.persisted is False
    assert "UNRESOLVED_REQUIREMENT_REFERENCE" in {
        diagnostic.code for diagnostic in result.diagnostics
    }
    assert result.delta.summary()["relationships_created"] == 0

    rows, _columns = backend.execute_raw("SELECT COUNT(*) AS n FROM edges")
    assert rows[0]["n"] == 0


def test_missing_configured_requirements_directory_is_fatal(tmp_path):
    result = IndexService((EmptyAdapter(),)).index(
        _request(tmp_path, tmp_path / "missing")
    )

    assert result.success is False
    assert result.diagnostics[0].code == "REQUIREMENTS_DIRECTORY_NOT_FOUND"


def test_empty_required_literal_is_sqlite_idempotent(tmp_path):
    from codegraph.backends.sqlite import SqliteBackend, SqliteConfig
    from codegraph_index.persistence import RepositoryPersistence

    requirements_dir = tmp_path / "requirements"
    path = _write_requirement(requirements_dir)
    path.write_text(
        path.read_text(encoding="utf-8")
        + "\n## Literal: `literal::`\n"
        + "- value_type: string\n"
        + "\n## Relationships\n"
        + "- `REQ-001` → `literal::` **depends_on** (LiteralNode)\n",
        encoding="utf-8",
    )
    config = SqliteConfig(path=str(tmp_path / "requirements.sqlite3"))
    backend = SqliteBackend(config)
    backend.initialize(config)
    service = IndexService(
        (EmptyAdapter(),),
        RepositoryPersistence(backend),
    )
    request = _request(tmp_path, requirements_dir)

    first = service.index(request)
    second = service.index(request)

    assert first.success and second.success
    assert second.delta.is_empty
