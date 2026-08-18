"""Unit tests for round-trip verification (verify.py, tiers 1 and 2).

Pure Python — synthetic graphs, no external tools.  Tier 1 pins the
compound qname-subset semantics (std:: refs, template slots, dup-uid
placements excluded); Tier 2 pins the canonical method-uid key
``(scope, name) → (canonical params, canonical qualifiers)`` that
reconciles the design fixture's decl-minus-qualifiers encoding with the
parse's argsstring + glued-qname-suffix encoding.
"""

from __future__ import annotations

from codegraph.codegen.verify import verify
from codegraph.graph import LayerGraph
from tests.codegen.context.conftest import key_document as _kd

# TODO Move this into a conftest to avoid repetition
def _deser(data):
    return LayerGraph.deserialize(_kd(data))



# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _class(name, qn, **extra):
    data = {
        "type": "ClassNode", "name": name, "qualified_name": qn,
        "kind": "class", "source": "test", "tags": ["design"],
    }
    data.update(extra)
    return data


def _method(name, qn, ts, args, *, tags=("design",)):
    return {
        "type": "MethodNode", "name": name, "qualified_name": qn,
        "kind": "function", "source": "test", "tags": list(tags),
        "type_signature": ts, "argsstring": args,
    }


def _ns_class(name, qn, methods):
    return _class(name, qn, composes=methods)


# The golden loop's real method surface (design vs parse), trimmed:
# design carries decl-minus-qualifiers ts; the parse glues the args
# suffix onto the qname and keeps return-type-only ts + argsstring.
DESIGN_METHODS = [
    _method("getVersion", "cpp_sqlite::Migration::getVersion",
            "int getVersion() const", "()"),
    _method("up", "cpp_sqlite::Migration::up",
            "void up(Transaction& txn)", "(Transaction&)"),
    _method("register_migration",
            "cpp_sqlite::MigrationManager::register_migration",
            "MigrationResult register_migration(std::unique_ptr<Migration> migration)",
            "(std::unique_ptr<Migration>)"),
    _method("computeSchemaChecksum",
            "cpp_sqlite::MigrationManager::computeSchemaChecksum",
            "std::string computeSchemaChecksum() const", ""),
    _method("recordApplied",
            "cpp_sqlite::MigrationManager::recordApplied",
            "void recordApplied(const SchemaVersion& version)", ""),
]

AS_BUILT_METHODS = [
    _method("getVersion", "cpp_sqlite::Migration::getVersion(())",
            "int", "() const", tags=("codebase",)),
    _method("up", "cpp_sqlite::Migration::up(Transaction &txn)",
            "void", "(Transaction &txn)", tags=("codebase",)),
    _method("register_migration",
            "cpp_sqlite::MigrationManager::register_migration(std::unique_ptr< Migration >)",
            "MigrationResult", "(std::unique_ptr< Migration > migration)",
            tags=("codebase",)),
    _method("computeSchemaChecksum",
            "cpp_sqlite::MigrationManager::computeSchemaChecksum(())",
            "std::string", "() const", tags=("codebase",)),
    _method("recordApplied",
            "cpp_sqlite::MigrationManager::recordApplied(const SchemaVersion &version)",
            "void", "(const SchemaVersion &version)", tags=("codebase",)),
]

DESIGN = [
    _class("MigrationManager", "cpp_sqlite::MigrationManager"),
    _class("Migration", "cpp_sqlite::Migration"),
    _class("vector", "std::vector"),                       # library ref
    _class("IsVector", "cpp_sqlite::IsVector< std::vector< T, Allocator > >"),  # slot
]


