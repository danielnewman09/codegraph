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

# ── Basic dispatch tests (no Neo4j required) ──────────────────────────────

class TestToolRegistration:
    # codegraph:test-desc test_tools.TestToolRegistration.test_create_dispatcher
    # Verifies that create_dispatcher correctly instantiates a dispatcher from the
    # codegraph.tools.dispatcher module, ensuring the tool registration and dispatch
    # mechanism functions as expected for system reliability.
    def test_create_dispatcher(self):
        d = create_dispatcher()
        # codegraph:test-desc test_tools.TestToolRegistration.test_create_dispatcher::post_0
        # Verifies that the dispatcher returned by `create_dispatcher` is an instance of
        # `CodeGraphDispatcher`, ensuring the function produces the correct object type.
        assert isinstance(d, CodeGraphDispatcher)
        # codegraph:test-desc test_tools.TestToolRegistration.test_create_dispatcher::post_1
        # Verifies that the dispatcher's `all_tool_schemas` list contains exactly 21
        # tool schemas, confirming that all expected tools have been registered
        # correctly.
        assert len(d.all_tool_schemas) == 23  # 10 original + 7 discovery + 4 lookup + 2 container

    # codegraph:test-desc test_tools.TestToolRegistration.test_all_tools_have_names
    # This test verifies that every tool registered within the code-under-test's
    # dispatcher has a non-empty name attribute, ensuring that tool references are
    # identifiable and preventing runtime errors from missing or blank tool names.
    def test_all_tools_have_names(self):
        d = create_dispatcher()
        names = {s["name"] for s in d.all_tool_schemas}
        # codegraph:test-desc test_tools.TestToolRegistration.test_all_tools_have_names::post_0
        # Verifies that 'graph_fetch' is included in the set of registered tool names,
        # confirming the basic tool for fetching graph data is properly registered.
        assert "graph_fetch" in names
        # codegraph:test-desc test_tools.TestToolRegistration.test_all_tools_have_names::post_1
        # Verifies that 'graph_fetch_compound' is included in the set of registered tool
        # names, confirming the compound fetch tool is properly registered.
        assert "graph_fetch_compound" in names
        # codegraph:test-desc test_tools.TestToolRegistration.test_all_tools_have_names::post_2
        # Verifies that 'graph_fetch_by_kind' is included in the set of registered tool
        # names, confirming the tool for fetching graphs by kind is properly registered.
        assert "graph_fetch_by_kind" in names
        # codegraph:test-desc test_tools.TestToolRegistration.test_all_tools_have_names::post_3
        # Verifies that 'graph_list_tags' is included in the set of registered tool
        # names, confirming the tool for retrieving graph tags is properly registered.
        assert "graph_list_tags" in names
        # codegraph:test-desc test_tools.TestToolRegistration.test_all_tools_have_names::post_4
        # Verifies that 'graph_format_export' is included in the set of registered tool
        # names, confirming the tool for exporting graph data is properly registered.
        assert "graph_format_export" in names
        # codegraph:test-desc test_tools.TestToolRegistration.test_all_tools_have_names::post_5
        # Verifies that 'graph_format_import' is included in the set of registered tool
        # names, confirming the tool for importing graph data is properly registered.
        assert "graph_format_import" in names
        # codegraph:test-desc test_tools.TestToolRegistration.test_all_tools_have_names::post_6
        # Verifies that 'graph_save' is included in the set of registered tool names,
        # confirming the tool for saving graph data is properly registered.
        assert "graph_save" in names

    # codegraph:test-desc test_tools.TestToolRegistration.test_all_schemas_valid
    # This test validates that every schema registered via create_dispatcher is
    # structurally sound and consistent, ensuring reliable tool execution and preventing
    # runtime errors in the dispatcher.
    def test_all_schemas_valid(self):
        d = create_dispatcher()
        for s in d.all_tool_schemas:
            # codegraph:test-desc test_tools.TestToolRegistration.test_all_schemas_valid::post_0
            # Verifies that every tool schema has a 'name' field, which uniquely
            # identifies the tool.
            assert "name" in s
            # codegraph:test-desc test_tools.TestToolRegistration.test_all_schemas_valid::post_1
            # Checks that each tool schema contains a 'description' field, which is
            # required for documentation and usability of the tool.
            assert "description" in s
            # codegraph:test-desc test_tools.TestToolRegistration.test_all_schemas_valid::post_2
            # Confirms that each tool schema includes an 'input_schema' field, which
            # defines the expected inputs for the tool.
            assert "input_schema" in s
            schema = s["input_schema"]
            # codegraph:test-desc test_tools.TestToolRegistration.test_all_schemas_valid::post_3
            # Verifies that the schema itself has a 'type' field, ensuring the schema
            # structure is properly defined.
            assert "type" in schema
            # codegraph:test-desc test_tools.TestToolRegistration.test_all_schemas_valid::post_4
            # Asserts that the schema type is 'object', as the top-level schema for tool
            # inputs should always be an object.
            assert schema["type"] == "object"
            if "properties" in schema:
                for prop_name, prop in schema["properties"].items():
                    # codegraph:test-desc test_tools.TestToolRegistration.test_all_schemas_valid::post_5
                    # Ensures that each property in the schema specifies its type either
                    # directly or via 'enum' or 'anyOf', which is necessary for input
                    # validation.
                    assert "type" in prop or "enum" in prop or "anyOf" in prop

    # codegraph:test-desc test_tools.TestToolRegistration.test_unknown_tool_returns_error
    # Verifies that dispatching an unknown tool name returns an error response, ensuring
    # the dispatcher correctly handles invalid inputs and prevents silent failures.
    def test_unknown_tool_returns_error(self):
        d = create_dispatcher()
        result = json.loads(d.dispatch("nonexistent", {}))
        # codegraph:test-desc test_tools.TestToolRegistration.test_unknown_tool_returns_error::post_0
        # Checks that the result dictionary includes an 'error' key, ensuring the
        # dispatcher signals failure with an error field when an unknown tool is used.
        assert "error" in result
        # codegraph:test-desc test_tools.TestToolRegistration.test_unknown_tool_returns_error::post_1
        # Verifies that the error message contains 'Unknown tool', confirming the
        # dispatcher correctly identifies and reports an unrecognized tool by name.
        assert "Unknown tool" in result["error"]

    # codegraph:test-desc test_tools.TestToolRegistration.test_duplicate_registration_raises
    # This test verifies that the ToolDispatcher's register method raises an appropriate
    # error when an attempt is made to register a tool with a name that has already been
    # registered, ensuring that the system prevents duplicate tool registrations and
    # maintains a unique mapping of tool names.
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
    # codegraph:test-desc test_tools.TestToolDispatch.test_custom_tool_dispatch
    # Verifies that the ToolDispatcher correctly registers and dispatches a custom tool,
    # ensuring the system can extend and invoke user-defined functionality as intended.
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
        # codegraph:test-desc test_tools.TestToolDispatch.test_custom_tool_dispatch::post_0
        # Verifies that the dispatched tool call returned the expected result 'hello',
        # confirming that the custom tool was correctly registered, dispatched, and
        # executed by the dispatcher.
        assert result["echo"] == "hello"

    # codegraph:test-desc test_tools.TestToolDispatch.test_all_tool_schemas_property
    # This test verifies that the `ToolDispatcher` class correctly exposes the JSON
    # schemas of all registered tools through its `all_tool_schemas` property, ensuring
    # that downstream consumers have complete and accurate metadata for tool invocation.
    def test_all_tool_schemas_property(self):
        d = ToolDispatcher()
        # codegraph:test-desc test_tools.TestToolDispatch.test_all_tool_schemas_property::post_0
        # Verifies that initially the all_tool_schemas property returns an empty list,
        # confirming no tools are registered.
        assert d.all_tool_schemas == []
        d.register("a", {
            "name": "a",
            "description": "A",
            "input_schema": {"type": "object", "properties": {}, "required": []},
        }, lambda inp: "ok")
        # codegraph:test-desc test_tools.TestToolDispatch.test_all_tool_schemas_property::post_1
        # Verifies that after registering one tool schema, the all_tool_schemas property
        # returns a list with exactly one schema, confirming proper registration.
        assert len(d.all_tool_schemas) == 1

