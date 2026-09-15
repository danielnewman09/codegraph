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

Generated `unit_test_data` and `codegraph_output` files are not inputs to
this fixture and are intentionally excluded from version control.
