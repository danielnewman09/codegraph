"""Unit tests for codegen signature reconciliation (R3).

Pins the exact behavior of ``codegraph.codegen.signature``:
encoding detection (full-declaration vs return-type-only), declaration
splitting (leading/return_type/name/params/qualifiers/body_hint),
argsstring param parsing, R3 rule-2 reconstruction, R3 rule-3
out-of-line definitions, and include-guard computation.

The matrix mirrors the plan's documented test cases, including the two
design encodings in the goldens (full declaration vs declaration-minus-
qualifiers) and the degraded as-built argsstrings.
"""

from __future__ import annotations

import pytest

from codegraph.codegen.signature import (
    compute_guard,
    is_full_declaration,
    out_of_line_definition,
    reconstruct_declaration,
    split_argsstring,
    split_declaration,
)


# ── Encoding detection (R3 rule 1) ──────────────────────────────────────────

class TestIsFullDeclaration:
    @pytest.mark.parametrize(
        "ts",
        [
            "virtual int getVersion() const = 0",   # committed fixture (D8)
            "int getVersion() const",               # pipeline copy (minus virtual/=0)
            "MigrationResult apply()",
            "MigrationManager(cpp_sqlite::Database& db)",
            "explicit MigrationManager(Database& db)",
            "~Migration() = default",
            "static MigrationResult apply()",
        ],
    )
    def test_full_declarations(self, ts: str):
        assert is_full_declaration(ts) is True

    @pytest.mark.parametrize(
        "ts",
        ["int", "MigrationResult", "bool", "", "   ", "std::vector<int>"],
    )
    def test_return_type_only(self, ts: str):
        assert is_full_declaration(ts) is False


# ── Declaration splitting ───────────────────────────────────────────────────

class TestSplitDeclaration:
    def test_committed_fixture_full_decl(self):
        parts = split_declaration("virtual int getVersion() const = 0")
        assert parts.leading == "virtual"
        assert parts.return_type == "int"
        assert parts.name == "getVersion"
        assert parts.params == []
        assert parts.qualifiers == "const = 0"
        assert parts.body_hint is True
        assert parts.raw == "virtual int getVersion() const = 0"

    def test_pipeline_copy_decl_minus_virtual(self):
        parts = split_declaration("int getVersion() const")
        assert parts.leading == ""
        assert parts.return_type == "int"
        assert parts.name == "getVersion"
        assert parts.params == []
        assert parts.qualifiers == "const"
        assert parts.body_hint is False

    def test_plain_method(self):
        parts = split_declaration("MigrationResult apply()")
        assert parts.return_type == "MigrationResult"
        assert parts.name == "apply"
        assert parts.params == []
        assert parts.qualifiers == ""
        assert parts.body_hint is False

    def test_constructor(self):
        parts = split_declaration("MigrationManager(cpp_sqlite::Database& db)")
        assert parts.return_type == ""
        assert parts.name == "MigrationManager"
        assert parts.params == [
            {"name": "db", "type": "cpp_sqlite::Database&", "default": ""}
        ]

    def test_destructor_defaulted(self):
        parts = split_declaration("~Migration() = default")
        assert parts.return_type == ""
        assert parts.name == "~Migration"
        assert parts.params == []
        assert parts.qualifiers == "= default"
        assert parts.body_hint is True

    def test_bare_operator(self):
        parts = split_declaration("operator==")
        assert parts.return_type == ""
        assert parts.name == "operator=="
        assert parts.params == []
        assert parts.qualifiers == ""

    def test_operator_with_return_type(self):
        parts = split_declaration("bool operator==(const Foo& other) const")
        assert parts.return_type == "bool"
        assert parts.name == "operator=="
        assert parts.params == [{"name": "other", "type": "const Foo&", "default": ""}]
        assert parts.qualifiers == "const"

    def test_pure_virtual_with_typed_param(self):
        parts = split_declaration(
            "virtual void up(cpp_sqlite::Transaction& transaction) = 0"
        )
        assert parts.leading == "virtual"
        assert parts.return_type == "void"
        assert parts.name == "up"
        assert parts.params == [
            {"name": "transaction", "type": "cpp_sqlite::Transaction&", "default": ""}
        ]
        assert parts.qualifiers == "= 0"
        assert parts.body_hint is True

    def test_param_with_default_and_template(self):
        parts = split_declaration(
            "MigrationResult register_migration(std::unique_ptr<Migration> migration)"
        )
        assert parts.name == "register_migration"
        assert parts.params == [
            {"name": "migration", "type": "std::unique_ptr<Migration>", "default": ""}
        ]

    def test_degraded_as_built_argsstring(self):
        parts = split_declaration("() const override")
        assert parts.name == ""
        assert parts.return_type == ""
        assert parts.params == []
        assert parts.qualifiers == "const override"
        assert parts.body_hint is False

    def test_explicit_constructor(self):
        parts = split_declaration("explicit MigrationManager(Database& db)")
        assert parts.leading == "explicit"
        assert parts.name == "MigrationManager"
        assert parts.params == [{"name": "db", "type": "Database&", "default": ""}]

    def test_empty_string(self):
        parts = split_declaration("")
        assert parts.name == ""
        assert parts.raw == ""


# ── Argsstring parsing (R6) ─────────────────────────────────────────────────

