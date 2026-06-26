"""LLRMiner — mines low-level requirements from test evidence.

For each compound (class, interface, enum) that has tests, gathers all
test context (descriptions, steps, assertions, fixtures) and sends it to
an LLM to infer low-level requirements.  Each LLR is traced to the
specific tests that verify it.

Usage::

    from codegraph_mine import LLRMiner

    miner = LLRMiner()
    results = miner.mine_all(tag="as-built")

    # Or mine a single compound:
    from codegraph.models.compound import ClassNode
    node = ClassNode.nodes.get(qualified_name="codegraph.models.compound.ClassNode")
    result = miner.mine_one(node)

Graph output::

    HLR -[:COMPOSES]-> LLR -[:COMPOSES]-> TestNode
    HLR -[:COMPOSES]-> CompoundNode
"""

from __future__ import annotations

from typing import Any

from codegraph_mine.base import RequirementMiner, MineResult
from codegraph_mine.schemas import MinedRequirements
from codegraph_mine.persistence import persist_mined_requirements


# ══════════════════════════════════════════════════════════════════════════
# System prompt
# ══════════════════════════════════════════════════════════════════════════

_MINING_SYSTEM_PROMPT = """\
You are a requirements engineer. Your task is to analyze existing test
evidence and infer low-level requirements (LLRs) for a software component.

Guidelines:
- Each LLR should be a **testable, specific requirement** — one or two
  sentences describing what the system shall do.
- Infer requirements from the *purpose* of each test: what behavior is
  being verified, what conditions matter, what actions are performed.
- Group related tests under the same LLR when they verify the same
  aspect of behavior (e.g., serialization tests, relationship tests).
- Each test should be assigned to exactly one LLR.
- Write requirements in clear, plain English suitable for non-developer
  stakeholders.  Use "The system shall..." or "The <component> shall..."
  phrasing.
- For the HLR, write one sentence that summarises the overall purpose
  of the component based on what all the tests collectively verify.

Response format — return ONLY a JSON object (no markdown, no explanation):

{
  "hlr_description": "The ClassNode system shall provide a complete data model for representing program classes including their members, relationships, serialization, and persistence lifecycle.",
  "llrs": [
    {
      "description": "The ClassNode shall support serialization of its composed methods and attributes so that roundtrip fidelity is maintained.",
      "verified_by": [
        "compound.test_class_composes_method.test_class_composes_method",
        "compound.test_class_composes_attribute.test_class_composes_attribute"
      ]
    },
    ...
  ]
}

IMPORTANT:
- Every test in the input MUST appear in exactly one LLR's `verified_by` list.
- Use the exact qualified_name strings as provided — do not modify them.
- Do not invent tests that aren't in the input.
"""


# ══════════════════════════════════════════════════════════════════════════
# LLRMiner
# ══════════════════════════════════════════════════════════════════════════


