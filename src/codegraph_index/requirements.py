"""Repository-authoritative requirements ingestion for unified indexing."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from codegraph.graph import LayerGraph
from codegraph_index.contracts import IndexDiagnostic, IndexRequest, Severity

AUTHORITATIVE_REQUIREMENTS_FILENAME = "requirements.md"
_LEGACY_SHA1_REFERENCE = re.compile(r"^[0-9a-f]{40}$")


@dataclass(frozen=True, slots=True)
class RequirementsLoadResult:
    """Requirements graph plus deterministic structured diagnostics."""

    graph: LayerGraph
    diagnostics: tuple[IndexDiagnostic, ...] = ()
    files: tuple[Path, ...] = ()


def _entries(graph: LayerGraph):
    for root in graph.entries.values():
        yield from LayerGraph._walk_entries(root)


def _content_fingerprint(node) -> str:
    data = node.serialize(fields="all")
    for field in ("uid", "canonical_key", "element_id"):
        data.pop(field, None)
    return json.dumps(data, sort_keys=True, default=str, separators=(",", ":"))


def _add_requirements_tag(graph: LayerGraph) -> None:
    for entry in _entries(graph):
        tags = list(getattr(entry.node, "tags", ()) or ())
        if "requirements" not in tags:
            entry.node.tags = [*tags, "requirements"]


def _resolve_reference_keys(graph: LayerGraph) -> tuple[IndexDiagnostic, ...]:
    """Replace importer qname references with canonical graph keys."""
    by_qname: dict[str, list[object]] = {}
    by_bare_name: dict[str, list[object]] = {}
    by_canonical: dict[str, list[object]] = {}
    for entry in _entries(graph):
        node = entry.node
        qname = getattr(node, "qualified_name", "") or ""
        name = getattr(node, "name", "") or ""
        canonical = getattr(node, "canonical_key", "") or ""
        if qname:
            by_qname.setdefault(qname, []).append(entry)
        if name:
            by_bare_name.setdefault(name, []).append(entry)
        if canonical:
            by_canonical.setdefault(canonical, []).append(entry)

    diagnostics: list[IndexDiagnostic] = []
    for entry in _entries(graph):
        resolved = []
        for relation_type, target, target_type in entry.references:
            if target.startswith("cg:v1:"):
                # A canonical key is already the storage identity, but it is
                # only a valid edge if the endpoint actually exists in the
                # graph.  Persisting a syntactically valid key for a missing
                # node silently stores nothing (the backend cannot join the
                # endpoint), so reject it the same way an unresolved qname is
                # rejected rather than reporting a phantom relationship.
                candidates = by_canonical.get(target, [])
                if not candidates:
                    diagnostics.append(
                        IndexDiagnostic(
                            code="UNRESOLVED_REQUIREMENT_REFERENCE",
                            severity=Severity.ERROR,
                            message=(
                                f"{getattr(entry.node, 'qualified_name', entry.node.name)!r} "
                                f"has {relation_type} canonical target {target!r} "
                                "that matches no graph entity; the unresolved "
                                "edge was omitted"
                            ),
                            adapter="requirements-markdown",
                        )
                    )
                    continue
                target_node = candidates[0].node
                resolved.append(
                    (
                        relation_type,
                        target,
                        target_type or type(target_node).__name__,
                    )
                )
                continue
            # A qualified-name match is authoritative. Bare names are only a
            # fallback; otherwise a code literal named ``literal::true`` can
            # incorrectly compete with the requirement literal whose actual
            # qualified name is ``literal::true``.
            candidates = by_qname.get(target, []) or by_bare_name.get(target, [])
            if target_type:
                candidates = [
                    candidate
                    for candidate in candidates
                    if type(candidate.node).__name__ == target_type
                ]
            # Code extraction and requirements documents can independently
            # materialize the same logical literal/operand. Treat repeated
            # placements of one canonical entity as one resolution target.
            candidates = list(
                {
                    candidate.node.canonical_key: candidate for candidate in candidates
                }.values()
            )
            if len(candidates) != 1:
                legacy = not candidates and bool(
                    _LEGACY_SHA1_REFERENCE.fullmatch(target)
                )
                code = (
                    "LEGACY_REQUIREMENT_REFERENCE_DROPPED"
                    if legacy
                    else (
                        "AMBIGUOUS_REQUIREMENT_REFERENCE"
                        if candidates
                        else "UNRESOLVED_REQUIREMENT_REFERENCE"
                    )
                )
                diagnostics.append(
                    IndexDiagnostic(
                        code=code,
                        severity=Severity.WARNING if legacy else Severity.ERROR,
                        message=(
                            f"{getattr(entry.node, 'qualified_name', entry.node.name)!r} "
                            f"has {relation_type} target {target!r} with "
                            f"{len(candidates)} matching graph entities; "
                            "the unresolved edge was omitted"
                        ),
                        adapter="requirements-markdown",
                    )
                )
                continue
            target_node = candidates[0].node
            resolved.append(
                (
                    relation_type,
                    target_node.canonical_key,
                    target_type or type(target_node).__name__,
                )
            )
        entry.references = resolved
    return tuple(diagnostics)


def load_requirements(
    request: IndexRequest,
    *,
    base_graph: LayerGraph | None = None,
) -> RequirementsLoadResult:
    """Load canonical ``requirements.md`` files configured for an index run.

    Other Markdown in the same tree is deliberately ignored: design drafts,
    feedback, lint reports, generated views, and archives are derived artifacts,
    not repository-authoritative requirements.
    """
    empty = LayerGraph(tags=frozenset({"requirements"}))
    if request.requirements_dir is None:
        return RequirementsLoadResult(empty)

    root = request.requirements_dir
    if not root.is_absolute():
        root = request.project_root / root
    root = root.resolve()
    if not root.is_dir():
        return RequirementsLoadResult(
            empty,
            (
                IndexDiagnostic(
                    code="REQUIREMENTS_DIRECTORY_NOT_FOUND",
                    severity=Severity.ERROR,
                    message=f"configured requirements directory does not exist: {root}",
                    adapter="requirements-markdown",
                ),
            ),
        )

    files = tuple(
        sorted(
            root.rglob(AUTHORITATIVE_REQUIREMENTS_FILENAME),
            key=lambda path: path.relative_to(root).as_posix(),
        )
    )
    if not files:
        return RequirementsLoadResult(
            empty,
            (
                IndexDiagnostic(
                    code="NO_REQUIREMENTS_DOCUMENTS",
                    severity=Severity.ERROR,
                    message=(
                        f"no {AUTHORITATIVE_REQUIREMENTS_FILENAME!r} files found "
                        f"under {root}"
                    ),
                    adapter="requirements-markdown",
                ),
            ),
        )

    from codegraph.export.markdown import MarkdownImporter
    from codegraph.export.plantuml import PlantUMLParseError
    from codegraph.identity import IdentityScope, identity_scope

    combined = LayerGraph(tags=frozenset({"requirements"}))
    diagnostics: list[IndexDiagnostic] = []
    identities: dict[str, tuple[str, Path]] = {}
    scope = IdentityScope.repository(request.project_id, request.repository_id)

    for path in files:
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            diagnostics.append(
                IndexDiagnostic(
                    code="REQUIREMENTS_READ_FAILED",
                    severity=Severity.ERROR,
                    message=f"cannot read {path}: {type(exc).__name__}: {exc}",
                    adapter="requirements-markdown",
                )
            )
            continue

        importer = MarkdownImporter(
            tags=frozenset({"requirements"}),
            source=request.source,
            strict=True,
        )
        try:
            with identity_scope(scope):
                document = importer.import_markdown(text)
        except PlantUMLParseError as exc:
            diagnostics.append(
                IndexDiagnostic(
                    code="MALFORMED_REQUIREMENTS_DOCUMENT",
                    severity=Severity.ERROR,
                    message=f"{path}: {exc}",
                    adapter="requirements-markdown",
                )
            )
            continue
        except Exception as exc:  # noqa: BLE001 - structured boundary diagnostic
            diagnostics.append(
                IndexDiagnostic(
                    code="REQUIREMENTS_IMPORT_FAILED",
                    severity=Severity.ERROR,
                    message=f"{path}: {type(exc).__name__}: {exc}",
                    adapter="requirements-markdown",
                )
            )
            continue

        document_entries = tuple(_entries(document))
        if not any(type(entry.node).__name__ == "HLR" for entry in document_entries):
            diagnostics.append(
                IndexDiagnostic(
                    code="REQUIREMENTS_DOCUMENT_HAS_NO_HLR",
                    severity=Severity.ERROR,
                    message=f"{path} contains no HLR heading",
                    adapter="requirements-markdown",
                )
            )
        _add_requirements_tag(document)
        for entry in document_entries:
            key = getattr(entry.node, "canonical_key", "") or ""
            fingerprint = _content_fingerprint(entry.node)
            previous = identities.get(key)
            if previous is not None:
                previous_fingerprint, previous_path = previous
                diagnostics.append(
                    IndexDiagnostic(
                        code=(
                            "DUPLICATE_REQUIREMENT_IDENTITY"
                            if previous_fingerprint == fingerprint
                            else "CONFLICTING_REQUIREMENT_IDENTITY"
                        ),
                        severity=Severity.ERROR,
                        message=(
                            f"canonical identity {key!r} occurs in both "
                            f"{previous_path} and {path}"
                        ),
                        adapter="requirements-markdown",
                    )
                )
            else:
                identities[key] = (fingerprint, path)
        combined.merge(document)

    if base_graph is not None:
        base_graph.merge(combined)
        base_graph.tags = base_graph.tags | combined.tags
        diagnostics.extend(_resolve_reference_keys(base_graph))
        result_graph = base_graph
    else:
        diagnostics.extend(_resolve_reference_keys(combined))
        result_graph = combined
    return RequirementsLoadResult(result_graph, tuple(diagnostics), files)
