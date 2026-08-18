from __future__ import annotations
from codegraph.graph import LayerGraph
from tests.codegen.context.conftest import key_document as _kd


def _deser(data):
    return LayerGraph.deserialize(_kd(data))

"""CLI config discovery tests (.codegraph.toml / .doxygen-index.toml).

Uses the project convention: the graph JSON lives at
``{output_dir}/{name}.json``; the CLI discovers it from the project
config instead of requiring an explicit ``--input``.
"""


import json
from pathlib import Path

import pytest

from codegraph.codegen.cli import main
from codegraph.codegen.cli_config import load_config

GOLDEN = Path(__file__).resolve().parent / "golden" / "design_layergraph_full_decl.json"

CODEGRAPH_TOML = """\
[project]
name = "my-project"
output_dir = "build/docs"

[codegraph-codegen]
tag = "design"
"""

DOXYGEN_TOML = """\
[project]
name = "cpp-sqlite"
input_paths = ["cpp_sqlite/src"]

[codegraph-codegen]
output_dir = "codegraph"
"""


def _seed_project(tmp_path: Path, *, toml: str, graph_name: str) -> Path:
    (tmp_path / ".doxygen-index.toml").write_text(toml, encoding="utf-8")
    return tmp_path


class TestLoadConfig:
    def test_codegraph_toml(self, tmp_path: Path):
        (tmp_path / ".codegraph.toml").write_text(CODEGRAPH_TOML, encoding="utf-8")
        config, project = load_config(tmp_path)
        assert config.name == "my-project"
        assert config.tag == "design"
        assert config.graph_json == (tmp_path / "build" / "docs" / "my-project.json")
        assert config.source_file == ".codegraph.toml"
        assert project == tmp_path.resolve()

    def test_doxygen_toml_default_output_dir(self, tmp_path: Path):
        (tmp_path / ".doxygen-index.toml").write_text(DOXYGEN_TOML, encoding="utf-8")
        config, _ = load_config(tmp_path)
        assert config.name == "cpp-sqlite"
        assert config.tag == "design"
        assert config.graph_json == (tmp_path / "codegraph" / "cpp-sqlite.json")
        assert config.source_file == ".doxygen-index.toml"

    def test_doxygen_toml_custom_tag(self, tmp_path: Path):
        toml = DOXYGEN_TOML.replace(
            'output_dir = "codegraph"', 'output_dir = "codegraph"\ntag = "as-built"'
        )
        (tmp_path / ".doxygen-index.toml").write_text(toml, encoding="utf-8")
        config, _ = load_config(tmp_path)
        assert config.tag == "as-built"

    def test_no_config_exits(self, tmp_path: Path):
        with pytest.raises(SystemExit):
            load_config(tmp_path)

    def test_missing_name_exits(self, tmp_path: Path):
        (tmp_path / ".codegraph.toml").write_text(
            "[project]\noutput_dir = \"x\"\n", encoding="utf-8"
        )
        with pytest.raises(SystemExit):
            load_config(tmp_path)


class TestCliDiscovery:
    def test_project_dir_discovery_end_to_end(self, tmp_path: Path, capsys):
        # Seed a doxygen-index-style project with the exported graph JSON.
        out_dir = tmp_path / "codegraph"
        out_dir.mkdir()
        graph = json.loads(GOLDEN.read_text())
        (out_dir / "cpp-sqlite.json").write_text(
            json.dumps(graph), encoding="utf-8"
        )
        (tmp_path / ".doxygen-index.toml").write_text(DOXYGEN_TOML, encoding="utf-8")

        rc = main(["--project-dir", str(tmp_path), "--dry-run"])
        out = capsys.readouterr().out
        assert rc == 0
        assert "include/cpp_sqlite/Migration.hpp" in out

    def test_discovery_missing_graph_json(self, tmp_path: Path, capsys):
        (tmp_path / ".doxygen-index.toml").write_text(DOXYGEN_TOML, encoding="utf-8")
        rc = main(["--project-dir", str(tmp_path), "--dry-run"])
        captured = capsys.readouterr()
        assert rc == 1
        assert "graph JSON not found" in captured.err
