"""codegraph-codegen CLI tests (dry-run planning, tree writing)."""

from __future__ import annotations

from pathlib import Path

import pytest

from codegraph.codegen.cli import main

GOLDEN = Path(__file__).resolve().parent / "golden" / "design_layergraph_full_decl.json"


class TestCli:
    def test_dry_run_prints_plan(self, capsys):
        rc = main([
            "--input", str(GOLDEN),
            "--dry-run",
        ])
        captured = capsys.readouterr()
        assert rc == 0
        assert "include/cpp_sqlite/Migration.hpp" in captured.out
        assert "7 file(s)" in captured.out
        assert "orphaned members skipped" in captured.err

    def test_output_writes_tree(self, tmp_path: Path, capsys):
        rc = main([
            "--input", str(GOLDEN),
            "--output", str(tmp_path),
        ])
        assert rc == 0
        assert (tmp_path / "include/cpp_sqlite/Migration.hpp").is_file()
        capsys.readouterr()  # swallow output

    def test_missing_input_raises(self):
        with pytest.raises(FileNotFoundError):
            main(["--input", str(GOLDEN) + ".missing", "--dry-run"])

    def test_unknown_pack_raises(self):
        with pytest.raises(FileNotFoundError):
            main(["--input", str(GOLDEN), "--dry-run", "--pack", "/nonexistent"])

    def test_markers_opt_in(self, tmp_path: Path, capsys):
        """Provenance markers are opt-in (``--markers``); the default
        output carries none (byte-fidelity with hand-written source)."""
        main(["--input", str(GOLDEN), "--output", str(tmp_path), "--markers"])
        capsys.readouterr()
        assert "// @codegraph uid:" in (
            tmp_path / "include/cpp_sqlite/Migration.hpp"
        ).read_text()
