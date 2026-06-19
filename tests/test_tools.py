"""Tests for codegraph agent tools.

Covers tool registration, schema validation, dispatch, and integration
with Neo4j (requires running Neo4j instance).
"""

import json
import subprocess
from pathlib import Path

import pytest

from codegraph.tools import (
    CodeGraphDispatcher,
    ToolDispatcher,
    create_dispatcher,
)
from codegraph.graph import LayerGraph, CompositeEntry
from codegraph.models.namespace import NamespaceNode
from codegraph.models.compound import ClassNode

DATA_DIR = Path(__file__).resolve().parent / "data"


# ── Basic dispatch tests (no Neo4j required) ──────────────────────────────


class TestToolRegistration:
    def test_create_dispatcher(self):
        d = create_dispatcher()
        assert isinstance(d, CodeGraphDispatcher)
        assert len(d.all_tool_schemas) == 21  # 10 original + 7 discovery + 4 lookup

    def test_all_tools_have_names(self):
        d = create_dispatcher()
        names = {s["name"] for s in d.all_tool_schemas}
        assert "graph_fetch" in names
        assert "graph_fetch_compound" in names
        assert "graph_fetch_by_kind" in names
        assert "graph_list_tags" in names
        assert "graph_format_export" in names
        assert "graph_format_import" in names
        assert "graph_save" in names

    def test_all_schemas_valid(self):
        d = create_dispatcher()
        for s in d.all_tool_schemas:
            assert "name" in s
            assert "description" in s
            assert "input_schema" in s
            schema = s["input_schema"]
            assert "type" in schema
            assert schema["type"] == "object"
            if "properties" in schema:
                for prop_name, prop in schema["properties"].items():
                    assert "type" in prop or "enum" in prop or "anyOf" in prop

    def test_unknown_tool_returns_error(self):
        d = create_dispatcher()
        result = json.loads(d.dispatch("nonexistent", {}))
        assert "error" in result
        assert "Unknown tool" in result["error"]

    def test_duplicate_registration_raises(self):
        d = ToolDispatcher()
        d.register("test", {
            "name": "test",
            "description": "A test",
            "input_schema": {"type": "object", "properties": {}, "required": []},
        }, lambda inp: "ok")
        with pytest.raises(ValueError, match="Duplicate"):
            d.register("test", {}, lambda inp: "fail")


class TestToolDispatch:
    def test_custom_tool_dispatch(self):
        d = ToolDispatcher()
        d.register("echo", {
            "name": "echo",
            "description": "Echo back",
            "input_schema": {
                "type": "object",
                "properties": {"msg": {"type": "string", "description": "Message"}},
                "required": ["msg"],
            },
        }, lambda inp: json.dumps({"echo": inp["msg"]}))

        result = json.loads(d.dispatch("echo", {"msg": "hello"}))
        assert result["echo"] == "hello"

    def test_all_tool_schemas_property(self):
        d = ToolDispatcher()
        assert d.all_tool_schemas == []
        d.register("a", {
            "name": "a",
            "description": "A",
            "input_schema": {"type": "object", "properties": {}, "required": []},
        }, lambda inp: "ok")
        assert len(d.all_tool_schemas) == 1


# ── Neo4j-dependent integration tests ──────────────────────────────────────


