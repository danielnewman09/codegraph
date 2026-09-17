"""Frozen identity contract for the Priority 5 ``Transaction`` golden slice.

WP5.0 of ``docs/plans/2026-09-16-priority-5-transaction-golden-slice.md``
characterizes the as-built cpp-sqlite extraction for the five real
GoogleTests that make up the Transaction slice: their exact canonical
keys, the class/method identities they resolve to, their baseline
assertion/step/edge counts, and the cross-domain edge classes that later
packages (WP5.1 requirements, WP5.3 memories, WP5.4 evidence, WP5.5
snapshot) rebind onto.

The module deliberately performs **no backend access**: every helper
operates on the nested serialized ``LayerGraph`` returned by the
session-scoped ``codegraph_graph`` fixture, so each later package shares
one frozen, repository-reviewable view of the slice instead of
re-deriving it.

Nothing here may be relaxed to make a failing slice assertion pass: the
real parsed GoogleTests and their extracted children are the oracle.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterator, Mapping, Sequence

from codegraph.identity.encoding import KeyFormatError, parse_key

# ---------------------------------------------------------------------------
# Frozen identities (WP5.0 step 2)
# ---------------------------------------------------------------------------

#: The as-built class node that owns the whole slice.
TRANSACTION_CLASS_QN = "cpp_sqlite::Transaction"

#: Selected members named by the frozen scope.  ``constructor``,
#: ``destructor``, the move operations, the query helpers and
#: ``executeSQL`` are the implementation surface of the slice; the two
#: ``=delete`` copy operations are retained because the WP5.3 RAII
#: "move-only" memory explains them.
TRANSACTION_METHOD_QNS: Mapping[str, str] = {
    "constructor": "cpp_sqlite::Transaction::Transaction(Database &db)",
    "destructor": "cpp_sqlite::Transaction::~Transaction(())",
    "move_constructor": (
        "cpp_sqlite::Transaction::Transaction((Transaction &&other))"
    ),
    "move_assignment": (
        "cpp_sqlite::Transaction::operator=((Transaction &&other))"
    ),
    "copy_constructor_deleted": (
        "cpp_sqlite::Transaction::Transaction((const Transaction &)=delete)"
    ),
    "copy_assignment_deleted": (
        "cpp_sqlite::Transaction::operator=((const Transaction &)=delete)"
    ),
    "commit": "cpp_sqlite::Transaction::commit()",
    "rollback": "cpp_sqlite::Transaction::rollback()",
    "is_active": "cpp_sqlite::Transaction::isActive(() const)",
    "is_savepoint": "cpp_sqlite::Transaction::isSavepoint(() const)",
    "get_savepoint_name": (
        "cpp_sqlite::Transaction::getSavepointName(() const)"
    ),
    "execute_sql": (
        "cpp_sqlite::Transaction::executeSQL(const std::string &sql)"
    ),
}

#: The five real GoogleTests, keyed by short test name.
TEST_QNS: Mapping[str, str] = {
    "TransactionCommit": (
        "testDatabase::DatabaseTest::TransactionCommit"
    ),
    "TransactionRollback": (
        "testDatabase::DatabaseTest::TransactionRollback"
    ),
    "TransactionAutoRollbackOnDestruction": (
        "testDatabase::DatabaseTest::TransactionAutoRollbackOnDestruction"
    ),
    "NestedTransactionWithSavepoints": (
        "testDatabase::DatabaseTest::NestedTransactionWithSavepoints"
    ),
    "NestedTransactionRollbackInner": (
        "testDatabase::DatabaseTest::NestedTransactionRollbackInner"
    ),
}

#: Repository-relative source paths that define the slice.  They are
#: asserted to exist on disk so "real file path" cannot decay into a
#: string-only check.
TRANSACTION_HEADER = (
    "tests/indexing/preservation/fixtures/cpp-sqlite/cpp_sqlite/src/"
    "cpp_sqlite/DBTransaction.hpp"
)
TRANSACTION_SOURCE = (
    "tests/indexing/preservation/fixtures/cpp-sqlite/cpp_sqlite/src/"
    "cpp_sqlite/DBTransaction.cpp"
)
TRANSACTION_TEST_SOURCE = (
    "tests/indexing/preservation/fixtures/cpp-sqlite/cpp_sqlite/test/"
    "testDatabase.cpp"
)

#: Every repository-relative source file that defines or observes the
#: slice.  The header declares the class and its members; the source
#: holds the out-of-line bodies; the test source holds the five tests.
SLICE_SOURCE_PATHS: tuple[str, ...] = (
    TRANSACTION_HEADER,
    TRANSACTION_SOURCE,
    TRANSACTION_TEST_SOURCE,
)


@dataclass(frozen=True)
class TestBaseline:
    """Characterized child/edge counts for one real GoogleTest."""

    assertions: int
    steps: int
    verifies: int
    callees: int


#: Baseline counts from the plan's "Existing baseline" table.  These are
#: properties of the current parser + fixture and must not be adjusted to
#: accommodate a parser or fixture change.
TEST_BASELINES: Mapping[str, TestBaseline] = {
    "TransactionCommit": TestBaseline(8, 6, 10, 6),
    "TransactionRollback": TestBaseline(4, 4, 8, 8),
    "TransactionAutoRollbackOnDestruction": TestBaseline(1, 2, 6, 5),
    "NestedTransactionWithSavepoints": TestBaseline(5, 4, 11, 8),
    "NestedTransactionRollbackInner": TestBaseline(2, 2, 8, 7),
}

#: The exact set of frozen Transaction members each real test
#: ``VERIFIES`` (the "core links" of WP5.0 step 5).  Values are
#: :data:`TRANSACTION_METHOD_QNS` labels, not qualified names, so the
#: contract reads against the plan's wording.  The mapping is
#: *characterization*: it records what the current extraction produces
#: and may only change with an approved plan change.
CORE_VERIFIES: Mapping[str, frozenset[str]] = {
    "TransactionCommit": frozenset({"commit", "is_active", "is_savepoint"}),
    "TransactionRollback": frozenset({"rollback", "is_active"}),
    "TransactionAutoRollbackOnDestruction": frozenset(),
    "NestedTransactionWithSavepoints": frozenset(
        {"commit", "is_savepoint", "get_savepoint_name"}
    ),
    "NestedTransactionRollbackInner": frozenset({"commit", "rollback"}),
}

#: The minimum links the plan names explicitly (WP5.0 step 5): the
#: commit test reaches ``commit()``, the rollback test reaches
#: ``rollback()``, and each savepoint test reaches the savepoint
#: query/commit/rollback methods it actually exercises.  Always a subset
#: of :data:`CORE_VERIFIES`; asserted separately so a regression names
#: the plan-level link rather than the whole diff.
REQUIRED_VERIFIES: Mapping[str, frozenset[str]] = {
    "TransactionCommit": frozenset({"commit"}),
    "TransactionRollback": frozenset({"rollback"}),
    "TransactionAutoRollbackOnDestruction": frozenset(),
    "NestedTransactionWithSavepoints": frozenset(
        {"commit", "is_savepoint", "get_savepoint_name"}
    ),
    "NestedTransactionRollbackInner": frozenset({"commit", "rollback"}),
}


class SliceContractError(AssertionError):
    """Raised when the serialized graph does not match the frozen slice."""


# ---------------------------------------------------------------------------
# Serialized-graph access helpers
# ---------------------------------------------------------------------------


def iter_nodes(serialized: Sequence[dict]) -> Iterator[dict]:
    """Yield every node in a nested serialized ``LayerGraph`` once.

    ``LayerGraph.serialize`` folds ``COMPOSES`` into a nested
    ``composes`` tree, so children are not top-level entries.  This walks
    the whole tree; a node reachable through two parents is yielded twice
    (see :func:`node_map`, which rejects that as a canonical-identity
    violation).
    """
    stack = list(serialized)
    while stack:
        node = stack.pop()
        yield node
        stack.extend(node.get("composes") or ())


def node_map(serialized: Sequence[dict]) -> dict[str, dict]:
    """Return ``{canonical_key: node}`` for a serialized graph.

    Raises:
        SliceContractError: if two *different* node records share one
            canonical key.  A snapshot must contain each canonical node
            exactly once.
    """
    by_key: dict[str, dict] = {}
    for node in iter_nodes(serialized):
        key = node.get("canonical_key")
        if not key:
            raise SliceContractError(
                f"node without canonical_key: {node.get('qualified_name')!r}"
            )
        existing = by_key.get(key)
        if existing is not None and existing is not node:
            raise SliceContractError(
                f"duplicate canonical node {key!r} "
                f"({existing.get('qualified_name')!r} vs "
                f"{node.get('qualified_name')!r})"
            )
        by_key[key] = node
    return by_key


def index_by_qualified_name(nodes: Mapping[str, dict]) -> dict[str, dict]:
    """Return ``{qualified_name: node}`` for named nodes."""
    index: dict[str, dict] = {}
    for node in nodes.values():
        qn = node.get("qualified_name")
        if qn:
            index.setdefault(qn, node)
    return index


def outgoing_edges(node: Mapping[str, Any]) -> tuple[tuple[str, str], ...]:
    """Return ``(relation_type, target_key)`` pairs for *node*'s edges."""
    return tuple(
        (edge["relation_type"], edge["target_key"])
        for edge in (node.get("edges") or ())
    )


