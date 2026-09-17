"""Tag-integrity tests for the doxygen-index dogfood graph.

Verifies the provenance-tag invariant that downstream consumers rely
on for the dogfood graph (this repository's own ``src`` + ``tests``).

The graph is single-*source* but two-*layer*: the project ``source``
label covers both the parser-owned ``as-built`` extraction layer and
the repository-authored requirements overlay that the unified index
operation ingests from ``requirements_dir`` (see
design_intent/14-prioritized-work-roadmap.md, Priority 4):

- Every node whose ``source`` is the project must carry either the
  ``as-built`` tag or an overlay tag (``requirements``, ``design``,
  ``scaffold``) — an untagged project node would be invisible to every
  tag-selected view, including ``LayerGraph.from_backend(...)``.
- Every node carrying the ``as-built`` tag must have the project
  ``source`` — there are no dependency sources in this graph, so the
  ``as-built`` tag must not leak outside the project (stronger than the
  cpp-sqlite suite, which must allow dependency-tagged one-hop
  neighbours).
- The two layers are disjoint and together account for exactly the
  project-source nodes.

These tests run against the fresh ingest produced by the
session-scoped ``codegraph_graph`` fixture, so they validate exactly
what the build writes to the backend (sqlite by default, Neo4j
opt-in via ``CODEGRAPH_BACKEND``).
"""

from __future__ import annotations

import pytest

from .artifacts import CODEGRAPH_ROOT, OVERLAY_TAGS, is_overlay

#: Source label the ingest assigns to the project's own code.  Derived
#: from the repo-root config name; must match what
#: ``tag_nodes_by_source`` uses as the project source.
PROJECT_SOURCE = CODEGRAPH_ROOT.name


class TestProvenanceTagIntegrity:
    """The ``source`` label, ``as-built`` and overlay tags agree.

    The dogfood graph has two provenance layers over one ``source``
    label.  Overlay membership is derived from the project-source nodes
    themselves, so the set algebra below never mixes in nodes loaded by
    a different fixture sharing the session backend.
    """

    @pytest.fixture(scope="class")
    def provenance_sets(self, codegraph_graph):
        """Query the backend directly.

        The session ``codegraph_graph`` fixture returns the *tagged*
        as-built LayerGraph — untagged project nodes never reach it —
        so the tag check must go to the repository API.
        """
        from codegraph import get_backend

        backend = get_backend()
        project_nodes = backend.graph.find_all_by_source(PROJECT_SOURCE)
        assert project_nodes, "expected project-source nodes after ingest"

        project_uids = {n.canonical_key for n in project_nodes}
        as_built_uids = set(backend.graph.find_uids_by_tag("as-built"))
        overlay_uids = {
            n.canonical_key for n in project_nodes if is_overlay(n)
        }
        assert as_built_uids, "expected as-built-tagged nodes after ingest"

        return project_uids, as_built_uids, overlay_uids

    def test_every_project_source_node_has_known_provenance(
        self, provenance_sets,
    ):
        """Every project-source node is either as-built or overlay.

        A project node with neither tag would exist in the backend but
        never appear in any tag-selected view — not the as-built graph,
        and not the requirements/design overlay either.
        """
        project_uids, as_built_uids, overlay_uids = provenance_sets
        unknown = project_uids - as_built_uids - overlay_uids
        assert not unknown, (
            f"{len(unknown)} project node(s) carry neither the as-built tag "
            f"nor an overlay tag {sorted(OVERLAY_TAGS)} — they would be "
            "invisible to every tag-selected view"
        )

    def test_all_as_built_tagged_nodes_have_project_source(
        self, provenance_sets,
    ):
        """Every ``as-built``-tagged node is project source.

        Unlike cpp-sqlite (whose one-hop view mixes in dependency-tagged
        neighbours), the dogfood graph is single-source — a non-project
        node carrying ``as-built`` would be a tagging leak.
        """
        project_uids, as_built_uids, _overlay_uids = provenance_sets
        leaked = as_built_uids - project_uids
        assert not leaked, (
            f"{len(leaked)} as-built-tagged nodes with non-project source"
        )

    def test_project_source_splits_into_as_built_and_overlay(
        self, provenance_sets,
    ):
        """The two layers are disjoint and exhaustive over the project.

        Every project node is exactly one of: parser-owned as-built
        fact, or durable overlay artifact.
        """
        project_uids, as_built_uids, overlay_uids = provenance_sets
        assert not (as_built_uids & overlay_uids), (
            "as-built and overlay provenance must be disjoint; "
            f"{len(as_built_uids & overlay_uids)} node(s) carry both"
        )
        assert project_uids == as_built_uids | overlay_uids, (
            f"project={len(project_uids)} vs as-built={len(as_built_uids)} "
            f"+ overlay={len(overlay_uids)} — the dogfood graph must "
            "contain no untagged and no non-project nodes"
        )

    def test_requirements_overlay_is_indexed(self, provenance_sets):
        """The unified index ingests ``requirements_dir`` into this graph.

        Pins the Priority 4 integration and keeps the provenance checks
        above honest: if the dogfood configuration stops ingesting its
        repository requirements, the overlay disappears and this fails
        instead of the split silently degenerating to as-built-only.
        """
        project_uids, _as_built_uids, overlay_uids = provenance_sets
        assert overlay_uids, (
            "no overlay nodes found — the dogfood index did not ingest "
            "requirements_dir (Priority 4)"
        )
        assert overlay_uids <= project_uids

    def test_serialized_fixture_carries_provenance_tags(
        self, codegraph_graph,
    ):
        """The serialized LayerGraph entries carry a provenance tag too."""
        serialized, uid_map = codegraph_graph
        for node in uid_map.values():
            tags = node.get("tags", [])
            assert "as-built" in tags or is_overlay(node), (
                f"entry carries no provenance tag: "
                f"{node.get('qualified_name')} tags={tags}"
            )
            assert "dependency" not in tags
