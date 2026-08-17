"""Manifest-driven scope resolution (WP6.2, canonical-only cutover).

Scope resolution is authoritative from ``.codegraph-project.toml``
(env overrides ``CODEGRAPH_PROJECT_ID`` / ``CODEGRAPH_PROJECT_FILE``),
never inferred from paths.  Migration/status helpers were removed in
the canonical-only cutover (WP A) — this file covers the retained
manifest surface only.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from codegraph.backends import get_backend, set_backend
from codegraph.backends.memory import InMemoryBackend
from codegraph.identity import (
    IdentityScope,
    ManifestError,
    find_manifest,
    load_manifest,
    manifest_project_id,
    project_scope,
    repository_scope,
    repository_scopes,
)

MANIFEST = """\
schema_version = 1

[project]
id = "manifest-suite"
database = "/tmp/ignored.sqlite3"

[[repositories]]
name = "alpha"
path = "."
source = "alpha"
index = true

[[repositories]]
name = "beta"
path = "../beta"
source = "beta"
index = true
"""


@pytest.fixture(autouse=True)
def _env_clean(monkeypatch, tmp_path):
    monkeypatch.delenv("CODEGRAPH_PROJECT_FILE", raising=False)
    monkeypatch.delenv("CODEGRAPH_PROJECT_ID", raising=False)
    (tmp_path / ".codegraph-project.toml").write_text(MANIFEST)
    previous = get_backend()
    set_backend(InMemoryBackend())
    yield tmp_path
    set_backend(previous)


class TestManifestResolution:
    def test_find_and_load(self, _env_clean) -> None:
        project_dir = _env_clean
        assert find_manifest(project_dir) == project_dir / ".codegraph-project.toml"
        data = load_manifest(project_dir)
        assert data["project"]["id"] == "manifest-suite"
        assert [r["name"] for r in data["repositories"]] == ["alpha", "beta"]

    def test_project_id_and_scopes(self, _env_clean) -> None:
        project_dir = _env_clean
        assert manifest_project_id(project_dir) == "manifest-suite"
        assert project_scope(project_dir) == IdentityScope.project("manifest-suite")
        assert repository_scope("alpha", project_dir) == IdentityScope.repository(
            "manifest-suite", "alpha"
        )
        scopes = repository_scopes(project_dir)
        assert set(scopes) == {"alpha", "beta"}
        assert scopes["beta"].scope_id == "manifest-suite/beta"

    def test_env_overrides_manifest(self, _env_clean, monkeypatch) -> None:
        monkeypatch.setenv("CODEGRAPH_PROJECT_ID", "env-suite")
        assert manifest_project_id(_env_clean) == "env-suite"
        assert project_scope(_env_clean) == IdentityScope.project("env-suite")

    def test_no_manifest_returns_none(self, tmp_path, monkeypatch) -> None:
        monkeypatch.delenv("CODEGRAPH_PROJECT_FILE", raising=False)
        manifest = tmp_path / ".codegraph-project.toml"
        manifest.unlink(missing_ok=True)  # the autouse fixture wrote one
        assert find_manifest(tmp_path) is None
        assert project_scope(tmp_path) is None
        assert repository_scopes(tmp_path) == {}

    def test_missing_project_id_raises(self, tmp_path, monkeypatch) -> None:
        monkeypatch.delenv("CODEGRAPH_PROJECT_FILE", raising=False)
        (tmp_path / ".codegraph-project.toml").write_text(
            "schema_version = 1\n[project]\ndatabase = \"/x\"\n"
        )
        with pytest.raises(ManifestError):
            load_manifest(tmp_path)

    def test_unsupported_schema_version_raises(self, tmp_path,
                                               monkeypatch) -> None:
        monkeypatch.delenv("CODEGRAPH_PROJECT_FILE", raising=False)
        (tmp_path / ".codegraph-project.toml").write_text(
            "schema_version = 99\n[project]\nid = \"x\"\n"
        )
        with pytest.raises(ManifestError, match="schema_version"):
            load_manifest(tmp_path)
