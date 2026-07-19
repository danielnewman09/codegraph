# codegraph: requirements

## HLR: `Database Migration Manager`
The Database Migration Manager shall provide a schema versioning system for SQLite databases using the cpp-sqlite library. It shall track applied migrations, apply pending migrations in version order, detect schema drift, and roll back migrations when requested. The manager shall integrate with the existing cpp_sqlite::`Database` and cpp_sqlite::`DataAccessObject<T>` classes without modifying them. Migrations shall be defined by the user as subclasses of a Migration class and registered with the manager. The manager shall provide a verify function that checks whether the current database schema matches the expected state from all applied migrations.
- qualified_name: Database Migration Manager
- tags: requirements
### LLR: `llr_migration_registration`
The Migration Manager shall expose a `register_migration` method that accepts a `Migration` subclass instance and stores it. Registered migrations shall be sorted by their `version` value (ascending). The manager shall reject duplicate version numbers by signaling an error. Registration shall be idempotent — registering the same migration twice shall be a no-op.
- tags: requirements
#### Test: `vm::migration_registration::test_duplicate_version_rejected`
Register two migrations with the same version number. Verify the second registration returns an error result indicating a duplicate version error. Verify the original migration remains registered.
- kind: test
- method: automated
- qualified_name: vm::migration_registration::test_duplicate_version_rejected
- test_name: test_register_migration_rejects_duplicate_version
##### Assertion: `cond::post::reg_dup_error_is_duplicate`
- kind: assertion
- operator: ==
- order: 0
- phase: post
- qualified_name: cond::post::reg_dup_error_is_duplicate

##### Assertion: `cond::post::reg_dup_original_retained`
- kind: assertion
- operator: is_true
- order: 0
- phase: post
- qualified_name: cond::post::reg_dup_original_retained

##### Assertion: `cond::pre::reg_dup_first_migration_registered`
- kind: assertion
- operator: is_true
- order: 0
- phase: pre
- qualified_name: cond::pre::reg_dup_first_migration_registered

##### TestStep: `step::reg_dup_invoke_register_second`
Invoke register_migration with a second migration having the same version as the first
- kind: test_step
- order: 0
- qualified_name: step::reg_dup_invoke_register_second

##### TestStep: `step::reg_dup_invoke_register_first`
Invoke register_migration with a migration at version 1
- kind: test_step
- order: 0
- qualified_name: step::reg_dup_invoke_register_first


#### Test: `vm::migration_registration::test_sorted_by_version`
Register migrations at versions 3, 1, and 2. Verify the manager stores them in ascending version order [1, 2, 3] regardless of registration order.
- kind: test
- method: automated
- qualified_name: vm::migration_registration::test_sorted_by_version
- test_name: test_register_migration_sorts_by_version
##### Assertion: `cond::post::reg_sort_order_correct`
- kind: assertion
- operator: ==
- order: 0
- phase: post
- qualified_name: cond::post::reg_sort_order_correct

##### Assertion: `cond::pre::reg_sort_no_migrations`
- kind: assertion
- operator: is_true
- order: 0
- phase: pre
- qualified_name: cond::pre::reg_sort_no_migrations

##### TestStep: `step::reg_sort_register_three`
Register migrations at versions 3, 1, 2
- kind: test_step
- order: 0
- qualified_name: step::reg_sort_register_three



### LLR: `llr_migration_apply`
The Migration Manager shall provide an `apply` method that executes all unapplied migrations in version order against a cpp_sqlite::`Database` instance. Each migration's `up` method shall be invoked with a cpp_sqlite::`Transaction` reference. The manager shall record each successfully applied migration in a `SchemaVersion` class (backed by a `schema_versions` table) that stores (version: INTEGER, applied_at: TEXT, checksum: TEXT). If any migration's `up` method throws, the manager shall roll back the current migration's changes via the active `Transaction` (without affecting previously applied migrations). The manager shall not re-apply migrations already recorded in `schema_versions`.
- tags: requirements
#### Test: `vm::migration_apply::test_applies_only_pending`
Register three migrations at versions 1, 2, 3. Pre-populate `schema_versions` with version 1 already applied. Invoke `apply`. Verify only versions 2 and 3 are executed. Verify `schema_versions` now contains versions 2 and 3. Verify the total number of applied migrations is 3.
- kind: test
- method: automated
- qualified_name: vm::migration_apply::test_applies_only_pending
- test_name: test_apply_migration_applies_only_pending
##### Assertion: `cond::post::apply_pending_count_correct`
- kind: assertion
- operator: ==
- order: 0
- phase: post
- qualified_name: cond::post::apply_pending_count_correct

