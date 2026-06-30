"""CompositeHLRMiner — mines composite technical requirements from HLR clusters.

For each namespace that contains two or more compounds with existing
per-compound HLRs, gathers the child HLR descriptions, compound metadata,
and structural relationships (inheritance, realization, dependencies)
and sends them to an LLM to synthesize a single composite technical
requirement.

The composite HLR is persisted with ``COMPOSES`` edges to each child
HLR, creating a multi-level requirement hierarchy::

    CompositeHLR -[:COMPOSES]-> HLR -[:COMPOSES]-> LLR -[:COMPOSES]-> TestNode
    CompositeHLR -[:COMPOSES]-> NamespaceNode

Usage::

    from codegraph_mine import CompositeHLRMiner

    miner = CompositeHLRMiner()
    results = miner.mine_all(tag="as-built")
    print(f"Mined {results.total_llrs} composite HLRs")
"""

from __future__ import annotations

from typing import Any

from codegraph_mine.base import RequirementMiner, MineResult
from codegraph_mine.schemas import MinedCompositeHLR
from codegraph_mine.persistence import persist_composite_hlr


# ══════════════════════════════════════════════════════════════════════════
# System prompt
# ══════════════════════════════════════════════════════════════════════════

_COMPOSITE_SYSTEM_PROMPT = """\
You are a requirements engineer. Your task is to synthesize a composite
technical requirement from a set of existing high-level requirements
(HLRs) for classes that belong to the same namespace or module.

Guidelines:
- The composite requirement should describe what the SUBSYSTEM (the
  collection of classes working together) shall do — not what individual
  classes do.
- It should be more abstract than any individual HLR but traceable to
  all of them.
- Use "The {namespace} subsystem shall..." or "The {namespace} module
  shall..." phrasing.
- Consider the structural relationships (inheritance, interface
  realization, dependencies) when determining the subsystem's purpose.
- The rationale should explain why these HLRs were grouped together and
  what shared architectural concern the composite requirement addresses.
- Include every child HLR name in `child_hlr_names` — use the exact
  names as provided in the input.

Response format — return ONLY a JSON object (no markdown, no explanation):

{
  "description": "The <namespace> subsystem shall provide <high-level capability covering all child HLRs>.",
  "rationale": "These classes collectively implement <shared architectural concern>. Their HLRs all address aspects of <common theme>.",
  "child_hlr_names": [
    "<exact HLR name from input>",
    "<exact HLR name from input>",
    "<exact HLR name from input>"
  ]
}

IMPORTANT:
- Include EVERY HLR listed in the input in `child_hlr_names`.
- Use the exact HLR name strings as provided — do not modify them.
- The description should be a single, cohesive requirement (1-3 sentences).
"""


# ══════════════════════════════════════════════════════════════════════════
# CompositeHLRMiner
# ══════════════════════════════════════════════════════════════════════════


