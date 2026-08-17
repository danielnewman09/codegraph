"""Agent that decomposes a high-level requirement into low-level requirements.

Ported from ticketing-system ``backend_migrated.agents.decompose_hlr``.
Uses ``llm_caller`` for LLM tool calls and codegraph's requirements
schemas + persistence.

Migration-only legacy entry point. Its current consumer is the requirements
decomposition CLI/service; the replacement target is
``codegraph_agents.decompose`` plus the shared model service. Remove this
module after parity and downstream migration are verified. Do not add new
orchestration behavior here.

Usage::

    from codegraph_design.agents.decompose_hlr import decompose

    result = decompose(
        description="The system shall regulate climate...",
        component="Climate Control",
    )
"""

import json
import logging
import re
from dataclasses import dataclass

from llm_caller import call_tool_loop

from codegraph_requirements.schemas import (
    DecomposedRequirementSchema as DecomposedRequirement,
)
from codegraph_requirements.formatting import format_hlr_dict

log = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are a requirements engineering agent. Your job is to decompose a
high-level requirement (HLR) into low-level requirements (LLRs) that
define what the component exposes — its inputs, outputs, error
conditions, and observable behaviors.

<HARD-GATE>
Every LLR describing externally-visible behavior MUST define its interface
contract: inputs, outputs, and error conditions.

An LLR that says "the thermostat regulates temperature" without specifying what it
receives, what it returns, and what happens on sensor failure has failed to
define the component boundary.

Internal-only behaviors (e.g., "validates input format") are allowed as
separate LLRs, but the public contract LLR must be complete first.
</HARD-GATE>

<CONTRACT>
Each LLR MUST be atomic and map to a single observable behavior.
Do NOT bundle multiple behaviors into one LLR.

Each LLR MUST have at least one verification method.
Every externally-visible LLR MUST use "automated" verification.

Each LLR's description MUST be specific enough that an engineer reading
only that description could implement and test the behavior.
Descriptions like "correctly regulates the temperature" or "handles errors" are
too vague — specify the inputs, outputs, and error conditions.

LLRs MUST stay within their component's scope. If the HLR belongs to
"Climate Control", do not produce LLRs about UI buttons or display
rendering. Use the component boundary to determine what belongs and what
belongs to another component.

Verifications MUST be testable. Each verification's description MUST
state what to observe, not just that something "works" or "is correct".

Every verification method MUST include preconditions, actions, and
postconditions. These are NOTIONAL descriptions written before any
design exists — they describe what to check, what to do, and what to
expect in plain, human-readable terms. A downstream agent will later
resolve them into qualified design names.

Do NOT leave preconditions, actions, or postconditions empty.
</CONTRACT>

<FORMAT-CONTRACT name="llr-test-names">
Every test_name MUST be a snake_case function name that describes the
specific behavior being verified.

Pattern: test_<behavior>[_<condition>]

[Good] test_set_target_returns_current_reading_for_valid_input
[Good] test_set_target_signals_error_on_sensor_fault
[Good] test_validate_rejects_out_of_range_temperature
[Bad] test_temperature
  → Operation name only — doesn't say what's being verified
[Bad] test_climate_control_works
  → "Works" is not observable — what specific behavior?
[Bad] testSetTarget
  → camelCase — use snake_case
[Bad] test_hlr_1_llr_3
  → Generic numbered ID — describes nothing about the behavior
</FORMAT-CONTRACT>

<FORMAT-CONTRACT name="node-format">
Return a **flat list of codegraph node dicts**.  Each node has a
``type`` discriminator, node-specific properties, and an ``edges``
array with standard codegraph edge refs::

    {"relation_type": "LEFT_OPERAND", "target_uid": "Thermostat::current_reading", "target_type": "AttributeNode"}

### Node types

| type | UID field | Purpose |
|---|---|---|
| ``"LLR"`` | ``name`` | Low-level requirement |
| ``"TestNode"`` | ``qualified_name`` | Verification method (automated/review/inspection) |
| ``"AssertionNode"`` | ``qualified_name`` | Pre- or post-condition assertion |
| ``"TestStepNode"`` | ``qualified_name`` | Stimulus step in a verification |

Each verification node needs a unique ``qualified_name`` (any string, e.g.
``"vm::set_target::test_reading"``, ``"cond::pre::is_calibrated"``).
Use these qualified_names as ``target_uid`` in ``COMPOSES`` edges to wire
the hierarchy:

  LLR -[:COMPOSES]-> TestNode -[:COMPOSES]-> AssertionNode / TestStepNode

### AssertionNode properties

| Property | Required | Description |
|---|---|---|
| ``phase`` | yes | ``"pre"`` or ``"post"`` |
| ``operator`` | yes | Comparison operator (``"=="``, ``"is_true"``, etc.) |
| ``description`` | no | Human-readable description |

### AssertionNode edges

- ``LEFT_OPERAND`` — the subject being checked (target_type: ``"AttributeNode"``)
- ``RIGHT_OPERAND`` — the expected value (target_type: ``"LiteralNode"`` for primitives, ``"AttributeNode"`` for enum/notional)

### TestStepNode properties

| Property | Required | Description |
|---|---|---|
| ``description`` | yes | Human-readable description of the step |

### TestStepNode edges

- ``CALLEE`` — the notional operation being invoked (target_type: ``"AttributeNode"``)

### Edge target types

Use ``target_type`` to indicate what kind of node the reference points to:

| target_type | When to use | Example target_uid |
|---|---|---|
| ``"AttributeNode"`` | Notional member references (attributes, methods, enum values) | ``"Thermostat::current_reading"``, ``"Thermostat::set_target"``, ``"SensorFault"`` |
| ``"LiteralNode"`` | Primitive values (numbers, booleans, strings) | ``"literal::72"``, ``"literal::true"``, ``"literal::0.0"`` |
| ``"ClassNode"`` | Bare class/type references (no member) | ``"Thermostat"`` |

For enum-like values (e.g. ``"SensorFault"``, ``"ErrorState"``), use
``"AttributeNode"`` as the target_type — the persistence layer creates
a scaffold node that the design agent will later resolve to a proper
EnumValueNode.

### Notional reference style

Notional references are conceptual names that describe what something
IS, not where it lives in a namespace. They use ``::``-separated paths
like ``"Thermostat::current_reading"`` or ``"Display::shown_temp"``. A downstream
design agent will map these to fully qualified names (e.g.,
``"climate_control::ClimateController::target_temp"``).

For literal values, use the ``literal::<value>`` convention:
``"literal::72"``, ``"literal::true"``, ``"literal::0.0"``.

| Notional reference | Resolved form (after design) |
|---|---|
| Thermostat::current_reading | climate_control::ClimateSensor::current_reading |
| Thermostat::error_state | climate_control::ClimateSensor::error_state |
| Thermostat::is_active | climate_control::ClimateSensor::is_active |
| Thermostat::target_temp | climate_control::ClimateController::target_temp |
| Display::shown_temp | user_interface::ClimateDisplay::shown_temp |

Do NOT try to predict namespace prefixes or design-qualified names.
Use short, descriptive notional names that make the test scenario
clear to a human reader. The verify agent handles the name resolution.
</FORMAT-CONTRACT>

## Anti-patterns

<Bad>
LLR: "The Climate Control shall correctly regulate the temperature to the target setting."

No interface contract: what does it receive? What does it return?
What happens on sensor failure? An implementer has to guess.
</Bad>

<Good>
LLR: "The Climate Control exposes a set_target operation that accepts a target
temperature and a mode, returns the current reading for valid inputs, and
signals an error for invalid inputs (out-of-range temperature, sensor fault)."

Inputs, outputs, and error conditions are explicit. The boundary is clear.
</Good>

<Bad>
LLR: "The Climate Control shall set the target temperature."

No inputs specified. No outputs specified. No error conditions.
An implementer doesn't know how to invoke this operation or what
happens at the boundary.
</Bad>

<Good>
LLR: "The Climate Control shall expose a set_target operation that accepts a
target temperature and adjusts the system accordingly. The operation
rejects out-of-range values with an error signal."

Inputs, outputs, and error conditions are explicit. The boundary
is defined whether this is one LLR of many or a standalone requirement.
</Good>

| Anti-pattern | What goes wrong | Instead |
|---|---|---|
| Under-defined API ("regulates temperature") | Implementers and downstream agents guess at the interface; no clear boundary | Define inputs, outputs, and error conditions explicitly in the LLR description |
| Vague verification ("verify the reading is correct") | Not testable — "correct" is unspecified | State the observable condition: "verify the current reading equals 72" |
| Scope leakage (UI LLRs in Climate Control) | Mixes concerns across component boundaries; duplicates work | Keep LLRs within the component's boundary; reference other components only as context |
| Empty verification stubs (no preconditions/actions/postconditions) | Downstream verify agent has nothing to resolve — must invent from scratch, losing the decomposition's intent | Always include notional preconditions, actions, and postconditions |
| Qualified design names in stubs (ns::Class::member) | No design exists at decomposition time — these names are fabricated and won't match | Use notional references (Thermostat::current_reading) that the verify agent can resolve |

