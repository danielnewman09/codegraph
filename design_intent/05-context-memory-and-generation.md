# LLM Context, Memory, and Generation

**Status:** Living intent  
**Established:** 2026-08-15

### `DI-CTX-001` — Graph-selected context

LLM context should be assembled from the target task and graph neighborhood,
including the relevant intent, requirements, design, implementation, tests,
dependencies, decisions, and current synchronization findings.

### `DI-CTX-002` — Smallest sufficient context

Context construction should optimize for sufficiency and relevance rather than
maximum volume. Selection rules and omissions should be inspectable when they
could affect the result.

### `DI-CTX-003` — Discover before generate

Before creating an artifact, the system should search for existing identities,
equivalent responsibilities, prior generation results, and applicable memories.

### `DI-MEM-001` — Durable, structured memory

Memory should preserve engineering knowledge that must survive sessions, such
as architectural constraints, conventions, user corrections, rejected
alternatives, known failure modes, and unresolved uncertainties.

### `DI-MEM-002` — Scoped memory

A memory should carry provenance, scope, status, and relationships to affected
artifacts. Retrieval should be based on relevance to the generation target, not
recency alone.

### `DI-MEM-003` — Memory lifecycle

Memories may be active, superseded, contradicted, or resolved. Newer memory
should not silently erase older rationale when that rationale is needed to
understand a decision.

### `DI-MEM-004` — Design iteration produces scoped learning

When implementation or verification reveals that a design must be iterated,
the resulting insight is a strong candidate for durable memory. The memory
should be associated with the specific design entity, assumption, requirement,
or constraint it qualifies rather than stored only as a general project note.

### `DI-GEN-001` — Intent-preserving generation

A generation plan should identify the requirements, decisions, constraints,
graph entities, and tests it intends to realize before rendering code.

### `DI-GEN-002` — Change existing artifacts deliberately

When a corresponding artifact already exists, generation should propose a
targeted update or explicitly justify replacement. It should not regenerate an
equivalent parallel artifact by default.

### `DI-GEN-003` — Generated ownership and provenance

Generated output should be distinguishable from handwritten output without
making manual evolution unsafe. The graph should retain the generation input,
template or strategy, and subsequent reconciliation state.

### `DI-GEN-004` — Tests participate in generation

Test intent and existing verification evidence should inform generation.
Generated implementation and tests should be planned as a coherent change,
then independently indexed and reconciled.
