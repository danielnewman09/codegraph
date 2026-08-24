"""Golden fixture integrity + sync convention (R1).

Pins the two golden design LayerGraphs:
- ``design_layergraph.json`` — current generator output (split encoding);
- ``design_layergraph_full_decl.json`` — committed full-declaration
  version (spec D8).

Asserts the goldens are valid, deserialize into LayerGraphs, carry the
encodings the signature reconciliation rule (R3) must handle, track the
pipeline generator output, and that the sync script's push/pull/check
behave (against a sandbox, never the real sister repo).
"""

from __future__ import annotations

import importlib.util
import json
from collections import Counter
from pathlib import Path

import pytest

from codegraph.identity import encode_key
from codegraph.identity import CanonicalIdentity
from codegraph.graph import LayerGraph
from codegraph.graph import GraphDocumentError


def _deser(data):
    return LayerGraph.deserialize(data)


GOLDEN_DIR = Path(__file__).resolve().parent / "golden"
GOLDEN_SPLIT = GOLDEN_DIR / "design_layergraph.json"
GOLDEN_FULL_DECL = GOLDEN_DIR / "design_layergraph_full_decl.json"
PIPELINE_COPY = (
    Path(__file__).resolve().parent.parent / "pipelines" / "unit_test_data"
    / "design_layergraph.json"
)
SISTER_DESIGN = (
    Path(__file__).resolve().parents[3]
    / "Doxygen-Dependency-Parser" / "tests" / "data" / "design_layergraph.json"
)
COMPLETE_GRAPH = (
    Path(__file__).resolve().parents[1]
    / "pipelines" / "data" / "cpp_sqlite" / "codegraph_as_built.json"
)

_SCRIPT = Path(__file__).resolve().parent.parent.parent / "scripts" \
    / "sync_codegen_fixtures.py"


def _load(path: Path) -> list[dict]:
    import json

    return json.loads(path.read_text(encoding="utf-8"))


def _total_nodes(entries: list[dict]) -> int:
    total = 0

    def walk(items: list[dict]) -> None:
        nonlocal total
        for entry in items:
            total += 1
            walk(entry.get("composes", []))

    walk(entries)
    return total


def _method_nodes(entries: list[dict]) -> list[dict]:
    out: list[dict] = []

    def walk(items: list[dict]) -> None:
        for entry in items:
            if entry.get("type") == "MethodNode":
                out.append(entry)
            walk(entry.get("composes", []))

    walk(entries)
    return out


def _relationship_multiset(entries: list[dict]) -> Counter[tuple[str, str, str, str]]:
    """Count explicit and structural relationships by canonical endpoint."""
    inventory: Counter[tuple[str, str, str, str]] = Counter()

    def walk(items: list[dict]) -> None:
        for entry in items:
            source = entry["canonical_key"]
            for child in entry.get("composes", []):
                inventory[(source, "COMPOSES", child["canonical_key"], child["type"])] += 1
                walk([child])
            for edge in entry.get("edges", []):
                inventory[(
                    source,
                    edge["relation_type"],
                    edge["target_key"],
                    edge["target_type"],
                )] += 1

    walk(entries)
    return inventory


_DESIGN_SCOPE = "codegraph-suite/codegraph"


def _reconciled_key(category: str, fields: list[tuple[str, str]]) -> str:
    return encode_key("repository", _DESIGN_SCOPE, category, fields)


