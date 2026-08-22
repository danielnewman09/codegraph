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
from pathlib import Path

import pytest

from codegraph.graph import LayerGraph


def _deser(data):
    return LayerGraph.deserialize(data)


GOLDEN_DIR = Path(__file__).resolve().parent / "golden"
GOLDEN_SPLIT = GOLDEN_DIR / "design_layergraph.json"
GOLDEN_FULL_DECL = GOLDEN_DIR / "design_layergraph_full_decl.json"
PIPELINE_COPY = (
    Path(__file__).resolve().parent.parent / "pipelines" / "unit_test_data"
    / "design_layergraph.json"
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


class TestSyncScript:
    """Sandboxed — never touches the real sibling repo."""

    _CONTENT = '{"fixture": 1}\n'
    _OTHER = '{"fixture": 2}\n'

    def _setup(self, sync_module, tmp_path: Path, *, with_sister: bool = True):
        canonical = tmp_path / "sister.json"
        gen = tmp_path / "gen.json"
        golden = tmp_path / "golden.json"
        one_hop = tmp_path / "one_hop.json"
        sister_one_hop = tmp_path / "sister_one_hop.json"
        impl = tmp_path / "impl.json"
        sister_impl = tmp_path / "sister_impl.json"
        for p in (canonical, gen, golden, one_hop, sister_one_hop, impl, sister_impl):
            p.write_text(self._CONTENT, encoding="utf-8")
        sync_module.PIPELINE_COPY = gen
        sync_module.GOLDEN = golden
        sync_module.SISTER_CANONICAL = canonical
        sync_module.SISTER = tmp_path if with_sister else tmp_path / "no-sister"
        sync_module.ONE_HOP = one_hop
        sync_module.SISTER_ONE_HOP = sister_one_hop
        sync_module.IMPL = impl
        sync_module.SISTER_IMPL = sister_impl
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
