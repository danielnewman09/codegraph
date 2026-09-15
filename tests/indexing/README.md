# Codegraph indexing preservation tests

`src/codegraph_index` and this repository's indexing tests are the sole
authority for indexing behavior. The preservation suite lives under
`tests/indexing/preservation/`; it includes the local Python and cpp-sqlite
fixtures needed to exercise the migrated behavior.

`cpp_sqlite_minimal`, `tests/unit_test_data`, and `tests/codegraph_output` are
non-versioned inspection artifacts. They are never required inputs. Tests
generate their own inspection outputs when needed.

The former DDP migration snapshot and comparison tooling have been retired
after outcome parity was accepted. Compatibility distribution checks, if any,
belong in the deprecated distribution rather than this repository.