def relation_types(node: Mapping[str, Any]) -> frozenset[str]:
    """Return the set of relation types leaving *node*."""
    return frozenset(
        edge["relation_type"] for edge in (node.get("edges") or ())
    )


def edge_targets(
    nodes: Mapping[str, dict],
    source_key: str,
    relation_type: str,
) -> frozenset[str]:
    """Return the target keys of ``source_key -[relation_type]-> ?``."""
    node = nodes[source_key]
    return frozenset(
        target
        for relation, target in outgoing_edges(node)
        if relation == relation_type
    )


def repository_path_for_file_key(key: str) -> str:
    """Decode a ``file`` node's canonical key to its repository path.

    Uses the canonical key parser rather than ad-hoc percent decoding so
    the slice reads the same identity grammar the indexer wrote.

    Raises:
        SliceContractError: if *key* is not a decodable file key.
    """
    try:
        parsed = parse_key(key)
    except KeyFormatError as exc:  # pragma: no cover - defensive
        raise SliceContractError(f"undecodable file key {key!r}: {exc}") from exc
    fields = parsed.field_map()
    path = fields.get("normalized_repository_path")
    if parsed.category != "file" or path is None:
        raise SliceContractError(
            f"not a file key: {key!r} (category={parsed.category!r})"
        )
    return path


