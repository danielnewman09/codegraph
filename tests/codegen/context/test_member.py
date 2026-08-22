"""Member context builder tests (R3 signature reconciliation applied).

Pins: full-declaration verbatim emission (both design encodings),
return-type-only reconstruction (as-built), role naming (ctor/dtor/
operator), string-derived flags (D8), attributes (plain + typedef),
enum values, and defines.
"""

from __future__ import annotations

from codegraph.codegen.context import member

from codegraph.graph import LayerGraph


def _deser(data):
    return LayerGraph.deserialize(data)



def _method(**overrides):
    data = {
        "type": "MethodNode",
        "canonical_key": 'cg:v1:repository:codegraph-suite%2Fcodegraph:method:qualified_name=cpp_sqlite%3A%3AMigrationManager%3A%3Aapply:canonical_signature=lang%3Acpp%7C%28%29',
        "name": "apply",
        "qualified_name": "cpp_sqlite::MigrationManager::apply",
        "kind": "method",
        "type_signature": "MigrationResult apply()",
        "argsstring": "()",
        "source": "test",
        "tags": ["design"],
        "visibility": "public",
    }
    data.update(overrides)
    return data


class TestCallableMembers:
    def test_full_decl_verbatim(self, make_state, find_entry):
        graph, state = make_state([_method(
            type_signature="virtual int getVersion() const = 0",
            name="getVersion",
            qualified_name="cpp_sqlite::Migration::getVersion",
        )])
        ctx = member.build_context(find_entry(graph, type_name="MethodNode"), state)
        assert ctx["declaration"] == "virtual int getVersion() const = 0"
        assert ctx["return_type"] == "int"
        assert ctx["name"] == "getVersion"
        assert ctx["role"] == "method"
        assert ctx["virtual"] is True
        assert ctx["const"] is True
        assert ctx["static"] is False
        assert ctx["params"] == []
        assert ctx["body"] is None
        assert ctx["visibility"] == "public"

    def test_pipeline_decl_minus_virtual(self, make_state, find_entry):
        """Pipeline-copy encoding: verbatim, but flags honestly False."""
        graph, state = make_state([_method(
            type_signature="int getVersion() const",
            name="getVersion",
            qualified_name="cpp_sqlite::Migration::getVersion",
        )])
        ctx = member.build_context(find_entry(graph, type_name="MethodNode"), state)
        assert ctx["declaration"] == "int getVersion() const"
        assert ctx["virtual"] is False
        assert ctx["const"] is True

    def test_as_built_reconstruction(self, make_state, find_entry):
        """Return-type-only encoding: reconstruct from ts + name + args."""
        graph, state = make_state([_method(
            type_signature="std::string",
            name="getTableName",
            qualified_name="cpp_sqlite::DataAccessObject::getTableName",
            argsstring="() const override",
            definition="std::string cpp_sqlite::DataAccessObject::getTableName",
            is_const=True,
        )])
        ctx = member.build_context(find_entry(graph, type_name="MethodNode"), state)
        assert ctx["declaration"] == "std::string getTableName() const override"
        assert ctx["return_type"] == "std::string"
        assert ctx["const"] is True

    def test_constructor_role(self, make_state, find_entry):
        graph, state = make_state([_method(
            name="MigrationManager",
            qualified_name="cpp_sqlite::MigrationManager::MigrationManager",
            type_signature="MigrationManager(cpp_sqlite::Database& db)",
        )])
        ctx = member.build_context(
            find_entry(graph, type_name="MethodNode"), state, parent_name="MigrationManager"
        )
        assert ctx["role"] == "constructor"
        assert ctx["return_type"] == ""
        assert ctx["params"] == [
            {"name": "db", "type": "cpp_sqlite::Database&", "default": ""}
        ]

    def test_destructor_role(self, make_state, find_entry):
        graph, state = make_state([_method(
            name="~Migration",
            qualified_name="cpp_sqlite::Migration::~Migration",
            type_signature="virtual ~Migration() = default",
        )])
        ctx = member.build_context(find_entry(graph, type_name="MethodNode"), state)
        assert ctx["role"] == "destructor"
        assert ctx["virtual"] is True
        assert ctx["body"] is None

    def test_operator_role(self, make_state, find_entry):
        graph, state = make_state([_method(
            name="operator==",
            qualified_name="cpp_sqlite::Widget::operator==",
            type_signature="bool operator==(const Widget& other) const",
        )])
        ctx = member.build_context(find_entry(graph, type_name="MethodNode"), state)
        assert ctx["role"] == "operator"
        assert ctx["params"] == [
            {"name": "other", "type": "const Widget&", "default": ""}
        ]

    def test_function_role(self, make_state, find_entry):
        graph, state = make_state([{
            "type": "FunctionNode",
            "canonical_key": 'cg:v1:repository:codegraph-suite%2Fcodegraph:function:qualified_name=cpp_sqlite%3A%3Ahelper:canonical_signature=lang%3Acpp%7C%28int%29',
            "name": "helper",
            "qualified_name": "cpp_sqlite::helper",
            "kind": "function",
            "type_signature": "int helper(int x)",
            "argsstring": "(int x)",
            "source": "test",
            "tags": ["design"],
        }])
        ctx = member.build_context(find_entry(graph, type_name="FunctionNode"), state)
        assert ctx["role"] == "function"
        assert ctx["params"] == [{"name": "x", "type": "int", "default": ""}]

    def test_qualified_name_and_docs(self, make_state, find_entry):
        graph, state = make_state([_method(
            brief_description="Applies all pending migrations.",
            detailed_description="Each in its own committed transaction.",
            line_number=42,
        )])
        ctx = member.build_context(find_entry(graph, type_name="MethodNode"), state)
        assert ctx["qualified_name"] == "cpp_sqlite::MigrationManager::apply"
        assert ctx["brief"] == "Applies all pending migrations."
        assert ctx["detailed"] == "Each in its own committed transaction."
        assert ctx["line_number"] == 42


