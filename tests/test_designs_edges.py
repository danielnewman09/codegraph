import pytest
from codegraph.designs.edges import Association


def test_association_llm_aliases():
    assoc = Association(
        subject="calc::Calculator",
        predicate="aggregates",
        object="calc::Matrix",
        mechanism="std::vector",
        description="Internal matrix storage",
    )
    dumped = assoc.model_dump(tags={"llm"})
    assert dumped["from_class"] == "calc::Calculator"
    assert dumped["to_class"] == "calc::Matrix"
    assert dumped["kind"] == "aggregates"
    assert "subject" not in dumped
    assert "predicate" not in dumped
    assert "object" not in dumped
    assert dumped["mechanism"] == "std::vector"
    assert dumped["description"] == "Internal matrix storage"
