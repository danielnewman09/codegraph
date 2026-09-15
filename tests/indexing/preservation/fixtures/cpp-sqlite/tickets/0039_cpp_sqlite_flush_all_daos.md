# Ticket 0039: cpp_sqlite flushAllDAOs() Method

## Status
- [x] Draft
- [ ] Ready for Design
- [ ] Design Complete — Awaiting Review
- [ ] Design Approved — Ready for Prototype
- [ ] Prototype Complete — Awaiting Review
- [ ] Ready for Implementation
- [ ] Implementation Complete — Awaiting Quality Gate
- [ ] Quality Gate Passed — Awaiting Review
- [ ] Approved — Ready to Merge
- [ ] Documentation Complete
- [ ] Merged / Complete

**Current Phase**: Draft
**Assignee**: Unassigned
**Created**: 2026-02-06
**Priority**: Medium
**Complexity**: Small
**Target Component**: cpp_sqlite (external library)
**Generate Tutorial**: No
**Blocked By**: None
**Blocks**: 0038_simulation_data_recorder (design simplification)

---

## Summary

Add a `flushAllDAOs()` method to `cpp_sqlite::Database` that iterates over all registered `DataAccessObject` instances and calls their `insert()` method to flush buffered records. This enables bulk flushing without requiring consumers to track individual DAO references.

---

## Motivation

The `cpp_sqlite` library's `Database` class manages `DataAccessObject<T>` instances internally via `getDAO<T>()`. Currently, to flush all buffered records, a consumer must:

1. Track every DAO type they've used
2. Retrieve each DAO individually via `getDAO<T>()`
3. Call `insert()` on each one

This creates redundant bookkeeping in consumers like the `DataRecorder` class (ticket 0038), which would otherwise need to maintain a `std::vector<DAOBase*>` just to iterate and flush.

Since the `Database` already owns all DAO instances internally, it's the natural place to provide a bulk flush operation.

**User impact**: Simplifies DataRecorder design by eliminating redundant DAO tracking. Any cpp_sqlite consumer needing periodic batch writes benefits from this convenience method.

---

## Requirements

### Functional Requirements

1. **FR-1**: The `Database` class shall provide a `flushAllDAOs()` method
2. **FR-2**: `flushAllDAOs()` shall call `insert()` on every `DataAccessObject` that has been created via `getDAO<T>()`
3. **FR-3**: The flush order shall be deterministic (e.g., creation order or alphabetical by type name)
4. **FR-4**: `flushAllDAOs()` shall be safe to call when no DAOs exist (no-op)
5. **FR-5**: `flushAllDAOs()` shall be safe to call when all DAO buffers are empty (no-op per DAO)

### Non-Functional Requirements

1. **NFR-1**: `flushAllDAOs()` shall complete in O(n) time where n is the number of registered DAOs
2. **NFR-2**: The method shall be thread-safe (safe to call while other threads call `addToBuffer()`)

---

## Proposed Interface

```cpp
namespace cpp_sqlite {

class Database {
public:
    // ... existing methods ...

    /**
     * @brief Flush all buffered records from all registered DAOs
     *
     * Iterates over all DataAccessObject instances created via getDAO<T>()
     * and calls insert() on each to flush their write buffers to the database.
     *
     * Thread-safe: Can be called while other threads add records via addToBuffer().
     *
     * @note This is a convenience method equivalent to calling dao.insert()
     *       on each DAO individually. The flush order is deterministic
     *       (creation order of DAOs).
     */
    void flushAllDAOs();

private:
    // Existing: stores DAOs by type
    // Need to also maintain iteration order
    std::vector<DAOBase*> daoCreationOrder_;  // New: for ordered iteration
};

}  // namespace cpp_sqlite
```

---

## Implementation Notes

### Current cpp_sqlite Architecture

The `Database` class likely stores DAOs in a type-erased map (e.g., `std::unordered_map<std::type_index, std::unique_ptr<DAOBase>>`). The `DAOBase` class already provides a virtual `insert()` method for polymorphic flushing.

### Required Changes

1. **Add `daoCreationOrder_` vector**: When `getDAO<T>()` creates a new DAO, append its `DAOBase*` to this vector
2. **Implement `flushAllDAOs()`**: Iterate `daoCreationOrder_` and call `dao->insert()` on each
3. **Thread safety**: The existing `insert()` method is already thread-safe (buffer swap is mutex-protected). No additional synchronization needed in `flushAllDAOs()` itself.

### Edge Cases

- **Empty database**: `daoCreationOrder_` is empty, loop is no-op
- **DAO with empty buffer**: `insert()` on empty buffer is already a no-op in cpp_sqlite
- **Concurrent `getDAO<T>()` during flush**: If new DAOs can be created while flushing, need mutex protection on `daoCreationOrder_`. Alternatively, document that `flushAllDAOs()` only flushes DAOs that existed at call time.

---

## Acceptance Criteria

- [ ] **AC1**: `Database::flushAllDAOs()` method exists and compiles
- [ ] **AC2**: Calling `flushAllDAOs()` flushes all records added via `addToBuffer()` to all DAOs
- [ ] **AC3**: Calling `flushAllDAOs()` on empty database does not crash
- [ ] **AC4**: Calling `flushAllDAOs()` when buffers are empty does not crash
- [ ] **AC5**: Flush order is deterministic across multiple calls
- [ ] **AC6**: Unit test demonstrates flushing multiple DAO types in single call
- [ ] **AC7**: Thread safety test: concurrent `addToBuffer()` and `flushAllDAOs()` does not corrupt data

---

## Test Cases

| Test Case | Description |
|-----------|-------------|
| `FlushAllDAOs_EmptyDatabase_NoOp` | Call on fresh database with no DAOs |
| `FlushAllDAOs_SingleDAO_FlushesRecords` | Single DAO with buffered records |
| `FlushAllDAOs_MultipleDAOs_FlushesAll` | Multiple DAO types, all flushed |
| `FlushAllDAOs_EmptyBuffers_NoOp` | DAOs exist but buffers are empty |
| `FlushAllDAOs_DeterministicOrder` | Verify flush order matches creation order |
| `FlushAllDAOs_ThreadSafety` | Concurrent addToBuffer() during flush |

---

## Scope Boundaries

### In Scope
- `flushAllDAOs()` method on `Database` class
- Internal tracking of DAO creation order
- Unit tests for the new method

### Out of Scope
- Transaction wrapping (separate enhancement if needed)
- Selective flushing (flush only specific DAOs)
- Async/non-blocking flush
- Changes to existing `insert()` behavior

---

## References

- **Parent ticket**: [0038_simulation_data_recorder](./0038_simulation_data_recorder.md) — DataRecorder needs bulk flush capability
- **cpp_sqlite patterns**: `DataAccessObject<T>::insert()`, `DAOBase` virtual interface

---

## Workflow Log

### Draft Phase
- **Started**: 2026-02-06
- **Completed**: 2026-02-06
- **Artifacts**: Initial ticket created
- **Notes**: Created to simplify DataRecorder design (ticket 0038). Instead of DataRecorder tracking individual DAO pointers, the Database class provides bulk flush. This is a cpp_sqlite library enhancement.

---

## Human Feedback

*(Space for reviewer comments)*

