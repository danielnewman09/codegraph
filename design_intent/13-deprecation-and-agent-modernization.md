# Deprecation and Agent Modernization

**Status:** Approved direction and current inventory  
**Established:** 2026-08-15

## Purpose

Codegraph should actively remove functionality that is superseded, unused, or
inconsistent with the intended workspace. Removal decisions should be grounded
in public entry points, internal consumers, tests, persisted data, and an
identified replacement—not only in whether code appears old.

### `DI-DEP-001` — Every subsystem has an owner and purpose

A maintained subsystem should serve a current product outcome, have an explicit
architectural home, and be covered by tests that prove behavior still needed by
the intended workflow.

### `DI-DEP-002` — Replacement evidence precedes removal

Live behavior should be removed only after its required capabilities are
covered by a replacement or deliberately retired. Compatibility code should
have a named consumer and an expiration condition.

### `DI-DEP-003` — Remove complete surfaces

When a feature is retired, remove its public exports, CLI commands,
configuration, implementation, templates, tests, examples, and current-user
documentation together. Historical design records may remain clearly marked as
historical.

### `DI-DEP-004` — Tests do not justify obsolete behavior

A large test suite demonstrates implementation investment, not continued
product value. Tests dedicated only to retired behavior should be removed with
that behavior.

### `DI-DEP-005` — Domain services outlive agent runtimes

Graph queries, validation, persistence, reconciliation, and artifact generation
should be reusable domain services. Agent frameworks orchestrate these services
but should not become the only place their behavior can be called or tested.

## Approved removal: static HTML export

The `codegraph.export.viz` static Cytoscape HTML exporter and its associated
public functionality are approved for removal. The Codegraph explorer is the
intended interactive dashboard and is explicitly implemented independently.

### `DI-RMV-001` — Remove HTML export

Remove the following current surfaces as one change:

- `codegraph.export.viz` and the HTML template it exclusively uses;
- `export_html` and `export_html_from_json` public APIs;
- the `codegraph-html` console script;
- `python -m codegraph viz` dispatch;
- `[codegraph-html]` configuration handling used only by the exporter;
- exporter-specific README instructions and runnable examples;
- tests whose only contract is static HTML generation, styling, configuration,
  or browser rendering of that export.

### `DI-RMV-002` — Preserve non-HTML capabilities deliberately

Do not remove PlantUML, Markdown, JSON, the explorer, or general graph
transformations solely because they were mentioned as visualization. If a
helper inside `export.viz` has a current non-HTML consumer, move that helper to
the consumer's proper subsystem and retain only its relevant tests.

### Current removal inventory

The inspected surface includes:

- the `codegraph-html` entry point in `pyproject.toml`;
- the `viz` module command in `codegraph.__main__`;
- public exports from `codegraph` and `codegraph.export`;
- five source modules under `codegraph/export/viz`;
- `codegraph/export/templates/graph.html.j2`;
- HTML-specific examples and the README section;
- visualization unit/integration and browser screenshot tests;
- fallback parsing of `[codegraph-html]` in persistence configuration.

References in historical plans and specifications should be annotated as
superseded when necessary, not rewritten as if the historical decision never
occurred.

## Target agent architecture

`codegraph_agents` is the target home for stateful agent workflows. LangGraph
provides workflow state, checkpointing, routing, and human interruption;
LangChain message, prompt, tool, and model interfaces provide the integration
contract.

### `DI-AGT-001` — One agent lifecycle

Stateful Codegraph agents should share one lifecycle for context loading,
message state, tool dispatch, checkpointing, usage reporting, errors,
interruption, resumption, and structured results.

### `DI-AGT-002` — One model invocation abstraction

Agent workflows should not separately depend on `llm_caller`, direct OpenAI
calls, and LangChain model interfaces. The target runtime should have one
provider-neutral model invocation boundary with injectable test doubles.

### `DI-AGT-003` — LangGraph state records workflow progress

Long-running workflows should express phases and resumable state in the graph
rather than burying control flow in an uncheckpointed tool loop.

### `DI-AGT-004` — Context is supplied through shared providers

Requirements, design, as-built code, tests, memories, and drift findings should
be loaded through the common context-provider contract and recorded as run
inputs where provenance matters.

### `DI-AGT-005` — Agent results enter reconciliation

An agent run should return structured proposed artifacts, input provenance, tool
effects, diagnostics, and verification results suitable for indexing and
feature-level reconciliation.

### `DI-AGT-006` — Legacy packages become temporary adapters

During migration, legacy entry points may delegate to new agents or extracted
domain services. They should not contain a second active orchestration
implementation after parity is established.

## Current agent inventory

### Target-generation implementation

