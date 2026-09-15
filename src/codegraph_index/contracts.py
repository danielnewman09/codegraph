"""Immutable public contracts for in-process indexing.

The contract layer intentionally contains no parser, CLI, subprocess, or
optional-tool imports. It is safe for consumers to import while selecting an
adapter or reporting configuration errors.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping, Protocol, Sequence, TypeVar

from codegraph.graph import LayerGraph

__all__ = [
    "Availability",
    "ChangeSet",
    "EntityRef",
    "ExtractionAdapter",
    "ExtractionResult",
    "IndexDiagnostic",
    "IndexDelta",
    "IndexFinding",
    "IndexMode",
    "IndexPersistence",
    "IndexRequest",
    "IndexResult",
    "IndexServiceProtocol",
    "RelationshipRef",
    "Severity",
]


class IndexMode(str, Enum):
    """How an indexing request treats existing persisted source data."""

    INCREMENTAL = "incremental"
    REPLACE_SOURCE = "replace_source"
    EXTRACT_ONLY = "extract_only"


class Severity(str, Enum):
    """Severity of a structured indexing diagnostic."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


def _text(value: str, field_name: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    if not allow_empty and not value.strip():
        raise ValueError(f"{field_name} must not be empty")
    if value != value.strip():
        raise ValueError(f"{field_name} must not have leading/trailing whitespace")
    return value


def _paths(values: Sequence[Path] | Path | None, field_name: str) -> tuple[Path, ...]:
    if values is None:
        return ()
    if isinstance(values, (str, Path)):
        values = (Path(values),)
    result = tuple(Path(value) for value in values)
    if any(not str(value) for value in result):
        raise ValueError(f"{field_name} must contain only non-empty paths")
    return result


def _strings(values: Sequence[str] | str | None, field_name: str) -> tuple[str, ...]:
    if values is None:
        return ()
    if isinstance(values, str):
        values = (values,)
    return tuple(_text(value, field_name) for value in values)


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, set):
        return frozenset(_freeze(item) for item in value)
    return value


def _mapping(values: Mapping[str, Any] | None) -> Mapping[str, Any]:
    if values is None:
        return MappingProxyType({})
    if not isinstance(values, Mapping):
        raise TypeError("adapter_options must be a mapping")
    return MappingProxyType({key: _freeze(item) for key, item in values.items()})


@dataclass(frozen=True, slots=True)
class IndexRequest:
    """Normalized, immutable input to :class:`IndexService`."""

    project_root: Path
    project_id: str
    repository_id: str
    source: str
    language: str
    input_paths: tuple[Path, ...]
    test_paths: tuple[Path, ...] = ()
    output_dir: Path | None = None
    file_patterns: tuple[str, ...] = ()
    exclude_patterns: tuple[str, ...] = ()
    predefined: tuple[str, ...] = ()
    mode: IndexMode = IndexMode.INCREMENTAL
    emit_json: bool = False
    requirements_dir: Path | None = None
    adapter_options: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        root = Path(self.project_root)
        if not str(root):
            raise ValueError("project_root must not be empty")
        object.__setattr__(self, "project_root", root)
        object.__setattr__(self, "project_id", _text(self.project_id, "project_id"))
        object.__setattr__(
            self, "repository_id", _text(self.repository_id, "repository_id")
        )
        object.__setattr__(self, "source", _text(self.source, "source"))
        object.__setattr__(self, "language", _text(self.language, "language").lower())
        input_paths = _paths(self.input_paths, "input_paths")
        if not input_paths:
            raise ValueError("input_paths must contain at least one path")
        object.__setattr__(self, "input_paths", input_paths)
        object.__setattr__(self, "test_paths", _paths(self.test_paths, "test_paths"))
        if self.output_dir is not None:
            object.__setattr__(self, "output_dir", Path(self.output_dir))
        object.__setattr__(self, "file_patterns", _strings(self.file_patterns, "file_patterns"))
        object.__setattr__(self, "exclude_patterns", _strings(self.exclude_patterns, "exclude_patterns"))
        object.__setattr__(self, "predefined", _strings(self.predefined, "predefined"))
        object.__setattr__(self, "mode", IndexMode(self.mode))
        if not isinstance(self.emit_json, bool):
            raise TypeError("emit_json must be a bool")
        if self.requirements_dir is not None:
            object.__setattr__(self, "requirements_dir", Path(self.requirements_dir))
        object.__setattr__(self, "adapter_options", _mapping(self.adapter_options))


@dataclass(frozen=True, slots=True)
class EntityRef:
    """Canonical identity and fingerprint for one extracted entity."""

    canonical_key: str
    node_type: str
    source: str
    fingerprint: str = ""

    def __post_init__(self) -> None:
        for name in ("canonical_key", "node_type", "source"):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        object.__setattr__(
            self, "fingerprint", _text(self.fingerprint, "fingerprint", allow_empty=True)
        )


@dataclass(frozen=True, slots=True)
class RelationshipRef:
    """Canonical identity for one extracted relationship endpoint pair."""

    source_key: str
    relationship_type: str
    target_key: str

    def __post_init__(self) -> None:
        for name in ("source_key", "relationship_type", "target_key"):
            object.__setattr__(self, name, _text(getattr(self, name), name))


@dataclass(frozen=True, slots=True)
class IndexFinding:
    """Structured ambiguity or validation finding."""

    code: str
    canonical_keys: tuple[str, ...] = ()
    details: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "code", _text(self.code, "code"))
        object.__setattr__(self, "canonical_keys", _strings(self.canonical_keys, "canonical_keys"))
        object.__setattr__(self, "details", _mapping(self.details))