class TestSplitArgsstring:
    def test_empty(self):
        assert split_argsstring("") == []

    def test_bare_parens(self):
        assert split_argsstring("()") == []

    def test_parens_with_trailing_qualifiers(self):
        assert split_argsstring("() const override") == []

    def test_multiple_params_with_defaults(self):
        params = split_argsstring(
            "(Database &database, std::shared_ptr< spdlog::logger > pLogger=nullptr)"
        )
        assert params == [
            {"name": "database", "type": "Database &", "default": ""},
            {
                "name": "pLogger",
                "type": "std::shared_ptr< spdlog::logger >",
                "default": "nullptr",
            },
        ]

    def test_nameless_param(self):
        assert split_argsstring("(std::unique_ptr<Migration>)") == [
            {"type": "std::unique_ptr<Migration>", "name": "", "default": ""}
        ]

    def test_single_named_param(self):
        assert split_argsstring("(int target_version)") == [
            {"name": "target_version", "type": "int", "default": ""}
        ]

    def test_ref_without_name(self):
        assert split_argsstring("(Transaction&)") == [
            {"type": "Transaction&", "name": "", "default": ""}
        ]

    def test_bare_param_list_without_parens(self):
        """Degraded ctor argstring (working-tree design fixture)."""
        assert split_argsstring("Database &db") == [
            {"name": "db", "type": "Database &", "default": ""}
        ]

    def test_nested_template_with_commas(self):
        params = split_argsstring("(std::map<int, std::vector<int>> m)")
        assert params == [
            {"name": "m", "type": "std::map<int, std::vector<int>>", "default": ""}
        ]

    def test_default_with_braces(self):
        params = split_argsstring("(const SchemaVersion& version = SchemaVersion{})")
        assert params == [
            {
                "name": "version",
                "type": "const SchemaVersion&",
                "default": "SchemaVersion{}",
            }
        ]

    def test_pointer_and_reference_suffix(self):
        params = split_argsstring("(const char* name, void* data)")
        assert params == [
            {"name": "name", "type": "const char*", "default": ""},
            {"name": "data", "type": "void*", "default": ""},
        ]

    def test_pointer_prefixed_name(self):
        params = split_argsstring("(sqlite3_stmt* pStmt)")
        assert params == [
            {"name": "pStmt", "type": "sqlite3_stmt*", "default": ""}
        ]

    def test_single_type_no_name(self):
        assert split_argsstring("(bool)") == [
            {"type": "bool", "name": "", "default": ""}
        ]

    def test_array_param_degrades_gracefully(self):
        """Phase 1 limitation: arrays stay whole-segment (documented)."""
        assert split_argsstring("(int arr[10])") == [
            {"type": "int arr[10]", "name": "", "default": ""}
        ]


# ── R3 rule 2: reconstruction from return-type-only encoding ────────────────

class TestReconstructDeclaration:
    def test_flag_virtual(self):
        decl = reconstruct_declaration(
            "int", "getVersion", "()", flags={"is_virtual": True}
        )
        assert decl == "virtual int getVersion()"

    def test_flag_virtual_and_const(self):
        decl = reconstruct_declaration(
            "int", "getVersion", "()",
            flags={"is_virtual": True, "is_const": True},
        )
        assert decl == "virtual int getVersion() const"

    def test_no_flags(self):
        assert reconstruct_declaration("MigrationResult", "apply", "()") == (
            "MigrationResult apply()"
        )

    def test_no_duplicate_const(self):
        decl = reconstruct_declaration(
            "int", "getVersion", "() const", flags={"is_const": True}
        )
        assert decl == "int getVersion() const"

    def test_no_duplicate_virtual(self):
        decl = reconstruct_declaration(
            "void", "up", "(Transaction&)", flags={"is_virtual": True}
        )
        assert decl == "virtual void up(Transaction&)"

    def test_degraded_argsstring_wrapped_in_parens(self):
        decl = reconstruct_declaration("", "MigrationManager", "Database &db")
        assert decl == "MigrationManager(Database &db)"

    def test_empty_argsstring(self):
        assert reconstruct_declaration("std::string", "computeSchemaChecksum", "") == (
            "std::string computeSchemaChecksum()"
        )


# ── R3 rule 3: as-built out-of-line definitions ─────────────────────────────

class TestOutOfLineDefinition:
    def test_strips_namespace_prefix(self):
        defn = out_of_line_definition(
            "bool cpp_sqlite::DataAccessObject< T >::isInitialized",
            "() const override",
            "cpp_sqlite::",
        )
        assert defn == "bool DataAccessObject< T >::isInitialized() const override"

    def test_no_scope_prefix(self):
        defn = out_of_line_definition(
            "bool cpp_sqlite::DataAccessObject< T >::isInitialized",
            "() const override",
            "",
        )
        assert defn == (
            "bool cpp_sqlite::DataAccessObject< T >::isInitialized() const override"
        )

    def test_definition_without_matching_prefix(self):
        defn = out_of_line_definition("bool foo()", " const", "cpp_sqlite::")
        assert defn == "bool foo() const"

    def test_constructor_definition(self):
        defn = out_of_line_definition(
            "cpp_sqlite::DataAccessObject< T >::DataAccessObject",
            "(Database &database)",
            "cpp_sqlite::",
        )
        assert defn == "DataAccessObject< T >::DataAccessObject(Database &database)"


# ── Include guards ──────────────────────────────────────────────────────────

class TestComputeGuard:
    def test_header(self):
        assert compute_guard("include/cpp_sqlite/DataAccessObject.hpp") == (
            "INCLUDE_CPP_SQLITE_DATAACCESSOBJECT_HPP"
        )

    def test_source(self):
        assert compute_guard("src/foo.cpp") == "SRC_FOO_CPP"

    def test_leading_dot_slash(self):
        assert compute_guard("./include/x.hpp") == "INCLUDE_X_HPP"

    def test_empty(self):
        assert compute_guard("") == ""
