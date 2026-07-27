"""Design agent — the canonical HLR design pipeline for codegraph_design.

Ported from ticketing-system ``backend_migrated.agents.design_hlr``.
Runs a single tool loop that designs the OO class structure and
resolves notional verification stubs to qualified design names.
Uses :class:`DesignToolDispatcher` (design + codegraph tools) and
:class:`VerificationDispatcher` (verification resolution) together.

Usage::

    from codegraph_design.agents.design_oo import design_and_persist_hlr

    summary = design_and_persist_hlr(
        hlr_uid="2c3463b2…",
        log_dir="/path/to/logs",
    )
    # → {"nodes_created": 5, "verifications_resolved": 8, "links_applied": 3}
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field

from llm_caller import call_tool_loop
from codegraph.backends import get_backend
from neomodel import RelationshipTo, RelationshipFrom

from codegraph.models.tags import CodeGraphNode
from codegraph.models.test import TestNode
from codegraph.persistence.repository import GraphRepository
from codegraph_requirements.models import HLR, LLR
from codegraph_design.tools.dispatcher import (
    DesignToolDispatcher,
    VerificationDispatcher,
)
from codegraph_requirements.formatting import format_hlrs_for_prompt

log = logging.getLogger(__name__)


def _first_or_none(query_set):
    """Like ``.first()`` but returns ``None`` on empty results.

    neomodel's ``filter().first()`` raises ``DoesNotExist`` when no
    nodes match.  This wrapper returns ``None`` instead, matching
    the old ``get_or_none`` behaviour while still handling duplicates.
    """
    try:
        return query_set.first()
    except Exception:
        return None


# ══════════════════════════════════════════════════════════════════════════
# Utility: typed edge target traversal for verification nodes
# ══════════════════════════════════════════════════════════════════════════


def get_typed_edge_targets(node, edge_type: str) -> list[dict]:
    """Return all targets of *edge_type* from *node* across all relationship managers.

    Because codegraph test models declare separate RelationshipTo /
    RelationshipFrom descriptors per target type (e.g.
    ``left_operand_compound``, ``left_operand_literal``), a single edge
    type has multiple managers.  This helper iterates all of them and
    returns a combined list of dicts with ``qualified_name``, ``name``,
    ``labels``, and ``value`` keys.
    """
    targets: list[dict] = []
    seen: set[str] = set()

    for klass in type(node).__mro__:
        for name, val in vars(klass).items():
            if not isinstance(val, (RelationshipTo, RelationshipFrom)):
                continue
            if val.definition["relation_type"] != edge_type:
                continue
            if name in seen:
                continue
            seen.add(name)

            manager = getattr(node, name)
            for connected in manager.all():
                qn = getattr(connected, "qualified_name", "") or ""
                name_val = getattr(connected, "name", "") or ""

                labels: list[str] = []
                if hasattr(connected, "element_id_property"):
                    try:
                        _, results = get_backend().execute_raw(
                            "MATCH (n) WHERE elementId(n) = $eid RETURN labels(n)",
                            {"eid": (connected.element_id)},
                        )
                        if results:
                            labels = results[0][0]
                    except Exception:
                        pass

                value = ""
                if hasattr(connected, "value"):
                    value = connected.value or ""

                targets.append({
                    "qualified_name": qn,
                    "name": name_val,
                    "labels": labels,
                    "value": value,
                })

    return targets


# ══════════════════════════════════════════════════════════════════════════
# Result dataclass
# ══════════════════════════════════════════════════════════════════════════

@dataclass
class DesignHLRResult:
    """Output of ``design_hlr()``."""

    design: list[dict] = field(default_factory=list)
    verifications: dict[str, list[dict]] = field(default_factory=dict)


# ══════════════════════════════════════════════════════════════════════════
# Notional verification stub loading
# ══════════════════════════════════════════════════════════════════════════

def _load_notional_verifications(llrs: list[LLR]) -> dict[str, list[dict]]:
    """Load existing notional verification stubs from Neo4j for each LLR."""
    llr_verifications: dict[str, list[dict]] = {}

    for llr in llrs:
        tests = llr.verification_methods.all()
        if not tests:
            continue

        verifs_for_llr = []
        for test_node in tests:
            vm_dict = {
                "method": test_node.method,
                "test_name": test_node.test_name or "",
                "description": test_node.description or "",
                "preconditions": [],
                "actions": [],
                "postconditions": [],
            }

            assertions = test_node.assertions.all()
            for assertion in sorted(assertions, key=lambda a: a.order):
                left_targets = get_typed_edge_targets(assertion, "LEFT_OPERAND")
                right_targets = get_typed_edge_targets(assertion, "RIGHT_OPERAND")
                cond_dict = {
                    "subject_qualified_name": left_targets[0]["qualified_name"] if left_targets else "",
                    "operator": assertion.operator or "==",
                    "expected_value": (
                        right_targets[0].get("value") or
                        right_targets[0]["qualified_name"]
                    ) if right_targets else "",
                    "object_qualified_name": right_targets[0]["qualified_name"] if right_targets else "",
                }
                if assertion.phase == "pre":
                    vm_dict["preconditions"].append(cond_dict)
                else:
                    vm_dict["postconditions"].append(cond_dict)

            steps = test_node.steps.all()
            for step in sorted(steps, key=lambda s: s.order):
                callee_targets = get_typed_edge_targets(step, "CALLEE")
                caller_targets = get_typed_edge_targets(step, "CALLER")
                vm_dict["actions"].append({
                    "description": step.description or "",
                    "callee_qualified_name": callee_targets[0]["qualified_name"] if callee_targets else "",
                    "caller_qualified_name": caller_targets[0]["qualified_name"] if caller_targets else "",
                })

            verifs_for_llr.append(vm_dict)

        if verifs_for_llr:
            llr_verifications[llr.uid] = verifs_for_llr

    return llr_verifications


def _format_verifications_for_prompt(
    llrs: list[LLR],
    notional_verifications: dict[str, list[dict]],
) -> str:
    """Format LLRs with their notional verification stubs for the prompt."""
    lines = []
    for llr in llrs:
        lines.append(f"LLR {llr.uid}: {llr.description}")
        verifs = notional_verifications.get(llr.uid, [])
        if verifs:
            lines.append("  Verifications (notional — resolve to qualified names):")
            for v in verifs:
                label = v.get("test_name", "") or v.get("method", "")
                lines.append(f"    [{v['method']}] {label}: {v.get('description', '')}")
                if v.get("preconditions"):
                    lines.append("      Pre-conditions:")
                    for c in v["preconditions"]:
                        lines.append(
                            f"        {c.get('subject_qualified_name', '')} "
                            f"{c.get('operator', '==')} "
                            f"{c.get('expected_value', '')}"
                        )
                if v.get("actions"):
                    lines.append("      Actions:")
                    for a in v["actions"]:
                        callee = a.get("callee_qualified_name", "")
                        lines.append(
                            f"        {a.get('description', '')}"
                            + (f" → {callee}" if callee else "")
                        )
                if v.get("postconditions"):
                    lines.append("      Post-conditions:")
                    for c in v["postconditions"]:
                        lines.append(
                            f"        {c.get('subject_qualified_name', '')} "
                            f"{c.get('operator', '==')} "
                            f"{c.get('expected_value', '')}"
                        )
        else:
            lines.append("  (No verification stubs)")
        lines.append("")
    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════════
# System prompt for the design + verification agent
# ══════════════════════════════════════════════════════════════════════════

SYSTEM_PROMPT = """\
You are a software architect and verification engineer. Given design context
and requirements, your job is to produce an object-oriented class design AND
resolve verification stubs to reference real design elements.

**Workflow:**

0. **Discover as-built context** — Use search_symbols to find relevant
   classes by name.  For each class you need to reference (e.g. as a
   dependency, parameter type, or base class), call import_compound
   to load it into the context graph.  Do NOT recreate these classes
   as design nodes — your design should contain ONLY new classes.
   The context graph makes as-built names valid reference targets.
