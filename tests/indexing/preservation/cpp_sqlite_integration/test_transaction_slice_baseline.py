"""WP5.0 — characterize the Priority 5 ``Transaction`` golden slice.

Plan: ``docs/plans/2026-09-16-priority-5-transaction-golden-slice.md``.

This module is the cheap, exact baseline taken *before* the slice grows
requirement, memory and evidence artifact types.  It freezes:

* the five real GoogleTests and their exact qualified names,
* the ``cpp_sqlite::Transaction`` class and selected member identities,
* every composed ``AssertionNode`` / ``TestStepNode`` key,
* the baseline assertion/step/``VERIFIES``/``CALLEE`` counts, and
* the exact core links from each test to the frozen Transaction members.

It reads the session-scoped ``codegraph_graph`` fixture — the shared
cpp-sqlite ingest owned by ``conftest.py`` — and never launches a second
index operation, mutates the fixture, or repairs the parser.  The real
parsed tests are the oracle; a failure here means the baseline changed,
not that the test should be relaxed.

The reusable view built here (:mod:`transaction_slice`) is what WP5.1+
rebind requirements, memories and evidence onto.
"""

from __future__ import annotations

import re

import pytest

from .artifacts import CODEGRAPH_ROOT
from .transaction_slice import (
    CORE_VERIFIES,
    REQUIRED_VERIFIES,
    SLICE_SOURCE_PATHS,
    TEST_BASELINES,
    TEST_QNS,
    TRANSACTION_CLASS_QN,
    TRANSACTION_HEADER,
    TRANSACTION_METHOD_QNS,
    TRANSACTION_TEST_SOURCE,
    SliceContractError,
    TransactionSlice,
    build_transaction_slice,
    node_map,
    outgoing_edges,
)

#: The table in the plan is reproduced here to make a drift visible in
#: the failure message rather than only in the assertion.
_PLAN_BASELINE_TABLE = (
    "TransactionCommit 8/6/10/6, TransactionRollback 4/4/8/8, "
    "TransactionAutoRollbackOnDestruction 1/2/6/5, "
    "NestedTransactionWithSavepoints 5/4/11/8, "
    "NestedTransactionRollbackInner 2/2/8/7"
)

#: Matches ``TEST_F(DatabaseTest, <Name>)`` regardless of inner spacing.
_TEST_F_RE = re.compile(r"^TEST_F\(\s*DatabaseTest\s*,\s*(\w+)\s*\)")


@pytest.fixture(scope="module")
def slice_(codegraph_graph) -> TransactionSlice:
    """The frozen slice, built once from the shared as-built graph."""
    serialized, _uid_map = codegraph_graph
    return build_transaction_slice(serialized)


def _source_lines(relative_path: str) -> list[str]:
    """Read a fixture source file relative to the repository root."""
    path = CODEGRAPH_ROOT / relative_path
    assert path.is_file(), f"slice source is missing on disk: {path}"
    return path.read_text(encoding="utf-8").splitlines()


def _collapse_whitespace(text: str) -> str:
    return re.sub(r"\s+", "", text)


def _prune_qualified_name(serialized, qualified_name: str) -> list[dict]:
    """Return a copy of *serialized* with one node removed from the tree."""
    pruned: list[dict] = []
    for node in serialized:
        if node.get("qualified_name") == qualified_name:
            continue
        clone = dict(node)
        clone["composes"] = _prune_qualified_name(
            node.get("composes") or (), qualified_name
        )
        pruned.append(clone)
    return pruned