# The target identities are derived from the complete cpp-sqlite extraction
# fixture.  The source fixture uses the design repository scope, so the
# identity fields are re-encoded in that scope rather than copying an old UID.
_RECONCILIATION = {
    ("cpp_sqlite::BaseTransferObject", "DEFINED_IN", "FileNode"): _reconciled_key(
        "file", [("normalized_repository_path", "tests/fixtures/cpp-sqlite/cpp_sqlite/src/cpp_sqlite/DBBaseTransferObject.hpp")]
    ),
    ("cpp_sqlite::Database", "DEFINED_IN", "FileNode"): _reconciled_key(
        "file", [("normalized_repository_path", "tests/fixtures/cpp-sqlite/cpp_sqlite/src/cpp_sqlite/DBDatabase.hpp")]
    ),
    ("cpp_sqlite::DataAccessObject", "DEFINED_IN", "FileNode"): _reconciled_key(
        "file", [("normalized_repository_path", "tests/fixtures/cpp-sqlite/cpp_sqlite/src/cpp_sqlite/DBDataAccessObject.hpp")]
    ),
    ("cpp_sqlite::DataAccessObject", "INHERITS_FROM", "ClassNode"): _reconciled_key(
        "class", [("qualified_name", "DAOBase")]
    ),
    ("cpp_sqlite::ForeignKeyTypeT< ForeignKey< T > >", "DEFINED_IN", "FileNode"): _reconciled_key(
        "file", [("normalized_repository_path", "tests/fixtures/cpp-sqlite/cpp_sqlite/src/cpp_sqlite/DBTraits.hpp")]
    ),
    ("cpp_sqlite::ForeignKey", "DEFINED_IN", "FileNode"): _reconciled_key(
        "file", [("normalized_repository_path", "tests/fixtures/cpp-sqlite/cpp_sqlite/src/cpp_sqlite/DBForeignKey.hpp")]
    ),
    ("cpp_sqlite::Logger", "DEFINED_IN", "FileNode"): _reconciled_key(
        "file", [("normalized_repository_path", "tests/fixtures/cpp-sqlite/cpp_sqlite/src/utils/Logger.hpp")]
    ),
    ("cpp_sqlite::RepeatedFieldTransferObject", "DEFINED_IN", "FileNode"): _reconciled_key(
        "file", [("normalized_repository_path", "tests/fixtures/cpp-sqlite/cpp_sqlite/src/cpp_sqlite/DBRepeatedFieldTransferObject.hpp")]
    ),
    ("cpp_sqlite::Transaction", "DEFINED_IN", "FileNode"): _reconciled_key(
        "file", [("normalized_repository_path", "tests/fixtures/cpp-sqlite/cpp_sqlite/src/cpp_sqlite/DBTransaction.hpp")]
    ),
    ("cpp_sqlite::TransactionError", "INHERITS_FROM", "ClassNode"): _reconciled_key(
        "class", [("qualified_name", "std::runtime_error")]
    ),
    ("cpp_sqlite::ValidTransferObject", "CONSTRAINS", "MethodNode"): {
        _reconciled_key(
            "method",
            [("qualified_name", "cpp_sqlite::Database::getDAO()"),
             ("canonical_signature", "lang:cpp|template:[ValidTransferObject T]|()")],
        ),
        _reconciled_key(
            "method",
            [("qualified_name", "cpp_sqlite::Database::select(PreparedSQLStmt &stmt)"),
             ("canonical_signature", "lang:cpp|template:[ValidTransferObject T]|(PreparedSQLStmt&)" )],
        ),
        _reconciled_key(
            "method",
            [("qualified_name", "cpp_sqlite::Database::insert(PreparedSQLStmt &stmt, T &data)"),
             ("canonical_signature", "lang:cpp|template:[ValidTransferObject T]|(PreparedSQLStmt&,T&)")],
        ),
    },
    ("cpp_sqlite::isSupportedDBType", "CONSTRAINS", "MethodNode"): _reconciled_key(
        "method",
        [("qualified_name", "cpp_sqlite::DataAccessObject::getSQLType()"),
         ("canonical_signature", "lang:cpp|template:[isSupportedDBType FieldType]|()")],
    ),
}


