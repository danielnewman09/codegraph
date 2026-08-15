# Current-State Gap Assessment

**Status:** Point-in-time assessment  
**Assessed:** 2026-08-15  
**Scope:** Codegraph, Doxygen Dependency Parser, and `cpp-sqlite`

This document compares the current implementation with the design intent in
this folder. Unlike the normative intent documents, it describes a dated
snapshot and should be revised or superseded as capabilities change.

## Executive assessment

Codegraph has a credible foundation for the intended workspace. Source indexing
is the strongest subsystem. Requirements, test, and memory models also exist as
first-class graph structures, with meaningful persistence and serialization
tests. The primary gap is no longer the absence of these concepts; it is the
absence of one reconciliation contract that proves they remain connected while
code moves through generation and re-indexing.

The next useful milestone is therefore not another isolated model or exporter.
It is a golden, end-to-end preservation test using `cpp-sqlite` that combines:

```text
repository requirements + scoped memories + real tests + as-built code
                              ↓ index
                    connected baseline graph
                              ↓ generate/re-index
                    connected observed graph
                              ↓ reconcile
          identity, content, and linkage preservation report
```

## What exists today

### Code indexing and generation — strong, actively converging

- C++ and Python indexing produce stable code entities and relationships.
- The `cpp-sqlite` as-built fixture is already used by codegen tests.
- Codegen renders C++ declarations and can pass through complete source files
  when implementation text is available.
- Round-trip verification currently has three useful levels:
  compound correspondence, canonical method-signature correspondence, and a
  normalized identity comparison over selected code node types.
- Known parser and generator asymmetries are explicitly classified rather than
  hidden.

The remaining code-only fidelity gaps are real but bounded. Current golden tests
pin such limitations as base-class rendering, enum parsing, template artifacts,
file/parameter asymmetry, and documentation normalization.

### As-built test indexing — stronger than the codegen proof currently uses

The Doxygen Dependency Parser's `cpp-sqlite` integration suite already checks:

- one `TestNode` for each real GoogleTest `TEST_F` case;
- assertion nodes derived from `ASSERT_*` and `EXPECT_*` statements;
- setup and action `TestStepNode` instances with source ranges;
- test-to-code `VERIFIES` edges and step-to-code `CALLEE` edges;
- at least 100 resolved edges of each relationship kind in the fixture;
- as-built provenance and source identity;
- preservation of test composition, verification edges, and enriched test
  descriptions during an unchanged incremental re-index.

This means test discovery and basic re-index stability are not greenfield work.

### Requirements — model and document round trips exist

- `HLR` and `LLR` are first-class graph nodes with deterministic identities.
- The model supports `HLR → LLR → TestNode` composition and links requirements
  to design compounds.
- The requirements repository resolves full HLR/LLR/test trees and verification
  targets.
- Markdown import/export tests preserve requirement hierarchy, descriptions,
  tags, and component structure.
- The design pipeline can create requirement, design, and verification
  structures and persist `VERIFIES` links.
- Project configuration recognizes a `requirements_dir` path.

### Memory — useful subsystem, currently parallel to generation

- Decisions, constraints, rationales, assumptions, tradeoffs, and insights are
  first-class nodes with deterministic identities and provenance.
- Memory nodes link to compounds or members through typed relationships.
- Memory-to-memory relations such as `SUPERSEDES`, `REFINES`, and `CONTRADICTS`
  exist.
- `MemoryGraph` supports code-scoped queries and JSON-style
  serialization/deserialization.
- Repository implementations support lookup, full-text and semantic search,
  ancestor/descendant context, and code-node linking.
- Lifecycle checks detect orphaned and low-confidence memories.

## Material gaps

### `GAP-001` — Unified round-trip scope

The Tier-3 codegen identity comparison intentionally excludes requirement and
test-model nodes. Its current golden test pins 68 such nodes as
`requirement-model: never emitted as code`. Memory nodes are outside the codegen
context registry entirely.

The missing contract is not that requirements or memories should be rendered as
C++. It is that non-code artifacts and their edges must survive around a code
round trip and be reconciled against re-indexed code identities.

### `GAP-002` — Test generation fidelity

Codegen understands `TestNode`, `TestStepNode`, and `AssertionNode`, but C++ test
generation is intentionally honest scaffolding: descriptions and TODO comments,
not reconstructed executable test bodies. `TestFixtureNode` is a declared skip.

