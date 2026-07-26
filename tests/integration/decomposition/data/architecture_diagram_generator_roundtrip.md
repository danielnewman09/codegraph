# codegraph: design

## HLR: `Architecture Diagram Generator`
The Architecture Diagram Generator shall produce a single unified PlantUML diagram that renders the complete module/architecture view of a codegraph project. The generator shall query the codegraph Neo4j store for all modules/namespaces and their composition/dependency relationships, aggregate them into one coherent diagram, and emit valid PlantUML component-diagram syntax. The diagram shall use package notation for modules/namespaces, show key classes inside each package (medium detail level), render directed relationship arrows between packages, filter out packages below a configurable minimum entity count, produce deterministic output for the same input graph, and support standalone export to .puml files.
- qualified_name: Architecture Diagram Generator
- tags: design
### LLR: `Diagram Generation Operation`
The Architecture Diagram Generator exposes a generate_diagram operation that accepts a DiagramConfig (containing Neo4j connection parameters, a minimum entity count threshold, and an optional output file path) and returns a DiagramResult containing the PlantUML diagram string on success. On failure, it signals an error via error_type indicating Neo4jConnectionError (when Neo4j connection fails), QueryExecutionError (when the graph query fails), or FileWriteError (when writing the output file fails).
- qualified_name: Diagram Generation Operation
- tags: design
#### Test: `vm::generate::test_valid_config`
Invoke generate_diagram with a valid DiagramConfig and verify the result indicates success and contains a non-empty diagram string.
- kind: test
- method: automated
- qualified_name: vm::generate::test_valid_config
- tags: design
- test_name: test_generate_diagram_returns_diagram_for_valid_config
##### Assertion: `cond::pre::valid_config_provided`
A valid DiagramConfig with reachable Neo4j connection, min_entity_count of 0, and no output_path is prepared.
- kind: assertion
- operator: is_true
- order: 0
- phase: pre
- qualified_name: cond::pre::valid_config_provided
- tags: design

##### Assertion: `cond::post::success_true`
DiagramResult::is_success is true after generate_diagram returns.
- kind: assertion
- operator: is_true
- order: 0
- phase: post
- qualified_name: cond::post::success_true
- tags: design

##### Assertion: `cond::post::diagram_not_empty`
DiagramResult::diagram_text is a non-empty string after generate_diagram returns.
- kind: assertion
- operator: is_true
- order: 0
- phase: post
- qualified_name: cond::post::diagram_not_empty
- tags: design

##### TestStep: `step::invoke_generate_valid`
Invoke ArchDiagramGenerator::generate_diagram with the valid DiagramConfig.
- kind: test_step
- order: 0
- qualified_name: step::invoke_generate_valid
- tags: design


#### Test: `vm::generate::test_neo4j_connection_error`
Invoke generate_diagram with a DiagramConfig containing invalid Neo4j connection parameters and verify the result signals Neo4jConnectionError.
- kind: test
- method: automated
- qualified_name: vm::generate::test_neo4j_connection_error
- tags: design
- test_name: test_generate_diagram_signals_neo4j_connection_error
##### Assertion: `cond::pre::invalid_connection_config`
A DiagramConfig with an unreachable Neo4j URI, wrong credentials, or missing host is prepared.
- kind: assertion
- operator: is_false
- order: 0
- phase: pre
- qualified_name: cond::pre::invalid_connection_config
- tags: design

##### Assertion: `cond::post::success_false`
DiagramResult::is_success is false after generate_diagram returns with invalid connection.
- kind: assertion
- operator: is_false
- order: 0
- phase: post
- qualified_name: cond::post::success_false
- tags: design

##### Assertion: `cond::post::error_is_neo4j_connection`
DiagramResult::error_type equals Neo4jConnectionError after connection failure.
- kind: assertion
- operator: ==
- order: 0
- phase: post
- qualified_name: cond::post::error_is_neo4j_connection
- tags: design