1. **Design** — Use validate_design and check_class_name to produce a
   sound OO class design. Call produce_oo_design when ready.
2. **Smell-check** — Call check_design_smells with your design nodes.
   Fix all blocking smells before proceeding (orphaned enums, invalid
   edges, duplicate names, etc.). Warning-level smells should be
   reviewed but don't block the pipeline.
3. **Resolve verifications** — Map each notional verification stub to
   qualified names from your design. Call draft_verifications to check
   that all references resolve.
4. **Commit** — Call commit_design_and_verifications with the final
   design and verifications as arguments.

{specializations_section}
{namespace_section}
{as_built_section}
{existing_classes_section}
{intercomponent_section}

### Design rules

- **NEVER create a design node for a class that already exists in the codegraph.**
  Use import_compound to load it into context, then reference it by its
  fully-qualified name in DEPENDS_ON edges, type signatures, and verifications.
- Qualified names follow C++ convention: Namespace::ClassName::memberName
- The full codegraph is the single source of truth — any qualified name that
  exists anywhere in Neo4j (any tag) is a valid reference target
- Use check_class_name to discover names, import_compound to load them
  into context, then reference them in your design
- Keep classes focused and cohesive

### Verification resolution

For each LLR, the notional verification stubs describe test scenarios
using placeholder references like "Thermostat.current_reading" or "Display.shown_temp".
Your job is to translate each stub into a fully resolved verification
method that references actual design members.

For each verification stub:
1. Identify what design element each reference targets
2. Replace placeholder references with qualified names from your design
3. Call draft_verifications to validate that every reference resolves
4. If a reference can't resolve, either add the missing member to your
   design via produce_oo_design, or use expected_value alone for literals

<FORMAT-CONTRACT name="qualified-names">
All `subject_qualified_name`, `object_qualified_name`, `callee_qualified_name`,
and `caller_qualified_name` fields MUST use qualified names that exactly match
the design context or the current draft.

Pattern: <namespace>::<ClassName>::<memberName>

Leave `caller_qualified_name` empty if the caller is the test harness.

**Enum values:** When comparing against an enum value, reference the enum
*attribute* as `subject_qualified_name` and put the enum *value* in
`expected_value`. Do NOT use enum values as `subject_qualified_name`.

Example:
  subject_qualified_name: "climate::Thermostat::error_state"
  operator: "=="
  expected_value: "SensorFault"
</FORMAT-CONTRACT>

<FORMAT-CONTRACT name="verification-key-format">
The `verifications` field in `draft_verifications` MUST be a JSON object
keyed by LLR uid (string), NOT by test name.

Example: "verifications": {{ "abc123": [...], "def456": [...] }}
Wrong:   "verifications": {{ "test_set_target": [...] }}
</FORMAT-CONTRACT>

