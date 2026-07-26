"""ComponentMiner — mines functional Components from the full HLR landscape.

Unlike :class:`LLRMiner` (per-compound) and :class:`CompositeHLRMiner`
(per-namespace), the ComponentMiner is a **global** operation: one LLM
call sees all project HLRs (composite + per-compound, grouped + isolated)
and clusters them into the minimal set of functional Components.

Each Component represents a business-level or functional requirement
that the assigned HLRs technically implement::

    ProjectMeta -[:COMPOSES]-> Component -[:COMPOSES]-> HLR -[:COMPOSES]-> LLR ...
    Component -[:GROUPS]-> NamespaceNode

Every HLR must be assigned to exactly one Component.  The LLM is
instructed to produce as few Components as necessary.

Usage::

    from codegraph_mine import ComponentMiner

    miner = ComponentMiner()
    result = miner.mine_all(tag="as-built")
    print(f"Mined {result.llr_count} Components")
"""

from __future__ import annotations

from typing import Any

from codegraph_mine.base import RequirementMiner, MineResult
from codegraph_mine.schemas import MinedComponents
from codegraph_mine.persistence import persist_mined_components


# ══════════════════════════════════════════════════════════════════════════
# System prompt
# ══════════════════════════════════════════════════════════════════════════

_COMPONENT_SYSTEM_PROMPT = """\
You are a systems architect. Below is the complete inventory of
high-level requirements (HLRs) for a software project, organized by
namespace.  Some HLRs have already been grouped into composite
technical requirements (shown as their parent composite).  Your task
is to cluster ALL HLRs into the minimal set of functional Components.

Each Component represents a **functional or business-level requirement**
that the assigned HLRs technically implement.  Components are not
technical — they describe *what the system does for its users*, not *how
the code is structured*.

Guidelines:
- **Every HLR MUST be assigned to exactly one Component.**  No HLR
  may be left unassigned, and no HLR may appear in more than one
  Component.
- **Use as few Components as possible.**  Merge namespaces that serve
  the same functional purpose.  For example, if a project has separate
  namespaces for different entity types that all serve the same data
  layer, they should be one Component.
- **Component descriptions are functional**, not technical.  Write
  descriptions at the level of *what the system does for its users*, not
  *how individual classes are structured*.  For example, describe a
  component's purpose in terms of user-facing capabilities, not class
  internals.
- **Consider cross-namespace dependencies** when deciding to merge.
  If classes in namespace A depend on classes in namespace B, they
  likely belong to the same functional Component.
- The `namespace` field should be the primary top-level namespace for
  the Component.
- Include every assigned HLR name in `hlr_names` — use the exact
  strings as provided.

Response format — return ONLY a JSON object (no markdown, no explanation):

{
  "components": [
    {
      "name": "<Component Name>",
      "description": "The <Component Name> component shall provide <functional/business-level capability description>.",
      "namespace": "<primary top-level namespace>",
      "hlr_names": [
        "<exact HLR name from input>",
        "<exact HLR name from input>",
        ...
      ]
    },
    {
      "name": "<Another Component>",
      "description": "The <Another Component> component shall provide <functional capability>.",
      "namespace": "<primary namespace>",
      "hlr_names": [
        "<exact HLR name from input>",
        ...
      ]
    }
  ]
}

IMPORTANT:
- Include EVERY HLR listed in the input in exactly one Component's
  `hlr_names`.
- Use the exact HLR name strings as provided — do not modify them.
- Aim for the minimal number of Components that fully covers the
  functional scope of the project.
"""


# ══════════════════════════════════════════════════════════════════════════
# ComponentMiner
# ══════════════════════════════════════════════════════════════════════════


