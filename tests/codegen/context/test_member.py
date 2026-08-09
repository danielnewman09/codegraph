"""Member context builder tests (R3 signature reconciliation applied).

Pins: full-declaration verbatim emission (both design encodings),
return-type-only reconstruction (as-built), role naming (ctor/dtor/
operator), string-derived flags (D8), attributes (plain + typedef),
enum values, and defines.
"""

from __future__ import annotations

from codegraph.codegen.context import member


def _method(**overrides):
    data = {
        "type": "MethodNode",
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

        p_url = "uid-param-url"
        p_allow = "uid-param-allow"
        graph = LayerGraph.deserialize([
            {
                "type": "ParameterNode", "node_type": "ParameterNode",
                "name": "url", "type": "std::string", "position": 0,
                "uid": p_url, "source": "test", "tags": ["as-built"],
            },
            {
                "type": "ParameterNode", "node_type": "ParameterNode",
                "name": "allowWrite", "type": "bool", "position": 1,
                "uid": p_allow, "source": "test", "tags": ["as-built"],
            },
            {
                "type": "MethodNode",
                "name": "Database",
                "qualified_name": "cpp_sqlite::Database::Database",
                "kind": "function",
                "type_signature": "",
                "argsstring": "(std::string url, bool allowWrite)",
                "source": "test", "tags": ["as-built"],
                "edges": [
                    {"relation_type": "HAS_PARAMETER", "target_uid": p_url,
                     "target_type": "ParameterNode"},
                    {"relation_type": "HAS_PARAMETER", "target_uid": p_allow,
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
            "name": "CODEGRAPH_VERSION",
            "qualified_name": "CODEGRAPH_VERSION",
            "kind": "define",
            "definition": "#define CODEGRAPH_VERSION 1",
            "source": "test",
            "tags": ["design"],
        }])
        ctx = member.build_context(find_entry(graph, type_name="DefineNode"), state)
        assert ctx["definition"] == "#define CODEGRAPH_VERSION 1"
