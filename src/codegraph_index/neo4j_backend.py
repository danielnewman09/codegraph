"""Legacy persistence facade for the historical ``neo4j_backend`` name.

The active implementation is :mod:`codegraph_index.service` plus
:mod:`codegraph_index.persistence`. This module remains only because the
compatibility CLI and older callers pass a ``ParseResult`` directly. It does
not contain a backend writer or backend-specific query language.
"""

from __future__ import annotations

import re
import sys
import json
from collections import Counter, defaultdict
from dataclasses import dataclass, field, fields
from pathlib import Path
from time import perf_counter
from typing import Any

from codegraph import get_backend
from codegraph.graph import LayerGraph
from codegraph.identity import IdentityScope

from codegraph_index.graph_json import result_to_graph_json
from codegraph_index.inventory import Inventory, delta_between, inventory_from_graph
from codegraph_index.persistence import RepositoryPersistence
from codegraph_index.parser import ParseResult


class CanonicalReconciliationError(ValueError):
    """Compatibility error raised when a parsed result is unsafe to persist."""


@dataclass
class CanonicalInventory:
    """Compatibility view of the source inventory used by old callers."""

    entries: dict[str, Any] = field(default_factory=dict)
    by_source: dict[str, set[str]] = field(
        default_factory=lambda: defaultdict(set)
    )
    by_type: dict[str, set[str]] = field(
        default_factory=lambda: defaultdict(set)
    )

    def add(
        self,
        key: str,
        node_type: str,
        source: str,
        *,
        fingerprint: str = "",
        allow_identical_duplicate: bool = False,
    ) -> None:
        existing = self.entries.get(key)
        value = (node_type, source, fingerprint)
        if existing is not None:
            old = (
                getattr(existing, "node_type", existing[0]),
                getattr(existing, "source", existing[1]),
                getattr(existing, "fingerprint", existing[2]),
            )
            if not allow_identical_duplicate or old != value:
                raise CanonicalReconciliationError(
                    f"ambiguous canonical identity: {key!r} is claimed by "
                    f"{old[0]}/{old[1]} and {node_type}/{source}"
                )
            return
        self.entries[key] = value
        self.by_source[source].add(key)
        self.by_type[node_type].add(key)

    def keys_for_source(self, source: str) -> set[str]:
        return set(self.by_source.get(source, set()))

    def counts_for_keys(self, keys: set[str]) -> dict[str, int]:
        return dict(Counter(self.entries[key][0] for key in keys))


_AUTO_DESC_PATTERNS = (
    re.compile(r"^assert\s", re.IGNORECASE),
    re.compile(r"^Setup block$", re.IGNORECASE),
    re.compile(r"^Action block\s", re.IGNORECASE),
    re.compile(r"^$"),
)


def _is_placeholder_description(desc: str | None) -> bool:
    if not desc or not desc.strip():
        return True
    return any(pattern.match(desc) for pattern in _AUTO_DESC_PATTERNS)


def fetch_node_descriptions(
    qualified_names: list[str], *, include_placeholder: bool = False
) -> dict[str, str]:
    """Read descriptions through the active repository for compatibility."""
    if not qualified_names:
        return {}
    out: dict[str, str] = {}
    graph = get_backend().graph
    for qualified_name in qualified_names:
        try:
            node = graph.find_by_qualified_name(qualified_name)
        except Exception as exc:
            print(
                f"Warning: could not fetch descriptions from graph: {exc}",
                file=sys.stderr,
            )
            return out
        description = getattr(node, "description", "") if node else ""
        if description and (
            include_placeholder or not _is_placeholder_description(description)
        ):
            out.setdefault(qualified_name, description)
    return out


