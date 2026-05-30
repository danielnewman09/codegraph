from codegraph.constants import (
    COMPOUND_KINDS,
    MEMBER_KINDS,
    NAMESPACE_KINDS,
    NODE_KINDS,
    LAYERS,
    VISIBILITY_CHOICES,
    PREDICATES,
    PREDICATE_TO_REL_TYPE,
    CONSTRAINTS_AND_INDEXES,
)


class TestKinds:
    def test_compound_kinds_contains_expected(self):
        assert "class" in COMPOUND_KINDS
        assert "struct" in COMPOUND_KINDS
        assert "template_class" in COMPOUND_KINDS
        assert "interface" in COMPOUND_KINDS
        assert "abstract_class" in COMPOUND_KINDS
        assert "enum" in COMPOUND_KINDS
        assert "enum_class" in COMPOUND_KINDS
        assert "union" in COMPOUND_KINDS
        assert len(COMPOUND_KINDS) == 8

    def test_member_kinds_contains_expected(self):
        assert "method" in MEMBER_KINDS
        assert "variable" in MEMBER_KINDS
        assert "define" in MEMBER_KINDS
        assert "enumvalue" in MEMBER_KINDS
        assert "function" in MEMBER_KINDS
        assert len(MEMBER_KINDS) == 5

    def test_namespace_kinds_contains_expected(self):
        assert "namespace" in NAMESPACE_KINDS
        assert "package" in NAMESPACE_KINDS
        assert "module" in NAMESPACE_KINDS
        assert len(NAMESPACE_KINDS) == 3

    def test_node_kinds_is_union_of_all(self):
        all_kinds = set(COMPOUND_KINDS + MEMBER_KINDS + NAMESPACE_KINDS)
        assert set(NODE_KINDS) == all_kinds

    def test_kinds_are_disjoint(self):
        c = set(COMPOUND_KINDS)
        m = set(MEMBER_KINDS)
        n = set(NAMESPACE_KINDS)
        assert c.isdisjoint(m)
        assert c.isdisjoint(n)
        assert m.isdisjoint(n)


class TestLayers:
    def test_layers_contain_expected(self):
        assert LAYERS == ["design", "as-built", "dependency"]


class TestVisibility:
    def test_visibility_choices(self):
        assert VISIBILITY_CHOICES == ["public", "private", "protected"]


class TestPredicateMapping:
    def test_all_predicates_have_rel_type(self):
        for predicate in PREDICATES:
            assert predicate in PREDICATE_TO_REL_TYPE, f"Missing rel type for {predicate}"
            rel_type = PREDICATE_TO_REL_TYPE[predicate]
            assert rel_type == rel_type.upper(), f"{rel_type} must be UPPER_SNAKE_CASE"
            assert " " not in rel_type, f"{rel_type} must not contain spaces"

    def test_rel_types_map_back_to_predicates(self):
        seen = set()
        for predicate, rel_type in PREDICATE_TO_REL_TYPE.items():
            assert rel_type not in seen, f"Duplicate rel type {rel_type}"
            seen.add(rel_type)

    def test_no_duplicate_predicates(self):
        assert len(PREDICATES) == len(set(PREDICATES))


class TestConstraintsAndIndexes:
    def test_is_list_of_strings(self):
        assert isinstance(CONSTRAINTS_AND_INDEXES, list)
        assert all(isinstance(s, str) for s in CONSTRAINTS_AND_INDEXES)
        assert len(CONSTRAINTS_AND_INDEXES) > 0

    def test_contains_file_constraint(self):
        assert any("CREATE CONSTRAINT file_refid" in s for s in CONSTRAINTS_AND_INDEXES)

    def test_contains_compound_indexes(self):
        statements = "\n".join(CONSTRAINTS_AND_INDEXES)
        assert "compound_refid" in statements
        assert "compound_name" in statements
        assert "compound_qualified" in statements
        assert "compound_kind" in statements
        assert "compound_layer" in statements
        assert "compound_source" in statements

    def test_contains_fulltext_search(self):
        statements = "\n".join(CONSTRAINTS_AND_INDEXES)
        assert "FULLTEXT INDEX doc_search" in statements
