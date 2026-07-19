# codegraph: api-contract

## Class: `Migration`
Abstract base class that users subclass to define schema migrations.
- kind: class
- qualified_name: Migration
- tags: scaffold

**Public methods:**
- `getVersion() const: int` — Return the migration version number (pure virtual)
- `up(Database&): void` — Apply the migration (pure virtual)
- `down(Database&): void` — Roll back the migration (pure virtual)

## Class: `MigrationManager`
Orchestrates schema migrations against a SQLite database using cpp-sqlite.
- kind: class
- qualified_name: MigrationManager
- tags: scaffold

**Public methods:**
- `register_migration(std::unique_ptr<Migration>): MigrationResult` — Register a migration. Duplicate versions return MigrationErrorCode::DuplicateVersion. Idempotent.
- `apply(): MigrationResult` — Apply all unapplied migrations in version order. Creates schema_versions table on first call. Failing migration rolls back only that migration's Transaction.
- `rollback(int target_version): MigrationResult` — Roll back migrations above target version in descending order. Returns MigrationErrorCode::VersionNotFound if target matches no migration. Idempotent.
- `verify(): SchemaVerificationResult` — Compare live schema checksum against stored checksums. Returns list of mismatches (empty if consistent).

## Class: `SchemaVersion`
Record of an applied migration in the schema_versions tracking table.
- kind: class
- qualified_name: SchemaVersion
- tags: scaffold

**Public attributes:**
- `version: int` — Migration version number
- `applied_at: std::string` — ISO 8601 timestamp of application
- `checksum: std::string` — SHA-256 hash of the migration's SQL

## Class: `MigrationResult`
Value type returned by apply, rollback, and register_migration.
- kind: struct
- qualified_name: MigrationResult
- tags: scaffold

**Public attributes:**
- `success: bool` — Whether the operation succeeded
- `error: MigrationErrorCode` — Error code (Success on success)
- `message: std::string` — Human-readable error detail

## Enum: `MigrationErrorCode`
Error codes for migration operation results.
- kind: enum
- qualified_name: MigrationErrorCode
- tags: scaffold

**Values:**
- `Success` — Operation completed successfully
- `DuplicateVersion` — A migration with this version is already registered
- `MigrationFailed` — A migration's up() method threw an exception
- `RollbackFailed` — A migration's down() method threw an exception
- `VersionNotFound` — Target version does not match any registered migration
- `NotInitialized` — No migrations have been applied (schema_versions is empty)

## Class: `SchemaMismatch`
Describes one schema drift detection in a verify result.
- kind: struct
- qualified_name: SchemaMismatch
- tags: scaffold

**Public attributes:**
- `version: int` — The migration version this mismatch relates to
- `kind: MismatchKind` — What kind of drift was detected
- `detail: std::string` — Human-readable description of the mismatch

## Enum: `MismatchKind`
Kinds of schema mismatch detected during verification.
- kind: enum
- qualified_name: MismatchKind
- tags: scaffold

**Values:**
- `MissingTable` — A table expected by the migration does not exist
- `ExtraTable` — A table exists that is not expected by any migration
- `ColumnDifference` — A column definition differs from the expected schema

## Class: `SchemaVerificationResult`
Result of the verify operation, containing detected schema mismatches.
- kind: struct
- qualified_name: SchemaVerificationResult
- tags: scaffold

**Public attributes:**
- `mismatches: std::vector<SchemaMismatch>` — Detected schema mismatches (empty if consistent)
- `is_consistent: bool` — True if no mismatches were found

## Relationships
- `MigrationManager` → `Migration` **uses**
- `MigrationManager` → `SchemaVersion` **uses**
- `MigrationManager` → `MigrationResult` **composes**
- `MigrationManager` → `SchemaVerificationResult` **composes**
- `MigrationResult` → `MigrationErrorCode` **uses**
- `SchemaMismatch` → `MismatchKind` **uses**
- `SchemaVerificationResult` → `SchemaMismatch` **composes**
