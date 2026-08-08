"""Unit tests for the codegraph constants vocabulary.

Phase 0 codegen blockers: ``has_parameter`` predicate vocabulary and
canonical language normalization (Doxygen writes ``"C++"``, the Python
parser writes ``"Python"``; ``FileNode.language`` promises lowercase).
"""

import pytest

from codegraph.constants import (
    DEFAULT_PREDICATES,
    PREDICATE_TO_REL_TYPE,
    PREDICATES,
    normalize_language,
)


class TestHasParameterPredicate:
    """HAS_PARAMETER must be part of the predicate vocabulary.

    doxygen-index emits ``HAS_PARAMETER`` edges (member → parameter);
    the context builder for codegen depends on this being discoverable
    via the vocabulary, not hard-coded per consumer.
    """

    def test_predicate_to_rel_type_contains_has_parameter(self):
        assert PREDICATE_TO_REL_TYPE["has_parameter"] == "HAS_PARAMETER"

    def test_predicates_list_contains_has_parameter(self):
        assert "has_parameter" in PREDICATES

    def test_default_predicates_documents_has_parameter(self):
        descriptions = dict(DEFAULT_PREDICATES)
        assert "has_parameter" in descriptions
        assert "parameter" in descriptions["has_parameter"].lower()

    def test_vocabulary_consistency(self):
        # Every predicate maps to a UPPER_SNAKE_CASE rel type and vice versa.
        assert PREDICATES == list(PREDICATE_TO_REL_TYPE.keys())
        for predicate, rel_type in PREDICATE_TO_REL_TYPE.items():
            assert rel_type == rel_type.upper()
            assert " " not in rel_type


class TestNormalizeLanguage:
    """Producer spellings → canonical lowercase language keys."""

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            # Doxygen C++ spelling
            ("C++", "cpp"),
            ("c++", "cpp"),
            # Already canonical
            ("cpp", "cpp"),
            ("python", "python"),
            # Python AST parser spelling
            ("Python", "python"),
            ("PYTHON", "python"),
            # Other aliases
            ("py", "python"),
            ("JavaScript", "javascript"),
            ("ts", "typescript"),
            ("Rust", "rust"),
        ],
    )
    def test_known_aliases(self, raw, expected):
        assert normalize_language(raw) == expected

    def test_empty_string(self):
        assert normalize_language("") == ""
        assert normalize_language(None) == ""

    def test_unknown_passthrough_lowercased(self):
        assert normalize_language("Fortran") == "fortran"
        assert normalize_language(" Go ") == "go"

    def test_whitespace_insensitive(self):
        assert normalize_language("  C++  ") == "cpp"