T = TypeVar("T")


def _ordered(values: Sequence[T]) -> tuple[T, ...]:
    """Return a deterministic tuple without requiring domain-specific types."""
    return tuple(sorted(values, key=repr))


@dataclass(frozen=True, slots=True)
class ChangeSet:
    """Deterministic entity or relationship change categories."""

    created: tuple[Any, ...] = ()
    matched: tuple[Any, ...] = ()
    changed: tuple[Any, ...] = ()
    deleted: tuple[Any, ...] = ()
    ambiguous: tuple[IndexFinding, ...] = ()

    def __post_init__(self) -> None:
        for name in ("created", "matched", "changed", "deleted"):
            object.__setattr__(self, name, _ordered(tuple(getattr(self, name))))
        ambiguous = tuple(self.ambiguous)
        if not all(isinstance(item, IndexFinding) for item in ambiguous):
            raise TypeError("ambiguous entries must be IndexFinding values")
        object.__setattr__(self, "ambiguous", _ordered(ambiguous))

    @property
    def is_empty(self) -> bool:
        return not any(
            (self.created, self.changed, self.deleted, self.ambiguous)
        )


@dataclass(frozen=True, slots=True)
class IndexDelta:
    """Entity and relationship reconciliation results."""

    entities: ChangeSet = field(default_factory=ChangeSet)
    relationships: ChangeSet = field(default_factory=ChangeSet)

    @property
    def is_empty(self) -> bool:
        return self.entities.is_empty and self.relationships.is_empty

    def summary(self) -> dict[str, int]:
        result: dict[str, int] = {}
        for prefix, change_set in (("entities", self.entities), ("relationships", self.relationships)):
            for name in ("created", "matched", "changed", "deleted", "ambiguous"):
                result[f"{prefix}_{name}"] = len(getattr(change_set, name))
        result["ambiguous"] = len(self.entities.ambiguous) + len(self.relationships.ambiguous)
        return result


@dataclass(frozen=True, slots=True)
class IndexDiagnostic:
    """Structured non-fatal or fatal indexing diagnostic."""

    code: str
    severity: Severity
    message: str
    adapter: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "code", _text(self.code, "code"))
        object.__setattr__(self, "severity", Severity(self.severity))
        object.__setattr__(self, "message", _text(self.message, "message"))
        object.__setattr__(self, "adapter", _text(self.adapter, "adapter", allow_empty=True))


@dataclass(frozen=True, slots=True)
class Availability:
    """Whether an adapter can process a request."""

    available: bool
    diagnostics: tuple[IndexDiagnostic, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.available, bool):
            raise TypeError("available must be a bool")
        diagnostics = tuple(self.diagnostics)
        if not all(isinstance(item, IndexDiagnostic) for item in diagnostics):
            raise TypeError("diagnostics must contain IndexDiagnostic values")
        object.__setattr__(self, "diagnostics", diagnostics)


@dataclass(frozen=True, slots=True)
class ExtractionResult:
    """Backend-neutral output from an extraction adapter."""

    graph: LayerGraph
    diagnostics: tuple[IndexDiagnostic, ...] = ()
    artifacts: tuple[Path, ...] = ()
    timings: Mapping[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.graph, LayerGraph):
            raise TypeError("graph must be a LayerGraph")
        object.__setattr__(self, "diagnostics", tuple(self.diagnostics))
        object.__setattr__(self, "artifacts", _paths(self.artifacts, "artifacts"))
        object.__setattr__(self, "timings", MappingProxyType(dict(self.timings)))


@dataclass(frozen=True, slots=True)
class IndexResult:
    """Complete structured result returned by the in-process service."""

    request: IndexRequest
    graph: LayerGraph
    delta: IndexDelta = field(default_factory=IndexDelta)
    diagnostics: tuple[IndexDiagnostic, ...] = ()
    artifacts: tuple[Path, ...] = ()
    timings: Mapping[str, float] = field(default_factory=dict)
    adapter_name: str = ""
    adapter_version: str = ""
    persisted: bool = False
    success: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.request, IndexRequest):
            raise TypeError("request must be an IndexRequest")
        if not isinstance(self.graph, LayerGraph):
            raise TypeError("graph must be a LayerGraph")
        object.__setattr__(self, "diagnostics", tuple(self.diagnostics))
        object.__setattr__(self, "artifacts", _paths(self.artifacts, "artifacts"))
        object.__setattr__(self, "timings", MappingProxyType(dict(self.timings)))
        object.__setattr__(self, "adapter_name", _text(self.adapter_name, "adapter_name", allow_empty=True))
        object.__setattr__(self, "adapter_version", _text(self.adapter_version, "adapter_version", allow_empty=True))
        if not isinstance(self.persisted, bool) or not isinstance(self.success, bool):
            raise TypeError("persisted and success must be bool values")


class ExtractionAdapter(Protocol):
    """Protocol implemented by language-specific extraction adapters."""

    name: str
    languages: frozenset[str]
    version: str

    def available(self, request: IndexRequest) -> Availability: ...

    def extract(self, request: IndexRequest) -> ExtractionResult: ...


class IndexPersistence(Protocol):
    """Persistence boundary consumed by the indexing service."""

    def inventory(self, source: str) -> Any: ...

    def apply(self, graph: LayerGraph, delta: IndexDelta) -> None: ...


class IndexServiceProtocol(Protocol):
    """Minimal protocol for service consumers and test doubles."""

    def index(self, request: IndexRequest) -> IndexResult: ...
