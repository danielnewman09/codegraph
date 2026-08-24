"""Compound context builder tests.

Pins: class/struct sections grouped by visibility, nested compounds
rendered inline, enums with values, concepts with initializer,
INHERITS_FROM bases + REALIZES interfaces (flat-format references),
and string-derived D8 flags.
"""

from __future__ import annotations

from codegraph.codegen.context import BuildState, compound
from codegraph.identity import IdentityScope, resolve_identity_for
from codegraph.models.compound import ClassNode, ConceptNode, EnumNode, InterfaceNode
from codegraph.models.member import AttributeNode, EnumValueNode, MethodNode


_SCOPE = IdentityScope.repository("codegraph-suite", "codegraph")


def _class_key(qn, *, kind="class"):
    return resolve_identity_for(
        ClassNode(name=qn.rsplit("::", 1)[-1], qualified_name=qn, kind=kind),
        _SCOPE,
    ).key()


def _interface_key(qn):
    return resolve_identity_for(
        InterfaceNode(name=qn.rsplit("::", 1)[-1], qualified_name=qn), _SCOPE
    ).key()


def _enum_key(qn):
    return resolve_identity_for(
        EnumNode(name=qn.rsplit("::", 1)[-1], qualified_name=qn), _SCOPE
    ).key()


def _attribute_key(qn):
    return resolve_identity_for(
        AttributeNode(name=qn.rsplit("::", 1)[-1], qualified_name=qn), _SCOPE
    ).key()


def _method_key(qn, argsstring=""):
    return resolve_identity_for(
        MethodNode(name=qn.rsplit("::", 1)[-1], qualified_name=qn,
                   argsstring=argsstring),
        _SCOPE,
    ).key()


def _concept_key(qn):
    return resolve_identity_for(
        ConceptNode(name=qn.rsplit("::", 1)[-1], qualified_name=qn), _SCOPE
    ).key()


def _enum_value_key(qn):
    return resolve_identity_for(
        EnumValueNode(name=qn.rsplit("::", 1)[-1], qualified_name=qn), _SCOPE
    ).key()


def _class(name="MigrationManager", qn="cpp_sqlite::MigrationManager", **overrides):
    data = {
        "type": "ClassNode",
        "name": name,
        "qualified_name": qn,
        "kind": "class",
        "source": "test",
        "tags": ["design"],
        "visibility": "",
        "canonical_key": _class_key(qn, kind=overrides.get("kind", "class")),
    }
    data.update(overrides)
    return data