class LLRMiner(RequirementMiner):
    """Mine low-level requirements from test evidence for code compounds.

    Finds all compounds (classes, interfaces, enums) that have tests
    verifying them, gathers test context, and sends it to an LLM to
    infer LLRs.

    One LLM call per compound — tests are batched into a single prompt
    with their descriptions, steps, assertions, and fixtures.
    """

    __test__ = False  # prevent pytest collection

    # ------------------------------------------------------------------
    # System prompt
    # ------------------------------------------------------------------

    @property
    def system_prompt(self) -> str:
        return _MINING_SYSTEM_PROMPT

    # ------------------------------------------------------------------
    # Target discovery
    # ------------------------------------------------------------------

    def _find_targets(self, **filters) -> list:
        """Find all CompoundNodes that have tests verifying them.

        Walks VERIFIES edges in reverse: for each TestNode, find
        the compounds (classes, interfaces, enums) that it verifies,
        deduplicate, and return the distinct set.

        This uses neomodel relationship traversal rather than raw
        Cypher to avoid label-guessing.  Mining is a one-time operation
        so the N+1 query cost (one per TestNode) is acceptable.

        Keyword Args:
            tag: If provided, only consider TestNodes with this tag
                (e.g. ``"as-built"``).

        Returns:
            List of unique compound neomodel instances.
        """
        from codegraph.models.test import TestNode
        from codegraph.models.compound import ClassNode, InterfaceNode, EnumNode

        tag = filters.get("tag")

        # Collect all TestNodes
        if tag:
            test_nodes = TestNode.fetch_by_tag(tag)
        else:
            test_nodes = list(TestNode.nodes.all())

        # Collect all compound nodes that these tests verify
        seen: set[str] = set()
        compounds: list = []

        for test_node in test_nodes:
            for rel_attr in [
                "verifies_classes",
                "verifies_interfaces",
                "verifies_enums",
            ]:
                mgr = getattr(test_node, rel_attr, None)
                if mgr is None:
                    continue
                try:
                    for node in mgr.all():
                        uid = getattr(node, "uid", None)
                        if uid and uid not in seen:
                            seen.add(uid)
                            compounds.append(node)
                except Exception:
                    pass

        return compounds

    # ------------------------------------------------------------------
    # Context fetching
    # ------------------------------------------------------------------

    def _fetch_context(self, target) -> dict:
        """Fetch all test context for one compound.

        Returns a dict with:

        - ``"compound_name"``: The compound's qualified_name.
        - ``"compound_description"``: Any existing description.
        - ``"tests"``: List of test dicts, each with:
          - ``qualified_name``, ``test_name``, ``test_module``,
            ``description``
          - ``verifies``: list of {qualified_name, kind} dicts
          - ``steps``: list of step dicts with ``qualified_name``,
            ``description``, ``callees``
          - ``assertions``: list of assertion dicts with
            ``qualified_name``, ``description``, ``phase``,
            ``operator``
          - ``fixtures``: list of fixture dicts with
            ``qualified_name``, ``name``, ``description``,
            ``type_signature``
        """
        from codegraph.models.test import TestNode

        compound_name = self.node_name(target)
        compound_desc = getattr(target, "description", "") or ""

        # Find all TestNodes that VERIFIES this compound
        tests_context: list[dict] = []

        # Walk all verifies_* relationships in reverse by querying
        # TestNodes that have a VERIFIES edge to this compound
        test_nodes = self._find_tests_for_compound(target)

        for test_node in test_nodes:
            test_dict = self._build_test_dict(test_node)
            tests_context.append(test_dict)

        return {
            "compound_name": compound_name,
            "compound_description": compound_desc,
            "compound_kind": getattr(target, "kind", "class"),
            "tests": tests_context,
        }

    def _find_tests_for_compound(self, compound) -> list:
        """Find all TestNodes that verify this compound via VERIFIES edges.

        Uses raw Cypher for the reverse-lookup (compound → tests) since
        the compound models don't carry a ``verified_by`` relationship
        manager.
        """
        from neomodel import db
        from codegraph.models.test import TestNode

        compound_element_id = None
        try:
            compound_element_id = db.parse_element_id(compound.element_id)
        except Exception:
            pass

        if compound_element_id is None:
            return []

        # neomodel labels: TestNode for test nodes,
        # ClassNode/InterfaceNode/EnumNode for compounds
        query = """
        MATCH (t:TestNode)-[:VERIFIES]->(c)
        WHERE elementId(c) = $compound_id
        RETURN t
        """
        try:
            results, _ = db.cypher_query(
                query, {"compound_id": compound_element_id}
            )
        except Exception:
            return []

        tests: list = []
        for row in results:
            node = TestNode.inflate(row[0])
            tests.append(node)
        return tests

    def _build_test_dict(self, test_node) -> dict:
        """Build a dict of test context from a TestNode neomodel instance."""
        qn = self.node_name(test_node)

        # Gather VERIFIES targets
        verifies = []
        for rel_attr, kind in [
            ("verifies_methods", "method"),
            ("verifies_functions", "function"),
            ("verifies_classes", "class"),
            ("verifies_interfaces", "interface"),
            ("verifies_enums", "enum"),
            ("verifies_unions", "union"),
            ("verifies_modules", "module"),
        ]:
            mgr = getattr(test_node, rel_attr, None)
            if mgr is None:
                continue
            try:
                for node in mgr.all():
                    verifies.append({
                        "qualified_name": self.node_name(node),
                        "kind": kind,
                    })
            except Exception:
                pass

        # Gather steps
        steps = []
        try:
            for step in test_node.steps.all():
                step_dict = {
                    "qualified_name": self.node_name(step),
                    "order": getattr(step, "order", 0),
                    "description": getattr(step, "description", "") or "",
                }
                # Gather callees for each step
                callees = []
                for callee_rel, callee_kind in [
                    ("callee_method", "method"),
                    ("callee_function", "function"),
                    ("callee_class", "class"),
                ]:
                    mgr = getattr(step, callee_rel, None)
                    if mgr is None:
                        continue
                    try:
                        for c in mgr.all():
                            callees.append({
                                "qualified_name": self.node_name(c),
                                "kind": callee_kind,
                            })
                    except Exception:
                        pass
                step_dict["callees"] = callees
                steps.append(step_dict)
        except Exception:
            pass

        # Gather assertions
        assertions = []
        try:
            for a in test_node.assertions.all():
                assertions.append({
                    "qualified_name": self.node_name(a),
                    "description": getattr(a, "description", "") or "",
                    "phase": getattr(a, "phase", "post"),
                    "operator": getattr(a, "operator", "=="),
                    "order": getattr(a, "order", 0),
                })
        except Exception:
            pass

        # Gather fixtures
        fixtures = []
        try:
            for f in test_node.fixtures.all():
                fixtures.append({
                    "qualified_name": self.node_name(f),
                    "name": getattr(f, "name", ""),
                    "description": getattr(f, "description", "") or "",
                    "type_signature": getattr(f, "type_signature", "") or "",
                })
        except Exception:
            pass

        return {
            "qualified_name": qn,
            "test_name": getattr(test_node, "test_name", ""),
            "test_module": getattr(test_node, "test_module", ""),
            "description": getattr(test_node, "description", "") or "",
            "verifies": verifies,
            "steps": steps,
            "assertions": assertions,
            "fixtures": fixtures,
        }

    # ------------------------------------------------------------------
    # Prompt builder
    # ------------------------------------------------------------------

    def _build_prompt(
        self,
        target,
        context: dict,
    ) -> str:
        """Build the batch user prompt for one compound.

        Includes the compound identity, then one section per test with
        its description, verifies targets, steps, assertions, and
        fixtures.
        """
        compound_name = context["compound_name"]
        compound_desc = context.get("compound_description", "")
        compound_kind = context.get("compound_kind", "class")
        tests = context.get("tests", [])

        lines = [
            f"Analyze the following tests for the {compound_kind} "
            f"`{compound_name}` and infer low-level requirements.",
            "",
        ]

        if compound_desc:
            lines.append(f"Existing description: {compound_desc}")
            lines.append("")

        lines.append(
            f"There are {len(tests)} tests that verify this {compound_kind}."
        )
        lines.append("")

        for i, test in enumerate(tests):
            lines.append(f"## Test {i + 1}: {test['qualified_name']}")
            lines.append(f"Name: {test['test_name']}")
            lines.append(f"Module: {test['test_module']}")
            lines.append(f"Description: {test['description'] or '(none)'}")
            lines.append("")

            if test["verifies"]:
                lines.append("Verifies:")
                for v in test["verifies"]:
                    lines.append(f"  - {v['qualified_name']} ({v['kind']})")
                lines.append("")

            if test["fixtures"]:
                lines.append("Fixtures:")
                for f in test["fixtures"]:
                    type_info = (
                        f" ({f['type_signature']})"
                        if f["type_signature"]
                        else ""
                    )
                    desc_info = (
                        f" — {f['description']}" if f["description"] else ""
                    )
                    lines.append(f"  - {f['name']}{type_info}{desc_info}")
                lines.append("")

            if test["steps"]:
                lines.append("Steps:")
                for s in sorted(test["steps"], key=lambda x: x["order"]):
                    callee_str = ""
                    if s["callees"]:
                        callee_names = [
                            c["qualified_name"] for c in s["callees"]
                        ]
                        callee_str = f" → {', '.join(callee_names)}"
                    desc_info = (
                        f": {s['description']}" if s["description"] else ""
                    )
                    lines.append(
                        f"  - step_{s['order']}{callee_str}{desc_info}"
                    )
                lines.append("")

            if test["assertions"]:
                lines.append("Assertions:")
                for a in sorted(test["assertions"], key=lambda x: x["order"]):
                    desc_info = (
                        f" — {a['description']}"
                        if a["description"]
                        else ""
                    )
                    lines.append(
                        f"  - {a['phase']} {a['operator']}{desc_info}"
                    )
                lines.append("")

            lines.append("---")
            lines.append("")

        # Footer
        lines.append(
            f"Infer an HLR and {min(len(tests), 10)}–{max(len(tests), 5)} "
            f"LLRs for this {compound_kind}. Every test MUST appear in "
            "exactly one LLR's `verified_by` list."
        )
        lines.append("Return the JSON object now:")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _persist_results(
        self,
        target,
        mined: MinedRequirements,
    ) -> MineResult:
        """Persist mined HLR/LLR nodes and edges to Neo4j."""
        return persist_mined_requirements(
            compound=target,
            mined=mined,
            source=getattr(target, "source", "codegraph"),
            tag="as-built",
        )

    # ------------------------------------------------------------------
    # Idempotency
    # ------------------------------------------------------------------

    def _has_existing_requirements(self, target) -> bool:
        """Check if HLR nodes already exist for this compound.

        Uses raw Cypher to avoid triggering the neomodel class-registry
        conflict between ``codegraph_requirements.models.requirement.HLR``
        and ``backend_migrated.models.requirement.HLR`` (both claim the
        ``HLR`` Neo4j label).
        """
        from neomodel import db
        from codegraph_mine.persistence import _make_hlr_name

        compound_name = self.node_name(target)
        hlr_name = _make_hlr_name(compound_name)

        try:
            results, _ = db.cypher_query(
                "MATCH (h:HLR {name: $name}) RETURN count(h) AS cnt",
                {"name": hlr_name},
            )
            return results[0][0] > 0
        except Exception:
            return False
