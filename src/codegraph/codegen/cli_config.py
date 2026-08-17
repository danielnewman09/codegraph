"""CLI configuration for the codegraph codegen exporter.

Resolves a project's name, tag, and graph JSON path from a config file
in the project root, in priority order:

1. ``.codegraph.toml``  — a standalone codegraph config::

       [project]
       name = "cpp-sqlite"
       output_dir = "build/docs"

       [codegraph-codegen]
       tag = "design"

2. ``.doxygen-index.toml``  — the config used by the
   ``doxygen-index`` tool.  Project name comes from ``[project].name``;
   the output directory from ``[codegraph-codegen].output_dir``,
   defaulting to ``"codegraph"`` (where doxygen-index writes its graph
   JSON)::

       [project]
       name = "cpp_sqlite"
       input_paths = ["cpp_sqlite/src"]

The codegen CLI reads the graph JSON at ``{output_dir}/{name}.json`` —
the same convention as the codegraph project configuration.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

try:
    import tomllib
except ImportError:
    import tomli as tomllib  # Python 3.10 fallback

CONFIG_FILENAME = ".codegraph.toml"
DOXYGEN_CONFIG_FILENAME = ".doxygen-index.toml"

#: Default graph-JSON output dir when reading a .doxygen-index.toml
#: without an explicit [codegraph-codegen].output_dir (matches
#: doxygen-index's own default).
_DEFAULT_OUTPUT_DIR = "codegraph"


@dataclass(frozen=True)
class CodegenConfig:
    """Configuration for the codegen CLI.

    Attributes:
        name: Project / graph name — the input JSON filename is
            ``{output_dir}/{name}.json``.
        tag: Provenance tag to generate from (``"design"`` default).
        output_dir: Directory containing the code-graph JSON.
        graph_json: Resolved path of the input graph JSON.
        source_file: Which config file the values came from, for
            diagnostics (``.codegraph.toml`` or ``.doxygen-index.toml``).
    """

    name: str
    tag: str
    output_dir: Path
    graph_json: Path
    source_file: str


def load_config(project_dir: str | Path = ".") -> tuple[CodegenConfig, Path]:
    """Load codegen config from *project_dir*.

    Looks for ``.codegraph.toml`` first, then falls back to
    ``.doxygen-index.toml``.

    Returns:
        Tuple of ``(CodegenConfig, resolved_project_dir)``.

    Raises:
        SystemExit: If no config file is found, or required fields
            (``[project].name`` and an output directory) are absent.
    """
    project_dir = Path(project_dir).resolve()

    codegraph_path = project_dir / CONFIG_FILENAME
    doxygen_path = project_dir / DOXYGEN_CONFIG_FILENAME

    if codegraph_path.exists():
        return _load_codegraph_toml(codegraph_path, project_dir)
    if doxygen_path.exists():
        return _load_doxygen_toml(doxygen_path, project_dir)

    _print_config_help(project_dir)
    sys.exit(1)


def _make_config(
    name: str,
    tag: str,
    output_dir: Path,
    project_dir: Path,
    source_file: str,
) -> CodegenConfig:
    """Assemble the config with the graph JSON path resolved."""
    resolved_output = (project_dir / output_dir).resolve()
    return CodegenConfig(
        name=name,
        tag=tag,
        output_dir=resolved_output,
        graph_json=resolved_output / f"{name}.json",
        source_file=source_file,
    )


def _load_codegraph_toml(
    config_path: Path, project_dir: Path
) -> tuple[CodegenConfig, Path]:
    """Parse a standalone ``.codegraph.toml`` config file."""
    data = tomllib.loads(config_path.read_text())
    proj = data.get("project", {})

    if "name" not in proj:
        print(
            f"Error: [project] section must specify 'name' in {config_path}",
            file=sys.stderr,
        )
        sys.exit(1)

    codegen_section = data.get("codegraph-codegen", {})
    tag = codegen_section.get("tag", "design")
    output_dir = proj.get("output_dir") or codegen_section.get("output_dir")

    if not output_dir:
        print(
            f"Error: an output_dir is required in {config_path} "
            "([project].output_dir or [codegraph-codegen].output_dir)",
            file=sys.stderr,
        )
        sys.exit(1)

    return (
        _make_config(
            proj["name"], tag, output_dir, project_dir, CONFIG_FILENAME
        ),
        project_dir,
    )


def _load_doxygen_toml(
    config_path: Path, project_dir: Path
) -> tuple[CodegenConfig, Path]:
    """Parse a ``.doxygen-index.toml`` config file.

    Project name from ``[project].name``; the graph output directory
    from ``[codegraph-codegen].output_dir`` (default ``"codegraph"``).
    """
    data = tomllib.loads(config_path.read_text())
    proj = data.get("project", {})

    if "name" not in proj:
        print(
            f"Error: [project] section must specify 'name' in {config_path}",
            file=sys.stderr,
        )
        sys.exit(1)

    codegen_section = data.get("codegraph-codegen", {})
    tag = codegen_section.get("tag", "design")
    output_dir = codegen_section.get("output_dir", _DEFAULT_OUTPUT_DIR)

    return (
        _make_config(
            proj["name"], tag, output_dir, project_dir, DOXYGEN_CONFIG_FILENAME
        ),
        project_dir,
    )


def _print_config_help(project_dir: Path) -> None:
    """Print a helpful error message with minimal config templates."""
    template = """\
[project]
name = "my-project"
output_dir = "build/docs"
"""
    print(
        f"Error: no {CONFIG_FILENAME} or {DOXYGEN_CONFIG_FILENAME} found "
        f"in {project_dir}.",
        file=sys.stderr,
    )
    print(f"Create {project_dir / CONFIG_FILENAME} with:", file=sys.stderr)
    print(template, file=sys.stderr)
    print(
        "…or create a .doxygen-index.toml with a [codegraph-codegen] section:",
        file=sys.stderr,
    )
    print(
        '[project]\nname = "my-project"\n\n'
        "[codegraph-codegen]\noutput_dir = \"codegraph\"\n",
        file=sys.stderr,
    )