@pytest.fixture(scope="module")
def sync_module():
    """Import scripts/sync_codegen_fixtures.py as a module."""
    spec = importlib.util.spec_from_file_location("sync_codegen_fixtures", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestGoldensExistAndDeserialize:
    @pytest.mark.parametrize("path", [GOLDEN_SPLIT, GOLDEN_FULL_DECL])
    def test_golden_is_valid_json(self, path: Path):
        entries = _load(path)
        assert entries, f"{path.name} is empty"

    @pytest.mark.parametrize("path", [GOLDEN_SPLIT, GOLDEN_FULL_DECL])
    def test_golden_deserializes_to_layer_graph(self, path: Path):
        graph = _deser(_load(path))
        assert graph.entries, f"{path.name} produced no root entries"

    def test_split_golden_is_current_generator_output(self):
        """The reviewed golden must match the generator artifact byte-for-byte."""
        assert GOLDEN_SPLIT.read_bytes() == PIPELINE_COPY.read_bytes(), (
            "golden/design_layergraph.json diverged from the pipeline "
            "generator output — run scripts/sync_codegen_fixtures.py push; "
            f"paths: {GOLDEN_SPLIT} and {PIPELINE_COPY}"
        )

    def test_split_golden_size(self):
        assert _total_nodes(_load(GOLDEN_SPLIT)) == 179

    def test_full_decl_golden_size(self):
        assert _total_nodes(_load(GOLDEN_FULL_DECL)) == 155


class TestEncodingContract:
    """The two goldens exercise both encodings the R3 rule must handle."""

    def test_split_encoding_is_declaration_minus_virtual(self):
        """The split golden encodes members as return-type-only or
        declaration-minus-qualifiers (R3 rule 1/2 must render verbatim)."""
        methods = _method_nodes(_load(GOLDEN_SPLIT))
        get_version = next(
            m for m in methods if m.get("name") == "getVersion"
        )
        assert get_version["type_signature"] == "int"
        assert get_version["argsstring"] == "()"

    def test_split_encoding_params_are_typed(self):
        """D6 invariant: composed members carry types in type_signature
        (the return type); parameter types live in argsstring."""
        methods = _method_nodes(_load(GOLDEN_SPLIT))
        register = next(
            m for m in methods if m.get("name") == "register_migration"
        )
        assert register["type_signature"] == "MigrationResult"
        assert "std::unique_ptr<Migration>" in register["argsstring"]
        attrs = []

        def walk(items, parent_type):
            for e in items:
                if e.get("type") == "AttributeNode" and parent_type == "ClassNode":
                    attrs.append(e)
                walk(e.get("composes", []), e.get("type"))

        walk(_load(GOLDEN_SPLIT), None)
        assert attrs, "no composed attributes found"
        assert all(
            a.get("type_signature", "").strip() for a in attrs
        ), "untyped composed attribute in split golden"

    def test_full_decl_encoding_has_full_declaration(self):
        methods = _method_nodes(_load(GOLDEN_FULL_DECL))
        get_version = next(
            m for m in methods if m.get("name") == "getVersion"
        )
        assert get_version["type_signature"] == "virtual int getVersion() const = 0"

    def test_flags_unreliable_on_design_nodes(self):
        """D8: is_virtual is False despite a virtual declaration."""
        methods = _method_nodes(_load(GOLDEN_FULL_DECL))
        get_version = next(
            m for m in methods if m.get("name") == "getVersion"
        )
        assert get_version["is_virtual"] is False

    def test_duplicate_canonical_keys_present_in_full_decl(self):
        """Repeated placements retain one canonical identity each."""
        keys = {}

        def walk(items: list[dict]) -> None:
            for entry in items:
                keys[entry["canonical_key"]] = keys.get(entry["canonical_key"], 0) + 1
                walk(entry.get("composes", []))

        walk(_load(GOLDEN_FULL_DECL))
        duplicates = {u: c for u, c in keys.items() if c > 1}
        assert len(duplicates) == 10


class TestPortableEndpointContract:
    """Exercise the three legal endpoint states on both encodings."""

    @staticmethod
    def _key(name: str, category: str = "class") -> str:
        fields = (
            [("qualified_name", name)]
            if category == "class"
            else [("qualified_name", name), ("canonical_signature", "lang:cpp|()")]
        )
        return encode_key("repository", "portable-tests", category, fields)

    @classmethod
    def _node(cls, name: str, *, key: str | None = None, node_type: str = "ClassNode"):
        return {
            "type": node_type,
            "name": name.rsplit("::", 1)[-1],
            "kind": "class" if node_type == "ClassNode" else "function",
            "qualified_name": name,
            "source": "portable-tests",
            "tags": ["as-built"],
            "canonical_key": key or cls._key(name),
            "edges": [],
        }

    def test_flat_included_endpoint_closes_and_external_roundtrips(self):
        source_key = self._key("portable::Source")
        target_key = self._key("portable::Target")
        excluded_key = self._key("portable::Excluded")
        source = self._node("portable::Source", key=source_key)
        source["edges"] = [
            {
                "relation_type": "DEPENDS_ON",
                "target_key": target_key,
                "target_type": "ClassNode",
            },
            {
                "relation_type": "DEPENDS_ON",
                "target_key": excluded_key,
                "target_type": "ClassNode",
                "external": True,
            },
        ]
        graph = LayerGraph.deserialize([source, self._node("portable::Target", key=target_key)])
        encoded = graph.serialize(fields="llm")
        edges = encoded[0]["edges"]
        included = next(edge for edge in edges if edge["target_key"] == target_key)
        external = next(edge for edge in edges if edge["target_key"] == excluded_key)
        assert "external" not in included
        assert external["external"] is True

        roundtrip = LayerGraph.deserialize(encoded).serialize(fields="all")
        roundtrip_edge = next(
            edge for edge in roundtrip[0]["edges"]
            if edge.get("target_key") == excluded_key
        )
        assert roundtrip_edge["external"] is True

    def test_nested_unresolved_endpoint_has_diagnostic(self):
        source_key = self._key("portable::Source")
        child_key = self._key("portable::Child")
        data = [
            {
                **self._node("portable::Source", key=source_key),
                "composes": [self._node("portable::Child", key=child_key)],
                "edges": [{
                    "relation_type": "DEPENDS_ON",
                    "target_key": child_key,
                    "target_type": "ClassNode",
                }],
            }
        ]
        graph = LayerGraph.deserialize(data)
        edge = graph.serialize(fields="all")[0]["edges"][0]
        assert edge["target_key"] == child_key
        assert "external" not in edge

        unknown = [
            {
                **self._node("portable::Source", key=source_key),
                "edges": [{
                    "relation_type": "DEPENDS_ON",
                    "target_key": self._key("portable::NotSelected"),
                    "target_type": "ClassNode",
                }],
            }
        ]
        unknown_edge = LayerGraph.deserialize(unknown).serialize(
            fields="all"
        )[0]["edges"][0]
        assert "target_key" not in unknown_edge
        assert unknown_edge["target_ref"]
        assert unknown_edge["unresolved"] is True
        assert unknown_edge["diagnostic"]

        unresolved = [
            {
                **self._node("portable::Source", key=source_key),
                "edges": [{
                    "relation_type": "INVOKES",
                    "target_ref": "unresolved::call",
                    "target_type": "MethodNode",
                    "unresolved": True,
                    "diagnostic": "parser did not resolve the referenced call",
                }],
            }
        ]
        unresolved_graph = LayerGraph.deserialize(unresolved)
        result = unresolved_graph.serialize(fields="all")[0]["edges"][0]
        assert result["target_ref"] == "unresolved::call"
        assert result["unresolved"] is True
        assert result["diagnostic"]

    def test_malformed_external_and_duplicate_keys_are_rejected(self):
        source_key = self._key("portable::Source")
        malformed = self._node("portable::Source", key=source_key)
        malformed["edges"] = [{
            "relation_type": "DEPENDS_ON",
            "target_key": "not-a-canonical-key",
            "target_type": "ClassNode",
            "external": True,
        }]
        with pytest.raises(GraphDocumentError, match="invalid edge target_key"):
            LayerGraph.deserialize([malformed])

        in_document_external = self._node("portable::Source", key=source_key)
        in_document_external["edges"] = [{
            "relation_type": "DEPENDS_ON",
            "target_key": self._key("portable::Target"),
            "target_type": "ClassNode",
            "external": True,
        }]
        with pytest.raises(GraphDocumentError, match="in-document target"):
            LayerGraph.deserialize([
                in_document_external,
                self._node("portable::Target", key=self._key("portable::Target")),
            ])

        duplicate = self._node("portable::Other", key=source_key)
        with pytest.raises(ValueError, match="duplicate|conflict|canonical"):
            LayerGraph.deserialize([self._node("portable::Source", key=source_key), duplicate])

    def test_sync_checker_rejects_injected_unclassified_edge(self, sync_module, tmp_path):
        path = tmp_path / "injected.json"
        source_key = self._key("portable::Source")
        source = self._node("portable::Source", key=source_key)
        source["edges"] = [{
            "relation_type": "DEPENDS_ON",
            "target_key": self._key("portable::Missing"),
            "target_type": "ClassNode",
        }]
        import json
        path.write_text(json.dumps([source]), encoding="utf-8")
        problems = sync_module._validate_portable_json(path)
        assert any("not classified external" in problem for problem in problems)

    def test_known_omitted_target_exports_as_external(self):
        source_key = self._key("portable::Source")
        target_key = self._key("portable::KnownButOmitted")
        source = self._node("portable::Source", key=source_key)
        source["edges"] = [{
            "relation_type": "DEPENDS_ON",
            "target_key": target_key,
            "target_type": "ClassNode",
        }]
        graph = LayerGraph.deserialize([source])
        graph.known_keys = frozenset({source_key, target_key})

        edge = graph.serialize(fields="all")[0]["edges"][0]
        assert edge["target_key"] == target_key
        assert edge["external"] is True
        assert "target_ref" not in edge
        assert "unresolved" not in edge

    def test_sync_checker_rejects_uid_shaped_target_ref(self, sync_module, tmp_path):
        path = tmp_path / "design_layergraph.json"
        source = self._node("portable::Source", key=self._key("portable::Source"))
        source["edges"] = [{
            "relation_type": "DEPENDS_ON",
            "target_ref": "a" * 40,
            "target_type": "ClassNode",
        }]
        import json
        path.write_text(json.dumps([source]), encoding="utf-8")

        problems = sync_module._validate_portable_json(path)
        assert any("UID-shaped target_ref" in problem for problem in problems)


class TestDesignFixtureFamily:
    """The synchronized design copies contain only canonical endpoints."""

    @staticmethod
    def _walk(entries):
        for entry in entries:
            yield entry
            yield from TestDesignFixtureFamily._walk(entry.get("composes", []))

    @pytest.mark.parametrize("path", [GOLDEN_SPLIT, PIPELINE_COPY, SISTER_DESIGN])
    def test_all_relationships_use_reconciled_canonical_targets(self, path):
        entries = _load(path)
        nodes = list(self._walk(entries))
        node_keys = {node["canonical_key"] for node in nodes}
        affected = []

        for node in nodes:
            for edge in node.get("edges", []):
                assert "target_ref" not in edge
                assert edge.get("unresolved") is not True
                assert "diagnostic" not in edge
                target_key = edge.get("target_key")
                assert isinstance(target_key, str) and target_key
                CanonicalIdentity.from_key(target_key)
                if target_key in node_keys:
                    assert edge.get("external") is not True
                else:
                    assert edge.get("external") is True

                signature = (
                    node.get("qualified_name"),
                    edge.get("relation_type"),
                    edge.get("target_type"),
                )
                if (
                    edge.get("relation_type") == "DEFINED_IN"
                    and edge.get("target_type") == "FileNode"
                ):
                    expected = _reconciled_key(
                        "file",
                        [("normalized_repository_path", node["file_path"])],
                    )
                    assert target_key == expected
                elif signature in _RECONCILIATION:
                    expected = _RECONCILIATION[signature]
                    if isinstance(expected, set):
                        assert target_key in expected
                    else:
                        assert target_key == expected

                if edge.get("external") is True:
                    affected.append((signature, target_key))

        assert len(affected) == 34
        assert len({target for _, target in affected}) == 14
        assert all(target not in node_keys for _, target in affected)


class TestCompleteAsBuiltFixture:
    """The committed artifact is a bounded canonical cpp-sqlite view."""

    @staticmethod
    def _walk(entries):
        for entry in entries:
            yield entry
            yield from TestCompleteAsBuiltFixture._walk(entry.get("composes", []))

    def test_every_endpoint_is_canonical_and_closed(self):
        entries = _load(COMPLETE_GRAPH)
        nodes = list(self._walk(entries))
        keys = {node.get("canonical_key") for node in nodes}
        assert len(keys) == len(nodes)
        assert nodes
        assert any(node.get("source") == "cpp-sqlite" for node in nodes)

        for node in nodes:
            assert not {
                "uid", "target_uid", "refid", "compound_refid",
                "member_refid", "parent_refid", "child_refid",
            } & set(node)
            CanonicalIdentity.from_key(node["canonical_key"])
            for edge in node.get("edges", []):
                assert edge.get("relation_type")
                assert edge.get("target_type")
                assert "target_ref" not in edge
                assert edge.get("unresolved") is not True
                assert "diagnostic" not in edge
                assert not {
                    "uid", "target_uid", "refid", "from_refid", "to_refid",
                } & set(edge)
                target = edge.get("target_key")
                assert isinstance(target, str) and target
                CanonicalIdentity.from_key(target)
                if target in keys:
                    assert edge.get("external") is not True
                else:
                    assert edge.get("external") is True

    def test_import_serialize_preserves_relationship_multiset(self):
        entries = _load(COMPLETE_GRAPH)
        graph = LayerGraph.deserialize(entries)
        serialized = graph.serialize(fields="all")
        assert _relationship_multiset(entries) == _relationship_multiset(serialized)
        assert serialized == LayerGraph.deserialize(serialized).serialize(fields="all")
        assert all(
            "target_ref" not in edge
            for node in self._walk(serialized)
            for edge in node.get("edges", [])
        )

    def test_sync_checker_rejects_injected_target_ref(self, sync_module, tmp_path):
        import json

        entries = _load(COMPLETE_GRAPH)
        entries[0].setdefault("edges", []).append({
            "relation_type": "DEPENDS_ON",
            "target_ref": "a" * 40,
            "target_type": "ClassNode",
        })
        path = tmp_path / "codegraph_as_built.json"
        path.write_text(json.dumps(entries), encoding="utf-8")
        problems = sync_module._validate_portable_json(path)
        assert any("target_ref" in problem for problem in problems)



class TestSyncScript:
    """Sandboxed — never touches the real sibling repo."""

    _CONTENT = (
        '[{"canonical_key":"cg:v1:repository:portable-tests:class:'
        'qualified_name=portable%3A%3ASource","edges":[],"name":"Source",'
        '"qualified_name":"portable::Source","source":"portable-tests",'
        '"tags":["as-built"],"type":"ClassNode"}]\n'
    )
    _OTHER = (
        '[{"canonical_key":"cg:v1:repository:portable-tests:class:'
        'qualified_name=portable%3A%3AOther","edges":[],"name":"Other",'
        '"qualified_name":"portable::Other","source":"portable-tests",'
        '"tags":["as-built"],"type":"ClassNode"}]\n'
    )

    def _setup(self, sync_module, tmp_path: Path, *, with_sister: bool = True):
        canonical = tmp_path / "sister.json"
        gen = tmp_path / "design_layergraph.json"
        golden = tmp_path / "golden.json"
        one_hop = tmp_path / "one_hop.json"
        sister_one_hop = tmp_path / "sister_one_hop.json"
        impl = tmp_path / "impl.json"
        sister_impl = tmp_path / "sister_impl.json"
        complete = tmp_path / "complete.json"
        for p in (
            canonical, gen, golden, one_hop, sister_one_hop, impl,
            sister_impl, complete,
        ):
            p.write_text(self._CONTENT, encoding="utf-8")
        sync_module.PIPELINE_COPY = gen
        sync_module.GOLDEN = golden
        sync_module.SISTER_CANONICAL = canonical
        sync_module.SISTER = tmp_path if with_sister else tmp_path / "no-sister"
        sync_module.ONE_HOP = one_hop
        sync_module.SISTER_ONE_HOP = sister_one_hop
        sync_module.IMPL = impl
        sync_module.SISTER_IMPL = sister_impl
        sync_module.COMPLETE_GRAPH = complete
        # Priority-1 provenance sandbox: a fake manifest + source copies +
        # provenance record under tmp_path (never the real fixture).
        sync_module.MANIFEST = tmp_path / "manifest.txt"
        sync_module.PROVENANCE = tmp_path / "provenance.md"
        sync_module.IMPL_SRC = tmp_path / "impl_src"
        rel = "tests/fixtures/cpp-sqlite/cpp_sqlite/src/cpp_sqlite/A.hpp"
        sync_module.MANIFEST.write_text(f"{rel}\n", encoding="utf-8")
        src = sync_module.IMPL_SRC / rel
        src.parent.mkdir(parents=True, exist_ok=True)
        src.write_text("int golden;\n", encoding="utf-8")
        import hashlib
        digest = hashlib.sha256(src.read_bytes()).hexdigest()
        sync_module.PROVENANCE.write_text(
            "# Provenance\n\n```\n"
            f"{digest}  {rel}\n"
            "```\n",
            encoding="utf-8",
        )
        return canonical, gen, golden

    def test_check_in_sync(self, sync_module, tmp_path: Path):
        self._setup(sync_module, tmp_path)
        assert sync_module.check() == 0

    def test_check_detects_drift(self, sync_module, tmp_path: Path):
        _, _, golden = self._setup(sync_module, tmp_path)
        golden.write_text(self._OTHER, encoding="utf-8")
        assert sync_module.check() == 1

    def test_push_copies_generator_output(self, sync_module, tmp_path: Path):
        # Without the sister repo: push refreshes the golden only.
        canonical, gen, golden = self._setup(sync_module, tmp_path, with_sister=False)
        assert sync_module.push() == 0
        assert golden.read_bytes() == gen.read_bytes()
        # With the sister repo: push also updates the canonical copy.
        canonical, gen, golden = self._setup(sync_module, tmp_path, with_sister=True)
        gen.write_text(self._OTHER, encoding="utf-8")
        assert sync_module.push() == 0
        assert golden.read_bytes() == self._OTHER.encode()
        assert canonical.read_bytes() == self._OTHER.encode()

    def test_push_copies_endpoint_semantics_verbatim(
        self, sync_module, tmp_path: Path
    ):
        _, gen, golden = self._setup(sync_module, tmp_path, with_sister=False)
        source = TestPortableEndpointContract._node("portable::Source")
        source["edges"] = [{
            "relation_type": "DEPENDS_ON",
            "target_key": TestPortableEndpointContract._key("portable::Target"),
            "target_type": "ClassNode",
            "external": True,
        }]
        import json
        generated = json.dumps([source], indent=2, sort_keys=True) + "\n"
        gen.write_text(generated, encoding="utf-8")

        assert sync_module.push() == 0
        assert gen.read_text(encoding="utf-8") == generated
        assert golden.read_text(encoding="utf-8") == generated

    def test_push_rejects_invalid_endpoint_without_copying(
        self, sync_module, tmp_path: Path
    ):
        _, gen, golden = self._setup(sync_module, tmp_path, with_sister=False)
        before = golden.read_bytes()
        source = TestPortableEndpointContract._node("portable::Source")
        source["edges"] = [{
            "relation_type": "DEPENDS_ON",
            "target_ref": "unresolved-endpoint",
            "target_type": "ClassNode",
        }]
        import json
        gen.write_text(json.dumps([source]), encoding="utf-8")

        assert sync_module.push() == 1
        assert golden.read_bytes() == before
        assert json.loads(gen.read_text(encoding="utf-8"))[0]["edges"][0]["target_ref"] == (
            "unresolved-endpoint"
        )

    def test_pull_copies_sister_canonical(self, sync_module, tmp_path: Path):
        canonical, _, golden = self._setup(sync_module, tmp_path)
        canonical.write_text(self._OTHER, encoding="utf-8")
        assert sync_module.pull() == 0
        assert golden.read_bytes() == canonical.read_bytes()

    # ── Priority-1 provenance (WP5) ──────────────────────────────────────

    def test_check_verifies_source_copy_hashes(self, sync_module, tmp_path: Path):
        """``check`` compares the committed source copies against the
        provenance record and never modifies anything."""
        _, _, _ = self._setup(sync_module, tmp_path)
        assert sync_module.check() == 0
        # the provenance file is untouched by check
        provenance_before = sync_module.PROVENANCE.read_bytes()
        assert sync_module.check() == 0
        assert sync_module.PROVENANCE.read_bytes() == provenance_before

    def test_check_detects_source_copy_drift(self, sync_module, tmp_path: Path):
        _, _, _ = self._setup(sync_module, tmp_path)
        rel = sync_module.MANIFEST.read_text().strip()
        (sync_module.IMPL_SRC / rel).write_text("int changed;\n", encoding="utf-8")
        assert sync_module.check() == 1

    def test_pull_rerecords_provenance_hashes(self, sync_module, tmp_path: Path):
        """Refreshing is explicit (``pull``) and re-records the golden
        hashes so the newly adopted bytes become the verified baseline."""
        _, _, _ = self._setup(sync_module, tmp_path)
        # simulate the sister fixture having different source bytes — the
        # sister fixture root mirrors ``tests/fixtures/cpp-sqlite``, so the
        # production file sits at ``cpp_sqlite/src/...`` under it
        rel = sync_module.MANIFEST.read_text().strip()
        inner = rel[len("tests/fixtures/cpp-sqlite/"):]
        sister_src = tmp_path / "sister_fixture" / inner
        sister_src.parent.mkdir(parents=True, exist_ok=True)
        sister_src.write_text("int refreshed;\n", encoding="utf-8")
        sync_module.SISTER_FIXTURE_SRC = tmp_path / "sister_fixture"
        assert sync_module.pull() == 0
        # the source copy was refreshed and the hash re-recorded
        assert (sync_module.IMPL_SRC / rel).read_text() == "int refreshed;\n"
        assert sync_module.check() == 0

    def test_hash_refresh_preserves_path_only_manifest_block(
        self, sync_module, tmp_path: Path
    ):
        """Hash refresh must not overwrite the human-readable manifest."""
        self._setup(sync_module, tmp_path)
        rel = sync_module.MANIFEST.read_text().strip()
        old_digest = "a" * 64
        new_digest = "b" * 64
        sync_module.PROVENANCE.write_text(
            "## Production manifest\n\n"
            f"```\n{rel}\n```\n\n"
            "## Golden source-copy hashes\n\n"
            f"```\n{old_digest}  {rel}\n```\n",
            encoding="utf-8",
        )

        sync_module._write_provenance_hashes({rel: new_digest})
        text = sync_module.PROVENANCE.read_text(encoding="utf-8")
        assert f"```\n{rel}\n```" in text
        assert f"```\n{new_digest}  {rel}\n```" in text
        assert sync_module._provenance_hashes() == {rel: new_digest}

    def test_pull_prints_every_changed_target(self, sync_module, tmp_path: Path, capsys):
        _, _, _ = self._setup(sync_module, tmp_path)
        rel = sync_module.MANIFEST.read_text().strip()
        inner = rel[len("tests/fixtures/cpp-sqlite/"):]
        sister_src = tmp_path / "sister_fixture" / inner
        sister_src.parent.mkdir(parents=True, exist_ok=True)
        sister_src.write_text("int refreshed;\n", encoding="utf-8")
        sync_module.SISTER_FIXTURE_SRC = tmp_path / "sister_fixture"
        sync_module.pull()
        out = capsys.readouterr().out
        assert f"synced → {sync_module.IMPL_SRC}" in out
        assert "provenance re-recorded" in out
