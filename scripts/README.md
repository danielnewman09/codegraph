# Scripts

Utility scripts for the codegraph project. Grouped by workflow.

---

## Design Document Pipeline

Tools for creating, ingesting, and verifying design-layer documents in Neo4j.

### `ingest_design.py`

Ingests a design or test Markdown file into the Neo4j codegraph. Accepts a single `.md` file path, imports it via `MarkdownImporter`, and persists all nodes and relationships via `LayerGraph.to_neo4j()`. Supports cross-document references (e.g., tests referencing design LLRs from a separate file) via Neo4j lookup at persist time.

```bash
python scripts/ingest_design.py codegraph/requirements/architecture_diagram_tool_design.md
```

### `verify_callee_granularity.py`

Audits every `CALLEE` edge from test steps to design elements, verifying that method-level calls target `MethodNode` (not `ClassNode`) and function-level calls target `FunctionNode`. Exit code 0 = all correct, 1 = issues found. Run after any test or design update to catch granularity regressions.

```bash
python scripts/verify_callee_granularity.py
```

---

## Document Generation

Deterministic markdown documents generated from the Neo4j graph. All output goes to `codegraph/requirements/generated/`. No LLM enrichment.

### `generate_hlr_docs.py`

Generates one markdown file per HLR showing the full requirement → test → design stack. Each file includes LLR descriptions, test descriptions with step breakdowns, and a summary of all design elements (methods/functions) exercised by the tests under that HLR.

```bash
python scripts/generate_hlr_docs.py
# → generated/hlr_docs/{01..04}_*.md
```

### `generate_hlr_feedback_docs.py`

Generates per-HLR feedback documents with blank `### Feedback` sections under each LLR. Designed for the iterative requirements review cycle:

1. **Export** — generates fresh docs with blank feedback sections
2. **Review** — human/agent writes comments under each LLR
3. **Update** — agent modifies Neo4j design nodes based on feedback
4. **Archive & re-export** — old feedback moved to `archive/{timestamp}/`, fresh docs regenerated
5. **Repeat**

```bash
python scripts/generate_hlr_feedback_docs.py
# → generated/feedback_docs/{01..04}_*.md
# → previous feedback archived to generated/feedback_docs/archive/
```

### `generate_requirement_docs.py`

Finalizes the full requirement document set from chain output. Takes the design + tests markdown produced by the `decompose-hlr` agent (via the `design-workflow` chain) and generates the complete document set: authored design/tests markdown, discovery context, and all generated artifacts (coverage report, HLR docs, feedback docs). After generating, ingests into Neo4j and runs verification scripts.

```bash
# From chain output (with ---DESIGN---/---TESTS--- delimiters)
python scripts/generate_requirement_docs.py --feature "my_feature" \
    --chain-output /path/to/chain_result.md --context-doc /path/to/context.md

# From separate files
python scripts/generate_requirement_docs.py --feature "my_feature" \
    --design-doc design.md --tests-doc tests.md --context-doc context.md

# Documents only, skip Neo4j ingestion
python scripts/generate_requirement_docs.py --feature "my_feature" \
    --design-doc design.md --tests-doc tests.md --skip-ingest
```

---

## Coverage Evaluation

### `evaluate_design_coverage.py`

Queries Neo4j for all `MethodNode`/`FunctionNode` instances tagged `design`, counts `CALLEE` edges from test steps, and produces a deterministic JSON report. Flags uncovered public methods as **design smells** (potential API leaks, not just coverage gaps). Accepts `--json` for JSON output.

```bash
python scripts/evaluate_design_coverage.py
python scripts/evaluate_design_coverage.py --json codegraph/requirements/generated/coverage_report.json
```

---

## Enrichment & Data Management

Pre-existing scripts for loading, enriching, and serializing codegraph data.

### `load_api_to_neo4j.py`

Extracts codegraph API metadata via Sphinx (`sphinx-build -b json_api`) and persists it to Neo4j. Used to populate API-level metadata (docstrings, signatures) from the codebase into the graph.

### `reingest_enrichment.py`

Re-ingests LLM-enriched test descriptions from previous enrichment logs. Reads `_response.md` files from `codegraph/logs/` produced by a prior `codegraph-enrich --all` run, parses the description JSON, and writes it back to Neo4j.

### `serialize_requirements_to_markdown.py`

Serializes requirements (Component, HLR, LLR) from Neo4j to Markdown. Queries Neo4j for all Component/HLR/LLR nodes, builds a `LayerGraph` from their `COMPOSES` hierarchy, and exports it to a Markdown document in codegraph's ingestion format.

### `write_test_descriptions_from_graph.py`

One-time script: writes enriched test descriptions from Neo4j back into test source files. Reads the `description` property from Test/TestStep/TestFixture/Assertion nodes in the graph and injects them into the corresponding Python test source.

---

## Quick Reference

| I want to... | Run |
|---|---|
| Ingest a new design | `python scripts/ingest_design.py path/to/design.md` |
| Check CALLEE edge accuracy | `python scripts/verify_callee_granularity.py` |
| See the full per-HLR stack | `python scripts/generate_hlr_docs.py` |
| Review requirements with feedback | `python scripts/generate_hlr_feedback_docs.py` |
| Evaluate test coverage | `python scripts/evaluate_design_coverage.py` |
| Regenerate everything | See pipeline below |
| Finalize docs from chain output | `python scripts/generate_requirement_docs.py --feature ...` |

**Full regeneration pipeline:**

```bash
# 1. Ingest authored docs into Neo4j
python scripts/ingest_design.py codegraph/requirements/architecture_diagram_tool_design.md
python scripts/ingest_design.py codegraph/requirements/architecture_diagram_tool_tests.md

# 2. Generate deterministic output from Neo4j
python scripts/evaluate_design_coverage.py --json codegraph/requirements/generated/coverage_report.json
python scripts/generate_hlr_docs.py
python scripts/generate_hlr_feedback_docs.py

# 3. Verify integrity
python scripts/verify_callee_granularity.py
```

**Design workflow pipeline (chain → finalize):**

```bash
# 1. Run the design-workflow chain (discover → decompose → review)
#    via Pi: subagent chain code-analysis.design-workflow, task: "feature description"

# 2. Finalize the chain output into the full document set
python scripts/generate_requirement_docs.py \
    --feature "my_feature" \
    --chain-output /path/to/chain_result.md \
    --context-doc /path/to/discovery_context.md
```