- `codegraph_agents.BaseAgent` builds a LangGraph state machine with
  checkpointing and shared context/callback infrastructure.
- `codegraph_agents.design.DesignAgent` is implemented and has extensive unit
  coverage plus a pipeline test.
- `codegraph_agents.requirements_lint.RequirementsLintAgent` is implemented on
  the new framework.

### Incomplete migration seams

- `DesignAgent` still imports legacy design dispatchers, prompt-section
  builders, reconciliation, verification persistence, and artifact functions.
- `DesignAgent` contains two `__init__` definitions; the second silently
  replaces the first and narrows the annotated path type.
- the base runtime uses LangChain/LangGraph state but converts messages and tools
  to a direct OpenAI client call rather than using a single LangChain chat-model
  interface;
- `codegraph_agents.decompose` and `codegraph_agents.feedback` are placeholders.

### Legacy live workflows

- `codegraph_design.agents.decompose_hlr` uses `llm_caller.call_tool_loop`;
- `codegraph_design.agents.design_oo` retains the old design tool loop;
- `codegraph_feedback.agents.analyze_feedback` uses the old tool loop;
- `codegraph_enrich` uses `llm_caller.call_text`;
- `codegraph_mine` uses `call_text` and `call_tool_loop`;
- the `enrich` and `design` optional dependency groups still install
  `llm-caller`.

Mining and enrichment may not each require a stateful LangGraph agent. They do,
however, need to use the same provider-neutral model client, context,
provenance, and structured-result conventions. A one-shot model operation
should not be forced into an agent loop solely for uniform naming.

## Prioritized removal and migration sequence

### Priority 0 — Remove the approved HTML surface

This is low architectural risk and immediately reduces public API,
configuration, documentation, dependencies on remote browser assets, and test
maintenance. Run the non-visualization suite afterward to catch accidental
imports.

### Priority 1 — Stabilize the target agent foundation

Before porting more workflows:

1. select the provider-neutral LangChain chat-model/tool invocation contract;
2. remove the direct-OpenAI versus LangChain split from `BaseAgent`;
3. fix the duplicate `DesignAgent.__init__` definition;
4. define durable run identity, checkpoint storage, usage, interruption, and
   structured error contracts;
5. add requirements, tests, memory, and drift to shared context providers.

### Priority 2 — Finish the design-agent vertical slice

Move reusable dispatchers, prompt helpers, reconciliation, persistence, and
artifact functions out of the legacy agent module into framework-neutral domain
services. Make the LangGraph `DesignAgent` the sole orchestration path, then run
its unit, pipeline, persistence, and `cpp-sqlite` golden tests.

Only after this step should the old `design_hlr` tool loop be removed.

### Priority 3 — Migrate decompose and feedback agents

Implement `DecomposeAgent` and `FeedbackAgent` on the stabilized base, preserving
their validation, persistence, memory proposal, and engineer-review behavior.
Keep compatibility functions as thin delegators during the transition.

Feedback migration should align with the feature drift workflow so design
iterations create scoped memories and consequential decisions can interrupt for
engineer input.

### Priority 4 — Migrate mining and enrichment model access

Move `codegraph_mine` and `codegraph_enrich` away from `llm_caller` to the shared
model invocation layer. Use LangGraph only where checkpointed multi-step state
adds value; retain simple services for bounded structured completion.

### Priority 5 — Delete legacy packages and dependency

After parity and downstream migration:

- remove obsolete legacy agent implementations and compatibility exports;
- remove placeholder or duplicate modules that gained no implementation;
- remove `llm-caller` imports and optional dependencies;
- remove environment variables and documentation specific to the old runtime;
- confirm no CLI, script, test, or external package imports legacy paths.

## Removal-candidate classification

Future stale-code reviews should classify each candidate as:

- **remove now:** approved, isolated, and without required consumers;
- **replace then remove:** live capability with an identified target;
- **extract then remove:** useful domain logic trapped in an obsolete subsystem;
- **compatibility with deadline:** temporary public adapter with known consumers;
- **retain:** serves current intent and has an appropriate architectural home;
- **unknown:** usage or persistence impact must be measured before action.

## Acceptance criteria

- Static HTML export has no public entry point, implementation, template,
  exporter-only configuration, example, or active test remaining.
- The explorer and non-HTML exports continue to work.
- All stateful agents use the common LangGraph lifecycle.
- All model calls use one injectable, provider-neutral boundary.
- Design, decomposition, feedback, mining, and enrichment have no
  `llm_caller` imports.
- Legacy paths are either removed or documented thin compatibility adapters.
- Agent runs consume indexed requirements, tests, memories, and drift context
  and emit structured outputs suitable for reconciliation.