class TestAttributes:
    def test_plain_attribute(self, make_state, find_entry):
        graph, state = make_state([{
            "type": "AttributeNode",
            "canonical_key": 'cg:v1:repository:codegraph-suite%2Fcodegraph:attribute:qualified_name=cpp_sqlite%3A%3AMigrationManager%3A%3Amigrations_',
            "name": "migrations_",
            "qualified_name": "cpp_sqlite::MigrationManager::migrations_",
            "kind": "attribute",
            "type_signature": "std::vector<std::unique_ptr<Migration>>",
            "visibility": "private",
            "source": "test",
            "tags": ["design"],
        }])
        ctx = member.build_context(find_entry(graph, type_name="AttributeNode"), state)
        assert ctx["type"] == "AttributeNode"
        assert ctx["kind"] == "attribute"
        assert ctx["name"] == "migrations_"
        assert ctx["type_signature"] == "std::vector<std::unique_ptr<Migration>>"
        assert ctx["is_static"] is False
        assert ctx["is_const"] is False
        assert ctx["visibility"] == "private"

    def test_typedef_definition_verbatim(self, make_state, find_entry):
        graph, state = make_state([{
            "type": "AttributeNode",
            "canonical_key": 'cg:v1:repository:codegraph-suite%2Fcodegraph:attribute:qualified_name=cpp_sqlite%3A%3Asqlite3',
            "name": "sqlite3",
            "qualified_name": "cpp_sqlite::sqlite3",
            "kind": "typedef",
            "definition": "typedef struct sqlite3 sqlite3",
            "source": "test",
            "tags": ["design"],
        }])
        ctx = member.build_context(find_entry(graph, type_name="AttributeNode"), state)
        assert ctx["kind"] == "typedef"
        assert ctx["declaration"] == "typedef struct sqlite3 sqlite3"

    def test_typedef_using_fallback(self, make_state, find_entry):
        graph, state = make_state([{
            "type": "AttributeNode",
            "canonical_key": 'cg:v1:repository:codegraph-suite%2Fcodegraph:attribute:qualified_name=cpp_sqlite%3A%3ACallback',
            "name": "Callback",
            "qualified_name": "cpp_sqlite::Callback",
            "kind": "typedef",
            "type_signature": "void (*)(int)",
            "definition": "",
            "source": "test",
            "tags": ["design"],
        }])
        ctx = member.build_context(find_entry(graph, type_name="AttributeNode"), state)
        assert ctx["declaration"] == "using Callback = void (*)(int)"


