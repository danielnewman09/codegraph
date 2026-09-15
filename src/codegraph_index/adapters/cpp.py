"""C++/Doxygen extraction adapter."""

from __future__ import annotations

import shutil
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


class CppExtractionAdapter:
    """Adapt Doxygen XML generation and parsing without persistence."""

    name = "cpp-doxygen"
    version = "1"
    languages = frozenset({"cpp", "c++", "c"})

    def available(self, request: IndexRequest) -> Availability:
        xml_dir = request.adapter_options.get("xml_dir")
        if xml_dir:
            return Availability(True)
        if shutil.which("doxygen"):
            return Availability(True)
        return Availability(
            False,
            (
                IndexDiagnostic(
                    code="DOXYGEN_UNAVAILABLE",
                    severity=Severity.ERROR,
                    message="doxygen is not available; provide adapter_options['xml_dir'] or install Doxygen",
                    adapter=self.name,
                ),
            ),
        )

    def extract(self, request: IndexRequest) -> ExtractionResult:
        from codegraph_index.graph_json import result_to_graph_json
        from codegraph_index.parser import parse_xml_dir

        xml_dir = request.adapter_options.get("xml_dir")
        artifacts: list[Path] = []
        if xml_dir:
            xml_path = Path(xml_dir)
        else:
            from codegraph_index.doxygen import run_doxygen

            output_base = request.output_dir or request.project_root / "build" / "docs"
            with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                xml_path = run_doxygen(
                    name=request.source,
                    input_paths=list(request.input_paths),
                    output_base=output_base,
                    predefined=" ".join(request.predefined),
                    file_patterns=" ".join(request.file_patterns)
                    or "*.h *.hpp *.hxx *.cpp *.cxx *.cc",
                    exclude_patterns=" ".join(request.exclude_patterns),
                    xml_subdir="xml",
                    test_source_dirs=list(request.test_paths) or None,
                )
            if xml_path is None:
                return ExtractionResult(
                    graph=_empty_graph(),
                    diagnostics=(
                        IndexDiagnostic(
                            code="DOXYGEN_FAILED",
                            severity=Severity.ERROR,
                            message="Doxygen did not produce an XML directory",
                            adapter=self.name,
                        ),
                    ),
                )
            artifacts.append(Path(xml_path))

        with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
            result = parse_xml_dir(
                xml_path,
                source=request.source,
                layer=str(request.adapter_options.get("layer", "codebase")),
                progress_interval=int(request.adapter_options.get("progress_interval", 0)),
                test_source_dirs=list(request.test_paths) or None,
            )
            _normalize_source_paths(result, request.project_root)
            _complete_cpp_resolution(result)
            entries = result_to_graph_json(
                result,
                source=request.source,
                text_scan=bool(
                    request.adapter_options.get("text_scan", request.emit_json)
                ),
                identity_scope=_identity_scope(request),
            )
        from codegraph.graph import LayerGraph

        return ExtractionResult(
            graph=LayerGraph.deserialize(entries, create_missing=False),
            artifacts=tuple(artifacts),
        )


def _empty_graph():
    from codegraph.graph import LayerGraph

    return LayerGraph(tags=frozenset({"as-built"}))


def _normalize_source_paths(result, project_root: Path) -> None:
    """Make Doxygen paths portable relative to the indexed project root."""
    root = project_root.resolve()
    for value in vars(result).values():
        if not isinstance(value, list):
            continue
        for node in value:
            for attribute in ("file_path", "body_file", "path"):
                raw = getattr(node, attribute, None)
                if not isinstance(raw, str) or not raw:
                    continue
                candidate = Path(raw)
                if not candidate.is_absolute():
                    candidate = Path.cwd() / candidate
                candidate = candidate.resolve()
                try:
                    relative = candidate.relative_to(root)
                except ValueError:
                    continue
                setattr(node, attribute, relative.as_posix())
            if type(node).__name__ == "SourceFragmentNode":
                file_path = getattr(node, "file_path", "") or ""
                start_line = getattr(node, "start_line", 0) or 0
                end_line = getattr(node, "end_line", 0) or 0
                if file_path and start_line and end_line:
                    # The parser uses an absolute-path locator as the
                    # display qualified name.  It is not identity data, but
                    # retaining it would make otherwise identical temporary
                    # project roots compare as graph drift.
                    setattr(
                        node,
                        "qualified_name",
                        f"{file_path}#{start_line}-{end_line}",
                    )


def _complete_cpp_resolution(result) -> None:
    """Apply the deterministic post-parse resolution used by the CLI.

    ``parse_xml_dir`` performs parser-local post-processing.  The historical
    full-ingestion command then ran the cross-result passes once more after
    all XML sources had been assembled.  Keeping those passes in the adapter
    makes the public in-process ``index()`` contract produce the same graph
    shape as the compatibility CLI, including namespace dependencies and
    compositions.
    """
    from codegraph_index.doxygen import resolve_namespace_type_deps
    from codegraph_index.graph_json import sort_parse_result
    from codegraph_index.parser.cpp_parser import (
        _derive_namespace_compositions,
        _resolve_concept_constraints,
    )

    sort_parse_result(result)
    _resolve_concept_constraints(result)
    resolve_namespace_type_deps(result)
    result.compositions.clear()
    _derive_namespace_compositions(result)


def _identity_scope(request: IndexRequest):
    from codegraph.identity import IdentityScope

    return IdentityScope.repository(request.project_id, request.repository_id)