class TestVerify:
    def test_subset_pass(self):
        design = _deser(DESIGN)
        as_built = _deser([
            _class("MigrationManager", "cpp_sqlite::MigrationManager"),
            _class("Migration", "cpp_sqlite::Migration"),
            _class("Extra", "cpp_sqlite::Extra"),          # parse-only
        ])
        report = verify(design, as_built)
        assert report.missing == []
        assert report.extra == ["cpp_sqlite::Extra"]
        assert report.template_slots == [
            "cpp_sqlite::IsVector< std::vector< T, Allocator > >",
            "std::vector",
        ]

    def test_missing_reported(self):
        design = _deser(DESIGN)
        as_built = _deser([
            _class("MigrationManager", "cpp_sqlite::MigrationManager"),
        ])
        report = verify(design, as_built)
        assert report.missing == ["cpp_sqlite::Migration"]

    def test_kinds_filter(self):
        design = _deser([
            _class("MigrationManager", "cpp_sqlite::MigrationManager"),
            {
                "type": "EnumNode", "name": "Code",
                "qualified_name": "cpp_sqlite::Code", "kind": "enum",
                "source": "test", "tags": ["design"],
            },
        ])
        as_built = _deser([
            _class("MigrationManager", "cpp_sqlite::MigrationManager"),
        ])
        # classes only: enum is out of scope → pass
        report = verify(design, as_built, kinds=frozenset({"ClassNode"}))
        assert report.missing == []
        # all kinds: enum missing → drift
        report_all = verify(design, as_built)
        assert report_all.missing == ["cpp_sqlite::Code"]

    def test_ambiguous_duplicate_uid_excluded(self):
        """D9: a struct nested in a parent AND peering under the namespace
        (same qname → same uid) is excluded from the assert — the emitted
        placement is ambiguous, and the parse scopes it one way."""
        design = _deser([
            {
                "type": "NamespaceNode", "name": "cpp_sqlite",
                "qualified_name": "cpp_sqlite", "kind": "namespace",
                "source": "test", "tags": ["design"],
                "composes": [
                    _class("MigrationManager", "cpp_sqlite::MigrationManager", composes=[
                        _class("MigrationResult", "cpp_sqlite::MigrationResult"),
                    ]),
                    # peer with the SAME qname → same uid (D9)
                    _class("MigrationResult", "cpp_sqlite::MigrationResult"),
                ],
            },
        ])
        as_built = _deser([
            _class("MigrationManager", "cpp_sqlite::MigrationManager"),
            # the parse scopes the nested struct inside the manager only
            _class("MigrationResult", "cpp_sqlite::MigrationManager::MigrationResult"),
        ])
        report = verify(design, as_built)
        assert report.missing == []
        assert report.ambiguous == ["cpp_sqlite::MigrationResult"]

    def test_tier_2_methods_match_across_encodings(self):
        """The canonical key reconciles design ts + parse argsstring/qname."""
        design = _deser([
            _ns_class("Migration", "cpp_sqlite::Migration",
                      DESIGN_METHODS[:2]),
            _ns_class("MigrationManager", "cpp_sqlite::MigrationManager",
                      DESIGN_METHODS[2:]),
        ])
        as_built = _deser([
            _ns_class("Migration", "cpp_sqlite::Migration",
                      AS_BUILT_METHODS[:2]),
            _ns_class("MigrationManager", "cpp_sqlite::MigrationManager",
                      AS_BUILT_METHODS[2:]),
        ])
        report = verify(design, as_built, tier=2)
        assert report.tier == 2
        assert report.missing_methods == []
        assert report.drift_methods == []
        assert report.extra_methods == []
        assert report.summarize().startswith("tier 2")

    def test_tier2_missing_and_extra(self):
        design = _deser([
            _ns_class("MigrationManager", "cpp_sqlite::MigrationManager",
                      DESIGN_METHODS[2:]),
        ])
        dropped = AS_BUILT_METHODS[:3] + AS_BUILT_METHODS[4:]  # no computeSchemaChecksum
        as_built = _deser([
            _ns_class("MigrationManager", "cpp_sqlite::MigrationManager",
                      dropped + [
                          _method("extra", "cpp_sqlite::MigrationManager::extra()",
                                  "void", "()", tags=("codebase",)),
                      ]),
        ])
        report = verify(design, as_built, tier=2)
        assert report.missing_methods == [
            "cpp_sqlite::MigrationManager::computeSchemaChecksum"
        ]
        assert report.extra_methods == [
            "cpp_sqlite::Migration::getVersion",
            "cpp_sqlite::Migration::up",
            "cpp_sqlite::MigrationManager::extra",
        ]
        assert report.drift_methods == []

    def test_tier2_signature_drift(self):
        """Same method key, different canonical params → drift, not missing."""
        design = _deser([
            _ns_class("Migration", "cpp_sqlite::Migration",
                      DESIGN_METHODS[:2]),
        ])
        wrong = [
            _method("up", "cpp_sqlite::Migration::up(Transaction &txn)",
                    "void", "(Transaction &txn, bool force)", tags=("codebase",)),
            _method("getVersion", "cpp_sqlite::Migration::getVersion(())",
                    "int", "() const", tags=("codebase",)),
        ]
        as_built = _deser([
            _ns_class("Migration", "cpp_sqlite::Migration", wrong),
        ])
        report = verify(design, as_built, tier=2)
        # getVersion matches exactly; up is present but with a different
        # param list → classified as signature drift, not missing.
        assert report.missing_methods == []
        assert report.drift_methods == ["cpp_sqlite::Migration::up"]

    def test_tier2_degraded_ctor_argsstring(self):
        """The degraded bare ctor argstring (no parens) still canonicalizes."""
        design = _deser([
            _ns_class("MigrationManager", "cpp_sqlite::MigrationManager", [
                _method("MigrationManager",
                        "cpp_sqlite::MigrationManager::MigrationManager(Database &db)",
                        "MigrationManager(Database& db)", "Database &db"),
            ]),
        ])
        as_built = _deser([
            _ns_class("MigrationManager", "cpp_sqlite::MigrationManager", [
                _method("MigrationManager",
                        "cpp_sqlite::MigrationManager::MigrationManager(Database &db)",
                        "", "(Database &db)", tags=("codebase",)),
            ]),
        ])
        report = verify(design, as_built, tier=2)
        assert report.missing_methods == []
        assert report.drift_methods == []
