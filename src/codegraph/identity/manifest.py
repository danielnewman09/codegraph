"""Manifest-driven scope resolution (WP6.2).

The authoritative scope source is ``.codegraph-project.toml`` (a fixed
architectural decision): scope is never inferred from filesystem paths,
database paths, or parser names.  The MCP bridge launches the Python
bridge with ``CODEGRAPH_PROJECT_FILE`` / ``CODEGRAPH_PROJECT_ID`` /
``SQLITE_PATH`` set; this module turns those — or a discovered
manifest — into :class:`IdentityScope` instances so indexing and
migration services run under the resolved scope.

Manifest shape (schema_version 1)::

    [project]
    id = "codegraph-suite"
    database = "/abs/path/codegraph.sqlite3"

    [[repositories]]
    name = "codegraph"
    path = "."
    source = "codegraph"
    index = true
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from codegraph.identity.scope import IdentityScope, IdentityScopeError

MANIFEST_NAME = ".codegraph-project.toml"
SCHEMA_VERSION = 1


class ManifestError(ValueError):
    """Raised when a manifest is present but malformed."""


def _read_toml(path: Path) -> dict[str, Any]:
    try:
        import tomllib
    except ImportError:  # pragma: no cover - py3.11+
        import tomli as tomllib  # type: ignore[no-redef]
    with open(path, "rb") as fh:
        return tomllib.load(fh)


def find_manifest(project_dir: str | Path | None = None) -> Path | None:
    """Locate the active manifest.

    Precedence: ``CODEGRAPH_PROJECT_FILE`` (explicit), then
    ``project_dir/.codegraph-project.toml`` (or cwd when None).
    """
    explicit = os.environ.get("CODEGRAPH_PROJECT_FILE", "").strip()
    if explicit:
        path = Path(explicit)
        if path.is_file():
            return path
    base = Path(project_dir) if project_dir else Path.cwd()
    candidate = base / MANIFEST_NAME
    return candidate if candidate.is_file() else None


def load_manifest(project_dir: str | Path | None = None) -> dict[str, Any] | None:
    """Parse the active manifest, or None when none exists."""
    path = find_manifest(project_dir)
    if path is None:
        return None
    data = _read_toml(path)
    version = data.get("schema_version", SCHEMA_VERSION)
    if version != SCHEMA_VERSION:
        raise ManifestError(
            f"{path}: unsupported schema_version {version} "
            f"(this build supports {SCHEMA_VERSION})"
        )
    project = data.get("project") or {}
    if not project.get("id"):
        raise ManifestError(f"{path}: [project].id is required")
    return data


def manifest_project_id(project_dir: str | Path | None = None) -> str | None:
    """Resolve the project id: env override first, then the manifest."""
    env_id = os.environ.get("CODEGRAPH_PROJECT_ID", "").strip()
    if env_id:
        return env_id
    data = load_manifest(project_dir)
    if data is None:
        return None
    return (data.get("project") or {}).get("id")


def project_scope(project_dir: str | Path | None = None) -> IdentityScope | None:
    """The project scope from ``project.id`` (env or manifest)."""
    pid = manifest_project_id(project_dir)
    if not pid:
        return None
    try:
        return IdentityScope.project(pid)
    except IdentityScopeError:
        return None


def repository_scope(
    repository: str,
    project_dir: str | Path | None = None,
) -> IdentityScope | None:
    """The repository scope for *repository* under the resolved project.

    ``repository`` is the manifest ``[[repositories]].name`` — the
    ``repository_id`` half of the scope pair.
    """
    pid = manifest_project_id(project_dir)
    if not pid:
        return None
    try:
        return IdentityScope.repository(pid, repository)
    except IdentityScopeError:
        return None


def repository_scopes(
    project_dir: str | Path | None = None,
) -> dict[str, IdentityScope]:
    """Every manifest repository's scope, keyed by repository name."""
    data = load_manifest(project_dir)
    if data is None:
        return {}
    pid = manifest_project_id(project_dir)
    if not pid:
        return {}
    out: dict[str, IdentityScope] = {}
    for repo in data.get("repositories", []):
        name = repo.get("name")
        if not name:
            continue
        try:
            out[name] = IdentityScope.repository(pid, name)
        except IdentityScopeError:
            continue
    return out


def resolve_scope_from_env(
    project_dir: str | Path | None = None,
) -> IdentityScope | None:
    """Best-effort scope for the current environment.

    Returns the manifest project scope when the manifest (or env) names
    a project — the fallback used by bridge-launched indexing when no
    repository is specified.  Callers that know the repository should
    prefer :func:`repository_scope`.
    """
    return project_scope(project_dir)
