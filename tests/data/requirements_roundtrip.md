# codegraph: design

## HLR: `Diagram Generator`
The Diagram Generator shall produce a unified PlantUML diagram from a codegraph project.
- qualified_name: Diagram Generator
- tags: design
### LLR: `DG-LLR-001`
The generate operation accepts a project_id, queries Neo4j, and returns a PlantUML string. On connection failure it signals Neo4jConnectionError.
- qualified_name: DG-LLR-001
- tags: design
#### Test: `vm::generate::test_valid`
Invoke generate with a valid project_id and verify the returned string is a non-empty PlantUML diagram.
- kind: test
- method: automated
- qualified_name: vm::generate::test_valid
- tags: design
- test_name: test_generate_returns_diagram_for_valid_project
##### Assertion: `cond::generate::pre::db_reachable`
- kind: assertion
- operator: is_true
- order: 0
- phase: pre
- qualified_name: cond::generate::pre::db_reachable
- tags: design

##### Assertion: `cond::generate::post::non_empty`
- kind: assertion
- operator: is_true
- order: 0
- phase: post
- qualified_name: cond::generate::post::non_empty
- tags: design

##### Assertion: `cond::generate::post::has_startuml`
- kind: assertion
- operator: contains
- order: 0
- phase: post
- qualified_name: cond::generate::post::has_startuml
- tags: design

##### TestStep: `step::generate::invoke`
Invoke generate with project_id=test-project and default config.
- kind: test_step
- order: 0
- qualified_name: step::generate::invoke
- tags: design



### LLR: `DG-LLR-002`
The generator produces byte-identical PlantUML output for identical input graph data and identical configuration.
- qualified_name: DG-LLR-002
- tags: design
#### Test: `vm::det::test_identical`
Invoke generate twice with the same project_id and config, then verify the two outputs are byte-identical.
- kind: test
- method: automated
- qualified_name: vm::det::test_identical
- tags: design
- test_name: test_identical_input_produces_identical_output
##### Assertion: `cond::det::pre::stable_data`
- kind: assertion
- operator: is_true
- order: 0
- phase: pre
- qualified_name: cond::det::pre::stable_data
- tags: design

##### Assertion: `cond::det::post::outputs_match`
- kind: assertion
- operator: ==
- order: 0
- phase: post
- qualified_name: cond::det::post::outputs_match
- tags: design

##### TestStep: `step::det::invoke_first`
First invocation of generate with project_id=test-project.
- kind: test_step
- order: 0
- qualified_name: step::det::invoke_first
- tags: design

##### TestStep: `step::det::invoke_second`
Second invocation of generate with the same project_id and config.
- kind: test_step
- order: 0
- qualified_name: step::det::invoke_second
- tags: design



### LLR: `DG-LLR-003`
When output_path is provided, the generator writes the PlantUML content to a .puml file and returns the resolved path. On write failure it signals FileWriteError.
- qualified_name: DG-LLR-003
- tags: design
#### Test: `vm::export::test_writes_file`
Invoke generate with output_path set to a writable directory and verify a .puml file is created.
- kind: test
- method: automated
- qualified_name: vm::export::test_writes_file
- tags: design
- test_name: test_export_writes_puml_file
##### Assertion: `cond::export::pre::dir_writable`
- kind: assertion
- operator: is_true
- order: 0
- phase: pre
- qualified_name: cond::export::pre::dir_writable
- tags: design

##### Assertion: `cond::export::post::file_exists`
- kind: assertion
- operator: is_true
- order: 0
- phase: post
- qualified_name: cond::export::post::file_exists
- tags: design

##### Assertion: `cond::export::post::returns_path`
- kind: assertion
- operator: is_true
- order: 0
- phase: post
- qualified_name: cond::export::post::returns_path
- tags: design

##### TestStep: `step::export::invoke`
Invoke generate with project_id=test-project and config={output_path: /tmp/diagram}.
- kind: test_step
- order: 0
- qualified_name: step::export::invoke
- tags: design




## Attribute: `Generator::db_reachable`
- kind: attribute
- qualified_name: Generator::db_reachable
- tags: design

## Attribute: `Generator::plantuml_output`
- kind: attribute
- qualified_name: Generator::plantuml_output
- tags: design

## Attribute: `Generator::error_state`
- kind: attribute
- qualified_name: Generator::error_state
- tags: design

## Attribute: `Generator::generate`
- kind: attribute
- qualified_name: Generator::generate
- tags: design

## Attribute: `Generator::first_output`
- kind: attribute
- qualified_name: Generator::first_output
- tags: design

## Attribute: `Generator::second_output`
- kind: attribute
- qualified_name: Generator::second_output
- tags: design

## Attribute: `Generator::output_path`
- kind: attribute
- qualified_name: Generator::output_path
- tags: design

## Attribute: `Generator::file_exists`
- kind: attribute
- qualified_name: Generator::file_exists
- tags: design

## Attribute: `Generator::returned_path`
- kind: attribute
- qualified_name: Generator::returned_path
- tags: design

## Attribute: `NoError`
- kind: attribute
- qualified_name: NoError
- tags: design

## Attribute: `Neo4jConnectionError`
- kind: attribute
- qualified_name: Neo4jConnectionError
- tags: design

## Attribute: `FileWriteError`
- kind: attribute
- qualified_name: FileWriteError
- tags: design

## Literal: `literal::true`
- kind: literal
- qualified_name: literal::true
- tags: design
- value: true

## Literal: `literal::@startuml`
- kind: literal
- qualified_name: literal::@startuml
- tags: design
- value: @startuml

## Literal: `literal::non_empty`
- kind: literal
- qualified_name: literal::non_empty
- tags: design
- value: non_empty

## Relationships
- `cond::generate::pre::db_reachable` → `Generator::db_reachable` **left_operand** (AttributeNode)
- `cond::generate::pre::db_reachable` → `literal::true` **right_operand** (LiteralNode)
- `cond::generate::post::non_empty` → `Generator::plantuml_output` **left_operand** (AttributeNode)
- `cond::generate::post::non_empty` → `literal::non_empty` **right_operand** (LiteralNode)
- `cond::generate::post::has_startuml` → `Generator::plantuml_output` **left_operand** (AttributeNode)
- `cond::generate::post::has_startuml` → `literal::@startuml` **right_operand** (LiteralNode)
- `step::generate::invoke` → `Generator::generate` **callee** (AttributeNode)
- `cond::det::pre::stable_data` → `Generator::db_reachable` **left_operand** (AttributeNode)
- `cond::det::pre::stable_data` → `literal::true` **right_operand** (LiteralNode)
- `cond::det::post::outputs_match` → `Generator::first_output` **left_operand** (AttributeNode)
- `cond::det::post::outputs_match` → `Generator::second_output` **right_operand** (AttributeNode)
- `step::det::invoke_first` → `Generator::generate` **callee** (AttributeNode)
- `step::det::invoke_second` → `Generator::generate` **callee** (AttributeNode)
- `cond::export::pre::dir_writable` → `Generator::output_path` **left_operand** (AttributeNode)
- `cond::export::pre::dir_writable` → `literal::true` **right_operand** (LiteralNode)
- `cond::export::post::file_exists` → `Generator::file_exists` **left_operand** (AttributeNode)
- `cond::export::post::file_exists` → `literal::true` **right_operand** (LiteralNode)
- `cond::export::post::returns_path` → `Generator::returned_path` **left_operand** (AttributeNode)
- `cond::export::post::returns_path` → `literal::non_empty` **right_operand** (LiteralNode)
- `step::export::invoke` → `Generator::generate` **callee** (AttributeNode)
