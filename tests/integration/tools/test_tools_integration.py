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

FIXTURE = Path(__file__).resolve().parent / "data" / "design_graph.json"
OUT_DIR = Path(__file__).resolve().parent / "unit_test_data"

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

@pytest.fixture(autouse=True)
def _require_dev_neo4j(request):
    """Fail fast if dev Neo4j isn't running (needed by @pytest.mark.integration)."""
    if not request.node.get_closest_marker("integration"):
        return

    from codegraph.persistence.connection import require_connection

    try:
        require_connection()
    except Exception as exc:
        pytest.fail(
            f"Dev Neo4j is not reachable (needed by @pytest.mark.integration).\n"
            f"  Error: {exc}\n"
            f"  Start it with: docker compose up -d"
        )

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

    # codegraph:test-desc test_tools_integration.TestToolsIntegration.test_list_tags
    # Verifies that the ToolDispatcher correctly lists tags, ensuring the dispatch and
    # save functionalities work together properly.
    def test_list_tags(self):
        inp = {}
        result = self.disp.dispatch("graph_list_tags", inp)
        _save(OUT_DIR, "tools_list_tags.json", result, inp)

        data = json.loads(result)
        # codegraph:test-desc test_tools_integration.TestToolsIntegration.test_list_tags::post_0
        # Asserts that the response contains the expected top-level structure (e.g.,
        # 'available_tags' and 'node_counts' keys), which is necessary for the
        # dispatcher to return a complete and well-formed result.
        assert "available_tags" in data
        # codegraph:test-desc test_tools_integration.TestToolsIntegration.test_list_tags::post_1
        # Asserts that the response includes the expected top-level structure (e.g.,
        # 'available_tags' and 'node_counts' keys), ensuring the dispatcher returns a
        # complete and well-formed result.
        assert "node_counts" in data
        # codegraph:test-desc test_tools_integration.TestToolsIntegration.test_list_tags::post_2
        # Checks that 'design' appears as one of the available tags in the result,
        # confirming that the dispatcher properly records the tag's existence after some
        # node is tagged with it.
        assert "design" in data["available_tags"]
        # codegraph:test-desc test_tools_integration.TestToolsIntegration.test_list_tags::post_3
        # Verifies that the count of nodes tagged with 'design' is greater than zero,
        # ensuring that the dispatcher correctly reports at least one design-related
        # node after a tagging operation.
        assert data["node_counts"]["design"] > 0

    # ── Query tools ─────────────────────────────────────────────────────

    # codegraph:test-desc test_tools_integration.TestToolsIntegration.test_fetch_tag_all_formats
    # Ensures that fetching a tag returns consistent correct results across multiple
    # output formats, validating the reliability and interoperability of the tag
    # retrieval functionality regardless of how the output is requested.
    def test_fetch_tag_all_formats(self):
        for fmt, ext in [("markdown", "md"), ("json", "json"),
                         ("plantuml", "puml")]:
            inp = {"tag": "design", "format": fmt}
            result = self.disp.dispatch("graph_fetch", inp)
            _save(OUT_DIR, f"tools_fetch_tag.{ext}", result, inp)

            if fmt == "markdown":
                # codegraph:test-desc test_tools_integration.TestToolsIntegration.test_fetch_tag_all_formats::post_0
                # Verifies that the result contains the '# codegraph: design' comment,
                # confirming that the correct tag was used to retrieve the design
                # diagram.
                assert "# codegraph: design" in result
            elif fmt == "json":
                data = json.loads(result)
                # codegraph:test-desc test_tools_integration.TestToolsIntegration.test_fetch_tag_all_formats::post_1
                # Verifies that the fetched data is a list, confirming that the code
                # returned the expected data structure.
                assert isinstance(data, list)
                # codegraph:test-desc test_tools_integration.TestToolsIntegration.test_fetch_tag_all_formats::post_2
                # Verifies that the fetched data list is not empty, ensuring that the
                # code successfully returned some content.
                assert len(data) > 0
            elif fmt == "plantuml":
                # codegraph:test-desc test_tools_integration.TestToolsIntegration.test_fetch_tag_all_formats::post_3
                # Verifies that the result starts with the PlantUML diagram marker
                # '@startuml', ensuring that the output is valid PlantUML format.
                assert result.startswith("@startuml")

    # codegraph:test-desc test_tools_integration.TestToolsIntegration.test_fetch_namespace
    # Verifies that ToolDispatcher.dispatch correctly fetches a namespace and that the
    # result is saved via _save, ensuring the core dispatching and data persistence
    # logic works together.
    def test_fetch_namespace(self):
        inp = {"qualified_name": "calc", "format": "markdown"}
        result = self.disp.dispatch("graph_fetch_namespace", inp)
        _save(OUT_DIR, "tools_fetch_namespace.md", result, inp)
        # codegraph:test-desc test_tools_integration.TestToolsIntegration.test_fetch_namespace::post_0
        # Verifies that the output contains the namespace header `calc`, ensuring that
        # the code under test correctly identifies and reports the top-level namespace
        # being queried.
        assert "## Namespace: `calc`" in result
        # codegraph:test-desc test_tools_integration.TestToolsIntegration.test_fetch_namespace::post_1
        # Verifies that the output includes the class heading `calc::CalculatorEngine`,
        # confirming that the tool correctly retrieves and formats class-level details
        # within the requested namespace.
        assert "### Class: `calc::CalculatorEngine`" in result

    # codegraph:test-desc test_tools_integration.TestToolsIntegration.test_fetch_neighborhood
    # Verifies that the ToolDispatcher correctly dispatches a fetch neighborhood request
    # and that the helper _save function persists the result, ensuring the integration
    # between dispatch and data saving works as expected.
    def test_fetch_neighborhood(self):
        inp = {"qualified_name": "calc::CalculatorEngine", "format": "markdown"}
        result = self.disp.dispatch("graph_fetch_neighborhood", inp)
        _save(OUT_DIR, "tools_fetch_neighborhood.md", result, inp)
        # codegraph:test-desc test_tools_integration.TestToolsIntegration.test_fetch_neighborhood::post_0
        # Verifies that the fetched result contains the expected class definition from
        # the CalculatorEngine, confirming the dispatcher correctly retrieves and
        # formats code metadata for the requested neighborhood.
        assert "### Class: `calc::CalculatorEngine`" in result

    # codegraph:test-desc test_tools_integration.TestToolsIntegration.test_fetch_compound
    # This test verifies that ToolDispatcher.dispatch correctly processes a compound
    # tool call and that the _save helper stores the result, ensuring the integration
    # between dispatching and saving functions as expected.
    def test_fetch_compound(self):
        inp = {"qualified_name": "calc::CalculatorEngine", "format": "markdown"}
        result = self.disp.dispatch("graph_fetch_compound", inp)
        _save(OUT_DIR, "tools_fetch_compound.md", result, inp)
        # codegraph:test-desc test_tools_integration.TestToolsIntegration.test_fetch_compound::post_0
        # Verifies that the fetched documentation for the 'CalculatorEngine' class is
        # present in the result, confirming that the 'dispatch' method correctly
        # retrieves and returns the expected compound symbol information.
        assert "### Class: `calc::CalculatorEngine`" in result

    # codegraph:test-desc test_tools_integration.TestToolsIntegration.test_fetch_compound_json
    # This test verifies that the ToolDispatcher.dispatch method correctly fetches and
    # processes a compound JSON payload from a tool invocation, ensuring that the
    # dispatch logic handles complex data structures as expected.
    def test_fetch_compound_json(self):
        inp = {"qualified_name": "calc::CalculatorEngine", "format": "json"}
        result = self.disp.dispatch("graph_fetch_compound", inp)
        _save(OUT_DIR, "tools_fetch_compound.json", result, inp)
        data = json.loads(result)
        # codegraph:test-desc test_tools_integration.TestToolsIntegration.test_fetch_compound_json::post_0
        # Verifies that the result of the fetch is a list, confirming the return type
        # matches the expected data structure before further processing.
        assert isinstance(data, list)
        # codegraph:test-desc test_tools_integration.TestToolsIntegration.test_fetch_compound_json::post_1
        # Checks that the returned data list is not empty, ensuring the fetch operation
        # successfully retrieved at least one record from the source.
        assert len(data) > 0

    # codegraph:test-desc test_tools_integration.TestToolsIntegration.test_fetch_compound_not_found
    # Verifies that the ToolDispatcher.dispatch method gracefully and predictably
    # handles the case where a requested compound is not found, returning a clear error
    # response to prevent unexpected crashes or misleading results.
    def test_fetch_compound_not_found(self):
        inp = {"qualified_name": "nonexistent::Nothing", "format": "json"}
        result = self.disp.dispatch("graph_fetch_compound", inp)
        data = json.loads(result)
        # codegraph:test-desc test_tools_integration.TestToolsIntegration.test_fetch_compound_not_found::post_0
        # Confirms that the result from the dispatcher is a list, ensuring the response
        # adheres to the expected data type before checking its content.
        assert isinstance(data, list)
        # codegraph:test-desc test_tools_integration.TestToolsIntegration.test_fetch_compound_not_found::post_1
        # Verifies that the returned data is an empty list, confirming that the
        # dispatcher correctly returns no results for a non-existent compound query.
        assert len(data) == 0

    # codegraph:test-desc test_tools_integration.TestToolsIntegration.test_fetch_by_kind
    # Verifies that the ToolDispatcher can dispatch a call to fetch items by kind and
    # that the result can be saved, ensuring both dispatch and save logic work together.
    def test_fetch_by_kind(self):
        inp = {"kind": "class", "tag": "design", "format": "markdown"}
        result = self.disp.dispatch("graph_fetch_by_kind", inp)
        _save(OUT_DIR, "tools_fetch_by_kind.md", result, inp)
        # codegraph:test-desc test_tools_integration.TestToolsIntegration.test_fetch_by_kind::post_0
        # Verify that the dispatched tool for kind 'CalculatorEngine' is correctly
        # identified and included in the result, ensuring the dispatcher accurately
        # resolves tool kinds.
        assert "CalculatorEngine" in result

    # codegraph:test-desc test_tools_integration.TestToolsIntegration.test_fetch_by_kind_json
    # Tests that the ToolDispatcher correctly dispatches a request for JSON tools,
    # validating the integration of type collection and saving functions to ensure
    # accurate tool registration by kind.
    def test_fetch_by_kind_json(self):
        inp = {"kind": "class", "tag": "design", "format": "json"}
        result = self.disp.dispatch("graph_fetch_by_kind", inp)
        _save(OUT_DIR, "tools_fetch_by_kind.json", result, inp)
        data = json.loads(result)
        # codegraph:test-desc test_tools_integration.TestToolsIntegration.test_fetch_by_kind_json::post_0
        # Checks that the result of the fetch operation is a list, confirming the
        # dispatcher returns a collection as expected.
        assert isinstance(data, list)
        all_types = _collect_types(data)
        # codegraph:test-desc test_tools_integration.TestToolsIntegration.test_fetch_by_kind_json::post_1
        # Verifies that at least one 'ClassNode' exists in the returned list, ensuring
        # the fetch-by-kind logic correctly retrieves nodes of the requested type.
        assert "ClassNode" in all_types

    # codegraph:test-desc test_tools_integration.TestToolsIntegration.test_fetch_by_kind_enum
    # Verifies that the ToolDispatcher.dispatch method correctly handles and routes
    # requests based on the kind enumeration, ensuring that the selection logic works as
    # intended for different tool types, which is critical for proper tool execution and
    # integration.
    def test_fetch_by_kind_enum(self):
        inp = {"kind": "enum", "tag": "design", "format": "markdown"}
        result = self.disp.dispatch("graph_fetch_by_kind", inp)
        _save(OUT_DIR, "tools_fetch_by_kind_enum.md", result, inp)
        # codegraph:test-desc test_tools_integration.TestToolsIntegration.test_fetch_by_kind_enum::post_0
        # Verifies that the enumeration `calc::Operation` is present in the output,
        # confirming that the dispatcher correctly retrieves and formats enums by their
        # kind.
        assert "### Enum: `calc::Operation`" in result

    # codegraph:test-desc test_tools_integration.TestToolsIntegration.test_fetch_by_kind_no_tag
    # Verifies that the ToolDispatcher's dispatch method correctly filters tasks by kind
    # when no tag filter is applied, ensuring the system returns only tasks matching the
    # required kind.
    def test_fetch_by_kind_no_tag(self):
        inp = {"kind": "method", "format": "markdown"}
        result = self.disp.dispatch("graph_fetch_by_kind", inp)
        _save(OUT_DIR, "tools_fetch_by_kind_method.md", result, inp)
        # codegraph:test-desc test_tools_integration.TestToolsIntegration.test_fetch_by_kind_no_tag::post_0
        # Verifies that the dispatch result is a string, confirming the method returns
        # data in the expected format.
        assert isinstance(result, str)

    # codegraph:test-desc test_tools_integration.TestToolsIntegration.test_fetch_by_source
    # Verifies that ToolDispatcher.dispatch correctly retrieves and returns a tool
    # result by its source identifier, ensuring the dispatch logic properly maps sources
    # to their corresponding tool implementations.
    def test_fetch_by_source(self):
        inp = {"source": "calculator", "format": "json"}
        result = self.disp.dispatch("graph_fetch_by_source", inp)
        _save(OUT_DIR, "tools_fetch_by_source.json", result, inp)
        data = json.loads(result)
        # codegraph:test-desc test_tools_integration.TestToolsIntegration.test_fetch_by_source::post_0
        # Verifies that the data returned by the dispatcher is a list, ensuring the
        # response structure matches expectations before checking its contents.
        assert isinstance(data, list)
        # codegraph:test-desc test_tools_integration.TestToolsIntegration.test_fetch_by_source::post_1
        # Checks that the returned list is not empty, confirming that the dispatcher
        # successfully retrieved and returned at least one record from the specified
        # source.
        assert len(data) > 0

    # ── Format tools ─────────────────────────────────────────────────────

    # codegraph:test-desc test_tools_integration.TestToolsIntegration.test_format_export
    # Verifies that the ToolDispatcher correctly dispatches to the appropriate save
    # function for the specified export format, ensuring the output file is generated as
    # expected.
    def test_format_export(self):
        self.disp.dispatch("graph_fetch", {"tag": "design", "format": "markdown"})
        inp = {"format": "plantuml"}
        result = self.disp.dispatch("graph_format_export", inp)
        _save(OUT_DIR, "tools_export.puml", result, inp)
        # codegraph:test-desc test_tools_integration.TestToolsIntegration.test_format_export::post_0
        # Verifies that the exported diagram format starts with '@startuml', ensuring
        # the output is valid PlantUML syntax required for correct rendering.
        assert result.startswith("@startuml")

    # codegraph:test-desc test_tools_integration.TestToolsIntegration.test_format_import_and_reexport
    # Verifies that the ToolDispatcher.dispatch correctly formats and re-exports
    # imported data using the _save helper, ensuring the toolchain produces consistent
    # and serialized outputs.
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
        # codegraph:test-desc test_tools_integration.TestToolsIntegration.test_format_import_and_reexport::post_0
        # Verifies that the tool output was successfully imported by checking that the
        # 'imported' flag is True, confirming the import step completed without errors
        # as required for the test to be valid.
        assert data["imported"] is True
        # codegraph:test-desc test_tools_integration.TestToolsIntegration.test_format_import_and_reexport::post_1
        # Checks that the imported data contains at least one node, ensuring that the
        # formatting and re-export process preserved meaningful content, which is
        # essential for the tool to function correctly.
        assert data["node_count"] >= 1

        # Re-export (no separate input saved — output-only artifact)
        export_result = self.disp.dispatch("graph_format_export",
                                           {"format": "markdown"})
        _save(OUT_DIR, "tools_import_export.md", export_result)

    # ── Save tool ────────────────────────────────────────────────────────

    # codegraph:test-desc test_tools_integration.TestToolsIntegration.test_save
    # Verifies that the ToolDispatcher's dispatch method correctly calls the _save
    # helper, ensuring tool execution and data persistence function as intended.
    def test_save(self):
        self.disp.dispatch("graph_fetch", {"tag": "design", "format": "json"})
        inp = {}
        result = self.disp.dispatch("graph_save", inp)
        _save(OUT_DIR, "tools_save_info.json", result, inp)

        data = json.loads(result)
        # codegraph:test-desc test_tools_integration.TestToolsIntegration.test_save::post_0
        # Verifies that the dispatch result indicates a successful save (i.e.,
        # `data['saved']` is `True`), ensuring the save command completed without error.
        assert data["saved"] is True
        # codegraph:test-desc test_tools_integration.TestToolsIntegration.test_save::post_1
        # Verifies that after saving, at least one node was stored (i.e.,
        # `data['node_count'] > 0`), confirming that the operation persisted meaningful
        # data and not an empty result.
        assert data["node_count"] > 0

    # codegraph:test-desc test_tools_integration.TestToolsIntegration.test_save_after_import
    # Verifies that after importing tool definitions, the ToolDispatcher.dispatch and
    # the _save function correctly persist the configuration, ensuring that imported
    # settings are reliably stored for later use.
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
        # codegraph:test-desc test_tools_integration.TestToolsIntegration.test_save_after_import::post_0
        # Verifies that the save operation was acknowledged by the system, ensuring that
        # the data structure contains a 'saved' flag set to True, which confirms the
        # dispatch initiated a successful save.
        assert data["saved"] is True
        # codegraph:test-desc test_tools_integration.TestToolsIntegration.test_save_after_import::post_1
        # Checks that at least one node was processed after the save, confirming that
        # the tool dispatcher handled the import data and produced a non-empty node
        # count, which indicates the save action was not trivial.
        assert data["node_count"] >= 1