class TestPhase2:
    """Phase 2 fidelity: TypeRef normalization, HAS_PARAMETER params,
    typedef scope-strip, static/const attributes."""

    def test_as_built_declaration_normalized(self, make_state, find_entry):
        """Reconstructed as-built declarations collapse doxygen spacing
        (``Database &db`` → ``Database& db``); verbatim design
        declarations are untouched."""
        graph, state = make_state([_method(
            name="resolve",
            qualified_name="cpp_sqlite::ForeignKey::resolve",
            type_signature="std::optional< std::reference_wrapper< const T > >",
            argsstring="(Database &db)",
        )])
        ctx = member.build_context(find_entry(graph, type_name="MethodNode"), state)
        assert ctx["declaration"] == (
            "std::optional<std::reference_wrapper<const T>> resolve(Database& db)"
        )
        assert ctx["params"] == [
            {"name": "db", "type": "Database&", "default": ""}
        ]

    def test_full_decl_verbatim_untouched(self, make_state, find_entry):
        graph, state = make_state([_method(
            type_signature="virtual int getVersion() const = 0",
            name="getVersion",
            qualified_name="cpp_sqlite::Migration::getVersion",
        )])
        ctx = member.build_context(find_entry(graph, type_name="MethodNode"), state)
        assert ctx["declaration"] == "virtual int getVersion() const = 0"

    def test_has_parameter_backed_params(self):
        """HAS_PARAMETER references (typed, positional) drive the params
        list; argsstring supplies defaults; types are normalized."""
        from codegraph.graph import LayerGraph

        from codegraph.codegen.context import BuildState

        method_key = (
            "cg:v1:repository:codegraph-suite%2Fcodegraph:method:"
            "qualified_name=cpp_sqlite%3A%3ADatabase%3A%3ADatabase:"
            "canonical_signature=lang%3Acpp%7Cconstructor%7C%28"
            "std%3A%3Astring%2Cbool%29"
        )
        p_url = (
            "cg:v1:repository:codegraph-suite%2Fcodegraph:parameter:"
            "parent_callable_key=cg%3Av1%3Arepository%3Acodegraph-suite%252F"
            "codegraph%253Amethod%253Aqualified_name%253Dcpp_sqlite%25253A"
            "%25253ADatabase%25253A%25253ADatabase%253Acanonical_signature%253D"
            "lang%25253Acpp%25257Cconstructor%25257C%252528std%25253A%25253A"
            "string%25252Cbool%252529:position="
        )
        p_allow = p_url + "1"
        graph = _deser([
            {
                "type": "ParameterNode", "node_type": "ParameterNode",
                "name": "url", "type": "std::string", "position": 0,
                "canonical_key": p_url, "parent_callable_key": method_key,
                "source": "test", "tags": ["as-built"],
            },
            {
                "type": "ParameterNode", "node_type": "ParameterNode",
                "name": "allowWrite", "type": "bool", "position": 1,
                "canonical_key": p_allow, "parent_callable_key": method_key,
                "source": "test", "tags": ["as-built"],
            },
            {
                "type": "MethodNode",
                "canonical_key": method_key,
                "name": "Database",
                "qualified_name": "cpp_sqlite::Database::Database",
                "kind": "function",
                "type_signature": "",
                "argsstring": "(std::string url, bool allowWrite)",
                "source": "test", "tags": ["as-built"],
                "edges": [
                    {"relation_type": "HAS_PARAMETER", "target_key": p_url,
                     "target_type": "ParameterNode"},
                    {"relation_type": "HAS_PARAMETER", "target_key": p_allow,
                     "target_type": "ParameterNode"},
                ],
            },
        ])
        state = BuildState(graph=graph, flat=graph._flat_index())
        entry = next(e for e in graph._all_entries()
                     if type(e.node).__name__ == "MethodNode")
        ctx = member.build_context(entry, state)
        assert ctx["params"] == [
            {"name": "url", "type": "std::string", "default": ""},
            {"name": "allowWrite", "type": "bool", "default": ""},
        ]

    def test_attribute_type_normalized_and_static(self, make_state, find_entry):
        graph, state = make_state([{
            "type": "AttributeNode",
            "canonical_key": 'cg:v1:repository:codegraph-suite%2Fcodegraph:attribute:qualified_name=cpp_sqlite%3A%3AGetRepeatedFieldParams%3A%3AkIsSpecialization',
            "name": "kIsSpecialization",
            "qualified_name": "cpp_sqlite::GetRepeatedFieldParams::kIsSpecialization",
            "kind": "variable",
            "type_signature": "bool",
            "is_static": True,
            "source": "test",
            "tags": ["as-built"],
        }])
        ctx = member.build_context(find_entry(graph, type_name="AttributeNode"), state)
        assert ctx["is_static"] is True
        assert ctx["type_signature"] == "bool"

    def test_typedef_scope_stripped(self, make_state, find_entry):
        """As-built typedefs carry the fully-scoped declaration — the
        owning compound's own scope is stripped for member rendering."""
        graph, state = make_state([{
            "type": "AttributeNode",
            "canonical_key": 'cg:v1:repository:codegraph-suite%2Fcodegraph:attribute:qualified_name=cpp_sqlite%3A%3AForeignKeyTypeT%3C%20ForeignKey%3C%20T%20%3E%20%3E%3A%3Atype',
            "name": "type",
            "qualified_name": "cpp_sqlite::ForeignKeyTypeT< ForeignKey< T > >::type",
            "kind": "typedef",
            "definition": "using cpp_sqlite::ForeignKeyTypeT< ForeignKey< T > >::type = T",
            "source": "test",
            "tags": ["as-built"],
        }])
        entry = find_entry(graph, type_name="AttributeNode")
        ctx = member.build_context(
            entry, state, parent_qname="cpp_sqlite::ForeignKeyTypeT< ForeignKey< T > >"
        )
        assert ctx["declaration"] == "using type = T"


