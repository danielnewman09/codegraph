# As-built context: cpp-sqlite

## Class: `DAOBase`
**Inherits from:** `1e1fa0bab3aa9807fe0cd6c170821cac105671f6`
- kind: class
- qualified_name: DAOBase

## Namespace: `cpp_sqlite`
- kind: namespace
- qualified_name: cpp_sqlite
### Class: `cpp_sqlite::Transaction`
RAII-style transaction management for SQLite database operations.
**Public methods:**
- `executeSQL(const std::string &sql): void` — Execute a SQL statement and handle errors.
- `getSavepointName() const noexcept: const std::string &` — Get the savepoint name (empty if not a savepoint).
- `isSavepoint() const noexcept: bool` — Check if this is a savepoint (nested transaction).
- `isActive() const noexcept: bool` — Check if the transaction is still active (not committed or rolled back).
- `rollback(): void` — Explicitly rollback the transaction.
- `commit(): void` — Commit the transaction.
- `operator=(Transaction &&other) noexcept: Transaction &`
- `Transaction(Transaction &&other) noexcept`
- `operator=(const Transaction &)=delete: Transaction &`
- `Transaction(const Transaction &)=delete`
- `~Transaction() noexcept` — Destructor - automatically rolls back if not committed.
- `Transaction(Database &db)` — Begin a new transaction.
**Public attributes:**
- `savepointCounter_: uint32_t` — Static counter for generating unique savepoint names.
- `savepointName_: std::string` — The savepoint name (if this is a savepoint).
- `isSavepoint_: bool` — Whether this is a savepoint (nested transaction).
- `isActive_: bool` — Whether this transaction is still active.
- `db_: Database *` — Reference to the database.
- kind: class
- qualified_name: cpp_sqlite::Transaction


## File Notes
- `DBDataAccessObject.hpp`
- `DBForeignKey.hpp`
- `DBBaseTransferObject.hpp`
- `DBDatabase.hpp`
- `DBTransaction.hpp`
