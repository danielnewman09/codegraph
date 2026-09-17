# codegraph: design

## HLR: `Architecture Diagram Generator`
The Architecture Diagram Generator shall produce a single unified PlantUML diagram that renders the complete module/architecture view of a codegraph project. The generator shall query the codegraph Neo4j store for all modules/namespaces and their composition/dependency relationships, aggregate them into one coherent diagram, and emit valid PlantUML component-diagram syntax. The diagram shall use package notation for modules/namespaces, show key classes inside each package (medium detail level), render directed relationship arrows between packages, filter out packages below a configurable minimum entity count, produce deterministic output for the same input graph, and support standalone export to .puml files.
- qualified_name: Architecture Diagram Generator
- tags: design
### LLR: `llr_0ab516fa`
The Diagram Generator exposes an export_to_file operation that accepts a PlantUML syntax string and a file path, writes the string as a .puml file, and returns a success indicator. The operation signals an error on file system failure or invalid file path.
- tags: design
#### Test: `vm::export::test_file_system_error`
Invoke export_to_file with an invalid file path (e.g., unwritable directory). Verify the operation signals an error state indicating file system failure.
- kind: test
- method: automated
- qualified_name: vm::export::test_file_system_error
- test_name: test_export_to_file_signals_error_on_fs_failure
##### Assertion: `cond::post::export_success_false`
- kind: assertion
- operator: is_false
- order: 0
- phase: post
- qualified_name: cond::post::export_success_false

##### Assertion: `cond::post::export_error_is_file_system`
- kind: assertion
- operator: ==
- order: 0
- phase: post
- qualified_name: cond::post::export_error_is_file_system

##### Assertion: `cond::pre::export_invalid_path`
- kind: assertion
- operator: is_true
- order: 0
- phase: pre
- qualified_name: cond::pre::export_invalid_path

##### TestStep: `step::invoke_export_to_file_invalid`
Invoke export_to_file with an invalid file path
- kind: test_step
- order: 0
- qualified_name: step::invoke_export_to_file_invalid


#### Test: `vm::export::test_successful_write`
Invoke export_to_file with a valid PlantUML string and a valid writable file path. Verify the file exists at the path, contains the expected content, and the operation returns a success indicator.
- kind: test
- method: automated
- qualified_name: vm::export::test_successful_write
- test_name: test_export_to_file_writes_puml_file
##### Assertion: `cond::post::export_success_true`
- kind: assertion
- operator: is_true
- order: 0
- phase: post
- qualified_name: cond::post::export_success_true

##### Assertion: `cond::post::export_file_content_matches`
- kind: assertion
- operator: ==
- order: 0
- phase: post
- qualified_name: cond::post::export_file_content_matches

##### Assertion: `cond::post::export_file_exists`
- kind: assertion
- operator: is_true
- order: 0
- phase: post
- qualified_name: cond::post::export_file_exists

##### Assertion: `cond::pre::export_valid_input`
- kind: assertion
- operator: is_true
- order: 0
- phase: pre
- qualified_name: cond::pre::export_valid_input

##### TestStep: `step::invoke_export_to_file`
Invoke export_to_file with a valid PlantUML string and writable path
- kind: test_step
- order: 0
- qualified_name: step::invoke_export_to_file



### LLR: `llr_4a268d85`
The Diagram Generator produces identical PlantUML output for identical input graphs and configuration, regardless of invocation order or timing. The render_plantuml operation returns the same result when invoked multiple times with the same diagram model.
- tags: design
#### Test: `vm::deterministic::test_identical_output`
Invoke render_plantuml twice with the same diagram model and configuration. Verify both invocations return identical PlantUML syntax strings.
- kind: test
- method: automated
- qualified_name: vm::deterministic::test_identical_output
- test_name: test_render_plantuml_identical_for_same_model
##### Assertion: `cond::post::deterministic_outputs_match`
- kind: assertion
- operator: ==
- order: 0
- phase: post
- qualified_name: cond::post::deterministic_outputs_match

