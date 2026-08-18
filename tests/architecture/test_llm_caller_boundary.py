"""Keep new model-client usage inside the reviewed migration boundary."""

from __future__ import annotations

import ast
from pathlib import Path
import tomllib

ROOT = Path(__file__).parents[2]
SRC = ROOT / "src"
PYPROJECT = ROOT / "pyproject.toml"

ALLOWLIST = {
    "src/codegraph_design/agents/decompose_hlr.py": (
        "Priority 9 replacement: codegraph_agents.decompose + shared model service"
    ),
    "src/codegraph_design/agents/design_oo.py": (
        "Priority 9 replacement: codegraph_agents.design + shared model service"
    ),
    "src/codegraph_feedback/agents/analyze_feedback.py": (
        "Priority 9 replacement: codegraph_agents.feedback + shared model service"
    ),
    "src/codegraph_mine/base.py": (
        "Priority 9 replacement: shared model service and mining agent"
    ),
    "src/codegraph_mine/__init__.py": (
        "Priority 9 replacement: shared model service and mining agent"
    ),
    "src/codegraph_enrich/base.py": (
        "Priority 9 replacement: shared model service"
    ),
    "src/codegraph_enrich/__init__.py": (
        "Priority 9 replacement: shared model service"
    ),
}

ALLOWED_DEPENDENCY_GROUPS = {
    "design": "Priority 9 replacement: codegraph_agents.design model boundary",
    "enrich": "Priority 9 replacement: shared enrichment model boundary",
}


def _imports(root: Path) -> set[str]:
    found: set[str] = set()
    for path in root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            imported = None
            if isinstance(node, ast.Import):
                imported = next(
                    (alias.name for alias in node.names if alias.name == "llm_caller"),
                    None,
                )
            elif isinstance(node, ast.ImportFrom) and node.module == "llm_caller":
                imported = node.module
            if imported:
                found.add(path.relative_to(root.parent).as_posix())
    return found


def _dependency_groups(path: Path) -> set[str]:
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    project = data.get("project", {})
    locations = {
        "project.dependencies"
        for dep in project.get("dependencies", [])
        if str(dep).split(";")[0].strip().lower() == "llm-caller"
    }
    groups = project.get("optional-dependencies", {})
    locations.update({
        group
        for group, dependencies in groups.items()
        if any(str(dep).split(";")[0].strip().lower() == "llm-caller" for dep in dependencies)
    })
    return locations


def test_llm_caller_imports_are_explicitly_allowlisted() -> None:
    assert _imports(SRC) == set(ALLOWLIST)


def test_llm_caller_dependency_groups_are_explicitly_allowlisted() -> None:
    assert _dependency_groups(PYPROJECT) == set(ALLOWED_DEPENDENCY_GROUPS)


def test_guard_detects_a_new_import(tmp_path: Path) -> None:
    source = tmp_path / "new_consumer.py"
    source.write_text("from llm_caller import call_text\n", encoding="utf-8")
    matches = _imports(tmp_path)
    relative_match = source.relative_to(tmp_path.parent).as_posix()
    assert matches == {relative_match}
    assert relative_match not in ALLOWLIST


def test_guard_detects_a_new_dependency_group(tmp_path: Path) -> None:
    manifest = tmp_path / "pyproject.toml"
    manifest.write_text(
        "[project.optional-dependencies]\nfuture = ['llm-caller']\n",
        encoding="utf-8",
    )
    assert _dependency_groups(manifest) == {"future"}
    assert "future" not in ALLOWED_DEPENDENCY_GROUPS


def test_guard_detects_a_new_base_dependency(tmp_path: Path) -> None:
    manifest = tmp_path / "pyproject.toml"
    manifest.write_text(
        "[project]\ndependencies = ['llm-caller']\n",
        encoding="utf-8",
    )
    assert _dependency_groups(manifest) == {"project.dependencies"}
    assert "project.dependencies" not in ALLOWED_DEPENDENCY_GROUPS


def test_comments_and_markdown_are_not_import_matches(tmp_path: Path) -> None:
    source = tmp_path / "comment_only.py"
    source.write_text("# llm_caller is mentioned in migration docs\n", encoding="utf-8")
    assert _imports(tmp_path) == set()