def _assert_points_at_declaration(node: dict, relative_path: str) -> None:
    """Assert *node*'s line number lands on its own declaration.

    The extracted ``argsstring`` (whitespace-insensitive) must appear on
    the source line, which proves the node is a parsed source location
    rather than a synthesized one.
    """
    lines = _source_lines(relative_path)
    line_number = node.get("line_number")
    assert isinstance(line_number, int) and line_number > 0, (
        f"{node.get('qualified_name')!r} has no line number"
    )
    assert line_number <= len(lines), (
        f"{node.get('qualified_name')!r} line {line_number} is past the "
        f"end of {relative_path} ({len(lines)} lines)"
    )
    line = lines[line_number - 1]
    assert line.strip(), (
        f"{node.get('qualified_name')!r} points at a blank line "
        f"({relative_path}:{line_number})"
    )
    needle = _collapse_whitespace(node.get("argsstring") or "")
    if needle:
        assert needle in _collapse_whitespace(line), (
            f"{node.get('qualified_name')!r} does not point at its "
            f"declaration: {relative_path}:{line_number} is {line!r}"
        )


class TestFrozenIdentities:
    """WP5.0 steps 2–4: exact keys, qualified names, real source spans."""

    def test_five_real_tests_present_with_exact_qualified_names(
        self, slice_: TransactionSlice
    ):
        found = {
            slice_.nodes[key].get("qualified_name")
            for key in slice_.test_keys.values()
        }
        assert found == set(TEST_QNS.values())

    def test_selected_tests_are_parsed_as_built_nodes(
        self, slice_: TransactionSlice
    ):
        lines = _source_lines(TRANSACTION_TEST_SOURCE)
        for name, key in slice_.test_keys.items():
            node = slice_.nodes[key]
            assert node.get("kind") == "test", node.get("qualified_name")
            assert node.get("type") == "TestNode", node.get("qualified_name")
            assert node.get("source") == "cpp-sqlite"
            assert "as-built" in (node.get("tags") or [])
            assert node.get("test_name") == name
            assert node.get("test_module") == "testDatabase"
            assert node.get("method") == "automated"
            assert node.get("file_path") == TRANSACTION_TEST_SOURCE

            line_number = node["line_number"]
            assert 0 < line_number <= len(lines)
            match = _TEST_F_RE.match(lines[line_number - 1].strip())
            assert match and match.group(1) == name, (
                f"{node['qualified_name']} line {line_number} is not its "
                f"TEST_F declaration: {lines[line_number - 1]!r}"
            )

    def test_transaction_class_resolves_to_its_declaration(
        self, slice_: TransactionSlice
    ):
        node = slice_.nodes[slice_.class_key]
        assert node.get("kind") == "class"
        assert node.get("type") == "ClassNode"
        assert node.get("qualified_name") == TRANSACTION_CLASS_QN
        assert node.get("file_path") == TRANSACTION_HEADER
        lines = _source_lines(TRANSACTION_HEADER)
        line = lines[node["line_number"] - 1].strip()
        assert line.startswith("class Transaction"), line

    def test_transaction_members_are_composed_by_the_class(
        self, slice_: TransactionSlice
    ):
        class_node = slice_.nodes[slice_.class_key]
        composed = {
            child["canonical_key"] for child in (class_node.get("composes") or ())
        }
        missing = set(slice_.method_keys.values()) - composed
        assert not missing, (
            "Transaction members not composed by the class: "
            f"{sorted(missing)}"
        )

    def test_transaction_members_resolve_to_real_declarations(
        self, slice_: TransactionSlice
    ):
        for label, key in slice_.method_keys.items():
            node = slice_.nodes[key]
            assert node.get("kind") == "function", label
            assert node.get("type") == "MethodNode", label
            assert node.get("source") == "cpp-sqlite"
            assert node.get("file_path") == TRANSACTION_HEADER
            assert node.get("qualified_name") == TRANSACTION_METHOD_QNS[label]
            _assert_points_at_declaration(node, TRANSACTION_HEADER)
            # The declaration must sit inside the class body span.
            class_node = slice_.nodes[slice_.class_key]
            assert class_node["line_number"] < node["line_number"] <= (
                class_node["end_line"]
            ), label

    def test_implementation_bodies_are_present_for_out_of_line_members(
        self, slice_: TransactionSlice
    ):
        """Out-of-line members carry ``body_file``/``body_start``/
        ``body_end`` so the WP5.5 snapshot can assert implementation
        content without a second parse."""
        for label, key in slice_.method_keys.items():
            node = slice_.nodes[key]
            if label in {
                "copy_constructor_deleted",
                "copy_assignment_deleted",
            }:
                continue
            assert node.get("body_file"), f"{label} has no body_file"
            assert node.get("body_start", 0) > 0, label
            assert node.get("body_end", 0) >= node.get("body_start", 0), label

    def test_every_slice_key_is_a_versioned_canonical_key(
        self, slice_: TransactionSlice
    ):
        for key in slice_.canonical_keys():
            assert key.startswith("cg:v1:"), key
        assert len(slice_.canonical_keys()) == len(
            {key for key in slice_.canonical_keys()}
        )

    def test_real_source_files_exist_on_disk(self):
        for relative_path in SLICE_SOURCE_PATHS:
            assert (CODEGRAPH_ROOT / relative_path).is_file(), relative_path

    def test_slice_file_keys_point_at_the_defining_sources(
        self, slice_: TransactionSlice
    ):
        assert set(slice_.file_keys) >= set(SLICE_SOURCE_PATHS), (
            "the slice must retain every defining source; got "
            f"{sorted(slice_.file_keys)}"
        )