##### Assertion: `cond::pre::deterministic_valid_model`
- kind: assertion
- operator: >
- order: 0
- phase: pre
- qualified_name: cond::pre::deterministic_valid_model

##### TestStep: `step::invoke_render_plantuml_second`
Second invocation of render_plantuml with the same diagram model
- kind: test_step
- order: 0
- qualified_name: step::invoke_render_plantuml_second

##### TestStep: `step::invoke_render_plantuml_first`
First invocation of render_plantuml with the diagram model
- kind: test_step
- order: 0
- qualified_name: step::invoke_render_plantuml_first



### LLR: `llr_0bf25c87`
The Diagram Generator exposes a set_min_entity_count operation that accepts a positive integer threshold and a diagram model, and returns a filtered diagram model with packages whose entity count is below the threshold removed. The operation rejects non-positive threshold values by signaling an error.
- tags: design
#### Test: `vm::filter::test_rejects_non_positive`
Invoke set_min_entity_count with threshold 0. Verify it signals an error state for invalid threshold and the current threshold remains unchanged.
- kind: test
- method: automated
- qualified_name: vm::filter::test_rejects_non_positive
- test_name: test_set_min_entity_count_rejects_non_positive
##### Assertion: `cond::post::filter_threshold_unchanged`
- kind: assertion
- operator: ==
- order: 0
- phase: post
- qualified_name: cond::post::filter_threshold_unchanged

##### Assertion: `cond::post::filter_error_invalid_threshold`
- kind: assertion
- operator: ==
- order: 0
- phase: post
- qualified_name: cond::post::filter_error_invalid_threshold

##### Assertion: `cond::pre::filter_default_state`
- kind: assertion
- operator: is_true
- order: 0
- phase: pre
- qualified_name: cond::pre::filter_default_state

##### TestStep: `step::invoke_set_min_entity_count_zero`
Invoke set_min_entity_count with threshold 0
- kind: test_step
- order: 0
- qualified_name: step::invoke_set_min_entity_count_zero


#### Test: `vm::filter::test_applies_threshold`
Set the minimum entity count to 3 and invoke apply_filter on a diagram model containing packages with entity counts 1, 3, and 5. Verify the resulting model contains only packages with count >= 3.
- kind: test
- method: automated
- qualified_name: vm::filter::test_applies_threshold
- test_name: test_set_min_entity_count_filters_low_count_packages
##### Assertion: `cond::post::filter_high_count_retained`
- kind: assertion
- operator: is_true
- order: 0
- phase: post
- qualified_name: cond::post::filter_high_count_retained

##### Assertion: `cond::post::filter_low_count_removed`
- kind: assertion
- operator: ==
- order: 0
- phase: post
- qualified_name: cond::post::filter_low_count_removed

##### Assertion: `cond::pre::filter_model_with_varying_counts`
- kind: assertion
- operator: is_true
- order: 0
- phase: pre
- qualified_name: cond::pre::filter_model_with_varying_counts

##### TestStep: `step::invoke_apply_filter`
Invoke apply_filter on the diagram model
- kind: test_step
- order: 0
- qualified_name: step::invoke_apply_filter

##### TestStep: `step::invoke_set_min_entity_count`
Invoke set_min_entity_count with threshold 3
- kind: test_step
- order: 0
- qualified_name: step::invoke_set_min_entity_count



### LLR: `llr_9df31b85`
The Diagram Generator exposes a render_plantuml operation that accepts a diagram model and returns a valid PlantUML component-diagram syntax string. The output uses package notation for modules/namespaces, shows key classes inside each package at medium detail, and renders directed relationship arrows between packages.
- tags: design
#### Test: `vm::rendering::test_invalid_model`
Invoke the render_plantuml operation with an empty diagram model. Verify the operation returns an empty string and no error.
- kind: test
- method: automated
- qualified_name: vm::rendering::test_invalid_model
- test_name: test_render_plantuml_rejects_invalid_model
##### Assertion: `cond::post::render_no_error`
- kind: assertion
- operator: ==
- order: 0
- phase: post
- qualified_name: cond::post::render_no_error

