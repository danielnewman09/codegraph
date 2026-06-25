"""TestEnricher — LLM enrichment for TestNode descriptions.

Implements :class:`GraphEnricher` for test nodes.  Knows how to:

* Fetch TestNode's composed :class:`TestFixtureNode`,
  :class:`TestStepNode`, and :class:`AssertionNode` children from Neo4j
* Walk VERIFIES edges to find code-under-test context
* Build structured batch prompts with per-element-type guidance
* Query for all TestNodes (optionally filtered by tag)

Usage::

    from codegraph_enrich import TestEnricher

    enricher = TestEnricher()
    summary = enricher.enrich_one(test_node)
    print(summary.total_enriched)

    # Enrich all tests with the "as-built" tag:
    results = enricher.enrich_all(tag="as-built")
"""

from __future__ import annotations

import re
from typing import Any, TYPE_CHECKING

from codegraph_enrich.base import GraphEnricher

if TYPE_CHECKING:
    from codegraph.models.test import (
        TestNode,
        TestFixtureNode,
        TestStepNode,
        AssertionNode,
    )


# ══════════════════════════════════════════════════════════════════════════
# System prompt
# ══════════════════════════════════════════════════════════════════════════

_BATCH_SYSTEM_PROMPT = """\
You are a test metadata enrichment assistant. Your task is to generate
concise, human-readable descriptions for multiple test elements extracted
from a Python test suite. These descriptions bridge deterministic test
metadata and formal Low-Level Requirements (LLRs).

Guidelines:
- Write one or two sentences per element maximum.
- Focus on the *purpose* and *why* — not implementation syntax.
- Use clear, plain English suitable for non-developer stakeholders.
- Connect each element to the code under test when possible.
- For fixtures: what the variable represents and why it is needed.
- For steps: what action is performed and how it advances the test.
- For assertions: what condition is being verified and why it matters.

Response format — return ONLY a JSON object (no markdown, no explanation):

{
  "fully.qualified.name.1": "one or two sentence description",
  "fully.qualified.name.2": "one or two sentence description"
}"""


# ══════════════════════════════════════════════════════════════════════════
# Placeholder patterns (test-specific)
# ══════════════════════════════════════════════════════════════════════════

_PLACEHOLDER_PATTERNS = [
    re.compile(r"^Setup block$"),
    re.compile(r"^Action block \d+$"),
    re.compile(r"^assert .+$"),
]


# ══════════════════════════════════════════════════════════════════════════
# TestEnricher
# ══════════════════════════════════════════════════════════════════════════


