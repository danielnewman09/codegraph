from __future__ import annotations

import re
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


def test_cross_document_reference_keeps_its_declared_target_type():
    """A reference to a node declared in another document keeps its target type.

    The relationship line states the endpoint type (``(MethodNode)``) because
    the target lives in the code graph, not in this document.  Dropping that
    declaration makes the endpoint unresolvable whenever the code graph holds
    a second node with the same qualified name — which is the normal case for
    a ``MethodNode`` and its ``ImplementationNode`` (implementation nodes
    deliberately reuse the parent's qualified name).  The declared type is
    the author's disambiguator and must survive the import.
    """
    from codegraph.export.markdown import import_markdown
    from codegraph.identity import IdentityScope, identity_scope

    text = (
        "# codegraph: requirements\n\n"
        "## HLR: `REQ-001`\n"
        "The system shall provide the operation.\n"
        "- status: accepted\n"
        "### LLR: `REQ-001.1`\n"
        "The operation shall be implemented by the code under test.\n"
        "- status: accepted\n"
        "\n## Relationships\n"
        "- `REQ-001.1` → `p::C::m()` **realized_by** (MethodNode)\n"
    )
    with identity_scope(IdentityScope.repository("requirements-tests", "fixture")):
        graph = import_markdown(
            text,
            tags=frozenset({"requirements"}),
            source="fixture",
            strict=True,
        )

    llr = next(
        entry for entry in graph._all_entries()
        if type(entry.node).__name__ == "LLR"
    )
    assert llr.references == [("REALIZED_BY", "p::C::m()", "MethodNode")]


def test_declared_target_type_disambiguates_a_shared_qualified_name(tmp_path):
    """The declared type resolves a reference the qname alone cannot.

    ``p::C::m()`` names both the ``MethodNode`` and its ``ImplementationNode``.
    The requirements document says ``(MethodNode)``; resolution must honour
    that instead of reporting an ambiguous reference and dropping the edge.
    """
    from codegraph.graph import CompositeEntry, LayerGraph
    from codegraph.identity import (
        IdentityScope,
        identity_scope,
        resolve_identity_for,
    )
    from codegraph.models import ClassNode, ImplementationNode, MethodNode

    class SharedNameAdapter:
        name = "shared-name"
        version = "test"
        languages = frozenset({"shared-name"})

        def available(self, request):
            return Availability(True)

        def extract(self, request):
            scope = IdentityScope.repository(
                request.project_id, request.repository_id
            )
            with identity_scope(scope):
                cls = ClassNode(
                    name="C", qualified_name="p::C", source=request.source
                )
                cls.canonical_key = resolve_identity_for(cls, scope).key()
                method = MethodNode(
                    name="m", qualified_name="p::C::m()", source=request.source
                )
                method.canonical_key = resolve_identity_for(method, scope).key()
                impl = ImplementationNode(
                    name="m", qualified_name="p::C::m()", source=request.source
                )
                impl.canonical_key = resolve_identity_for(
                    impl,
                    scope,
                    parents={"parent_callable_key": method.canonical_key},
                ).key()
            class_entry = CompositeEntry(node=cls)
            class_entry.children.setdefault("MethodNode", {})[
                method.canonical_key
            ] = CompositeEntry(node=method)
            return ExtractionResult(
                LayerGraph(
                    tags=frozenset({"as-built"}),
                    entries={
                        cls.canonical_key: class_entry,
                        impl.canonical_key: CompositeEntry(node=impl),
                    },
                )
            )

    requirements_dir = tmp_path / "requirements"
    path = requirements_dir / "feature" / "requirements.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "# codegraph: requirements\n\n"
        "## HLR: `REQ-001`\n"
        "The system shall provide the operation.\n"
        "- status: accepted\n"
        "### LLR: `REQ-001.1`\n"
        "The operation shall be implemented by ``p::C::m()``.\n"
        "- status: accepted\n"
        "\n## Relationships\n"
        "- `REQ-001.1` → `p::C::m()` **realized_by** (MethodNode)\n",
        encoding="utf-8",
    )

    result = IndexService((SharedNameAdapter(),)).index(
        IndexRequest(
            project_root=tmp_path,
            project_id="requirements-tests",
            repository_id="fixture",
            source="fixture",
            language="shared-name",
            input_paths=(tmp_path,),
            requirements_dir=requirements_dir,
        )
    )

    assert result.success is True, [
        f"{d.code}: {d.message}" for d in result.diagnostics
    ]
    llr = next(
        entry for entry in result.graph._all_entries()
        if type(entry.node).__name__ == "LLR"
    )
    assert [rel for rel, _target, _type in llr.references] == ["REALIZED_BY"]
    _rel, target, target_type = llr.references[0]
    assert target.startswith("cg:v1:"), target
    method = next(
        entry for entry in result.graph._all_entries()
        if type(entry.node).__name__ == "MethodNode"
    )
    assert target == method.node.canonical_key
    assert target_type == "MethodNode"


