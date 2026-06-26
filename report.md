# Requirements Report

**Generated:** 2026-06-25 23:15 UTC  
**Tag filter:** `as-built`  
**Summary:** 28 HLRs, 151 LLRs, 152 distinct tests linked  

---

## Table of Contents

1. [Requirements for AssertionNode](#hlr-requirements-for-assertionnode) — `codegraph.models.test.AssertionNode` (9 LLRs)
2. [Requirements for AttributeNode](#hlr-requirements-for-attributenode) — `codegraph.models.member.AttributeNode` (6 LLRs)
3. [Requirements for ClassNode](#hlr-requirements-for-classnode) — `codegraph.models.compound.ClassNode` (1 LLRs)
4. [Requirements for CodeGraphDispatcher](#hlr-requirements-for-codegraphdispatcher) — `codegraph.tools.dispatcher.CodeGraphDispatcher` (2 LLRs)
5. [Requirements for CompositeEntry](#hlr-requirements-for-compositeentry) — `codegraph.graph.CompositeEntry` (15 LLRs)
6. [Requirements for DecomposedRequirementSchema](#hlr-requirements-for-decomposedrequirementschema) — `codegraph_requirements.schemas.DecomposedRequirementSchema` (2 LLRs)
7. [Requirements for DecompositionResult](#hlr-requirements-for-decompositionresult) — `codegraph_requirements.persistence.DecompositionResult` (2 LLRs)
8. [Requirements for DefineNode](#hlr-requirements-for-definenode) — `codegraph.models.member.DefineNode` (1 LLRs)
9. [Requirements for EnrichmentResult](#hlr-requirements-for-enrichmentresult) — `codegraph_enrich.base.EnrichmentResult` (7 LLRs)
10. [Requirements for EnrichmentSummary](#hlr-requirements-for-enrichmentsummary) — `codegraph_enrich.base.EnrichmentSummary` (3 LLRs)
11. [Requirements for EnumNode](#hlr-requirements-for-enumnode) — `codegraph.models.compound.EnumNode` (7 LLRs)
12. [Requirements for EnumValueNode](#hlr-requirements-for-enumvaluenode) — `codegraph.models.member.EnumValueNode` (4 LLRs)
13. [Requirements for FileNode](#hlr-requirements-for-filenode) — `codegraph.models.file.FileNode` (9 LLRs)
14. [Requirements for FunctionNode](#hlr-requirements-for-functionnode) — `codegraph.models.member.FunctionNode` (5 LLRs)
15. [Requirements for ImplementationNode](#hlr-requirements-for-implementationnode) — `codegraph.models.implementation.ImplementationNode` (10 LLRs)
16. [Requirements for InterfaceNode](#hlr-requirements-for-interfacenode) — `codegraph.models.compound.InterfaceNode` (8 LLRs)
17. [Requirements for LayerGraph](#hlr-requirements-for-layergraph) — `codegraph.graph.LayerGraph` (4 LLRs)
18. [Requirements for MarkdownImporter](#hlr-requirements-for-markdownimporter) — `codegraph.export.markdown.MarkdownImporter` (3 LLRs)
19. [Requirements for MethodNode](#hlr-requirements-for-methodnode) — `codegraph.models.member.MethodNode` (18 LLRs)
20. [Requirements for ModuleNode](#hlr-requirements-for-modulenode) — `codegraph.models.compound.ModuleNode` (2 LLRs)
21. [Requirements for NamespaceNode](#hlr-requirements-for-namespacenode) — `codegraph.models.namespace.NamespaceNode` (12 LLRs)
22. [Requirements for ParameterNode](#hlr-requirements-for-parameternode) — `codegraph.models.parameter.ParameterNode` (1 LLRs)
23. [Requirements for ParseDiagnostic](#hlr-requirements-for-parsediagnostic) — `codegraph.export.plantuml.ParseDiagnostic` (2 LLRs)
24. [Requirements for PlantUMLExporter](#hlr-requirements-for-plantumlexporter) — `codegraph.export.plantuml.PlantUMLExporter` (1 LLRs)
25. [Requirements for PlantUMLImporter](#hlr-requirements-for-plantumlimporter) — `codegraph.export.plantuml.PlantUMLImporter` (11 LLRs)
26. [Requirements for PlantUMLParseError](#hlr-requirements-for-plantumlparseerror) — `codegraph.export.plantuml.PlantUMLParseError` (1 LLRs)
27. [Requirements for ToolDispatcher](#hlr-requirements-for-tooldispatcher) — `codegraph.tools.dispatcher.ToolDispatcher` (3 LLRs)
28. [Requirements for UnionNode](#hlr-requirements-for-unionnode) — `codegraph.models.compound.UnionNode` (2 LLRs)

---

## Requirements for AssertionNode {#hlr-requirements-for-assertionnode}

**Description:** The AssertionNode system shall provide a complete data model for representing program assertions under test, including unique identification, default attributes, serialization with type discriminator and phase, and relationship to test fixtures.

**Compound:** `codegraph.models.test.AssertionNode`

**LLRs:** 9 | **Linked tests:** 9

### LLR 1: The AssertionNode shall automatically assign a unique identifier (uid) upon creation, which is a non-empty string.

**Verification tests:**

| Test | Module | Description |
|------|--------|-------------|
| `test_uid_auto_generated` | `test.test_assertion_node` | Verifies that an AssertionNode instance is automatically assigned a unique identifier (uid) upon creation, ensuring each |

### LLR 2: The AssertionNode shall have a default empty description when created without arguments.

**Verification tests:**

| Test | Module | Description |
|------|--------|-------------|
| `test_description_default_empty` | `test.test_assertion_node` | Verifies that a newly created AssertionNode instance has an empty description by default, ensuring the initial state is  |

### LLR 3: The serialization of an AssertionNode shall include the phase and operator fields with values matching the instance attributes.

**Verification tests:**

| Test | Module | Description |
|------|--------|-------------|
| `test_serialize_includes_phase` | `test.test_assertion_node` | Verifies that the serialized output of an AssertionNode includes the correct phase identifier, ensuring accurate reconst |

### LLR 4: The AssertionNode shall support a CHECKED_BY relationship to test fixture nodes, ensuring exactly one unique connection per assertion identifier.

**Verification tests:**

| Test | Module | Description |
|------|--------|-------------|
| `test_checked_by_connects_to_assertion` | `test.test_test_fixture_node` | CHECKED_BY links fixture to the assertion that checks it. |

### LLR 5: The AssertionNode shall have a kind attribute that defaults to 'assertion'.

**Verification tests:**

| Test | Module | Description |
|------|--------|-------------|
| `test_kind_defaults_to_assertion` | `test.test_assertion_node` | Verifies that when an AssertionNode is created, its type defaults to 'assertion', ensuring the node correctly identifies |

### LLR 6: The AssertionNode shall initialize with an empty tags list by default.

**Verification tests:**

| Test | Module | Description |
|------|--------|-------------|
| `test_tags_default_empty_list` | `test.test_assertion_node` | Verifies that a newly created AssertionNode instance initializes with an empty tags list, ensuring the default state is  |

### LLR 7: The AssertionNode shall have an operator field that defaults to 'eq' when not explicitly set.

**Verification tests:**

| Test | Module | Description |
|------|--------|-------------|
| `test_operator_defaults_to_eq` | `test.test_assertion_node` | Verifies that an AssertionNode is created with the operator field defaulting to 'eq', ensuring consistent behavior for a |

### LLR 8: The serialization of an AssertionNode shall include a type discriminator field set to 'AssertionNode'.

**Verification tests:**

| Test | Module | Description |
|------|--------|-------------|
| `test_serialize_includes_type_discriminator` | `test.test_assertion_node` | Verifies that the serialization of an AssertionNode includes a type discriminator, ensuring correct deserialization and  |

### LLR 9: The AssertionNode shall have an order attribute that defaults to zero.

**Verification tests:**

| Test | Module | Description |
|------|--------|-------------|
| `test_order_defaults_to_zero` | `test.test_assertion_node` | This test verifies that a newly created AssertionNode instance has its order attribute set to zero by default, ensuring  |

---

## Requirements for AttributeNode {#hlr-requirements-for-attributenode}

**Description:** The AttributeNode system shall provide a complete data model for representing program attributes including their composition relationships, file definitions, serialization roundtrip integrity, and relationship manager presence.

**Compound:** `codegraph.models.member.AttributeNode`

**LLRs:** 6 | **Linked tests:** 6

### LLR 1: The AttributeNode, when assigned to a ClassNode as a composed attribute, shall preserve the composition relationship through serialization and deserialization so that roundtrip fidelity is maintained.

**Verification tests:**

| Test | Module | Description |
|------|--------|-------------|
| `test_class_composes_attribute` | `compound.test_class_composes_attribute` | Verifies that a ClassNode with an assigned AttributeNode can be serialized and deserialized while preserving its structu |

### LLR 2: The AttributeNode shall have an 'implementation_ref' relationship manager.

**Verification tests:**

| Test | Module | Description |
|------|--------|-------------|
| `test_attribute_has_implementation_ref` | `member.test_member_search_fields` | AttributeNode has an implementation_ref relationship manager. |

### LLR 3: The AttributeNode, when defined in a file, shall preserve the 'defined_in' edge to the FileNode through serialization and deserialization so that roundtrip integrity is maintained.

**Verification tests:**

| Test | Module | Description |
|------|--------|-------------|
| `test_attribute_defined_in_file` | `member.test_attribute_defined_in_file` | Verifies that an attribute defined in a file is correctly serialized and deserialized through the system, ensuring round |

### LLR 4: The AttributeNode shall be correctly modeled as composed by a ClassNode, with exactly one parent representing that containing class.

**Verification tests:**

| Test | Module | Description |
|------|--------|-------------|
| `test_attribute_composed_by_class` | `member.test_attribute_composed_by_class` | This test verifies that an attribute node whose type is a custom class is correctly modeled as composed by that class, e |

### LLR 5: The ClassNode.walk_composes() method shall include AttributeNode instances among the composed children returned.

**Verification tests:**

| Test | Module | Description |
|------|--------|-------------|
| `test_walk_composes_returns_methods_and_attributes` | `test_codegraph_node` | ClassNode.walk_composes() returns composed methods and attributes. |

### LLR 6: The AttributeNode shall support serialization and deserialization using CompositeEntry.serialize and LayerGraph.deserialize so that a roundtrip produces an equivalent node of the same type and data.

**Verification tests:**

| Test | Module | Description |
|------|--------|-------------|
| `test_attribute_node_roundtrip` | `member.test_attribute_serialization` | This test verifies that an AttributeNode can be serialized and then deserialized without loss of data, ensuring roundtri |

---

## Requirements for ClassNode {#hlr-requirements-for-classnode}

**Description:** The ClassNode shall provide a complete data model.

**Compound:** `codegraph.models.compound.ClassNode`

**LLRs:** 1 | **Linked tests:** 1

### LLR 1: The system shall support serialization.

**Verification tests:**

| Test | Module | Description |
|------|--------|-------------|
| `test_class_composes_method` | `compound.test_class_composes_method` | Verifies that a ClassNode containing a MethodNode can be serialized, deserialized, and reconstructed correctly, ensuring |

---

## Requirements for CodeGraphDispatcher {#hlr-requirements-for-codegraphdispatcher}

**Description:** The CodeGraphDispatcher shall enforce a required fetch operation before allowing save or format-export actions, returning a clear error message when no graph is loaded.

**Compound:** `codegraph.tools.dispatcher.CodeGraphDispatcher`

**LLRs:** 2 | **Linked tests:** 2

### LLR 1: The CodeGraphDispatcher shall not allow saving the graph until a graph has been fetched, and shall return an error response containing the message 'No graph loaded' if save is attempted without a prior fetch.

**Verification tests:**

| Test | Module | Description |
|------|--------|-------------|
| `test_save_requires_fetch` | `test_tools` | Verifies that the ToolDispatcher requires a fetch operation before allowing a save, ensuring data consistency and preven |

### LLR 2: The CodeGraphDispatcher shall not allow format or export actions until a graph has been fetched, and shall return an error response containing the message 'No graph loaded' if such an action is attempted without a prior fetch.

**Verification tests:**

| Test | Module | Description |
|------|--------|-------------|
| `test_format_export_requires_fetch` | `test_tools` | Verifies that the dispatch method of CodeGraphDispatcher enforces a fetch step before format export, ensuring that expor |

---

## Requirements for CompositeEntry {#hlr-requirements-for-compositeentry}

**Description:** The CompositeEntry system shall wrap a code node and manage its composition, serialization, and integration into a LayerGraph, supporting export to multiple formats and round-trip preservation of relationships.

**Compound:** `codegraph.graph.CompositeEntry`

**LLRs:** 15 | **Linked tests:** 17

### LLR 1: The CompositeEntry shall serialize itself and forward field-based serialization to its wrapped node.

**Verification tests:**

| Test | Module | Description |
|------|--------|-------------|
| `test_composite_entry_serialize_fields` | `test_layer_graph` | CompositeEntry.serialize(fields=...) forwards to its node. |

### LLR 2: The CompositeEntry shall support PlantUML export for enum types including their enum value members.

**Verification tests:**

| Test | Module | Description |
|------|--------|-------------|
| `test_enum_to_png` | `test_plantuml` | Verifies that an EnumNode with its EnumValueNode members is correctly exported to a PNG image via export_plantuml, ensur |

### LLR 3: The CompositeEntry shall support PlantUML export for inheritance relationships.

**Verification tests:**

| Test | Module | Description |
|------|--------|-------------|
| `test_inheritance_to_png` | `test_plantuml` | Verifies that the PlantUML export correctly translates class inheritance relationships into a PNG diagram, ensuring the  |

### LLR 4: The CompositeEntry shall support PlantUML export for dependency relationships (depends_on arrows).

**Verification tests:**

| Test | Module | Description |
|------|--------|-------------|
| `test_depends_on_arrow` | `test_plantuml` | Verifies that the PlantUML export correctly renders a 'depends on' arrow relationship between two nodes, ensuring that d |

### LLR 5: The CompositeEntry shall support round-trip export and import via PlantUML while preserving inheritance relationships.

**Verification tests:**

| Test | Module | Description |
|------|--------|-------------|
| `test_round_trip_inheritance` | `test_plantuml` | This test verifies that inheritance relationships among classes are preserved when exporting a LayerGraph to PlantUML an |

### LLR 6: The CompositeEntry shall support Markdown export that includes inheritance information and a relationships section with dependencies.

**Verification tests:**

| Test | Module | Description |
|------|--------|-------------|
| `test_relationships_section` | `test_markdown` | Validates that the 'relationships' section of a Markdown export correctly renders dependencies between code elements, en |
| `test_inherits_from_inline` | `test_markdown` | Verifies that the Markdown export correctly handles a class node that inherits from an inline-syntax class, ensuring the |

### LLR 7: The CompositeEntry shall support round-trip export and import via Markdown while preserving inheritance relationships.

**Verification tests:**

| Test | Module | Description |
|------|--------|-------------|
| `test_round_trip_inheritance` | `test_markdown` | Verifies that exporting and then importing a class hierarchy containing inheritance relationships preserves the structur |

### LLR 8: The CompositeEntry, when part of a LayerGraph, shall support transformation to Cytoscape format producing one node for a simple class.

**Verification tests:**

| Test | Module | Description |
|------|--------|-------------|
| `test_layer_graph_to_cytoscape_single_class` | `test_viz` | A simple ClassNode without members renders as a Cy node. |

### LLR 9: The CompositeEntry shall support transformation to Cytoscape format including namespace nodes with an is_namespace flag and child nodes with a parent attribute.

**Verification tests:**

| Test | Module | Description |
|------|--------|-------------|
| `test_layer_graph_to_cytoscape_with_namespace` | `test_viz` | Namespace nodes get is_namespace flag and children get parent. |

### LLR 10: The CompositeEntry shall support transformation to Cytoscape format where a class with composed methods is represented as a single node with an html_label containing the method names.

**Verification tests:**

| Test | Module | Description |
|------|--------|-------------|
| `test_layer_graph_to_cytoscape_class_with_members` | `test_viz` | A class with composed methods produces UML label. |

### LLR 11: The CompositeEntry shall support transformation to Cytoscape format where references from collapsed methods become edges originating from the parent entry.

**Verification tests:**

| Test | Module | Description |
|------|--------|-------------|
| `test_layer_graph_to_cytoscape_method_reference_becomes_edge` | `test_viz` | A reference from a collapsed method becomes an edge from the parent. |

### LLR 12: The CompositeEntry shall support transformation to Cytoscape format that excludes edges referencing ImplementationNode objects.

**Verification tests:**

| Test | Module | Description |
|------|--------|-------------|
| `test_layer_graph_to_cytoscape_excludes_implementation_node` | `test_viz` | ImplementationNode references are excluded from edges. |

### LLR 13: The CompositeEntry shall support transformation to Cytoscape format that generates unique edge IDs when multiple edges exist from the same source to different targets.

**Verification tests:**

| Test | Module | Description |
|------|--------|-------------|
| `test_edge_ids_are_unique` | `test_viz` | Multiple edges from same source to different targets have unique IDs. |

### LLR 14: The CompositeEntry shall support transformation to Cytoscape format that produces edges for DEPENDS_ON relationships with correct source, target, and label.

**Verification tests:**

| Test | Module | Description |
|------|--------|-------------|
| `test_layer_graph_to_cytoscape_with_edges` | `test_viz` | References between nodes produce Cytoscape edges. |

### LLR 15: The CompositeEntry shall support transformation to Cytoscape format where the node's layer field reflects the layer tag of the entry (as-built or dependency).

**Verification tests:**

| Test | Module | Description |
|------|--------|-------------|
| `test_layer_graph_to_cytoscape_dependency_layer` | `test_viz` | dependency tag produces layer='dependency' in node data. |
| `test_layer_graph_to_cytoscape_as_built_layer` | `test_viz` | as-built tag produces layer='as-built' in node data. |

---

## Requirements for DecomposedRequirementSchema {#hlr-requirements-for-decomposedrequirementschema}

**Description:** The DecomposedRequirementSchema shall provide a flexible data model for representing decomposed requirements as a list of nodes, each with a designated type, accepting both empty input and structured node dictionaries.

**Compound:** `codegraph_requirements.schemas.DecomposedRequirementSchema`

**LLRs:** 2 | **Linked tests:** 2

### LLR 1: The DecomposedRequirementSchema shall accept an empty list of nodes, initializing its 'nodes' attribute to an empty list.

**Verification tests:**

| Test | Module | Description |
|------|--------|-------------|
| `test_decomposed_requirement_schema_empty` | `requirements` | Schema accepts empty nodes list. |

### LLR 2: The DecomposedRequirementSchema shall accept a list of node dictionaries, correctly parsing each node's 'type' field (e.g., 'LLR') and storing them in the 'nodes' attribute.

**Verification tests:**

| Test | Module | Description |
|------|--------|-------------|
| `test_decomposed_requirement_schema_with_nodes` | `requirements` | Schema accepts node dicts in codegraph format. |

---

## Requirements for DecompositionResult {#hlr-requirements-for-decompositionresult}

**Description:** The DecompositionResult system shall represent and track the outcome of a decomposition process, including counts of added, updated, skipped, written, unchanged items, duration, errors, and scaffold mappings, with support for default and non-zero states and aggregate consistency.

**Compound:** `codegraph_requirements.persistence.DecompositionResult`

**LLRs:** 2 | **Linked tests:** 2

### LLR 1: The DecompositionResult shall initialize all numeric attributes to zero, the errors attribute to an empty list, and the scaffold_map attribute to an empty dictionary when created with default arguments.

**Verification tests:**

| Test | Module | Description |
|------|--------|-------------|
| `test_decomposition_result_defaults` | `requirements` | Result dataclass defaults to zeros. |

### LLR 2: The DecompositionResult shall correctly compute aggregate totals (total and handled) from its detailed counts and ensure that the handled count is included in the unhandled_categories list when initialized with non-zero values.

**Verification tests:**

| Test | Module | Description |
|------|--------|-------------|
| `test_decomposition_result_with_counts` | `requirements` | Result dataclass accepts non-zero values. |

---

## Requirements for DefineNode {#hlr-requirements-for-definenode}

**Description:** The DefineNode system shall ensure that each definition node possesses a relationship manager for linking to implementation code.

**Compound:** `codegraph.models.member.DefineNode`

**LLRs:** 1 | **Linked tests:** 1

### LLR 1: The DefineNode shall provide an implementation_ref attribute that acts as a relationship manager for linking to implementation code.

**Verification tests:**

| Test | Module | Description |
|------|--------|-------------|
| `test_define_has_implementation_ref` | `member.test_member_search_fields` | DefineNode has an implementation_ref relationship manager. |

---

## Requirements for EnrichmentResult {#hlr-requirements-for-enrichmentresult}

**Description:** The EnrichmentResult system shall provide a data model for representing enrichment results with attributes for state tracking, change detection, success/error handling, and dictionary serialization, as well as a summary method for grouping results by node type.

**Compound:** `codegraph_enrich.base.EnrichmentResult`

**LLRs:** 7 | **Linked tests:** 7

### LLR 1: The EnrichmentResult shall have default attribute values: provider as empty string, type as empty string, value as empty string, details as empty dict, error as None, and skipped as False.

**Verification tests:**

| Test | Module | Description |
|------|--------|-------------|
| `test_defaults` | `enrich.test_enrich_unit` | Verifies that a freshly instantiated EnrichmentResult has all default attributes set to their expected initial values, e |

### LLR 2: The EnrichmentResult shall report changed as True when the new description differs from the original description.

**Verification tests:**

| Test | Module | Description |
|------|--------|-------------|
| `test_changed_true_when_descriptions_differ` | `enrich.test_enrich_unit` | Verifies that an EnrichmentResult is marked as changed when its new description differs from the original, which is crit |

### LLR 3: The EnrichmentResult shall report changed as False when the new description is identical to the original description.

**Verification tests:**

| Test | Module | Description |
|------|--------|-------------|
| `test_changed_false_when_identical` | `enrich.test_enrich_unit` | Verifies that an EnrichmentResult initialized with identical data does not flag a change, ensuring correctness in change |

### LLR 4: The EnrichmentResult shall report success as False when an error is present.

**Verification tests:**

| Test | Module | Description |
|------|--------|-------------|
| `test_success_false_when_error` | `enrich.test_enrich_unit` | Verifies that an EnrichmentResult indicates failure by having its success attribute as False when an error is present, e |

### LLR 5: The EnrichmentResult shall report changed as False when the result is empty (default state).

**Verification tests:**

| Test | Module | Description |
|------|--------|-------------|
| `test_changed_false_when_empty` | `enrich.test_enrich_unit` | This test ensures that an empty EnrichmentResult correctly reports no changes, validating the baseline behavior of the c |

### LLR 6: The to_dict method of EnrichmentResult shall return a dictionary containing 'qualified_name', 'node_type', 'changed', and 'skipped' fields with values matching the instance attributes.

**Verification tests:**

| Test | Module | Description |
|------|--------|-------------|
| `test_to_dict` | `enrich.test_enrich_unit` | Verifies that the EnrichmentResult.to_dict method correctly serializes all relevant attributes (qualified name, node typ |

### LLR 7: The EnrichmentSummary.to_dict method shall group enrichment results by node type (fixtures, steps, assertions) and return a dictionary with target name, total count, and per-type lists containing qualified names and descriptions.

**Verification tests:**

| Test | Module | Description |
|------|--------|-------------|
| `test_to_dict_groups_by_node_type` | `enrich.test_enrich_unit` | This test ensures that the to_dict method of EnrichmentSummary correctly groups enriched elements by their node type (e. |

---

## Requirements for EnrichmentSummary {#hlr-requirements-for-enrichmentsummary}

**Description:** The EnrichmentSummary system shall provide a data model for summarizing and reporting enrichment results, including default state, node-type-based grouping, and error handling.

**Compound:** `codegraph_enrich.base.EnrichmentSummary`

**LLRs:** 3 | **Linked tests:** 3

### LLR 1: The EnrichmentSummary shall initialize with default counts (total, successful, failed, skipped) set to zero and an empty results list when no enrichment data is provided.

**Verification tests:**

| Test | Module | Description |
|------|--------|-------------|
| `test_empty_summary` | `enrich.test_enrich_unit` | The test validates that an EnrichmentSummary object is correctly instantiated with default empty values, ensuring the cl |

### LLR 2: The EnrichmentSummary's to_dict method shall return a dictionary that groups enriched elements by node type (fixtures, steps, assertions) with accurate counts, qualified names, and descriptions, and shall include the target name and total enriched count.

**Verification tests:**

| Test | Module | Description |
|------|--------|-------------|
| `test_to_dict_groups_by_node_type` | `enrich.test_enrich_unit` | This test ensures that the to_dict method of EnrichmentSummary correctly groups enriched elements by their node type (e. |

### LLR 3: The EnrichmentSummary's to_dict method shall include error messages in the resulting dictionary when the summary contains errors.

**Verification tests:**

| Test | Module | Description |
|------|--------|-------------|
| `test_to_dict_with_errors` | `enrich.test_enrich_unit` | Verifies that when an enrichment summary contains errors, the 'to_dict' method correctly includes the error messages in  |

---

## Requirements for EnumNode {#hlr-requirements-for-enumnode}

**Description:** The EnumNode system shall provide a complete data model for representing enumeration types, including their values, composition relationships, serialization, and export to PlantUML.

**Compound:** `codegraph.models.compound.EnumNode`

**LLRs:** 7 | **Linked tests:** 7

### LLR 1: The EnumNode shall support nested serialization that inlines its composed EnumValueNode children.

**Verification tests:**

| Test | Module | Description |
|------|--------|-------------|
| `test_class_composes_method` | `compound.test_class_composes_method` | Verifies that a ClassNode containing a MethodNode can be serialized, deserialized, and reconstructed correctly, ensuring |

### LLR 2: An EnumValueNode shall belong to exactly one parent EnumNode, establishing a one-to-one composition relationship.

**Verification tests:**

| Test | Module | Description |
|------|--------|-------------|
| `test_enum_value_composed_by_enum` | `member.test_enum_value_composed_by_enum` | Verifies that an EnumValueNode properly belongs to its parent EnumNode, ensuring the composition relationship is correct |

### LLR 3: The EnumNode shall have an implementation_ref relationship manager.

**Verification tests:**

| Test | Module | Description |
|------|--------|-------------|
| `test_enum_has_implementation_ref` | `compound.test_compound_search_fields` | EnumNode has an implementation_ref relationship manager. |

### LLR 4: An EnumNode composed within a NamespaceNode shall survive a round-trip serialization and deserialization, preserving its type, fields, and composition edges.

**Verification tests:**

| Test | Module | Description |
|------|--------|-------------|
| `test_namespace_composes_enum` | `namespace.test_namespace_composes_enum` | Verifies that a NamespaceNode, which contains an EnumNode, can be composed, serialized, and deserialized correctly withi |

### LLR 5: An EnumNode shall be correctly composed within a NamespaceNode, having the namespace as its sole parent.

**Verification tests:**

| Test | Module | Description |
|------|--------|-------------|
| `test_enum_composed_by_namespace` | `compound.test_enum_composed_by_namespace` | Verifies that an EnumNode can be correctly composed within a NamespaceNode, ensuring the enumeration is properly nested  |

### LLR 6: An EnumNode composed of EnumValueNodes shall correctly serialize and deserialize through CompositeEntry and LayerGraph, preserving type, fields, and composition edges.

**Verification tests:**

| Test | Module | Description |
|------|--------|-------------|
| `test_enum_composes_value` | `compound.test_enum_composes_value` | Verifies that an EnumNode built from EnumValueNodes correctly serializes and deserializes through the CompositeEntry and |

### LLR 7: The EnumNode with its EnumValueNode members shall be correctly exported to a PNG image via PlantUML export.

**Verification tests:**

| Test | Module | Description |
|------|--------|-------------|
| `test_enum_to_png` | `test_plantuml` | Verifies that an EnumNode with its EnumValueNode members is correctly exported to a PNG image via export_plantuml, ensur |

---

## Requirements for EnumValueNode {#hlr-requirements-for-enumvaluenode}

**Description:** The EnumValueNode system shall represent a single enumerated value within an enumeration type and support correct parent-child composition, serialization, and PlantUML export.

**Compound:** `codegraph.models.member.EnumValueNode`

**LLRs:** 4 | **Linked tests:** 4

### LLR 1: The EnumValueNode shall be correctly composed by its parent EnumNode, so that the parent-child relationship is established with exactly one parent.

**Verification tests:**

| Test | Module | Description |
|------|--------|-------------|
| `test_enum_value_composed_by_enum` | `member.test_enum_value_composed_by_enum` | Verifies that an EnumValueNode properly belongs to its parent EnumNode, ensuring the composition relationship is correct |

### LLR 2: The EnumValueNode, when part of an EnumNode, shall support serialization roundtrip through CompositeEntry and LayerGraph, preserving the composition edge, target type, UID, and fields.

**Verification tests:**

| Test | Module | Description |
|------|--------|-------------|
| `test_enum_composes_value` | `compound.test_enum_composes_value` | Verifies that an EnumNode built from EnumValueNodes correctly serializes and deserializes through the CompositeEntry and |

### LLR 3: The EnumValueNode shall be included in the nested serialization of its parent EnumNode, with the serialized output containing all child enum values by name.

**Verification tests:**

| Test | Module | Description |
|------|--------|-------------|
| `test_nested_enum_composes_values` | `test_codegraph_node` | EnumNode.serialize(nested=True) inlines enum value children. |

### LLR 4: The EnumValueNode shall support PlantUML PNG export when part of an EnumNode in a LayerGraph, ensuring the diagram generation works end-to-end for enum types.

**Verification tests:**

| Test | Module | Description |
|------|--------|-------------|
| `test_enum_to_png` | `test_plantuml` | Verifies that an EnumNode with its EnumValueNode members is correctly exported to a PNG image via export_plantuml, ensur |

---

## Requirements for FileNode {#hlr-requirements-for-filenode}

**Description:** The FileNode system shall provide a complete data model for representing source files including serialization, identity, membership, and relationship management.

**Compound:** `codegraph.models.file.FileNode`

**LLRs:** 9 | **Linked tests:** 9

### LLR 1: The FileNode shall support serialization and deserialization that preserves all fields and type information, ensuring roundtrip fidelity.

**Verification tests:**

| Test | Module | Description |
|------|--------|-------------|
| `test_file_node_roundtrip` | `file.test_file_serialization` | Verifies that a FileNode can be serialized and then deserialized back to an identical FileNode, ensuring the roundtrip s |

### LLR 2: The FileNode shall generate an auto-generated unique identifier (uid) as a non-empty string for unsaved instances, and _node_key shall return that uid.

**Verification tests:**

| Test | Module | Description |
|------|--------|-------------|
| `test_file_node_instance_uses_uid` | `test_layer_graph` | Unsaved FileNode: uid is auto-generated (random), _node_key returns it. |

### LLR 3: The FileNode shall support a 'defined_in' relationship from MethodNodes, ensuring serialization and deserialization preserve edges that point to the correct FileNode instance.

**Verification tests:**

| Test | Module | Description |
|------|--------|-------------|
| `test_method_defined_in_file` | `member.test_method_defined_in_file` | Verifies that a method defined in a file is correctly serialized, deserialized, and represented within the code graph's  |

### LLR 4: The FileNode shall serialize LLM fields (path, name, source) and omit non-LLM fields (refid, language) by default.

**Verification tests:**

| Test | Module | Description |
|------|--------|-------------|
| `test_llm_fields_on_file_node` | `test_codegraph_node` | FileNode.serialize() includes _llm_fields but omits non-LLM fields. |

### LLR 5: The FileNode shall include the refid (uid) when serialized with fields='all', and the refid shall not be null.

**Verification tests:**

| Test | Module | Description |
|------|--------|-------------|
| `test_all_fields_on_file_node_includes_refid` | `test_codegraph_node` | FileNode.serialize(fields='all') includes refid (the uid). |

### LLR 6: The FileNode shall include the uid field in nested serialization even though uid is not in _llm_fields.

**Verification tests:**

| Test | Module | Description |
|------|--------|-------------|
| `test_nested_includes_uid_for_file_node` | `test_codegraph_node` | FileNode.serialize(nested=True) includes uid even though it's not in _llm_fields. |

### LLR 7: The FileNode shall provide a non-null, non-empty string uid (via _uid_value) for unsaved instances.

**Verification tests:**

| Test | Module | Description |
|------|--------|-------------|
| `test_uid_value_for_unsaved_file_node` | `test_codegraph_node` | FileNode gets auto-generated refid even before explicit save. |

### LLR 8: The FileNode shall support a 'defined_in' relationship from AttributeNodes, ensuring serialization and deserialization preserve edges that point to the correct FileNode instance.

**Verification tests:**

| Test | Module | Description |
|------|--------|-------------|
| `test_attribute_defined_in_file` | `member.test_attribute_defined_in_file` | Verifies that an attribute defined in a file is correctly serialized and deserialized through the system, ensuring round |

### LLR 9: The FileNode shall raise a ValueError when find_relationship_manager is called with a valid relation_type but a wrong target type (e.g., ClassNode).

**Verification tests:**

| Test | Module | Description |
|------|--------|-------------|
| `test_raises_on_wrong_target_type` | `test_codegraph_node` | Raises ValueError for a valid relation_type but wrong target type. |

---

## Requirements for FunctionNode {#hlr-requirements-for-functionnode}

**Description:** The FunctionNode system shall provide a complete data model for representing program functions including their namespace composition, implementation references, body location, doc embedding, and roundtrip serialization.

**Compound:** `codegraph.models.member.FunctionNode`

**LLRs:** 5 | **Linked tests:** 5

### LLR 1: The FunctionNode shall support a parent-child composition relationship with a NamespaceNode such that it has exactly one parent.

**Verification tests:**

| Test | Module | Description |
|------|--------|-------------|
| `test_function_composed_by_namespace` | `member.test_function_composed_by_namespace` | Verifies that a FunctionNode composed into a NamespaceNode correctly models the relationship between a function and its  |

### LLR 2: The FunctionNode shall expose an implementation_ref relationship manager attribute.

**Verification tests:**

| Test | Module | Description |
|------|--------|-------------|
| `test_function_has_implementation_ref` | `member.test_member_search_fields` | FunctionNode has an implementation_ref relationship manager. |

### LLR 3: The FunctionNode shall initialize its doc_embedding field as an empty list by default.

**Verification tests:**

| Test | Module | Description |
|------|--------|-------------|
| `test_function_doc_embedding_default` | `member.test_member_search_fields` | Verifies that the default docstring embedding for a FunctionNode is generated correctly, ensuring documentation-based se |

### LLR 4: The FunctionNode shall correctly store the body_start location (non-null) when created with a known value.

**Verification tests:**

| Test | Module | Description |
|------|--------|-------------|
| `test_function_body_start_stored` | `member.test_member_search_fields` | Verifies that the body start location of a function node is correctly stored, ensuring reliable code graph analysis and  |

### LLR 5: The FunctionNode shall support serialization and deserialization (roundtrip) such that a NamespaceNode composed with a FunctionNode preserves its type, fields, and composes edges with correct target type and UID.

**Verification tests:**

| Test | Module | Description |
|------|--------|-------------|
| `test_namespace_composes_function` | `namespace.test_namespace_composes_function` | Verifies that a NamespaceNode composes a FunctionNode correctly during deserialization of a LayerGraph, ensuring the str |

---

## Requirements for ImplementationNode {#hlr-requirements-for-implementationnode}

**Description:** The ImplementationNode system shall provide a comprehensive data model for representing method implementations, including storage of implementation text, embedding vectors, serialization, and automatic identifier generation.

**Compound:** `codegraph.models.implementation.ImplementationNode`

**LLRs:** 10 | **Linked tests:** 13

### LLR 1: The ImplementationNode shall allow creation without implementation text and shall set the implementation field to an empty string by default.

**Verification tests:**

| Test | Module | Description |
|------|--------|-------------|
| `test_implementation_default_empty` | `implementation.test_implementation_node` | Verifies that a newly created ImplementationNode instance has an empty default state (e.g., no children, empty content), |
| `test_empty_implementation_allowed` | `implementation.test_implementation_search_fields` | ImplementationNode can be created without implementation text. |

### LLR 2: The ImplementationNode shall automatically generate a non-empty UUID for its uid attribute when no value is provided.

**Verification tests:**

| Test | Module | Description |
|------|--------|-------------|
| `test_uid_auto_generated` | `implementation.test_implementation_node` | UniqueIdProperty auto-generates a UUID for uid when no value is provided. |

### LLR 3: The ImplementationNode shall ensure that its qualified_name matches the parent MethodNode's qualified_name and may be explicitly set.

**Verification tests:**

| Test | Module | Description |
|------|--------|-------------|
| `test_qualified_name_explicit_set` | `implementation.test_implementation_node` | qualified_name can be explicitly set to match the parent member. |
| `test_qualified_name_correlates_to_parent` | `implementation.test_implementation_search_fields` | ImplementationNode.qualified_name matches its parent MethodNode's qualified_name. |

### LLR 4: The ImplementationNode shall store and retrieve its attributes and relationships correctly.

**Verification tests:**

| Test | Module | Description |
|------|--------|-------------|
| `test_implementation_stored` | `implementation.test_implementation_node` | Verifies that an ImplementationNode can be stored and retrieved correctly, ensuring the node's attributes and relationsh |

### LLR 5: The ImplementationNode shall ensure that the impl_embedding attribute is a list, defaulting to an empty list when no embedding is provided.

**Verification tests:**

| Test | Module | Description |
|------|--------|-------------|
| `test_impl_embedding_default_empty` | `implementation.test_implementation_node` | This test verifies that a newly created ImplementationNode has an empty impl_embedding list by default, ensuring the mod |
| `test_impl_embedding_is_list` | `implementation.test_implementation_search_fields` | Verifies that the 'embedding' attribute of an ImplementationNode is stored as a list, ensuring consistency for downstrea |

### LLR 6: The ImplementationNode shall serialize its representation, excluding the impl_embedding field from the serialized output.

**Verification tests:**

| Test | Module | Description |
|------|--------|-------------|
| `test_serialize_excludes_embedding` | `implementation.test_implementation_node` | Verifies that the serialization of an ImplementationNode omits the embedding field, ensuring that exported data does not |

### LLR 7: The ImplementationNode shall correctly store and return a provided embedding vector.

**Verification tests:**

| Test | Module | Description |
|------|--------|-------------|
| `test_impl_embedding_stored` | `implementation.test_implementation_node` | Verifies that an ImplementationNode correctly stores and returns its embedding vector, ensuring that the model can persi |

### LLR 8: The ImplementationNode shall default its kind attribute to 'implementation'.

**Verification tests:**

| Test | Module | Description |
|------|--------|-------------|
| `test_kind_defaults_to_implementation` | `implementation.test_implementation_node` | Verifies that an ImplementationNode, when created without explicit arguments, defaults its 'kind' attribute to 'implemen |

### LLR 9: The ImplementationNode shall store the implementation text as a string and make it available for search indexing.

**Verification tests:**

| Test | Module | Description |
|------|--------|-------------|
| `test_implementation_field_is_string` | `implementation.test_implementation_search_fields` | Verifies that an ImplementationNode instance has a searchable field named 'description' that is stored as a string, ensu |

### LLR 10: The ImplementationNode shall include the implementation text in its serialized output.

**Verification tests:**

| Test | Module | Description |
|------|--------|-------------|
| `test_serialize_includes_implementation` | `implementation.test_implementation_node` | Verifies that the serialization of an ImplementationNode correctly includes all relevant data, ensuring that the output  |

---

## Requirements for InterfaceNode {#hlr-requirements-for-interfacenode}

**Description:** The InterfaceNode class shall model program interfaces by supporting composition with methods and namespaces, realization by classes, serialization roundtrip fidelity, default search fields, and relationship managers.

**Compound:** `codegraph.models.compound.InterfaceNode`

**LLRs:** 8 | **Linked tests:** 8

### LLR 1: The InterfaceNode shall preserve non-COMPOSES edges (such as REALIZES) in both nested and flat serialization modes.

**Verification tests:**

| Test | Module | Description |
|------|--------|-------------|
| `test_nested_preserves_non_composes_edges` | `test_codegraph_node` | Non-COMPOSES edges are preserved in both nested and flat modes. |

### LLR 2: The InterfaceNode shall support a realization relationship from a ClassNode that survives serialization and deserialization roundtrip with correct type and target reference.

**Verification tests:**

| Test | Module | Description |
|------|--------|-------------|
| `test_class_realizes_interface` | `compound.test_class_realizes_interface` | This test verifies that a ClassNode correctly realizes an InterfaceNode by serializing and deserializing the relationshi |

### LLR 3: The InterfaceNode shall be composable from a NamespaceNode with exactly one parent relationship.

**Verification tests:**

| Test | Module | Description |
|------|--------|-------------|
| `test_interface_composed_by_namespace` | `compound.test_interface_composed_by_namespace` | Verifies that an InterfaceNode can be properly composed from a NamespaceNode, ensuring correct structural relationships  |

### LLR 4: The InterfaceNode shall initialize its doc_embedding field as an empty list.

**Verification tests:**

| Test | Module | Description |
|------|--------|-------------|
| `test_interface_doc_embedding_default_empty` | `compound.test_compound_search_fields` | Verifies that a newly created InterfaceNode has an empty doc_embedding list by default, ensuring consistent initializati |

### LLR 5: The InterfaceNode shall correctly compute a MethodNode's composition so that the method has exactly one parent pointing to the interface.

**Verification tests:**

| Test | Module | Description |
|------|--------|-------------|
| `test_method_composed_by_interface` | `member.test_method_composed_by_parent` | Verifies that a method node correctly resolves its composition when inherited from a parent class and defined by an inte |

### LLR 6: The InterfaceNode shall support composition by a NamespaceNode that survives serialization and deserialization roundtrip with correct type and target reference.

**Verification tests:**

| Test | Module | Description |
|------|--------|-------------|
| `test_namespace_composes_interface` | `namespace.test_namespace_composes_interface` | Verifies that a NamespaceNode can successfully compose with an InterfaceNode and be serialized and deserialized via Comp |

### LLR 7: The InterfaceNode shall support composition of a MethodNode and preserve that composition through serialization and deserialization roundtrip with correct type, target reference, and single connected node.

**Verification tests:**

| Test | Module | Description |
|------|--------|-------------|
| `test_interface_composes_method` | `compound.test_interface_composes_method` | Verifies that an InterfaceNode correctly composes and serializes a MethodNode through CompositeEntry and LayerGraph oper |

### LLR 8: The InterfaceNode shall expose an implementation_ref relationship manager attribute.

**Verification tests:**

| Test | Module | Description |
|------|--------|-------------|
| `test_interface_has_implementation_ref` | `compound.test_compound_search_fields` | InterfaceNode has an implementation_ref relationship manager. |

---

## Requirements for LayerGraph {#hlr-requirements-for-layergraph}

**Description:** The LayerGraph system shall provide a complete data model for representing layered code structures including nodes, relationships, tags, serialization, and export to multiple formats.

**Compound:** `codegraph.graph.LayerGraph`

**LLRs:** 4 | **Linked tests:** 27

### LLR 1: The LayerGraph shall support tag validation, rejecting invalid tags and accepting valid ones, including multiple tags.

**Verification tests:**

| Test | Module | Description |
|------|--------|-------------|
| `test_invalid_tag_mixed_raises` | `test_layer_graph` | A valid tag mixed with an invalid one still raises. |
| `test_valid_dependency` | `test_layer_graph` | Verifies that a dependency with a valid tag is correctly accepted by LayerGraph, ensuring tag-based dependency validatio |
| `test_valid_multiple_tags` | `test_layer_graph` | Verifies that multiple tags can be assigned to a single layer without errors, ensuring the LayerGraph correctly handles  |
| `test_valid_design` | `test_layer_graph` | Verifies that a LayerGraph instance with valid tags is correctly constructed, ensuring tag validation logic does not rej |
| `test_invalid_tag_raises` | `test_layer_graph` | Verifies that providing an invalid tag to LayerGraph raises an appropriate error, ensuring that only properly formatted  |
| `test_valid_as_built` | `test_layer_graph` | Verifies that a layer graph tagged as 'as-built' passes validation, ensuring the system correctly recognizes and accepts |

### LLR 2: The LayerGraph shall correctly serialize and deserialize its structure, preserving nodes and edges.

**Verification tests:**

| Test | Module | Description |
|------|--------|-------------|
| `test_layer_graph_to_cytoscape_as_built_layer` | `test_viz` | as-built tag produces layer='as-built' in node data. |
| `test_layer_graph_to_cytoscape_empty_graph` | `test_viz` | Empty LayerGraph produces empty nodes/edges. |
| `test_layer_graph_to_cytoscape_dependency_layer` | `test_viz` | dependency tag produces layer='dependency' in node data. |
| `test_layer_graph_to_cytoscape_excludes_implementation_node` | `test_viz` | ImplementationNode references are excluded from edges. |
| `test_edge_ids_are_unique` | `test_viz` | Multiple edges from same source to different targets have unique IDs. |
| `test_layer_graph_to_cytoscape_method_reference_becomes_edge` | `test_viz` | A reference from a collapsed method becomes an edge from the parent. |
| `test_layer_graph_to_cytoscape_with_namespace` | `test_viz` | Namespace nodes get is_namespace flag and children get parent. |
| `test_layer_graph_to_cytoscape_with_edges` | `test_viz` | References between nodes produce Cytoscape edges. |
| `test_layer_graph_to_cytoscape_class_with_members` | `test_viz` | A class with composed methods produces UML label. |
| `test_layer_graph_to_cytoscape_single_class` | `test_viz` | A simple ClassNode without members renders as a Cy node. |

### LLR 3: The LayerGraph shall support export to PlantUML format, including empty graphs, inheritance, and dependencies, and compilation to PNG.

**Verification tests:**

| Test | Module | Description |
|------|--------|-------------|
| `test_depends_on_arrow` | `test_plantuml` | Verifies that the PlantUML export correctly renders a 'depends on' arrow relationship between two nodes, ensuring that d |
| `test_inheritance_to_png` | `test_plantuml` | Verifies that the PlantUML export correctly translates class inheritance relationships into a PNG diagram, ensuring the  |
| `test_enum_to_png` | `test_plantuml` | Verifies that an EnumNode with its EnumValueNode members is correctly exported to a PNG image via export_plantuml, ensur |
| `test_empty_graph_to_png` | `test_plantuml` | Verifies that exporting an empty LayerGraph to a PNG image via export_plantuml does not raise any errors, ensuring the s |
| `test_round_trip_inheritance` | `test_plantuml` | This test verifies that inheritance relationships among classes are preserved when exporting a LayerGraph to PlantUML an |
| `test_empty_graph_export` | `test_plantuml` | Verifies that exporting an empty LayerGraph via export_plantuml produces a valid PlantUML string with no errors, ensurin |

### LLR 4: The LayerGraph shall support export to Markdown format, including relationships, inheritance, and empty graphs.

**Verification tests:**

| Test | Module | Description |
|------|--------|-------------|
| `test_unknown_format_raises` | `test_markdown` | Verifies that the export_graph function raises an error when given an unsupported format, ensuring proper error handling |
| `test_round_trip_inheritance` | `test_markdown` | Verifies that exporting and then importing a class hierarchy containing inheritance relationships preserves the structur |
| `test_inherits_from_inline` | `test_markdown` | Verifies that the Markdown export correctly handles a class node that inherits from an inline-syntax class, ensuring the |
| `test_relationships_section` | `test_markdown` | Validates that the 'relationships' section of a Markdown export correctly renders dependencies between code elements, en |
| `test_empty_graph` | `test_markdown` | Verifies that exporting an empty LayerGraph via export_markdown produces correct output (likely an empty or minimal mark |

---

## Requirements for MarkdownImporter {#hlr-requirements-for-markdownimporter}

**Description:** The MarkdownImporter shall import Markdown documents and produce diagnostics to report structural integrity issues such as dangling relationship targets or sources, while correctly identifying well-formed content.

**Compound:** `codegraph.export.markdown.MarkdownImporter`

**LLRs:** 3 | **Linked tests:** 3

### LLR 1: The MarkdownImporter shall successfully import a valid Markdown document without generating any diagnostic warnings or errors.

**Verification tests:**

| Test | Module | Description |
|------|--------|-------------|
| `test_valid_document_no_diagnostics` | `test_markdown` | This test verifies that importing a valid Markdown document via MarkdownImporter.import_markdown produces no diagnostic  |

### LLR 2: The MarkdownImporter shall detect and report at least one diagnostic error when a relationship target does not exist in the imported data.

**Verification tests:**

| Test | Module | Description |
|------|--------|-------------|
| `test_dangling_relationship_target` | `test_markdown` | Verifies that the MarkdownImporter correctly detects and reports a dangling relationship target, ensuring import failure |

### LLR 3: The MarkdownImporter shall detect and report at least one diagnostic error when a relationship references a nonexistent source node.

**Verification tests:**

| Test | Module | Description |
|------|--------|-------------|
| `test_dangling_relationship_source` | `test_markdown` | Verifies that the MarkdownImporter correctly identifies and reports a relationship referencing a nonexistent source node |

---

## Requirements for MethodNode {#hlr-requirements-for-methodnode}

**Description:** The MethodNode system shall provide a complete data model for representing class methods including their composition, serialization, relationships, and persistence lifecycle.

**Compound:** `codegraph.models.member.MethodNode`

**LLRs:** 18 | **Linked tests:** 27

### LLR 1: The MethodNode shall support serialization of its fields and relationships so that roundtrip fidelity is maintained.

**Verification tests:**

| Test | Module | Description |
|------|--------|-------------|
| `test_method_invokes_method` | `member.test_method_invokes_method` | This test verifies that a method invocation is correctly serialized and deserialized by the CodeGraph system, ensuring t |
| `test_method_defined_in_file` | `member.test_method_defined_in_file` | Verifies that a method defined in a file is correctly serialized, deserialized, and represented within the code graph's  |
| `test_class_composes_method` | `compound.test_class_composes_method` | Verifies that a ClassNode containing a MethodNode can be serialized, deserialized, and reconstructed correctly, ensuring |
| `test_method_node_roundtrip` | `member.test_method_serialization` | Verifies that a MethodNode can be serialized and then deserialized without losing data, ensuring correctness in the pers |
| `test_interface_composes_method` | `compound.test_interface_composes_method` | Verifies that an InterfaceNode correctly composes and serializes a MethodNode through CompositeEntry and LayerGraph oper |

### LLR 2: The MethodNode shall have a body_start attribute that defaults to zero and stores a non-zero value when set.

**Verification tests:**

| Test | Module | Description |
|------|--------|-------------|
| `test_method_body_start_stored` | `member.test_member_search_fields` | Verifies that a MethodNode correctly stores the starting line number of its body within the source code, which ensures a |
| `test_method_body_start_default_zero` | `member.test_member_search_fields` | Verifies that the body_start attribute of a method node defaults to zero, ensuring consistent initialization of code loc |

### LLR 3: The MethodNode shall have a body_end attribute that defaults to zero.

**Verification tests:**

| Test | Module | Description |
|------|--------|-------------|
| `test_method_body_end_default_zero` | `member.test_member_search_fields` | Verifies that a method node's body_end attribute defaults to zero to ensure accurate tracking of method boundaries in co |

### LLR 4: The MethodNode shall have a doc_embedding attribute that defaults to an empty list and can store a list of floats.

**Verification tests:**

| Test | Module | Description |
|------|--------|-------------|
| `test_method_doc_embedding_stored` | `member.test_member_search_fields` | This test verifies that a method's documentation embedding is correctly stored and retrievable, preventing data loss or  |
| `test_method_doc_embedding_default_empty` | `member.test_member_search_fields` | Verifies that a MethodNode's doc_embedding field defaults to an empty value, ensuring the initial state of newly created |

### LLR 5: The MethodNode shall correctly identify its parent class when composed by a ClassNode.

**Verification tests:**

| Test | Module | Description |
|------|--------|-------------|
| `test_method_composed_by_class` | `member.test_method_composed_by_parent` | Verifies that a method node correctly identifies its parent class when inherited from a parent class, ensuring class com |

### LLR 6: The MethodNode shall correctly identify its parent interface when composed by an InterfaceNode.

**Verification tests:**

| Test | Module | Description |
|------|--------|-------------|
| `test_method_composed_by_interface` | `member.test_method_composed_by_parent` | Verifies that a method node correctly resolves its composition when inherited from a parent class and defined by an inte |

### LLR 7: The MethodNode shall support find_relationship_manager to locate matching relationship managers and raise ValueError for unknown relations.

**Verification tests:**

| Test | Module | Description |
|------|--------|-------------|
| `test_raises_on_unknown_relation` | `test_codegraph_node` | Raises ValueError when no matching relationship exists. |
| `test_finds_matching_manager` | `test_codegraph_node` | Finds the correct manager when relation_type + target match. |

### LLR 8: The MethodNode shall support fetch_all_by_tag across registered types to retrieve tagged nodes.

**Verification tests:**

| Test | Module | Description |
|------|--------|-------------|
| `test_fetch_all_by_tag_across_types` | `test_codegraph_node` | fetch_all_by_tag queries all registered types. |

### LLR 9: The MethodNode serialization with nested=True shall recursively include children of children.

**Verification tests:**

| Test | Module | Description |
|------|--------|-------------|
| `test_nested_recursive` | `test_codegraph_node` | serialize(nested=True) recursively includes children's children. |

### LLR 10: The MethodNode serialization with nested=False shall produce output identical to the old serialize() method.

**Verification tests:**

| Test | Module | Description |
|------|--------|-------------|
| `test_flat_mode_unchanged` | `test_codegraph_node` | serialize(nested=False) produces identical output to the old serialize(). |

### LLR 11: The MethodNode shall exclude body_location fields ('body_start', 'body_end') from its serialized output.

**Verification tests:**

| Test | Module | Description |
|------|--------|-------------|
| `test_method_serialize_excludes_body_location` | `member.test_member_search_fields` | Verifies that the serialize method of CompositeEntry excludes the body_location field, ensuring that serialized output i |

### LLR 12: The MethodNode shall exclude embedding fields ('doc_embedding', 'impl_embedding') from its serialized output.

**Verification tests:**

| Test | Module | Description |
|------|--------|-------------|
| `test_method_serialize_excludes_embeddings` | `member.test_member_search_fields` | Verifies that the serialize method of CompositeEntry correctly excludes embedding data from the output, ensuring that se |

### LLR 13: The MethodNode serialization with nested=True shall include composed children under the 'composes' key and exclude COMPOSES edges from the edges list.

**Verification tests:**

| Test | Module | Description |
|------|--------|-------------|
| `test_nested_removes_composes_from_edges` | `test_codegraph_node` | COMPOSES edges are removed from edges when nested=True. |
| `test_nested_includes_composes_key` | `test_codegraph_node` | serialize(nested=True) includes composed children under 'composes'. |

### LLR 14: The MethodNode serialization with nested=True shall omit the 'composes' key for leaf nodes that have no composition relationships.

**Verification tests:**

| Test | Module | Description |
|------|--------|-------------|
| `test_nested_no_composes_for_leaf_nodes` | `test_codegraph_node` | Leaf nodes (no COMPOSES edges) have no 'composes' key. |

### LLR 15: The MethodNode shall support fields propagation to child nodes in nested serialization when fields='all' is specified.

**Verification tests:**

| Test | Module | Description |
|------|--------|-------------|
| `test_nested_fields_propagates_to_children` | `test_codegraph_node` | fields='all' propagates to recursively serialized children. |

### LLR 16: The MethodNode shall preserve non-COMPOSES edges (e.g., REALIZES) in both nested and flat serialization modes.

**Verification tests:**

| Test | Module | Description |
|------|--------|-------------|
| `test_nested_preserves_non_composes_edges` | `test_codegraph_node` | Non-COMPOSES edges are preserved in both nested and flat modes. |

### LLR 17: The MethodNode shall support walk_composes() to return an empty list for leaf nodes and to include composed methods and attributes for parent nodes.

**Verification tests:**

| Test | Module | Description |
|------|--------|-------------|
| `test_walk_composes_returns_methods_and_attributes` | `test_codegraph_node` | ClassNode.walk_composes() returns composed methods and attributes. |
| `test_walk_composes_returns_empty_for_leaf_nodes` | `test_codegraph_node` | MethodNode.walk_composes() returns empty list. |

### LLR 18: The MethodNode shall have an implementation_ref relationship manager.

**Verification tests:**

| Test | Module | Description |
|------|--------|-------------|
| `test_method_has_implementation_ref` | `member.test_member_search_fields` | MethodNode has an implementation_ref relationship manager. |

---

## Requirements for ModuleNode {#hlr-requirements-for-modulenode}

**Description:** The ModuleNode system shall support composition with namespace nodes and ensure that serialization/deserialization preserves the module hierarchy and relationships.

**Compound:** `codegraph.models.compound.ModuleNode`

**LLRs:** 2 | **Linked tests:** 2

### LLR 1: The ModuleNode shall have exactly one parent namespace node, establishing a proper composition relationship.

**Verification tests:**

| Test | Module | Description |
|------|--------|-------------|
| `test_module_composed_by_namespace` | `compound.test_module_composed_by_namespace` | Verifies that a module correctly references its parent namespace and has exactly one parent, ensuring proper composition |

### LLR 2: The ModuleNode shall participate in serialization and deserialization such that its composition edge (including target type and UID) is preserved when round-tripped through a NamespaceNode.

**Verification tests:**

| Test | Module | Description |
|------|--------|-------------|
| `test_namespace_composes_module` | `namespace.test_namespace_composes_module` | Verifies that a [NamespaceNode] correctly composes its module hierarchy and that the resulting [ModuleNode] can be seria |

---

## Requirements for NamespaceNode {#hlr-requirements-for-namespacenode}

**Description:** The NamespaceNode system shall provide a complete data model for representing namespaces including their composition relationships with various code elements, serialization and deserialization fidelity, and support for export in multiple formats.

**Compound:** `codegraph.models.namespace.NamespaceNode`

**LLRs:** 12 | **Linked tests:** 30

### LLR 1: The NamespaceNode shall support serialization and deserialization that preserves its type and all scalar fields after a round-trip via CompositeEntry and LayerGraph.

**Verification tests:**

| Test | Module | Description |
|------|--------|-------------|
| `test_namespace_composes_union` | `namespace.test_namespace_composes_union` | Validates that a NamespaceNode containing a UnionNode is correctly serialized and deserialized through CompositeEntry an |
| `test_namespace_composes_function` | `namespace.test_namespace_composes_function` | Verifies that a NamespaceNode composes a FunctionNode correctly during deserialization of a LayerGraph, ensuring the str |
| `test_namespace_composes_class` | `namespace.test_namespace_composes_class` | Verifies that the composite namespace and class serialization/deserialization pipeline correctly reconstructs a Namespac |
| `test_namespace_composes_interface` | `namespace.test_namespace_composes_interface` | Verifies that a NamespaceNode can successfully compose with an InterfaceNode and be serialized and deserialized via Comp |
| `test_namespace_composes_module` | `namespace.test_namespace_composes_module` | Verifies that a [NamespaceNode] correctly composes its module hierarchy and that the resulting [ModuleNode] can be seria |
| `test_namespace_composes_enum` | `namespace.test_namespace_composes_enum` | Verifies that a NamespaceNode, which contains an EnumNode, can be composed, serialized, and deserialized correctly withi |
| `test_namespace_composes_namespace` | `namespace.test_namespace_composes_namespace` | Verifies that a NamespaceNode can be correctly serialized and deserialized via CodeGraphNode.serialize, LayerGraph.deser |

### LLR 2: The NamespaceNode's walk_composes() method shall return exactly the composed child nodes (e.g., ClassNode) when navigated.

**Verification tests:**

| Test | Module | Description |
|------|--------|-------------|
| `test_walk_composes_namespace_returns_classes` | `test_codegraph_node` | NamespaceNode.walk_composes() returns composed classes. |

### LLR 3: The NamespaceNode shall correctly model a hierarchy where an inner namespace has a parent namespace, ensuring accurate incoming composition relationships.

**Verification tests:**

| Test | Module | Description |
|------|--------|-------------|
| `test_namespace_composed_by_parent_namespace` | `namespace.test_namespace_composed_by_namespace_incoming` | Verifies that a NamespaceNode correctly composes its qualified name from the namespace that contains it (the parent name |

### LLR 4: The NamespaceNode shall support nested serialization (nested=True) that recursively includes children and grandchildren with their names and composition keys.

**Verification tests:**

| Test | Module | Description |
|------|--------|-------------|
| `test_nested_recursive` | `test_codegraph_node` | serialize(nested=True) recursively includes children's children. |

### LLR 5: The NamespaceNode shall maintain exactly one 'composes' edge per composed child element, and that edge shall correctly identify the child's type and UID after serialization and deserialization.

**Verification tests:**

| Test | Module | Description |
|------|--------|-------------|
| `test_namespace_composes_union` | `namespace.test_namespace_composes_union` | Validates that a NamespaceNode containing a UnionNode is correctly serialized and deserialized through CompositeEntry an |
| `test_namespace_composes_function` | `namespace.test_namespace_composes_function` | Verifies that a NamespaceNode composes a FunctionNode correctly during deserialization of a LayerGraph, ensuring the str |
| `test_namespace_composes_class` | `namespace.test_namespace_composes_class` | Verifies that the composite namespace and class serialization/deserialization pipeline correctly reconstructs a Namespac |
| `test_namespace_composes_interface` | `namespace.test_namespace_composes_interface` | Verifies that a NamespaceNode can successfully compose with an InterfaceNode and be serialized and deserialized via Comp |
| `test_namespace_composes_module` | `namespace.test_namespace_composes_module` | Verifies that a [NamespaceNode] correctly composes its module hierarchy and that the resulting [ModuleNode] can be seria |
| `test_namespace_composes_enum` | `namespace.test_namespace_composes_enum` | Verifies that a NamespaceNode, which contains an EnumNode, can be composed, serialized, and deserialized correctly withi |
| `test_namespace_composes_namespace` | `namespace.test_namespace_composes_namespace` | Verifies that a NamespaceNode can be correctly serialized and deserialized via CodeGraphNode.serialize, LayerGraph.deser |

### LLR 6: The NamespaceNode shall ensure that the number of connected nodes via composes edges is exactly one per composed child after round-trip serialization.

**Verification tests:**

| Test | Module | Description |
|------|--------|-------------|
| `test_namespace_composes_union` | `namespace.test_namespace_composes_union` | Validates that a NamespaceNode containing a UnionNode is correctly serialized and deserialized through CompositeEntry an |
| `test_namespace_composes_function` | `namespace.test_namespace_composes_function` | Verifies that a NamespaceNode composes a FunctionNode correctly during deserialization of a LayerGraph, ensuring the str |
| `test_namespace_composes_class` | `namespace.test_namespace_composes_class` | Verifies that the composite namespace and class serialization/deserialization pipeline correctly reconstructs a Namespac |
| `test_namespace_composes_interface` | `namespace.test_namespace_composes_interface` | Verifies that a NamespaceNode can successfully compose with an InterfaceNode and be serialized and deserialized via Comp |
| `test_namespace_composes_module` | `namespace.test_namespace_composes_module` | Verifies that a [NamespaceNode] correctly composes its module hierarchy and that the resulting [ModuleNode] can be seria |
| `test_namespace_composes_enum` | `namespace.test_namespace_composes_enum` | Verifies that a NamespaceNode, which contains an EnumNode, can be composed, serialized, and deserialized correctly withi |
| `test_namespace_composes_namespace` | `namespace.test_namespace_composes_namespace` | Verifies that a NamespaceNode can be correctly serialized and deserialized via CodeGraphNode.serialize, LayerGraph.deser |

### LLR 7: A FunctionNode composed into a NamespaceNode shall have exactly one parent, which is the NamespaceNode.

**Verification tests:**

| Test | Module | Description |
|------|--------|-------------|
| `test_function_composed_by_namespace` | `member.test_function_composed_by_namespace` | Verifies that a FunctionNode composed into a NamespaceNode correctly models the relationship between a function and its  |

### LLR 8: An InterfaceNode composed by a NamespaceNode shall have exactly one parent, which is the NamespaceNode.

**Verification tests:**

| Test | Module | Description |
|------|--------|-------------|
| `test_interface_composed_by_namespace` | `compound.test_interface_composed_by_namespace` | Verifies that an InterfaceNode can be properly composed from a NamespaceNode, ensuring correct structural relationships  |

### LLR 9: A UnionNode composed by a NamespaceNode shall have exactly one parent, which is the NamespaceNode.

**Verification tests:**

| Test | Module | Description |
|------|--------|-------------|
| `test_union_composed_by_namespace` | `compound.test_union_composed_by_namespace` | Verifies that a UnionNode composed by a NamespaceNode correctly reflects its parent namespace, ensuring the union compos |

### LLR 10: A ClassNode composed into a NamespaceNode shall have exactly one parent, which is the NamespaceNode.

**Verification tests:**

| Test | Module | Description |
|------|--------|-------------|
| `test_class_composed_by_namespace` | `compound.test_class_composed_by_namespace` | Verifies that a ClassNode composed with a NamespaceNode correctly integrates and produces the expected combined behavior |

### LLR 11: A ModuleNode composed from a NamespaceNode shall have exactly one parent, which is the NamespaceNode.

**Verification tests:**

| Test | Module | Description |
|------|--------|-------------|
| `test_module_composed_by_namespace` | `compound.test_module_composed_by_namespace` | Verifies that a module correctly references its parent namespace and has exactly one parent, ensuring proper composition |

### LLR 12: An EnumNode composed within a NamespaceNode shall have exactly one parent, which is the NamespaceNode.

**Verification tests:**

| Test | Module | Description |
|------|--------|-------------|
| `test_enum_composed_by_namespace` | `compound.test_enum_composed_by_namespace` | Verifies that an EnumNode can be correctly composed within a NamespaceNode, ensuring the enumeration is properly nested  |

---

## Requirements for ParameterNode {#hlr-requirements-for-parameternode}

**Description:** The ParameterNode system shall allow identification and retrieval of nodes using a unique identifier as the node key.

**Compound:** `codegraph.models.parameter.ParameterNode`

**LLRs:** 1 | **Linked tests:** 1

### LLR 1: The ParameterNode shall use its UID as the node key returned by LayerGraph._node_key.

**Verification tests:**

| Test | Module | Description |
|------|--------|-------------|
| `test_parameter_node_uses_uid` | `test_layer_graph` | ParameterNode now has uid UniqueIdProperty, so _node_key returns uid. |

---

## Requirements for ParseDiagnostic {#hlr-requirements-for-parsediagnostic}

**Description:** The ParseDiagnostic system shall represent individual parsing diagnostics with severity, error code, and message details, and integrate into multi-diagnostic error messages.

**Compound:** `codegraph.export.plantuml.ParseDiagnostic`

**LLRs:** 2 | **Linked tests:** 2

### LLR 1: The ParseDiagnostic shall provide a string representation that includes its error code, severity level, and descriptive message.

**Verification tests:**

| Test | Module | Description |
|------|--------|-------------|
| `test_parse_diagnostic_str` | `test_plantuml` | ParseDiagnostic has a useful string representation. |

### LLR 2: The PlantUMLParseError shall compose an error message that lists all diagnostics, including their line numbers and specific diagnostic content.

**Verification tests:**

| Test | Module | Description |
|------|--------|-------------|
| `test_parse_error_message` | `test_plantuml` | PlantUMLParseError message lists all diagnostics. |

---

## Requirements for PlantUMLExporter {#hlr-requirements-for-plantumlexporter}

**Description:** The PlantUMLExporter shall provide a convenience method to export a CodeGraph to a valid PlantUML diagram string.

**Compound:** `codegraph.export.plantuml.PlantUMLExporter`

**LLRs:** 1 | **Linked tests:** 1

### LLR 1: The PlantUMLExporter shall export a simple CodeGraph as a PlantUML diagram string that includes the '@startuml' tag.

**Verification tests:**

| Test | Module | Description |
|------|--------|-------------|
| `test_exporter_class_direct` | `test_plantuml` | Verifies that the PlantUMLExporter can directly export a simple graph using its convenience method, ensuring that the ex |

---

## Requirements for PlantUMLImporter {#hlr-requirements-for-plantumlimporter}

**Description:** The PlantUMLImporter shall parse PlantUML diagram text and produce a code graph with diagnostic messages that report syntax errors, warnings for unrecognized content, and provide accurate line numbers while handling unknown elements with fallback behavior.

**Compound:** `codegraph.export.plantuml.PlantUMLImporter`

**LLRs:** 11 | **Linked tests:** 12

### LLR 1: The PlantUMLImporter shall generate no diagnostics when importing a well-formed PlantUML diagram.

**Verification tests:**

| Test | Module | Description |
|------|--------|-------------|
| `test_valid_diagram_has_no_diagnostics` | `test_plantuml` | A well-formed diagram produces zero diagnostics. |

### LLR 2: The PlantUMLImporter shall generate a warning diagnostic when an unknown stereotype is encountered, and shall fall back to a default element type (ClassNode) for the associated element.

**Verification tests:**

| Test | Module | Description |
|------|--------|-------------|
| `test_unknown_stereotype` | `test_plantuml` | Unknown stereotype → warning diagnostic, falls back to default. |

### LLR 3: The PlantUMLImporter shall correctly import a PlantUML diagram and produce a code graph with appropriate tags (e.g., frozenset({'as-built'})) and expected contents.

**Verification tests:**

| Test | Module | Description |
|------|--------|-------------|
| `test_importer_class_direct` | `test_plantuml` | Verifies that the PlantUMLImporter class can directly import and parse PlantUML content without intermediate steps, ensu |

### LLR 4: The PlantUMLImporter shall generate an error diagnostic when an arrow references an unknown source alias, and the error message shall include the phrase 'source alias'.

**Verification tests:**

| Test | Module | Description |
|------|--------|-------------|
| `test_dangling_arrow_source` | `test_plantuml` | Arrow with unknown source alias → error diagnostic. |

### LLR 5: The PlantUMLImporter shall generate an error diagnostic when an arrow references an unknown target alias, and the error message shall include the phrase 'target alias'.

**Verification tests:**

| Test | Module | Description |
|------|--------|-------------|
| `test_dangling_arrow_target` | `test_plantuml` | Arrow with unknown target alias → error diagnostic. |

### LLR 6: The PlantUMLImporter shall generate a warning diagnostic when an unrecognized line appears at the root level or inside an element, and the diagnostic shall provide context about the problematic line.

**Verification tests:**

| Test | Module | Description |
|------|--------|-------------|
| `test_unrecognized_line_at_root` | `test_plantuml` | Unrecognized content at root level → warning. |
| `test_unrecognized_line_inside_body` | `test_plantuml` | Unrecognized content inside an element → warning with context. |

### LLR 7: The PlantUMLImporter shall generate diagnostics with accurate 1-based line numbers.

**Verification tests:**

| Test | Module | Description |
|------|--------|-------------|
| `test_diagnostic_line_numbers` | `test_plantuml` | Diagnostics include accurate 1-based line numbers. |

### LLR 8: The PlantUMLImporter shall generate an error diagnostic when encountering an unmatched closing brace in a PlantUML diagram.

**Verification tests:**

| Test | Module | Description |
|------|--------|-------------|
| `test_unmatched_closing_brace` | `test_plantuml` | Extra '}' with nothing on the stack → error diagnostic. |

### LLR 9: The PlantUMLImporter shall generate a warning diagnostic when an unknown arrow label is encountered, and shall fall back to a default reference type (DEPENDS_ON) for that arrow.

**Verification tests:**

| Test | Module | Description |
|------|--------|-------------|
| `test_unknown_arrow_label` | `test_plantuml` | Unknown arrow label → warning, falls back to arrow default. |

### LLR 10: The PlantUMLImporter, when configured with strict=True, shall not raise an exception when only warning diagnostics are present.

**Verification tests:**

| Test | Module | Description |
|------|--------|-------------|
| `test_strict_mode_ok_on_warnings_only` | `test_plantuml` | strict=True does NOT raise when only warnings exist. |

### LLR 11: The PlantUMLImporter shall generate warning diagnostics for unclosed elements (missing closing braces), and shall detect all such instances.

**Verification tests:**

| Test | Module | Description |
|------|--------|-------------|
| `test_unclosed_element` | `test_plantuml` | Open brace never closed → warning diagnostic. |

---

## Requirements for PlantUMLParseError {#hlr-requirements-for-plantumlparseerror}

**Description:** The PlantUMLParseError class shall provide a structured error representation for PlantUML parsing that aggregates and formats diagnostic messages for comprehensible output.

**Compound:** `codegraph.export.plantuml.PlantUMLParseError`

**LLRs:** 1 | **Linked tests:** 1

### LLR 1: The PlantUMLParseError message shall list all diagnostics, including their line numbers and descriptions (e.g., 'Arrow target', 'Unexpected'), so that all parsing issues are reported.

**Verification tests:**

| Test | Module | Description |
|------|--------|-------------|
| `test_parse_error_message` | `test_plantuml` | PlantUMLParseError message lists all diagnostics. |

---

## Requirements for ToolDispatcher {#hlr-requirements-for-tooldispatcher}

**Description:** The ToolDispatcher system shall manage tool registration and dispatch, ensuring unique tool names, providing schema metadata, and enabling user-defined tool execution.

**Compound:** `codegraph.tools.dispatcher.ToolDispatcher`

**LLRs:** 3 | **Linked tests:** 3

### LLR 1: The ToolDispatcher shall raise an error when an attempt is made to register a tool with a name that has already been registered.

**Verification tests:**

| Test | Module | Description |
|------|--------|-------------|
| `test_duplicate_registration_raises` | `test_tools` | This test verifies that the ToolDispatcher's register method raises an appropriate error when an attempt is made to regi |

### LLR 2: The ToolDispatcher shall expose an all_tool_schemas property that returns an empty list when no tools are registered and a non-empty list after tools are registered.

**Verification tests:**

| Test | Module | Description |
|------|--------|-------------|
| `test_all_tool_schemas_property` | `test_tools` | This test verifies that the `ToolDispatcher` class correctly exposes the JSON schemas of all registered tools through it |

### LLR 3: The ToolDispatcher shall successfully register and dispatch a custom tool, returning the expected result upon invocation.

**Verification tests:**

| Test | Module | Description |
|------|--------|-------------|
| `test_custom_tool_dispatch` | `test_tools` | Verifies that the ToolDispatcher correctly registers and dispatches a custom tool, ensuring the system can extend and in |

---

## Requirements for UnionNode {#hlr-requirements-for-unionnode}

**Description:** The UnionNode system shall represent a union type within a namespace, support parent-child relationships, and preserve structural integrity through serialization round-trips.

**Compound:** `codegraph.models.compound.UnionNode`

**LLRs:** 2 | **Linked tests:** 2

### LLR 1: The UnionNode shall support a single parent namespace relationship such that a composed UnionNode has exactly one parent which is the intended NamespaceNode.

**Verification tests:**

| Test | Module | Description |
|------|--------|-------------|
| `test_union_composed_by_namespace` | `compound.test_union_composed_by_namespace` | Verifies that a UnionNode composed by a NamespaceNode correctly reflects its parent namespace, ensuring the union compos |

### LLR 2: The UnionNode shall support serialization and deserialization round-trip of its composition relationship with a NamespaceNode, preserving node type, fields, composition edges, and connectivity.

**Verification tests:**

| Test | Module | Description |
|------|--------|-------------|
| `test_namespace_composes_union` | `namespace.test_namespace_composes_union` | Validates that a NamespaceNode containing a UnionNode is correctly serialized and deserialized through CompositeEntry an |

---
