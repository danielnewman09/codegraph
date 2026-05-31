"""Test FieldTags annotation and field filtering."""
import pytest
from typing import Annotated, get_type_hints
from pydantic import BaseModel
from codegraph.designs.tags import FieldTags, get_fields_by_tags


class SampleModel(BaseModel):
    name: Annotated[str, FieldTags("llm", "neo4j")]
    file_path: Annotated[str, FieldTags("neo4j")]
    internal: str = ""  # no tags


def test_field_tags_are_inspectable():
    hints = get_type_hints(SampleModel, include_extras=True)
    assert hints["name"].__metadata__[0].tags == frozenset({"llm", "neo4j"})
    assert hints["file_path"].__metadata__[0].tags == frozenset({"neo4j"})


def test_get_fields_by_tags_llm():
    fields = get_fields_by_tags(SampleModel, {"llm"})
    assert "name" in fields
    assert "file_path" not in fields
    assert "internal" not in fields


def test_get_fields_by_tags_neo4j():
    fields = get_fields_by_tags(SampleModel, {"neo4j"})
    assert "name" in fields
    assert "file_path" in fields
    assert "internal" not in fields


def test_untagged_fields_excluded():
    fields = get_fields_by_tags(SampleModel, {"llm", "neo4j"})
    assert "internal" not in fields