##### TestStep: `step::invoke_generate_invalid_connection`
Invoke ArchDiagramGenerator::generate_diagram with the DiagramConfig containing invalid Neo4j connection parameters.
- kind: test_step
- order: 0
- qualified_name: step::invoke_generate_invalid_connection
- tags: design



### LLR: `Package and Class Rendering`
The generated PlantUML diagram shall render each queried module/namespace as a PlantUML package (package notation) containing the names of its constituent classes at medium detail level. Packages with zero classes after filtering are still rendered as empty packages.
- qualified_name: Package and Class Rendering
- tags: design
#### Test: `vm::package::test_notation`
Invoke generate_diagram with a graph containing modules and verify each module is rendered as a PlantUML package block in the output.
- kind: test
- method: automated
- qualified_name: vm::package::test_notation
- tags: design
- test_name: test_package_notation_uses_plantuml_package_syntax
##### Assertion: `cond::pre::graph_with_modules`
The Neo4j graph contains at least two modules/namespaces with no classes inside them.
- kind: assertion
- operator: is_true
- order: 0
- phase: pre
- qualified_name: cond::pre::graph_with_modules
- tags: design

##### Assertion: `cond::post::packages_present`
The output diagram string contains PlantUML package notations (lines matching pattern 'package <name> {') for each module in the input graph.
- kind: assertion
- operator: is_true
- order: 0
- phase: post
- qualified_name: cond::post::packages_present
- tags: design

##### TestStep: `step::invoke_generate_modules_graph`
Invoke ArchDiagramGenerator::generate_diagram with a graph containing multiple modules/namespaces.
- kind: test_step
- order: 0
- qualified_name: step::invoke_generate_modules_graph
- tags: design



### LLR: `Entity Count Filtering`
The generator shall exclude from the diagram any package/module whose entity count (number of classes) is strictly below the configured minimum entity count threshold from DiagramConfig. Packages meeting or exceeding the threshold SHALL be included.
- qualified_name: Entity Count Filtering
- tags: design
#### Test: `vm::filter::test_below_threshold_excluded`
Configure DiagramConfig with min_entity_count=3, provide a graph where a package has 2 entities, invoke generate_diagram, and verify the output does NOT contain that package.
- kind: test
- method: automated
- qualified_name: vm::filter::test_below_threshold_excluded
- tags: design
- test_name: test_packages_below_min_entity_count_are_excluded
##### Assertion: `cond::pre::config_with_threshold_3`
DiagramConfig is configured with min_entity_count = 3.
- kind: assertion
- operator: ==
- order: 0
- phase: pre
- qualified_name: cond::pre::config_with_threshold_3
- tags: design

##### Assertion: `cond::pre::graph_with_small_package`
The Neo4j graph contains a package with exactly 2 entities (below the threshold of 3).
- kind: assertion
- operator: is_true
- order: 0
- phase: pre
- qualified_name: cond::pre::graph_with_small_package
- tags: design

##### Assertion: `cond::post::small_package_absent`
The output diagram does NOT contain the package that had 2 entities (below threshold of 3).
- kind: assertion
- operator: is_false
- order: 0
- phase: post
- qualified_name: cond::post::small_package_absent
- tags: design

##### TestStep: `step::invoke_generate_filter_test`
Invoke ArchDiagramGenerator::generate_diagram with the configured DiagramConfig and graph for filter testing.
- kind: test_step
- order: 0
- qualified_name: step::invoke_generate_filter_test
- tags: design



### LLR: `Deterministic Output`
The generator shall produce identical PlantUML diagram output for identical input graph data across multiple invocations. Package ordering, class ordering within packages, and arrow ordering shall be stable and repeatable.
- qualified_name: Deterministic Output
- tags: design
#### Test: `vm::deterministic::test_identical_output`
Invoke generate_diagram twice with the identical DiagramConfig and Neo4j graph data, then compare the two output diagram strings for exact equality.
- kind: test
- method: automated
- qualified_name: vm::deterministic::test_identical_output
- tags: design
- test_name: test_same_input_produces_identical_output_across_invocations
##### Assertion: `cond::pre::valid_config_deterministic`
A valid DiagramConfig and a stable, unchanging Neo4j graph are prepared for the first invocation.
- kind: assertion
- operator: is_true
- order: 0
- phase: pre
- qualified_name: cond::pre::valid_config_deterministic
- tags: design