class TestClassLike:
    def test_source_template_declarations_preserve_constraints(self, make_state, find_entry):
        graph, state = make_state([_class(
            name="RepeatedFieldTransferObject",
            qn="cpp_sqlite::RepeatedFieldTransferObject",
            kind="struct",
            template_declarations=["ValidTransferObject T"],
        )])
        ctx = compound.build_context(find_entry(graph, type_name="ClassNode"), state)
        assert ctx["template_params"] == [{"declaration": "ValidTransferObject T"}]

    def test_sections_grouped_by_visibility(self, make_state, find_entry):
        graph, state = make_state([_class(composes=[
            {
                "type": "AttributeNode",
                "canonical_key": _attribute_key("cpp_sqlite::MigrationManager::db_"),
                "name": "db_",
                "qualified_name": "cpp_sqlite::MigrationManager::db_",
                "kind": "attribute",
                "type_signature": "Database&",
                "visibility": "private",
                "source": "test",
            },
            {
                "type": "MethodNode",
                "canonical_key": _method_key("cpp_sqlite::MigrationManager::apply"),
                "name": "apply",
                "qualified_name": "cpp_sqlite::MigrationManager::apply",
                "kind": "method",
                "type_signature": "MigrationResult apply()",
                "visibility": "public",
                "source": "test",
            },
        ])])
        ctx = compound.build_context(find_entry(graph, type_name="ClassNode"), state)
        assert ctx["type"] == "ClassNode"
        assert ctx["kind"] == "class"
        assert ctx["name"] == "MigrationManager"
        assert ctx["qualified_name"] == "cpp_sqlite::MigrationManager"
        # first-seen access order: private attrs first, then public
        assert [(s["access"], [m["name"] for m in s["members"]]) for s in ctx["sections"]] == [
            ("private", ["db_"]),
            ("public", ["apply"]),
        ]
        assert ctx["visibility"] == "public"  # '' → public

    def test_mixed_members_follow_source_order_not_type_bucket_order(
        self, make_state, find_entry
    ):
        """Source spans must keep methods ahead of later attributes.

        ``CompositeEntry.children`` is grouped by node type, so a backend
        returning attributes first must not force the generated class into a
        private-then-public layout when the source declares the method first.
        """
        graph, state = make_state([_class(composes=[
            {
                "type": "AttributeNode",
                "canonical_key": _attribute_key("cpp_sqlite::Thing::state_"),
                "name": "state_",
                "qualified_name": "cpp_sqlite::Thing::state_",
                "kind": "attribute",
                "visibility": "private",
                "start_line": 20,
                "source": "test",
            },
            {
                "type": "MethodNode",
                "canonical_key": _method_key("cpp_sqlite::Thing::render"),
                "name": "render",
                "qualified_name": "cpp_sqlite::Thing::render",
                "kind": "method",
                "type_signature": "void render()",
                "visibility": "public",
                "start_line": 10,
                "source": "test",
            },
        ])])

        ctx = compound.build_context(
            find_entry(graph, type_name="ClassNode"), state
        )
        assert [
            (section["access"], [member["name"] for member in section["members"]])
            for section in ctx["sections"]
        ] == [("public", ["render"]), ("private", ["state_"])]

    def test_empty_visibility_is_public(self, make_state, find_entry):
        graph, state = make_state([_class(composes=[
            {
                "type": "AttributeNode",
                "canonical_key": _attribute_key("cpp_sqlite::MigrationManager::x"),
                "name": "x",
                "qualified_name": "cpp_sqlite::MigrationManager::x",
                "kind": "attribute",
                "type_signature": "int",
                "source": "test",
            },
        ])])
        ctx = compound.build_context(find_entry(graph, type_name="ClassNode"), state)
        assert len(ctx["sections"]) == 1
        assert ctx["sections"][0]["access"] == "public"
        assert [m["name"] for m in ctx["sections"][0]["members"]] == ["x"]

    def test_nested_compound_renders_inline(self, make_state, find_entry):
        graph, state = make_state([_class(composes=[
            {
                "type": "ClassNode",
                "canonical_key": _class_key("cpp_sqlite::MigrationManager::MigrationResult", kind="struct"),
                "name": "MigrationResult",
                "qualified_name": "cpp_sqlite::MigrationManager::MigrationResult",
                "kind": "struct",
                "source": "test",
                "composes": [
                    {
                        "type": "AttributeNode",
                        "canonical_key": _attribute_key("cpp_sqlite::MigrationManager::MigrationResult::is_consistent"),
                        "name": "is_consistent",
                        "qualified_name": "cpp_sqlite::MigrationManager::MigrationResult::is_consistent",
                        "kind": "attribute",
                        "type_signature": "bool",
                        "source": "test",
                    },
                ],
            },
        ])])
        ctx = compound.build_context(find_entry(graph, type_name="ClassNode"), state)
        member_ctxs = [m for s in ctx["sections"] for m in s["members"]]
        nested = member_ctxs[0]
        assert nested["type"] == "ClassNode"
        assert nested["kind"] == "struct"
        assert nested["name"] == "MigrationResult"
        assert nested["sections"][0]["members"][0]["name"] == "is_consistent"

    def test_interface_defaults(self, make_state, find_entry):
        graph, state = make_state([{
            "type": "InterfaceNode",
            "name": "ITransferObject",
            "qualified_name": "cpp_sqlite::ITransferObject",
            "kind": "interface",
            "source": "test",
            "tags": ["design"],
            "canonical_key": _interface_key("cpp_sqlite::ITransferObject"),
        }])
        ctx = compound.build_context(find_entry(graph, type_name="InterfaceNode"), state)
        assert ctx["kind"] == "interface"
        assert ctx["type"] == "InterfaceNode"

    def test_struct_kind_preserved(self, make_state, find_entry):
        graph, state = make_state([_class(name="MigrationResult", qn="cpp_sqlite::MigrationResult", kind="struct")])
        ctx = compound.build_context(find_entry(graph, type_name="ClassNode"), state)
        assert ctx["kind"] == "struct"

    def test_bases_from_inherits_from_reference(self, make_state, find_entry):
        # Flat format: edges resolve via identity fields (qualified_name).
        graph, state = make_state([
            _class(name="Derived", qn="cpp_sqlite::Derived", edges=[
                {"relation_type": "INHERITS_FROM", "target_key": _class_key("cpp_sqlite::Base"),
                 "target_type": "ClassNode"},
            ]),
            _class(name="Base", qn="cpp_sqlite::Base"),
        ])
        ctx = compound.build_context(find_entry(graph, type_name="ClassNode", name="Derived"), state)
        assert ctx["bases"] == [{"name": "cpp_sqlite::Base", "access": "public", "virtual": False}]
        assert ctx["interfaces"] == []

    def test_interfaces_from_realizes_reference(self, make_state, find_entry):
        graph, state = make_state([
            _class(name="Printer", qn="cpp_sqlite::Printer", edges=[
                {"relation_type": "REALIZES", "target_key": _interface_key("cpp_sqlite::IPrintable"),
                 "target_type": "InterfaceNode"},
            ]),
            {
                "type": "InterfaceNode",
                "name": "IPrintable",
                "qualified_name": "cpp_sqlite::IPrintable",
                "kind": "interface",
                "source": "test",
                "tags": ["design"],
                "canonical_key": _interface_key("cpp_sqlite::IPrintable"),
            },
        ])
        ctx = compound.build_context(find_entry(graph, type_name="ClassNode", name="Printer"), state)
        assert ctx["interfaces"] == [{"name": "cpp_sqlite::IPrintable"}]

    def test_template_params_from_reference(self, make_state, find_entry):
        # Flat format: type_parameter slot + TEMPLATE_PARAM edge.
        graph, state = make_state([
            _class(name="DataAccessObject", qn="cpp_sqlite::DataAccessObject", edges=[
                {"relation_type": "TEMPLATE_PARAM", "target_key": _class_key("T", kind="type_parameter"),
                 "target_type": "ClassNode"},
            ]),
            {
                "type": "ClassNode",
                "name": "T",
                "qualified_name": "T",
                "kind": "type_parameter",
                "source": "test",
                "tags": ["design"],
                "canonical_key": _class_key("T", kind="type_parameter"),
            },
        ])
        ctx = compound.build_context(find_entry(graph, type_name="ClassNode", name="DataAccessObject"), state)
        assert ctx["template_params"] == [{
            "name": "T", "kind": "type_parameter", "default": "", "concept": "",
        }]