##### Assertion: `cond::post::apply_pending_version3_recorded`
- kind: assertion
- operator: is_true
- order: 0
- phase: post
- qualified_name: cond::post::apply_pending_version3_recorded

##### Assertion: `cond::post::apply_pending_version2_recorded`
- kind: assertion
- operator: is_true
- order: 0
- phase: post
- qualified_name: cond::post::apply_pending_version2_recorded

##### Assertion: `cond::post::apply_pending_version1_not_reapplied`
- kind: assertion
- operator: is_false
- order: 0
- phase: post
- qualified_name: cond::post::apply_pending_version1_not_reapplied

##### Assertion: `cond::pre::apply_pending_version1_preexists`
- kind: assertion
- operator: is_true
- order: 0
- phase: pre
- qualified_name: cond::pre::apply_pending_version1_preexists

##### TestStep: `step::apply_pending_invoke_apply`
Invoke apply on the migration manager
- kind: test_step
- order: 0
- qualified_name: step::apply_pending_invoke_apply

##### TestStep: `step::apply_pending_prepopulate_schema_versions`
Pre-populate schema_versions table with version 1 as applied
- kind: test_step
- order: 0
- qualified_name: step::apply_pending_prepopulate_schema_versions

##### TestStep: `step::apply_pending_register_migrations`
Register migrations at versions 1, 2, 3
- kind: test_step
- order: 0
- qualified_name: step::apply_pending_register_migrations


#### Test: `vm::migration_apply::test_up_failure_rolls_back`
Register two migrations at version 1 (succeeds) and version 2 (whose `up` method throws a `std::runtime_error`). Invoke `apply`. Verify version 1 is marked as applied in `schema_versions`. Verify version 2 is NOT marked as applied. Verify the apply operation signals an error indicating the migration failure. Verify the database still contains any schema objects created by version 1.
- kind: test
- method: automated
- qualified_name: vm::migration_apply::test_up_failure_rolls_back
- test_name: test_apply_migration_rolls_back_on_up_failure
##### Assertion: `cond::post::apply_fail_earlier_schema_preserved`
- kind: assertion
- operator: is_true
- order: 0
- phase: post
- qualified_name: cond::post::apply_fail_earlier_schema_preserved

##### Assertion: `cond::post::apply_fail_error_signaled`
- kind: assertion
- operator: is_true
- order: 0
- phase: post
- qualified_name: cond::post::apply_fail_error_signaled

##### Assertion: `cond::post::apply_fail_version2_not_recorded`
- kind: assertion
- operator: is_false
- order: 0
- phase: post
- qualified_name: cond::post::apply_fail_version2_not_recorded

##### Assertion: `cond::post::apply_fail_version1_recorded`
- kind: assertion
- operator: is_true
- order: 0
- phase: post
- qualified_name: cond::post::apply_fail_version1_recorded

##### Assertion: `cond::pre::apply_fail_migrations_registered`
- kind: assertion
- operator: is_true
- order: 0
- phase: pre
- qualified_name: cond::pre::apply_fail_migrations_registered

##### TestStep: `step::apply_fail_invoke_apply`
Invoke apply on the migration manager
- kind: test_step
- order: 0
- qualified_name: step::apply_fail_invoke_apply

##### TestStep: `step::apply_fail_register_migrations`
Register a succeeding migration (v1) and a failing migration (v2)
- kind: test_step
- order: 0
- qualified_name: step::apply_fail_register_migrations