class TestEnricher(GraphEnricher):
    """Enrich descriptions on test-related Neo4j nodes.

    One :class:`TestNode` at a time — fetches its fixtures, steps, and
    assertions, builds a batched prompt with peer context, calls the
    LLM, and saves updated descriptions.
    """

    __test__ = False  # prevent pytest collection

    # ------------------------------------------------------------------
    # System prompt
    # ------------------------------------------------------------------

    @property
    def system_prompt(self) -> str:
        return _BATCH_SYSTEM_PROMPT

    # ------------------------------------------------------------------
    # Placeholder detection (test-specific patterns)
    # ------------------------------------------------------------------

    @staticmethod
    def is_placeholder(desc: str) -> bool:
        """Check for test-specific placeholder descriptions.

        Extends the base (empty/whitespace check) with patterns for
        parser-generated labels like ``"Setup block"``,
        ``"Action block 3"``, and raw ``assert x == 1``.
        """
        if GraphEnricher.is_placeholder(desc):
            return True
        stripped = desc.strip()
        return any(p.match(stripped) for p in _PLACEHOLDER_PATTERNS)

    # ------------------------------------------------------------------
    # Neo4j fetchers
    # ------------------------------------------------------------------

    def _fetch_children(self, test_node: TestNode) -> dict[str, list]:
        """Fetch all composed children of a TestNode.

        Returns ``{"fixtures": [...], "steps": [...], "assertions": [...]}``.
        """
        children: dict[str, list] = {
            "fixtures": [],
            "steps": [],
            "assertions": [],
        }

        for rel_attr, key in [
            ("fixtures", "fixtures"),
            ("steps", "steps"),
            ("assertions", "assertions"),
        ]:
            mgr = getattr(test_node, rel_attr, None)
            if mgr is None:
                continue
            try:
                children[key] = list(mgr.all())
            except Exception:
                pass

        return children

    def _fetch_verifies(self, test_node: TestNode) -> list[dict]:
        """Collect all code nodes that this test VERIFIES.

        This is **not** part of the abstract interface — it is a
        TestEnricher-specific helper called from :meth:`_build_prompt`.

        Walks each typed ``verifies_*`` relationship manager on the
        TestNode.
        """
        targets: list[dict] = []

        for rel_attr, kind in [
            ("verifies_methods", "MethodNode"),
            ("verifies_functions", "FunctionNode"),
            ("verifies_classes", "ClassNode"),
            ("verifies_interfaces", "InterfaceNode"),
            ("verifies_enums", "EnumNode"),
            ("verifies_unions", "UnionNode"),
            ("verifies_modules", "ModuleNode"),
        ]:
            mgr = getattr(test_node, rel_attr, None)
            if mgr is None:
                continue
            try:
                for node in mgr.all():
                    qn = self.node_name(node)
                    desc = getattr(node, self.enrichment_field, "")
                    targets.append({
                        "qualified_name": qn,
                        "kind": kind,
                        "description": desc,
                    })
            except Exception:
                pass

        return targets

    def _find_targets(self, **filters) -> list:
        """Find all TestNodes, optionally filtered by tag.

        Keyword Args:
            tag: If provided, only return TestNodes whose ``tags``
                array contains this value (e.g. ``"as-built"``).
        """
        from codegraph.models.test import TestNode

        tag = filters.get("tag")
        if tag:
            return TestNode.fetch_by_tag(tag)
        return list(TestNode.nodes.all())

    # ------------------------------------------------------------------
    # Prompt builder — test-specific context
    # ------------------------------------------------------------------

    def _build_prompt(
        self,
        test_node: TestNode,
        all_children: dict[str, list],
        to_enrich: dict[str, list],
    ) -> str:
        """Build the batch user prompt for one TestNode.

        Includes test context, code-under-test, and per-element
        sections with peer context.
        """
        verifies = self._fetch_verifies(test_node)

        field_label = self.enrichment_field.capitalize()
        lines = [
            "Describe the test elements below. "
            "Respond with a JSON object mapping each qualified_name "
            f"to its {self.enrichment_field}:",
            "",
            "## Test Context",
            f"Test: {self.node_name(test_node)}",
            f"{field_label}: {getattr(test_node, self.enrichment_field, '') or '(none)'}",
            f"Module: {getattr(test_node, 'test_module', '') or '(unknown)'}",
            "",
        ]

        # Code under test
        if verifies:
            lines.append("Code under test (what this test exercises):")
            for v in verifies:
                lines.append(
                    f"  - {v['qualified_name']} ({v['kind']}): "
                    f"{v['description'] or '(no description)'}"
                )
            lines.append("")

        # Fixtures
        all_fixtures = all_children.get("fixtures", [])
        enrich_fixtures = to_enrich.get("fixtures", [])
        if enrich_fixtures:
            lines.append(f"## Fixtures ({len(enrich_fixtures)} to describe)")
            for i, fix in enumerate(enrich_fixtures):
                qn = self.node_name(fix)
                ctx = _build_fixture_context(fix, all_fixtures, field=self.enrichment_field)
                lines.append(f"### Fixture {i + 1}: {qn}")
                lines.append(ctx)
                lines.append("")
                lines.append(
                    f"Generate a concise description of fixture '{qn}': "
                    "what does it represent, why was it created, and how "
                    "does it relate to the code under test?"
                )
                lines.append("")

        # Steps
        all_steps = all_children.get("steps", [])
        enrich_steps = to_enrich.get("steps", [])
        if enrich_steps:
            lines.append(f"## Steps ({len(enrich_steps)} to describe)")
            for i, step in enumerate(enrich_steps):
                qn = self.node_name(step)
                ctx = _build_step_context(step, all_steps, field=self.enrichment_field)
                lines.append(f"### Step {i + 1}: {qn}")
                lines.append(ctx)
                lines.append("")
                lines.append(
                    f"Generate a concise description of step '{qn}': "
                    "what action does it perform, and how does it "
                    "advance the test toward verification?"
                )
                lines.append("")

        # Assertions
        all_assertions = all_children.get("assertions", [])
        enrich_assertions = to_enrich.get("assertions", [])
        if enrich_assertions:
            lines.append(
                f"## Assertions ({len(enrich_assertions)} to describe)"
            )
            for i, a in enumerate(enrich_assertions):
                qn = self.node_name(a)
                ctx = _build_assertion_context(a, all_assertions, field=self.enrichment_field)
                lines.append(f"### Assertion {i + 1}: {qn}")
                lines.append(ctx)
                lines.append("")
                lines.append(
                    f"Generate a concise description of assertion "
                    f"'{qn}': what condition does it verify, and why "
                    "does this condition matter to the correctness of "
                    "the code under test?"
                )
                lines.append("")

        # Footer with counts
        lines.append(
            f"({len(enrich_fixtures)} fixtures, {len(enrich_steps)} steps, "
            f"{len(enrich_assertions)} assertions)"
        )
        lines.append("Return the JSON object now:")
        return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════════