##### Assertion: `cond::post::render_output_is_empty`
- kind: assertion
- operator: ==
- order: 0
- phase: post
- qualified_name: cond::post::render_output_is_empty

##### Assertion: `cond::pre::render_empty_model`
- kind: assertion
- operator: ==
- order: 0
- phase: pre
- qualified_name: cond::pre::render_empty_model

##### TestStep: `step::invoke_render_plantuml_empty`
Invoke render_plantuml with an empty diagram model
- kind: test_step
- order: 0
- qualified_name: step::invoke_render_plantuml_empty


#### Test: `vm::rendering::test_relationship_arrows`
Invoke the render_plantuml operation with a diagram model where packages have directed dependencies. Verify the output contains directed arrow syntax between the package references.
- kind: test
- method: automated
- qualified_name: vm::rendering::test_relationship_arrows
- test_name: test_render_plantuml_relationship_arrows
##### Assertion: `cond::post::render_arrow_direction`
- kind: assertion
- operator: is_true
- order: 0
- phase: post
- qualified_name: cond::post::render_arrow_direction

##### Assertion: `cond::post::render_contains_arrow_syntax`
- kind: assertion
- operator: contains
- order: 0
- phase: post
- qualified_name: cond::post::render_contains_arrow_syntax

##### Assertion: `cond::pre::render_model_with_relationships`
- kind: assertion
- operator: >
- order: 0
- phase: pre
- qualified_name: cond::pre::render_model_with_relationships

##### TestStep: `step::invoke_render_plantuml_rels`
Invoke render_plantuml with a diagram model that has directed relationships
- kind: test_step
- order: 0
- qualified_name: step::invoke_render_plantuml_rels


#### Test: `vm::rendering::test_class_details`
Invoke the render_plantuml operation with a diagram model where a module contains multiple classes. Verify the output includes class names inside the corresponding package section.
- kind: test
- method: automated
- qualified_name: vm::rendering::test_class_details
- test_name: test_render_plantuml_shows_class_details_in_packages
##### Assertion: `cond::post::render_classes_within_package`
- kind: assertion
- operator: is_true
- order: 0
- phase: post
- qualified_name: cond::post::render_classes_within_package

##### Assertion: `cond::post::render_contains_class_names`
- kind: assertion
- operator: contains
- order: 0
- phase: post
- qualified_name: cond::post::render_contains_class_names

##### Assertion: `cond::pre::render_model_with_classes`
- kind: assertion
- operator: >
- order: 0
- phase: pre
- qualified_name: cond::pre::render_model_with_classes

##### TestStep: `step::invoke_render_plantuml_classes`
Invoke render_plantuml with a diagram model that has classes in packages
- kind: test_step
- order: 0
- qualified_name: step::invoke_render_plantuml_classes


#### Test: `vm::rendering::test_package_notation`
Invoke the render_plantuml operation with a diagram model containing multiple modules. Verify the output contains @startuml, package keyword for each module, and @enduml.
- kind: test
- method: automated
- qualified_name: vm::rendering::test_package_notation
- test_name: test_render_plantuml_uses_package_notation
##### Assertion: `cond::post::render_contains_end_enduml`
- kind: assertion
- operator: contains
- order: 0
- phase: post
- qualified_name: cond::post::render_contains_end_enduml

##### Assertion: `cond::post::render_contains_package_keywords`
- kind: assertion
- operator: contains
- order: 0
- phase: post
- qualified_name: cond::post::render_contains_package_keywords

##### Assertion: `cond::post::render_contains_startuml`
- kind: assertion
- operator: contains
- order: 0
- phase: post
- qualified_name: cond::post::render_contains_startuml

##### Assertion: `cond::pre::render_valid_model`
- kind: assertion
- operator: >
- order: 0
- phase: pre
- qualified_name: cond::pre::render_valid_model

##### TestStep: `step::invoke_render_plantuml`
Invoke render_plantuml with a valid diagram model
- kind: test_step
- order: 0
- qualified_name: step::invoke_render_plantuml