class TestBaselineCounts:
    """WP5.0 step 3: the plan's baseline table, exactly."""

    def test_assertion_and_step_counts_match_baseline(
        self, slice_: TransactionSlice
    ):
        for name, key in slice_.test_keys.items():
            children = [
                slice_.nodes[child_key]
                for child_key in slice_.child_keys[name]
            ]
            assertions = [c for c in children if c.get("kind") == "assertion"]
            steps = [c for c in children if c.get("kind") == "test_step"]
            baseline = TEST_BASELINES[name]
            assert len(assertions) == baseline.assertions, (
                f"{name}: {len(assertions)} assertions, expected "
                f"{baseline.assertions} ({_PLAN_BASELINE_TABLE})"
            )
            assert len(steps) == baseline.steps, (
                f"{name}: {len(steps)} steps, expected {baseline.steps} "
                f"({_PLAN_BASELINE_TABLE})"
            )
            assert len(slice_.child_keys[name]) == (
                baseline.assertions + baseline.steps
            ), name

    def test_verifies_and_callee_counts_match_baseline(
        self, slice_: TransactionSlice
    ):
        for name in slice_.test_keys:
            baseline = TEST_BASELINES[name]
            assert slice_.verifies_edge_count[name] == baseline.verifies, (
                f"{name}: {slice_.verifies_edge_count[name]} VERIFIES edges, "
                f"expected {baseline.verifies} ({_PLAN_BASELINE_TABLE})"
            )
            assert slice_.callee_edge_count[name] == baseline.callees, (
                f"{name}: {slice_.callee_edge_count[name]} CALLEE edges, "
                f"expected {baseline.callees} ({_PLAN_BASELINE_TABLE})"
            )

    def test_composed_children_are_unique_and_resolved(
        self, slice_: TransactionSlice
    ):
        for name, keys in slice_.child_keys.items():
            assert len(keys) == len(set(keys)), name
            assert set(keys) <= set(slice_.nodes), name

    def test_slice_internal_edges_have_present_endpoints(
        self, slice_: TransactionSlice
    ):
        unresolved = slice_.unresolved_edges()
        assert not unresolved, (
            f"{len(unresolved)} slice edges point at nodes that are absent "
            f"from the serialized graph: {sorted(unresolved)[:5]}"
        )


