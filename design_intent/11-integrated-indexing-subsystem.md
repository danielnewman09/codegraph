# Integrated Indexing Subsystem

**Status:** Proposed direction  
**Established:** 2026-08-15

## Decision direction

The capabilities currently delivered by the separate `doxygen-index` project
should converge into Codegraph as an indexing subsystem, provisionally named
`codegraph_index`.

Here, “submodule” means a Python package and architectural subsystem within the
Codegraph project, such as `src/codegraph_index/`. It does not require a Git
submodule. A Git submodule would retain many of the repository-boundary costs
that this consolidation is intended to remove.

### `DI-IDX-001` — Indexing is part of the closed loop

Indexing shall be a first-class Codegraph capability because it constructs the
observed graph used by generation, requirements traceability, test mapping,
memory preservation, drift detection, and the explorer workflow.

### `DI-IDX-002` — Doxygen is an adapter, not the product boundary

The enduring abstraction is codebase indexing. Doxygen XML is one C++
extraction adapter; Python AST parsing is another. Future languages and evidence
sources should be addable without inheriting a Doxygen-specific package or
command model.

### `DI-IDX-003` — One orchestration boundary

Code, tests, repository requirements, and other configured artifacts should be
indexed through one project-level orchestration API. The orchestration should
also own preservation and reconciliation of graph data that is not regenerated
by source parsing.

### `DI-IDX-004` — Parser adapters remain isolated

Repository consolidation shall not merge parser details into core graph models.
Each language or extraction mechanism should implement a stable adapter
contract that returns normalized nodes, relationships, diagnostics, provenance,
and fidelity limitations.

### `DI-IDX-005` — Core remains usable without extraction toolchains

The graph model, persistence APIs, serialization, and in-memory operations
should remain usable without Doxygen, a C++ compiler, Conan, or optional web
scraping dependencies. Indexer dependencies should be optional or isolated by
adapter.

### `DI-IDX-006` — In-process API before subprocess coupling

Codegen verification, the explorer, and orchestration workflows should invoke a
stable indexing service API when operating in the same environment. A CLI may
wrap that API, but subprocess invocation should not be the only integration
contract.

### `DI-IDX-007` — Incremental indexing preserves external knowledge

The indexer must distinguish source-owned facts from external durable overlays.
Re-indexing source may replace observed nodes and parser-owned edges, but shall
preserve or deliberately reconcile requirements, memories, design links,
enrichment, test intent, and verification evidence.

### `DI-IDX-008` — Index runs emit reconciliation inputs

An index run should report created, matched, changed, deleted, and ambiguous
entities and edges. This delta becomes an input to feature-level drift detection
rather than remaining an internal parser side effect.

### `DI-IDX-009` — One project configuration model

Indexing, persistence, generation, visualization, requirements ingestion, and
the explorer should share a coherent Codegraph project configuration. Adapter-
specific settings may occupy namespaced sections.

### `DI-IDX-010` — Backward compatibility is deliberate

During migration, the `doxygen-index` command and `.doxygen-index.toml` should
remain supported as compatibility surfaces. They may delegate to
`codegraph_index` while users move to a Codegraph-named command and
configuration on an explicit deprecation schedule.

## Proposed responsibility boundary

```text
codegraph core
├── models and stable identities
├── graph containers and repositories
├── persistence backends
├── serialization and derived views
└── reconciliation vocabulary

codegraph_index
├── project-level indexing orchestration
├── incremental update and preservation policy
├── normalized indexing result and delta
├── requirements-folder ingestion
├── test extraction coordination
└── language/source adapters
    ├── C++ / Doxygen XML
    ├── C++ test extraction
    ├── Python AST
    ├── Python test extraction
    ├── Conan dependencies
    └── optional cppreference enrichment
```

Generation, the explorer, and higher-level agents consume the public Codegraph
and `codegraph_index` APIs. They should not need to know whether a code entity
was extracted through Doxygen, an AST, or another adapter unless provenance or
fidelity diagnostics matter to the task.

## Why the boundary has converged

The current projects already share more than a data format:

- `doxygen-index` depends on Codegraph and imports its models throughout;
- indexing writes through Codegraph backends and repository semantics;
- it creates Codegraph test nodes, assertions, steps, and verification edges;
- incremental re-indexing contains policies for preserving enriched Codegraph
  data and external relationships;
- Codegraph's round-trip tests invoke `doxygen-index` as the parse-back stage;
- Codegraph's explorer invokes its CLI to re-index edited code;
- both projects understand `.doxygen-index.toml` and Codegraph output paths.

The meaningful seam is therefore parser adapter versus engineering model, not
one repository versus another.

## Migration constraints

### Preserve behavior before relocation

The existing C++ and Python integration suites should be runnable against the
new package before deleting or substantially rewriting the old implementation.
Relocation and semantic changes should be separable so regressions are
attributable.

### Resolve runtime compatibility

The indexing project currently declares Python 3.10+, while Codegraph requires
Python 3.12+. Consolidation should explicitly choose the Codegraph runtime
contract or justify retaining a separately distributable compatibility package.

### Remove duplicate persistence ownership

Indexer modules named as Neo4j or JSON backends should be evaluated as writers,
adapters, or compatibility layers. Canonical datastore operations belong behind
Codegraph backend and repository interfaces; indexing should submit normalized
results rather than own a parallel persistence architecture.

### Preserve optionality

Doxygen, Conan, cppreference scraping, BeautifulSoup, requests, and lxml should
not become mandatory dependencies for users who only need Python indexing or
core graph operations.

### Maintain fixture provenance

The `cpp-sqlite` integration fixture and its source revision should have one
declared ownership and refresh path after consolidation. Duplicated fixture
trees should not drift silently between packages.

## Suggested migration sequence

1. Define an `IndexRequest`, normalized `IndexResult`, and `IndexDelta` API.
2. Add `codegraph_index` inside the Codegraph repository without changing the
   existing external CLI.
3. Move or wrap project configuration and the top-level pipeline first.
4. Move language and test adapters behind the normalized interface.
5. Route writes exclusively through Codegraph repositories and preservation
   policies.
6. Add requirements-folder ingestion to the unified project index operation.
7. Change codegen verification and explorer re-indexing from subprocess-only
   integration to the in-process service API.
8. Run the existing parser suites and the connected `cpp-sqlite` golden ladder
   against the integrated package.
9. Keep `doxygen-index` as a thin compatibility entry point, then deprecate it
   only after downstream configuration and automation have migrated.

## Acceptance criteria for consolidation

The move is successful when:

- C++ and Python indexing retain their current node and edge fidelity;
- real C++ and Python tests retain extraction and verification links;
- unchanged incremental indexing preserves external durable overlays;
- requirements in the configured repository folder are indexed in the same
  operation;
- codegen and the explorer use a documented indexing API;
- optional parser dependencies remain isolated;
- the old CLI produces equivalent results through the new implementation;
- the `cpp-sqlite` connected golden test passes without maintaining two
  independently evolving fixture implementations.

