"""Agent that decomposes a high-level requirement into low-level requirements.

Ported from ticketing-system ``backend_migrated.agents.decompose_hlr``.
Uses ``llm_caller`` for LLM tool calls and codegraph's requirements
schemas + persistence.

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

from llm_caller import call_tool

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
| ``"LLR"`` | ``refid`` | Low-level requirement |
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
Your decomposition will be validated before it is persisted. If any of
these rules fail, the decomposition is REJECTED and nothing is saved:

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
</HARD-VALIDATION>

You MUST use the decompose_requirement tool to return your result.
"""

TOOL_DEFINITION = {
    "name": "decompose_requirement",
    "description": "Return the structured decomposition of a high-level requirement",
    "input_schema": DecomposedRequirement.model_json_schema(),
}


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

    nodes_by_refid: dict[str, dict] = {}
    llr_ids: set[str] = set()
    test_ids: set[str] = set()
    cond_ids: set[str] = set()
    action_ids: set[str] = set()

    for n in nodes:
        ntype = n.get("type", "")
        ident = n.get("refid") or n.get("qualified_name", "")
        if ident:
            nodes_by_refid[ident] = n
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
        ident = n.get("refid") or n.get("qualified_name", "")
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
        ident = n.get("refid") or n.get("qualified_name", "")
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
            nodes_by_refid.get(cid, {}).get("phase") == "pre"
            for cid in cond_list
        )
        has_post = any(
            nodes_by_refid.get(cid, {}).get("phase") == "post"
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
        ident = n.get("refid") or n.get("qualified_name", "?")
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
        ident = n.get("refid") or n.get("qualified_name", "?")
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


def decompose(
    description: str,
    component: str = "",
    dependency_context: dict | None = None,
    model: str = "",
    prompt_log_file: str = "",
) -> DecomposedRequirement:
    """Decompose a high-level requirement description into LLRs with verification stubs.

    Args:
        description: The HLR description text.
        component: Name of the architectural component this HLR belongs to.
        dependency_context: Optional dict with dependency assessment context.
        model: LLM model identifier to use.
        prompt_log_file: Path to write raw prompt/response for debugging.

    Returns:
        A DecomposedRequirement with description and low_level_requirements.
    """
    user_content = f"Decompose this high-level requirement:\n\n{description}"
    if component:
        user_content += (
            f"\n\nThis HLR belongs to the **{component}** component. "
        )
    user_content += _format_dependency_context(dependency_context or {})

    result = call_tool(
        system=SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": user_content,
            }
        ],
        tools=[TOOL_DEFINITION],
        tool_name="decompose_requirement",
        model=model,
        max_tokens=32768,
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
    refid: str,
    *,
    model: str = "",
    log_dir: str = "",
) -> dict:
    """Decompose a single HLR end-to-end: load from Neo4j → decompose → persist.

    Args:
        refid: The HLR's ``refid`` (hex UUID string).
        model: LLM model override.
        log_dir: Directory for per-step prompt logs.

    Returns:
        Dict with keys ``hlr_refid``, ``num_llrs``, ``llrs_created``, etc.
    """
    from codegraph_requirements.models import HLR
    from codegraph_requirements.persistence import persist_decomposition

    log.info("decompose_and_persist_hlr: loading HLR %s", refid[:8])
    hlr = HLR.nodes.get_or_none(refid=refid)
    if not hlr:
        raise ValueError(f"HLR {refid} not found")

    hlr_description = hlr.description

    comp_nodes = hlr.component.all()
    component_name = comp_nodes[0].name if comp_nodes else ""

    dep_ctx = getattr(hlr, "dependency_context", None)

    prompt_log_file = ""
    if log_dir:
        import os
        os.makedirs(log_dir, exist_ok=True)
        prompt_log_file = os.path.join(log_dir, f"decompose_hlr_{refid[:8]}.md")

    log.info("decompose_and_persist_hlr: running decompose for %s", refid[:8])
    decomposed = decompose(
        description=hlr_description,
        component=component_name,
        dependency_context=dep_ctx,
        model=model,
        prompt_log_file=prompt_log_file,
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
            node.get("refid") or node.get("qualified_name", "?"),
        )

    violations = validate_decomposition(list(decomposed.nodes))
    if violations:
        msg_lines = [f"Decomposition failed validation with {len(violations)} violation(s):"]
        for v in violations:
            msg_lines.append(f"  [{v.rule}] {v.message}")
        msg = "\n".join(msg_lines)
        log.error("decompose_and_persist_hlr: %s", msg)
        raise DecompositionValidationError(msg, violations=violations)
    log.info("decompose_and_persist_hlr: validation passed (%d nodes)", len(decomposed.nodes))

    log.info("decompose_and_persist_hlr: persisting for %s", refid[:8])
    result = persist_decomposition(refid, decomposed)

    log.info(
        "Decomposition+persist complete for HLR %s: %d LLRs, %d tests, "
        "%d assertions, %d steps, %d fixtures, %d scaffold classes, %d scaffold attributes",
        refid[:8], result.llrs_created, result.tests_created,
        result.assertions_created, result.steps_created,
        result.fixtures_created, result.scaffold_classes, result.scaffold_attributes,
    )

    return {
        "hlr_refid": refid,
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
    }


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python -m codegraph_design.agents.decompose_hlr 'description of requirement'")
        print("       python -m codegraph_design.agents.decompose_hlr --refid <hlr_refid>")
        sys.exit(1)

    if sys.argv[1] == "--refid":
        if len(sys.argv) < 3:
            print("Usage: python -m codegraph_design.agents.decompose_hlr --refid <hlr_refid>")
            sys.exit(1)
        from codegraph.persistence.connection import init_neo4j, close_neo4j
        init_neo4j()
        result = decompose_and_persist_hlr(refid=sys.argv[2])
        print(json.dumps(result, indent=2, default=str))
        close_neo4j()
    else:
        description = " ".join(sys.argv[1:])
        result = decompose(description)
        print(json.dumps(result.model_dump(), indent=2))