def _preserve_descriptions(*node_lists: list) -> None:
    candidates: dict[str, list] = {}
    for node_list in node_lists:
        for node in node_list:
            if _is_placeholder_description(getattr(node, "description", None)):
                qualified_name = getattr(node, "qualified_name", "")
                if qualified_name:
                    candidates.setdefault(qualified_name, []).append(node)
    if not candidates:
        return
    existing = fetch_node_descriptions(list(candidates))
    preserved = 0
    for qualified_name, nodes in candidates.items():
        description = existing.get(qualified_name)
        if description and not _is_placeholder_description(description):
            for node in nodes:
                node.description = description
                preserved += 1
    if preserved:
        print(f"  Preserved {preserved} enriched descriptions")


def _infer_source(result: ParseResult) -> str:
    counts: Counter[str] = Counter()
    for item in fields(result):
        value = getattr(result, item.name)
        if not isinstance(value, list):
            continue
        for node in value:
            source = getattr(node, "source", "") or ""
            if source:
                counts[source] += 1
    return counts.most_common(1)[0][0] if counts else ""


def _result_nodes(result: ParseResult):
    for item in fields(result):
        value = getattr(result, item.name)
        if isinstance(value, list):
            yield from value


def _validate_result(result: ParseResult, source: str) -> None:
    """Retain the old fail-safe checks at the compatibility boundary."""
    for parameter in result.parameters:
        if not getattr(parameter, "member_refid", ""):
            raise CanonicalReconciliationError(
                "ParameterNode has incomplete member_refid identity"
            )

    from codegraph.identity import resolve_identity_for
    from codegraph.models.descriptors import PropertyRegistry

    seen: dict[str, str] = {}
    for node in _result_nodes(result):
        node_source = getattr(node, "source", "") or source
        # Unified dependency parses deliberately retain independently-owned
        # ecosystems. Their repeated qnames are resolved by the parser's
        # source-aware bridge; strict duplicate rejection applies to the
        # source being updated, where ambiguity would make reconciliation
        # unsafe.
        if node_source != source:
            continue
        try:
            key = resolve_identity_for(
                node,
                IdentityScope.repository(source, node_source),
            ).key()
        except Exception:
            continue
        properties = PropertyRegistry.properties_of(type(node))
        payload = {
            name: getattr(node, name, None)
            for name in properties
            if name not in {
                "uid", "canonical_key", "element_id", "tags",
                "refid", "member_refid", "file_refid", "parent_refid",
            }
        }
        fingerprint = json.dumps(payload, sort_keys=True, default=str)
        previous = seen.get(key)
        if previous is not None and previous != fingerprint:
            raise CanonicalReconciliationError(
                f"distinct payloads share canonical key {key!r}"
            )
        seen[key] = fingerprint


def _normalized_data(result: ParseResult, source: str) -> list[dict]:
    _validate_result(result, source)
    try:
        return result_to_graph_json(
            result,
            source,
            text_scan=False,
        )
    except Exception as exc:
        raise CanonicalReconciliationError(str(exc)) from exc


def _graph_for_result(result: ParseResult, source: str) -> LayerGraph:
    return LayerGraph.deserialize(
        _normalized_data(result, source),
        create_missing=False,
    )


def _build_incoming_inventory(
    result: ParseResult,
    source: str,
) -> tuple[CanonicalInventory, list[dict]]:
    data = _normalized_data(result, source)
    graph = LayerGraph.deserialize(data, create_missing=False)
    inventory = inventory_from_graph(graph, source=source)
    compatibility = CanonicalInventory()
    for entry in inventory.entities.values():
        compatibility.add(
            entry.canonical_key,
            entry.node_type,
            entry.source,
            fingerprint=entry.fingerprint,
            allow_identical_duplicate=True,
        )
    return compatibility, data


def _build_persisted_inventory(source: str) -> CanonicalInventory:
    inventory = RepositoryPersistence(get_backend()).inventory(source)
    compatibility = CanonicalInventory()
    for entry in inventory.entities.values():
        compatibility.add(
            entry.canonical_key,
            entry.node_type,
            entry.source,
            fingerprint=entry.fingerprint,
            allow_identical_duplicate=True,
        )
    return compatibility


