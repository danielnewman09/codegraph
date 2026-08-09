"""Context builders for test scaffolding (mirrors models/test.py).

Addresses: ``TestNode`` (composes ordered ``TestStepNode`` +
``AssertionNode`` children), ``TestStepNode``, ``AssertionNode``.
``TestFixtureNode`` remains a declared skip — no fixture carries one yet.

Phase 3 (Catch2 export): the design pipeline emits the test *structure*
(test / step descriptions, assertion operator + operands) but not step
code, so generated tests are honest scaffolding — TEST_CASE with the
steps/assertions as documented TODO comments.
"""

from __future__ import annotations

from codegraph.codegen.context import base

#: Node types this module addresses (mirrors models/test.py).
NODE_TYPES = ("TestNode", "TestStepNode", "AssertionNode", "TestFixtureNode")

#: TestFixtureNode has no data in any current fixture — declared skip
#: (registered per-type as a skip_builder); the others are real.
SKIP_REASONS: dict[str, str] = {
    "TestFixtureNode": "test fixture — no data in any current fixture (Phase 3)",
}

#: Assertion operand edge kinds, in display order.
_OPERANDS = ("LEFT_OPERAND", "RIGHT_OPERAND")


def build_context(entry, state) -> dict | None:
    """Build the test-scaffolding context dict for *entry*."""
    node_type = type(entry.node).__name__
    if node_type == "TestNode":
        return _build_test(entry, state)
    if node_type == "TestStepNode":
        return _build_step(entry, state)
    if node_type == "AssertionNode":
        return _build_assertion(entry, state)
    return None  # TestFixtureNode — declared skip


def _build_test(entry, state) -> dict:
    node = entry.node
    steps: list[dict] = []
    assertions: list[dict] = []
    for child_type, _key, child in base.ordered_children(entry):
        if child_type == "TestStepNode":
            ctx = _build_step(child, state)
            if ctx is not None:
                steps.append(ctx)
        elif child_type == "AssertionNode":
            ctx = _build_assertion(child, state)
            if ctx is not None:
                assertions.append(ctx)
    steps.sort(key=lambda s: (s.get("order") is None, s.get("order") or 0))
    return {
        "type": "TestNode",
        "kind": node.kind or "test",
        "name": node.name or "",
        "qualified_name": node.qualified_name or "",
        "uid": node.uid or "",
        "description": (node.description or node.brief_description or ""),
        "steps": steps,
        "assertions": assertions,
        "file_path": node.file_path or "",
        "line_number": node.line_number or 0,
    }


def _build_step(entry, state) -> dict:
    node = entry.node
    return {
        "type": "TestStepNode",
        "kind": node.kind or "test_step",
        "name": node.name or "",
        "qualified_name": node.qualified_name or "",
        "uid": node.uid or "",
        "description": (node.description or ""),
        "order": node.order or 0,
    }


def _build_assertion(entry, state) -> dict:
    node = entry.node
    operands: dict[str, str] = {}
    if state is not None:
        for relation_type, target_key, _target_type in entry.references:
            if relation_type not in _OPERANDS:
                continue
            target = state.flat.get(target_key)
            if target is None:
                operands[relation_type] = ""
                continue
            t = target.node
            operands[relation_type] = (
                getattr(t, "value", "") or getattr(t, "name", "")
                or getattr(t, "qualified_name", "") or ""
            )
    return {
        "type": "AssertionNode",
        "kind": node.kind or "assertion",
        "name": node.name or "",
        "qualified_name": node.qualified_name or "",
        "uid": node.uid or "",
        "operator": node.operator or "",
        "phase": node.phase or "",
        "left_operand": operands.get("LEFT_OPERAND", ""),
        "right_operand": operands.get("RIGHT_OPERAND", ""),
    }
