"""Integration test: populate Neo4j from design_graph.json, exercise every tool.

Loads the fixture graph into Neo4j, then calls each tool in the
CodeGraphDispatcher against the live data.  Saves both tool inputs
(``.input.json``) and outputs to gitignored files in ``unit_test_data/``.

Artefacts saved (stem.* for output, stem.input.json for input)::

    unit_test_data/tools_list_tags.json / .input.json
    unit_test_data/tools_fetch_tag.md  / .input.json
    unit_test_data/tools_fetch_tag.json / .input.json
    unit_test_data/tools_fetch_tag.puml / .input.json
    unit_test_data/tools_fetch_namespace.md / .input.json
    unit_test_data/tools_fetch_neighborhood.md / .input.json
    unit_test_data/tools_fetch_compound.md / .input.json
    unit_test_data/tools_fetch_compound.json / .input.json
    unit_test_data/tools_fetch_by_kind.md / .input.json
    unit_test_data/tools_fetch_by_kind.json / .input.json
    unit_test_data/tools_fetch_by_kind_enum.md / .input.json
    unit_test_data/tools_fetch_by_kind_method.md / .input.json
    unit_test_data/tools_fetch_by_source.json / .input.json
    unit_test_data/tools_export.puml / .input.json
    unit_test_data/tools_import_info.json / .input.json
    unit_test_data/tools_import_export.md / (no input — re-export)
    unit_test_data/tools_save_info.json / .input.json
    unit_test_data/tools_save_after_import.json / .input.json

Requires Neo4j for the ``to_neo4j()`` call.
"""

import json
from pathlib import Path

import pytest

from codegraph.graph import LayerGraph
from codegraph.tools import CodeGraphDispatcher

DATA_DIR = Path(__file__).resolve().parent / "data"
FIXTURE = DATA_DIR / "design_graph.json"
OUT_DIR = Path(__file__).resolve().parent.parent / "unit_test_data"


