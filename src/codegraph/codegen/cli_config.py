"""``.codegraph.toml`` / ``.doxygen-index.toml`` discovery for codegen CLI.

Mirrors ``codegraph.export.viz.cli_config``: locate and parse the
project config, extract the ``[codegraph-codegen]``-relevant settings
(project name, tag, output dir), with ``.codegraph.toml`` taking
precedence over the ``[codegraph-codegen]`` section of
``.doxygen-index.toml``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class CodegenConfig:
    """Resolved CLI config.

    Attributes:
        name: Project name (source label).
        tag: Provenance tag to generate from.
        output_dir: Where to write the generated tree.
        source_file: Which config file was used (for diagnostics).
    """

    name: str = ""
    tag: str = "design"
    output_dir: Path | None = None
    source_file: str = ""


def load_config(project_dir: str | Path) -> tuple[CodegenConfig, Path]:
    """Discover and parse config for *project_dir*.

    Raises:
        NotImplementedError: Phase 1 render slice.
    """
    raise NotImplementedError("load_config: Phase 1 render slice")


__all__ = ["CodegenConfig", "load_config"]
