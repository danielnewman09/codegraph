"""Test description field on CodebaseEdge."""
import pytest
from codegraph.edges import CodebaseEdge


def test_codebase_edge_has_description_field():
    edge = CodebaseEdge(
        subject_qualified_name="calc::Calculator",
        predicate="aggregates",
        object_qualified_name="calc::Matrix",
        description="Holds the internal matrix for operations",
    )
    assert edge.description == "Holds the internal matrix for operations"


def test_codebase_edge_description_defaults_to_empty():
    edge = CodebaseEdge(
        subject_qualified_name="calc::Calculator",
        predicate="aggregates",
        object_qualified_name="calc::Matrix",
    )
    assert edge.description == ""