#### Test: `vm::migration_apply::test_apply_in_order`
Register three migrations at versions 1, 2, 3 where each `up` method records its execution in a shared vector. Invoke `apply`. Verify the execution order recorded is [1, 2, 3].
- kind: test
- method: automated
- qualified_name: vm::migration_apply::test_apply_in_order
- test_name: test_apply_migration_executes_in_version_order
##### Assertion: `cond::post::apply_order_is_ascending`
- kind: assertion
- operator: ==
- order: 0
- phase: post
- qualified_name: cond::post::apply_order_is_ascending

##### Assertion: `cond::pre::apply_order_migrations_registered`
- kind: assertion
- operator: is_true
- order: 0
- phase: pre
- qualified_name: cond::pre::apply_order_migrations_registered

##### TestStep: `step::apply_order_invoke_apply`
Invoke apply on the migration manager
- kind: test_step
- order: 0
- qualified_name: step::apply_order_invoke_apply

##### TestStep: `step::apply_order_register_migrations`
Register migrations at versions 1, 2, 3
- kind: test_step
- order: 0
- qualified_name: step::apply_order_register_migrations



### LLR: `llr_schema_verification`
The Migration Manager shall provide a `verify` method that checks whether the current database schema matches the expected state from all applied migrations. The verify method shall compute a checksum of the current schema and compare it against the stored checksums in `schema_versions`. It shall return a list of mismatches — versions where the stored checksum does not match the live schema checksum. For each mismatch, it shall report the version number and the kind of mismatch (missing table, extra table, column difference). An empty mismatch list indicates the schema is consistent with recorded migrations.
- tags: requirements
#### Test: `vm::schema_verify::test_mismatch_detected`
Register and apply a migration at version 1 that creates a table "users". Then manually alter the database to add an unexpected table "extra". Invoke verify. Verify the result contains one mismatch entry. Verify the mismatch reports version 1 and the kind as an unexpected table.
- kind: test
- method: automated
- qualified_name: vm::schema_verify::test_mismatch_detected
- test_name: test_verify_detects_schema_mismatch
##### Assertion: `cond::post::verify_mismatch_kind_extra_table`
- kind: assertion
- operator: ==
- order: 0
- phase: post
- qualified_name: cond::post::verify_mismatch_kind_extra_table

##### Assertion: `cond::post::verify_mismatch_version_is_1`
- kind: assertion
- operator: ==
- order: 0
- phase: post
- qualified_name: cond::post::verify_mismatch_version_is_1

##### Assertion: `cond::post::verify_mismatch_count_is_1`
- kind: assertion
- operator: ==
- order: 0
- phase: post
- qualified_name: cond::post::verify_mismatch_count_is_1

##### Assertion: `cond::pre::verify_migration_applied`
- kind: assertion
- operator: is_true
- order: 0
- phase: pre
- qualified_name: cond::pre::verify_migration_applied

##### TestStep: `step::verify_invoke_verify`
Invoke verify on the migration manager
- kind: test_step
- order: 0
- qualified_name: step::verify_invoke_verify

##### TestStep: `step::verify_add_unexpected_table`
Manually add an unexpected table "extra" to the database
- kind: test_step
- order: 0
- qualified_name: step::verify_add_unexpected_table

##### TestStep: `step::verify_register_and_apply_migration`
Register and apply a migration at version 1 that creates a table "users"
- kind: test_step
- order: 0
- qualified_name: step::verify_register_and_apply_migration


#### Test: `vm::schema_verify::test_consistent_schema`
Register and apply a migration at version 1 that creates a table "users". Do not modify the schema afterward. Invoke verify. Verify the result contains zero mismatches.
- kind: test
- method: automated
- qualified_name: vm::schema_verify::test_consistent_schema
- test_name: test_verify_reports_consistent_schema
##### Assertion: `cond::post::verify_consistent_no_mismatches`
- kind: assertion
- operator: ==
- order: 0
- phase: post
- qualified_name: cond::post::verify_consistent_no_mismatches