class TestCoreLinks:
    """WP5.0 step 5: the exact links from real tests to real members."""

    def test_real_tests_verify_exactly_the_frozen_member_set(
        self, slice_: TransactionSlice
    ):
        member_keys = set(slice_.method_keys.values())
        label_by_key = {
            key: label for label, key in slice_.method_keys.items()
        }
        for name in slice_.test_keys:
            actual = {
                label_by_key[target]
                for target in slice_.verifies_targets[name]
                if target in member_keys
            }
            assert actual == set(CORE_VERIFIES[name]), (
                f"{name} VERIFIES Transaction members {sorted(actual)}, "
                f"expected {sorted(CORE_VERIFIES[name])}"
            )

    def test_plan_named_core_links_are_present(self, slice_: TransactionSlice):
        for name, labels in REQUIRED_VERIFIES.items():
            source_key = slice_.test_key(name)
            for label in labels:
                assert (source_key, "VERIFIES", slice_.method_key(label)) in (
                    slice_.edges()
                ), f"{name} is missing VERIFIES -> {label}"

    def test_commit_test_verifies_commit(self, slice_: TransactionSlice):
        assert slice_.method_key("commit") in slice_.verifies_targets[
            "TransactionCommit"
        ]

    def test_rollback_test_verifies_rollback(self, slice_: TransactionSlice):
        assert slice_.method_key("rollback") in slice_.verifies_targets[
            "TransactionRollback"
        ]

    def test_savepoint_tests_verify_savepoint_methods(
        self, slice_: TransactionSlice
    ):
        outer = slice_.verifies_targets["NestedTransactionWithSavepoints"]
        assert slice_.method_key("is_savepoint") in outer
        assert slice_.method_key("get_savepoint_name") in outer
        assert slice_.method_key("commit") in outer

        inner = slice_.verifies_targets["NestedTransactionRollbackInner"]
        assert slice_.method_key("commit") in inner
        assert slice_.method_key("rollback") in inner

    def test_savepoint_steps_callee_the_savepoint_lifecycle(
        self, slice_: TransactionSlice
    ):
        """The savepoint tests' ``CALLEE`` edges reach the commit and
        rollback members through their steps."""
        assert slice_.method_key("commit") in slice_.callee_targets[
            "NestedTransactionWithSavepoints"
        ]
        inner_callees = slice_.callee_targets["NestedTransactionRollbackInner"]
        assert slice_.method_key("commit") in inner_callees
        assert slice_.method_key("rollback") in inner_callees


class TestKnownLimitation:
    """WP5.0 step 6: characterize — do not hide — the destructor gap.

    Source parsing cannot infer the implicit destructor call from scope
    exit, so ``TransactionAutoRollbackOnDestruction`` reaches neither
    ``~Transaction()`` nor the ``rollback()`` it invokes.  The gap is
    recorded here as a characterization.  It must never be "fixed" by
    fabricating a ``VERIFIES`` or ``CALLEE`` edge.
    """

    TEST_NAME = "TransactionAutoRollbackOnDestruction"

    def test_auto_rollback_test_has_no_destructor_edges(
        self, slice_: TransactionSlice
    ):
        destructor_key = slice_.method_key("destructor")
        rollback_key = slice_.method_key("rollback")
        assert destructor_key not in slice_.verifies_targets[self.TEST_NAME]
        assert rollback_key not in slice_.verifies_targets[self.TEST_NAME]
        assert destructor_key not in slice_.callee_targets[self.TEST_NAME]
        assert rollback_key not in slice_.callee_targets[self.TEST_NAME]

    def test_auto_rollback_action_block_calls_nothing(
        self, slice_: TransactionSlice
    ):
        test_key = slice_.test_key(self.TEST_NAME)
        blocks = [
            slice_.nodes[child_key]
            for child_key in slice_.child_keys[self.TEST_NAME]
            if slice_.nodes[child_key].get("kind") == "test_step"
        ]
        action_blocks = [
            block
            for block in blocks
            if (block.get("description") or "").startswith("Action block")
        ]
        assert action_blocks, "expected an Action block in the auto-rollback test"
        for block in action_blocks:
            assert not [
                edge
                for edge in outgoing_edges(block)
                if edge[0] == "CALLEE"
            ], (
                f"{block['qualified_name']} unexpectedly resolves a CALLEE; "
                "the scope-exit destructor call is not inferred today — do "
                "not fabricate the edge"
            )
        # The test node itself exists and is real; only the implicit
        # destructor link is missing.
        assert test_key in slice_.nodes

    def test_destructor_does_invoke_rollback(self, slice_: TransactionSlice):
        """The RAII chain is present in the code graph — it is only the
        test-to-destructor link that source parsing cannot infer."""
        destructor_key = slice_.method_key("destructor")
        rollback_key = slice_.method_key("rollback")
        assert (destructor_key, "INVOKES", rollback_key) in slice_.edges()

    def test_missing_link_is_not_compensated_by_requirement_reach(
        self, slice_: TransactionSlice
    ):
        """A test may reach the behavior only through the real graph.

        The auto-rollback test's member ``VERIFIES`` set is empty; the
        LLR authored in WP5.1 must therefore bind ``VERIFIED_BY`` to the
        test itself rather than inventing a code link.
        """
        member_keys = set(slice_.method_keys.values())
        assert not (slice_.verifies_targets[self.TEST_NAME] & member_keys)