def _persist_result(
    result: ParseResult,
    source: str,
    *,
    timings: dict[str, float] | None = None,
) -> tuple[LayerGraph, object]:
    _preserve_descriptions(
        result.tests,
        result.assertions,
        result.test_steps,
        result.test_fixtures,
    )
    started = perf_counter()
    graph = _graph_for_result(result, source)
    if timings is not None:
        timings["serialization"] = perf_counter() - started
    persistence = RepositoryPersistence(get_backend())
    incoming = inventory_from_graph(graph, source=source)
    persisted = persistence.inventory(source)
    delta = delta_between(incoming, persisted)
    started = perf_counter()
    persistence.apply(graph, delta)
    if timings is not None:
        timings["persistence"] = perf_counter() - started
    return graph, delta


def connect_neo4j() -> None:
    """Compatibility health check; backend selection remains Codegraph-owned."""
    backend = get_backend()
    if not backend.health_check():
        raise RuntimeError("configured graph backend is unavailable")


def ensure_schema(stdout=None) -> None:
    del stdout
    get_backend().apply_schema()


def clear_source(source: str) -> None:
    deleted = get_backend().graph.delete_by_source(source)
    print(f"  Cleared {deleted} existing '{source}' nodes.")


def clear_all() -> None:
    get_backend().wipe()
    print("  Cleared all codebase data from the graph.")


def write_result(
    result: ParseResult,
    source: str | None = None,
    *,
    timings: dict[str, float] | None = None,
) -> None:
    src = source or _infer_source(result)
    graph, delta = _persist_result(result, src, timings=timings)
    print(
        f"  Wrote {len(graph)} nodes to {type(get_backend()).__name__} "
        f"({delta.summary()['entities_created']} created)"
    )


def update_result(result: ParseResult, source: str) -> dict[str, int]:
    _, delta = _persist_result(result, source)
    return dict(Counter(entity.node_type for entity in delta.entities.deleted))


def delete_stale_nodes(
    source: str,
    stale_keys: set[str],
    persisted: Inventory | CanonicalInventory,
) -> dict[str, int]:
    """Compatibility helper for callers that precomputed stale keys."""
    if isinstance(persisted, Inventory):
        entries = persisted.entities
        source_keys = {
            key for key, item in entries.items() if item.source == source
        }
        counts = Counter(
            entries[key].node_type for key in stale_keys if key in entries
        )
    else:
        source_keys = persisted.keys_for_source(source)
        counts = Counter(persisted.entries[key][0] for key in stale_keys)
    if not set(stale_keys) <= source_keys:
        raise CanonicalReconciliationError(
            "stale canonical deletion escaped its source scope"
        )
    for key in sorted(stale_keys):
        get_backend().graph.delete_by_key(key)
    return dict(counts)


def ingest(
    xml_dir: Path | str,
    source: str = "msd",
    database: str = "neo4j",
    clear: bool = False,
    layer: str = "dependency",
    incremental: bool = True,
) -> None:
    """Compatibility entry point routed through the C++ extraction adapter."""
    del database
    from codegraph_index.contracts import IndexMode, IndexRequest
    from codegraph_index.service import IndexService

    xml_path = Path(xml_dir)
    request = IndexRequest(
        project_root=xml_path.parent,
        project_id=source,
        repository_id=source,
        source=source,
        language="cpp",
        input_paths=(xml_path,),
        mode=(
            IndexMode.INCREMENTAL
            if incremental and not clear
            else IndexMode.REPLACE_SOURCE
        ),
        adapter_options={"xml_dir": xml_path, "layer": layer, "text_scan": False},
    )
    result = IndexService(
        persistence=RepositoryPersistence(get_backend())
    ).index(request)
    if not result.success:
        message = "; ".join(item.message for item in result.diagnostics)
        raise RuntimeError(message or "indexing failed")
    print(f"\nNode counts by source:\n  [{source}]: {len(result.graph)}")