# ── Neo4j-dependent integration tests ──────────────────────────────────────

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
class TestCodeGraphDispatcherIntegration:
    """Tests that require Neo4j with data loaded."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        """Load the fixture graph into Neo4j."""
        with open(Path(__file__).resolve().parent / "data" / "design_graph.json") as f:
            data = json.load(f)
        self.graph = LayerGraph.deserialize(data)
        self.graph.to_neo4j()
        self.dispatcher = CodeGraphDispatcher()

    # codegraph:test-desc test_tools.TestCodeGraphDispatcherIntegration.test_list_tags
    # This test verifies that the ToolDispatcher's dispatch method correctly lists tags,
    # ensuring the tagging functionality works as intended for proper code analysis and
    # navigation.
    def test_list_tags(self):
        result = json.loads(self.dispatcher.dispatch("graph_list_tags", {}))
        # codegraph:test-desc test_tools.TestCodeGraphDispatcherIntegration.test_list_tags::post_0
        # Verifies that the result contains an 'available_tags' key, confirming that the
        # dispatcher returns the expected structure with tag information.
        assert "available_tags" in result
        # codegraph:test-desc test_tools.TestCodeGraphDispatcherIntegration.test_list_tags::post_1
        # Verifies that the result contains a 'node_counts' key, confirming that the
        # dispatcher provides count data for nodes associated with each tag.
        assert "node_counts" in result
        # codegraph:test-desc test_tools.TestCodeGraphDispatcherIntegration.test_list_tags::post_2
        # Verifies that the 'design' tag is present in the 'available_tags' list,
        # ensuring that relevant tags are properly collected and returned by the
        # dispatcher.
        assert "design" in result["available_tags"]
        # codegraph:test-desc test_tools.TestCodeGraphDispatcherIntegration.test_list_tags::post_3
        # Verifies that the node count for the 'design' tag is greater than zero,
        # confirming that at least one design-related node exists in the code graph.
        assert result["node_counts"]["design"] > 0

    # codegraph:test-desc test_tools.TestCodeGraphDispatcherIntegration.test_fetch_by_tag_markdown
    # Verifies that the dispatcher correctly retrieves and returns tools matching a
    # specified tag in markdown format, ensuring reliable filtered access to tools.
    def test_fetch_by_tag_markdown(self):
        result = self.dispatcher.dispatch("graph_fetch", {
            "tag": "design",
            "format": "markdown",
        })
        # codegraph:test-desc test_tools.TestCodeGraphDispatcherIntegration.test_fetch_by_tag_markdown::post_0
        # Checks that the markdown contains the top-level heading '# codegraph: design',
        # confirming the dispatcher returns a well-structured overview for the requested
        # tag.
        assert "# codegraph: design" in result
        # codegraph:test-desc test_tools.TestCodeGraphDispatcherIntegration.test_fetch_by_tag_markdown::post_1
        # Ensures the markdown output includes a namespace header for 'calc', verifying
        # that the dispatcher properly organizes code under its namespace.
        assert "## Namespace: `calc`" in result
        # codegraph:test-desc test_tools.TestCodeGraphDispatcherIntegration.test_fetch_by_tag_markdown::post_2
        # Confirms that the 'Relationships' section is present in the markdown output,
        # validating that relationships among code elements are documented correctly.
        assert "## Relationships" in result

    # codegraph:test-desc test_tools.TestCodeGraphDispatcherIntegration.test_fetch_by_tag_json
    # This test verifies that the ToolDispatcher.dispatch method correctly fetches tools
    # by tag and returns them in JSON format, ensuring the integration between tool
    # selection and JSON serialization works as expected.
    def test_fetch_by_tag_json(self):
        result = self.dispatcher.dispatch("graph_fetch", {
            "tag": "design",
            "format": "json",
        })
        data = json.loads(result)
        # codegraph:test-desc test_tools.TestCodeGraphDispatcherIntegration.test_fetch_by_tag_json::post_0
        # Verifies that the result of the dispatch, stored in `data`, is a list,
        # ensuring the function returns a structured collection as expected.
        assert isinstance(data, list)
        # codegraph:test-desc test_tools.TestCodeGraphDispatcherIntegration.test_fetch_by_tag_json::post_1
        # Verifies that the list `data` contains at least one element, confirming that
        # the dispatch produced actual results and did not return empty.
        assert len(data) > 0

    # codegraph:test-desc test_tools.TestCodeGraphDispatcherIntegration.test_fetch_by_tag_plantuml
    # Verifies that the ToolDispatcher.dispatch method correctly fetches and returns
    # PlantUML diagrams by a specific tag, ensuring the dispatcher's tagging and
    # rendering integration works as expected for downstream tooling.
    def test_fetch_by_tag_plantuml(self):
        result = self.dispatcher.dispatch("graph_fetch", {
            "tag": "design",
            "format": "plantuml",
        })
        # codegraph:test-desc test_tools.TestCodeGraphDispatcherIntegration.test_fetch_by_tag_plantuml::post_0
        # Verifies that the dispatched result begins with the PlantUML diagram header
        # '@startuml', confirming the tool returns a valid PlantUML representation of
        # the queried code element.
        assert result.startswith("@startuml")

    # codegraph:test-desc test_tools.TestCodeGraphDispatcherIntegration.test_fetch_namespace
    # Verifies that the ToolDispatcher.dispatch method correctly resolves and returns
    # the namespace for a given tool, ensuring proper routing and execution of
    # dispatched operations.
    def test_fetch_namespace(self):
        result = self.dispatcher.dispatch("graph_fetch_namespace", {
            "qualified_name": "calc",
            "format": "markdown",
        })
        # codegraph:test-desc test_tools.TestCodeGraphDispatcherIntegration.test_fetch_namespace::post_0
        # Verifies that the dispatched output contains the expected namespace header '##
        # Namespace: `calc`', confirming that the dispatcher correctly retrieves and
        # formats the namespace information.
        assert "## Namespace: `calc`" in result

    # codegraph:test-desc test_tools.TestCodeGraphDispatcherIntegration.test_fetch_neighborhood
    # Verifies that the ToolDispatcher.dispatch method correctly handles a fetch
    # neighborhood request, ensuring robust integration of the dispatcher with
    # neighborhood data retrieval logic.
    def test_fetch_neighborhood(self):
        result = self.dispatcher.dispatch("graph_fetch_neighborhood", {
            "qualified_name": "calc::CalculatorEngine",
            "format": "markdown",
        })
        # codegraph:test-desc test_tools.TestCodeGraphDispatcherIntegration.test_fetch_neighborhood::post_0
        # Verifies that the result contains the header for the `CalculatorEngine` class,
        # confirming that the dispatcher correctly fetches and includes the neighborhood
        # information for the referenced code element.
        assert "### Class: `calc::CalculatorEngine`" in result

    # codegraph:test-desc test_tools.TestCodeGraphDispatcherIntegration.test_fetch_compound
    # Verifies that ToolDispatcher.dispatch correctly handles a compound fetch request,
    # ensuring the dispatcher returns the expected result when processing a combination
    # of multiple tools or data sources.
    def test_fetch_compound(self):
        result = self.dispatcher.dispatch("graph_fetch_compound", {
            "qualified_name": "calc::CalculatorEngine",
            "format": "markdown",
        })
        # codegraph:test-desc test_tools.TestCodeGraphDispatcherIntegration.test_fetch_compound::post_0
        # Verifies that the dispatched tool result contains the expected markdown
        # representation of the CalculatorEngine class, confirming that the dispatcher
        # correctly retrieves and formats class documentation.
        assert "### Class: `calc::CalculatorEngine`" in result

    # codegraph:test-desc test_tools.TestCodeGraphDispatcherIntegration.test_fetch_by_kind
    # Verifies that the ToolDispatcher.dispatch method correctly fetches code graph data
    # filtered by a specified kind, ensuring the dispatching functionality works as
    # expected for type-specific queries.
    def test_fetch_by_kind(self):
        result = self.dispatcher.dispatch("graph_fetch_by_kind", {
            "kind": "class",
            "tag": "design",
            "format": "markdown",
        })
        # codegraph:test-desc test_tools.TestCodeGraphDispatcherIntegration.test_fetch_by_kind::post_0
        # Verifies that the dispatcher's result contains 'CalculatorEngine', confirming
        # that the correct tool was found based on the requested kind.
        assert "CalculatorEngine" in result

    # codegraph:test-desc test_tools.TestCodeGraphDispatcherIntegration.test_fetch_by_source
    # This test verifies that the ToolDispatcher's dispatch method correctly fetches a
    # tool by its source identifier, ensuring the method can locate and return the
    # appropriate tool instance based on source metadata.
    def test_fetch_by_source(self):
        result = self.dispatcher.dispatch("graph_fetch_by_source", {
            "source": "calculator",
            "format": "json",
        })
        data = json.loads(result)
        # codegraph:test-desc test_tools.TestCodeGraphDispatcherIntegration.test_fetch_by_source::post_0
        # Verifies that the result from the dispatcher is a list, which is the expected
        # data type for fetched content and ensures the basic structure of the output is
        # correct.
        assert isinstance(data, list)
        # codegraph:test-desc test_tools.TestCodeGraphDispatcherIntegration.test_fetch_by_source::post_1
        # Checks that the list returned by the dispatcher is non-empty, confirming that
        # at least one piece of data was retrieved by source, which validates the
        # fundamental operation of the dispatch method.
        assert len(data) > 0

    # codegraph:test-desc test_tools.TestCodeGraphDispatcherIntegration.test_save_requires_fetch
    # Verifies that the ToolDispatcher requires a fetch operation before allowing a
    # save, ensuring data consistency and preventing stale or unauthorized writes.
    def test_save_requires_fetch(self):
        d = CodeGraphDispatcher()
        result = json.loads(d.dispatch("graph_save", {}))
        # codegraph:test-desc test_tools.TestCodeGraphDispatcherIntegration.test_save_requires_fetch::post_0
        # Verifies that the result contains an 'error' key, confirming that the
        # dispatcher correctly returns an error response rather than succeeding or
        # crashing when saving is attempted without a loaded graph.
        assert "error" in result
        # codegraph:test-desc test_tools.TestCodeGraphDispatcherIntegration.test_save_requires_fetch::post_1
        # Verifies that the error message explicitly states 'No graph loaded',
        # confirming the dispatcher provides a clear and specific error when save is
        # attempted before any graph is fetched.
        assert "No graph loaded" in result["error"]

    # codegraph:test-desc test_tools.TestCodeGraphDispatcherIntegration.test_format_export_requires_fetch
    # Verifies that the dispatch method of CodeGraphDispatcher enforces a fetch step
    # before format export, ensuring that exported data includes current context.
    def test_format_export_requires_fetch(self):
        d = CodeGraphDispatcher()  # fresh dispatcher, no fetch
        result = json.loads(d.dispatch("graph_format_export", {
            "format": "markdown",
        }))
        # codegraph:test-desc test_tools.TestCodeGraphDispatcherIntegration.test_format_export_requires_fetch::post_0
        # Confirms that the dispatch result includes an 'error' key, ensuring that the
        # dispatcher properly returns an error response when the required graph data is
        # missing.
        assert "error" in result
        # codegraph:test-desc test_tools.TestCodeGraphDispatcherIntegration.test_format_export_requires_fetch::post_1
        # Verifies that the error message explicitly states 'No graph loaded',
        # confirming that the system correctly identifies the root cause of the failure
        # and provides a clear explanation to the user.
        assert "No graph loaded" in result["error"]

    # codegraph:test-desc test_tools.TestCodeGraphDispatcherIntegration.test_format_export_after_fetch
    # This test verifies that after fetching data, the dispatcher correctly handles
    # format export operations, ensuring that output formatting works as expected for
    # downstream consumption.
    def test_format_export_after_fetch(self):
        self.dispatcher.dispatch("graph_fetch", {
            "tag": "design",
            "format": "markdown",
        })
        result = self.dispatcher.dispatch("graph_format_export", {
            "format": "plantuml",
        })
        # codegraph:test-desc test_tools.TestCodeGraphDispatcherIntegration.test_format_export_after_fetch::post_0
        # Verifies that the exported diagram output starts with the PlantUML `@startuml`
        # marker, ensuring the format is correct for PlantUML rendering.
        assert result.startswith("@startuml")

    # codegraph:test-desc test_tools.TestCodeGraphDispatcherIntegration.test_format_import_markdown
    # Verifies that the ToolDispatcher's dispatch method correctly formats import
    # markdown output, ensuring that imported modules are displayed in a readable and
    # consistent format, which is essential for users to understand code dependencies
    # and structure.
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
        # codegraph:test-desc test_tools.TestCodeGraphDispatcherIntegration.test_format_import_markdown::post_0
        # Verifies that the import operation was successfully executed
        # (result['imported'] is True), confirming that the code-under-test correctly
        # processed the import request.
        assert result["imported"] is True
        # codegraph:test-desc test_tools.TestCodeGraphDispatcherIntegration.test_format_import_markdown::post_1
        # Checks that at least one node was created by the import (result['node_count']
        # >= 1), ensuring that the import populated the graph structure as expected.
        assert result["node_count"] >= 1

    # codegraph:test-desc test_tools.TestCodeGraphDispatcherIntegration.test_import_caches_graph
    # This test verifies that a tool dispatcher can correctly import a module based on
    # its graph representation, ensuring that the dispatching logic accurately
    # translates cached graph data into executable code.
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
        # codegraph:test-desc test_tools.TestCodeGraphDispatcherIntegration.test_import_caches_graph::post_0
        # Verifies that the data returned by the dispatch method is a list, confirming
        # the output structure matches the expected format.
        assert isinstance(data, list)
        # codegraph:test-desc test_tools.TestCodeGraphDispatcherIntegration.test_import_caches_graph::post_1
        # Checks that the list returned by the dispatch method is non-empty, ensuring
        # that the import/caching process actually produced at least one result.
        assert len(data) > 0

    def test_save_after_fetch(self):
        """Fetch a graph then save it back."""
        self.dispatcher.dispatch("graph_fetch", {
            "tag": "design",
            "format": "json",
        })
        result = json.loads(self.dispatcher.dispatch("graph_save", {}))
        # codegraph:test-desc test_tools.TestCodeGraphDispatcherIntegration.test_save_after_fetch::post_0
        # Asserts that the save operation on the fetched graph completed successfully,
        # confirming that the dispatch function can persist graph data without errors.
        assert result["saved"] is True
        # codegraph:test-desc test_tools.TestCodeGraphDispatcherIntegration.test_save_after_fetch::post_1
        # Verifies that the graph fetched contains at least one node, confirming that
        # the fetch operation successfully retrieved graph data and the save operation
        # preserved it.
        assert result["node_count"] > 0