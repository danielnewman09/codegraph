"""TypeRef tests — deterministic C++ spacing normalization + template
free-variable derivation (Phase 2 fidelity).

Pins: doxygen-index spacing artifacts collapse to source style
(``Database &db`` → ``Database& db``, ``std::shared_ptr< X >`` →
``std::shared_ptr<X>``, nested ``> >`` → ``>>``) while string literals,
numbers, ``=`` defaults, and identifiers survive byte-for-byte.
"""

from __future__ import annotations

from codegraph.codegen.typeref import (
    free_template_vars,
    normalize_declaration,
    normalize_type,
    scope_parts,
)


class TestNormalizeDeclaration:
    def test_template_args_hug(self):
        assert normalize_declaration("std::optional< std::reference_wrapper< const T > >") == (
            "std::optional<std::reference_wrapper<const T>>"
        )

    def test_refs_attach(self):
        assert normalize_declaration("Database &db") == "Database& db"
        assert normalize_declaration("const std::string &loggerName") == (
            "const std::string& loggerName"
        )
        assert normalize_declaration("Func &&func") == "Func&& func"
        assert normalize_declaration("PreparedSQLStmt &stmt") == "PreparedSQLStmt& stmt"

    def test_decltype_and_parens(self):
        assert normalize_declaration(
            "std::unique_ptr< sqlite3 , decltype(& sqlite3_close )> db_"
        ) == "std::unique_ptr<sqlite3, decltype(&sqlite3_close)> db_"

    def test_declaration_with_ctor_and_defaults(self):
        assert normalize_declaration(
            "Database(std::string url, bool allowWrite, "
            "std::shared_ptr< spdlog::logger > pLogger=nullptr)"
        ) == (
            "Database(std::string url, bool allowWrite, "
            "std::shared_ptr<spdlog::logger> pLogger=nullptr)"
        )

    def test_string_literals_survive(self):
        assert normalize_declaration(
            'bool configure(const std::string &loggerName = "cpp_sqlite", '
            'const std::string &logFile = "cpp_sqlite.log")'
        ) == (
            'bool configure(const std::string& loggerName="cpp_sqlite", '
            'const std::string& logFile="cpp_sqlite.log")'
        )

    def test_brace_initializers(self):
        assert normalize_declaration("uint32_t id{0}") == "uint32_t id{0}"
        assert normalize_declaration(
            "std::optional<std::reference_wrapper<const T>> data_{std::nullopt}"
        ) == "std::optional<std::reference_wrapper<const T>> data_{std::nullopt}"

    def test_deleted_and_default_markers(self):
        assert normalize_declaration("Logger(const Logger &)=delete") == (
            "Logger(const Logger&)=delete"
        )
        assert normalize_declaration("~Logger()=default") == "~Logger()=default"

    def test_qualified_names(self):
        assert normalize_declaration("spdlog::level::level_enum level=spdlog::level::info") == (
            "spdlog::level::level_enum level=spdlog::level::info"
        )
        assert normalize_declaration("IsForeignKeyT <T>::value") == "IsForeignKeyT<T>::value"

    def test_pointer_and_arrays(self):
        assert normalize_declaration("T * const") == "T* const"
        assert normalize_declaration("std::vector< T > data") == "std::vector<T> data"
        assert normalize_declaration("char buf[256]") == "char buf[256]"

    def test_static_and_qualifiers(self):
        assert normalize_declaration("static inline Logger & getInstance()") == (
            "static inline Logger& getInstance()"
        )
        assert normalize_declaration("bool isSet() const") == "bool isSet() const"

    def test_virtual_destructor(self):
        assert normalize_declaration("virtual ~DAOBase()=default") == (
            "virtual ~DAOBase()=default"
        )
        assert normalize_declaration("~Logger()=default") == "~Logger()=default"


class TestNormalizeType:
    def test_bare_type(self):
        assert normalize_type("std::vector< T >") == "std::vector<T>"
        assert normalize_type("const Transaction &") == "const Transaction&"


class TestFreeTemplateVars:
    def test_single_var(self):
        assert free_template_vars("< ForeignKey< T > >") == ["T"]

    def test_multiple_vars(self):
        assert free_template_vars("< std::vector< T, Allocator > >") == ["T", "Allocator"]

    def test_qualified_type_excluded(self):
        assert free_template_vars("< std::vector< T > >") == ["T"]

    def test_nested_type_args(self):
        assert free_template_vars("< RepeatedFieldTransferObject< T > >") == ["T"]


class TestScopeParts:
    def test_template_args_with_scope(self):
        assert scope_parts("cpp_sqlite::IsVector< std::vector< T, Allocator > >") == [
            "cpp_sqlite", "IsVector< std::vector< T, Allocator > >"
        ]

    def test_plain_scope(self):
        assert scope_parts("a::b::c") == ["a", "b", "c"]
        assert scope_parts("solo") == ["solo"]