##### Assertion: `cond::post::first_output_not_empty`
The first invocation output is a non-empty string.
- kind: assertion
- operator: is_true
- order: 0
- phase: post
- qualified_name: cond::post::first_output_not_empty
- tags: design

##### Assertion: `cond::post::outputs_identical`
The second invocation output is identical to the first invocation output.
- kind: assertion
- operator: ==
- order: 0
- phase: post
- qualified_name: cond::post::outputs_identical
- tags: design

##### TestStep: `step::invoke_generate_first_time`
Invoke ArchDiagramGenerator::generate_diagram the first time with the prepared config and graph.
- kind: test_step
- order: 0
- qualified_name: step::invoke_generate_first_time
- tags: design

##### TestStep: `step::invoke_generate_second_time`
Invoke ArchDiagramGenerator::generate_diagram a second time with the identical config and graph.
- kind: test_step
- order: 0
- qualified_name: step::invoke_generate_second_time
- tags: design



### LLR: `Valid PlantUML Component-Diagram Syntax`
The generated PlantUML diagram shall be valid PlantUML component-diagram syntax. The output shall begin with @startuml and end with @enduml, use component-diagram notation, and be parsable by the PlantUML engine without syntax errors.
- qualified_name: Valid PlantUML Component-Diagram Syntax
- tags: design
#### Test: `vm::syntax::test_valid_plantuml`
Invoke generate_diagram with a valid config, pass the output diagram through a PlantUML syntax parser/validator, and verify no syntax errors are reported.
- kind: test
- method: automated
- qualified_name: vm::syntax::test_valid_plantuml
- tags: design
- test_name: test_diagram_is_valid_plantuml_component_diagram_syntax
##### Assertion: `cond::pre::valid_config_syntax_test`
A valid DiagramConfig with a graph containing several modules, classes, and relationships is prepared.
- kind: assertion
- operator: is_true
- order: 0
- phase: pre
- qualified_name: cond::pre::valid_config_syntax_test
- tags: design

##### Assertion: `cond::post::starts_with_startuml`
The diagram text starts with the '@startuml' directive.
- kind: assertion
- operator: is_true
- order: 0
- phase: post
- qualified_name: cond::post::starts_with_startuml
- tags: design

##### Assertion: `cond::post::ends_with_end_uml`
The diagram text ends with the '@enduml' directive.
- kind: assertion
- operator: is_true
- order: 0
- phase: post
- qualified_name: cond::post::ends_with_end_uml
- tags: design

##### TestStep: `step::invoke_generate_syntax_test`
Invoke ArchDiagramGenerator::generate_diagram with valid config and then pass the output to the PlantUML syntax validator.
- kind: test_step
- order: 0
- qualified_name: step::invoke_generate_syntax_test
- tags: design




## Class: `DiagramConfig`
**Public attributes:**
- `is_valid`
- `neo4j_is_reachable`
- `output_path_is_writable`
- `min_entity_count`
- kind: class
- qualified_name: DiagramConfig
- tags: design

## Class: `DiagramResult`
**Public attributes:**
- `is_success`
- `diagram_text`
- `error_type`
- kind: class
- qualified_name: DiagramResult
- tags: design

## Class: `ModuleData`
**Public attributes:**
- `has_multiple_packages`
- `packages_have_classes`
- `has_relationships`
- `has_package_with_entity_count`
- kind: class
- qualified_name: ModuleData
- tags: design

## Class: `ArchDiagramGenerator`
**Public attributes:**
- `generate_diagram`
- kind: class
- qualified_name: ArchDiagramGenerator
- tags: design

## Attribute: `DiagramConfig::is_valid`
- kind: attribute
- qualified_name: DiagramConfig::is_valid
- tags: scaffold