### LLR: `llr_1766ea7a`
The Diagram Generator exposes a generate_diagram operation that accepts a project identifier, queries the codegraph Neo4j store for all modules/namespaces and their composition/dependency relationships, and returns a coherent diagram model. The operation signals an error state on database connection failure or empty result.
- tags: design
#### Test: `vm::data_retrieval::test_empty_result`
Invoke the generate_diagram operation with a project identifier whose codegraph has no modules. Verify the error state indicates an empty result.
- kind: test
- method: automated
- qualified_name: vm::data_retrieval::test_empty_result
- test_name: test_generate_diagram_signals_error_on_empty_result
##### Assertion: `cond::post::data_model_is_empty_empty`
- kind: assertion
- operator: ==
- order: 0
- phase: post
- qualified_name: cond::post::data_model_is_empty_empty

##### Assertion: `cond::post::data_error_is_empty_result`
- kind: assertion
- operator: ==
- order: 0
- phase: post
- qualified_name: cond::post::data_error_is_empty_result

##### Assertion: `cond::pre::data_empty_project`
- kind: assertion
- operator: is_true
- order: 0
- phase: pre
- qualified_name: cond::pre::data_empty_project

##### TestStep: `step::invoke_generate_diagram_empty`
Invoke generate_diagram with a project that has no modules
- kind: test_step
- order: 0
- qualified_name: step::invoke_generate_diagram_empty


#### Test: `vm::data_retrieval::test_database_error`
Invoke the generate_diagram operation when the Neo4j store is unreachable. Verify the error state indicates a database connection failure.
- kind: test
- method: automated
- qualified_name: vm::data_retrieval::test_database_error
- test_name: test_generate_diagram_signals_error_on_db_failure
##### Assertion: `cond::post::data_model_is_empty`
- kind: assertion
- operator: ==
- order: 0
- phase: post
- qualified_name: cond::post::data_model_is_empty

##### Assertion: `cond::post::data_error_is_database_error`
- kind: assertion
- operator: ==
- order: 0
- phase: post
- qualified_name: cond::post::data_error_is_database_error

##### Assertion: `cond::pre::data_db_unreachable`
- kind: assertion
- operator: is_true
- order: 0
- phase: pre
- qualified_name: cond::pre::data_db_unreachable

##### TestStep: `step::invoke_generate_diagram_db_error`
Invoke generate_diagram when Neo4j is unreachable
- kind: test_step
- order: 0
- qualified_name: step::invoke_generate_diagram_db_error


#### Test: `vm::data_retrieval::test_successful_query`
Invoke the generate_diagram operation with a valid project identifier whose codegraph has modules and relationships. Verify the returned diagram model contains the expected modules.
- kind: test
- method: automated
- qualified_name: vm::data_retrieval::test_successful_query
- test_name: test_generate_diagram_returns_model_for_valid_project
##### Assertion: `cond::post::data_no_error`
- kind: assertion
- operator: ==
- order: 0
- phase: post
- qualified_name: cond::post::data_no_error

##### Assertion: `cond::post::data_model_has_modules`
- kind: assertion
- operator: >
- order: 0
- phase: post
- qualified_name: cond::post::data_model_has_modules

##### Assertion: `cond::pre::data_valid_project`
- kind: assertion
- operator: is_true
- order: 0
- phase: pre
- qualified_name: cond::pre::data_valid_project

##### TestStep: `step::invoke_generate_diagram`
Invoke generate_diagram with a valid project identifier
- kind: test_step
- order: 0
- qualified_name: step::invoke_generate_diagram




## Attribute: `DiagramGenerator::export_success`
- kind: attribute
- qualified_name: DiagramGenerator::export_success
- tags: scaffold

## Literal: `literal::false`
- kind: literal
- qualified_name: literal::false
- tags: scaffold
- value: false
- value_type: boolean

## Attribute: `DiagramGenerator::error_state`
- kind: attribute
- qualified_name: DiagramGenerator::error_state
- tags: scaffold