class TestSpecializations:
    """Phase 2: template-specialization compounds render as valid partial
    specializations — template params derived from the qname args (the
    graph carries no TEMPLATE_PARAM edges), scope-qualified member
    definitions stripped.
    """

    def test_spec_info_derives_base_args_and_params(self, make_state, find_entry):
        graph, state = make_state([_class(
            name="IsForeignKeyT< ForeignKey< T > >",
            qn="cpp_sqlite::IsForeignKeyT< ForeignKey< T > >",
            kind="struct",
        )])
        entry = find_entry(graph, type_name="ClassNode")
        info = compound._spec_info(entry)
        assert info == {
            "base": "IsForeignKeyT",
            "args": "<ForeignKey<T>>",
            "params": [{"kind": "typename", "name": "T", "default": "", "concept": ""}],
        }

    def test_spec_context_shape(self, make_state, find_entry):
        graph, state = make_state([_class(
            name="IsVector< std::vector< T, Allocator > >",
            qn="cpp_sqlite::IsVector< std::vector< T, Allocator > >",
            kind="struct",
        )])
        ctx = compound.build_context(
            find_entry(graph, type_name="ClassNode"), state
        )
        assert ctx["name"] == "IsVector"
        assert ctx["template_args"] == "<std::vector<T, Allocator>>"
        assert [p["name"] for p in ctx["template_params"]] == ["T", "Allocator"]

    def test_plain_class_has_no_spec_keys(self, make_state, find_entry):
        graph, state = make_state([_class()])
        ctx = compound.build_context(
            find_entry(graph, type_name="ClassNode"), state
        )
        assert ctx["name"] == "MigrationManager"
        assert ctx["template_args"] == ""
        assert ctx["template_params"] == []