# Per-element context builders
# ══════════════════════════════════════════════════════════════════════════


def _build_fixture_context(
    fixture: TestFixtureNode,
    all_fixtures: list[TestFixtureNode],
    *,
    field: str = "description",
) -> str:
    """Build context lines for a single TestFixtureNode."""
    fixture_name = getattr(fixture, "name", "?")
    lines = [
        f"Type: {getattr(fixture, 'type_signature', '') or '(unspecified)'}",
        f"Current {field}: {getattr(fixture, field, '') or '(empty)'}",
    ]
    peers = [f for f in all_fixtures if getattr(f, "name", "") != fixture_name]
    if peers:
        lines.append("Other fixtures in this test:")
        for p in peers:
            p_name = getattr(p, "name", "?")
            p_type = getattr(p, "type_signature", "") or "?"
            p_desc = getattr(p, field, "") or "(not set)"
            lines.append(f"  - {p_name} ({p_type}): {p_desc}")
    return "\n".join(lines)


def _build_step_context(
    step: TestStepNode,
    all_steps: list[TestStepNode],
    *,
    field: str = "description",
) -> str:
    """Build context lines for a single TestStepNode."""
    lines = [
        f"Order: {getattr(step, 'order', '?')}",
        f"Current {field}: {getattr(step, field, '') or '(empty)'}",
    ]
    peers = [s for s in all_steps if getattr(s, "name", "") != getattr(step, "name", "")]
    if peers:
        lines.append("Other steps in this test:")
        for p in sorted(peers, key=lambda x: getattr(x, "order", 0)):
            lines.append(
                f"  - step {getattr(p, 'order', '?')}: "
                f"{getattr(p, 'name', '?')} — "
                f"{getattr(p, field, '') or '(not set)'}"
            )
    return "\n".join(lines)


def _build_assertion_context(
    assertion: AssertionNode,
    all_assertions: list[AssertionNode],
    *,
    field: str = "description",
) -> str:
    """Build context lines for a single AssertionNode."""
    lines = [
        f"Phase: {getattr(assertion, 'phase', 'post')}",
        f"Operator: {getattr(assertion, 'operator', '==')}",
        f"Order: {getattr(assertion, 'order', 0)}",
        f"Current {field}: {getattr(assertion, field, '') or '(empty)'}",
    ]
    peers = [
        a for a in all_assertions
        if getattr(a, "name", "") != getattr(assertion, "name", "")
    ]
    if peers:
        lines.append("Other assertions in this test:")
        for p in peers:
            lines.append(
                f"  - {getattr(p, 'name', '?')} "
                f"({getattr(p, 'phase', '?')} "
                f"{getattr(p, 'operator', '?')}): "
                f"{getattr(p, field, '') or '(not set)'}"
            )
    return "\n".join(lines)