## Attribute: `FileSystemError`
- kind: attribute
- qualified_name: FileSystemError
- tags: scaffold

## Attribute: `DiagramGenerator::is_initialized`
- kind: attribute
- qualified_name: DiagramGenerator::is_initialized
- tags: scaffold

## Literal: `literal::true`
- kind: literal
- qualified_name: literal::true
- tags: scaffold
- value: true
- value_type: boolean

## Attribute: `DiagramGenerator::file_content`
- kind: attribute
- qualified_name: DiagramGenerator::file_content
- tags: scaffold

## Attribute: `DiagramGenerator::plantuml_output`
- kind: attribute
- qualified_name: DiagramGenerator::plantuml_output
- tags: scaffold

## Attribute: `DiagramGenerator::file_exists`
- kind: attribute
- qualified_name: DiagramGenerator::file_exists
- tags: scaffold

## Attribute: `DiagramGenerator::first_output`
- kind: attribute
- qualified_name: DiagramGenerator::first_output
- tags: scaffold

## Attribute: `DiagramGenerator::second_output`
- kind: attribute
- qualified_name: DiagramGenerator::second_output
- tags: scaffold

## Attribute: `DiagramGenerator::module_count`
- kind: attribute
- qualified_name: DiagramGenerator::module_count
- tags: scaffold

## Literal: `literal::0`
- kind: literal
- qualified_name: literal::0
- tags: scaffold
- value: 0
- value_type: int

## Attribute: `DiagramGenerator::min_entity_count`
- kind: attribute
- qualified_name: DiagramGenerator::min_entity_count
- tags: scaffold

## Literal: `literal::1`
- kind: literal
- qualified_name: literal::1
- tags: scaffold
- value: 1
- value_type: int

## Attribute: `InvalidThresholdError`
- kind: attribute
- qualified_name: InvalidThresholdError
- tags: scaffold

## Attribute: `DiagramGenerator::diagram_model`
- kind: attribute
- qualified_name: DiagramGenerator::diagram_model
- tags: scaffold

## Attribute: `DiagramGenerator::filtered_package_count`
- kind: attribute
- qualified_name: DiagramGenerator::filtered_package_count
- tags: scaffold

## Literal: `literal::2`
- kind: literal
- qualified_name: literal::2
- tags: scaffold
- value: 2
- value_type: int

## Literal: `None`
- kind: literal
- qualified_name: None
- tags: scaffold
- value: None
- value_type: string

## Literal: `literal::`
- kind: literal
- qualified_name: literal::
- tags: scaffold
- value_type: string

## Literal: `literal::-->`
- kind: literal
- qualified_name: literal::-->
- tags: scaffold
- value: -->
- value_type: string

## Attribute: `DiagramGenerator::relationship_count`
- kind: attribute
- qualified_name: DiagramGenerator::relationship_count
- tags: scaffold

## Literal: `literal::class`
- kind: literal
- qualified_name: literal::class
- tags: scaffold
- value: class
- value_type: string

## Literal: `literal::@enduml`
- kind: literal
- qualified_name: literal::@enduml
- tags: scaffold
- value: @enduml
- value_type: string

## Literal: `literal::package`
- kind: literal
- qualified_name: literal::package
- tags: scaffold
- value: package
- value_type: string

## Literal: `literal::@startuml`
- kind: literal
- qualified_name: literal::@startuml
- tags: scaffold
- value: @startuml
- value_type: string

## Attribute: `EmptyResultError`
- kind: attribute
- qualified_name: EmptyResultError
- tags: scaffold

## Attribute: `DatabaseError`
- kind: attribute
- qualified_name: DatabaseError
- tags: scaffold

## Attribute: `DiagramGenerator::is_db_unreachable`
- kind: attribute
- qualified_name: DiagramGenerator::is_db_unreachable
- tags: scaffold