def _save(out_dir: Path, stem: str, content: str,
         tool_input: dict | None = None) -> None:
    """Write tool output and input to out_dir.

    Saves ``stem`` (output) and, if *tool_input* is given,
    ``<stem_without_ext>.input.json``.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / stem).write_text(content, encoding="utf-8")
    if tool_input is not None:
        input_stem = Path(stem).stem + ".input.json"
        (out_dir / input_stem).write_text(
            json.dumps(tool_input, indent=2),
            encoding="utf-8",
        )


def _collect_types(entries: list[dict]) -> set[str]:
    """Walk nested serialized data and collect all node types."""
    types: set[str] = set()
    for entry in entries:
        if "type" in entry:
            types.add(entry["type"])
        for child in entry.get("composes", []):
            types |= _collect_types([child])
    return types


# ── Full integration: fixture → Neo4j → every tool → files ────────────────


@pytest.mark.integration
class TestToolsIntegration:
    """End-to-end test: populate Neo4j, exercise every tool, save results."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        """Load fixture, persist to Neo4j, create dispatcher."""
        with open(FIXTURE) as f:
            data = json.load(f)
        self.graph = LayerGraph.deserialize(data)
        self.graph.to_neo4j()
        self.disp = CodeGraphDispatcher()
        OUT_DIR.mkdir(exist_ok=True)

    # ── Info tools ──────────────────────────────────────────────────────

    def test_list_tags(self):
        inp = {}
        result = self.disp.dispatch("graph_list_tags", inp)
        _save(OUT_DIR, "tools_list_tags.json", result, inp)

        data = json.loads(result)
        assert "available_tags" in data
        assert "node_counts" in data
        assert "design" in data["available_tags"]
        assert data["node_counts"]["design"] > 0

    # ── Query tools ─────────────────────────────────────────────────────

    def test_fetch_tag_all_formats(self):
        for fmt, ext in [("markdown", "md"), ("json", "json"),
                         ("plantuml", "puml")]:
            inp = {"tag": "design", "format": fmt}
            result = self.disp.dispatch("graph_fetch", inp)
            _save(OUT_DIR, f"tools_fetch_tag.{ext}", result, inp)

            if fmt == "markdown":
                assert "# codegraph: design" in result
            elif fmt == "json":
                data = json.loads(result)
                assert isinstance(data, list)
                assert len(data) > 0
            elif fmt == "plantuml":
                assert result.startswith("@startuml")

    def test_fetch_namespace(self):
        inp = {"qualified_name": "calc", "format": "markdown"}
        result = self.disp.dispatch("graph_fetch_namespace", inp)
        _save(OUT_DIR, "tools_fetch_namespace.md", result, inp)
        assert "## Namespace: `calc`" in result
        assert "### Class: `calc::CalculatorEngine`" in result

    def test_fetch_neighborhood(self):
        inp = {"qualified_name": "calc::CalculatorEngine", "format": "markdown"}
        result = self.disp.dispatch("graph_fetch_neighborhood", inp)
        _save(OUT_DIR, "tools_fetch_neighborhood.md", result, inp)
        assert "### Class: `calc::CalculatorEngine`" in result

    def test_fetch_compound(self):
        inp = {"qualified_name": "calc::CalculatorEngine", "format": "markdown"}
        result = self.disp.dispatch("graph_fetch_compound", inp)
        _save(OUT_DIR, "tools_fetch_compound.md", result, inp)
        assert "### Class: `calc::CalculatorEngine`" in result

    def test_fetch_compound_json(self):
        inp = {"qualified_name": "calc::CalculatorEngine", "format": "json"}
        result = self.disp.dispatch("graph_fetch_compound", inp)
        _save(OUT_DIR, "tools_fetch_compound.json", result, inp)
        data = json.loads(result)
        assert isinstance(data, list)
        assert len(data) > 0

    def test_fetch_compound_not_found(self):
        inp = {"qualified_name": "nonexistent::Nothing", "format": "json"}
        result = self.disp.dispatch("graph_fetch_compound", inp)
        data = json.loads(result)
        assert isinstance(data, list)
        assert len(data) == 0

    def test_fetch_by_kind(self):
        inp = {"kind": "class", "tag": "design", "format": "markdown"}
        result = self.disp.dispatch("graph_fetch_by_kind", inp)
        _save(OUT_DIR, "tools_fetch_by_kind.md", result, inp)
        assert "CalculatorEngine" in result

    def test_fetch_by_kind_json(self):
        inp = {"kind": "class", "tag": "design", "format": "json"}
        result = self.disp.dispatch("graph_fetch_by_kind", inp)
        _save(OUT_DIR, "tools_fetch_by_kind.json", result, inp)
        data = json.loads(result)
        assert isinstance(data, list)
        all_types = _collect_types(data)
        assert "ClassNode" in all_types

    def test_fetch_by_kind_enum(self):
        inp = {"kind": "enum", "tag": "design", "format": "markdown"}
        result = self.disp.dispatch("graph_fetch_by_kind", inp)
        _save(OUT_DIR, "tools_fetch_by_kind_enum.md", result, inp)
        assert "### Enum: `calc::Operation`" in result

    def test_fetch_by_kind_no_tag(self):
        inp = {"kind": "method", "format": "markdown"}
        result = self.disp.dispatch("graph_fetch_by_kind", inp)
        _save(OUT_DIR, "tools_fetch_by_kind_method.md", result, inp)
        assert isinstance(result, str)

    def test_fetch_by_source(self):
        inp = {"source": "calculator", "format": "json"}
        result = self.disp.dispatch("graph_fetch_by_source", inp)
        _save(OUT_DIR, "tools_fetch_by_source.json", result, inp)
        data = json.loads(result)
        assert isinstance(data, list)
        assert len(data) > 0

    # ── Format tools ─────────────────────────────────────────────────────

    def test_format_export(self):
        self.disp.dispatch("graph_fetch", {"tag": "design", "format": "markdown"})
        inp = {"format": "plantuml"}
        result = self.disp.dispatch("graph_format_export", inp)
        _save(OUT_DIR, "tools_export.puml", result, inp)
        assert result.startswith("@startuml")

    def test_format_import_and_reexport(self):
        md_text = (
            "## Namespace: `tools_test`\n\n"
            "### Class: `tools_test::TestClass`\n"
            "A test class created via the tools integration test.\n"
            "**Public methods:**\n"
            "- `example_method()` — Example method\n"
        )
        inp = {"text": md_text, "format": "markdown"}
        result = self.disp.dispatch("graph_format_import", inp)
        _save(OUT_DIR, "tools_import_info.json", result, inp)

        data = json.loads(result)
        assert data["imported"] is True
        assert data["node_count"] >= 1

        # Re-export (no separate input saved — output-only artifact)
        export_result = self.disp.dispatch("graph_format_export",
                                           {"format": "markdown"})
        _save(OUT_DIR, "tools_import_export.md", export_result)

    # ── Save tool ────────────────────────────────────────────────────────

    def test_save(self):
        self.disp.dispatch("graph_fetch", {"tag": "design", "format": "json"})
        inp = {}
        result = self.disp.dispatch("graph_save", inp)
        _save(OUT_DIR, "tools_save_info.json", result, inp)

        data = json.loads(result)
        assert data["saved"] is True
        assert data["node_count"] > 0

    def test_save_after_import(self):
        md_text = (
            "## Namespace: `tools_save_test`\n\n"
            "### Class: `tools_save_test::SavedClass`\n"
            "A class saved via tools integration test.\n"
        )
        self.disp.dispatch("graph_format_import",
                           {"text": md_text, "format": "markdown"})
        inp = {}
        result = self.disp.dispatch("graph_save", inp)
        _save(OUT_DIR, "tools_save_after_import.json", result, inp)

        data = json.loads(result)
        assert data["saved"] is True
        assert data["node_count"] >= 1