# Test Suite Completion — Implementation Plan

## Layer 1: Per-type roundtrip tests (no Neo4j)

### 1.1 ClassNode

**Create** `tests/data/class_node_full.json`:
```json
{
    "type": "ClassNode",
    "qualified_name": "calc::CalculatorEngine",
    "name": "CalculatorEngine",
    "kind": "class",
    "layer": "design",
    "component_id": 1,
    "source_type": "doxygen",
    "visibility": "public",
    "brief_description": "Core calculator engine",
    "detailed_descriimplemption": "Performs arithmetic operations with input validation.",
    "file_path": "/src/calc/calculator_engine.h",
    "line_number": 15,
    "definition": "class CalculatorEngine",
    "module": "calc",
    "base_classes": [],
    "is_final": false,
    "is_abstract": false,
    "source": "codegraph",
    "edges": []
}
```

**Create** `tests/compound/test_class_serialization.py` — read fixture, `CodeGraphNode.from_json()`, assert type is ClassNode, assert `qualified_name` is non-empty, loop all other fields.

### 1.2 InterfaceNode

**Create** `tests/data/interface_node_full.json`:
```json
{
    "type": "InterfaceNode",
    "qualified_name": "calc::ICalculator",
    "name": "ICalculator",
    "kind": "interface",
    "layer": "design",
    "component_id": 2,
    "source_type": "doxygen",
    "visibility": "public",
    "brief_description": "Calculator interface contract",
    "detailed_description": "Defines the core calculation operation.",
    "file_path": "/src/calc/icalculator.h",
    "line_number": 5,
    "definition": "class ICalculator",
    "module": "calc",
    "is_abstract": true,
    "source": "codegraph",
    "edges": []
}
```

**Create** `tests/compound/test_interface_serialization.py` — same pattern.

### 1.3 EnumNode

**Create** `tests/data/enum_node_full.json`:
```json
{
    "type": "EnumNode",
    "qualified_name": "calc::Operation",
    "name": "Operation",
    "kind": "enum",
    "layer": "design",
    "component_id": 3,
    "source_type": "doxygen",
    "visibility": "public",
    "brief_description": "Supported arithmetic operations",
    "detailed_description": "ADD, SUBTRACT, MULTIPLY, and DIVIDE.",
    "file_path": "/src/calc/operation.h",
    "line_number": 3,
    "definition": "enum Operation",
    "module": "calc",
    "source": "codegraph",
    "edges": []
}
```

**Create** `tests/compound/test_enum_serialization.py` — same pattern.

### 1.4 ModuleNode

**Create** `tests/data/module_node_full.json`:
```json
{
    "type": "ModuleNode",
    "qualified_name": "calc",
    "name": "calc",
    "kind": "module",
    "layer": "design",
    "component_id": 4,
    "source_type": "doxygen",
    "description": "Calculation engine module",
    "source": "codegraph",
    "edges": []
}
```

**Create** `tests/compound/test_module_serialization.py` — same pattern. Note: ModuleNode has fewer fields than other compounds.

### 1.5 UnionNode

**Create** `tests/data/union_node_full.json`:
```json
{
    "type": "UnionNode",
    "qualified_name": "calc::DataValue",
    "name": "DataValue",
    "kind": "union",
    "layer": "design",
    "component_id": 5,
    "source_type": "doxygen",
    "visibility": "public",
    "brief_description": "A tagged union for polymorphic data storage",
    "detailed_description": "Holds int, float, or string values.",
    "file_path": "/src/calc/data_value.h",
    "line_number": 8,
    "definition": "union DataValue",
    "module": "calc",
    "source": "codegraph",
    "edges": []
}
```

**Create** `tests/compound/test_union_serialization.py` — same pattern.

### 1.6 EnumValueNode

**Create** `tests/data/enum_value_node_full.json`:
```json
{
    "type": "EnumValueNode",
    "qualified_name": "calc::Operation::ADD",
    "name": "ADD",
    "kind": "enumvalue",
    "layer": "design",
    "component_id": 6,
    "compound_refid": "enum_operation",
    "visibility": "public",
    "brief_description": "Represents addition.",
    "detailed_description": "The addition operation.",
    "file_path": "/src/calc/operation.h",
    "line_number": 4,
    "definition": "ADD",
    "source": "codegraph",
    "edges": []
}
```

**Create** `tests/member/test_enum_value_serialization.py` — same pattern.

### 1.7 FunctionNode

**Create** `tests/data/function_node_full.json`:
```json
{
    "type": "FunctionNode",
    "qualified_name": "calc::compute",
    "name": "compute",
    "kind": "function",
    "layer": "design",
    "component_id": 7,
    "compound_refid": "module_calc",
    "visibility": "public",
    "brief_description": "Free function that computes a result",
    "detailed_description": "Invokes the calculator engine and returns the result.",
    "file_path": "/src/calc/compute.h",
    "line_number": 10,
    "definition": "CalculatorResult compute(Operation op, double a, double b)",
    "type_signature": "CalculatorResult",
    "argsstring": "(Operation op, double a, double b)",
    "source": "codegraph",
    "edges": []
}
```

**Create** `tests/member/test_function_serialization.py` — same pattern.

### 1.8 DefineNode

