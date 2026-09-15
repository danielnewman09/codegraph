"""Characterization checks for the direct DDP → Codegraph migration."""

from __future__ import annotations

from pathlib import Path


FIXTURE = Path(__file__).parent / "fixtures" / "python"


def test_old_and_new_parser_entry_points_have_equal_inventories():
    from codegraph_index.parser import parse_python_dir as new_parse
    from doxygen_index.parser import parse_python_dir as old_parse

    old_result = old_parse(FIXTURE, source="parity", progress_interval=0)
    new_result = new_parse(FIXTURE, source="parity", progress_interval=0)

    for field in (
        "files", "namespaces", "classes", "enums", "unions", "interfaces",
        "methods", "attributes", "functions", "parameters", "tests",
        "assertions", "test_steps", "test_fixtures", "includes", "invokes",
        "verifies", "callees",
    ):
        assert len(getattr(old_result, field)) == len(getattr(new_result, field)), field

    old_qnames = {
        getattr(node, "qualified_name", "")
        for node in old_result.classes + old_result.methods + old_result.functions
    }
    new_qnames = {
        getattr(node, "qualified_name", "")
        for node in new_result.classes + new_result.methods + new_result.functions
    }
    assert old_qnames == new_qnames
