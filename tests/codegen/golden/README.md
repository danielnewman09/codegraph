# Codegen golden fixtures

Pinned inputs for `tests/codegen/` snapshot + round-trip tests. Tests in
this directory read **only** these files — never sibling-repo paths.

## Files

| File | Encoding | Nodes | Provenance |
|---|---|---|---|
| `design_layergraph.json` | full declaration **minus leading qualifiers / pure-virtual markers** (`type_signature` = `'int getVersion() const'`; `argsstring` degraded `'()'`; attributes carry plain types) | 181 | Current design-agent generator output. Copy of `tests/pipelines/unit_test_data/design_layergraph.json` (written by `tests/pipelines/test_design_migration_manager.py`), which mirrors `../doxygen-dependency-parser/tests/data/design_layergraph.json` |
| `design_layergraph_full_decl.json` | full declaration (`type_signature` = complete C++ declaration, spec D8, e.g. `'virtual int getVersion() const = 0'`) | 155 | Committed revision of `doxygen-dependency-parser/tests/data/design_layergraph.json` (git HEAD, sha `c4df38f7d4395347`), extracted via `git show HEAD:tests/data/design_layergraph.json`. Pins the D8 verbatim-emission path and D9 duplicate-uid dedup (10 dup uids). Refreshed only deliberately |

## Sync convention (R1)

`scripts/sync_codegen_fixtures.py` — explicit two-way copy so the
golden never drifts silently:

- `push` — copy freshly generated
  `tests/pipelines/unit_test_data/design_layergraph.json` into the
  sister repo (`../doxygen-dependency-parser/tests/data/`) **and**
  refresh `design_layergraph.json` here. Mirrors the manual step.
- `pull` — copy the canonical sister-repo file here when the sister
  repo regenerates it.
- `check` — byte-compare golden vs canonical; fail with drift report.

Run the generator with `CODEGRAPH_SYNC_FIXTURES=1` to auto-copy on
test completion.