class CompositeHLRMiner(RequirementMiner):
    """Mine composite technical requirements from clusters of per-compound HLRs.

    Finds all namespaces that contain two or more compounds with existing
    HLRs (mined by :class:`LLRMiner`), gathers the child HLR descriptions
    and structural relationships between the compounds, and sends them to
    an LLM to synthesize a single composite technical requirement.

    One LLM call per namespace cluster.  The composite HLR is persisted
    with ``COMPOSES`` edges to each child HLR and to the NamespaceNode.
    """

    __test__ = False  # prevent pytest collection

    # Minimum number of child HLRs required to form a composite
    MIN_HLRS_FOR_COMPOSITE = 2

    # ------------------------------------------------------------------
    # System prompt
    # ------------------------------------------------------------------

    @property
    def system_prompt(self) -> str:
        return _COMPOSITE_SYSTEM_PROMPT

    # ------------------------------------------------------------------
    # Agentic mining configuration
    # ------------------------------------------------------------------

    @property
    def _final_tool_name(self) -> str:
        return "submit_composite_hlr"

    @property
    def _final_tool_schema(self) -> dict:
        return {
            "name": "submit_composite_hlr",
            "description": (
                "Submit the synthesized composite HLR after exploring the "
                "namespace's classes and their existing requirements."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "description": {
                        "type": "string",
                        "minLength": 10,
                        "description": "Composite technical requirement text.",
                    },
                    "rationale": {
                        "type": "string",
                        "description": "Why these HLRs were grouped.",
                    },
                    "child_hlr_names": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "HLR names being composed.",
                    },
                },
                "required": ["description", "child_hlr_names"],
            },
        }

    @property
    def _exploration_tool_names(self) -> list[str]:
        """Tools for exploring the namespace's code structure.

        - search_symbols: find compounds by name within the namespace
        - get_compound: inspect a compound's members and description
        - find_inheritance: understand type relationships between compounds
        """
        return ["search_symbols", "get_compound", "find_inheritance"]

    def _build_initial_message(self, target, context: dict) -> str:
        """Build the initial message with the HLR inventory as seed context.

        The existing HLR names and descriptions are provided because no
        existing tool queries HLR nodes.  The LLM can then use exploration
        tools to inspect the underlying compounds and their relationships.
        """
        ns_name = context["namespace_name"]
        child_hlrs = context.get("child_hlrs", [])

        lines = [
            f"Synthesize a composite technical HLR for the `{ns_name}` "
            f"namespace. {len(child_hlrs)} per-compound HLRs exist for "
            f"classes in this namespace.",
            "",
            f"Use the exploration tools to inspect the compounds and their "
            f"relationships, then call `{self._final_tool_name}` to submit "
            f"the composite HLR.",
            "",
            "## Existing HLRs:",
            "",
        ]

        for i, hlr in enumerate(child_hlrs):
            lines.append(f"### HLR {i + 1}: `{hlr['hlr_name']}`")
            lines.append(f"**Compound:** `{hlr['compound_qualified_name']}` ({hlr['compound_kind']})")
            if hlr["brief_description"]:
                lines.append(f"**Description:** {hlr['brief_description']}")
            lines.append(f"**HLR:** {hlr['hlr_description']}")
            lines.append("")

        lines.append("---")
        lines.append("")
        lines.append(
            f"Explore the compounds using the available tools to understand "
            f"their structure and relationships. Include all {len(child_hlrs)} "
            f"HLR names in `child_hlr_names`, then call "
            f"`{self._final_tool_name}`."
        )
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Output schema override
    # ------------------------------------------------------------------

    def _parse_output(self, parsed: dict[str, Any]):
        """Parse LLM output into MinedCompositeHLR instead of MinedRequirements."""
        return MinedCompositeHLR.model_validate(parsed)

    # ------------------------------------------------------------------
    # Target discovery
    # ------------------------------------------------------------------

    def _find_targets(self, **filters) -> list:
        """Find all NamespaceNodes that contain ≥2 compounds with HLRs.

        Walks the graph: HLR → CompoundNode ← NamespaceNode, groups by
        namespace, and returns namespaces with at least
        :attr:`MIN_HLRS_FOR_COMPOSITE` HLRs.

        Keyword Args:
            tag: If provided, only consider HLRs with this tag
                (e.g. ``"as-built"``).

        Returns:
            List of unique NamespaceNode neomodel instances.
        """
        from neomodel import db
        from codegraph.models.namespace import NamespaceNode

        tag = filters.get("tag")

        query = """
        MATCH (h:HLR)-[:COMPOSES]->(c)
        WHERE (c:ClassNode OR c:InterfaceNode OR c:EnumNode OR c:UnionNode)
        """
        params: dict = {}
        if tag:
            query += " AND $tag IN h.tags"
            params["tag"] = tag

        query += """
        MATCH (ns:NamespaceNode)-[:COMPOSES]->(c)
        WITH ns, collect(DISTINCT h) AS hlrs
        WHERE size(hlrs) >= $min_hlrs
        RETURN ns
        ORDER BY ns.qualified_name
        """
        params["min_hlrs"] = self.MIN_HLRS_FOR_COMPOSITE

        try:
            results, _ = db.cypher_query(query, params)
        except Exception as exc:
            import logging
            logging.getLogger(__name__).error(
                "CompositeHLRMiner._find_targets: query failed: %s", exc
            )
            return []

        namespaces: list = []
        for row in results:
            try:
                ns = NamespaceNode.inflate(row[0])
                namespaces.append(ns)
            except Exception:
                pass

        return namespaces

    # ------------------------------------------------------------------
    # Context fetching
    # ------------------------------------------------------------------

    def _fetch_context(self, target) -> dict:
        """Fetch all context needed to mine a composite HLR for one namespace.

        Returns a dict with:

        - ``namespace_name``: The namespace's qualified_name.
        - ``namespace_description``: Any existing description.
        - ``child_hlrs``: List of dicts, each with:
          - ``hlr_name``, ``hlr_description``
          - ``compound_qualified_name``, ``compound_kind``
          - ``brief_description``, ``base_classes``
        - ``relationships``: List of dicts with ``source``, ``type``,
          ``target`` describing structural relationships between
          compounds in the namespace.
        """
        from neomodel import db

        ns_name = self.node_name(target)
        ns_desc = getattr(target, "description", "") or ""

        try:
            ns_element_id = db.parse_element_id(target.element_id)
        except Exception:
            ns_element_id = None

        if ns_element_id is None:
            return {
                "namespace_name": ns_name,
                "namespace_description": ns_desc,
                "child_hlrs": [],
                "relationships": [],
            }

        # 1. Fetch all child HLRs + their compound metadata
        hlr_query = """
        MATCH (ns:NamespaceNode)-[:COMPOSES]->(c)<-[:COMPOSES]-(h:HLR)
        WHERE elementId(ns) = $ns_id
        RETURN h.name AS hlr_name,
               h.description AS hlr_description,
               c.qualified_name AS compound_qn,
               c.kind AS compound_kind,
               c.brief_description AS brief_desc,
               c.base_classes AS base_classes
        ORDER BY c.qualified_name
        """
        try:
            hlr_results, _ = db.cypher_query(
                hlr_query, {"ns_id": ns_element_id}
            )
        except Exception:
            hlr_results = []

        child_hlrs: list[dict] = []
        compound_qns: list[str] = []
        for row in hlr_results:
            hlr_name, hlr_desc, comp_qn, comp_kind, brief, bases = row
            child_hlrs.append({
                "hlr_name": hlr_name or "",
                "hlr_description": hlr_desc or "",
                "compound_qualified_name": comp_qn or "",
                "compound_kind": comp_kind or "",
                "brief_description": brief or "",
                "base_classes": bases or [],
            })
            if comp_qn:
                compound_qns.append(comp_qn)

        # 2. Fetch structural relationships between compounds in the namespace
        relationships: list[dict] = []
        if len(compound_qns) >= 2:
            rel_query = """
            MATCH (c1)-[r]->(c2)
            WHERE (c1:ClassNode OR c1:InterfaceNode OR c1:EnumNode)
              AND (c2:ClassNode OR c2:InterfaceNode OR c2:EnumNode)
              AND c1.qualified_name IN $compound_qns
              AND c2.qualified_name IN $compound_qns
              AND type(r) IN ['INHERITS_FROM', 'REALIZES',
                              'DEPENDS_ON', 'REFERENCES', 'SPECIALIZES']
            RETURN c1.qualified_name AS source,
                   type(r) AS rel_type,
                   c2.qualified_name AS target
            """
            try:
                rel_results, _ = db.cypher_query(
                    rel_query, {"compound_qns": compound_qns}
                )
                for row in rel_results:
                    relationships.append({
                        "source": row[0] or "",
                        "type": row[1] or "",
                        "target": row[2] or "",
                    })
            except Exception:
                pass

        return {
            "namespace_name": ns_name,
            "namespace_description": ns_desc,
            "child_hlrs": child_hlrs,
            "relationships": relationships,
        }

    # ------------------------------------------------------------------
    # Prompt builder
    # ------------------------------------------------------------------

    def _build_prompt(self, target, context: dict) -> str:
        """Build the synthesis prompt for one namespace cluster."""
        ns_name = context["namespace_name"]
        ns_desc = context.get("namespace_description", "")
        child_hlrs = context.get("child_hlrs", [])
        relationships = context.get("relationships", [])

        lines = [
            f"Analyze the following high-level requirements for classes in "
            f"the `{ns_name}` namespace and synthesize a single composite "
            f"technical requirement.",
            "",
        ]

        if ns_desc:
            lines.append(f"Namespace description: {ns_desc}")
            lines.append("")

        lines.append(f"There are {len(child_hlrs)} HLRs to synthesize.")
        lines.append("")

        # --- Child HLRs with compound context ---
        lines.append("## Existing HLRs:")
        lines.append("")
        for i, hlr in enumerate(child_hlrs):
            lines.append(f"### HLR {i + 1}: {hlr['hlr_name']}")
            lines.append(f"**Compound:** `{hlr['compound_qualified_name']}` ({hlr['compound_kind']})")
            if hlr["brief_description"]:
                lines.append(f"**Description:** {hlr['brief_description']}")
            if hlr["base_classes"]:
                lines.append(f"**Base classes:** {', '.join(hlr['base_classes'])}")
            lines.append(f"**HLR:** {hlr['hlr_description']}")
            lines.append("")

        # --- Structural relationships ---
        if relationships:
            lines.append("## Structural relationships between compounds:")
            lines.append("")
            for rel in relationships:
                lines.append(
                    f"- `{rel['source']}` -[:{rel['type']}]-> `{rel['target']}`"
                )
            lines.append("")

        lines.append("---")
        lines.append("")

        # --- Footer ---
        lines.append(
            f"Synthesize a single composite HLR for the `{ns_name}` "
            f"subsystem. Include all {len(child_hlrs)} HLR names in "
            "`child_hlr_names`."
        )
        lines.append("Return the JSON object now:")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _persist_results(self, target, mined) -> MineResult:
        """Persist the composite HLR and its child HLR links to Neo4j."""
        return persist_composite_hlr(
            namespace=target,
            mined=mined,
            source=getattr(target, "source", "codegraph"),
            tag="as-built",
        )

    # ------------------------------------------------------------------
    # Idempotency
    # ------------------------------------------------------------------

    def _has_existing_requirements(self, target) -> bool:
        """Check if a composite HLR already exists for this namespace."""
        from neomodel import db
        from codegraph_mine.persistence import _make_composite_hlr_name

        namespace_name = self.node_name(target)
        hlr_name = _make_composite_hlr_name(namespace_name)

        try:
            results, _ = db.cypher_query(
                "MATCH (h:HLR {name: $name}) "
                "WHERE 'composite' IN h.tags "
                "RETURN count(h) AS cnt",
                {"name": hlr_name},
            )
            return results[0][0] > 0
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Eligibility override
    # ------------------------------------------------------------------

    def _should_mine_target(self, target, context: dict) -> bool:
        """Require at least MIN_HLRS_FOR_COMPOSITE child HLRs."""
        return len(context.get("child_hlrs", [])) >= self.MIN_HLRS_FOR_COMPOSITE