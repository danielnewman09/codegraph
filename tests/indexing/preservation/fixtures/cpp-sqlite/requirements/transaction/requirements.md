# codegraph: requirements

## HLR: `Transaction Lifecycle`

The `cpp_sqlite::Transaction` class shall provide RAII-style ownership of a SQLite
transaction on a `cpp_sqlite::Database`: constructing a Transaction begins a transaction,
`commit()` or `rollback()` ends it, and the destructor rolls back a transaction that is
still active so that nothing executed inside it survives. A Transaction shall be
move-only, shall report whether it is still active, and shall represent a transaction
nested inside an already-active transaction as a SQLite savepoint that can be committed
or rolled back independently of the enclosing transaction.

- status: accepted

### LLR: `llr_transaction_begin_and_active_ownership`

The `cpp_sqlite::Transaction` constructor shall begin a SQLite transaction on the
referenced database and take ownership of ending it. `isActive()` shall report true from
construction until `commit()` or `rollback()` ends the transaction, and `isSavepoint()`
shall report whether this Transaction is a savepoint rather than a top-level transaction.

- status: accepted

### LLR: `llr_transaction_commit`

`commit()` called on an active Transaction shall commit every statement executed since the
transaction began and shall leave the Transaction inactive, so that its destructor does not
roll back. `commit()` called on an inactive Transaction shall signal
`cpp_sqlite::TransactionError` rather than committing.

- status: accepted

### LLR: `llr_transaction_rollback`

`rollback()` called on an active Transaction shall discard every statement executed since
the transaction began and shall leave the Transaction inactive, so that its destructor does
not attempt a second rollback. `rollback()` called on an inactive Transaction shall signal
`cpp_sqlite::TransactionError` rather than rolling back.

- status: accepted

### LLR: `llr_transaction_automatic_rollback_on_destruction`

A Transaction destroyed while still active shall roll back its transaction, so that no
statement executed inside it is persisted. The destructor shall be `noexcept` and shall not
propagate a rollback failure. Moving from a Transaction shall transfer the transaction and
leave the moved-from object inactive, so the moved-from object does not roll back the
transaction it transferred; assigning over an active Transaction shall end that
Transaction's own transaction before taking the incoming one.

- status: accepted

### LLR: `llr_transaction_nested_savepoints`

A Transaction constructed while a transaction is already active on the database shall
create a SQLite savepoint with a non-empty generated name instead of beginning a new
transaction, and `isSavepoint()` shall report true with `getSavepointName()` returning that
name. `commit()` on a savepoint Transaction shall release the savepoint, and `rollback()`
shall roll back to the savepoint and release it, leaving the enclosing transaction active
and the statements it executed before the savepoint intact.

- status: accepted

## Relationships

- `llr_transaction_begin_and_active_ownership` → `cpp_sqlite::Transaction` **realized_by** (ClassNode)
- `llr_transaction_begin_and_active_ownership` → `cpp_sqlite::Transaction::Transaction(Database &db)` **realized_by** (MethodNode)
- `llr_transaction_begin_and_active_ownership` → `cpp_sqlite::Transaction::isActive(() const)` **realized_by** (MethodNode)
- `llr_transaction_begin_and_active_ownership` → `cpp_sqlite::Transaction::isSavepoint(() const)` **realized_by** (MethodNode)
- `llr_transaction_begin_and_active_ownership` → `testDatabase::DatabaseTest::TransactionCommit` **verified_by** (TestNode)
- `llr_transaction_commit` → `cpp_sqlite::Transaction::commit()` **realized_by** (MethodNode)
- `llr_transaction_commit` → `cpp_sqlite::Transaction::executeSQL(const std::string &sql)` **realized_by** (MethodNode)
- `llr_transaction_commit` → `testDatabase::DatabaseTest::TransactionCommit` **verified_by** (TestNode)
- `llr_transaction_rollback` → `cpp_sqlite::Transaction::rollback()` **realized_by** (MethodNode)
- `llr_transaction_rollback` → `cpp_sqlite::Transaction::executeSQL(const std::string &sql)` **realized_by** (MethodNode)
- `llr_transaction_rollback` → `testDatabase::DatabaseTest::TransactionRollback` **verified_by** (TestNode)
- `llr_transaction_automatic_rollback_on_destruction` → `cpp_sqlite::Transaction::~Transaction(())` **realized_by** (MethodNode)
- `llr_transaction_automatic_rollback_on_destruction` → `cpp_sqlite::Transaction::Transaction((Transaction &&other))` **realized_by** (MethodNode)
- `llr_transaction_automatic_rollback_on_destruction` → `cpp_sqlite::Transaction::operator=((Transaction &&other))` **realized_by** (MethodNode)
- `llr_transaction_automatic_rollback_on_destruction` → `testDatabase::DatabaseTest::TransactionAutoRollbackOnDestruction` **verified_by** (TestNode)
- `llr_transaction_nested_savepoints` → `cpp_sqlite::Transaction::Transaction(Database &db)` **realized_by** (MethodNode)
- `llr_transaction_nested_savepoints` → `cpp_sqlite::Transaction::getSavepointName(() const)` **realized_by** (MethodNode)
- `llr_transaction_nested_savepoints` → `cpp_sqlite::Transaction::commit()` **realized_by** (MethodNode)
- `llr_transaction_nested_savepoints` → `cpp_sqlite::Transaction::rollback()` **realized_by** (MethodNode)
- `llr_transaction_nested_savepoints` → `testDatabase::DatabaseTest::NestedTransactionWithSavepoints` **verified_by** (TestNode)
- `llr_transaction_nested_savepoints` → `testDatabase::DatabaseTest::NestedTransactionRollbackInner` **verified_by** (TestNode)