## Attribute: `DiagramConfig::neo4j_is_reachable`
- kind: attribute
- qualified_name: DiagramConfig::neo4j_is_reachable
- tags: scaffold

## Attribute: `DiagramConfig::output_path_is_writable`
- kind: attribute
- qualified_name: DiagramConfig::output_path_is_writable
- tags: scaffold

## Attribute: `DiagramConfig::min_entity_count`
- kind: attribute
- qualified_name: DiagramConfig::min_entity_count
- tags: scaffold

## Attribute: `DiagramResult::is_success`
- kind: attribute
- qualified_name: DiagramResult::is_success
- tags: scaffold

## Attribute: `DiagramResult::diagram_text`
- kind: attribute
- qualified_name: DiagramResult::diagram_text
- tags: scaffold

## Attribute: `DiagramResult::error_type`
- kind: attribute
- qualified_name: DiagramResult::error_type
- tags: scaffold

## Attribute: `ModuleData::has_multiple_packages`
- kind: attribute
- qualified_name: ModuleData::has_multiple_packages
- tags: scaffold

## Attribute: `ModuleData::packages_have_classes`
- kind: attribute
- qualified_name: ModuleData::packages_have_classes
- tags: scaffold

## Attribute: `ModuleData::has_relationships`
- kind: attribute
- qualified_name: ModuleData::has_relationships
- tags: scaffold

## Attribute: `ModuleData::has_package_with_entity_count`
- kind: attribute
- qualified_name: ModuleData::has_package_with_entity_count
- tags: scaffold

## Attribute: `ArchDiagramGenerator::generate_diagram`
- kind: attribute
- qualified_name: ArchDiagramGenerator::generate_diagram
- tags: scaffold

## Attribute: `Neo4jConnectionError`
- kind: attribute
- qualified_name: Neo4jConnectionError
- tags: scaffold

## Attribute: `QueryExecutionError`
- kind: attribute
- qualified_name: QueryExecutionError
- tags: scaffold

## Attribute: `FileWriteError`
- kind: attribute
- qualified_name: FileWriteError
- tags: scaffold

## Attribute: `PlantUMLValidator::has_syntax_errors`
- kind: attribute
- qualified_name: PlantUMLValidator::has_syntax_errors
- tags: scaffold

## Literal: `literal::true`
- kind: literal
- qualified_name: literal::true
- tags: scaffold
- value: true

## Literal: `literal::false`
- kind: literal
- qualified_name: literal::false
- tags: scaffold
- value: false

## Literal: `literal::3`
- kind: literal
- qualified_name: literal::3
- tags: scaffold
- value: 3

## Literal: `literal::2`
- kind: literal
- qualified_name: literal::2
- tags: scaffold
- value: 2

## Literal: `literal::not_empty`
- kind: literal
- qualified_name: literal::not_empty
- tags: scaffold
- value: not_empty

## Literal: `literal::contains_package_notation`
- kind: literal
- qualified_name: literal::contains_package_notation
- tags: scaffold
- value: contains_package_notation

## Literal: `literal::contains_excluded_package`
- kind: literal
- qualified_name: literal::contains_excluded_package
- tags: scaffold
- value: contains_excluded_package

## Literal: `literal::starts_with_startuml`
- kind: literal
- qualified_name: literal::starts_with_startuml
- tags: scaffold
- value: starts_with_startuml

## Literal: `literal::ends_with_end_uml`
- kind: literal
- qualified_name: literal::ends_with_end_uml
- tags: scaffold
- value: ends_with_end_uml

