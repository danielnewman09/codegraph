# In-process indexing

Codegraph owns the active implementation in `src/codegraph_index`. The public
boundary is:

```python
from codegraph_index import IndexRequest, IndexService

result = IndexService().index(request)
```

`IndexRequest` is immutable and carries explicit project/repository scope.
`IndexService` selects one registered language adapter, returns a backend-
neutral `LayerGraph`, computes deterministic `IndexDelta` change sets, and
can persist through an injected `RepositoryPersistence`. `EXTRACT_ONLY` never
calls persistence. Diagnostics are structured `IndexDiagnostic` values; the
service does not print, exit, parse CLI text, or invoke a subprocess.

The long-term scope authority is a `.codegraph-project.toml` manifest:

```toml
[project]
id = "my-project"

[[repositories]]
name = "main"
path = "."
```

Library callers can use `request_from_project_config()` to translate a legacy
project config while resolving IDs from that manifest. The `codegraph-index
project` command remains the CLI compatibility surface and the
`doxygen-index` command delegates to the same implementation.

The Python adapter uses the AST parser in-process. The C++ adapter is the only
place that coordinates Doxygen availability/generation. Doxygen and Conan are
host executables checked at adapter selection time; they are not imported by
the core library. Conan discovery, cppreference, and enrichment remain
optional capabilities; install `codegraph[index-cppreference]` or
`codegraph[enrich]` as needed.
`.doxygen-index.toml` remains accepted
by the compatibility CLI, while `.codegraph-project.toml` supplies long-term
project/repository scope.

The historical `Doxygen-Dependency-Parser` distribution may provide
compatibility imports and a `doxygen-index` wrapper, but Codegraph neither
depends on nor tests against that distribution. Codegraph owns the active
implementation and its behavioral fixtures.