As-built test indexing is robust, but there is no golden proof of either:

1. source test → indexed test → regenerated executable-equivalent test →
   re-indexed test; or
2. design test intent → generated test scaffold/implementation → re-indexed
   test with preserved intent correspondence.

These are different contracts and should be tested separately.

### `GAP-003` — Requirement-folder ingestion is not yet the normal index loop

The configuration model accepts `requirements_dir`, and Markdown requirement
import works in Codegraph. In the inspected parser implementation, however, the
path is configured but no normal indexing orchestration consumes it. The
canonical repository requirement corpus is therefore not yet demonstrably
indexed alongside code and tests by one command.

### `GAP-004` — Requirement linkage preservation under code replacement

Unit and integration tests demonstrate requirement trees and verification-edge
operations, but there is no end-to-end assertion that requirement-to-design,
requirement-to-test, and test-to-code linkages survive when generated code is
parsed into new as-built identities or when an incremental re-index replaces
code nodes.

### `GAP-005` — Memory is not part of codegen context or reconciliation

Memory can be queried by code node, but `CodegenContextBuilder` has no memory
context input. A generation run does not declare which memories constrained it,
and the round-trip report does not check that those memories still resolve to
the corresponding as-built entities.

### `GAP-006` — Memory scope does not cover all intended artifacts

Typed memory relationships currently target compounds and members. There is no
equally explicit model for scoping a memory directly to a requirement, test,
assertion, design decision target, or drift finding. This limits the intended
workflow in which a design iteration creates memory attached to the precise
artifact or assumption that changed.

### `GAP-007` — Deserialized memory edge fidelity

`MemoryGraph` preserves its primary linked-code metadata across serialization,
but its existing test documents that live serialized edges disappear when an
in-memory deserialized node is immediately re-serialized because those edges
are backend-derived. A portable snapshot needs an explicit edge-preservation
contract independent of current database attachment.

### `GAP-008` — No unified drift vocabulary or report

Codegen identity drift, memory lifecycle drift, unresolved verification, and
requirement coverage are separate mechanisms. They do not yet produce the
feature-level classification required by `DI-FTR-007`: implementation defect,
design iteration, requirement/test issue, consequential decision, or indexing
fidelity limitation.

### `GAP-009` — Verification evidence is mostly structural

Current graph tests strongly verify node and edge extraction. They do not yet
bind an actual GoogleTest execution result, build identity, timestamp, and
relevant artifact revision to the requirement and test nodes. Consequently,
`test exists` and `test currently passed for this implementation` remain
different facts without a complete evidence bridge.

### `GAP-010` — Golden fixture and golden project can diverge

Codegraph carries archived `cpp-sqlite` JSON and source fixtures while the real
`cpp-sqlite` repository now exists beside it. Without a declared fixture-sync
policy, tests may prove behavior against an older projection rather than the
current golden project.

### `GAP-011` — Indexing and graph lifecycle are split across repositories

The indexing project now creates Codegraph-native models and edges, writes
through Codegraph backends, preserves enriched graph state during incremental
updates, shares project configuration with Codegraph commands, drives Codegraph
round-trip verification, and is invoked directly by the explorer. These are no
longer cleanly independent products.

The repository boundary adds coordination cost precisely where the desired
workflow needs one transaction: index code, tests, and requirements; preserve
external memory and requirement edges; generate; re-index; and reconcile. The
proposed direction is captured in the integrated indexing intent document.

### `GAP-012` — SHA-1 obscures rather than defines node identity

`CodeGraphNode.uid` is currently the SHA-1 digest of `source` plus each node
type's declared identity fields. The digest is deterministic, but it provides no
additional identity semantics and makes graph data, logs, fixtures, debugging,
and manual reconciliation less legible.

The current tuple also exposes semantic debt independent of hashing:

- node type is not included, so different model types can derive the same UID
  from the same source and qualified name;
- source is included even when design and as-built views should correspond to
  the same logical entity;
- round-trip verification consequently cannot compare UIDs and instead rebuilds
  normalized qualified-name and signature keys;
- relationship fixtures and APIs traffic in opaque 40-character values even
  when the meaningful identity fields are already available.