## Relationships
- `cond::pre::valid_config_provided` → `DiagramConfig::is_valid` **left_operand** (AttributeNode)
- `cond::pre::valid_config_provided` → `literal::true` **right_operand** (LiteralNode)
- `cond::post::success_true` → `DiagramResult::is_success` **left_operand** (AttributeNode)
- `cond::post::success_true` → `literal::true` **right_operand** (LiteralNode)
- `cond::post::diagram_not_empty` → `DiagramResult::diagram_text` **left_operand** (AttributeNode)
- `cond::post::diagram_not_empty` → `literal::not_empty` **right_operand** (LiteralNode)
- `step::invoke_generate_valid` → `ArchDiagramGenerator::generate_diagram` **callee** (AttributeNode)
- `cond::pre::invalid_connection_config` → `DiagramConfig::neo4j_is_reachable` **left_operand** (AttributeNode)
- `cond::pre::invalid_connection_config` → `literal::false` **right_operand** (LiteralNode)
- `cond::post::success_false` → `DiagramResult::is_success` **left_operand** (AttributeNode)
- `cond::post::success_false` → `literal::false` **right_operand** (LiteralNode)
- `cond::post::error_is_neo4j_connection` → `DiagramResult::error_type` **left_operand** (AttributeNode)
- `cond::post::error_is_neo4j_connection` → `Neo4jConnectionError` **right_operand** (AttributeNode)
- `step::invoke_generate_invalid_connection` → `ArchDiagramGenerator::generate_diagram` **callee** (AttributeNode)
- `cond::pre::graph_with_modules` → `ModuleData::has_multiple_packages` **left_operand** (AttributeNode)
- `cond::pre::graph_with_modules` → `literal::true` **right_operand** (LiteralNode)
- `cond::post::packages_present` → `DiagramResult::diagram_text` **left_operand** (AttributeNode)
- `cond::post::packages_present` → `literal::contains_package_notation` **right_operand** (LiteralNode)
- `step::invoke_generate_modules_graph` → `ArchDiagramGenerator::generate_diagram` **callee** (AttributeNode)
- `cond::pre::config_with_threshold_3` → `DiagramConfig::min_entity_count` **left_operand** (AttributeNode)
- `cond::pre::config_with_threshold_3` → `literal::3` **right_operand** (LiteralNode)
- `cond::pre::graph_with_small_package` → `ModuleData::has_package_with_entity_count` **left_operand** (AttributeNode)
- `cond::pre::graph_with_small_package` → `literal::2` **right_operand** (LiteralNode)
- `cond::post::small_package_absent` → `DiagramResult::diagram_text` **left_operand** (AttributeNode)
- `cond::post::small_package_absent` → `literal::contains_excluded_package` **right_operand** (LiteralNode)
- `step::invoke_generate_filter_test` → `ArchDiagramGenerator::generate_diagram` **callee** (AttributeNode)
- `cond::pre::valid_config_deterministic` → `DiagramConfig::is_valid` **left_operand** (AttributeNode)
- `cond::pre::valid_config_deterministic` → `literal::true` **right_operand** (LiteralNode)
- `cond::post::first_output_not_empty` → `DiagramResult::diagram_text` **left_operand** (AttributeNode)
- `cond::post::first_output_not_empty` → `literal::not_empty` **right_operand** (LiteralNode)
- `cond::post::outputs_identical` → `DiagramResult::diagram_text` **left_operand** (AttributeNode)
- `cond::post::outputs_identical` → `DiagramResult::diagram_text` **right_operand** (AttributeNode)
- `step::invoke_generate_first_time` → `ArchDiagramGenerator::generate_diagram` **callee** (AttributeNode)
- `step::invoke_generate_second_time` → `ArchDiagramGenerator::generate_diagram` **callee** (AttributeNode)
- `cond::pre::valid_config_syntax_test` → `DiagramConfig::is_valid` **left_operand** (AttributeNode)
- `cond::pre::valid_config_syntax_test` → `literal::true` **right_operand** (LiteralNode)
- `cond::post::starts_with_startuml` → `DiagramResult::diagram_text` **left_operand** (AttributeNode)
- `cond::post::starts_with_startuml` → `literal::starts_with_startuml` **right_operand** (LiteralNode)
- `cond::post::ends_with_end_uml` → `DiagramResult::diagram_text` **left_operand** (AttributeNode)
- `cond::post::ends_with_end_uml` → `literal::ends_with_end_uml` **right_operand** (LiteralNode)
- `step::invoke_generate_syntax_test` → `ArchDiagramGenerator::generate_diagram` **callee** (AttributeNode)