# ---------------------------------------------------------------------------
# The frozen slice
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TransactionSlice:
    """Canonical-key set, edge classes and baseline of the golden slice.

    Instances are built from one serialized as-built graph and are the
    shared input for every later Priority 5 package.
    """

    nodes: Mapping[str, dict]
    class_key: str
    method_keys: Mapping[str, str]
    test_keys: Mapping[str, str]
    child_keys: Mapping[str, tuple[str, ...]]
    file_keys: Mapping[str, str]
    verifies_targets: Mapping[str, frozenset[str]]
    callee_targets: Mapping[str, frozenset[str]]
    verifies_edge_count: Mapping[str, int]
    callee_edge_count: Mapping[str, int]
    observed_relation_types: Mapping[str, frozenset[str]] = field(
        default_factory=dict
    )

    # -- convenience -------------------------------------------------------

    def key(self, qualified_name: str) -> str:
        """Return the canonical key for *qualified_name* in this slice."""
        for mapping in (self.method_keys, self.test_keys):
            for key in mapping.values():
                if self.nodes[key].get("qualified_name") == qualified_name:
                    return key
        raise KeyError(qualified_name)

    def method_key(self, label: str) -> str:
        """Canonical key of the frozen Transaction member *label*."""
        return self.method_keys[label]

    def test_key(self, name: str) -> str:
        """Canonical key of the real GoogleTest named *name*."""
        return self.test_keys[name]

    def canonical_keys(self) -> frozenset[str]:
        """Every canonical key owned by the slice (class, members, tests,
        their composed children, and the defining files)."""
        keys: set[str] = {self.class_key}
        keys.update(self.method_keys.values())
        keys.update(self.test_keys.values())
        keys.update(self.file_keys.values())
        for children in self.child_keys.values():
            keys.update(children)
        return frozenset(keys)

    def edges(self) -> frozenset[tuple[str, str, str]]:
        """Every ``(source_key, relation_type, target_key)`` triple whose
        source is a slice node and whose target is also in the slice."""
        keys = self.canonical_keys()
        triples: set[tuple[str, str, str]] = set()
        for source_key in keys:
            for relation, target in outgoing_edges(self.nodes[source_key]):
                triples.add((source_key, relation, target))
        return frozenset(triples)

    def unresolved_edges(self) -> frozenset[tuple[str, str, str]]:
        """Slice edges whose target is absent from the serialized graph."""
        keys = self.canonical_keys()
        missing: set[tuple[str, str, str]] = set()
        for source_key in keys:
            for relation, target in outgoing_edges(self.nodes[source_key]):
                if target not in self.nodes:
                    missing.add((source_key, relation, target))
        return frozenset(missing)