def test_description_line_starting_with_code_span_is_not_dropped():
    """A description line beginning with an inline code span is prose.

    The importer skipped every line starting with a backtick, so authored
    requirement text such as "`commit()` called on an inactive Transaction
    shall signal an error." silently vanished from the indexed description.
    Only a fenced code-block marker (```` ``` ````) is structural.
    """
    from codegraph.export.markdown import import_markdown
    from codegraph.identity import IdentityScope, identity_scope

    description = (
        "The operation shall be transactional.\n"
        "`commit()` called on an inactive Transaction shall signal an error."
    )
    text = (
        "# codegraph: requirements\n\n"
        "## HLR: `REQ-001`\n"
        f"{description}\n"
        "- status: accepted\n"
    )
    with identity_scope(IdentityScope.repository("requirements-tests", "fixture")):
        graph = import_markdown(
            text,
            tags=frozenset({"requirements"}),
            source="fixture",
            strict=True,
        )

    hlr = next(
        entry.node for entry in graph._all_entries()
        if type(entry.node).__name__ == "HLR"
    )
    assert hlr.description == description


def test_description_bullets_that_are_not_properties_are_preserved():
    """An authored description bullet is prose, not a dropped property.

    A description may contain a Markdown list, and a property-looking line
    whose key the node type does not declare (``- TODO: revisit``) is prose
    too.  Both were silently discarded — the importer looked only for the
    ``- key: value`` property form and dropped every other ``- `` line —
    so authored text vanished on import and on the round trip.  A declared
    property line must still set the property.
    """
    from codegraph.export.markdown import import_markdown
    from codegraph.identity import IdentityScope, identity_scope

    description = (
        "The operation shall be atomic:\n"
        "- either every statement is applied\n"
        "- or none is.\n"
        "- TODO: revisit under a concurrent writer"
    )
    text = (
        "# codegraph: requirements\n\n"
        "## HLR: `REQ-001`\n"
        f"{description}\n"
        "- status: accepted\n"
    )
    with identity_scope(IdentityScope.repository("requirements-tests", "fixture")):
        graph = import_markdown(
            text,
            tags=frozenset({"requirements"}),
            source="fixture",
            strict=True,
        )

    hlr = next(
        entry.node for entry in graph._all_entries()
        if type(entry.node).__name__ == "HLR"
    )
    assert hlr.description == description
    assert hlr.status == "accepted"


