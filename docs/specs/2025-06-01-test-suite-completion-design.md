# Test Suite Completion Design

**Date:** 2025-06-01
**Status:** Approved

## Overview

Complete the test suite for all CodeGraphNode types in the codegraph data model,
following the existing pattern of per-type roundtrip tests, per-relationship edge
tests, and a full integration test.

## Current State

**Tested (8 tests):**
- FileNode: serialization roundtrip, full deserialization
- AttributeNode: serialization roundtrip, full deserialization, DEFINED_IN edge
- MethodNode: serialization roundtrip, full deserialization, DEFINED_IN edge

**Untested types (10):**
- Compounds: ClassNode, InterfaceNode, EnumNode, UnionNode, ModuleNode
- Members: EnumValueNode, FunctionNode, DefineNode
- Other: NamespaceNode, ParameterNode

**Untested relationships (8):**
- COMPOSES, INHERITS_FROM, REALIZES, DEPENDS_ON, REFERENCES, INVOKES, HAS_ARGUMENT, RETURNS

## Design

### Layer 1: Per-type roundtrip tests (no Neo4j)

For each untested type, add:
- A JSON fixture in `tests/data/` with all property fields populated
- A test file in the directory mirroring `src/codegraph/models/`

| Type | Fixture | Test file |
|---|---|---|
| ClassNode | `tests/data/class_node_full.json` | `tests/compound/test_class_serialization.py` |
| InterfaceNode | `tests/data/interface_node_full.json` | `tests/compound/test_interface_serialization.py` |
| EnumNode | `tests/data/enum_node_full.json` | `tests/compound/test_enum_serialization.py` |
| ModuleNode | `tests/data/module_node_full.json` | `tests/compound/test_module_serialization.py` |
| UnionNode | `tests/data/union_node_full.json` | `tests/compound/test_union_serialization.py` |
| EnumValueNode | `tests/data/enum_value_node_full.json` | `tests/member/test_enum_value_serialization.py` |
| FunctionNode | `tests/data/function_node_full.json` | `tests/member/test_function_serialization.py` |
| DefineNode | `tests/data/define_node_full.json` | `tests/member/test_define_serialization.py` |
| NamespaceNode | `tests/data/namespace_node_full.json` | `tests/namespace/test_namespace_serialization.py` |
| ParameterNode | `tests/data/parameter_node_full.json` | `tests/parameter/test_parameter_serialization.py` |

Each test follows the pattern from `test_method_deserialization.py`:
1. Read JSON fixture from `tests/data/`
2. `CodeGraphNode.from_json(data)` → assert correct type
3. Loop over JSON fields (skip auto-generated uid, `edges`, `type`) and assert `getattr(node, field) == expected`

ParameterNode has no `UniqueIdProperty`, so all fields are asserted directly.

### Layer 2: Per-relationship edge tests (requires Neo4j)

One test per relationship type, following the pattern from `test_attribute_defined_in_file.py`.
Nodes are constructed inline (no separate fixture).

| Relationship | Source → Target | Test file |
|---|---|---|
| COMPOSES | ClassNode → MethodNode | `tests/compound/test_class_composes_method.py` |
| COMPOSES | ClassNode → AttributeNode | `tests/compound/test_class_composes_attribute.py` |
| COMPOSES | EnumNode → EnumValueNode | `tests/compound/test_enum_composes_value.py` |
| COMPOSES | InterfaceNode → MethodNode | `tests/compound/test_interface_composes_method.py` |
| COMPOSES | NamespaceNode → ClassNode | `tests/namespace/test_namespace_composes_class.py` |
| INHERITS_FROM | ClassNode → ClassNode | `tests/compound/test_class_inherits.py` |
| REALIZES | ClassNode → InterfaceNode | `tests/compound/test_class_realizes_interface.py` |
| DEPENDS_ON | ClassNode → ClassNode | `tests/compound/test_class_depends_on.py` |
| INVOKES | MethodNode → MethodNode | `tests/member/test_method_invokes_method.py` |

Each edge test:
1. Create and save source + target nodes
2. Connect via the relationship
3. Serialize source, write to JSON
4. Read back, `CodeGraphNode.from_json()`, assert type and fields
5. Assert `edges` array contains the expected edge with correct `relation_type`, `target_type`, and `target_uid`
6. Assert live graph agrees (`source.relationship.all()`)

Skipped relationships (same assertion pattern, add later if needed):
- REFERENCES (ClassNode → ClassNode)
- TEMPLATE_PARAM / SPECIALIZES (ClassNode → ClassNode)
- HAS_ARGUMENT / RETURNS (MethodNode → ClassNode)

### Layer 3: Integration test — full Calculator graph

Update `tests/data/design_graph.json` to match the current `CodeGraphNode.serialize()` schema:

- List of node objects, each containing `type`, `_llm_fields`, and `edges` array
- Use only supported relationship types: COMPOSES, INHERITS_FROM, REALIZES, DEPENDS_ON, DEFINED_IN
- Include `source` (project name) on FileNode

The Calculator scenario exercises: ClassNode, InterfaceNode, EnumNode, EnumValueNode, MethodNode, AttributeNode, ModuleNode, and FileNode with COMPOSES, INHERITS_FROM, REALIZES, DEPENDS_ON, and DEFINED_IN relationships.

Test file: `tests/test_graph_integration.py`

Test steps:
1. Create all nodes from the fixture via `CodeGraphNode.from_json()` + `.save()`
2. Connect all edges by iterating each node's `edges` array, looking up targets by `target_uid` mapping the fixture
3. Serialize the entire graph and assert every node's type and `_llm_fields` roundtrip
4. Assert every edge in the fixture matches a live edge in Neo4j
5. Assert total edge counts match

## Scope

- No changes to the data model (models in `src/codegraph/models/`)
- No changes to `CodeGraphNode` serialization logic
- `conftest.py` stays as-is (session-scoped DB clear)
- Fixtures in `tests/data/` are committed to version control