##### Assertion: `cond::pre::verify_consistent_migration_applied`
- kind: assertion
- operator: is_true
- order: 0
- phase: pre
- qualified_name: cond::pre::verify_consistent_migration_applied

##### TestStep: `step::verify_consistent_invoke_verify`
Invoke verify on the migration manager
- kind: test_step
- order: 0
- qualified_name: step::verify_consistent_invoke_verify

##### TestStep: `step::verify_consistent_apply_migration`
Register and apply a migration at version 1 that creates table "users"
- kind: test_step
- order: 0
- qualified_name: step::verify_consistent_apply_migration



### LLR: `llr_migration_rollback`
The Migration Manager shall provide a `rollback` method that accepts a target version and rolls back all migrations above that version in descending order. Each migration's `down` method shall be invoked with a cpp_sqlite::`Transaction` reference. Rollback shall update `schema_versions` to remove rows for rolled-back migrations. If any `down` method throws, the manager shall abort the rollback and leave the database in its partially-rolled-back state, signaling an error. Rollback to a version lower than any registered migration shall remove all applied migrations.
- tags: requirements
#### Test: `vm::rollback::test_rollback_to_version`
Apply migrations at versions 1, 2, 3. Invoke `rollback(2)`. Verify version 3's `down` method was called. Verify only versions 1 and 2 remain in `schema_versions`. Verify version 3 is not in `schema_versions`.
- kind: test
- method: automated
- qualified_name: vm::rollback::test_rollback_to_version
- test_name: test_rollback_rolls_back_to_target_version
##### Assertion: `cond::post::rollback_version3_not_in_table`
- kind: assertion
- operator: is_false
- order: 0
- phase: post
- qualified_name: cond::post::rollback_version3_not_in_table

##### Assertion: `cond::post::rollback_versions_1_and_2_remain`
- kind: assertion
- operator: is_true
- order: 0
- phase: post
- qualified_name: cond::post::rollback_versions_1_and_2_remain

##### Assertion: `cond::post::rollback_down_called`
- kind: assertion
- operator: is_true
- order: 0
- phase: post
- qualified_name: cond::post::rollback_down_called

##### Assertion: `cond::pre::rollback_three_migrations_applied`
- kind: assertion
- operator: is_true
- order: 0
- phase: pre
- qualified_name: cond::pre::rollback_three_migrations_applied

##### TestStep: `step::rollback_invoke_rollback`
Invoke rollback(2) on the migration manager
- kind: test_step
- order: 0
- qualified_name: step::rollback_invoke_rollback

##### TestStep: `step::rollback_apply_three_migrations`
Register and apply migrations at versions 1, 2, 3
- kind: test_step
- order: 0
- qualified_name: step::rollback_apply_three_migrations


#### Test: `vm::rollback::test_down_failure_aborts`
Apply migrations at versions 1 and 2 where version 2's `down` method throws. Invoke `rollback(1)`. Verify the operation signals an error. Verify version 2 remains in `schema_versions`. Verify version 1 still exists in `schema_versions`.
- kind: test
- method: automated
- qualified_name: vm::rollback::test_down_failure_aborts
- test_name: test_rollback_aborts_on_down_failure
##### Assertion: `cond::post::rollback_fail_version1_preserved`
- kind: assertion
- operator: is_true
- order: 0
- phase: post
- qualified_name: cond::post::rollback_fail_version1_preserved

##### Assertion: `cond::post::rollback_fail_version2_still_exists`
- kind: assertion
- operator: is_true
- order: 0
- phase: post
- qualified_name: cond::post::rollback_fail_version2_still_exists

##### Assertion: `cond::post::rollback_fail_error_signaled`
- kind: assertion
- operator: is_true
- order: 0
- phase: post
- qualified_name: cond::post::rollback_fail_error_signaled

##### Assertion: `cond::pre::rollback_fail_two_applied`
- kind: assertion
- operator: is_true
- order: 0
- phase: pre
- qualified_name: cond::pre::rollback_fail_two_applied

