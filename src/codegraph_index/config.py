"""Translate legacy and manifest configuration into ``IndexRequest``."""

from __future__ import annotations

from pathlib import Path

from codegraph.identity.manifest import load_manifest
from codegraph_index.contracts import IndexMode, IndexRequest


class ConfigurationError(ValueError):
    """Raised for invalid indexing configuration in library callers."""


def _words(value: str | list[str] | tuple[str, ...] | None) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return tuple(part for part in value.split() if part)
    return tuple(value)


def load_config_file(project_dir: str | Path, *, filename: str = ".doxygen-index.toml"):
    """Load legacy configuration without printing or calling ``sys.exit``."""
    import tomllib
    from codegraph_index.project import ProjectConfig

    root = Path(project_dir).resolve()
    path = root / filename
    if not path.is_file():
        raise ConfigurationError(f"configuration file not found: {path}")
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    project = data.get("project") or {}
    if not project.get("name"):
        raise ConfigurationError(f"[project].name is required in {path}")
    if not project.get("input_paths"):
        raise ConfigurationError(f"[project].input_paths is required in {path}")
    base = path.parent
    input_paths = tuple((base / item).resolve() for item in project["input_paths"])
    test_paths = tuple(
        (base / item).resolve() for item in project.get("test_paths", [])
    )
    output_dir = project.get("output_dir")
    return ProjectConfig(
        name=project["name"],
        input_paths=list(input_paths),
        language=project.get("language", "cpp"),
        output_dir=(base / output_dir).resolve() if output_dir else None,
        file_patterns=project.get("file_patterns", "*.h *.hpp *.hxx *.cpp *.cxx *.cc"),
        recursive=project.get("recursive", True),
        exclude_patterns=project.get("exclude_patterns", ""),
        predefined=project.get("predefined", ""),
        test_paths=list(test_paths) or None,
        requirements_dir=(base / project["requirements_dir"]).resolve()
        if project.get("requirements_dir") else None,
    )


def request_from_project_config(
    project_root: str | Path,
    config,
    *,
    project_id: str | None = None,
    repository_id: str | None = None,
    source: str | None = None,
    mode: IndexMode = IndexMode.INCREMENTAL,
    emit_json: bool = False,
    adapter_options: dict | None = None,
) -> IndexRequest:
    """Build a request using explicit scope or the active manifest."""
    root = Path(project_root).resolve()
    manifest = load_manifest(root)
    repository = None
    if manifest is not None:
        project_id = project_id or manifest["project"]["id"]
        if repository_id:
            repository = next(
                (item for item in manifest.get("repositories", [])
                 if item.get("name") == repository_id),
                None,
            )
        else:
            for item in manifest.get("repositories", []):
                candidate = (root / item.get("path", ".")).resolve()
                if candidate == root:
                    repository = item
                    repository_id = item.get("name")
                    break
        if repository is None and repository_id:
            repository = {"name": repository_id}
    if not project_id or not repository_id:
        # The legacy CLI has no manifest flag. Keep its config usable while
        # making the fallback explicit and local to this compatibility path.
        project_id = project_id or config.name
        repository_id = repository_id or config.name

    request_options = dict(adapter_options or {})
    return IndexRequest(
        project_root=root,
        project_id=project_id,
        repository_id=repository_id,
        source=source or getattr(config, "name", repository_id),
        language=getattr(config, "language", "cpp"),
        input_paths=tuple(config.input_paths),
        test_paths=tuple(getattr(config, "test_paths", None) or ()),
        output_dir=getattr(config, "output_dir", None),
        file_patterns=_words(getattr(config, "file_patterns", None)),
        exclude_patterns=_words(getattr(config, "exclude_patterns", None)),
        predefined=_words(getattr(config, "predefined", None)),
        mode=mode,
        emit_json=emit_json,
        requirements_dir=getattr(config, "requirements_dir", None),
        adapter_options=request_options,
    )
