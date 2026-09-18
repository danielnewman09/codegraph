# cpp-sqlite migration fixture

The source files in this directory are the regular-file materialization of
the `cpp-sqlite` gitlink recorded by the frozen DDP baseline:

```text
4a1450a5e6a5b8edf7f3572b4eaa6085df37e571
```

That revision is migration evidence only.  Tests consume this local copy and
must not read a DDP checkout.  The `.doxygen-index.toml` file is a
Codegraph-owned parity overlay: it selects the source and GoogleTest paths
whose resulting graph contract is asserted by the lifted suite.

The `requirements/` tree is likewise Codegraph-authored, not lifted source:
it holds the repository-authoritative requirement documents for the Priority 5
Transaction golden slice (one HLR owning five LLRs bound to the real
`cpp_sqlite::Transaction` members and the five real GoogleTests).  Re-syncing
the lifted `cpp_sqlite/` sources must not overwrite it, and the requirement
text must stay consistent with those sources.

Generated `unit_test_data` and `codegraph_output` files are not inputs to
this fixture and are intentionally excluded from version control.