def build_transaction_slice(serialized: Sequence[dict]) -> TransactionSlice:
    """Build the frozen :class:`TransactionSlice` from a serialized graph.

    Raises:
        SliceContractError: if any frozen identity is missing, duplicated,
            or carries a non-``cg:v1`` canonical key.
    """
    nodes = node_map(serialized)
    by_qn = index_by_qualified_name(nodes)

    def require(qn: str) -> dict:
        node = by_qn.get(qn)
        if node is None:
            raise SliceContractError(
                f"frozen slice node is missing from the graph: {qn!r}"
            )
        key = node["canonical_key"]
        if not key.startswith("cg:v1:"):
            raise SliceContractError(
                f"frozen slice node {qn!r} has a non-canonical key: {key!r}"
            )
        return node

    class_node = require(TRANSACTION_CLASS_QN)
    method_keys = {
        label: require(qn)["canonical_key"]
        for label, qn in TRANSACTION_METHOD_QNS.items()
    }
    test_keys = {
        name: require(qn)["canonical_key"]
        for name, qn in TEST_QNS.items()
    }

    child_keys: dict[str, tuple[str, ...]] = {}
    for name, key in test_keys.items():
        child_keys[name] = tuple(
            child["canonical_key"] for child in (nodes[key].get("composes") or ())
        )

    # File nodes: the keys the slice's nodes point at via DEFINED_IN,
    # plus the known defining sources.  DEFINED_IN always resolves to the
    # declaration file (the header), so the out-of-line ``.cpp`` that
    # holds the bodies is added from the file nodes themselves.  The
    # slice never invents a file identity.
    file_keys: dict[str, str] = {}
    for key in (
        class_node["canonical_key"],
        *method_keys.values(),
        *test_keys.values(),
    ):
        for relation, target in outgoing_edges(nodes[key]):
            if relation != "DEFINED_IN":
                continue
            target_node = nodes.get(target)
            if target_node is None or target_node.get("kind") != "file":
                continue
            file_keys.setdefault(
                repository_path_for_file_key(target), target
            )
    for key, node in nodes.items():
        if node.get("kind") != "file":
            continue
        try:
            path = repository_path_for_file_key(key)
        except SliceContractError:  # pragma: no cover - defensive
            continue
        if path in SLICE_SOURCE_PATHS:
            file_keys.setdefault(path, key)

    verifies_targets = {
        name: edge_targets(nodes, key, "VERIFIES")
        for name, key in test_keys.items()
    }
    verifies_edge_count = {
        name: sum(
            1
            for relation, _ in outgoing_edges(nodes[key])
            if relation == "VERIFIES"
        )
        for name, key in test_keys.items()
    }
    callee_targets: dict[str, frozenset[str]] = {}
    callee_edge_count: dict[str, int] = {}
    for name, key in test_keys.items():
        targets: set[str] = set()
        edges = 0
        for child_key in child_keys[name]:
            targets |= edge_targets(nodes, child_key, "CALLEE")
            edges += sum(
                1
                for relation, _ in outgoing_edges(nodes[child_key])
                if relation == "CALLEE"
            )
        callee_targets[name] = frozenset(targets)
        callee_edge_count[name] = edges

    observed: dict[str, frozenset[str]] = {}
    for key in (
        class_node["canonical_key"],
        *method_keys.values(),
        *test_keys.values(),
        *(c for children in child_keys.values() for c in children),
    ):
        observed.setdefault(nodes[key].get("kind", ""), frozenset())
        observed[nodes[key].get("kind", "")] = (
            observed[nodes[key].get("kind", "")] | relation_types(nodes[key])
        )

    return TransactionSlice(
        nodes=nodes,
        class_key=class_node["canonical_key"],
        method_keys=method_keys,
        test_keys=test_keys,
        child_keys=child_keys,
        file_keys=file_keys,
        verifies_targets=verifies_targets,
        callee_targets=callee_targets,
        verifies_edge_count=verifies_edge_count,
        callee_edge_count=callee_edge_count,
        observed_relation_types=observed,
    )