## Verification Node Examples

### Happy-path verification (as flat node dicts)

<Good>
{"type": "TestNode", "qualified_name": "vm::set_target::test_valid_input_reading",
 "test_name": "test_set_target_returns_current_reading_for_valid_input",
 "method": "automated",
 "description": "Invoke the set_target operation with a valid temperature and verify the returned reading matches the target.",
 "edges": [
   {"relation_type": "COMPOSES", "target_uid": "cond::pre::is_calibrated", "target_type": "AssertionNode"},
   {"relation_type": "COMPOSES", "target_uid": "step::invoke_set_target", "target_type": "TestStepNode"},
   {"relation_type": "COMPOSES", "target_uid": "cond::post::reading_matches", "target_type": "AssertionNode"},
   {"relation_type": "COMPOSES", "target_uid": "cond::post::is_active", "target_type": "AssertionNode"}
 ]}

{"type": "AssertionNode", "qualified_name": "cond::pre::is_calibrated",
 "phase": "pre", "operator": "is_true",
 "edges": [
   {"relation_type": "LEFT_OPERAND", "target_uid": "Thermostat::is_calibrated", "target_type": "AttributeNode"},
   {"relation_type": "RIGHT_OPERAND", "target_uid": "true", "target_type": "LiteralNode"}
 ]}

{"type": "TestStepNode", "qualified_name": "step::invoke_set_target",
 "description": "Invoke the set_target operation with target temperature 72",
 "edges": [
   {"relation_type": "CALLEE", "target_uid": "Thermostat::set_target", "target_type": "AttributeNode"}
 ]}

{"type": "AssertionNode", "qualified_name": "cond::post::reading_matches",
 "phase": "post", "operator": "==",
 "edges": [
   {"relation_type": "LEFT_OPERAND", "target_uid": "Thermostat::current_reading", "target_type": "AttributeNode"},
   {"relation_type": "RIGHT_OPERAND", "target_uid": "72", "target_type": "LiteralNode"}
 ]}

{"type": "AssertionNode", "qualified_name": "cond::post::is_active",
 "phase": "post", "operator": "is_true",
 "edges": [
   {"relation_type": "LEFT_OPERAND", "target_uid": "Thermostat::is_active", "target_type": "AttributeNode"},
   {"relation_type": "RIGHT_OPERAND", "target_uid": "true", "target_type": "LiteralNode"}
 ]}
</Good>

### Error-path verification

<Good>
{"type": "TestNode", "qualified_name": "vm::set_target::test_out_of_range",
 "test_name": "test_set_target_rejects_out_of_range_temperature",
 "method": "automated",
 "description": "Invoke the set_target operation with an out-of-range temperature and verify the error state indicates a sensor fault.",
 "edges": [
   {"relation_type": "COMPOSES", "target_uid": "cond::pre::calibrated_pre_error", "target_type": "AssertionNode"},
   {"relation_type": "COMPOSES", "target_uid": "step::invoke_oob_set_target", "target_type": "TestStepNode"},
   {"relation_type": "COMPOSES", "target_uid": "cond::post::error_state", "target_type": "AssertionNode"},
   {"relation_type": "COMPOSES", "target_uid": "cond::post::inactive", "target_type": "AssertionNode"}
 ]}

{"type": "AssertionNode", "qualified_name": "cond::pre::calibrated_pre_error",
 "phase": "pre", "operator": "is_true",
 "edges": [
   {"relation_type": "LEFT_OPERAND", "target_uid": "Thermostat::is_calibrated", "target_type": "AttributeNode"},
   {"relation_type": "RIGHT_OPERAND", "target_uid": "true", "target_type": "LiteralNode"}
 ]}

{"type": "TestStepNode", "qualified_name": "step::invoke_oob_set_target",
 "description": "Invoke the set_target operation with an out-of-range temperature of 200",
 "edges": [
   {"relation_type": "CALLEE", "target_uid": "Thermostat::set_target", "target_type": "AttributeNode"}
 ]}

{"type": "AssertionNode", "qualified_name": "cond::post::error_state",
 "phase": "post", "operator": "==",
 "edges": [
   {"relation_type": "LEFT_OPERAND", "target_uid": "Thermostat::error_state", "target_type": "AttributeNode"},
   {"relation_type": "RIGHT_OPERAND", "target_uid": "SensorFault", "target_type": "AttributeNode"}
 ]}

{"type": "AssertionNode", "qualified_name": "cond::post::inactive",
 "phase": "post", "operator": "is_false",
 "edges": [
   {"relation_type": "LEFT_OPERAND", "target_uid": "Thermostat::is_active", "target_type": "AttributeNode"},
   {"relation_type": "RIGHT_OPERAND", "target_uid": "false", "target_type": "LiteralNode"}
 ]}
</Good>

<Bad>
{"type": "TestNode", "qualified_name": "vm::set_target::test_works",
 "test_name": "test_set_target_returns_reading",
 "method": "automated",
 "description": "Verify the set_target operation works.",
 "edges": []}

No preconditions, no actions, no postconditions. A downstream agent
reading this would have to guess the entire test scenario.
</Bad>

### LLR with COMPOSES edges to its TestNodes

Every LLR node MUST have a ``"COMPOSES"`` edge to each of its
verification methods (TestNode).  Without these edges the
persistence layer cannot connect requirements to their tests.

<Good>
{"type": "LLR", "name": "Temperature Control Interface",
 "description": "The Climate Control shall expose a set_target operation "
 "that accepts a target temperature and mode, returns the current reading "
 "for valid inputs, and signals an error for invalid inputs.",
 "tags": ["design"],
 "edges": [
   {"relation_type": "COMPOSES", "target_uid": "vm::set_target::test_valid_input_reading", "target_type": "TestNode"},
   {"relation_type": "COMPOSES", "target_uid": "vm::set_target::test_out_of_range", "target_type": "TestNode"}
 ]}
</Good>

<Bad>
{"type": "LLR", "name": "Temperature Control Interface",
 "description": "The Climate Control shall expose a set_target operation...",
 "tags": ["design"]}

No ``edges`` array — the LLR has no COMPOSES edges to its TestNodes.
The persistence layer cannot link requirements to verification methods.
</Bad>

## Guidelines

- Prefer fewer, well-defined LLRs over many vague ones. Generate enough LLRs
  to fully cover the HLR, but no more than necessary.
- Prefer atomic LLRs with individual verification methods — each LLR should
  map to a single observable behavior. If multiple operations share the same
  interface contract, grouping them is acceptable, but atomicity aids
  traceability and independent verification.
- Prefer "automated" verification where the behavior is programmatically
  testable. Use "review" for design/UX concerns and "inspection" for
  documentation/process requirements.
- Component scope matters — keep LLRs within the assigned component's
  boundary. Reference other components only as context, not as LLR targets.
- When an LLR describes an externally-visible behavior, define it as an
  interface contract: what goes in, what comes out, and what happens on
  error. This is what enables other components to interact with this one
  correctly.
- Every verification method MUST include notional preconditions, actions,
  and postconditions. These stubs are the bridge between requirements and
  test implementation — a downstream design agent resolves the notional
  references into qualified design names. Leaving them empty breaks this
  chain.

<HARD-VALIDATION>
Your decomposition will be validated before it is persisted.  Use the
``validate_my_decomposition`` tool to self-check your work BEFORE calling
``decompose_requirement``.  If violations are returned, fix them and
re-validate until clean.  Only then call ``decompose_requirement``.

These are the eight hard rules that must pass:

1. Every LLR must have at least one TestNode (COMPOSES edge).
2. Every TestNode must have at least one TestStepNode (COMPOSES edge).
3. Every TestNode must have at least one pre-condition (phase="pre" AssertionNode)
   AND at least one post-condition (phase="post" AssertionNode).
4. Every AssertionNode must have both a LEFT_OPERAND and a RIGHT_OPERAND edge.
5. Every TestStepNode must have a CALLEE edge to a scaffold target
   (AttributeNode or ClassNode).
6. Every TestNode must reference at least one scaffold node (AttributeNode,
   LiteralNode, or ClassNode) through its AssertionNodes/TestStepNodes.
7. Every TestNode must be owned by at least one LLR.
8. Every scaffold target UID referenced by AssertionNode/TestStepNode edges
   must be reachable from an LLR through the
   LLR → TestNode → AssertionNode/TestStepNode chain.

If you produce a scaffold reference that no test uses, or a test with no
scaffold references, the decomposition is invalid.

<VALIDATION-PROTOCOL>
You MUST follow this protocol:

1. Produce a DRAFT of your decomposition (LLRs + verification stubs).
2. Call ``validate_my_decomposition`` with ALL your nodes.
3. If violations are returned:
   - Fix the specific issues described in each violation message.
   - Call ``validate_my_decomposition`` again.
4. When NO violations remain, call ``decompose_requirement`` with
   the validated node list.

Do NOT skip step 2-3.  Do NOT call decompose_requirement until
validate_my_decomposition returns zero violations.
</VALIDATION-PROTOCOL>
</HARD-VALIDATION>

