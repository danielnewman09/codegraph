import pytest
from pydantic import ValidationError

from codegraph.edges import CodebaseEdge, PREDICATES


class TestCodebaseEdge:
    def test_minimal_creation(self):
        e = CodebaseEdge(
            subject_qualified_name="calc::Calculator",
            predicate="composes",
            object_qualified_name="calc::Calculator::add",
        )
        assert e.subject_qualified_name == "calc::Calculator"
        assert e.predicate == "composes"
        assert e.object_qualified_name == "calc::Calculator::add"
        assert e.mechanism == ""
        assert e.position is None
        assert e.name == ""
        assert e.display_name == ""

    def test_full_creation(self):
        e = CodebaseEdge(
            subject_qualified_name="calc::Calculator",
            predicate="aggregates",
            object_qualified_name="calc::Logger",
            mechanism="std::shared_ptr",
            position=None,
            name="",
            display_name="",
        )
        assert e.mechanism == "std::shared_ptr"

    def test_with_template_param_fields(self):
        e = CodebaseEdge(
            subject_qualified_name="calc::Container",
            predicate="template_param",
            object_qualified_name="T",
            position=0,
            name="T",
            display_name="typename T",
        )
        assert e.position == 0
        assert e.name == "T"
        assert e.display_name == "typename T"

    def test_subject_required(self):
        with pytest.raises(ValidationError):
            CodebaseEdge(predicate="composes", object_qualified_name="calc::foo")

    def test_predicate_required(self):
        with pytest.raises(ValidationError):
            CodebaseEdge(
                subject_qualified_name="calc::Calculator",
                object_qualified_name="calc::foo",
            )

    def test_object_required(self):
        with pytest.raises(ValidationError):
            CodebaseEdge(
                subject_qualified_name="calc::Calculator",
                predicate="composes",
            )

    def test_any_predicate_in_list_is_accepted(self):
        for predicate in PREDICATES:
            e = CodebaseEdge(
                subject_qualified_name="a",
                predicate=predicate,
                object_qualified_name="b",
            )
            assert e.predicate == predicate

    def test_model_dump_roundtrip(self):
        e = CodebaseEdge(
            subject_qualified_name="calc::Calculator",
            predicate="composes",
            object_qualified_name="calc::Calculator::add",
            mechanism="",
            position=None,
            name="",
            display_name="",
        )
        data = e.model_dump()
        e2 = CodebaseEdge.model_validate(data)
        assert e == e2

    def test_position_stays_none_when_not_set(self):
        e = CodebaseEdge(
            subject_qualified_name="a",
            predicate="composes",
            object_qualified_name="b",
        )
        data = e.model_dump()
        assert data["position"] is None


class TestPredicatesImport:
    def test_predicates_is_list_of_strings(self):
        assert isinstance(PREDICATES, list)
        assert all(isinstance(p, str) for p in PREDICATES)
        assert len(PREDICATES) > 0

    def test_predicates_contain_core_edges(self):
        for pred in ["composes", "depends_on", "generalizes", "references", "invokes", "returns"]:
            assert pred in PREDICATES