class ComponentMiner(RequirementMiner):
    """Mine functional Components from the full HLR landscape.

    This is a **global** miner: one target (the ProjectMeta singleton),
    one LLM call that sees all project HLRs and clusters them into the
    minimal set of functional Components.

    Every HLR (composite + per-compound, grouped + isolated) must be
    assigned to exactly one Component.  Components carry the ``"mined"``
    tag to distinguish them from human-written Components.
    """

    __test__ = False  # prevent pytest collection

    # Minimum HLRs required to mine Components
    MIN_HLRS_FOR_COMPONENTS = 2

    # ------------------------------------------------------------------
    # System prompt
    # ------------------------------------------------------------------

    @property
    def system_prompt(self) -> str:
        return _COMPONENT_SYSTEM_PROMPT

    # ------------------------------------------------------------------
    # Agentic mining configuration
    # ------------------------------------------------------------------

    @property
    def _final_tool_name(self) -> str:
        return "submit_components"

    @property
    def _final_tool_schema(self) -> dict:
        return {
            "name": "submit_components",
            "description": (
                "Submit the mined functional Components after exploring "
                "the codegraph. Every HLR must be assigned to exactly one "
                "Component."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "components": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {
                                    "type": "string",
                                    "minLength": 2,
                                    "description": "Component name.",
                                },
                                "description": {
                                    "type": "string",
                                    "minLength": 10,
                                    "description": "Functional/business-level requirement.",
                                },
                                "namespace": {
                                    "type": "string",
                                    "description": "Primary top-level namespace.",
                                },
                                "hlr_names": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "description": "HLR names assigned to this Component.",
                                },
                            },
                            "required": ["name", "description", "hlr_names"],
                        },
                    },
                },
                "required": ["components"],
            },
        }

    @property
    def _exploration_tool_names(self) -> list[str]:
        """Tools for exploring the codegraph during global Component mining.

        - search_symbols: find compounds by name to understand functional scope
        - get_compound: inspect a compound's members and description
        - find_inheritance: understand type relationships across namespaces
        - graph_list_tags: discover what views exist in the graph
        """
        return ["search_symbols", "get_compound", "find_inheritance", "graph_list_tags"]

    def _build_initial_message(self, target, context: dict) -> str:
        """Build the initial message with the complete HLR inventory as seed.

        The full HLR inventory (names + descriptions + namespaces) is provided
        because no existing tool queries HLR nodes.  The LLM can then use
        exploration tools to understand the code structure behind each HLR
        before clustering them into Components.
        """
        hlr_inventory = context.get("hlr_inventory", [])
        ns_hierarchy = context.get("namespace_hierarchy", [])

        lines = [
            f"Cluster all {len(hlr_inventory)} HLRs into the minimal set "
            f"of functional Components.",
            "",
            f"Use the exploration tools to inspect compounds and their "
            f"relationships, then call `{self._final_tool_name}` to submit "
            f"the Components.",
            "",
            "## HLR Inventory by Namespace:",
            "",
        ]

        # Group by namespace
        ns_groups: dict[str, list[dict]] = {}
        for hlr in hlr_inventory:
            ns = hlr["namespace"] or "(unknown)"
            ns_groups.setdefault(ns, []).append(hlr)

        for ns in sorted(ns_groups.keys()):
            hlrs = ns_groups[ns]
            composited = sum(1 for h in hlrs if h["parent_composite"])
            isolated = len(hlrs) - composited

            composites = set(
                h["parent_composite"] for h in hlrs if h["parent_composite"]
            )
            if composites:
                lines.append(f"### {ns} ({len(hlrs)} HLRs: {composited} composited, {isolated} isolated)")
                for comp in sorted(composites):
                    comp_hlrs = [h for h in hlrs if h["parent_composite"] == comp]
                    lines.append(f"  **Composite: {comp}** ({len(comp_hlrs)} HLRs)")
                    for h in comp_hlrs:
                        lines.append(f"    - `{h['hlr_name']}`")
                        lines.append(f"      {h['hlr_description'][:120]}")
            else:
                lines.append(f"### {ns} ({len(hlrs)} HLRs, all isolated)")
                for h in hlrs:
                    lines.append(f"  - `{h['hlr_name']}`")
                    lines.append(f"    {h['hlr_description'][:120]}")
            lines.append("")

        if ns_hierarchy:
            lines.append("## Namespace Hierarchy:")
            lines.append("")
            for pair in ns_hierarchy:
                lines.append(f"  {pair['parent']} → {pair['child']}")
            lines.append("")

        lines.append("---")
        lines.append("")
        lines.append(
            f"Every HLR MUST appear in exactly one Component's `hlr_names`. "
            f"Use the exploration tools to understand the code structure, "
            f"then call `{self._final_tool_name}`."
        )
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Output schema override
    # ------------------------------------------------------------------

    def _parse_output(self, parsed: dict[str, Any]):
        """Parse LLM output into MinedComponents."""
        return MinedComponents.model_validate(parsed)

    # ------------------------------------------------------------------
    # Target discovery
    # ------------------------------------------------------------------

    def _find_targets(self, **filters) -> list:
        """Return the ProjectMeta singleton as the single mining target.

        The Component miner is a global operation — one target, one
        LLM call for all HLRs.
        """
        from codegraph_project.models.project import ProjectMeta

        return [ProjectMeta.get_singleton()]

    # ------------------------------------------------------------------
    # Context fetching
    # ------------------------------------------------------------------

    def _fetch_context(self, target) -> dict:
        """Fetch the complete HLR landscape for global clustering.

        Returns a dict with:

        - ``project_name``: The project name.
        - ``hlr_inventory``: List of dicts, each with:
          - ``hlr_name``, ``hlr_description``
          - ``namespace``: the compound's parent namespace qualified_name
          - ``compound_qualified_name``, ``compound_kind``
          - ``brief_description``
          - ``parent_composite``: composite HLR name if grouped, else ""
        - ``namespace_hierarchy``: List of (parent, child) namespace pairs
        - ``cross_namespace_deps``: List of cross-namespace dependency
          edges between compounds
        """
        from codegraph.backends import get_backend

        project_name = getattr(target, "name", "") or "project"

        # 1. Fetch the complete HLR inventory
        hlr_query = """
        MATCH (h:HLR)-[:COMPOSES]->(c)
        WHERE (c:ClassNode OR c:InterfaceNode OR c:EnumNode OR c:UnionNode)
          AND $tag IN h.tags
          AND NOT 'composite' IN h.tags
        OPTIONAL MATCH (ns:NamespaceNode)-[:COMPOSES]->(c)
        OPTIONAL MATCH (comp:HLR)-[:COMPOSES]->(h)
        WHERE 'composite' IN comp.tags
        RETURN h.name AS hlr_name,
               h.description AS hlr_description,
               ns.qualified_name AS namespace,
               c.qualified_name AS compound_qn,
               c.kind AS compound_kind,
               c.brief_description AS brief_desc,
               CASE WHEN comp IS NOT NULL THEN comp.name ELSE '' END AS parent_composite
        ORDER BY ns.qualified_name, h.name
        """
        tag = "as-built"  # default; could be parameterized
        try:
            hlr_results, _ = get_backend().execute_raw(hlr_query, {"tag": tag})
        except Exception:
            hlr_results = []

        hlr_inventory: list[dict] = []
        compound_qns: list[str] = []
        for row in hlr_results:
            hlr_name, hlr_desc, ns_qn, comp_qn, comp_kind, brief, parent_comp = row
            hlr_inventory.append({
                "hlr_name": hlr_name or "",
                "hlr_description": hlr_desc or "",
                "namespace": ns_qn or "",
                "compound_qualified_name": comp_qn or "",
                "compound_kind": comp_kind or "",
                "brief_description": brief or "",
                "parent_composite": parent_comp or "",
            })
            if comp_qn:
                compound_qns.append(comp_qn)

        # 2. Fetch namespace hierarchy (parent → child)
        ns_hierarchy: list[dict] = []
        ns_query = """
        MATCH (parent:NamespaceNode)-[:COMPOSES]->(child:NamespaceNode)
        RETURN parent.qualified_name AS parent, child.qualified_name AS child
        ORDER BY parent.qualified_name
        """
        try:
            ns_results, _ = get_backend().execute_raw(ns_query)
            for row in ns_results:
                ns_hierarchy.append({
                    "parent": row[0] or "",
                    "child": row[1] or "",
                })
        except Exception:
            pass

        # 3. Fetch cross-namespace dependencies between compounds
        cross_deps: list[dict] = []
        if len(compound_qns) >= 2:
            dep_query = """
            MATCH (c1)-[r]->(c2)
            WHERE (c1:ClassNode OR c1:InterfaceNode)
              AND (c2:ClassNode OR c2:InterfaceNode)
              AND c1.qualified_name IN $compound_qns
              AND c2.qualified_name IN $compound_qns
              AND type(r) IN ['INHERITS_FROM', 'REALIZES',
                              'DEPENDS_ON', 'REFERENCES']
            OPTIONAL MATCH (ns1:NamespaceNode)-[:COMPOSES]->(c1)
            OPTIONAL MATCH (ns2:NamespaceNode)-[:COMPOSES]->(c2)
            WITH ns1, ns2, r, c1, c2
            WHERE ns1.qualified_name <> ns2.qualified_name
            RETURN DISTINCT ns1.qualified_name AS ns1,
                             type(r) AS rel_type,
                             ns2.qualified_name AS ns2,
                             c1.qualified_name AS c1,
                             c2.qualified_name AS c2
            """
            try:
                dep_results, _ = get_backend().execute_raw(
                    dep_query, {"compound_qns": compound_qns}
                )
                for row in dep_results:
                    cross_deps.append({
                        "from_namespace": row[0] or "",
                        "type": row[1] or "",
                        "to_namespace": row[2] or "",
                        "from_compound": row[3] or "",
                        "to_compound": row[4] or "",
                    })
            except Exception:
                pass

        return {
            "project_name": project_name,
            "hlr_inventory": hlr_inventory,
            "namespace_hierarchy": ns_hierarchy,
            "cross_namespace_deps": cross_deps,
        }

    # ------------------------------------------------------------------
    # Prompt builder
    # ------------------------------------------------------------------

    def _build_prompt(self, target, context: dict) -> str:
        """Build the global Component clustering prompt."""
        project_name = context.get("project_name", "project")
        hlr_inventory = context.get("hlr_inventory", [])
        ns_hierarchy = context.get("namespace_hierarchy", [])
        cross_deps = context.get("cross_namespace_deps", [])

        lines = [
            f"Analyze the complete HLR inventory for the `{project_name}` "
            f"project and cluster all {len(hlr_inventory)} HLRs into the "
            f"minimal set of functional Components.",
            "",
        ]

        # --- Group HLRs by namespace for readability ---
        ns_groups: dict[str, list[dict]] = {}
        for hlr in hlr_inventory:
            ns = hlr["namespace"] or "(unknown)"
            ns_groups.setdefault(ns, []).append(hlr)

        lines.append("## HLR Inventory by Namespace:")
        lines.append("")

        for ns in sorted(ns_groups.keys()):
            hlrs = ns_groups[ns]
            composited = sum(1 for h in hlrs if h["parent_composite"])
            isolated = len(hlrs) - composited

            # Show composite grouping info
            composites = set(
                h["parent_composite"] for h in hlrs
                if h["parent_composite"]
            )
            if composites:
                lines.append(
                    f"### {ns} ({len(hlrs)} HLRs: "
                    f"{composited} composited, {isolated} isolated)"
                )
                for comp in sorted(composites):
                    comp_hlrs = [h for h in hlrs if h["parent_composite"] == comp]
                    lines.append(f"  **Composite: {comp}** ({len(comp_hlrs)} HLRs)")
                    for h in comp_hlrs:
                        lines.append(f"    - {h['hlr_name']}: {h['hlr_description'][:120]}")
                        if h["brief_description"]:
                            lines.append(f"      ({h['compound_qualified_name']}: {h['brief_description'][:80]})")
            else:
                lines.append(f"### {ns} ({len(hlrs)} HLRs, all isolated)")
                for h in hlrs:
                    lines.append(f"  - {h['hlr_name']}: {h['hlr_description'][:120]}")
                    if h["brief_description"]:
                        lines.append(f"    ({h['compound_qualified_name']}: {h['brief_description'][:80]})")
            lines.append("")

        # --- Namespace hierarchy ---
        if ns_hierarchy:
            lines.append("## Namespace Hierarchy:")
            lines.append("")
            for pair in ns_hierarchy:
                lines.append(f"  {pair['parent']} → {pair['child']}")
            lines.append("")

        # --- Cross-namespace dependencies ---
        if cross_deps:
            lines.append("## Cross-Namespace Dependencies:")
            lines.append("")
            for dep in cross_deps:
                lines.append(
                    f"  {dep['from_compound']} -[:{dep['type']}]-> "
                    f"{dep['to_compound']}"
                )
                lines.append(
                    f"    ({dep['from_namespace']} → {dep['to_namespace']})"
                )
            lines.append("")

        lines.append("---")
        lines.append("")

        # --- Footer ---
        lines.append(
            f"Cluster all {len(hlr_inventory)} HLRs into the minimal set "
            f"of functional Components. Every HLR MUST appear in exactly "
            f"one Component's `hlr_names`."
        )
        lines.append("Return the JSON object now:")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _persist_results(self, target, mined) -> MineResult:
        """Persist all mined Components and their HLR links to Neo4j."""
        return persist_mined_components(
            mined=mined,
            source="codegraph",
            tag="as-built",
        )

    # ------------------------------------------------------------------
    # Idempotency
    # ------------------------------------------------------------------

    def _has_existing_requirements(self, target) -> bool:
        """Check if mined Components already exist."""
        from codegraph.backends import get_backend

        try:
            results, _ = get_backend().execute_raw(
                "MATCH (c:Component) WHERE 'mined' IN c.tags "
                "RETURN count(c) AS cnt"
            )
            return results[0][0] > 0
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Eligibility override
    # ------------------------------------------------------------------

    def _should_mine_target(self, target, context: dict) -> bool:
        """Require at least MIN_HLRS_FOR_COMPONENTS HLRs to cluster."""
        return (
            len(context.get("hlr_inventory", []))
            >= self.MIN_HLRS_FOR_COMPONENTS
        )