class TestSliceContractHelper:
    """WP5.0 step 7: the shared contract later packages consume."""

    def test_helper_exposes_the_complete_key_set(
        self, slice_: TransactionSlice
    ):
        keys = slice_.canonical_keys()
        assert slice_.class_key in keys
        assert set(slice_.method_keys.values()) <= keys
        assert set(slice_.test_keys.values()) <= keys
        assert set(slice_.file_keys.values()) <= keys
        for name, children in slice_.child_keys.items():
            assert set(children) <= keys, name
        assert keys <= set(slice_.nodes)

    def test_helper_edge_classes_cover_the_core_links(
        self, slice_: TransactionSlice
    ):
        edges = slice_.edges()
        for name, labels in CORE_VERIFIES.items():
            source_key = slice_.test_key(name)
            for label in labels:
                assert (
                    source_key,
                    "VERIFIES",
                    slice_.method_key(label),
                ) in edges, f"{name} -> {label}"

    def test_helper_reports_observed_relation_classes(
        self, slice_: TransactionSlice
    ):
        observed = slice_.observed_relation_types
        assert observed["test"] >= {"VERIFIES", "DEFINED_IN"}
        assert observed["test_step"] >= {"CALLEE", "DEFINED_IN"}
        assert observed["assertion"] >= {"DEFINED_IN"}
        assert observed["class"] >= {"DEFINED_IN"}
        assert observed["function"] >= {"DEFINED_IN"}

    def test_helper_is_deterministic(self, codegraph_graph):
        serialized, _uid_map = codegraph_graph
        first = build_transaction_slice(serialized)
        second = build_transaction_slice(serialized)
        assert first.canonical_keys() == second.canonical_keys()
        assert first.edges() == second.edges()
        assert first.verifies_targets == second.verifies_targets
        assert first.callee_targets == second.callee_targets

    def test_missing_frozen_node_is_reported(self, codegraph_graph):
        serialized, _uid_map = codegraph_graph
        pruned = _prune_qualified_name(serialized, TRANSACTION_CLASS_QN)
        remaining = node_map(pruned)
        assert all(
            node.get("qualified_name") != TRANSACTION_CLASS_QN
            for node in remaining.values()
        ), "the class node is not nested in the serialized tree"
        with pytest.raises(SliceContractError, match="Transaction"):
            build_transaction_slice(pruned)

    def test_duplicate_canonical_nodes_are_rejected(self):
        node = {
            "canonical_key": "cg:v1:repository:x%2Fy:test:qualified_name=a",
            "kind": "test",
            "qualified_name": "a",
            "composes": [],
        }
        duplicate = {**node, "qualified_name": "b"}
        with pytest.raises(SliceContractError, match="duplicate canonical node"):
            node_map([node, duplicate])