class TestEnumValues:
    def test_enum_value_with_initializer(self, make_state, find_entry):
        graph, state = make_state([{
            "type": "EnumValueNode",
            "canonical_key": 'cg:v1:repository:codegraph-suite%2Fcodegraph:enum-value:qualified_name=palette%3A%3AColor%3A%3ARed',
            "name": "Red",
            "qualified_name": "palette::Color::Red",
            "kind": "enumvalue",
            "initializer": "1 << 3",
            "source": "test",
            "tags": ["design"],
        }])
        ctx = member.build_context(find_entry(graph, type_name="EnumValueNode"), state)
        assert ctx["initializer"] == "1 << 3"

    def test_enum_value_implicit(self, make_state, find_entry):
        graph, state = make_state([{
            "type": "EnumValueNode",
            "canonical_key": 'cg:v1:repository:codegraph-suite%2Fcodegraph:enum-value:qualified_name=cpp_sqlite%3A%3AMigrationErrorCode%3A%3ASuccess',
            "name": "Success",
            "qualified_name": "cpp_sqlite::MigrationErrorCode::Success",
            "kind": "enumvalue",
            "source": "test",
            "tags": ["design"],
        }])
        ctx = member.build_context(find_entry(graph, type_name="EnumValueNode"), state)
        assert ctx["initializer"] == ""


class TestDefines:
    def test_define_definition_verbatim(self, make_state, find_entry):
        graph, state = make_state([{
            "type": "DefineNode",
            "canonical_key": 'cg:v1:repository:codegraph-suite%2Fcodegraph:define:qualified_name=CODEGRAPH_VERSION',
            "name": "CODEGRAPH_VERSION",
            "qualified_name": "CODEGRAPH_VERSION",
            "kind": "define",
            "definition": "#define CODEGRAPH_VERSION 1",
            "source": "test",
            "tags": ["design"],
        }])
        ctx = member.build_context(find_entry(graph, type_name="DefineNode"), state)
        assert ctx["definition"] == "#define CODEGRAPH_VERSION 1"
