# codegraph: api-contract

## Class: `Migration`
Abstract base class that users subclass to define schema migrations.
- kind: class
- qualified_name: Migration
- tags: scaffold

**Public methods:**
- `getVersion() const: int` — Return the migration version number (pure virtual)
- `up(Transaction&): void` — Apply the migration within a cpp-sqlite Transaction (pure virtual)
- `down(Transaction&): void` — Roll back the migration within a cpp-sqlite Transaction (pure virtual)

## Class: `MigrationManager`
Orchestrates schema migrations against a SQLite database using cpp-sqlite.
- kind: class
- qualified_name: MigrationManager
- tags: scaffold

**Constructor:**
- `MigrationManager(Database& db)` — Construct with a reference to the cpp_sqlite Database to manage

**Public attributes:**
- `initialized: bool` — True once a migration has been successfully applied; derived from schema_versions at construction (table exists with rows) and never reset by rollback
- `registered_migrations: std::vector<std::unique_ptr<Migration>>` — Registered migrations, kept sorted by version ascending

**Public methods:**
- `register_migration(std::unique_ptr<Migration>): MigrationResult` — Register a migration. Duplicate versions return MigrationErrorCode::DuplicateVersion.
- `apply(): MigrationResult` — Apply all unapplied migrations in version order, each in its own committed Transaction. Creates schema_versions table on first call in its own committed Transaction (an empty table remains if the first migration fails). Records each SchemaVersion.checksum as the SHA-256 hash of the schema (sqlite_master SQL concatenation) captured after up() in the same Transaction. Failing migration rolls back only that migration's Transaction.
- `rollback(int target_version): MigrationResult` — Roll back migrations above the target version in descending order; each down() and its row deletion run in a single committed Transaction. Precedence: NotInitialized only when no migration has ever been applied; targets at or below the lowest applied version perform a full rollback; applied targets roll back strictly-above versions; any other target returns VersionNotFound. Idempotent for repeated calls.
- `verify(): SchemaVerificationResult` — Compute SHA-256 checksum of live schema via sqlite_master and compare against the stored checksum of the highest applied SchemaVersion. Returns mismatches if they differ.

## Class: `SchemaVersion`
Record of an applied migration in the schema_versions tracking table.
- kind: class
- qualified_name: SchemaVersion
- tags: scaffold

**Public attributes:**
- `version: int` — Migration version number
- `applied_at: std::string` — ISO 8601 timestamp of application
- `checksum: std::string` — SHA-256 hash of the database schema (sqlite_master SQL concatenation) after applying this migration

## Class: `MigrationResult`
Value type returned by apply, rollback, and register_migration.
- kind: struct
- qualified_name: MigrationResult
- tags: scaffold

**Public attributes:**
- `success: bool` — Whether the operation succeeded
- `error: MigrationErrorCode` — Error code (Success on success)

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
- `VersionNotFound` — Rollback target matches no applied migration and is greater than the lowest applied version
- `NotInitialized` — No migration has ever been successfully applied (fresh database)

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
- `MissingTable` — A table expected by the migration does not exist (reserved; not emitted by the current verify algorithm)
- `ExtraTable` — A table exists that is not expected by any migration (reserved; not emitted by the current verify algorithm)
- `ColumnDifference` — A column definition differs from the expected schema (reserved; not emitted by the current verify algorithm)
- `ChecksumMismatch` — Live schema checksum does not match the stored checksum (the only kind the current verify algorithm emits)

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