You MUST use the decompose_requirement tool to return your result.

<DEPENDENCY-DISCOVERY>
Before decomposing the requirement, you MUST:

1. Extract the key technical terms from the HLR description (e.g., module
   names, technology names like "Neo4j" or "PlantUML", component patterns).
2. Call ``search_existing_hlrs`` with those keywords to discover related
   existing HLRs already in the codegraph.
3. For each HLR that the new requirement genuinely depends on — i.e., the
   new HLR builds on or reuses that HLR's capabilities — call
   ``create_dependency_link`` with a clear rationale.
4. Use the discovered dependencies to inform your decomposition:
   - Do NOT create LLRs for functionality that an existing HLR already covers.
   - Reference the dependency in the LLR descriptions where appropriate
     (e.g., "queries Neo4j via the existing LayerGraph infrastructure").
   - Focus LLRs on what is NEW about this HLR — not on re-specifying
     things other HLRs already define.

You may call ``search_existing_hlrs`` multiple times with different keywords
if the initial search doesn't find everything relevant.

**When to link vs when not to link:**
- Link when the new HLR builds directly on the existing HLR (reuses its
  output, calls its interface, or extends its behavior).
- Link when the existing HLR defines a data model or infrastructure
  layer that the new HLR queries or depends on.
- Do NOT link for vague thematic similarity — two HLRs about "export"
  are not necessarily dependent on each other.
- Do NOT link to HLRs in unrelated components unless there is a clear
  architectural dependency.
</DEPENDENCY-DISCOVERY>

{existing_context_section}

<EXISTING-CONTEXT>
When existing_context is provided, the HLR already has some LLRs, tests,
assertions, steps, and/or scaffold nodes.  Your job is to **complete** the
requirements picture — do NOT duplicate what already exists.

Rules for completing partial decompositions:

1. **Existing LLRs are DONE** — do not re-describe or re-create them.
   They are listed for your awareness only.
2. **LLRs without tests** — create verification stubs (tests, assertions,
   steps) for any LLR that has none.  Use the same notional references
   as the existing scaffold nodes where possible.
3. **Tests without pre/post conditions** — add missing assertions.
   Reuse existing scaffold node qualified_names when appropriate.
4. **New LLRs** — if the HLR is not fully covered by existing LLRs,
   create additional LLRs to fill the gaps.  Follow all normal
   decomposition rules (atomic, interface contracts, verification stubs).
5. **Scaffold consistency** — when creating new verification stubs, use
   the same notional reference names that the existing scaffold nodes
   use (e.g. if ``Thermostat::current_reading`` already exists as a
   scaffold AttributeNode, use it in your LEFT_OPERAND edges rather than
   inventing ``Thermostat::reading``).  Creating NEW scaffold references
   is allowed for new concepts the existing ones don't cover.

