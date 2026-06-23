"""CLI configuration for the codegraph HTML exporter.

Resolves a project's name and HTML output directory from a config file
in the project root, in priority order:

1. ``.codegraph.toml``  — a standalone codegraph config::

       [project]
       name = "design"
       output_dir = "build/docs"

2. ``.doxygen-index.toml``  — the config used by the
   `Doxygen-Dependency-Parser <https://github.com/danielnewman09/Doxygen-Dependency-Parser>`_
   ``doxygen-index`` tool.  When present, the HTML output directory is
   taken from its optional ``[codegraph-html]`` section (defaulting to
   ``"codegraph"``), and the project name from ``[project].name``::

       [project]
       name = "codegraph"
       language = "python"
       input_paths = ["src"]

       [codegraph-html]
       output_dir = "codegraph"

This lets a project keep a single ``.doxygen-index.toml`` for both the
parser and the HTML renderer, without a separate ``.codegraph.toml``.

The exporter reads ``{output_dir}/{name}.json`` as the code-graph JSON
file to visualise.
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

# Default HTML output dir when reading a .doxygen-index.toml that has
# no explicit [codegraph-html].output_dir (matches doxygen-index's own
# default).
_DEFAULT_HTML_OUTPUT_DIR = "codegraph"


@dataclass(frozen=True)
class HtmlExportConfig:
    """Configuration for the HTML exporter.

    Attributes:
        name: Project / graph name — used for the input JSON filename
            (``{output_dir}/{name}.json``) and the default output HTML
            filename (``{output_dir}/{name}.html``).
        output_dir: Directory containing the code-graph JSON and where
            the HTML will be written by default.
        source_file: Which config file the values were read from, for
            diagnostics (e.g. ``.codegraph.toml`` or
            ``.doxygen-index.toml``).
    """

    name: str
    output_dir: Path
    source_file: str


def load_config(project_dir: Path | str = ".") -> tuple[HtmlExportConfig, Path]:
    """Load HTML export config from *project_dir*.

    Looks for ``.codegraph.toml`` first, then falls back to
    ``.doxygen-index.toml`` (reading its ``[codegraph-html]`` section).

    Args:
        project_dir: Directory containing the config file.  Defaults
            to the current working directory.

    Returns:
        Tuple of ``(HtmlExportConfig, resolved_project_dir)``.

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


def _load_codegraph_toml(
    config_path: Path, project_dir: Path
) -> tuple[HtmlExportConfig, Path]:
    """Parse a standalone ``.codegraph.toml`` config file."""
    data = tomllib.loads(config_path.read_text())
    proj = data.get("project", {})

    if "name" not in proj:
        print(
            f"Error: [project] section must specify 'name' in {config_path}",
            file=sys.stderr,
        )
        sys.exit(1)
    if "output_dir" not in proj:
        print(
            f"Error: [project] section must specify 'output_dir' in {config_path}",
            file=sys.stderr,
        )
        sys.exit(1)

    resolved_output = (project_dir / proj["output_dir"]).resolve()
    return (
        HtmlExportConfig(
            name=proj["name"],
            output_dir=resolved_output,
            source_file=CONFIG_FILENAME,
        ),
        project_dir,
    )


def _load_doxygen_toml(
    config_path: Path, project_dir: Path
) -> tuple[HtmlExportConfig, Path]:
    """Parse a ``.doxygen-index.toml`` config file.

    Project name comes from ``[project].name``; the HTML output
    directory comes from ``[codegraph-html].output_dir`` (defaulting
    to ``"codegraph"``), matching the doxygen-index tool's behaviour.
    """
    data = tomllib.loads(config_path.read_text())
    proj = data.get("project", {})

    if "name" not in proj:
        print(
            f"Error: [project] section must specify 'name' in {config_path}",
            file=sys.stderr,
        )
        sys.exit(1)

    html_section = data.get("codegraph-html", {})
    output_raw = html_section.get("output_dir", _DEFAULT_HTML_OUTPUT_DIR)
    resolved_output = (project_dir / output_raw).resolve()

    return (
        HtmlExportConfig(
            name=proj["name"],
            output_dir=resolved_output,
            source_file=DOXYGEN_CONFIG_FILENAME,
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
        "…or create a .doxygen-index.toml with a [codegraph-html] section:",
        file=sys.stderr,
    )
    print(
        '[project]\nname = "my-project"\n\n'
        "[codegraph-html]\noutput_dir = \"codegraph\"\n",
        file=sys.stderr,
    )