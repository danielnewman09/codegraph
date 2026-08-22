# Codegen golden fixtures

Pinned inputs for `tests/codegen/` snapshot + round-trip tests. Tests in
this directory read **only** these files — never sibling-repo paths.

## Files

| File | Encoding | Nodes | Provenance |
|---|---|---|---|
| `design_layergraph.json` | full declaration **minus leading qualifiers / pure-virtual markers** | 179 | Parser-owned design export, copied after semantic comparison |
| `design_layergraph_full_decl.json` | full declaration (`type_signature` = complete C++ declaration) | 155 | Reviewed full-declaration fixture; repeated placements share canonical identity |

## Artifact ownership

The parser repository owns generated design and cpp-sqlite exports. Codegraph
keeps consumer copies; `scripts/sync_codegen_fixtures.py check` is the
non-mutating gate for byte identity, canonical-only wire fields, relationship
endpoints, and source-copy provenance.

| Artifact | Owner | Consumer |
|---|---|---|
| Design LayerGraph | parser design export | Codegraph codegen goldens |
| One-hop graph | parser cpp-sqlite integration export | Codegraph fixpoint tests |
| Implementation graph | parser export workflow | Codegraph implementation tests |
| cpp-sqlite sources | parser fixture repository | Codegraph byte-fidelity tests |

## Sync convention (R1)

`scripts/sync_codegen_fixtures.py` — explicit two-way copy so the
golden never drifts silently:

- `push` — copy freshly generated
  `tests/pipelines/unit_test_data/design_layergraph.json` into the
  sister repo (`../doxygen-dependency-parser/tests/data/`) **and**
  refresh `design_layergraph.json` here. Mirrors the manual step.
- `pull` — copy the canonical sister-repo file here when the sister
  repo regenerates it.
- `check` — byte-compare synchronized artifacts and fail on drift; it never
  uses modification times or rewrites files.

Run the generator with `CODEGRAPH_SYNC_FIXTURES=1` to auto-copy on
test completion.