class TestForwardDecls:
    def test_depends_on_class_targets_forward_declared(self, make_state, find_entry):
        graph, state = make_state([
            _class(name="MigrationManager", qn="cpp_sqlite::MigrationManager", edges=[
                {"relation_type": "DEPENDS_ON", "target_key": _class_key("cpp_sqlite::Migration"),
                 "target_type": "ClassNode"},
                {"relation_type": "DEPENDS_ON", "target_key": _class_key("cpp_sqlite::Database"),
                 "target_type": "ClassNode"},
            ]),
            _class(name="Migration", qn="cpp_sqlite::Migration"),
            _class(name="Database", qn="cpp_sqlite::Database"),
        ])
        ctx = compound.build_context(find_entry(graph, type_name="ClassNode", name="MigrationManager"), state)
        assert ctx["forward_decls"] == [
            {"name": "Database", "kind": "class"},
            {"name": "Migration", "kind": "class"},
        ]

    def test_struct_keyword_and_cross_namespace_qualified(self, make_state, find_entry):
        graph, state = make_state([
            _class(name="MigrationManager", qn="cpp_sqlite::MigrationManager", edges=[
                {"relation_type": "DEPENDS_ON", "target_key": _class_key("cpp_sqlite::MigrationResult", kind="struct"),
                 "target_type": "ClassNode"},
                {"relation_type": "DEPENDS_ON", "target_key": _class_key("util::Registry"),
                 "target_type": "ClassNode"},
            ]),
            {
                "type": "ClassNode", "name": "MigrationResult",
                "qualified_name": "cpp_sqlite::MigrationResult", "kind": "struct",
                "source": "test", "tags": ["design"],
                "canonical_key": _class_key("cpp_sqlite::MigrationResult", kind="struct"),
            },
            {
                "type": "ClassNode", "name": "Registry",
                "qualified_name": "util::Registry", "kind": "class",
                "source": "test", "tags": ["design"],
                "canonical_key": _class_key("util::Registry"),
            },
        ])
        ctx = compound.build_context(find_entry(graph, type_name="ClassNode", name="MigrationManager"), state)
        # same-namespace struct unqualified; cross-namespace keeps its qname
        assert ctx["forward_decls"] == [
            {"name": "MigrationResult", "kind": "struct"},
            {"name": "util::Registry", "kind": "class"},
        ]

    def test_excludes_std_enum_self_and_composed_children(self, make_state, find_entry):
        graph, state = make_state([
            _class(name="MigrationManager", qn="cpp_sqlite::MigrationManager", composes=[
                {
                    "type": "ClassNode", "name": "MigrationResult",
                    "canonical_key": _class_key("cpp_sqlite::MigrationResult", kind="struct"),
                    "qualified_name": "cpp_sqlite::MigrationResult", "kind": "struct",
                    "source": "test", "tags": ["design"],
                },
            ], edges=[
                {"relation_type": "DEPENDS_ON", "target_key": _class_key("std::vector"),
                 "target_type": "ClassNode"},
                {"relation_type": "DEPENDS_ON", "target_key": _enum_key("cpp_sqlite::MigrationErrorCode"),
                 "target_type": "EnumNode"},
                {"relation_type": "DEPENDS_ON", "target_key": _class_key("cpp_sqlite::MigrationManager"),
                 "target_type": "ClassNode"},
                {"relation_type": "DEPENDS_ON", "target_key": _class_key("cpp_sqlite::MigrationResult", kind="struct"),
                 "target_type": "ClassNode"},
            ]),
            {
                "type": "ClassNode", "name": "vector",
                "qualified_name": "std::vector", "kind": "class",
                "source": "test", "tags": ["design"],
                "canonical_key": _class_key("std::vector"),
            },
            {
                "type": "EnumNode", "name": "MigrationErrorCode",
                "qualified_name": "cpp_sqlite::MigrationErrorCode", "kind": "enum",
                "source": "test", "tags": ["design"],
                "canonical_key": _enum_key("cpp_sqlite::MigrationErrorCode"),
            },
        ])
        ctx = compound.build_context(find_entry(graph, type_name="ClassNode", name="MigrationManager"), state)
        # std::, enum, self, and the composed child are all excluded
        assert ctx["forward_decls"] == []

    def test_no_depends_on_edges(self, make_state, find_entry):
        graph, state = make_state([_class()])
        ctx = compound.build_context(find_entry(graph, type_name="ClassNode"), state)
        assert ctx["forward_decls"] == []