You MUST use commit_design_and_verifications to return your final result.
Pass the design (same list of CodeGraphNode dicts from produce_oo_design)
and the verifications dict (same structure from draft_verifications) as
arguments to commit_design_and_verifications.
"""


# ══════════════════════════════════════════════════════════════════════════
# Core pipeline
# ══════════════════════════════════════════════════════════════════════════

def design_hlr(
    hlr: HLR,
    llrs: list[LLR],
    *,
    context_classes: list[dict] | None = None,
    component_namespace: str = "",
    sibling_namespaces: list[str] | None = None,
    model: str = "",
    log_dir: str = "",
) -> DesignHLRResult:
    """Design a single HLR and resolve its verification stubs.

    Runs a single tool loop that:
    1. Designs the OO class structure (using DesignToolDispatcher)
    2. Resolves notional verification stubs to qualified names (using
       VerificationDispatcher)
    3. Commits the combined result

    Args:
        hlr: Neomodel HLR instance.
        llrs: Neomodel LLR instances belonging to this HLR.
        context_classes: Inter-component / prior-design class dicts to
            seed into the context graph.
        component_namespace: Required C++ namespace for this component.
        sibling_namespaces: Other component namespaces.
        model: LLM model override.
        log_dir: Directory for per-step prompt logs.

    Returns:
        ``DesignHLRResult`` with ``design`` (LayerGraph-format nodes)
        and ``verifications`` (LLR uid → verification method lists).
    """
    from codegraph_design.agents.design_oo_prompt import (
        build_existing_classes_section,
        build_intercomponent_section,
        build_namespace_section,
    )

    # --- Load notional verification stubs from Neo4j ---
    notional_verifications = _load_notional_verifications(llrs)

    # --- Build requirements text for the prompt ---
    hlr_line = f"HLR: {hlr.description}"
    verifs_text = _format_verifications_for_prompt(llrs, notional_verifications)
    requirements_text = f"{hlr_line}\n\n{verifs_text}"

    # --- Build prompt sections ---
    namespace_section = (
        build_namespace_section(component_namespace, sibling_namespaces or [])
        if component_namespace
        else ""
    )
    existing_section = (
        build_existing_classes_section(context_classes or [])
        if context_classes
        else ""
    )
    intercomp_section = (
        build_intercomponent_section(context_classes or [])
        if context_classes
        else ""
    )

    system = SYSTEM_PROMPT.format(
        specializations_section="",
        namespace_section=namespace_section,
        as_built_section="",
        existing_classes_section=existing_section,
        intercomponent_section=intercomp_section,
    )

    # --- Component hint for user prompt ---
    comp_nodes = hlr.component.all()
    component_hint = ""
    if comp_nodes:
        comp = comp_nodes[0]
        comp_name = comp.name or ""
        if comp_name:
            component_hint = (
                f"\n\nThis requirement belongs to the architectural "
                f"component: **{comp_name}**"
            )
            if component_namespace:
                component_hint += f" (namespace: `{component_namespace}`)"
            component_hint += (
                ". Your class design should be scoped to this component.\n"
            )
            if comp.description:
                component_hint += (
                    f"\n### Component Description\n\n{comp.description}\n"
                )

    user_message = {
        "role": "user",
        "content": (
            "Design the object-oriented class structure and resolve "
            "verification stubs for the following requirements:\n\n"
            f"{requirements_text}{component_hint}"
        ),
    }

    messages = [user_message]

    # --- Build dispatchers ---
    design_disp = DesignToolDispatcher(
        context_classes=context_classes or None,
        component_namespace=component_namespace,
        sibling_namespaces=sibling_namespaces or [],
    )
    verif_disp = VerificationDispatcher(design_dispatcher=design_disp)

    # --- Composite dispatch function ---
    def dispatch(tool_name: str, tool_input: dict) -> str:
        if tool_name in verif_disp._handlers:
            return verif_disp.dispatch(tool_name, tool_input)
        return design_disp.dispatch(tool_name, tool_input)

    # --- Combined tool schemas ---
    all_tools = design_disp.all_tool_schemas + verif_disp.all_tool_schemas

    # --- Run the tool loop ---
    prompt_log = ""
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)
        prompt_log = os.path.join(log_dir, f"design_verify_hlr_{hlr.uid[:8]}.md")

    log.info(
        "design_hlr: starting tool loop for HLR %s with %d tools",
        hlr.uid[:8], len(all_tools),
    )
    try:
        result = call_tool_loop(
            system=system,
            messages=messages,
            tools=all_tools,
            final_tool_name="commit_design_and_verifications",
            tool_dispatcher=dispatch,
            model=model,
            max_tokens=65536,
            max_turns=75,
            prompt_log_file=prompt_log,
        )
    except Exception as exc:
        log.error(
            "design_hlr: tool loop failed for HLR %s: %s",
            hlr.uid[:8], exc, exc_info=True,
        )
        raise

    # --- Extract result ---
    design_nodes = result.get("design", [])
    verifications = result.get("verifications", {})

    log.info(
        "Design complete for HLR %s: %d design nodes, %d LLRs with verifications",
        hlr.uid[:8], len(design_nodes), len(verifications),
    )

    return DesignHLRResult(
        design=design_nodes,
        verifications=verifications,
    )


# ══════════════════════════════════════════════════════════════════════════
# Scaffold → design reconciliation helpers
# ══════════════════════════════════════════════════════════════════════════


def _last_segment(qn: str) -> str:
    """Extract the last segment from a qualified name."""
    if not qn:
        return ""
    if qn.startswith("literal::"):
        return qn
    if "::" in qn:
        return qn.rsplit("::", 1)[-1]
    if "." in qn:
        return qn.rsplit(".", 1)[-1]
    return qn


def _flatten_design_nodes(design_nodes: list[dict]) -> list[dict]:
    """Flatten nested design node dicts into a flat list."""
    flat: list[dict] = []

    def _walk(node: dict) -> None:
        flat.append(node)
        for child in node.get("composes", []):
            _walk(child)

    for d in design_nodes:
        _walk(d)
    return flat


def _update_scaffold_to_design(scaffold_node, design_dict: dict) -> bool:
    """Update a scaffold node in place to become a design node via raw Cypher."""
    from codegraph.uid import compute_uid, normalize_argsstring

    dqn = design_dict.get("qualified_name", "")
    if not dqn:
        return False

    dname = design_dict.get("name", "") or _last_segment(dqn)
    dkind = design_dict.get("kind", "")
    dtype = design_dict.get("type", "")
    dts = design_dict.get("type_signature", "")
    dvis = design_dict.get("visibility", "")
    dbd = design_dict.get("brief_description", "")

    if dtype == "MethodNode":
        argsstring = design_dict.get("argsstring", "") or dts
        new_uid = compute_uid(dqn, normalize_argsstring(argsstring))
    else:
        new_uid = compute_uid(dqn)

    sn_type = type(scaffold_node).__name__
    eid = (scaffold_node.element_id)

    set_parts = [
        "n.qualified_name = $qn",
        "n.name = $name",
        "n.kind = $kind",
        "n.tags = $tags",
        "n.uid = $uid",
    ]
    params: dict = {
        "eid": eid,
        "qn": dqn,
        "name": dname,
        "kind": dkind,
        "tags": ["design"],
        "uid": new_uid,
    }
    # Update parent_qualified_name — the test queries MethodNode.nodes.all()
    # grouped by parent_qualified_name.  Without this, scaffold→design
    # qualified_name updates break method-to-parent lookups.
    if "::" in dqn:
        parent_qn = dqn.rsplit("::", 1)[0]
        if parent_qn and parent_qn != dqn:
            set_parts.append("n.parent_qualified_name = $parent_qn")
            params["parent_qn"] = parent_qn
    if dts:
        set_parts.append("n.type_signature = $ts")
        params["ts"] = dts
    if dvis:
        set_parts.append("n.visibility = $vis")
        params["vis"] = dvis
    if dbd:
        set_parts.append("n.brief_description = $bd")
        params["bd"] = dbd

    label_ops = ""
    stale: set[str] = set()
    if dtype:
        # Query the ACTUAL labels from Neo4j, not from the Python
        # class hierarchy.  Neomodel may resolve a node with labels
        # {AttributeNode, MemberNode} as either AttributeNode or
        # MemberNode; relying on inherited_labels() from the Python
        # type loses the concrete label (e.g. AttributeNode) and
        # skips the REMOVE step.  Using actual DB labels ensures we
        # know exactly what to remove.
        actual_label_rows, __ = get_backend().execute_raw(
            "MATCH (n) WHERE elementId(n) = $eid RETURN labels(n)",
            {"eid": eid},
        )
        old_labels = set(actual_label_rows[0][0]) if actual_label_rows else {sn_type}
        target_cls = CodeGraphNode._registry.get(dtype)
        new_labels = set(getattr(target_cls, "inherited_labels", lambda: [dtype])()) if target_cls else {dtype}
        stale = old_labels - new_labels
        # Only run migration if the node doesn't already have the target label
        # Set ALL inherited labels, not just dtype.  Otherwise nodes
        # that lack a parent label (e.g. LiteralNode→EnumValueNode
        # where LiteralNode has no MemberNode) only get the leaf label
        # and fail neomodel resolution later.
        missing_labels = new_labels - old_labels
        label_ops = " ".join(f"SET n:`{l}`" for l in sorted(missing_labels))
        for sl in sorted(stale):
            try:
                get_backend().execute_raw(
                    "MATCH (n) WHERE elementId(n) = $eid REMOVE n:`" + sl + "`",
                    {"eid": eid},
                )
            except Exception as exc:
                log.warning("REMOVE label %s failed for %s: %s", sl, dqn, exc)

    query = (
        f"MATCH (n) WHERE elementId(n) = $eid "
        f"{label_ops}"
        f"SET {', '.join(set_parts)}"
    )
    try:
        get_backend().execute_raw(query, params)
        # ── Post-update: verify no stale labels remain ──
        if stale:
            for sl in sorted(stale):
                check_results, _ = get_backend().execute_raw(
                    "MATCH (n) WHERE elementId(n) = $eid AND n:`" + sl + "` RETURN n",
                    {"eid": eid},
                )
                if check_results:
                    log.warning(
                        "Scaffold %s still has stale label %s after update; forcing removal",
                        dqn, sl,
                    )
                    get_backend().execute_raw(
                        "MATCH (n) WHERE elementId(n) = $eid REMOVE n:`" + sl + "`",
                        {"eid": eid},
                    )
        log.info("Updated scaffold %s → %s (labels %s → %s)",
                 getattr(scaffold_node, "qualified_name", "?"), dqn,
                 sorted(old_labels), sorted(new_labels))
        return True
    except Exception as exc:
        log.warning("Failed to update scaffold %s → %s: %s",
                     getattr(scaffold_node, "qualified_name", "?"), dqn, exc)
        return False


def _create_design_node_fresh(design_dict: dict) -> bool:
    """Create or overlay a design node with ``tags=["design"]``.

    Look-up order (first match wins):
    1. ``overlays_qualified_name`` — explicit link from the model.
       The design properties are overlaid onto the found as-built node
       **in place**, reusing its ``uid`` so the node is merged, not
       duplicated.
    2. ``qualified_name`` — implicit match by name.  Same semantics
       as case 1.
    3. Fallback — create a fresh node via ``CodeGraphNode.deserialize()``.

    Validates that ``type`` and ``kind`` are consistent — if they
    conflict (e.g. ``type="ClassNode"`` + ``kind="enumvalue"``),
    corrects ``type`` to match ``kind`` to avoid creating nodes
    with conflicting Neo4j labels.
    """
    # ── Validate type/kind consistency ───────────────────────────────
    _KIND_TO_TYPE: dict[str, str] = {
        "namespace": "NamespaceNode",
        "module": "ModuleNode",
        "class": "ClassNode",
        "union": "UnionNode",
        "concept": "ConceptNode",
        "function": "FunctionNode",
        "define": "DefineNode",
        "interface": "InterfaceNode",
        "enum": "EnumNode",
        "method": "MethodNode",
        "attribute": "AttributeNode",
        "enumvalue": "EnumValueNode",
    }
    dtype = design_dict.get("type", "")
    dkind = design_dict.get("kind", "")
    if dkind and dkind in _KIND_TO_TYPE:
        expected_type = _KIND_TO_TYPE[dkind]
        if dtype and dtype != expected_type:
            log.warning(
                "_create_design_node_fresh: correcting type %s -> %s "
                "for %s (kind=%s)",
                dtype, expected_type,
                design_dict.get("qualified_name", "?"), dkind,
            )
            dtype = expected_type
            design_dict["type"] = expected_type

    qn = design_dict.get("qualified_name", "")
    dtype = design_dict.get("type", "")
    overlays_qn = design_dict.get("overlays_qualified_name", "")

    # ── Look-up targets (in priority order) ─────────────────────────
    lookup_targets: list[tuple[str, str]] = []
    if overlays_qn:
        lookup_targets.append((overlays_qn, "overlays_qualified_name"))
    if qn:
        lookup_targets.append((qn, "qualified_name"))

    # ── Try to find and overlay an existing node ────────────────────
    if lookup_targets and dtype and dtype in CodeGraphNode._registry:
        TargetCls = CodeGraphNode._registry[dtype]
        # Also try to find via the overlays target's own type — the
        # as-built node may be a different type (e.g. StructNode as-built
        # but the model wants it to be a ClassNode).
        for target_qn, source in lookup_targets:
            existing = _first_or_none(
                TargetCls.nodes.filter(qualified_name=target_qn)
            )
            if existing is None and overlays_qn:
                # Try with ANY registered type, not just TargetCls.
                for _cls in CodeGraphNode._registry.values():
                    try:
                        existing = _first_or_none(
                            _cls.nodes.filter(qualified_name=target_qn)
                        )
                        if existing is not None:
                            break
                    except Exception:
                        pass
            if existing is not None:
                # Overlay design tag and properties on the existing node.
                tags = list(existing.tags or [])
                if "design" not in tags:
                    tags.append("design")
                # Tag test-scaffolding types with "test" for DESIGN_API filtering.
                if dtype in ("TestNode", "AssertionNode", "TestStepNode",
                             "TestFixtureNode") and "test" not in tags:
                    tags.append("test")
                existing.tags = tags
                # Update descriptive properties from the design dict.
                for key in ("description", "kind", "name"):
                    val = design_dict.get(key)
                    if val:
                        setattr(existing, key, val)
                existing.save()
                log.info(
                    "Overlaid design on existing node "
                    "(%s=%s): %s (%s)",
                    source, target_qn, qn, dtype,
                )
                return True
        log.debug(
            "No existing node found for %s (tried %s)",
            qn, [t[0] for t in lookup_targets],
        )

    # ── Create fresh ────────────────────────────────────────────────
    node_data = dict(design_dict)
    tags = ["design"]
    # Tag test-scaffolding nodes with "test" so DESIGN_API views
    # can filter them out cleanly by tag rather than by node type.
    if dtype in ("TestNode", "AssertionNode", "TestStepNode",
                 "TestFixtureNode"):
        tags.append("test")
    node_data["tags"] = tags
    node_data.pop("composes", None)
    node_data.pop("overlays_qualified_name", None)
    try:
        node = CodeGraphNode.deserialize(node_data)
        node.save()
        log.info("Created design node: %s (%s)",
                 node_data.get("qualified_name", "?"),
                 node_data.get("type", "?"))
        return True
    except Exception as exc:
        log.warning("Failed to create design node %s: %s",
                     node_data.get("qualified_name", "?"), exc)
        return False


def _link_design_composes(flat_design: list[dict]) -> int:
    """Create COMPOSES edges between design nodes based on qualified-name hierarchy."""
    edges = 0
    qnames = {d.get("qualified_name", "") for d in flat_design}
    for d in flat_design:
        qn = d.get("qualified_name", "")
        if not qn or "::" not in qn:
            continue
        parent_qn = qn.rsplit("::", 1)[0]
        if not parent_qn or parent_qn not in qnames:
            continue
        try:
            suid = get_backend().graph.resolve_uid(parent_qn)
            tuid = get_backend().graph.resolve_uid(qn)
            if suid and tuid:
                get_backend().graph.merge_relationship(
                    suid, "COMPOSES", tuid,
                )
                edges += 1
        except Exception as exc:
            log.warning("Failed to COMPOSES %s → %s: %s", parent_qn, qn, exc)
    return edges


def _link_design_dependencies(flat_design: list[dict]) -> int:
    """Create DEPENDS_ON edges from design compounds to any target in Neo4j.

    Two sources of dependency information:

    1. **Explicit ``edges`` array**: Each design node may declare edges in
       its ``edges`` array with ``relation_type``, ``target_uid``, and
       ``target_type``.  These are trusted and created directly.
    2. **Type-signature scanning**: The ``type_signature`` and
       ``argsstring`` fields of member nodes are scanned for
       qualified-name references.

    Both sources can reference design compounds **or** existing as-built
    entities — targets are resolved against Neo4j via ``qualified_name``,
    not limited to the design compound set.

    References that don't resolve to any Neo4j node are silently skipped
    (the target may not be indexed yet, e.g. standard library types).

    Returns:
        Number of DEPENDS_ON edges created.
    """
    compound_types = {"ClassNode", "InterfaceNode", "EnumNode", "UnionNode", "ConceptNode"}

    # Primitive / standard-library types that should never become
    # DEPENDS_ON targets.
    _PRIMITIVES = frozenset({
        "bool", "int", "str", "void", "float", "double",
        "char", "size_t", "uint32_t", "uint64_t", "int32_t", "int64_t",
        "list", "dict", "set", "tuple", "Optional", "Vec", "vector",
        "map", "string", "String", "number", "boolean",
    })

    import re
    _QN_RE = re.compile(r"\b([a-zA-Z_]\w*(?:::\w+)+)\b")

    referenced: dict[str, set[str]] = {}  # source_qn → {target_qn, ...}

    for d in flat_design:
        source_qn = d.get("qualified_name", "")
        if not source_qn or d.get("type") not in compound_types:
            continue

        refs: set[str] = referenced.setdefault(source_qn, set())

        # ── 1. Explicit edges array (trusted, from produce_oo_design) ──
        for edge in d.get("edges", []):
            rel_type = edge.get("relation_type", "")
            if rel_type != "DEPENDS_ON":
                continue
            target_qn = edge.get("target_uid", "")
            if target_qn and target_qn != source_qn:
                refs.add(target_qn)

        # ── 2. Type-signature scanning ──────────────────────────────
        for member in d.get("composes", []):
            for field in ("type_signature", "argsstring"):
                text = member.get(field, "")
                if not text or text in _PRIMITIVES:
                    continue
                for match in _QN_RE.finditer(text):
                    qn = match.group(1)
                    if qn not in _PRIMITIVES and qn != source_qn:
                        refs.add(qn)

    # ── Create DEPENDS_ON edges, resolving targets via Neo4j ───────
    edges = 0
    seen: set[tuple[str, str]] = set()

    for source_qn, targets in referenced.items():
        for target_qn in targets:
            edge_key = (source_qn, target_qn)
            if edge_key in seen:
                continue
            seen.add(edge_key)
            try:
                suid = get_backend().graph.resolve_uid(source_qn)
                tuid = get_backend().graph.resolve_uid(target_qn)
                cnt = 0
                if suid and tuid:
                    cnt = get_backend().graph.merge_relationship(
                        suid, "DEPENDS_ON", tuid,
                    )
                if cnt:
                    edges += 1
                    log.info("DEPENDS_ON: %s → %s", source_qn, target_qn)
                else:
                    log.debug(
                        "DEPENDS_ON target not found in Neo4j: %s → %s",
                        source_qn, target_qn,
                    )
            except Exception as exc:
                log.warning("Failed to DEPENDS_ON %s → %s: %s",
                            source_qn, target_qn, exc)

    return edges


def _retag_remaining_scaffold() -> int:
    """Change ``tags`` from ``["scaffold"]`` to ``["design"]`` on scaffold
    nodes that still have verification edges."""
    repo = get_backend().requirements
    uids = repo.find_scaffold_uids(
        with_edges=["LEFT_OPERAND", "RIGHT_OPERAND", "CALLEE", "CALLER"],
    )
    retagged = 0
    for uid in uids:
        try:
            repo.retag_scaffold_to_design(uid)
            retagged += 1
        except Exception:
            pass
    if retagged:
        log.info("Re-tagged %d scaffold nodes (still referenced by edges) to design", retagged)
    return retagged


def _cleanup_orphaned_scaffold_nodes(hlr_uid: str) -> int:
    """Delete scaffold nodes that are no longer part of the design."""
    repo = get_backend().requirements
    cleaned = 0

    # 1. Orphans: zero relationships
    for uid in repo.find_scaffold_uids(without_edges=True):
        try:
            repo.delete_scaffold(uid)
            cleaned += 1
        except Exception:
            pass

    # 2. Stale children: scaffold with non-scaffold parent
    for uid in repo.find_scaffold_uids(parent_is_not_scaffold=True):
        try:
            repo.delete_scaffold(uid)
            cleaned += 1
        except Exception:
            pass

    if cleaned:
        log.info("Cleaned up %d scaffold nodes for HLR %s",
                 cleaned, hlr_uid[:8])
    return cleaned


def _reconcile_design_with_scaffold(
    hlr_uid: str,
    design_nodes: list[dict],
) -> dict:
    """Reconcile the design with existing scaffold nodes.

    Steps:
      1. Flatten the nested design node dicts.
      2. Fetch all scaffold nodes and index by last segment.
      3. Match design nodes to scaffold nodes by last segment.
      4. Update matched scaffold nodes in place.
      5. Create unmatched design nodes fresh with ``tags=["design"]``.
      6. Create ``COMPOSES`` edges between all design nodes.
      7. Re-tag scaffold ``LiteralNode`` s still referenced by edges.
      8. Clean up orphaned scaffold nodes.

    Returns:
        Dict with ``nodes_updated``, ``nodes_created``, ``edges_linked``,
        ``scaffold_retaged``, ``scaffold_cleaned``.
    """
    flat = _flatten_design_nodes(design_nodes)
    log.info("Reconciling design: %d flat nodes from %d root nodes",
             len(flat), len(design_nodes))

    # ── Separate namespaces from compounds ─────────────────────────
    # NamespaceNodes are handled by _create_design_namespaces which
    # uses get_or_none to reuse existing nodes (any tag).  We exclude
    # them from scaffold matching to avoid creating duplicates.
    compounds = [d for d in flat if d.get("type") != "NamespaceNode"]
    namespace_nodes = [d for d in flat if d.get("type") == "NamespaceNode"]
    if namespace_nodes:
        log.info("Design included %d explicit NamespaceNode(s): %s",
                 len(namespace_nodes),
                 [n.get("qualified_name", "") for n in namespace_nodes])

    # Infer missing namespace nodes from compound qualified_names.
    existing_qnames = {d.get("qualified_name", "") for d in flat}
    for d in compounds:
        qn = d.get("qualified_name", "")
        if "::" in qn:
            ns_qn = qn.split("::", 1)[0]
            if ns_qn not in existing_qnames:
                ns_dict = {
                    "qualified_name": ns_qn,
                    "name": ns_qn.rsplit("::", 1)[-1],
                    "type": "NamespaceNode",
                    "kind": "namespace",
                }
                namespace_nodes.append(ns_dict)
                existing_qnames.add(ns_qn)
                log.info("Inferred namespace node: %s", ns_qn)

    # Add inferred namespaces back to flat for _link_design_composes
    # and _create_design_namespaces — they were never scaffold nodes.
    flat = compounds + namespace_nodes

    scaffold_nodes = get_backend().graph.find_all_by_tag("scaffold")
    scaffold_by_seg: dict[str, list] = {}
    for sn in scaffold_nodes:
        qn = getattr(sn, "qualified_name", "") or ""
        seg = _last_segment(qn)
        if seg:
            scaffold_by_seg.setdefault(seg, []).append(sn)
    log.info("Found %d scaffold nodes indexed into %d segments",
             len(scaffold_nodes), len(scaffold_by_seg))

    matched_pairs: list[tuple[object, dict]] = []
    unmatched_design: list[dict] = []
    used_scaffold_eids: set[str] = set()

    for d in compounds:
        dqn = d.get("qualified_name", "")
        dseg = _last_segment(dqn)
        matched_sn = None
        if dseg and dseg in scaffold_by_seg:
            for sn in scaffold_by_seg[dseg]:
                sn_eid = sn.element_id
                if sn_eid not in used_scaffold_eids:
                    matched_sn = sn
                    used_scaffold_eids.add(sn_eid)
                    break
        if matched_sn is not None:
            matched_pairs.append((matched_sn, d))
        else:
            unmatched_design.append(d)

    log.info("Matched %d design nodes to scaffold, %d unmatched",
             len(matched_pairs), len(unmatched_design))

    nodes_updated = 0
    for sn, d in matched_pairs:
        if _update_scaffold_to_design(sn, d):
            nodes_updated += 1

    nodes_created = 0
    for d in unmatched_design:
        if _create_design_node_fresh(d):
            nodes_created += 1

    edges_linked = _link_design_composes(flat)
    deps_edges = _link_design_dependencies(flat)
    namespace_edges, nss_created, nss_reused = _create_design_namespaces(flat)
    scaffold_retaged = _retag_remaining_scaffold()
    scaffold_cleaned = _cleanup_orphaned_scaffold_nodes(hlr_uid)

    return {
        "nodes_updated": nodes_updated,
        "nodes_created": nodes_created,
        "edges_linked": edges_linked,
        "deps_edges": deps_edges,
        "namespace_edges": namespace_edges,
        "namespaces_created": nss_created,
        "namespaces_reused": nss_reused,
        "scaffold_retaged": scaffold_retaged,
        "scaffold_cleaned": scaffold_cleaned,
    }


def _persist_verifications(
    hlr_uid: str,
    verifications: dict[str, list[dict]],
) -> tuple[int, int]:
    """Persist VERIFIES and update CALLEE edges from resolved verifications.

    After the design agent resolves notional verification stubs
    to qualified design method names, this function:

    1. Creates ``VERIFIES`` edges from each TestNode to the design
       methods referenced in its actions' ``callee_qualified_name``.
    2. Updates existing TestStep ``CALLEE`` edges to point to the
       resolved design methods instead of scaffold stubs.

    Args:
        hlr_uid: The HLR's uid.
        verifications: Dict of LLR uid → list of verification dicts
            (same structure as ``DesignHLRResult.verifications``).

    Returns:
        (verifies_created, callee_updated) counts.
    """
    from codegraph.models.member import MemberNode

    verifies_created = 0
    callee_updated = 0

    for llr_uid, verif_list in verifications.items():
        llr = LLR.nodes.get_or_none(uid=llr_uid)
        if not llr:
            log.warning(
                "LLR %s not found for verification persistence",
                llr_uid[:8],
            )
            continue

        # Get all TestNodes for this LLR and index by test_name.
        tests = list(llr.verification_methods.all())
        test_by_name: dict[str, TestNode] = {}
        for t in tests:
            if t.test_name:
                # If duplicate test_names, prefer the first match.
                test_by_name.setdefault(t.test_name, t)

        for verif in verif_list:
            test_name = verif.get("test_name", "")
            test_node = test_by_name.get(test_name)
            if not test_node:
                log.warning(
                    "TestNode '%s' not found for LLR %s — skipping",
                    test_name, llr_uid[:8],
                )
                continue

            # ── 1. Create VERIFIES edges to callee methods ──────
            target_methods: set[str] = set()
            for action in verif.get("actions", []):
                callee_qn = action.get("callee_qualified_name", "")
                if callee_qn and "::" in callee_qn:
                    target_methods.add(callee_qn)

            for qn in sorted(target_methods):
                try:
                    test_uid = get_backend().graph.resolve_uid(
                        test_node.qualified_name
                    )
                    tuid = get_backend().graph.resolve_uid(qn)
                    if test_uid and tuid:
                        get_backend().graph.merge_relationship(
                            test_uid, "VERIFIES", tuid,
                        )
                        verifies_created += 1
                    log.debug(
                        "VERIFIES: %s → %s",
                        test_node.qualified_name, qn,
                    )
                except Exception as exc:
                    log.warning(
                        "VERIFIES edge failed: TestNode %s → %s: %s",
                        test_node.qualified_name, qn, exc,
                    )

            # ── 2. Update TestStep CALLEE edges ────────────────
            steps = sorted(test_node.steps.all(), key=lambda s: s.order)
            actions = verif.get("actions", [])
            for i, action in enumerate(actions):
                callee_qn = action.get("callee_qualified_name", "")
                if not callee_qn or "::" not in callee_qn:
                    continue
                if i >= len(steps):
                    log.warning(
                        "Action index %d out of range for TestNode %s "
                        "(%d steps)",
                        i, test_node.qualified_name, len(steps),
                    )
                    continue
                step = steps[i]
                try:
                    # Remove old CALLEE edge, create new one.
                    get_backend().execute_raw(
                        "MATCH (step:TestStepNode {qualified_name: $sqn})-[r:CALLEE]->() "
                        "DELETE r",
                        {"sqn": step.qualified_name},
                    )
                    step_uid = get_backend().graph.resolve_uid(step.qualified_name)
                    callee_uid = get_backend().graph.resolve_uid(callee_qn)
                    if step_uid and callee_uid:
                        get_backend().graph.merge_relationship(
                            step_uid, "CALLEE", callee_uid,
                        )
                        callee_updated += 1
                    log.debug(
                        "CALLEE updated: step %s → %s",
                        step.qualified_name, callee_qn,
                    )
                except Exception as exc:
                    log.warning(
                        "CALLEE update failed: step %s → %s: %s",
                        step.qualified_name, callee_qn, exc,
                    )

    log.info(
        "Verification persistence complete for HLR %s: "
        "%d VERIFIES edges, %d CALLEE edges updated",
        hlr_uid[:8], verifies_created, callee_updated,
    )
    return verifies_created, callee_updated


def _create_design_namespaces(flat_design: list[dict]) -> tuple[int, int, int]:
    """Ensure every design compound is composed under a NamespaceNode.

    Extracts namespace prefixes from qualified_names (everything before
    the last ``::``), creates/get-or-create a NamespaceNode for each,
    and MERGEs COMPOSES edges from the namespace to each top-level
    compound under it.

    Returns:
        Tuple of ``(edges_created, namespaces_created, namespaces_reused)``.
    """
    from codegraph.models.namespace import NamespaceNode
    from codegraph.models.tags import CodeGraphNode

    # Collect unique namespace prefixes from compound qualified_names.
    compound_types = {"ClassNode", "InterfaceNode", "EnumNode", "StructNode"}
    namespace_qns: set[str] = set()
    for d in flat_design:
        qn = d.get("qualified_name", "")
        if not qn or "::" not in qn:
            continue
        dtype = d.get("type", "")
        if dtype not in compound_types:
            continue
        prefix = qn.rsplit("::", 1)[0]
        if prefix:
            namespace_qns.add(prefix)

    if not namespace_qns:
        log.info("No namespace prefixes found in design — nothing to create")
        return 0, 0, 0

    edges = 0
    namespaces_created = 0
    namespaces_reused = 0
    for ns_qn in sorted(namespace_qns):
        # Get or create the NamespaceNode.
        ns_node = NamespaceNode.nodes.get_or_none(qualified_name=ns_qn)
        if ns_node is None:
            ns_name = ns_qn.rsplit("::", 1)[-1] if "::" in ns_qn else ns_qn
            try:
                ns_node = CodeGraphNode.deserialize({
                    "qualified_name": ns_qn,
                    "name": ns_name,
                    "type": "NamespaceNode",
                    "tags": ["design"],
                })
                ns_node.save()
                namespaces_created += 1
                log.info("Created design namespace: %s", ns_qn)
            except Exception as exc:
                log.warning("Failed to create namespace %s: %s", ns_qn, exc)
                continue
        else:
            namespaces_reused += 1
            if "design" not in (ns_node.tags or []):
                # Existing namespace — add design tag so it appears in
                # design-layer queries.
                try:
                    tags = list(ns_node.tags or [])
                    tags.append("design")
                    ns_node.tags = tags
                    ns_node.save()
                    log.info("Added 'design' tag to existing namespace: %s", ns_qn)
                except Exception as exc:
                    log.warning("Failed to tag namespace %s: %s", ns_qn, exc)

        # MERGE COMPOSES edges from namespace to each compound under it.
        for d in flat_design:
            dqn = d.get("qualified_name", "")
            if not dqn.startswith(ns_qn + "::"):
                continue
            dtype = d.get("type", "")
            if dtype not in compound_types:
                continue
            # Only top-level compounds (exactly one :: after namespace).
            remainder = dqn[len(ns_qn) + 2:]
            if "::" in remainder:
                continue
            try:
                suid = get_backend().graph.resolve_uid(ns_qn)
                tuid = get_backend().graph.resolve_uid(dqn)
                if suid and tuid:
                    get_backend().graph.merge_relationship(
                        suid, "COMPOSES", tuid,
                    )
                    edges += 1
            except Exception as exc:
                log.warning(
                    "Failed to COMPOSES %s → %s: %s", ns_qn, dqn, exc,
                )

    if edges:
        log.info(
            "Created %d namespace→compound COMPOSES edges "
            "for %d namespaces (%d created, %d reused)",
            edges, len(namespace_qns), namespaces_created, namespaces_reused,
        )
    return edges, namespaces_created, namespaces_reused


# ══════════════════════════════════════════════════════════════════════════
# Design artifact generation (markdown + PlantUML diagram)
# ══════════════════════════════════════════════════════════════════════════


def _generate_design_artifacts(hlr: HLR, design_nodes: list[dict]) -> dict:
    """Generate design.md and architecture_class_diagram.puml for an HLR.

    Derives the output directory from the HLR name (slugified) under
    ``codegraph/requirements/{hlr_slug}/``.  Loads the design LayerGraph
    from Neo4j for the namespace(s) found in the HLR's design compounds,
    exports to Markdown and PlantUML, and renders a PNG.

    Returns a dict with keys ``design_md``, ``puml``, ``png`` (paths or
    error messages).
    """
    import re
    import subprocess
    from pathlib import Path

    from codegraph.graph import LayerGraph
    from codegraph.export.markdown import MarkdownExporter
    from codegraph.export.plantuml import PlantUMLExporter

    result: dict = {"design_md": "", "requirements_md": "", "puml": "", "png": ""}

    # ── Derive output directory from HLR name ─────────────────────────
    hlr_name = hlr.name or "unnamed"
    slug = re.sub(r'[^a-z0-9]+', '-', hlr_name.lower()).strip('-')
    out_dir = Path("codegraph/requirements") / slug
    diagrams_dir = out_dir / "diagrams"

    try:
        diagrams_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        log.warning("Failed to create output dir %s: %s", diagrams_dir, exc)
        result["design_md"] = f"mkdir error: {exc}"
        result["puml"] = f"mkdir error: {exc}"
        return result

    # ── Find the namespace from HLR's design compounds ──────────────
    # After reconcile_design_nodes(), design compounds are persisted
    # to Neo4j and linked to the HLR.  Derive their namespace from
    # qualified_name and load the namespace subtree from Neo4j.
    from codegraph.models.tags import CodeGraphNode

    NamespaceNode = CodeGraphNode._registry.get("NamespaceNode")
    namespace_qn: str | None = None

    for dc in hlr.design_compounds.all():
        qn = getattr(dc, "qualified_name", None)
        if not qn:
            continue
        if "::" in qn:
            parts = qn.rsplit("::", 1)
        elif "." in qn:
            parts = qn.rsplit(".", 1)
        else:
            parts = [qn]
        if len(parts) == 2:
            namespace_qn = parts[0]
            break

    if not namespace_qn or not NamespaceNode:
        result["design_md"] = "no namespace found for HLR design compounds"
        result["puml"] = "no namespace found for HLR design compounds"
        return result

    # ── Load design LayerGraph, keep only the namespace ────────────
    try:
        full_graph = LayerGraph.from_neo4j(tag="design")
    except Exception as exc:
        exc_str = str(exc)
        # NodeClassNotDefined often means an EnumValueNode is missing
        # its parent MemberNode label — likely orphaned from its EnumNode.
        if "does not resolve to any of the known objects" in exc_str:
            log.warning(
                "Failed to load design LayerGraph — a node's labels do not "
                "match the neomodel class registry.  This often means an "
                "EnumValueNode was created without its parent MemberNode label. "
                "Error: %s", exc
            )
        else:
            log.warning("Failed to load design LayerGraph: %s", exc)
        result["design_md"] = f"LayerGraph load error: {exc}"
        result["puml"] = f"LayerGraph load error: {exc}"
        return result

    # Keep only root entries whose qualified_name falls under the
    # namespace.  Design compounds are persisted as individual nodes
    # (ClassNode, EnumNode, etc.); there is no separate NamespaceNode
    # unless one existed previously.  Filter by qualified_name prefix.
    prefix = namespace_qn + "::"
    filtered: dict = {}
    for key, entry in full_graph.entries.items():
        qn = getattr(entry.node, "qualified_name", "") or ""
        ntype = type(entry.node).__name__
        # NamespaceNode: exact match.
        if ntype == "NamespaceNode" and qn == namespace_qn:
            filtered[key] = entry
        # Top-level design compounds: prefix match.
        elif qn.startswith(prefix) and "::" not in qn[len(prefix):]:
            filtered[key] = entry

    if not filtered:
        result["design_md"] = (
            f"no design nodes found for namespace '{namespace_qn}' "
            f"in design graph ({len(full_graph.entries)} entries)"
        )
        result["puml"] = result["design_md"]
        return result

    log.info(
        "Filtered design graph: %d entries for namespace %s "
        "(from %d total)", len(filtered), namespace_qn,
        len(full_graph.entries),
    )

    # Also pull in external types referenced via DEPENDS_ON from
    # any kept entry or its children (e.g. codegraph.graph.LayerGraph).
    def _collect_referenced_keys(entry) -> set[str]:
        keys: set[str] = set()
        for rel_type, target_key, _ in entry.references:
            if rel_type == "DEPENDS_ON" and target_key in full_graph.entries:
                keys.add(target_key)
        for children in entry.children.values():
            for child in children.values():
                keys |= _collect_referenced_keys(child)
        return keys

    reference_keys: set[str] = set()
    for entry in filtered.values():
        reference_keys |= _collect_referenced_keys(entry)
    for key in reference_keys:
        if key not in filtered:
            filtered[key] = full_graph.entries[key]

    if not filtered:
        result["design_md"] = f"namespace {namespace_qn} not in design graph"
        result["puml"] = f"namespace {namespace_qn} not in design graph"
        return result

    graph = LayerGraph(tags=frozenset({"design"}), entries=filtered)
    log.info("Loaded namespace %s subtree for HLR %s", namespace_qn, hlr.name)

    # ── Export Markdown ──────────────────────────────────────────────
    try:
        exporter = MarkdownExporter(graph, public_only=True)
        md_text = exporter.export()
        md_path = out_dir / "design.md"
        md_path.write_text(md_text, encoding="utf-8")
        result["design_md"] = str(md_path)
        log.info("Wrote design markdown: %s (%d bytes)", md_path, len(md_text))
    except Exception as exc:
        log.warning("Failed to export design markdown: %s", exc)
        result["design_md"] = f"export error: {exc}"

    # ── Export Requirements Markdown (HLRs + LLRs only, no code) ─────
    try:
        from codegraph.persistence.repository import GraphRepository, _filter_graph_by_types
        repo = get_backend().graph
        req_graph = repo.get_hlr_subtree(hlr.uid)
        if req_graph.entries:
            # Strip design code (classes, attributes, etc.) — keep
            # requirements + test data: HLR, LLR, TestNode, AssertionNode,
            # TestStepNode, TestFixtureNode
            req_graph = _filter_graph_by_types(req_graph, frozenset({
                "HLR", "LLR", "TestNode", "AssertionNode",
                "TestStepNode", "TestFixtureNode",
            }))
            req_exporter = MarkdownExporter(req_graph, public_only=True)
            req_text = req_exporter.export()
            req_path = out_dir / "requirements.md"
            req_path.write_text(req_text, encoding="utf-8")
            result["requirements_md"] = str(req_path)
            log.info("Wrote requirements markdown: %s (%d bytes)", req_path, len(req_text))
    except Exception as exc:
        log.warning("Failed to export requirements markdown: %s", exc)
        result["requirements_md"] = f"export error: {exc}"

    # ── Export PlantUML ──────────────────────────────────────────────
    try:
        puml_exporter = PlantUMLExporter(graph)
        puml_text = puml_exporter.export()
        puml_path = diagrams_dir / "architecture_class_diagram.puml"
        puml_path.write_text(puml_text, encoding="utf-8")
        result["puml"] = str(puml_path)
        log.info("Wrote PlantUML diagram: %s (%d bytes)", puml_path, len(puml_text))

        # ── Render PNG ───────────────────────────────────────────
        try:
            subprocess.run(
                ["plantuml", "-tpng", "architecture_class_diagram.puml"],
                cwd=str(diagrams_dir.resolve()),
                capture_output=True,
                timeout=30,
                check=True,
            )
            png_path = diagrams_dir / "architecture_class_diagram.png"
            if png_path.exists():
                result["png"] = str(png_path)
                log.info("Rendered PNG: %s (%d bytes)", png_path,
                         png_path.stat().st_size)
            else:
                result["png"] = "plantuml ran but no PNG produced"
        except FileNotFoundError:
            result["png"] = "plantuml not installed"
        except subprocess.TimeoutExpired:
            result["png"] = "plantuml timed out"
        except subprocess.CalledProcessError as exc:
            result["png"] = f"plantuml error: {exc.stderr.decode()[:200] if exc.stderr else exc}"
    except Exception as exc:
        log.warning("Failed to export PlantUML: %s", exc)
        result["puml"] = f"export error: {exc}"

    return result


# ══════════════════════════════════════════════════════════════════════════
# Feedback file generation
# ══════════════════════════════════════════════════════════════════════════


def _generate_feedback_file(hlr: HLR) -> Path:
    """Generate a feedback.md file in the requirement directory for this HLR.

    Creates ``codegraph/requirements/{hlr_slug}/feedback.md`` with blank
    ``### Feedback`` sections under each LLR.  If a feedback file already
    exists, it is preserved as-is (not overwritten).

    Returns the path to the feedback file.
    """
    import re
    from pathlib import Path

    hlr_name = hlr.name or "unnamed"
    slug = re.sub(r'[^a-z0-9]+', '-', hlr_name.lower()).strip('-')
    out_dir = Path("codegraph/requirements") / slug
    feedback_path = out_dir / "feedback.md"

    # If feedback file already exists, preserve user edits
    if feedback_path.exists():
        log.info(
            "_generate_feedback_file: feedback.md already exists at %s — skipping",
            feedback_path,
        )
        return feedback_path

    try:
        out_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        log.warning("Failed to create output dir %s: %s", out_dir, exc)
        return feedback_path

    # Load LLRs from Neo4j
    llrs = list(hlr.llrs.all())

    lines = []
    lines.append(f"# {hlr_name}")
    lines.append("")
    lines.append(
        "> **Source**: Neo4j codegraph, `design` tag — deterministic, "
        "no LLM enrichment"
    )
    lines.append(
        "> **Cycle**: export → review → update Neo4j → archive → re-export"
    )
    lines.append("")
    if hlr.description:
        lines.append(hlr.description.strip())
    lines.append("")
    lines.append("---")
    lines.append("")

    for llr in llrs:
        llr_name = llr.name or llr.uid or "(unnamed)"
        # Truncate long UUID-style names for readability
        if len(llr_name) > 50 and llr_name[:8].isalnum():
            llr_name = llr_name[:8]
        lines.append(f"## {llr_name}")
        lines.append("")
        if llr.description:
            lines.append(llr.description.strip())
        else:
            lines.append("_(no description available)_")
        lines.append("")
        lines.append("### Feedback")
        lines.append("")
        lines.append(
            "<!-- Write your feedback on this requirement below. -->"
        )
        lines.append("")

    text = "\n".join(lines)
    feedback_path.write_text(text, encoding="utf-8")
    log.info(
        "_generate_feedback_file: wrote %d bytes to %s",
        len(text), feedback_path,
    )
    return feedback_path


# ══════════════════════════════════════════════════════════════════════════
# Full entry point — context loading + pipeline + persistence
# ══════════════════════════════════════════════════════════════════════════

def design_and_persist_hlr(
    hlr_uid: str,
    *,
    log_dir: str = "",
) -> dict:
    """Design a single HLR end-to-end: load context → design + verify → persist.

    Args:
        hlr_uid: The HLR's ``uid`` (deterministic unique ID).
        log_dir: Directory for per-step prompt logs.

    Returns:
        Dict with keys ``nodes_updated``, ``nodes_created``, ``edges_linked``,
        ``verifications_resolved``, ``conditions_created``, ``actions_created``,
        ``links_applied``, ``scaffold_retaged``, ``scaffold_cleaned``.
    """
    # ── Ensure agent-internal context logging is visible ──────────────
    for _lname in (
        "codegraph_design.tools.design_tools",
        "codegraph_design.tools.dispatcher",
        "codegraph_design.agents.design_oo",
    ):
        logging.getLogger(_lname).setLevel(logging.INFO)

    log.info("design_and_persist_hlr: loading HLR %s", hlr_uid[:16])
    hlr = HLR.nodes.get_or_none(uid=hlr_uid)
    if not hlr:
        raise ValueError(f"HLR {hlr_uid} not found")

    # --- Guard: refuse re-design if HLR already has design compounds ---
    existing_design = list(hlr.design_compounds.all())
    if existing_design:
        raise ValueError(
            f"HLR {hlr_uid[:8]} already has {len(existing_design)} design compound(s) — "
            f"design has already been run. To re-design, delete the existing design "
            f"compounds first, or call design_hlr() directly if you need to iterate."
        )

    llr_nodes = hlr.llrs.all()
    if not llr_nodes:
        raise ValueError(f"HLR {hlr_uid} has no LLRs — decompose it first")
    log.info(
        "design_and_persist_hlr: found HLR %s with %d LLRs",
        hlr_uid[:8], len(llr_nodes),
    )

    comp_nodes = hlr.component.all()
    component_namespace = getattr(comp_nodes[0], "namespace", "") if comp_nodes else ""

    sibling_namespaces: list[str] = []
    for s in HLR.nodes.all():
        if s.uid == hlr_uid:
            continue
        sc = s.component.all()
        if sc:
            ns = getattr(sc[0], "namespace", "")
            if ns and ns not in sibling_namespaces:
                sibling_namespaces.append(ns)

    context_classes: list[dict] = []
    for other_hlr in HLR.nodes.all():
        if other_hlr.uid == hlr_uid:
            continue
        for target in other_hlr.design_compounds.all():
            context_classes.append({
                "qualified_name": target.qualified_name,
                "name": target.name or "",
                "kind": getattr(target, "kind", "class"),
            })

    log.info("design_and_persist_hlr: running design_hlr for %s", hlr_uid[:8])
    result = design_hlr(
        hlr=hlr,
        llrs=llr_nodes,
        context_classes=context_classes or None,
        component_namespace=component_namespace,
        sibling_namespaces=sibling_namespaces or None,
        log_dir=log_dir,
    )
    log.info(
        "design_and_persist_hlr: design_hlr returned %d design nodes, %d LLR verifications",
        len(result.design), len(result.verifications),
    )

    # Reconcile design with scaffold
    recon = {"nodes_updated": 0, "nodes_created": 0, "edges_linked": 0, "deps_edges": 0,
             "scaffold_retaged": 0, "scaffold_cleaned": 0}
    if result.design:
        try:
            recon = _reconcile_design_with_scaffold(hlr_uid, result.design)
        except Exception as exc:
            log.warning("Design reconciliation failed for HLR %s: %s",
                        hlr_uid[:8], exc, exc_info=True)

    verifications_resolved = len(result.verifications)
    conditions_created = 0
    actions_created = 0
    for llr_uid, verif_list in result.verifications.items():
        for v in verif_list:
            conditions_created += len(v.get("preconditions", []))
            conditions_created += len(v.get("postconditions", []))
            actions_created += len(v.get("actions", []))

    # Persist VERIFIES edges from TestNodes → design methods and update
    # TestStep CALLEE edges from scaffold stubs to resolved design names.
    verifies_persisted = 0
    callees_updated = 0
    if result.verifications:
        try:
            verifies_persisted, callees_updated = _persist_verifications(
                hlr_uid, result.verifications
            )
        except Exception as exc:
            log.warning(
                "Verification persistence failed for HLR %s: %s",
                hlr_uid[:8], exc, exc_info=True,
            )

    # Create COMPOSES edges from HLR to top-level design compounds
    links_applied = 0
    from codegraph.models.compound import CompoundNode

    for node_dict in result.design:
        qn = node_dict.get("qualified_name", "")
        if not qn:
            continue
        kind = node_dict.get("kind", "")
        if kind not in ("class", "struct", "interface", "enum"):
            continue
        target_node = _first_or_none(
            CompoundNode.nodes.filter(qualified_name=qn)
        )
        if not target_node:
            continue
        try:
            hlr.design_compounds.connect(target_node)
            links_applied += 1
        except Exception as exc:
            node_cls = type(target_node).__name__
            node_labels = list(target_node.labels) if hasattr(target_node, 'labels') else ['?']
            node_type = node_dict.get("type", "?")
            node_kind = node_dict.get("kind", "?")
            log.warning("Failed to COMPOSES link HLR %s -> %s (design type=%s, kind=%s): %s (node class: %s, labels: %s)",
                        hlr_uid[:8], qn, node_type, node_kind, exc, node_cls, node_labels)

    log.info(
        "Design+verify complete for HLR %s: %d nodes updated, %d created, "
        "%d COMPOSES edges, %d DEPENDS_ON edges, %d verifications resolved, %d VERIFIES persisted, "
        "%d CALLEE updated, %d conditions, %d actions, "
        "%d scaffold retaged, %d scaffold cleaned",
        hlr_uid[:8], recon["nodes_updated"], recon["nodes_created"],
        recon["edges_linked"], recon["deps_edges"], verifications_resolved,
        verifies_persisted, callees_updated,
        conditions_created, actions_created,
        recon["scaffold_retaged"], recon["scaffold_cleaned"],
    )

    # ── Generate design artifacts (markdown + PlantUML diagram) ──────
    artifacts = _generate_design_artifacts(hlr, result.design)

    # ── Generate feedback file in requirements directory ───────────
    feedback_path = _generate_feedback_file(hlr)

    return {
        "nodes_updated": recon["nodes_updated"],
        "nodes_created": recon["nodes_created"],
        "edges_linked": recon["edges_linked"],
        "deps_edges": recon["deps_edges"],
        "verifications_resolved": verifications_resolved,
        "verifies_persisted": verifies_persisted,
        "callees_updated": callees_updated,
        "conditions_created": conditions_created,
        "actions_created": actions_created,
        "links_applied": links_applied,
        "scaffold_retaged": recon["scaffold_retaged"],
        "scaffold_cleaned": recon["scaffold_cleaned"],
        "artifacts": artifacts,
        "feedback_file": str(feedback_path),
        "status": "designed",
    }
