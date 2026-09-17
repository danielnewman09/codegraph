# codegraph: requirements

## HLR: `Transaction Safety`
A transaction shall apply the statements issued between begin and commit as a single unit,
and a failure before commit shall leave the database exactly as it was before begin,
including the values of every row it touched.
- status: accepted

### LLR: `llr_transaction_commit`
When commit succeeds the transaction shall persist every statement executed since begin
and release the underlying database lock.
- status: accepted

#### Test: `vm::transaction::test_commit_persists`
A row inserted inside a committed transaction is visible to a reader on a separate connection.
- method: automated

##### TestStep: `step::transaction_commit_insert`
Insert one row between begin and commit.

##### Assertion: `cond::post::commit_row_count_is_one`
The row count observed after commit equals one.
- operator: ==
- phase: post

### LLR: `llr_transaction_rollback`
When rollback is invoked the transaction shall discard every statement executed since begin and leave the database unchanged.
- status: accepted

#### Test: `vm::transaction::test_rollback_discards`
A row inserted inside a rolled-back transaction is not visible to a reader on a separate connection.
- method: automated

##### TestStep: `step::transaction_rollback_insert`
Insert one row between begin and rollback.

##### Assertion: `cond::post::rollback_row_count_is_zero`
The row count observed after rollback equals zero.
- operator: ==
- phase: post

## HLR: `Exception Safety`
The transaction shall roll back automatically when an exception escapes the scope that owns it,
so that no partially applied change survives unwinding.
- status: proposed

## Relationships
- `Exception Safety` → `Transaction Safety` **depends_on** (HLR)