@pytest.mark.integration
class TestCodeGraphDispatcherIntegration:
    """Tests that require Neo4j with data loaded."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        """Load the fixture graph into Neo4j."""
        with open(DATA_DIR / "design_graph.json") as f:
            data = json.load(f)
        self.graph = LayerGraph.deserialize(data)
        self.graph.to_neo4j()
        self.dispatcher = CodeGraphDispatcher()

    def test_list_tags(self):
        result = json.loads(self.dispatcher.dispatch("graph_list_tags", {}))
        assert "available_tags" in result
        assert "node_counts" in result
        assert "design" in result["available_tags"]
        assert result["node_counts"]["design"] > 0

    def test_fetch_by_tag_markdown(self):
        result = self.dispatcher.dispatch("graph_fetch", {
            "tag": "design",
            "format": "markdown",
        })
        assert "# codegraph: design" in result
        assert "## Namespace: `calc`" in result
        assert "## Relationships" in result

    def test_fetch_by_tag_json(self):
        result = self.dispatcher.dispatch("graph_fetch", {
            "tag": "design",
            "format": "json",
        })
        data = json.loads(result)
        assert isinstance(data, list)
        assert len(data) > 0

    def test_fetch_by_tag_plantuml(self):
        result = self.dispatcher.dispatch("graph_fetch", {
            "tag": "design",
            "format": "plantuml",
        })
        assert result.startswith("@startuml")

    def test_fetch_namespace(self):
        result = self.dispatcher.dispatch("graph_fetch_namespace", {
            "qualified_name": "calc",
            "format": "markdown",
        })
        assert "## Namespace: `calc`" in result

    def test_fetch_neighborhood(self):
        result = self.dispatcher.dispatch("graph_fetch_neighborhood", {
            "qualified_name": "calc::CalculatorEngine",
            "format": "markdown",
        })
        assert "### Class: `calc::CalculatorEngine`" in result

    def test_fetch_compound(self):
        result = self.dispatcher.dispatch("graph_fetch_compound", {
            "qualified_name": "calc::CalculatorEngine",
            "format": "markdown",
        })
        assert "### Class: `calc::CalculatorEngine`" in result

    def test_fetch_by_kind(self):
        result = self.dispatcher.dispatch("graph_fetch_by_kind", {
            "kind": "class",
            "tag": "design",
            "format": "markdown",
        })
        assert "CalculatorEngine" in result

    def test_fetch_by_source(self):
        result = self.dispatcher.dispatch("graph_fetch_by_source", {
            "source": "calculator",
            "format": "json",
        })
        data = json.loads(result)
        assert isinstance(data, list)
        assert len(data) > 0

    def test_save_requires_fetch(self):
        d = CodeGraphDispatcher()
        result = json.loads(d.dispatch("graph_save", {}))
        assert "error" in result
        assert "No graph loaded" in result["error"]

    def test_format_export_requires_fetch(self):
        d = CodeGraphDispatcher()  # fresh dispatcher, no fetch
        result = json.loads(d.dispatch("graph_format_export", {
            "format": "markdown",
        }))
        assert "error" in result
        assert "No graph loaded" in result["error"]

    def test_format_export_after_fetch(self):
        self.dispatcher.dispatch("graph_fetch", {
            "tag": "design",
            "format": "markdown",
        })
        result = self.dispatcher.dispatch("graph_format_export", {
            "format": "plantuml",
        })
        assert result.startswith("@startuml")

    def test_format_import_markdown(self):
        md_text = (
            "## Namespace: `test_ns`\n\n"
            "### Class: `test_ns::TestClass`\n"
            "A test class.\n"
        )
        result = json.loads(self.dispatcher.dispatch("graph_format_import", {
            "text": md_text,
            "format": "markdown",
        }))
        assert result["imported"] is True
        assert result["node_count"] >= 1

    def test_import_caches_graph(self):
        md_text = (
            "## Namespace: `test_ns`\n\n"
            "### Class: `test_ns::TestClass`\n"
        )
        self.dispatcher.dispatch("graph_format_import", {
            "text": md_text,
            "format": "markdown",
        })
        # Should now be able to format_export without error
        result = self.dispatcher.dispatch("graph_format_export", {
            "format": "json",
        })
        data = json.loads(result)
        assert isinstance(data, list)
        assert len(data) > 0

    def test_save_after_fetch(self):
        """Fetch a graph then save it back."""
        self.dispatcher.dispatch("graph_fetch", {
            "tag": "design",
            "format": "json",
        })
        result = json.loads(self.dispatcher.dispatch("graph_save", {}))
        assert result["saved"] is True
        assert result["node_count"] > 0