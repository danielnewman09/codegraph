"""In-process Python AST extraction adapter."""

from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path

from codegraph_index.contracts import (
    Availability,
    ExtractionResult,
    IndexDiagnostic,
    IndexRequest,
    Severity,
)


class PythonExtractionAdapter:
    """Adapt the migrated Python parser to the indexing service contract."""

    name = "python-ast"
    version = "1"
    languages = frozenset({"python", "py"})

    def available(self, request: IndexRequest) -> Availability:
        del request
        return Availability(True)

    def extract(self, request: IndexRequest) -> ExtractionResult:
        from codegraph_index.graph_json import result_to_graph_json
        from codegraph_index.parser import parse_python_dir

        paths = list(request.input_paths)
        for path in request.test_paths:
            if path not in paths:
                paths.append(path)
        configured_excludes = request.adapter_options.get("exclude_dirs", ())
        excludes = tuple(configured_excludes) + tuple(request.exclude_patterns)
        with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
            result = parse_python_dir(
                paths,
                source=request.source,
                layer="codebase",
                exclude_dirs=list(dict.fromkeys(excludes)) if excludes else None,
                progress_interval=int(request.adapter_options.get("progress_interval", 0)),
            )
            entries = result_to_graph_json(
                result,
                source=request.source,
                text_scan=bool(
                    request.adapter_options.get("text_scan", request.emit_json)
                ),
                identity_scope=_identity_scope(request),
            )
        from codegraph.graph import LayerGraph

        graph = LayerGraph.deserialize(entries, create_missing=False)
        return ExtractionResult(
            graph=graph,
            diagnostics=(),
            artifacts=tuple(
                Path(path)
                for path in request.adapter_options.get("artifacts", ())
            ),
        )


def _identity_scope(request: IndexRequest):
    from codegraph.identity import IdentityScope

    return IdentityScope.repository(request.project_id, request.repository_id)