class TestEnums:
    def test_enum_with_values(self, make_state, find_entry):
        graph, state = make_state([{
            "type": "EnumNode",
            "name": "MigrationErrorCode",
            "qualified_name": "cpp_sqlite::MigrationErrorCode",
            "kind": "enum",
            "source": "test",
            "tags": ["design"],
            "canonical_key": _enum_key("cpp_sqlite::MigrationErrorCode"),
            "composes": [
                {
                    "type": "EnumValueNode",
                    "name": "Success",
                    "qualified_name": "cpp_sqlite::MigrationErrorCode::Success",
                    "kind": "enumvalue",
                    "source": "test",
                    "canonical_key": _enum_value_key("cpp_sqlite::MigrationErrorCode::Success"),
                },
                {
                    "type": "EnumValueNode",
                    "name": "DuplicateVersion",
                    "qualified_name": "cpp_sqlite::MigrationErrorCode::DuplicateVersion",
                    "kind": "enumvalue",
                    "initializer": "1",
                    "source": "test",
                    "canonical_key": _enum_value_key("cpp_sqlite::MigrationErrorCode::DuplicateVersion"),
                },
            ],
        }])
        ctx = compound.build_context(find_entry(graph, type_name="EnumNode"), state)
        assert ctx["kind"] == "enum"
        assert [v["name"] for v in ctx["enumerators"]] == ["Success", "DuplicateVersion"]
        assert ctx["enumerators"][1]["initializer"] == "1"

        roundtripped = make_state(graph.serialize(fields="all"))[0]
        roundtrip_ctx = compound.build_context(
            find_entry(roundtripped, type_name="EnumNode"),
            BuildState(graph=roundtripped, flat=roundtripped._flat_index()),
        )
        assert [v["name"] for v in roundtrip_ctx["enumerators"]] == [
            "Success", "DuplicateVersion"
        ]


class TestConcepts:
    def test_concept_initializer(self, make_state, find_entry):
        graph, state = make_state([{
            "type": "ConceptNode",
            "name": "ValidTransferObject",
            "qualified_name": "cpp_sqlite::ValidTransferObject",
            "kind": "concept",
            "initializer": "template<typename T> concept cpp_sqlite::ValidTransferObject = TransferObject<T> && DefaultConstruct",
            "source": "test",
            "tags": ["design"],
            "canonical_key": _concept_key("cpp_sqlite::ValidTransferObject"),
        }])
        ctx = compound.build_context(find_entry(graph, type_name="ConceptNode"), state)
        assert ctx["initializer"].startswith("template<typename T> concept")