## Relationships
- `cond::post::export_success_false` → `DiagramGenerator::export_success` **left_operand** (AttributeNode)
- `cond::post::export_success_false` → `literal::false` **right_operand** (LiteralNode)
- `cond::post::export_error_is_file_system` → `DiagramGenerator::error_state` **left_operand** (AttributeNode)
- `cond::post::export_error_is_file_system` → `FileSystemError` **right_operand** (AttributeNode)
- `cond::pre::export_invalid_path` → `DiagramGenerator::is_initialized` **left_operand** (AttributeNode)
- `cond::pre::export_invalid_path` → `literal::true` **right_operand** (LiteralNode)
- `cond::post::export_success_true` → `DiagramGenerator::export_success` **left_operand** (AttributeNode)
- `cond::post::export_success_true` → `literal::true` **right_operand** (LiteralNode)
- `cond::post::export_file_content_matches` → `DiagramGenerator::file_content` **left_operand** (AttributeNode)
- `cond::post::export_file_content_matches` → `DiagramGenerator::plantuml_output` **right_operand** (AttributeNode)
- `cond::post::export_file_exists` → `DiagramGenerator::file_exists` **left_operand** (AttributeNode)
- `cond::post::export_file_exists` → `literal::true` **right_operand** (LiteralNode)
- `cond::pre::export_valid_input` → `DiagramGenerator::is_initialized` **left_operand** (AttributeNode)
- `cond::pre::export_valid_input` → `literal::true` **right_operand** (LiteralNode)
- `cond::post::deterministic_outputs_match` → `DiagramGenerator::first_output` **left_operand** (AttributeNode)
- `cond::post::deterministic_outputs_match` → `DiagramGenerator::second_output` **right_operand** (AttributeNode)
- `cond::pre::deterministic_valid_model` → `DiagramGenerator::module_count` **left_operand** (AttributeNode)
- `cond::pre::deterministic_valid_model` → `literal::0` **right_operand** (LiteralNode)
- `cond::post::filter_threshold_unchanged` → `DiagramGenerator::min_entity_count` **left_operand** (AttributeNode)
- `cond::post::filter_threshold_unchanged` → `literal::1` **right_operand** (LiteralNode)
- `cond::post::filter_error_invalid_threshold` → `DiagramGenerator::error_state` **left_operand** (AttributeNode)
- `cond::post::filter_error_invalid_threshold` → `InvalidThresholdError` **right_operand** (AttributeNode)
- `cond::pre::filter_default_state` → `DiagramGenerator::is_initialized` **left_operand** (AttributeNode)
- `cond::pre::filter_default_state` → `literal::true` **right_operand** (LiteralNode)
- `cond::post::filter_high_count_retained` → `DiagramGenerator::diagram_model` **left_operand** (AttributeNode)
- `cond::post::filter_high_count_retained` → `literal::true` **right_operand** (LiteralNode)
- `cond::post::filter_low_count_removed` → `DiagramGenerator::filtered_package_count` **left_operand** (AttributeNode)
- `cond::post::filter_low_count_removed` → `literal::2` **right_operand** (LiteralNode)
- `cond::pre::filter_model_with_varying_counts` → `DiagramGenerator::is_initialized` **left_operand** (AttributeNode)
- `cond::pre::filter_model_with_varying_counts` → `literal::true` **right_operand** (LiteralNode)
- `cond::post::render_no_error` → `DiagramGenerator::error_state` **left_operand** (AttributeNode)
- `cond::post::render_no_error` → `None` **right_operand** (LiteralNode)
- `cond::post::render_output_is_empty` → `DiagramGenerator::plantuml_output` **left_operand** (AttributeNode)
- `cond::post::render_output_is_empty` → `literal::` **right_operand** (LiteralNode)
- `cond::pre::render_empty_model` → `DiagramGenerator::module_count` **left_operand** (AttributeNode)
- `cond::pre::render_empty_model` → `literal::0` **right_operand** (LiteralNode)
- `cond::post::render_arrow_direction` → `DiagramGenerator::plantuml_output` **left_operand** (AttributeNode)
- `cond::post::render_arrow_direction` → `literal::true` **right_operand** (LiteralNode)
- `cond::post::render_contains_arrow_syntax` → `DiagramGenerator::plantuml_output` **left_operand** (AttributeNode)
- `cond::post::render_contains_arrow_syntax` → `literal::-->` **right_operand** (LiteralNode)
- `cond::pre::render_model_with_relationships` → `DiagramGenerator::relationship_count` **left_operand** (AttributeNode)
- `cond::pre::render_model_with_relationships` → `literal::0` **right_operand** (LiteralNode)
- `cond::post::render_classes_within_package` → `DiagramGenerator::plantuml_output` **left_operand** (AttributeNode)
- `cond::post::render_classes_within_package` → `literal::true` **right_operand** (LiteralNode)
- `cond::post::render_contains_class_names` → `DiagramGenerator::plantuml_output` **left_operand** (AttributeNode)
- `cond::post::render_contains_class_names` → `literal::class` **right_operand** (LiteralNode)
- `cond::pre::render_model_with_classes` → `DiagramGenerator::module_count` **left_operand** (AttributeNode)
- `cond::pre::render_model_with_classes` → `literal::0` **right_operand** (LiteralNode)
- `cond::post::render_contains_end_enduml` → `DiagramGenerator::plantuml_output` **left_operand** (AttributeNode)
- `cond::post::render_contains_end_enduml` → `literal::@enduml` **right_operand** (LiteralNode)
- `cond::post::render_contains_package_keywords` → `DiagramGenerator::plantuml_output` **left_operand** (AttributeNode)
- `cond::post::render_contains_package_keywords` → `literal::package` **right_operand** (LiteralNode)
- `cond::post::render_contains_startuml` → `DiagramGenerator::plantuml_output` **left_operand** (AttributeNode)
- `cond::post::render_contains_startuml` → `literal::@startuml` **right_operand** (LiteralNode)
- `cond::pre::render_valid_model` → `DiagramGenerator::module_count` **left_operand** (AttributeNode)
- `cond::pre::render_valid_model` → `literal::0` **right_operand** (LiteralNode)
- `cond::post::data_model_is_empty_empty` → `DiagramGenerator::module_count` **left_operand** (AttributeNode)
- `cond::post::data_model_is_empty_empty` → `literal::0` **right_operand** (LiteralNode)
- `cond::post::data_error_is_empty_result` → `DiagramGenerator::error_state` **left_operand** (AttributeNode)
- `cond::post::data_error_is_empty_result` → `EmptyResultError` **right_operand** (AttributeNode)
- `cond::pre::data_empty_project` → `DiagramGenerator::is_initialized` **left_operand** (AttributeNode)
- `cond::pre::data_empty_project` → `literal::true` **right_operand** (LiteralNode)
- `cond::post::data_model_is_empty` → `DiagramGenerator::module_count` **left_operand** (AttributeNode)
- `cond::post::data_model_is_empty` → `literal::0` **right_operand** (LiteralNode)
- `cond::post::data_error_is_database_error` → `DiagramGenerator::error_state` **left_operand** (AttributeNode)
- `cond::post::data_error_is_database_error` → `DatabaseError` **right_operand** (AttributeNode)
- `cond::pre::data_db_unreachable` → `DiagramGenerator::is_db_unreachable` **left_operand** (AttributeNode)
- `cond::pre::data_db_unreachable` → `literal::true` **right_operand** (LiteralNode)
- `cond::post::data_no_error` → `DiagramGenerator::error_state` **left_operand** (AttributeNode)
- `cond::post::data_no_error` → `None` **right_operand** (LiteralNode)
- `cond::post::data_model_has_modules` → `DiagramGenerator::module_count` **left_operand** (AttributeNode)
- `cond::post::data_model_has_modules` → `literal::0` **right_operand** (LiteralNode)
- `cond::pre::data_valid_project` → `DiagramGenerator::is_initialized` **left_operand** (AttributeNode)
- `cond::pre::data_valid_project` → `literal::true` **right_operand** (LiteralNode)