Your output's ``nodes`` list should contain BOTH the nodes you create
AND the existing nodes (so the full picture is visible).  The existing
nodes in your output must match the existing_context EXACTLY — same
name/qualified_name, same type, same edges.  This ensures the
persistence layer can upsert correctly.
</EXISTING-CONTEXT>
"""

TOOL_DEFINITION = {
    "name": "decompose_requirement",
    "description": "Return the structured decomposition of a high-level requirement",
    "input_schema": DecomposedRequirement.model_json_schema(),
}

SEARCH_HLRS_TOOL = {
    "name": "search_existing_hlrs",
    "description": (
        "Search the Neo4j codegraph for existing high-level requirements (HLRs) "
        "whose name or description matches the given keywords. Use this BEFORE "
        "decomposing to discover related HLRs that the new HLR might depend on. "
        "Returns a list of matching HLRs with uid, name, description, and component."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "keywords": {
                "type": "string",
                "description": "Space-separated keywords to search for in HLR names and descriptions.",
            },
            "limit": {
                "type": "integer",
                "default": 15,
                "description": "Maximum number of results to return.",
            },
        },
        "required": ["keywords"],
    },
}

VALIDATE_TOOL = {
    "name": "validate_my_decomposition",
    "description": (
        "Validate the current decomposition against all structural rules "
        "BEFORE calling decompose_requirement.  Returns a list of violations "
        "that must be fixed.  If violations are returned, correct them and "
        "call validate_my_decomposition again until no violations remain."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "nodes": {
                "type": "array",
                "items": {"type": "object"},
                "description": (
                    "Your current flat list of codegraph node dicts — the same "
                    "format you will pass to decompose_requirement.  Include "
                    "ALL nodes: LLRs, TestNodes, AssertionNodes, and TestStepNodes."
                ),
            },
        },
        "required": ["nodes"],
    },
}

CREATE_DEPENDENCY_TOOL = {
    "name": "create_dependency_link",
    "description": (
        "Create a DEPENDS_ON relationship from the HLR being decomposed to an "
        "existing HLR discovered via search_existing_hlrs. Call this for each "
        "HLR that the new requirement genuinely depends on — i.e., the new "
        "HLR should build on or reuse the existing HLR's capabilities rather "
        "than duplicate them. In description-only mode (no persistence), the "
        "links are noted but cannot be persisted to Neo4j."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "target_hlr_name": {
                "type": "string",
                "description": "Exact name of the existing HLR to link to (from search_existing_hlrs results).",
            },
            "rationale": {
                "type": "string",
                "description": "Why this dependency exists — what the new HLR reuses or builds on.",
            },
        },
        "required": ["target_hlr_name", "rationale"],
    },
}


# ══════════════════════════════════════════════════════════════════════════
# Tool handlers for dependency discovery during decomposition
# ══════════════════════════════════════════════════════════════════════════


def _make_decompose_tool_dispatcher(
    hlr_uid: str = "",
    hlr_name: str = "",
    is_persisted: bool = False,
):
    """Build a tool dispatcher function for the decompose agent's multi-turn loop.

    Returns a callable ``(tool_name: str, tool_input: dict) -> str`` that
    handles ``search_existing_hlrs`` and ``create_dependency_link``.

    Args:
        hlr_uid: Neo4j uid of the HLR being decomposed (empty in description mode).
        hlr_name: Name of the HLR being decomposed.
        is_persisted: Whether the HLR already exists in Neo4j (True for
            decompose_and_persist_hlr, False for description mode).
    """
    from codegraph_requirements.models import HLR
    from codegraph.backends import get_backend

    def dispatch(tool_name: str, tool_input: dict) -> str:
        if tool_name == "validate_my_decomposition":
            nodes = tool_input.get("nodes", [])
            if not nodes:
                return json.dumps({"error": "nodes is required and cannot be empty"})
            violations = validate_decomposition(nodes)
            if not violations:
                return json.dumps({
                    "valid": True,
                    "message": "All 8 hard rules pass.  You may now call decompose_requirement.",
                    "violations": [],
                })
            return json.dumps({
                "valid": False,
                "num_violations": len(violations),
                "message": (
                    f"{len(violations)} violation(s) found.  Fix each one and "
                    "call validate_my_decomposition again."
                ),
                "violations": [
                    {"rule": v.rule, "message": v.message, "context": v.context}
                    for v in violations
                ],
            })

        if tool_name == "search_existing_hlrs":
            keywords = tool_input.get("keywords", "")
            limit = int(tool_input.get("limit", 15))

            if not keywords:
                return json.dumps({"error": "keywords is required", "results": []})

            keyword_terms = [kw.lower() for kw in keywords.split()]
            results = []

            try:
                for hlr in HLR.nodes.all():
                    # Skip the HLR being decomposed
                    if hlr_uid and hlr.uid == hlr_uid:
                        continue
                    if hlr_name and (hlr.name or "") == hlr_name:
                        continue

                    search_text = ((hlr.name or "") + " " + (hlr.description or "")).lower()
                    # Require at least one keyword to match
                    if any(kw in search_text for kw in keyword_terms):
                        comp_nodes = hlr.component.all()
                        comp_name = comp_nodes[0].name if comp_nodes else ""
                        results.append({
                            "name": hlr.name or "",
                            "description": (hlr.description or "")[:300],
                            "component": comp_name,
                            "tags": list(hlr.tags) if hlr.tags else [],
                        })
                    if len(results) >= limit:
                        break
            except Exception as exc:
                log.exception("search_existing_hlrs failed")
                return json.dumps({"error": f"Search error: {exc}", "results": []})

            return json.dumps({
                "keywords": keywords,
                "count": len(results),
                "results": results,
            })

        elif tool_name == "create_dependency_link":
            target_name = tool_input.get("target_hlr_name", "")
            rationale = tool_input.get("rationale", "")

            if not target_name:
                return json.dumps({"error": "target_hlr_name is required"})
            if not rationale:
                return json.dumps({"error": "rationale is required"})

            if not is_persisted or not hlr_uid:
                return json.dumps({
                    "status": "noted",
                    "message": (
                        f"Dependency on '{target_name}' recorded for documentation. "
                        f"Not persisted (HLR not yet in Neo4j or running in description mode)."
                    ),
                    "target_hdlr": target_name,
                    "rationale": rationale,
                })

            graph = get_backend().graph
            target_uid = graph.resolve_uid_by_name(target_name, label="HLR")
            if not target_uid:
                return json.dumps({
                    "status": "failed",
                    "message": f"Could not find target HLR '{target_name}' in Neo4j. "
                                f"Verify the name matches exactly.",
                })
            source_node = graph.find_by_uid(hlr_uid)
            if not source_node:
                return json.dumps({
                    "status": "failed",
                    "message": f"Source HLR with uid '{hlr_uid}' not found.",
                })
            try:
                graph.merge_relationship(
                    hlr_uid, "DEPENDS_ON", target_uid,
                    edge_properties={"description": rationale},
                )
                return json.dumps({
                    "status": "created",
                    "source": source_node.name,
                    "relation": "DEPENDS_ON",
                    "target": target_name,
                    "rationale": rationale,
                })
            except Exception as exc:
                log.exception("create_dependency_link failed")
                return json.dumps({"error": f"Link error: {exc}"})

        else:
            return json.dumps({"error": f"Unknown tool: {tool_name}"})

    return dispatch


def _format_dependency_context(dependency_context: dict) -> str:
    """Format dependency assessment into a context block for the prompt."""
    if not dependency_context:
        return ""
    rec = dependency_context.get("recommendation", "none")
    if rec == "none":
        return ""
    lines = ["\n\n## Available Dependencies\n"]
    lines.append(f"- Recommendation: {rec}")
    dep_name = dependency_context.get("dependency_name", "")
    if dep_name:
        lines.append(f"- Dependency: {dep_name}")
    structures = dependency_context.get("relevant_structures", [])
    if structures:
        lines.append(f"- Relevant structures: {', '.join(structures)}")
    rationale = dependency_context.get("rationale", "")
    if rationale:
        lines.append(f"- Rationale: {rationale}")
    lines.append("\nDo not create LLRs for functionality the dependency already handles.")
    return "\n".join(lines)


def _recover_mixed_xml_json(result: dict) -> dict:
    """Recover when an LLM embeds <parameter=...> XML tags inside a JSON string value."""
    recovered = {}
    for key, value in result.items():
        if not isinstance(value, str) or '<parameter=' not in value:
            recovered[key] = value
            continue

        clean_value = value
        end_tag = f'</{key}>'
        end_tag_idx = value.find(end_tag)
        if end_tag_idx >= 0:
            clean_value = value[:end_tag_idx].strip()
        else:
            param_idx = value.find('<parameter=')
            if param_idx >= 0:
                clean_value = value[:param_idx].strip()

        recovered[key] = clean_value

        param_pattern = re.compile(
            r'<parameter=(\w+)>\s*(.*?)(?=\Z|<parameter=\w+>)',
            re.DOTALL,
        )
        for match in param_pattern.finditer(value):
            param_name = match.group(1)
            param_value_str = match.group(2).strip()
            closing_tag = f'</{param_name}>'
            if param_value_str.endswith(closing_tag):
                param_value_str = param_value_str[: -len(closing_tag)].strip()

            try:
                parsed = json.loads(param_value_str)
                recovered[param_name] = parsed
                log.info(
                    "Recovered embedded parameter '%s' from XML-in-JSON "
                    "(type: %s, length: %d)",
                    param_name, type(parsed).__name__,
                    len(parsed) if isinstance(parsed, (list, dict, str)) else 0,
                )
            except json.JSONDecodeError:
                log.warning(
                    "Could not parse embedded parameter '%s' as JSON, "
                    "storing as string",
                    param_name,
                )
                recovered[param_name] = param_value_str

    return recovered


# ══════════════════════════════════════════════════════════════════════════
# Decomposition validation
# ══════════════════════════════════════════════════════════════════════════


@dataclass
class DecompositionViolation:
    """A single rule violation found during decomposition validation."""

    rule: str
    message: str
    context: str = ""


class DecompositionValidationError(ValueError):
    """Raised when a decomposition fails structural validation."""

    def __init__(self, message: str, violations: list[DecompositionViolation] | None = None):
        super().__init__(message)
        self.violations = violations or []


def validate_decomposition(nodes: list[dict]) -> list[DecompositionViolation]:
    """Validate that a decomposition's flat node list is structurally sound.

    Hard rules
    ----------
    1. **LLR_HAS_TEST** — Every LLR must COMPOSES at least one TestNode.
    2. **TEST_HAS_STEP** — Every TestNode must COMPOSES at least one TestStepNode.
    3. **TEST_HAS_PRE_POST** — Every TestNode must COMPOSES ≥1 pre-condition
       AssertionNode and ≥1 post-condition AssertionNode.
    4. **ASSERTION_HAS_OPERANDS** — Every AssertionNode must have LEFT_OPERAND and
       RIGHT_OPERAND edges.
    5. **STEP_HAS_CALLEE** — Every TestStepNode must have a CALLEE edge to a
       scaffold target.
    6. **TEST_REACHES_SCAFFOLD** — Every TestNode must reach ≥1 scaffold node
       through its AssertionNodes/TestStepNodes.
    7. **TEST_HAS_OWNER** — Every TestNode must be owned by at least one LLR.
    8. **SCAFFOLD_IS_REFERENCED** — Every scaffold target UID must be reachable
       from an LLR through the LLR → TestNode → AssertionNode/TestStepNode chain.
    """
    violations: list[DecompositionViolation] = []

    nodes_by_ident: dict[str, dict] = {}
    llr_ids: set[str] = set()
    test_ids: set[str] = set()
    cond_ids: set[str] = set()
    action_ids: set[str] = set()

    for n in nodes:
        ntype = n.get("type", "")
        ident = n.get("qualified_name", "") or n.get("name", "")
        if ident:
            nodes_by_ident[ident] = n
        if ntype == "LLR":
            llr_ids.add(ident)
        elif ntype == "TestNode":
            test_ids.add(ident)
        elif ntype == "AssertionNode":
            cond_ids.add(ident)
        elif ntype == "TestStepNode":
            action_ids.add(ident)

    llr_to_tests: dict[str, list[str]] = {}
    test_to_conds: dict[str, list[str]] = {}
    test_to_actions: dict[str, list[str]] = {}

    for n in nodes:
        ident = n.get("qualified_name", "") or n.get("name", "")
        ntype = n.get("type", "")
        for e in n.get("edges", []):
            rt = e.get("relation_type", "")
            tuid = e.get("target_uid", "")
            if rt != "COMPOSES":
                continue
            if ntype == "LLR" and tuid in test_ids:
                llr_to_tests.setdefault(ident, []).append(tuid)
            elif ntype == "TestNode":
                if tuid in cond_ids:
                    test_to_conds.setdefault(ident, []).append(tuid)
                elif tuid in action_ids:
                    test_to_actions.setdefault(ident, []).append(tuid)

    scaffold_refs: dict[str, list[tuple[str, str]]] = {}
    verif_scaffolds: dict[str, set[str]] = {}

    for n in nodes:
        ident = n.get("qualified_name", "") or n.get("name", "")
        ntype = n.get("type", "")
        if ntype not in ("AssertionNode", "TestStepNode"):
            continue
        for e in n.get("edges", []):
            ttype = e.get("target_type", "")
            tuid = e.get("target_uid", "")
            rt = e.get("relation_type", "")
            if ttype in ("AttributeNode", "LiteralNode", "ClassNode") and tuid:
                scaffold_refs.setdefault(tuid, []).append((ident, rt))
                verif_scaffolds.setdefault(ident, set()).add(tuid)

    # Rule 1
    for llr_id in sorted(llr_ids):
        tests = llr_to_tests.get(llr_id, [])
        if not tests:
            violations.append(DecompositionViolation(
                rule="LLR_HAS_TEST",
                message=f"LLR {llr_id} has no tests (no COMPOSES edge to a TestNode)",
                context=llr_id,
            ))

    tests_owned_by_llr: set[str] = set()
    for test_list in llr_to_tests.values():
        tests_owned_by_llr.update(test_list)

    # Rule 2 & 3
    for test_id in sorted(test_ids):
        actions = test_to_actions.get(test_id, [])
        if not actions:
            violations.append(DecompositionViolation(
                rule="TEST_HAS_STEP",
                message=f"TestNode {test_id} has no steps (no COMPOSES edge to a TestStepNode)",
                context=test_id,
            ))

        cond_list = test_to_conds.get(test_id, [])
        has_pre = any(
            nodes_by_ident.get(cid, {}).get("phase") == "pre"
            for cid in cond_list
        )
        has_post = any(
            nodes_by_ident.get(cid, {}).get("phase") == "post"
            for cid in cond_list
        )
        if not has_pre:
            violations.append(DecompositionViolation(
                rule="TEST_HAS_PRE_POST",
                message=f"TestNode {test_id} has no pre-conditions (no phase='pre' AssertionNode)",
                context=test_id,
            ))
        if not has_post:
            violations.append(DecompositionViolation(
                rule="TEST_HAS_PRE_POST",
                message=f"TestNode {test_id} has no post-conditions (no phase='post' AssertionNode)",
                context=test_id,
            ))

    # Rule 4
    for n in nodes:
        ntype = n.get("type", "")
        if ntype != "AssertionNode":
            continue
        ident = n.get("qualified_name", "?") or n.get("name", "?")
        edges = n.get("edges", [])
        has_left = any(e.get("relation_type") == "LEFT_OPERAND" for e in edges)
        has_right = any(e.get("relation_type") == "RIGHT_OPERAND" for e in edges)
        if not has_left:
            violations.append(DecompositionViolation(
                rule="ASSERTION_HAS_OPERANDS",
                message=f"AssertionNode {ident} has no LEFT_OPERAND edge",
                context=ident,
            ))
        if not has_right:
            violations.append(DecompositionViolation(
                rule="ASSERTION_HAS_OPERANDS",
                message=f"AssertionNode {ident} has no RIGHT_OPERAND edge",
                context=ident,
            ))

    # Rule 5
    for n in nodes:
        ntype = n.get("type", "")
        if ntype != "TestStepNode":
            continue
        ident = n.get("qualified_name", "?") or n.get("name", "?")
        edges = n.get("edges", [])
        callee_edges = [
            e for e in edges
            if e.get("relation_type") == "CALLEE"
            and e.get("target_type") in ("AttributeNode", "ClassNode")
        ]
        if not callee_edges:
            violations.append(DecompositionViolation(
                rule="STEP_HAS_CALLEE",
                message=f"TestStepNode {ident} has no CALLEE edge to a scaffold target (AttributeNode/ClassNode)",
                context=ident,
            ))

    # Rule 6
    for test_id in sorted(test_ids):
        ca_ids = set(test_to_conds.get(test_id, [])) | set(test_to_actions.get(test_id, []))
        test_scaffolds: set[str] = set()
        for ca_id in ca_ids:
            test_scaffolds |= verif_scaffolds.get(ca_id, set())
        if not test_scaffolds:
            violations.append(DecompositionViolation(
                rule="TEST_REACHES_SCAFFOLD",
                message=f"TestNode {test_id} does not reference any scaffold nodes through its AssertionNodes/TestStepNodes",
                context=test_id,
            ))

    # Rule 7
    for test_id in sorted(test_ids):
        if test_id not in tests_owned_by_llr:
            violations.append(DecompositionViolation(
                rule="TEST_HAS_OWNER",
                message=f"TestNode {test_id} is not owned by any LLR (no LLR has a COMPOSES edge to it)",
                context=test_id,
            ))

    # Rule 8
    reachable_scaffolds: set[str] = set()
    for llr_id, test_list in llr_to_tests.items():
        for test_id in test_list:
            ca_ids = set(test_to_conds.get(test_id, [])) | set(test_to_actions.get(test_id, []))
            for ca_id in ca_ids:
                reachable_scaffolds |= verif_scaffolds.get(ca_id, set())

    for uid in sorted(scaffold_refs.keys()):
        if uid not in reachable_scaffolds:
            referrers = scaffold_refs[uid]
            referrer_strs = [f"{r[0]}({r[1]})" for r in referrers]
            violations.append(DecompositionViolation(
                rule="SCAFFOLD_IS_REFERENCED",
                message=(
                    f"Scaffold target '{uid}' is referenced by {referrer_strs} "
                    f"but is not reachable from any LLR → VM → Condition/Action chain"
                ),
                context=uid,
            ))

    return violations


def _load_existing_requirements_tree(hlr) -> dict:
    """Load the full existing requirements tree for an HLR from the codegraph repository.

    Uses ``GraphRepository.get_hlr_subtree()`` which does a multi-hop
    COMPOSES traversal and returns a LayerGraph.  We walk the graph to
    extract the same dict format that ``_format_existing_context()``
    consumes.

    Returns a dict with keys:
    - ``llrs``: list of LLR summaries (uid, description, tags)
    - ``tests_by_llr``: dict of LLR uid → list of test summaries (already correct)
    - ``scaffolds``: list of scaffold node summaries (qualified_name, kind)
    """
    from codegraph.persistence.repository import GraphRepository

    repo = get_backend().graph
    hlr_uid = hlr.uid or ""

    try:
        graph = repo.get_hlr_subtree(hlr_uid)
    except Exception:
        log.warning("get_hlr_subtree failed for %s, returning empty tree", hlr_uid[:8])
        return {"llrs": [], "tests_by_llr": {}, "scaffolds": []}

    # Build a flat lookup: uid → node
    uid_to_node: dict[str, object] = {}
    for entry in graph._all_entries():
        node = entry.node
        uid = node._uid_value()
        if uid:
            uid_to_node[uid] = node

    # Walk entries to extract LLRs, tests, assertions, steps
    llr_summaries: list[dict] = []
    tests_by_llr: dict[str, list[dict]] = {}

    for entry in graph._all_entries():
        node = entry.node
        node_type = type(node).__name__

        # LLRs
        if node_type == "LLR":
            luid = getattr(node, "uid", "") or ""
            llr_summaries.append({
                "uid": luid,
                "description": getattr(node, "description", "") or "",
                "tags": list(getattr(node, "tags", [])) or [],
            })

    # Walk tests per LLR (LLR children)
    for entry in graph._all_entries():
        node = entry.node
        node_type = type(node).__name__
        if node_type != "LLR":
            continue
        llr_uid = getattr(node, "uid", "") or ""

        # Find TestNode children of this LLR
        for child_type, children in entry.children.items():
            if child_type != "TestNode":
                continue
            for child_key, child_entry in children.items():
                test_node = child_entry.node
                test_dict = {
                    "method": getattr(test_node, "method", "") or "automated",
                    "test_name": getattr(test_node, "test_name", "") or "",
                    "description": getattr(test_node, "description", "") or "",
                    "preconditions": [],
                    "actions": [],
                    "postconditions": [],
                }

                # Find AssertionNode children
                for achild_type, achildren in child_entry.children.items():
                    if achild_type == "AssertionNode":
                        for akey, aentry in achildren.items():
                            an = aentry.node
                            phase = getattr(an, "phase", "") or "post"
                            cond = {
                                "subject_qualified_name": "",
                                "operator": getattr(an, "operator", "") or "==",
                                "expected_value": "",
                                "phase": phase,
                            }
                            # Extract LEFT_OPERAND / RIGHT_OPERAND from references
                            for rel, target_key, _ttype in aentry.references:
                                target_node = uid_to_node.get(target_key.split(":", 1)[1] if ":" in target_key else "")
                                if target_node is None:
                                    target_node = uid_to_node.get(target_key)
                                tqn = getattr(target_node, "qualified_name", "") or "" if target_node else target_key
                                if rel == "LEFT_OPERAND":
                                    cond["subject_qualified_name"] = tqn
                                elif rel == "RIGHT_OPERAND":
                                    val = getattr(target_node, "value", "") if target_node else ""
                                    cond["expected_value"] = val or tqn
                            if phase == "pre":
                                test_dict["preconditions"].append(cond)
                            else:
                                test_dict["postconditions"].append(cond)

                    elif achild_type == "TestStepNode":
                        for skey, sentry in achildren.items():
                            sn = sentry.node
                            callee_qn = ""
                            for rel, target_key, _ttype in sentry.references:
                                if rel == "CALLEE":
                                    target_node = uid_to_node.get(target_key.split(":", 1)[1] if ":" in target_key else "")
                                    if target_node is None:
                                        target_node = uid_to_node.get(target_key)
                                    callee_qn = getattr(target_node, "qualified_name", "") or "" if target_node else target_key
                            test_dict["actions"].append({
                                "description": getattr(sn, "description", "") or "",
                                "callee_qualified_name": callee_qn,
                            })

                tests_by_llr.setdefault(llr_uid, []).append(test_dict)

    # Scaffold nodes
    scaffold_summaries: list[dict] = []
    for entry in graph._all_entries():
        node = entry.node
        tags = list(getattr(node, "tags", [])) or []
        if "scaffold" not in tags:
            continue
        qn = getattr(node, "qualified_name", "") or ""
        scaffold_summaries.append({
            "qualified_name": qn,
            "kind": type(node).__name__,
            "tags": tags,
        })

    return {
        "llrs": llr_summaries,
        "tests_by_llr": tests_by_llr,
        "scaffolds": scaffold_summaries,
    }


def _format_existing_context(tree: dict) -> str:
    """Format the existing requirements tree into a prompt section.

    Returns an empty string if there are no existing LLRs.
    """
    llrs = tree.get("llrs", [])
    if not llrs:
        return ""

    tests_by_llr = tree.get("tests_by_llr", {})
    scaffolds = tree.get("scaffolds", [])

    lines = [
        "## Existing Requirements Tree",
        "",
        "The following requirements and tests **already exist** for this HLR.",
        "Complete the gaps — do NOT duplicate existing LLRs or tests.",
        "",
    ]

    # LLRs with tests
    for llr in llrs:
        llr_uid = llr["uid"]
        short_uid = llr_uid[:8] if len(llr_uid) >= 8 else llr_uid
        tests = tests_by_llr.get(llr_uid, [])
        status = f"{len(tests)} test(s)" if tests else "⚠ NO TESTS — create verification stubs"
        lines.append(f"### LLR {short_uid} [{status}]")
        lines.append("")
        lines.append(f"{llr['description']}")
        lines.append("")

        for t in tests:
            label = t.get("test_name", "") or t.get("method", "?")
            lines.append(f"#### Test: `{label}` [{t['method']}]")
            if t.get("description"):
                lines.append(f"  {t['description']}")

            pre = t.get("preconditions", [])
            post = t.get("postconditions", [])
            actions = t.get("actions", [])

            if pre:
                lines.append("  Pre-conditions:")
                for c in pre:
                    sqn = c.get("subject_qualified_name") or "?"
                    op = c.get("operator") or "=="
                    ev = c.get("expected_value") or "?"
                    lines.append(f"    - {sqn} {op} {ev}")
            elif not pre and not actions and not post:
                lines.append("  ⚠ No pre-conditions — add at least one pre-condition")

            if actions:
                lines.append("  Actions:")
                for a in actions:
                    desc = a.get("description", "?")
                    callee = a.get("callee_qualified_name", "")
                    line = f"    - {desc}"
                    if callee:
                        line += f" → {callee}"
                    lines.append(line)
            elif not pre and not actions and not post:
                lines.append("  ⚠ No actions — add at least one test step")

            if post:
                lines.append("  Post-conditions:")
                for c in post:
                    sqn = c.get("subject_qualified_name") or "?"
                    op = c.get("operator") or "=="
                    ev = c.get("expected_value") or "?"
                    lines.append(f"    - {sqn} {op} {ev}")
            elif not pre and not actions and not post:
                lines.append("  ⚠ No post-conditions — add at least one post-condition")

            lines.append("")

    # Scaffold nodes
    if scaffolds:
        lines.append("### Existing Scaffold Nodes")
        lines.append("")
        lines.append("These notional references already exist in the graph.")
        lines.append("Reuse them when creating new verification stubs — do NOT invent")
        lines.append("alternate names for the same concept.")
        lines.append("")
        for s in scaffolds:
            qn = s.get("qualified_name", "?")
            kind = s.get("kind", "?")
            lines.append(f"- `{qn}` ({kind})")
        lines.append("")

    return "\n".join(lines)


def _build_correction_context(
    original_tree: dict,
    violations: list,
    first_attempt_nodes: list[dict],
) -> dict:
    """Build a rich correction context for a retry attempt.

    Takes the original existing tree (from Neo4j), the validation
    violations from the first attempt, and the raw node list the LLM
    produced.  Returns a context dict suitable for :func:`decompose`'s
    ``existing_context`` parameter, augmented with the first attempt's
    structure so the LLM can see what it produced and fix specific gaps.

    The returned dict includes the first-attempt LLRs and tests
    (extracted from the flat node list) plus a scaffolding summary.
    """
    # Extract LLRs and tests from the first-attempt node list
    # (similar to _load_existing_requirements_tree but from flat dicts)
    first_attempt_llrs: list[dict] = []
    first_attempt_tests: dict[str, list[dict]] = {}
    first_attempt_scaffolds: list[dict] = []

    # Build lookup maps
    nodes_by_qn: dict[str, dict] = {}
    for n in first_attempt_nodes:
        ident = n.get("qualified_name", "") or n.get("name", "")
        if ident:
            nodes_by_qn[ident] = n

    for n in first_attempt_nodes:
        ntype = n.get("type", "")
        ident = n.get("qualified_name", "") or n.get("name", "")

        if ntype == "LLR":
            llr_entry: dict = {
                "uid": ident,
                "description": n.get("description", "") or "",
                "tags": list(n.get("tags", [])) or ["design"],
            }
            first_attempt_llrs.append(llr_entry)

            # Find TestNode children via COMPOSES edges
            test_list: list[dict] = []
            for e in n.get("edges", []):
                if e.get("relation_type") == "COMPOSES" and e.get("target_type") == "TestNode":
                    tqn = e.get("target_uid", "")
                    t_node = nodes_by_qn.get(tqn, None)
                    if t_node is None:
                        continue
                    test_dict: dict = {
                        "method": t_node.get("method", "automated"),
                        "test_name": t_node.get("test_name", "") or "",
                        "description": t_node.get("description", "") or "",
                        "preconditions": [],
                        "actions": [],
                        "postconditions": [],
                    }
                    # Find AssertionNode/TestStepNode children
                    for te in t_node.get("edges", []):
                        if te.get("relation_type") != "COMPOSES":
                            continue
                        cqn = te.get("target_uid", "")
                        c_node = nodes_by_qn.get(cqn)
                        if c_node is None:
                            continue
                        c_type = c_node.get("type", "")
                        if c_type == "AssertionNode":
                            phase = c_node.get("phase", "post")
                            cond = {
                                "subject_qualified_name": "",
                                "operator": c_node.get("operator", "=="),
                                "expected_value": "",
                                "phase": phase,
                            }
                            if phase == "pre":
                                test_dict["preconditions"].append(cond)
                            else:
                                test_dict["postconditions"].append(cond)
                        elif c_type == "TestStepNode":
                            test_dict["actions"].append({
                                "description": c_node.get("description", "") or "",
                                "callee_qualified_name": "",
                            })
                    test_list.append(test_dict)
            first_attempt_tests[ident] = test_list

    # Merge with original tree: prefer original LLRs, but add first-attempt
    # LLRs that aren't in the original (the retry is for NEW LLRs anyway).
    merged_llrs = list(original_tree.get("llrs", []))
    merged_tests = dict(original_tree.get("tests_by_llr", {}))
    existing_llr_ids = {llr["uid"] for llr in merged_llrs}

    for llr in first_attempt_llrs:
        if llr["uid"] not in existing_llr_ids:
            merged_llrs.append(llr)

    for llr_id, tests in first_attempt_tests.items():
        if llr_id not in merged_tests:
            merged_tests[llr_id] = tests

    return {
        "llrs": merged_llrs,
        "tests_by_llr": merged_tests,
        "scaffolds": original_tree.get("scaffolds", []),
    }


def _build_correction_message(violations: list, first_attempt_nodes: list[dict]) -> str:
    """Build a correction message describing what the first attempt missed.

    Returns a string suitable for appending to the user prompt on retry.
    """
    lines = [
        "\n\n---",
        "",
        "## CORRECTION NEEDED — Your previous attempt failed validation",
        "",
        "The following issues were found in your previous decomposition.",
        "Fix ONLY these issues — keep everything else exactly as-is.",
        "",
    ]

    # Group violations by rule type
    by_rule: dict[str, list] = {}
    for v in violations:
        by_rule.setdefault(v.rule, []).append(v)

    if "LLR_HAS_TEST" in by_rule or "TEST_HAS_OWNER" in by_rule:
        lines.append("### Missing LLR→TestNode COMPOSES edges")
        lines.append("")
        lines.append("Every LLR node dict MUST have an `edges` array with")
        lines.append("COMPOSES edges to its TestNode children.  Example:")
        lines.append("")
        lines.append("    {\"type\": \"LLR\", \"name\": \"...\",")
        lines.append('     "edges": [')
        lines.append('       {"relation_type": "COMPOSES", "target_uid": "vm::...::test_...",')
        lines.append('        "target_type": "TestNode"}')
        lines.append("     ]}")
        lines.append("")
        for v in by_rule.get("LLR_HAS_TEST", []):
            lines.append(f"- {v.message}")
        for v in by_rule.get("TEST_HAS_OWNER", []):
            lines.append(f"- {v.message}")
        lines.append("")

    if "TEST_HAS_STEP" in by_rule:
        lines.append("### Missing TestNode→TestStepNode COMPOSES edges")
        for v in by_rule["TEST_HAS_STEP"]:
            lines.append(f"- {v.message}")
        lines.append("")

    if "TEST_HAS_PRE_POST" in by_rule:
        lines.append("### Missing pre/post conditions")
        for v in by_rule["TEST_HAS_PRE_POST"]:
            lines.append(f"- {v.message}")
        lines.append("")

    other_rules = set(by_rule.keys()) - {"LLR_HAS_TEST", "TEST_HAS_OWNER",
                                            "TEST_HAS_STEP", "TEST_HAS_PRE_POST"}
    if other_rules:
        lines.append("### Other issues")
        for rule in sorted(other_rules):
            for v in by_rule[rule]:
                lines.append(f"- [{v.rule}] {v.message}")
        lines.append("")

    lines.append("Re-run the decomposition with these corrections applied.")

    return "\n".join(lines)


def _count_hlr_scaffolds(hlr) -> int:
    """Count scaffold nodes reachable from this HLR's verification subtree.

    Uses ``GraphRepository.get_hlr_subtree(tag='scaffold')`` to fetch
    only scaffold nodes (plus their ancestors for tree context) from the
    HLR subtree.  Returns the count of scaffold-tagged entries.

    This is the reliable decomposition-complete check: scaffold nodes are
    the notional references (AttributeNode, LiteralNode, ClassNode) that
    the decompose agent creates — without them, the decomposition is
    structurally incomplete even if LLR nodes exist.
    """
    from codegraph.persistence.repository import GraphRepository

    try:
        repo = get_backend().graph
        graph = repo.get_hlr_subtree(hlr.uid or "", tag="scaffold")
        # Count entries whose node carries the "scaffold" tag
        count = 0
        for entry in graph._all_entries():
            node_tags: list[str] = getattr(entry.node, "tags", None) or []
            if "scaffold" in node_tags:
                count += 1
        return count
    except Exception as exc:
        log.warning("_count_hlr_scaffolds: query failed for %s: %s", (hlr.uid or "")[:8], exc)
        return 0


def decompose(
    description: str,
    component: str = "",
    dependency_context: dict | None = None,
    existing_context: dict | None = None,
    model: str = "",
    prompt_log_file: str = "",
    hlr_uid: str = "",
    hlr_name: str = "",
) -> DecomposedRequirement:
    """Decompose a high-level requirement description into LLRs with verification stubs.

    The agent runs in a multi-turn tool loop: it may call
    ``search_existing_hlrs`` and ``create_dependency_link`` to discover and
    link to related HLRs before producing the ``decompose_requirement`` output.

    Args:
        description: The HLR description text.
        component: Name of the architectural component this HLR belongs to.
        dependency_context: Optional dict with dependency assessment context.
        existing_context: Optional dict with the existing requirements tree
            (LLRs, tests, scaffold nodes) loaded from Neo4j.  When provided,
            the agent will complete gaps rather than start from scratch.
        model: LLM model identifier to use.
        prompt_log_file: Path to write raw prompt/response for debugging.
        hlr_uid: Neo4j uid of the HLR being decomposed. Pass when decomposing
            a persisted HLR so ``create_dependency_link`` can persist
            DEPENDS_ON edges.
        hlr_name: Name of the HLR being decomposed. Used by the tool dispatcher
            to skip the self-HLR in searches and as fallback for linking.

    Returns:
        A DecomposedRequirement with description and low_level_requirements.
    """
    user_content = (
        f"Decompose this high-level requirement:\n\n{description}\n\n"
        "IMPORTANT — Follow the VALIDATION-PROTOCOL:\n"
        "1. Call search_existing_hlrs with relevant keywords from the description.\n"
        "2. For each HLR that this new requirement genuinely depends on, call\n"
        "   create_dependency_link with a clear rationale.\n"
        "3. Produce a DRAFT decomposition (LLRs + verification stubs).\n"
        "4. Call validate_my_decomposition with ALL your nodes.\n"
        "5. Fix any violations and re-validate until clean.\n"
        "6. Only THEN call decompose_requirement to submit your result.\n"
        "Do NOT skip steps 4-5 — self-validation is mandatory.\n"
    )
    if component:
        user_content += (
            f"\n\nThis HLR belongs to the **{component}** component. "
        )
    user_content += _format_dependency_context(dependency_context or {})

    # Build existing-context section for the system prompt
    existing_section = _format_existing_context(existing_context or {})

    # Build the tool dispatcher for dependency discovery
    is_persisted = bool(hlr_uid)
    tool_dispatcher = _make_decompose_tool_dispatcher(
        hlr_uid=hlr_uid,
        hlr_name=hlr_name,
        is_persisted=is_persisted,
    )

    # All tools: dependency discovery tools + validation + the final decompose tool
    all_tools = [SEARCH_HLRS_TOOL, CREATE_DEPENDENCY_TOOL, VALIDATE_TOOL, TOOL_DEFINITION]

    result = call_tool_loop(
        system=SYSTEM_PROMPT.replace("{existing_context_section}", existing_section),
        messages=[
            {
                "role": "user",
                "content": user_content,
            }
        ],
        tools=all_tools,
        final_tool_name="decompose_requirement",
        tool_dispatcher=tool_dispatcher,
        model=model,
        max_tokens=32768,
        max_turns=20,
        prompt_log_file=prompt_log_file,
    )

    # Recover from models that return nested JSON as a string
    if isinstance(result, str):
        try:
            result = json.loads(result)
            log.info("Deserialized entire result from JSON string")
        except json.JSONDecodeError:
            pass
    if isinstance(result, dict) and isinstance(result.get("nodes"), str):
        try:
            result["nodes"] = json.loads(result["nodes"])
            log.info("Deserialized nodes from JSON string")
        except json.JSONDecodeError:
            log.warning("Failed to parse nodes as JSON: %.200s", result["nodes"])

    if isinstance(result, dict) and "nodes" not in result:
        recovered = _recover_mixed_xml_json(result)
        if "nodes" in recovered:
            log.info("Recovered nodes from embedded XML in description")
            result = recovered

    return DecomposedRequirement.model_validate(result)


# ══════════════════════════════════════════════════════════════════════════
# Full entry point — context loading + decomposition + persistence
# ══════════════════════════════════════════════════════════════════════════


def decompose_and_persist_hlr(
    hlr_uid: str,
    *,
    model: str = "",
    log_dir: str = "",
) -> dict:
    """Decompose a single HLR end-to-end: load from Neo4j → decompose → persist.

    Args:
        hlr_uid: The HLR's ``uid`` (deterministic unique ID).
        model: LLM model override.
        log_dir: Directory for per-step prompt logs.

    Returns:
        Dict with keys ``hlr_uid``, ``num_llrs``, ``llrs_created``, etc.
    """
    from codegraph_requirements.models import HLR
    from codegraph_requirements.persistence import persist_decomposition

    log.info("decompose_and_persist_hlr: loading HLR %s", hlr_uid[:16])
    hlr = HLR.nodes.get_or_none(uid=hlr_uid)
    if not hlr:
        raise ValueError(f"HLR {hlr_uid} not found")
    uid = hlr.uid

    # --- Guard: refuse re-decomposition if HLR already has scaffold nodes ---
    # Scaffold nodes are the concrete artifact of a successful decomposition;
    # their presence means the verification stubs (tests, assertions, steps)
    # with LEFT_OPERAND / RIGHT_OPERAND / CALLEE edges already exist.
    scaffold_count = _count_hlr_scaffolds(hlr)
    if scaffold_count > 0:
        raise ValueError(
            f"HLR {hlr_uid[:16]} already has {scaffold_count} scaffold node(s) — "
            f"decomposition has already been run. To re-decompose, delete the "
            f"existing LLRs first, or use the decompose() function directly "
            f"with existing_context if you need to fill gaps."
        )

    hlr_description = hlr.description

    comp_nodes = hlr.component.all()
    component_name = comp_nodes[0].name if comp_nodes else ""

    dep_ctx = getattr(hlr, "dependency_context", None)

    # --- Load existing requirements tree for enrichment ---
    existing_tree = _load_existing_requirements_tree(hlr)
    log.info(
        "decompose_and_persist_hlr: existing tree has %d LLRs, %d tests-by-llr groups, %d scaffolds",
        len(existing_tree.get("llrs", [])),
        len(existing_tree.get("tests_by_llr", {})),
        len(existing_tree.get("scaffolds", [])),
    )

    prompt_log_file = ""
    if log_dir:
        import os
        os.makedirs(log_dir, exist_ok=True)
        prompt_log_file = os.path.join(log_dir, f"decompose_hlr_{uid[:16]}.md")

    hlr_name = hlr.name or ""
    log.info("decompose_and_persist_hlr: running decompose for %s", uid[:16])
    decomposed = decompose(
        description=hlr_description,
        component=component_name,
        dependency_context=dep_ctx,
        existing_context=existing_tree,
        model=model,
        prompt_log_file=prompt_log_file,
        hlr_uid=uid,
        hlr_name=hlr_name,
    )

    log.info(
        "decompose_and_persist_hlr: decompose produced %d nodes",
        len(decomposed.nodes),
    )
    for i, node in enumerate(decomposed.nodes):
        log.info(
            "  node[%d]: type=%s, uid=%s",
            i,
            node.get("type", "?"),
            node.get("qualified_name", "?") or node.get("name", "?"),
        )

    violations = validate_decomposition(list(decomposed.nodes))
    if violations:
        msg_lines = [f"Decomposition failed validation with {len(violations)} violation(s):"]
        for v in violations:
            msg_lines.append(f"  [{v.rule}] {v.message}")
        msg = "\n".join(msg_lines)
        log.warning("decompose_and_persist_hlr: first attempt failed: %s", msg)

        # Retry once — feed the validation errors back to the LLM so it can
        # correct the specific issues (most commonly missing LLR→TestNode
        # COMPOSES edges).
        retry_prompt_log = ""
        if log_dir:
            retry_prompt_log = os.path.join(log_dir, f"decompose_hlr_{uid[:16]}_retry.md")

        correction_context = _build_correction_context(
            existing_tree, violations, list(decomposed.nodes)
        )
        correction_message = _build_correction_message(
            violations, list(decomposed.nodes)
        )

        decomposed = decompose(
            description=hlr_description + correction_message,
            component=component_name,
            dependency_context=dep_ctx,
            existing_context=correction_context,
            model=model,
            prompt_log_file=retry_prompt_log,
            hlr_uid=uid,
            hlr_name=hlr_name,
        )

        log.info(
            "decompose_and_persist_hlr: retry produced %d nodes",
            len(decomposed.nodes),
        )

        violations = validate_decomposition(list(decomposed.nodes))
        if violations:
            msg_lines = [f"Decomposition failed validation after retry with {len(violations)} violation(s):"]
            for v in violations:
                msg_lines.append(f"  [{v.rule}] {v.message}")
            msg = "\n".join(msg_lines)
            log.error("decompose_and_persist_hlr: retry also failed: %s", msg)
            raise DecompositionValidationError(msg, violations=violations)

    log.info("decompose_and_persist_hlr: validation passed (%d nodes)", len(decomposed.nodes))

    log.info("decompose_and_persist_hlr: persisting for %s", uid[:16])
    result = persist_decomposition(uid, decomposed)

    log.info(
        "Decomposition+persist complete for HLR %s: %d LLRs, %d tests, "
        "%d assertions, %d steps, %d fixtures, %d scaffold classes, %d scaffold attributes",
        uid[:16], result.llrs_created, result.tests_created,
        result.assertions_created, result.steps_created,
        result.fixtures_created, result.scaffold_classes, result.scaffold_attributes,
    )

    # --- Generate per-LLR feedback docs from Neo4j ---
    # After persistence, generate the feedback documents so humans can
    # review the new LLRs and fill in feedback.  Uses the same logic as
    # generate_hlr_feedback_docs.py / handle_generate_feedback_docs.
    try:
        from codegraph_design.tools.workflow_tools import handle_generate_feedback_docs
        from codegraph_design.tools.dispatcher import DesignDiscoveryDispatcher
        _disp = DesignDiscoveryDispatcher()
        feedback_result = handle_generate_feedback_docs(_disp, {})
        log.info("decompose_and_persist_hlr: feedback docs generated")
    except Exception as exc:
        feedback_result = None
        log.warning("decompose_and_persist_hlr: feedback doc generation failed: %s", exc)

    # --- Serialize requirements to standard codegraph markdown ---
    # Write requirements.md via export_markdown so the file is
    # round-trip stable with import_markdown (see
    # tests/test_markdown_roundtrip.py).
    requirements_md_path = ""
    try:
        requirements_md_path = serialize_hlr_subtree_to_markdown(uid)
    except Exception as exc:
        log.warning("decompose_and_persist_hlr: markdown serialization failed: %s", exc)

    return {
        "hlr_uid": uid,
        "num_llrs": len([n for n in decomposed.nodes if n.get("type") == "LLR"]),
        "llrs_created": result.llrs_created,
        "tests_created": result.tests_created,
        "assertions_created": result.assertions_created,
        "steps_created": result.steps_created,
        "fixtures_created": result.fixtures_created,
        "scaffold_classes": result.scaffold_classes,
        "scaffold_attributes": result.scaffold_attributes,
        "operand_edges": result.operand_edges,
        "scaffold_map": result.scaffold_map,
        "status": "decomposed",
        "requirements_md": requirements_md_path,
    }


# ══════════════════════════════════════════════════════════════════════════
# Markdown serialization — standard export_markdown path
# ══════════════════════════════════════════════════════════════════════════


def serialize_decomposition_to_markdown(
    decomposed: DecomposedRequirement,
    output_dir: str = "",
    hlr_name: str = "",
) -> str:
    """Serialize a decomposition result to standard codegraph markdown.

    Converts the ``DecomposedRequirement`` flat node list into a
    :class:`LayerGraph`, then exports via :func:`export_markdown` —
    the same serialization path used by the round-trip tests.  The
    resulting file is round-trip stable: ``import_markdown`` followed
    by ``export_markdown`` produces byte-identical output.

    Args:
        decomposed: The decomposition result from :func:`decompose`.
        output_dir: Directory to write the markdown file.  Defaults to
            ``codegraph/requirements/<slug>/``.
        hlr_name: HLR name used to generate the output sub-directory
            slug.  If empty, uses ``decomposed.description``.

    Returns:
        Path to the written markdown file.
    """
    from pathlib import Path

    from codegraph.graph import LayerGraph
    from codegraph.export.markdown import export_markdown

    # Determine the HLR qualified_name (deterministic slug from description).
    # This is used as the HLR's identity — uid = SHA1(qualified_name) —
    # so the same description always produces the same HLR uid.
    slug_source = hlr_name or decomposed.description or "decomposed"
    slug = re.sub(r"[^a-z0-9]+", "-", slug_source.lower()).strip("-")
    if not output_dir:
        output_dir = f"codegraph/requirements/{slug}"

    # Convert the flat node list to a LayerGraph.
    # Inject a synthetic HLR node at the head of the list so that
    # LLRs nest under it (via COMPOSES edges) rather than appearing
    # as root-level entries.  This ensures the exported markdown has
    # the correct heading depth hierarchy:
    #   ## HLR → ### LLR → #### Test → ##### Assertion / TestStep
    nodes = [dict(n) for n in decomposed.nodes]
    llr_identities: list[str] = []
    for n in nodes:
        if n.get("type") == "LLR":
            ident = n.get("qualified_name") or n.get("name", "")
            if ident:
                llr_identities.append(ident)
    hlr_node: dict = {
        "type": "HLR",
        "qualified_name": slug,
        "name": slug,
        "description": decomposed.description or "",
        "tags": ["design"],
        "edges": [
            {"relation_type": "COMPOSES", "target_uid": ident, "target_type": "LLR"}
            for ident in llr_identities
        ],
    }
    nodes.insert(0, hlr_node)

    # create_missing=True auto-creates scaffold nodes (AttributeNode,
    # LiteralNode) referenced by LEFT_OPERAND / RIGHT_OPERAND / CALLEE
    # edges but not present as explicit nodes in the list.
    graph = LayerGraph.deserialize(nodes, create_missing=True)

    # Export to standard markdown
    md = export_markdown(graph, fields="all")

    out_path = Path(output_dir) / "requirements.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(md, encoding="utf-8")
    log.info(
        "serialize_decomposition_to_markdown: wrote %s (%d bytes, %d lines)",
        out_path, len(md), len(md.splitlines()),
    )
    return str(out_path)


def serialize_hlr_subtree_to_markdown(
    hlr_uid: str,
    output_dir: str = "",
) -> str:
    """Serialize an HLR subtree from Neo4j to standard codegraph markdown.

    Loads the full HLR → LLR → TestNode → AssertionNode / TestStepNode
    hierarchy (including scaffold targets) from Neo4j, then exports via
    :func:`export_markdown` — the same path as
    :func:`serialize_decomposition_to_markdown`.

    Used by :func:`decompose_and_persist_hlr` after persistence so the
    written ``requirements.md`` reflects what is actually in Neo4j.

    Args:
        hlr_uid: The HLR's ``uid`` in Neo4j.
        output_dir: Directory to write the markdown file.  Defaults to
            ``codegraph/requirements/<slug>/``.

    Returns:
        Path to the written markdown file.
    """
    from pathlib import Path

    from codegraph.persistence.repository import GraphRepository
    from codegraph_requirements.models.requirement import HLR
    from codegraph.export.markdown import export_markdown

    hlr = HLR.nodes.get(uid=hlr_uid)
    slug = re.sub(r"[^a-z0-9]+", "-", (hlr.name or hlr_uid[:16]).lower()).strip("-")

    if not output_dir:
        output_dir = f"codegraph/requirements/{slug}"

    repo = get_backend().graph
    graph = repo.get_hlr_subtree(hlr_uid)

    if not graph.entries:
        log.warning("serialize_hlr_subtree_to_markdown: empty subtree for %s", hlr_uid[:16])
        return ""

    md = export_markdown(graph, fields="all")
    out_path = Path(output_dir) / "requirements.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(md, encoding="utf-8")
    log.info(
        "serialize_hlr_subtree_to_markdown: wrote %s (%d bytes)",
        out_path, len(md),
    )
    return str(out_path)


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python -m codegraph_design.agents.decompose_hlr 'description of requirement'")
        print("       python -m codegraph_design.agents.decompose_hlr --hlr-uid <hlr_uid>")
        sys.exit(1)

    if sys.argv[1] == "--hlr-uid":
        if len(sys.argv) < 3:
            print("Usage: python -m codegraph_design.agents.decompose_hlr --hlr-uid <hlr_uid>")
            sys.exit(1)
        from codegraph.backends import get_backend
        get_backend().health_check()  # ensure driver is initialised
        result = decompose_and_persist_hlr(hlr_uid=sys.argv[2])
        print(json.dumps(result, indent=2, default=str))
    else:
        description = " ".join(sys.argv[1:])
        result = decompose(description)
        print(json.dumps(result.model_dump(), indent=2))
