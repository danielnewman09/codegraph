"""Test-owned setup and diagnostics for external codegen tools.

The C++ round-trip tests exercise Doxygen/Conan as part of their semantic
contract.  Conan 2 keeps an LRU database in its home, so sharing an ambient
home makes an otherwise read-only test fail when that database is not
writable.  This module creates a disposable Conan home by copying only the
cache metadata, recipe exports, and the host/Debug package artifacts resolved
by the fixture graph.  The source cache is read-only input; all Conan writes
land below pytest's temporary directory.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Mapping


FailureCategory = Literal[
    "missing_tool",
    "missing_recipe",
    "network",
    "environment",
    "semantic",
]


class ExternalToolError(RuntimeError):
    """A classified failure while preparing or invoking an external tool."""

    def __init__(self, category: FailureCategory, message: str) -> None:
        self.category = category
        super().__init__(f"[{category}] {message}")


@dataclass(frozen=True)
class ConanTestEnvironment:
    """Disposable Conan state and the inventory used to create it."""

    home: Path
    env: dict[str, str]
    inventory_path: Path
    inventory: dict[str, object]


_PROFILE_NAME = "default"
_BUILD_TYPE = "Debug"


def _resolve_executable(name: str, override: str | None = None) -> Path:
    candidate = override or os.environ.get(name.upper().replace("-", "_"))
    resolved = Path(candidate).expanduser() if candidate else None
    if resolved is not None and resolved.is_file():
        return resolved.resolve()
    on_path = shutil.which(candidate or name)
    if on_path:
        return Path(on_path).resolve()
    raise ExternalToolError(
        "missing_tool",
        f"{name!r} is unavailable; install it or set {name.upper().replace('-', '_')}",
    )


def _run(
    argv: list[str],
    *,
    env: Mapping[str, str] | None = None,
    cwd: Path | None = None,
    timeout: int = 120,
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            argv,
            cwd=cwd,
            env=dict(env) if env is not None else None,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError as exc:
        raise ExternalToolError("missing_tool", f"tool not found: {argv[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise ExternalToolError(
            "environment", f"external command timed out after {timeout}s: {' '.join(argv)}"
        ) from exc


def classify_failure(output: str) -> FailureCategory:
    """Classify an external-tool failure without treating it as a semantic pass."""
    text = output.lower()
    if any(
        marker in text
        for marker in (
            "name or service not known",
            "nodename nor servname",
            "max retries exceeded",
            "unable to connect to remote",
            "connection refused",
            "name resolution",
            "failed to resolve",
            "could not resolve",
            "timed out",
        )
    ):
        return "network"
    if any(
        marker in text
        for marker in (
            "not found in local cache",
            "could not be resolved",
            "no remote defined",
            "recipe '",
            "package folder does not exist",
            "cache path failed",
        )
    ) or ("package '" in text and "not resolved" in text):
        return "missing_recipe"
    if "readonly database" in text or "read-only database" in text:
        return "environment"
    if "conan" in text and "not found" in text:
        return "missing_tool"
    return "semantic"


def run_index(
    argv: list[str], *, cwd: Path, env: Mapping[str, str], timeout: int = 600
) -> subprocess.CompletedProcess[str]:
    """Run an index command and raise a classified failure on non-zero exit."""
    proc = _run(argv, cwd=cwd, env=env, timeout=timeout)
    if proc.returncode:
        combined = f"{proc.stdout}\n{proc.stderr}"
        category = classify_failure(combined)
        detail = combined.strip()[-4000:]
        raise ExternalToolError(category, f"index command failed:\n{detail}")
    return proc


def _source_home(conan: Path) -> Path:
    configured = os.environ.get("CODEGRAPH_CONAN_SOURCE_HOME")
    if configured:
        return Path(configured).expanduser().resolve()
    proc = _run([str(conan), "config", "home"], timeout=30)
    if proc.returncode:
        raise ExternalToolError(
            "environment", f"could not determine Conan source home:\n{proc.stderr.strip()}"
        )
    return Path(proc.stdout.strip()).expanduser().resolve()


def _copy_recipe_exports(source_home: Path, isolated_home: Path) -> None:
    db = sqlite3.connect(source_home / "p" / "cache.sqlite3")
    try:
        rows = db.execute("SELECT path FROM recipes").fetchall()
    finally:
        db.close()
    for (relative_path,) in rows:
        source = source_home / "p" / str(relative_path) / "e"
        if not source.is_dir():
            continue
        target = isolated_home / "p" / str(relative_path) / "e"
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source, target, dirs_exist_ok=True)


def _resolved_packages(
    conan: Path, env: Mapping[str, str], project_dir: Path
) -> list[dict[str, str]]:
    """Resolve the fixture graph offline and return every package artifact."""
    proc = _run(
        [
            str(conan),
            "graph",
            "info",
            str(project_dir),
            "--format=json",
            "-s",
            f"build_type={_BUILD_TYPE}",
            "-nr",
        ],
        env=env,
        timeout=300,
    )
    if proc.returncode:
        category = classify_failure(f"{proc.stdout}\n{proc.stderr}")
        raise ExternalToolError(
            category,
            f"could not resolve the pinned Conan graph:\n{proc.stderr.strip()}",
        )
    try:
        nodes = json.loads(proc.stdout).get("graph", {}).get("nodes", {}).values()
    except (TypeError, ValueError) as exc:
        raise ExternalToolError(
            "environment", "Conan graph info returned invalid JSON"
        ) from exc
    packages: list[dict[str, str]] = []
    for node in nodes:
        ref = str(node.get("ref") or "")
        package_id = str(node.get("package_id") or "")
        if not ref or not package_id:
            continue
        reference, separator, recipe_revision = ref.partition("#")
        if not separator:
            # The consumer/root node is intentionally not a cache artifact;
            # every resolved dependency node carries a recipe revision.
            if str(node.get("id")) == "0" or reference == "cpp_sqlite/0.1.0":
                continue
            raise ExternalToolError(
                "environment", f"Conan graph omitted a recipe revision for {ref}"
            )
        packages.append(
            {
                "reference": reference,
                "recipe_revision": recipe_revision,
                "package_id": package_id,
            }
        )
    return packages


def prepare_conan_environment(
    root: Path, *, project_dir: Path
) -> ConanTestEnvironment:
    """Create isolated Conan 2 state and write a revision inventory.

    The source cache is never used as ``CONAN_HOME`` for the index process.
    Only its metadata, recipe exports, and matching resolved package folders
    are copied into ``root``.  A clean machine can point
    ``CODEGRAPH_CONAN_SOURCE_HOME`` at a read-only cache prepared by the
    documented setup instructions.
    """
    conan = _resolve_executable("conan")
    version_proc = _run([str(conan), "--version"], timeout=30)
    if version_proc.returncode:
        raise ExternalToolError("missing_tool", version_proc.stderr.strip())
    version = version_proc.stdout.strip() or version_proc.stderr.strip()
    match = re.search(r"Conan version (\d+)(?:\.(\d+))?", version)
    if not match or match.group(1) != "2":
        raise ExternalToolError(
            "environment", f"Conan 2 is required for CONAN_HOME isolation; found {version!r}"
        )

    source_home = _source_home(conan)
    source_db = source_home / "p" / "cache.sqlite3"
    source_profile = source_home / "profiles" / _PROFILE_NAME
    if not source_db.is_file() or not source_profile.is_file():
        raise ExternalToolError(
            "missing_recipe",
            f"Conan source cache needs {source_db} and {source_profile}; "
            "prepare the pinned dependency cache first",
        )

    root.mkdir(parents=True, exist_ok=True)
    isolated_home = root / "conan-home"
    (isolated_home / "p").mkdir(parents=True)
    for relative in (".conan.db", "settings.yml", "global.conf", "p/cache.sqlite3"):
        source = source_home / relative
        if source.is_file():
            target = isolated_home / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
    (isolated_home / "profiles").mkdir()
    shutil.copy2(source_profile, isolated_home / "profiles" / _PROFILE_NAME)

    inventory: dict[str, object] = {
        "conan": version,
        "profile": _PROFILE_NAME,
        "build_type": _BUILD_TYPE,
        "profile_sha256": hashlib.sha256(source_profile.read_bytes()).hexdigest(),
        "dependencies": {},
    }
    _copy_recipe_exports(source_home, isolated_home)
    env = dict(os.environ)
    env["CONAN_HOME"] = str(isolated_home)
    env["PATH"] = os.pathsep.join(
        [str(conan.parent), env.get("PATH", "")]
    ).rstrip(os.pathsep)
    resolved = _resolved_packages(conan, env, project_dir)
    source_cache_db = sqlite3.connect(source_db)
    try:
        for package in resolved:
            reference = package["reference"]
            recipe_revision = package["recipe_revision"]
            package_id = package["package_id"]
            recipe_row = source_cache_db.execute(
                "SELECT path FROM recipes WHERE reference = ? AND rrev = ?",
                (reference, recipe_revision),
            ).fetchone()
            if recipe_row is None:
                raise ExternalToolError(
                    "missing_recipe",
                    f"cached recipe metadata is absent: {reference}#{recipe_revision}",
                )
            package_row = source_cache_db.execute(
                "SELECT prev, path FROM packages WHERE reference = ? "
                "AND rrev = ? AND pkgid = ? ORDER BY timestamp DESC LIMIT 1",
                (reference, recipe_revision, package_id),
            ).fetchone()
            if package_row is None:
                raise ExternalToolError(
                    "missing_recipe",
                    "cached package metadata is absent: "
                    f"{reference}#{recipe_revision}:{package_id}",
                )
            package_revision, package_path = str(package_row[0]), str(package_row[1])
            source_package = source_home / "p" / package_path
            if not (source_package / "p").is_dir():
                raise ExternalToolError(
                    "missing_recipe",
                    f"cached package folder is absent: {reference}#{recipe_revision}:{package_id}",
                )
            target_package = isolated_home / "p" / package_path
            target_package.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(source_package, target_package, dirs_exist_ok=True)
            package_key = f"{reference}:{package_id}"
            inventory["dependencies"][package_key] = {
                "recipe_revision": recipe_revision,
                "package_id": package_id,
                "package_revision": package_revision,
                "recipe_cache_path": str(recipe_row[0]),
                "package_cache_path": package_path,
            }
    finally:
        source_cache_db.close()

    inventory_path = root / "conan-tool-inventory.json"
    inventory_path.write_text(
        json.dumps(inventory, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return ConanTestEnvironment(isolated_home, env, inventory_path, inventory)