**Create** `tests/data/define_node_full.json`:
```json
{
    "type": "DefineNode",
    "qualified_name": "MAX_BUFFER_SIZE",
    "name": "MAX_BUFFER_SIZE",
    "kind": "define",
    "layer": "design",
    "component_id": 8,
    "compound_refid": "",
    "visibility": "public",
    "brief_description": "Maximum buffer size constant",
    "detailed_description": "Defines the upper limit for buffer allocation.",
    "file_path": "/src/calc/config.h",
    "line_number": 1,
    "definition": "#define MAX_BUFFER_SIZE 1024",
    "source": "codegraph",
    "edges": []
}
```

**Create** `tests/member/test_define_serialization.py` — same pattern.

### 1.9 NamespaceNode

**Create** `tests/data/namespace_node_full.json`:
```json
{
    "type": "NamespaceNode",
    "qualified_name": "calc",
    "name": "calc",
    "kind": "namespace",
    "layer": "design",
    "component_id": 9,
    "description": "Calculation engine namespace",
    "source": "codegraph",
    "edges": []
}
```

**Create** `tests/namespace/test_namespace_serialization.py` — same pattern. NamespaceNode has fewer fields.

### 1.10 ParameterNode

**Create** `tests/data/parameter_node_full.json`:
```json
{
    "type": "ParameterNode",
    "name": "op",
    "position": 0,
    "type": "Operation",
    "default_value": "",
    "member_refid": "calc::ICalculator::calculate",
    "source": "codegraph",
    "edges": []
}
```

**Create** `tests/parameter/test_parameter_serialization.py` — `SKIP_FIELDS = {"edges", "type"}` only (no UniqueIdProperty).

---

## Layer 2: Per-relationship edge tests (requires Neo4j)

Each test follows the pattern from `test_attribute_defined_in_file.py`.

### 2.1 COMPOSES: ClassNode → MethodNode

**Create** `tests/compound/test_class_composes_method.py`
- Create ClassNode("CalculatorEngine") + MethodNode("add"), save, connect via `class_node.methods.connect(method_node)`
- Assert COMPOSES edge, assert live graph

### 2.2 COMPOSES: ClassNode → AttributeNode

**Create** `tests/compound/test_class_composes_attribute.py`
- Create ClassNode("CalculatorEngine") + AttributeNode("precision"), save, connect via `class_node.attributes.connect(attr_node)`
- Assert COMPOSES edge, assert live graph

### 2.3 COMPOSES: EnumNode → EnumValueNode

**Create** `tests/compound/test_enum_composes_value.py`
- Create EnumNode("Operation") + EnumValueNode("ADD"), save, connect via `enum_node.values.connect(value_node)`
- Assert COMPOSES edge, assert live graph

### 2.4 COMPOSES: InterfaceNode → MethodNode

**Create** `tests/compound/test_interface_composes_method.py`
- Create InterfaceNode("ICalculator") + MethodNode("calculate"), save, connect via `interface_node.methods.connect(method_node)`
- Assert COMPOSES edge, assert live graph

### 2.5 COMPOSES: NamespaceNode → ClassNode

**Create** `tests/namespace/test_namespace_composes_class.py`
- Create NamespaceNode("calc") + ClassNode("CalculatorEngine"), save, connect via `namespace_node.compounds.connect(class_node)`
- Assert COMPOSES edge, assert live graph

### 2.6 INHERITS_FROM: ClassNode → ClassNode

**Create** `tests/compound/test_class_inherits.py`
- Create ClassNode("CalculatorWindow") + ClassNode("BaseWindow"), save, connect via `derived.base.connect(base_class)`
- Assert INHERITS_FROM edge, assert live graph

### 2.7 REALIZES: ClassNode → InterfaceNode

**Create** `tests/compound/test_class_realizes_interface.py`
- Create ClassNode("CalculatorEngine") + InterfaceNode("ICalculator"), save, connect via `class_node.realizes.connect(interface_node)`
- Assert REALIZES edge, assert live graph

### 2.8 DEPENDS_ON: ClassNode → ClassNode

**Create** `tests/compound/test_class_depends_on.py`
- Create ClassNode("CalculatorWindow") + ClassNode("CalculatorEngine"), save, connect via `dependent.depends_on.connect(dependency)`
- Assert DEPENDS_ON edge, assert live graph

### 2.9 INVOKES: MethodNode → MethodNode

**Create** `tests/member/test_method_invokes_method.py`
- Create MethodNode("handleEquals") + MethodNode("performCalculation"), save, connect via `caller.invokes.connect(callee)`
- Assert INVOKES edge, assert live graph

---

## Layer 3: Integration test

### 3.1 Update `tests/data/design_graph.json`

Replace the current flat format with `CodeGraphNode.serialize()` format:
- List of node objects, each with `type`, `_llm_fields`, and `edges` array
- Use only: COMPOSES, INHERITS_FROM, REALIZES, DEPENDS_ON, DEFINED_IN
- Include `source: "calculator"` on FileNode

Calculator scenario covers: ClassNode, InterfaceNode, EnumNode, EnumValueNode, MethodNode, AttributeNode, ModuleNode (NamespaceNode), FileNode with COMPOSES, INHERITS_FROM, REALIZES, DEPENDS_ON, and DEFINED_IN.

### 3.2 Create `tests/test_graph_integration.py`

Test steps:
1. Read `tests/data/design_graph.json`
2. Create all nodes via `CodeGraphNode.from_json(node_data).save()`, building uid_map from fixture uids to saved node uids
3. Connect all edges by iterating each node's `edges` array
4. Serialize entire graph, assert every node's type and `_llm_fields` roundtrip
5. Assert every edge in fixture matches a live edge in Neo4j
6. Assert total edge counts match