"""Backend-neutral indexing service and adapter registry."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from time import monotonic
from typing import Iterable, Sequence

from codegraph_index.contracts import (
    Availability,
    ChangeSet,
    ExtractionAdapter,
    IndexDiagnostic,
    IndexDelta,
    IndexFinding,
    IndexMode,
    IndexRequest,
    IndexResult,
    Severity,
)


def _empty_graph():
    from codegraph.graph import LayerGraph

    return LayerGraph(tags=frozenset({"as-built"}))


@dataclass
class AdapterRegistry:
    """Explicit registry for language extraction adapters."""

    adapters: tuple[ExtractionAdapter, ...] = ()

    def __post_init__(self) -> None:
        self.adapters = tuple(self.adapters)

    def register(self, adapter: ExtractionAdapter) -> None:
        if not getattr(adapter, "name", ""):
            raise ValueError("an extraction adapter must have a name")
        if any(existing.name == adapter.name for existing in self.adapters):
            raise ValueError(f"adapter {adapter.name!r} is already registered")
        self.adapters = (*self.adapters, adapter)

    def select(self, language: str) -> ExtractionAdapter | None:
        normalized = language.lower()
        matches = [adapter for adapter in self.adapters if normalized in adapter.languages]
        if len(matches) > 1:
            raise ValueError(
                f"multiple extraction adapters support language {language!r}: "
                + ", ".join(adapter.name for adapter in matches)
            )
        return matches[0] if matches else None


def default_registry() -> AdapterRegistry:
    from codegraph_index.adapters.cpp import CppExtractionAdapter
    from codegraph_index.adapters.python import PythonExtractionAdapter

    return AdapterRegistry((PythonExtractionAdapter(), CppExtractionAdapter()))


class IndexService:
    """Coordinate selection, extraction, reconciliation, and persistence."""

    def __init__(self, adapters: Iterable[ExtractionAdapter] | None = None, persistence=None):
        self.registry = AdapterRegistry(tuple(adapters)) if adapters is not None else default_registry()
        self.persistence = persistence

    def index(self, request: IndexRequest) -> IndexResult:
        started = monotonic()
        adapter = self.registry.select(request.language)
        if adapter is None:
            diagnostic = IndexDiagnostic(
                code="UNSUPPORTED_LANGUAGE",
                severity=Severity.ERROR,
                message=f"no extraction adapter is registered for {request.language!r}",
            )
            return IndexResult(
                request=request,
                graph=_empty_graph(),
                diagnostics=(diagnostic,),
                timings={"total": monotonic() - started},
                success=False,
            )

        availability = adapter.available(request)
        if not isinstance(availability, Availability):
            raise TypeError(f"adapter {adapter.name!r} returned an invalid Availability")
        if not availability.available:
            return IndexResult(
                request=request,
                graph=_empty_graph(),
                diagnostics=availability.diagnostics,
                adapter_name=adapter.name,
                adapter_version=getattr(adapter, "version", ""),
                timings={"total": monotonic() - started},
                success=False,
            )

        try:
            extraction = adapter.extract(request)
        except Exception as exc:
            diagnostic = IndexDiagnostic(
                code="EXTRACTION_FAILED",
                severity=Severity.ERROR,
                message=f"{type(exc).__name__}: {exc}",
                adapter=adapter.name,
            )
            return IndexResult(
                request=request,
                graph=_empty_graph(),
                diagnostics=(diagnostic,),
                adapter_name=adapter.name,
                adapter_version=getattr(adapter, "version", ""),
                timings={"total": monotonic() - started},
                success=False,
            )
        try:
            delta = self._delta_for(request, extraction.graph)
            if self.persistence is not None:
                from codegraph_index.inventory import delta_between, inventory_from_graph

                incoming = inventory_from_graph(extraction.graph, source=request.source)
                persisted = self.persistence.inventory(request.source)
                delta = delta_between(incoming, persisted)
        except Exception as exc:
            code = "AMBIGUOUS_IDENTITY" if "ambiguous" in str(exc).lower() else "INVALID_INVENTORY"
            finding = IndexFinding(
                code=code,
                details={"source": request.source, "error": str(exc)},
            )
            diagnostic = IndexDiagnostic(
                code=code,
                severity=Severity.ERROR,
                message=f"{type(exc).__name__}: {exc}",
                adapter=adapter.name,
            )
            delta = IndexDelta(
                entities=ChangeSet(ambiguous=(finding,)),
            )
            return IndexResult(
                request=request,
                graph=extraction.graph,
                delta=delta,
                diagnostics=(*extraction.diagnostics, diagnostic),
                artifacts=extraction.artifacts,
                timings={**dict(extraction.timings), "total": monotonic() - started},
                adapter_name=adapter.name,
                adapter_version=getattr(adapter, "version", ""),
                success=False,
            )
        diagnostics = tuple(extraction.diagnostics)
        artifacts = tuple(extraction.artifacts)
        if request.emit_json and request.output_dir is not None:
            output_dir = Path(request.output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)
            output_path = output_dir / f"{request.source}.json"
            output_path.write_text(
                json.dumps(
                    extraction.graph.serialize(document=True),
                    indent=2,
                    sort_keys=True,
                    default=str,
                )
                + "\n",
                encoding="utf-8",
            )
            artifacts = (*artifacts, output_path)
        persisted = False
        success = not any(item.severity is Severity.ERROR for item in diagnostics)

        if success and request.mode is not IndexMode.EXTRACT_ONLY and self.persistence is not None:
            try:
                self.persistence.apply(extraction.graph, delta)
            except Exception as exc:
                diagnostics += (
                    IndexDiagnostic(
                        code="PERSISTENCE_FAILED",
                        severity=Severity.ERROR,
                        message=f"{type(exc).__name__}: {exc}",
                        adapter=adapter.name,
                    ),
                )
                success = False
            else:
                persisted = True

        return IndexResult(
            request=request,
            graph=extraction.graph,
            delta=delta,
            diagnostics=diagnostics,
            artifacts=artifacts,
            timings={**dict(extraction.timings), "total": monotonic() - started},
            adapter_name=adapter.name,
            adapter_version=getattr(adapter, "version", ""),
            persisted=persisted,
            success=success,
        )

    @staticmethod
    def _delta_for(request: IndexRequest, graph) -> IndexDelta:
        """Build a deterministic extraction or reconciliation delta."""
        from codegraph_index.inventory import delta_from_graph

        return delta_from_graph(graph, source=request.source)


def index(request: IndexRequest, *, service: IndexService | None = None) -> IndexResult:
    """Index one request through a service instance."""
    return (service or IndexService()).index(request)