The proposed direction is a typed, canonical, reversible string key. Changing
the encoding alone is insufficient; the migration must also settle the
semantics of project scope, provenance, overload identity, and cross-view
correspondence.

## Recommended golden-example test ladder

The safest next step is to add capability in layers so failures identify one
contract at a time.

### Stage 0 — Declare the golden baseline

- Treat the real `cpp-sqlite` repository as the source fixture.
- Pin or record the fixture revision without copying transient build output.
- Define a deterministic command that refreshes Codegraph's test fixture.
- Fail when the checked fixture and declared source revision disagree.

### Stage 1 — As-built connected baseline

Create honest, reviewable requirements for existing `cpp-sqlite` behavior and a
small set of scoped memories that explain real design choices. Index:

- source entities and relationships;
- GoogleTest tests, steps, assertions, `VERIFIES`, and `CALLEE` edges;
- HLR/LLR hierarchy from the repository requirements folder;
- requirement-to-component/design and LLR-to-test relationships;
- memory-to-code and, once supported, memory-to-requirement/test relationships.

Assert exact identities and edge endpoints for a deliberately small vertical
slice first, such as transaction behavior or data-access buffering.

### Stage 2 — Persistence-only preservation

Export the connected graph to a portable snapshot, reload it into an empty
backend, and assert a normalized bijection over:

- code nodes and code relationships;
- tests, steps, assertions, and operands;
- requirements and hierarchy;
- all cross-domain linkages;
- memories, memory-to-memory edges, and scoped targets.

This isolates serialization and datastore fidelity from code generation.

### Stage 3 — Unchanged incremental re-index

Re-index the unchanged `cpp-sqlite` source into the populated backend. Assert
that requirements, memories, enriched test intent, and every external linkage
remain unchanged. This extends the parser's existing preservation tests from
test-only relationships to the complete connected engineering model.

### Stage 4 — Code generation round trip with overlay preservation

Run code through source → index → generate → re-index. Compare code identity and
content using the existing Tier-3 machinery, while treating requirements,
memories, and test intent as a durable overlay. Rebind overlay edges to observed
as-built identities and assert that no linkage is silently lost.

Executable source-test reproduction can remain a separately declared gap while
overlay preservation is proven.

### Stage 5 — Test-generation contract

Choose and state one contract explicitly:

- byte or AST-equivalent reproduction of as-built tests;
- semantic reproduction of executable tests; or
- generation of traceable test scaffolds from design-time test intent.

Then add corresponding parse-back and execution assertions. Do not label TODO
scaffolding as full test round-trip fidelity.

### Stage 6 — Controlled drift scenarios

Introduce one change at a time and assert classification:

- rename a method while preserving behavior;
- change a signature;
- remove a verified method;
- change a requirement;
- change a test without changing its requirement;
- contradict a design assumption during implementation;
- remove or supersede a memory.

Each scenario should identify affected artifacts, stale evidence, lost or
rebound edges, the proposed resolution class, and whether engineer input is
required.

## Suggested first vertical slice

The first proof should be narrow enough to understand manually. A suitable
slice is `cpp_sqlite::Transaction`:

- requirements for begin, commit, rollback, automatic rollback, and nested
  transaction/savepoint behavior;
- design memories for RAII ownership, rollback safety, and nested transaction
  strategy;
- the class, its public methods, and implementation bodies;
- the corresponding GoogleTest cases, assertions, and verified method edges;
- build and test execution evidence.

Success is a single report showing that every durable artifact and cross-domain
edge survives snapshot reload, unchanged re-index, and the supported code
round trip—or appears as a precise, classified fidelity gap.

## Priority assessment

1. **Define the connected golden snapshot and normalized comparison contract.**
2. **Integrate repository requirement ingestion into normal indexing.**
3. **Preserve and reconcile external edges across re-indexed code identities.**
4. **Add memory to generation context with recorded provenance.**
5. **Extend memory scope to requirements, tests, and drift findings.**
6. **Add execution evidence and semantic staleness.**
7. **Only then broaden test code generation fidelity.**

The `codegraph_index` consolidation can proceed incrementally alongside these
priorities. Its first purpose should be to establish a stable in-process
indexing contract, not to rename every command before preservation behavior is
covered by tests.

This order uses the strong indexing foundation immediately and avoids coupling
the preservation of requirements and memory to the harder problem of perfectly
regenerating executable C++ tests.
