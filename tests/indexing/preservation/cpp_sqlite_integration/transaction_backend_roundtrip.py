"""Empty-backend persistence helpers for the WP5.5 fidelity proof.

Plan: ``docs/plans/2026-09-16-priority-5-transaction-golden-slice.md`` (WP5.5).

The slice document is written into a **brand-new** backend and read back
through backend-neutral repository APIs only:

===============================  =========================================
what the plan asks for           the API used
===============================  =========================================
persist to a new backend         ``Backend.bulk_save(graph)``
fetch every node by canonical    ``backend.graph.find_by_key(key)``
key
fetch every outgoing edge        ``Backend.get_all_edges_outgoing(node)``
node totals                      ``backend.graph.count_all_nodes(tag)``
key enumeration                  ``backend.graph.find_uids_by_tag(tag)``
relationship totals              ``backend.graph.count_relationships([...])``
===============================  =========================================

No SQL, no Cypher, no ``execute_raw``, no backend-specific attribute: the plan's
stop condition is a comparison that "uses raw backend SQL/Cypher".  A backend
that cannot answer one of those questions is recorded as unsupported by
:func:`require_contract` rather than worked around with raw queries.

The graph handed to :func:`graph_from_backend` is re-assembled from what the
backend *reports*, so the comparison in ``test_transaction_snapshot`` measures
persistence, not a copy of the in-memory object graph.  That re-assembly is the
only place layout is rebuilt; the normalization applied afterwards is the same
:func:`~.test_transaction_snapshot.normalized_model` the document side uses.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Sequence

from codegraph.backends.interface import Backend
from codegraph.graph import CompositeEntry, LayerGraph

#: Backend kinds the WP5.5 gate runs unconditionally.  ``neo4j`` is opt-in and
#: separately marked (plan step 8).
BACKEND_KINDS: tuple[str, ...] = ("sqlite_file", "sqlite_memory", "in_memory")

#: Opt-in parity kind; requires a reachable Neo4j.
NEO4J_KIND = "neo4j"

#: The provenance tag every slice node carries (extracted code/tests, authored
#: requirements, reviewed memories and reviewed evidence all include it).
SLICE_TAG = "as-built"

#: Credentials of the dedicated test container (mirror of
#: ``tests/backends/neo4j/conftest.py`` / ``tests/docker-compose.yml``).
NEO4J_URI = "bolt://localhost:7688"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "codegraph-test"


class BackendContractError(AssertionError):
    """A backend cannot carry the contract WP5.5 asserts against it."""


#: The provenance tags the slice is spread over.  Extracted code and tests and
#: the reviewed evidence carry ``as-built``; the authored requirements carry
#: ``requirements``.  A backend-neutral caller has no "give me every key" API
#: beyond counting, so enumeration goes tag by tag and the test proves the
#: union is the whole database.
SLICE_TAGS: tuple[str, ...] = ("as-built", "requirements")


def create_backend(kind: str, *, tmp_path: Path | None = None) -> Backend:
    """Return a brand-new, empty backend of *kind*.

    Every call builds a fresh instance, so a test can prove the persistence
    target really was empty before the slice was written to it.

    Raises:
        ValueError: for an unknown kind.
    """
    if kind in ("sqlite_file", "sqlite_memory"):
        from codegraph.backends.sqlite import SqliteBackend, SqliteConfig

        if kind == "sqlite_file":
            assert tmp_path is not None, "sqlite_file needs a tmp_path"
            path = str(Path(tmp_path) / "wp55_slice.sqlite3")
        else:
            path = ":memory:"
        config = SqliteConfig(path=path)
        backend = SqliteBackend(config)
        backend.initialize(config)
        return backend

    if kind == "in_memory":
        from codegraph.backends.memory import InMemoryBackend

        backend = InMemoryBackend()
        backend.initialize(None)
        return backend

    if kind == NEO4J_KIND:
        from codegraph.backends.neo4j import Neo4jBackend, Neo4jConfig

        config = Neo4jConfig(
            uri=NEO4J_URI, user=NEO4J_USER, password=NEO4J_PASSWORD
        )
        backend = Neo4jBackend(config)
        backend.initialize(config)
        return backend

    raise ValueError(f"unknown backend kind {kind!r}")


def require_contract(backend: Backend) -> None:
    """Fail clearly if *backend* cannot answer the questions WP5.5 asks.

    Called before a test asserts anything, so an unsupported backend is
    reported as "this backend does not carry the contract" instead of showing
    up as an unexplained difference in the comparison.
    """
    missing = [
        name
        for name in (
            "bulk_save",
            "get_all_edges_outgoing",
            "bulk_load_by_tag",
            "health_check",
        )
        if not callable(getattr(backend, name, None))
    ]
    repository = getattr(backend, "graph", None)
    if repository is None:
        missing.append("graph repository")
    else:
        missing += [
            f"graph.{name}"
            for name in ("find_by_key", "find_uids_by_tag", "count_all_nodes",
                         "count_relationships")
            if not callable(getattr(repository, name, None))
        ]
    if missing:
        raise BackendContractError(
            f"{type(backend).__name__} cannot carry the WP5.5 contract; "
            f"missing: {', '.join(missing)}"
        )


def graph_from_backend(
    backend: Backend,
    keys: Sequence[str],
    *,
    tags: frozenset[str] = frozenset({SLICE_TAG}),
) -> LayerGraph:
    """Rebuild a :class:`LayerGraph` from what *backend* reports.

    One :meth:`GraphRepository.find_by_key` per canonical key, one
    :meth:`Backend.get_all_edges_outgoing` per node.  ``COMPOSES`` edges become
    composition nesting (a node composed by several parents appears under each,
    as the flat document describes a DAG); every other edge becomes a reference
    with the relationship attributes the backend stored.

    Deliberately *not* reused here: :meth:`LayerGraph.from_backend`.  That
    loader is the visualization/export path — it drops ``ImplementationNode``
    and ``TEMPLATE_PARAM`` slots by design and prunes empty namespaces, so it
    cannot measure whether a backend kept the slice.
    """
    entries: dict[str, CompositeEntry] = {}
    for key in keys:
        node = backend.graph.find_by_key(key)
        assert node is not None, f"backend has no node for {key!r}"
        assert type(node) is not None
        entries[key] = CompositeEntry(node=node)

    child_keys: set[str] = set()
    for key, entry in entries.items():
        for edge in backend.get_all_edges_outgoing(entry.node):
            target_key = edge.target_key
            if not target_key:
                continue
            attrs = dict(getattr(edge, "attributes", None) or {})
            if edge.relation_type == "COMPOSES":
                child = entries.get(target_key)
                if child is None:
                    # A composition to a node the slice does not carry: keep it
                    # visible as a plain reference so the comparison reports it
                    # rather than nesting a phantom.
                    entry.references.append(
                        (edge.relation_type, target_key, edge.target_type)
                    )
                    if attrs:
                        entry.edge_attrs[(edge.relation_type, target_key)] = attrs
                    continue
                bucket = entry.children.setdefault(edge.target_type, {})
                if target_key in bucket and bucket[target_key] is child:
                    continue  # the same logical edge was already reported twice
                bucket[target_key] = child
                child_keys.add(target_key)
                continue
            entry.references.append(
                (edge.relation_type, target_key, edge.target_type)
            )
            if attrs:
                entry.edge_attrs[(edge.relation_type, target_key)] = attrs

    roots = {
        key: entry for key, entry in entries.items() if key not in child_keys
    }
    return LayerGraph(
        tags=tags,
        entries=roots,
        known_keys=frozenset(entries),
    )


def stored_keys(
    backend: Backend, tags: Sequence[str] = SLICE_TAGS
) -> set[str]:
    """Every canonical key the backend reports for *tags* (a union).

    ``GraphRepository`` enumerates keys per tag, so a slice that spans tags is
    enumerated per tag; the caller compares the union against
    ``count_all_nodes()`` to prove no node hides outside the tag filter.
    """
    keys: set[str] = set()
    for tag in tags:
        keys |= set(backend.graph.find_uids_by_tag(tag))
    return keys


def nodes_for(backend: Backend, keys: Iterable[str]) -> dict[str, object]:
    """``{canonical_key: node}`` fetched one key at a time."""
    found: dict[str, object] = {}
    for key in keys:
        node = backend.graph.find_by_key(key)
        if node is not None:
            found[key] = node
    return found


def edge_report(
    backend: Backend, keys: Sequence[str]
) -> dict[str, dict[tuple, dict]]:
    """``{source_key: {(relation, endpoint, target_type, field): attributes}}``.

    Exactly what :meth:`Backend.get_all_edges_outgoing` answers for each node —
    every relation type included, ``COMPOSES`` and ``HAS_IMPLEMENTATION`` too,
    with the relationship attributes as stored.  The document side builds the
    same shape from the wire edges, so the two are compared edge-for-edge
    rather than by count or digest.  ``field`` is always ``target_key``: a
    backend endpoint is a node it stores, named by its canonical key.
    """
    report: dict[str, dict[tuple, dict]] = {}
    for key in keys:
        node = backend.graph.find_by_key(key)
        assert node is not None, key
        edges: dict[tuple, dict] = {}
        for edge in backend.get_all_edges_outgoing(node):
            identity = (
                edge.relation_type,
                edge.target_key or "",
                edge.target_type or "",
                "target_key",
            )
            attrs = dict(getattr(edge, "attributes", None) or {})
            previous = edges.get(identity)
            if previous is not None and previous != attrs:
                raise BackendContractError(
                    f"{key} reports {identity} twice with different attributes"
                )
            edges[identity] = attrs
        report[key] = edges
    return report


def relationship_counts(
    backend: Backend, rel_types: Sequence[str]
) -> dict[str, int]:
    """``{relation_type: count}`` via the repository's own counting API."""
    return {
        rel_type: backend.graph.count_relationships([rel_type])
        for rel_type in rel_types
    }
