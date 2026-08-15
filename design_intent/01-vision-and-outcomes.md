# Vision and Outcomes

**Status:** Living intent  
**Established:** 2026-08-15

## Vision

Codegraph provides a persistent engineering model shared by engineers, tools,
and LLMs. It integrates indexed knowledge about requirements, design,
implementation, tests, decisions, and generated artifacts so that work can
continue coherently across sessions and across the evolution of a codebase.

The knowledge graph is not only a search index. It is the continuity layer that
records durable identity, provenance, relationships, and reconciliation state.
The source repository remains the reviewable home of authored engineering
artifacts, while the datastore provides structured projections and traversal.

## Intended outcomes

### `DI-VIS-001` — Durable engineering continuity

An LLM and engineer shall be able to discover relevant existing artifacts and
prior decisions before creating or changing work, independent of conversational
session history.

### `DI-VIS-002` — Explicit alignment

The system shall make the alignment or divergence among intent, requirements,
design, implementation, and tests observable. It shall not imply consistency
merely because artifacts exist.

### `DI-VIS-003` — Bounded comprehension

The workspace shall present the smallest sufficient component-level context for
an engineering decision. It should reduce the need to load an entire repository
or generate large explanatory documents solely to recover context.

### `DI-VIS-004` — Engineer authority

The engineer remains the decision maker. Codegraph should expose evidence,
uncertainty, provenance, and proposed deltas so that the engineer can make an
informed choice about what to build next and how to direct the LLM.

### `DI-VIS-005` — Closed-loop engineering

Generation is incomplete until its output is parsed, indexed, reconciled with
the intended graph, and connected to verification evidence.

## Success characteristics

Codegraph is succeeding when:

- a returning engineer can recover the intent and current state of a component
  without reconstructing it from chat history;
- an LLM reuses or updates existing artifacts instead of recreating equivalents;
- a requirement can be traversed to its design, implementation, tests, and
  latest evidence;
- generated code can be indexed back into the graph without losing identity or
  intent;
- stale, missing, conflicting, or unexpected artifacts are visible;
- the explorer helps an engineer understand and act without overwhelming them.

## Non-goals

Codegraph is not intended to:

- replace source control or make the datastore the only copy of authored work;
- treat generated documentation as correct without reconciliation;
- remove human review from architectural or product decisions;
- maximize the amount of code or prose an LLM can generate;
- preserve unrestricted conversational history as undifferentiated memory.