def test_ascii_arrow_relationship_line_is_parsed():
    """``->`` and ``-->`` are accepted wherever the canonical ``→`` is.

    The exporter writes ``→``; hand-authored documents are frequently
    written with an ASCII arrow.  A line the importer cannot parse is a
    dropped traceability edge, so both spellings must produce the same
    reference.  The canonical export spelling is unchanged.
    """
    from codegraph.export.markdown import import_markdown
    from codegraph.identity import IdentityScope, identity_scope

    template = (
        "# codegraph: requirements\n\n"
        "## HLR: `REQ-001`\n"
        "The system shall provide the operation.\n"
        "- status: accepted\n"
        "### LLR: `REQ-001.1`\n"
        "The operation shall be implemented by the code under test.\n"
        "- status: accepted\n"
        "\n## Relationships\n"
        "- `REQ-001.1` {arrow} `p::C::m()` **realized_by** (MethodNode)\n"
    )
    references = {}
    for arrow in ("→", "->", "-->"):
        with identity_scope(
            IdentityScope.repository("requirements-tests", "fixture")
        ):
            graph = import_markdown(
                template.format(arrow=arrow),
                tags=frozenset({"requirements"}),
                source="fixture",
                strict=True,
            )
        llr = next(
            entry for entry in graph._all_entries()
            if type(entry.node).__name__ == "LLR"
        )
        references[arrow] = llr.references

    assert references["→"] == [("REALIZED_BY", "p::C::m()", "MethodNode")]
    assert references["->"] == references["→"]
    assert references["-->"] == references["→"]


def test_unparseable_relationship_line_is_an_error_not_a_silent_drop(tmp_path):
    """A bullet under ``## Relationships`` that cannot parse must not vanish.

    Such a line is an authored traceability edge.  Ignoring it shipped a graph
    with a missing requirement→code link and no diagnostic, so the importer
    reports an error: a strict import fails instead of losing the edge.
    """
    requirements_dir = tmp_path / "requirements"
    path = requirements_dir / "feature" / "requirements.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "# codegraph: requirements\n\n"
        "## HLR: `REQ-001`\n"
        "The system shall provide the operation.\n"
        "- status: accepted\n"
        "\n## Relationships\n"
        "- `REQ-001` → `REQ-001`\n",
        encoding="utf-8",
    )

    result = IndexService((EmptyAdapter(),)).index(
        _request(tmp_path, requirements_dir)
    )

    assert result.success is False
    assert "MALFORMED_REQUIREMENTS_DOCUMENT" in {
        diagnostic.code for diagnostic in result.diagnostics
    }


def test_prose_under_a_relationships_heading_is_not_an_error(tmp_path):
    """Only a relationship *attempt* is fatal; prose stays prose.

    The check is deliberately narrow — a bullet carrying backticked names —
    so documentation-style prose in a hand-written document does not fail
    the index run.
    """
    requirements_dir = tmp_path / "requirements"
    path = requirements_dir / "feature" / "requirements.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "# codegraph: requirements\n\n"
        "## HLR: `REQ-001`\n"
        "The system shall provide the operation.\n"
        "- status: accepted\n"
        "\n## Relationships\n"
        "Relationships are listed here once implemented.\n",
        encoding="utf-8",
    )

    result = IndexService((EmptyAdapter(),)).index(
        _request(tmp_path, requirements_dir)
    )

    assert result.success is True, [
        f"{d.code}: {d.message}" for d in result.diagnostics
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


def test_repository_requirements_use_reviewable_names_and_resolve_without_warnings(
    tmp_path,
):
    """The authoritative repository tree contains no legacy SHA-1 endpoints.

    Human-readable relationship targets are resolved to canonical keys during
    indexing.  Loading the complete tree is important because shared scaffold
    literals may be declared in a sibling authoritative document.
    """
    requirements_dir = Path(__file__).parents[2] / "codegraph" / "requirements"
    legacy_reference = re.compile(r"`[0-9a-f]{40}`")
    legacy_lines = [
        f"{path.relative_to(requirements_dir)}:{line_number}: {line}"
        for path in sorted(requirements_dir.rglob("requirements.md"))
        for line_number, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), start=1
        )
        if legacy_reference.search(line)
    ]
    assert not legacy_lines, "\n".join(legacy_lines)

    result = IndexService((EmptyAdapter(),)).index(
        _request(tmp_path, requirements_dir)
    )

    assert result.success is True
    assert result.diagnostics == ()
    references = [
        reference
        for entry in result.graph._all_entries()
        for reference in entry.references
    ]
    assert references
    assert all(target.startswith("cg:v1:") for _, target, _ in references)


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
