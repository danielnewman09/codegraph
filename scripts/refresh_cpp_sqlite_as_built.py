#!/usr/bin/env python3
"""Refresh the bounded canonical cpp-sqlite as-built fixture.

The producer creates a fresh isolated DDP/SQLite index and then uses the normal
``LayerGraph.from_backend`` view contract. The JSON is a portable project view,
not an archive of the complete dependency database. Canonical targets omitted
from the bounded view remain explicit external relationships.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
DDP_ROOT = ROOT.parent / "Doxygen-Dependency-Parser"
DDP_FIXTURE = DDP_ROOT / "tests" / "fixtures" / "cpp-sqlite"
_DEFAULT_DOXYGEN_INDEX = DDP_ROOT.parent / ".venv" / "bin" / "doxygen-index"
DOXYGEN_INDEX = (
    os.environ.get("DOXYGEN_INDEX")
    or shutil.which("doxygen-index")
    or (str(_DEFAULT_DOXYGEN_INDEX) if _DEFAULT_DOXYGEN_INDEX.is_file() else None)
)
SOURCES = ("boost", "cpp-sqlite", "cppreference", "gtest", "spdlog", "sqlite3")
ONLY_SOURCES = "sqlite3,boost,spdlog"
FORBIDDEN_NODE_FIELDS = frozenset({
    "uid", "target_uid", "refid", "compound_refid", "member_refid",
    "parent_refid", "child_refid", "from_refid", "to_refid",
})
FORBIDDEN_EDGE_FIELDS = frozenset({
    "uid", "target_uid", "refid", "from_refid", "to_refid",
})
EXCLUDED_RELATIONS = frozenset({"HAS_IMPLEMENTATION", "TEMPLATE_PARAM"})
FIXTURE_SCOPE = "fixture/fixture"


def _normalize_canonical_value(value: Any) -> Any:
    """Structurally rewrite canonical keys into the stable fixture scope."""
    from codegraph.identity import CanonicalIdentity, encode_key

    if isinstance(value, str) and value.startswith("cg:v1:"):
        if value == "cg:v1:root":
            return value
        identity = CanonicalIdentity.from_key(value)
        values = [
            (name, _normalize_canonical_value(field_value))
            for name, field_value in identity.values
        ]
        return encode_key(
            "repository", FIXTURE_SCOPE, identity.category, values
        )
    if isinstance(value, list):
        return [_normalize_canonical_value(item) for item in value]
    if isinstance(value, dict):
        return {
            key: _normalize_canonical_value(item)
            for key, item in value.items()
        }
    return value


def _ddp_environment(sqlite_path: Path) -> dict[str, str]:
    env = os.environ.copy()
    env.update({
        "CODEGRAPH_BACKEND": "sqlite",
        "SQLITE_PATH": str(sqlite_path),
        "PYTHONHASHSEED": "0",
    })
    deterministic = DDP_ROOT / "tests" / "cpp_sqlite_integration" / "deterministic_python"
    src_path = ROOT / "src"
    env["PYTHONPATH"] = os.pathsep.join(
        str(path)
        for path in (deterministic, src_path, env.get("PYTHONPATH", ""))
        if str(path)
    )
    return env


def _run_index(sqlite_path: Path, output_dir: Path, *, cppreference: bool) -> None:
    if not DOXYGEN_INDEX:
        raise RuntimeError(
            "doxygen-index was not found; set DOXYGEN_INDEX or install the "
            "Doxygen-Dependency-Parser environment"
        )
    command = [
        DOXYGEN_INDEX,
        "codegraph",
        "--project-dir", str(DDP_FIXTURE),
        "--output-dir", str(output_dir),
        "--neo4j", "--no-csv", "--clear", "--yes",
        "--only", ONLY_SOURCES,
    ]
    if cppreference:
        command.append("--cppreference")
    result = subprocess.run(
        command,
        cwd=str(DDP_ROOT),
        env=_ddp_environment(sqlite_path),
        check=False,
        timeout=900,
    )
    if result.returncode:
        raise RuntimeError(
            f"isolated cpp-sqlite indexing failed with status {result.returncode}"
        )


def _iter_input_files() -> Iterable[tuple[str, Path]]:
    """Yield all deterministic mutable inputs that can affect the producer."""
    roots = (
        ("codegraph", ROOT / "src"),
        ("ddp", DDP_ROOT / "src"),
        ("ddp-deterministic", DDP_ROOT / "tests" / "cpp_sqlite_integration" / "deterministic_python"),
        ("fixture", DDP_FIXTURE),
    )
    seen: set[Path] = set()
    for label, root in roots:
        if not root.exists():
            continue
        paths = [root] if root.is_file() else sorted(p for p in root.rglob("*") if p.is_file())
        for path in paths:
            if path.suffix in {".pyc", ".sqlite3"} or "__pycache__" in path.parts:
                continue
            resolved = path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            yield f"{label}/{path.relative_to(root) if root.is_dir() else path.name}", path
    script = Path(__file__).resolve()
    if script not in seen:
        yield "codegraph-refresh-script", script


def _tool_version(command: list[str]) -> str:
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=30, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return f"unavailable:{type(exc).__name__}"
    text = (result.stdout or result.stderr).strip().splitlines()
    return text[0] if text else f"status:{result.returncode}"


def producer_input_manifest(*, cppreference: bool) -> dict[str, Any]:
    files = []
    for relative, path in sorted(_iter_input_files()):
        files.append({
            "path": relative,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "size": path.stat().st_size,
        })
    selected_env = {
        key: os.environ.get(key, "")
        for key in (
            "CODEGRAPH_BACKEND", "DOXYGEN_INDEX", "CONAN_HOME", "CONAN_USER_HOME",
            "CPPREFERENCE_DIR", "CPPREFERENCE_ARCHIVE", "CPPREFERENCE_CACHE",
        )
    }
    manifest = {
        "format": 1,
        "command": {
            "only": ONLY_SOURCES,
            "cppreference": cppreference,
            "project_dir": str(DDP_FIXTURE),
        },
        "environment": selected_env,
        "versions": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "doxygen_index": _tool_version([DOXYGEN_INDEX]) if DOXYGEN_INDEX else "missing",
            "doxygen": _tool_version(["doxygen", "--version"]),
            "conan": _tool_version(["conan", "--version"]),
        },
        "files": files,
    }
    canonical = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
    manifest["producer_input_digest"] = hashlib.sha256(canonical).hexdigest()
    return manifest


def assert_same_producer_inputs(first: dict[str, Any], second: dict[str, Any]) -> None:
    """Fail unless two independent producer runs used identical inputs."""
    first_digest = first.get("producer_input_digest")
    second_digest = second.get("producer_input_digest")
    if first_digest != second_digest or first != second:
        raise RuntimeError(
            "independent producer input manifests differ: "
            f"{first_digest!r} != {second_digest!r}"
        )


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _walk_entries(data: list[dict[str, Any]]) -> Iterable[dict[str, Any]]:
    for entry in data:
        yield entry
        yield from _walk_entries(entry.get("composes", []))


def _edge_map(data: list[dict[str, Any]]) -> dict[tuple[str, str, str], tuple[str, str]]:
    result: dict[tuple[str, str, str], tuple[str, str]] = {}
    entries = list(_walk_entries(data))
    nodes = {entry["canonical_key"] for entry in entries}
    for entry in entries:
        source = entry["canonical_key"]
        for edge in entry.get("edges", []):
            if FORBIDDEN_EDGE_FIELDS & set(edge):
                raise RuntimeError(f"forbidden edge fields: {sorted(FORBIDDEN_EDGE_FIELDS & set(edge))}")
            if edge.get("target_ref") or edge.get("unresolved") is True:
                raise RuntimeError("fixture contains an unresolved endpoint")
            target = edge.get("target_key")
            if not isinstance(target, str):
                raise RuntimeError(f"fixture edge has no canonical target: {target!r}")
            if target not in nodes and edge.get("external") is not True:
                raise RuntimeError(
                    f"out-of-view fixture target is not external: {target!r}"
                )
            if target in nodes and edge.get("external") is True:
                raise RuntimeError(
                    f"in-view fixture target is incorrectly external: {target!r}"
                )
            attrs = {
                key: value for key, value in edge.items()
                if key not in {"relation_type", "target_key", "target_type"}
            }
            logical = (source, edge["relation_type"], target)
            value = (
                edge["target_type"],
                json.dumps(attrs, sort_keys=True, separators=(",", ":")),
            )
            if logical in result and result[logical] != value:
                raise RuntimeError(f"conflicting fixture endpoint triple: {logical!r}")
            result[logical] = value
    return result


def _classify_projection_endpoints(data: list[dict[str, Any]]) -> None:
    """Mark canonical targets omitted from the bounded document as external."""
    entries = list(_walk_entries(data))
    node_keys = {entry["canonical_key"] for entry in entries}
    for entry in entries:
        for edge in entry.get("edges", []):
            target = edge.get("target_key")
            if target in node_keys:
                edge.pop("external", None)
            elif isinstance(target, str):
                edge["external"] = True


def validate_projection(data: list[dict[str, Any]]) -> dict[str, Any]:
    """Validate a canonical bounded projection and return inventories."""
    from codegraph.identity import CanonicalIdentity

    node_keys: set[str] = set()
    source_counts: Counter[str] = Counter()
    type_counts: Counter[str] = Counter()
    for entry in _walk_entries(data):
        if FORBIDDEN_NODE_FIELDS & set(entry):
            raise RuntimeError(f"forbidden node fields: {sorted(FORBIDDEN_NODE_FIELDS & set(entry))}")
        key = entry.get("canonical_key")
        if not isinstance(key, str) or not key:
            raise RuntimeError("fixture node is missing canonical_key")
        CanonicalIdentity.from_key(key)
        if key in node_keys:
            raise RuntimeError(f"duplicate canonical node key: {key}")
        node_keys.add(key)
        source_counts[entry.get("source", "")] += 1
        type_counts[entry.get("node_type") or entry.get("type", "")] += 1
        if "target_ref" in entry or "uid" in entry or "refid" in entry:
            raise RuntimeError(f"legacy node identity field in {key}")
    edges = _edge_map(data)
    if any(key[1] in EXCLUDED_RELATIONS for key in edges):
        raise RuntimeError("excluded relationship type survived portable export")
    return {
        "nodes": len(node_keys),
        "sources": dict(sorted(source_counts.items())),
        "node_types": dict(sorted(type_counts.items())),
        "relationships": len(edges),
        "relationship_types": dict(sorted(Counter(key[1] for key in edges).items())),
        "edge_map": edges,
    }


def _roundtrip(data: list[dict[str, Any]]) -> list[dict[str, Any]]:
    from codegraph.graph import LayerGraph

    graph = LayerGraph.deserialize(data)
    result = graph.serialize(fields="all")
    left = validate_projection(data)
    right = validate_projection(result)
    if left["edge_map"] != right["edge_map"]:
        raise RuntimeError("import/serialize changed the relationship map")
    if {e["canonical_key"] for e in _walk_entries(data)} != {
        e["canonical_key"] for e in _walk_entries(result)
    }:
        raise RuntimeError("import/serialize changed the projected node set")
    stable = LayerGraph.deserialize(result).serialize(fields="all")
    if json.dumps(result, sort_keys=True, separators=(",", ":")) != json.dumps(
        stable, sort_keys=True, separators=(",", ":")
    ):
        raise RuntimeError("fixture import/serialize is not a byte fixpoint")
    return result


def refresh(
    output: Path,
    *,
    cppreference: bool = True,
    manifest_path: Path | None = None,
    report_path: Path | None = None,
) -> dict[str, Any]:
    if output.resolve() == ROOT:
        raise ValueError("refusing to write the repository root")
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    manifest = producer_input_manifest(cppreference=cppreference)
    with tempfile.TemporaryDirectory(prefix="codegraph_cpp_sqlite_view_") as temp_dir:
        temp = Path(temp_dir)
        sqlite_path = temp / "index.sqlite3"
        xml_dir = temp / "doxygen"
        _run_index(sqlite_path, xml_dir, cppreference=cppreference)

        from codegraph.backends import get_backend, set_backend
        from codegraph.backends.sqlite import SqliteBackend, SqliteConfig
        from codegraph.graph import LayerGraph

        backend = SqliteBackend(SqliteConfig(path=str(sqlite_path)))
        previous_backend = get_backend()
        try:
            set_backend(backend)
            graph = LayerGraph.from_backend(backend, "as-built")
            data = _normalize_canonical_value(graph.serialize(fields="all"))
            _classify_projection_endpoints(data)
            data = _roundtrip(data)
            validation = validate_projection(data)
        finally:
            set_backend(previous_backend)
            backend.close()
        output.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

        report = {
            "producer_input_digest": manifest["producer_input_digest"],
            "projection": {
                key: value for key, value in validation.items()
                if key != "edge_map"
            },
            "fixture_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
        }
        if manifest_path:
            _write_json(manifest_path.resolve(), manifest)
        if report_path:
            _write_json(report_path.resolve(), report)
        print(
            f"wrote {output} ({report['projection']['nodes']} nodes, "
            f"{report['projection']['relationships']} logical relationships; "
            f"input {report['producer_input_digest']})"
        )
        return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument(
        "--no-cppreference",
        action="store_true",
        help="omit cppreference indexing",
    )
    args = parser.parse_args(argv)
    refresh(
        args.output,
        cppreference=not args.no_cppreference,
        manifest_path=args.manifest,
        report_path=args.report,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