##### TestStep: `step::rollback_fail_invoke_rollback`
Invoke rollback(1) on the migration manager
- kind: test_step
- order: 0
- qualified_name: step::rollback_fail_invoke_rollback

##### TestStep: `step::rollback_fail_apply_migrations`
Register and apply migrations v1 (succeeds), v2 (fails on down)
- kind: test_step
- order: 0
- qualified_name: step::rollback_fail_apply_migrations



## Attribute: `MigrationManager::error_state`
- kind: attribute
- qualified_name: MigrationManager::error_state
- tags: scaffold

## Attribute: `DuplicateVersionError`
- kind: attribute
- qualified_name: DuplicateVersionError
- tags: scaffold

## Attribute: `MigrationManager::is_initialized`
- kind: attribute
- qualified_name: MigrationManager::is_initialized
- tags: scaffold

## Literal: `literal::true`
- kind: literal
- qualified_name: literal::true
- tags: scaffold
- value: true
- value_type: boolean

## Attribute: `MigrationManager::registered_versions`
- kind: attribute
- qualified_name: MigrationManager::registered_versions
- tags: scaffold

## Literal: `literal::1`
- kind: literal
- qualified_name: literal::1
- tags: scaffold
- value: 1
- value_type: int

## Literal: `literal::2`
- kind: literal
- qualified_name: literal::2
- tags: scaffold
- value: 2
- value_type: int

## Literal: `literal::3`
- kind: literal
- qualified_name: literal::3
- tags: scaffold
- value: 3
- value_type: int

## Attribute: `MigrationManager::version1_reapplied`
- kind: attribute
- qualified_name: MigrationManager::version1_reapplied
- tags: scaffold

## Literal: `literal::false`
- kind: literal
- qualified_name: literal::false
- tags: scaffold
- value: false
- value_type: boolean

## Attribute: `MigrationManager::version2_recorded`
- kind: attribute
- qualified_name: MigrationManager::version2_recorded
- tags: scaffold

## Attribute: `MigrationManager::version3_recorded`
- kind: attribute
- qualified_name: MigrationManager::version3_recorded
- tags: scaffold

## Literal: `literal::0`
- kind: literal
- qualified_name: literal::0
- tags: scaffold
- value: 0
- value_type: int

## Attribute: `MigrationManager::execution_order`
- kind: attribute
- qualified_name: MigrationManager::execution_order
- tags: scaffold

## Attribute: `MigrationManager::version1_recorded_on_fail`
- kind: attribute
- qualified_name: MigrationManager::version1_recorded_on_fail
- tags: scaffold

## Attribute: `MigrationManager::version2_not_recorded_on_fail`
- kind: attribute
- qualified_name: MigrationManager::version2_not_recorded_on_fail
- tags: scaffold

## Attribute: `MigrationManager::error_on_fail`
- kind: attribute
- qualified_name: MigrationManager::error_on_fail
- tags: scaffold

## Attribute: `MigrationManager::version1_schema_preserved`
- kind: attribute
- qualified_name: MigrationManager::version1_schema_preserved
- tags: scaffold

## Attribute: `MigrationManager::mismatch_count`
- kind: attribute
- qualified_name: MigrationManager::mismatch_count
- tags: scaffold

## Attribute: `MigrationManager::mismatch_version`
- kind: attribute
- qualified_name: MigrationManager::mismatch_version
- tags: scaffold

## Attribute: `MigrationManager::mismatch_kind`
- kind: attribute
- qualified_name: MigrationManager::mismatch_kind
- tags: scaffold

## Attribute: `UnexpectedTable`
- kind: attribute
- qualified_name: UnexpectedTable
- tags: scaffold

## Attribute: `MigrationManager::migration_applied`
- kind: attribute
- qualified_name: MigrationManager::migration_applied
- tags: scaffold

## Attribute: `MigrationManager::version3_not_recorded`
- kind: attribute
- qualified_name: MigrationManager::version3_not_recorded
- tags: scaffold

## Attribute: `MigrationManager::versions_1_2_remain`
- kind: attribute
- qualified_name: MigrationManager::versions_1_2_remain
- tags: scaffold

