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

The `transaction_slice/` tree is Codegraph-authored too: it holds the reviewed
memory input for the same slice (`memories.toml`) — the RAII ownership
decision, the no-throw cleanup constraint, and the savepoint-nesting rationale
— whose `links` name the real `cpp_sqlite::Transaction` class and its twelve
frozen members.  Every construct a memory quotes is asserted to exist in
`DBTransaction.hpp`/`DBTransaction.cpp`, so the rationale cannot drift from
the sources it describes.  Re-syncing the lifted `cpp_sqlite/` sources must
not overwrite this tree either.

It also holds the reviewed execution evidence (WP5.4): `evidence.toml` and
the retained `logs/` of the successful Release build and the filtered
GoogleTest run over the five slice tests.  The only supported author is
`scripts/capture_transaction_slice_evidence.py` at the repository root; it
refuses to capture unless the worktree's `cpp_sqlite/` tree is digest-
identical to this fixture's copy, and each record's `revision` carries the
worktree git revision, that tree digest, and the golden gitlink above.
Ordinary test runs validate `evidence.toml` against the retained log bytes
and never rebuild or rewrite it.

Generated `unit_test_data` and `codegraph_output` files are not inputs to
this fixture and are intentionally excluded from version control.
