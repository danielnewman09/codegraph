"""Test memory drift detection tools."""

import pytest


@pytest.fixture
def drift_data(neo4j_connection):
    """Create test data for drift detection."""
    from codegraph_memory import DecisionNode, AssumptionNode
    from codegraph.models.compound import ClassNode

    # Code node with design tag
    cls = ClassNode.save_new(
        name="DriftTest", kind="class",
        qualified_name="test::DriftTest",
        tags=["design"], source="test",
    )

    # Decision linked to code (design-tagged)
    decision = DecisionNode.save_new(
        qualified_name="memory::test-drift-decision",
        name="Drift Decision",
        content="Use async processing.",
        tags=["design"], source="test",
    )
    decision.motivates_compound.connect(cls)

    # Low-confidence assumption
    low_conf = AssumptionNode.save_new(
        qualified_name="memory::test-drift-low-conf",
        name="Low Confidence",
        content="Assumes the queue is bounded.",
        tags=["design"], confidence=0.3, source="test",
    )
    low_conf.assumes_compound.connect(cls)

    # Orphan decision (no code links)
    DecisionNode.save_new(
        qualified_name="memory::test-drift-orphan",
        name="Orphan",
        content="Decision with no target.",
        tags=["design"], source="test",
    )

    return {"cls": cls, "decision": decision, "low_conf": low_conf}


class TestDriftDetection:
    """Test drift detection functions."""

    def test_detect_drift_finds_low_confidence(self, drift_data):
        """detect_drift finds low-confidence memories."""
        from codegraph_memory.lifecycle.drift import detect_drift

        findings = detect_drift("test")
        statuses = [f["status"] for f in findings]
        assert "confidence_stale" in statuses

    def test_detect_drift_finds_orphans(self, drift_data):
        """detect_drift finds orphan decisions."""
        from codegraph_memory.lifecycle.drift import detect_drift

        findings = detect_drift("test")
        statuses = [f["status"] for f in findings]
        assert "orphan" in statuses

    def test_find_orphan_decisions(self, drift_data):
        """find_orphan_decisions returns decisions without code links."""
        from codegraph_memory.lifecycle.drift import find_orphan_decisions

        orphans = find_orphan_decisions("test")
        qnames = [o["qualified_name"] for o in orphans]
        assert "memory::test-drift-orphan" in qnames

    def test_confidence_decay(self, drift_data):
        """confidence_decay reduces confidence on linked memories."""
        from codegraph_memory.lifecycle.drift import confidence_decay
        from codegraph_memory import AssumptionNode

        cls = drift_data["cls"]
        # Record original confidence
        original = AssumptionNode.nodes.get(
            qualified_name="memory::test-drift-low-conf"
        )
        original_conf = original.confidence

        count = confidence_decay(cls.canonical_key, decay_factor=0.5)
        assert count >= 1

        # Verify confidence was reduced
        updated = AssumptionNode.nodes.get(
            qualified_name="memory::test-drift-low-conf"
        )
        assert updated.confidence < original_conf