## Attribute: `MigrationManager::down_called`
- kind: attribute
- qualified_name: MigrationManager::down_called
- tags: scaffold

## Attribute: `MigrationManager::error_on_rollback_fail`
- kind: attribute
- qualified_name: MigrationManager::error_on_rollback_fail
- tags: scaffold

## Attribute: `MigrationManager::version2_still_exists_on_fail`
- kind: attribute
- qualified_name: MigrationManager::version2_still_exists_on_fail
- tags: scaffold

## Attribute: `MigrationManager::version1_preserved_on_fail`
- kind: attribute
- qualified_name: MigrationManager::version1_preserved_on_fail
- tags: scaffold

## Relationships
- `cond::post::reg_dup_error_is_duplicate` → `MigrationManager::error_state` **left_operand** (AttributeNode)
- `cond::post::reg_dup_error_is_duplicate` → `DuplicateVersionError` **right_operand** (AttributeNode)
- `cond::post::reg_dup_original_retained` → `MigrationManager::registered_versions` **left_operand** (AttributeNode)
- `cond::post::reg_dup_original_retained` → `literal::true` **right_operand** (LiteralNode)
- `cond::pre::reg_dup_first_migration_registered` → `MigrationManager::is_initialized` **left_operand** (AttributeNode)
- `cond::pre::reg_dup_first_migration_registered` → `literal::true` **right_operand** (LiteralNode)
- `cond::post::reg_sort_order_correct` → `MigrationManager::registered_versions` **left_operand** (AttributeNode)
- `cond::post::reg_sort_order_correct` → `literal::1` **right_operand** (LiteralNode)
- `cond::pre::reg_sort_no_migrations` → `MigrationManager::is_initialized` **left_operand** (AttributeNode)
- `cond::pre::reg_sort_no_migrations` → `literal::true` **right_operand** (LiteralNode)
- `cond::post::apply_pending_count_correct` → `MigrationManager::registered_versions` **left_operand** (AttributeNode)
- `cond::post::apply_pending_count_correct` → `literal::3` **right_operand** (LiteralNode)
- `cond::post::apply_pending_version3_recorded` → `MigrationManager::version3_recorded` **left_operand** (AttributeNode)
- `cond::post::apply_pending_version3_recorded` → `literal::true` **right_operand** (LiteralNode)
- `cond::post::apply_pending_version2_recorded` → `MigrationManager::version2_recorded` **left_operand** (AttributeNode)
- `cond::post::apply_pending_version2_recorded` → `literal::true` **right_operand** (LiteralNode)
- `cond::post::apply_pending_version1_not_reapplied` → `MigrationManager::version1_reapplied` **left_operand** (AttributeNode)
- `cond::post::apply_pending_version1_not_reapplied` → `literal::false` **right_operand** (LiteralNode)
- `cond::pre::apply_pending_version1_preexists` → `MigrationManager::is_initialized` **left_operand** (AttributeNode)
- `cond::pre::apply_pending_version1_preexists` → `literal::true` **right_operand** (LiteralNode)
- `cond::post::apply_order_is_ascending` → `MigrationManager::execution_order` **left_operand** (AttributeNode)
- `cond::post::apply_order_is_ascending` → `literal::1` **right_operand** (LiteralNode)
- `cond::pre::apply_order_migrations_registered` → `MigrationManager::is_initialized` **left_operand** (AttributeNode)
- `cond::pre::apply_order_migrations_registered` → `literal::true` **right_operand** (LiteralNode)
- `cond::post::apply_fail_version1_recorded` → `MigrationManager::version1_recorded_on_fail` **left_operand** (AttributeNode)
- `cond::post::apply_fail_version1_recorded` → `literal::true` **right_operand** (LiteralNode)
- `cond::post::apply_fail_version2_not_recorded` → `MigrationManager::version2_not_recorded_on_fail` **left_operand** (AttributeNode)
- `cond::post::apply_fail_version2_not_recorded` → `literal::true` **right_operand** (LiteralNode)
- `cond::post::apply_fail_error_signaled` → `MigrationManager::error_on_fail` **left_operand** (AttributeNode)
- `cond::post::apply_fail_error_signaled` → `literal::true` **right_operand** (LiteralNode)
- `cond::post::apply_fail_earlier_schema_preserved` → `MigrationManager::version1_schema_preserved` **left_operand** (AttributeNode)
- `cond::post::apply_fail_earlier_schema_preserved` → `literal::true` **right_operand** (LiteralNode)
- `cond::pre::apply_fail_migrations_registered` → `MigrationManager::is_initialized` **left_operand** (AttributeNode)
- `cond::pre::apply_fail_migrations_registered` → `literal::true` **right_operand** (LiteralNode)
- `cond::post::verify_mismatch_count_is_1` → `MigrationManager::mismatch_count` **left_operand** (AttributeNode)
- `cond::post::verify_mismatch_count_is_1` → `literal::1` **right_operand** (LiteralNode)
- `cond::post::verify_mismatch_version_is_1` → `MigrationManager::mismatch_version` **left_operand** (AttributeNode)
- `cond::post::verify_mismatch_version_is_1` → `literal::1` **right_operand** (LiteralNode)
- `cond::post::verify_mismatch_kind_extra_table` → `MigrationManager::mismatch_kind` **left_operand** (AttributeNode)
- `cond::post::verify_mismatch_kind_extra_table` → `UnexpectedTable` **right_operand** (AttributeNode)
- `cond::pre::verify_migration_applied` → `MigrationManager::migration_applied` **left_operand** (AttributeNode)
- `cond::pre::verify_migration_applied` → `literal::true` **right_operand** (LiteralNode)
- `cond::post::verify_consistent_no_mismatches` → `MigrationManager::mismatch_count` **left_operand** (AttributeNode)
- `cond::post::verify_consistent_no_mismatches` → `literal::0` **right_operand** (LiteralNode)
- `cond::pre::verify_consistent_migration_applied` → `MigrationManager::is_initialized` **left_operand** (AttributeNode)
- `cond::pre::verify_consistent_migration_applied` → `literal::true` **right_operand** (LiteralNode)
- `cond::post::rollback_down_called` → `MigrationManager::down_called` **left_operand** (AttributeNode)
- `cond::post::rollback_down_called` → `literal::true` **right_operand** (LiteralNode)
- `cond::post::rollback_versions_1_and_2_remain` → `MigrationManager::versions_1_2_remain` **left_operand** (AttributeNode)
- `cond::post::rollback_versions_1_and_2_remain` → `literal::true` **right_operand** (LiteralNode)
- `cond::post::rollback_version3_not_in_table` → `MigrationManager::version3_not_recorded` **left_operand** (AttributeNode)
- `cond::post::rollback_version3_not_in_table` → `literal::true` **right_operand** (LiteralNode)
- `cond::pre::rollback_three_migrations_applied` → `MigrationManager::is_initialized` **left_operand** (AttributeNode)
- `cond::pre::rollback_three_migrations_applied` → `literal::true` **right_operand** (LiteralNode)
- `cond::post::rollback_fail_error_signaled` → `MigrationManager::error_on_rollback_fail` **left_operand** (AttributeNode)
- `cond::post::rollback_fail_error_signaled` → `literal::true` **right_operand** (LiteralNode)
- `cond::post::rollback_fail_version2_still_exists` → `MigrationManager::version2_still_exists_on_fail` **left_operand** (AttributeNode)
- `cond::post::rollback_fail_version2_still_exists` → `literal::true` **right_operand** (LiteralNode)
- `cond::post::rollback_fail_version1_preserved` → `MigrationManager::version1_preserved_on_fail` **left_operand** (AttributeNode)
- `cond::post::rollback_fail_version1_preserved` → `literal::true` **right_operand** (LiteralNode)
- `cond::pre::rollback_fail_two_applied` → `MigrationManager::is_initialized` **left_operand** (AttributeNode)
- `cond::pre::rollback_fail_two_applied` → `literal::true` **right_operand** (LiteralNode)
