# AGENTS.md

## Codebase exploration

This repository is indexed in a codegraph knowledge graph (Neo4j). The
`codegraph_query` and `codegraph_explore` tools retrieve structured graph
context (classes, members, call graphs, inheritance, namespaces) that is
far richer than grepping source.

- For structure / relationships / call graphs / inheritance / "who calls X":
  call `codegraph_explore` (action: search/compound/member/callers_callees/
  inheritance) and `codegraph_query` (scope: neighborhood, format: markdown)
  BEFORE reading source files.
- Use `read`/`grep` for exact file contents / text-level detail after you have
  the graph context, not as the first move for understanding architecture.
- `codegraph_query` format: html renders an interactive neighborhood graph.
- The `as-built` tag holds the indexed source; dependency/design/scaffold may
  be empty.
