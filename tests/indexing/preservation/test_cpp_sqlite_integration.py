"""Configuration-resolution tests retained from the legacy integration suite.

The cpp_sqlite_minimal fixture-based tests were removed: that fixture was
untracked in DDP and is explicitly outside the parity fixture closure.
"""

from pathlib import Path


class TestConfigResolution:
    """Verify that ``_find_project_source_dirs`` respects project config."""

    def test_config_input_paths_take_precedence(self, tmp_path: Path):
        from codegraph_index.cli import _find_project_source_dirs

        (tmp_path / "my_src").mkdir()
        (tmp_path / "my_src" / "header.h").write_text("// ok")
        (tmp_path / "include").mkdir()
        (tmp_path / "include" / "header.h").write_text("// also ok")
        (tmp_path / ".doxygen-index.toml").write_text(
            '[project]\nname = "test"\ninput_paths = ["my_src"]\n'
        )

        dirs = _find_project_source_dirs(tmp_path)
        resolved = [directory.relative_to(tmp_path) for directory in dirs]
        assert Path("my_src") in resolved
        assert Path("include") not in resolved

    def test_fallback_when_no_config(self, tmp_path: Path):
        from codegraph_index.cli import _find_project_source_dirs

        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "main.cpp").write_text("// test")

        dirs = _find_project_source_dirs(tmp_path)
        assert Path("src") in [directory.relative_to(tmp_path) for directory in dirs]

    def test_fallback_when_no_dirs_found(self, tmp_path: Path):
        from codegraph_index.cli import _find_project_source_dirs

        assert _find_project_source_dirs(tmp_path) == [tmp_path]

    def test_config_nonexistent_path_ignored(self, tmp_path: Path):
        from codegraph_index.cli import _find_project_source_dirs

        (tmp_path / "exists").mkdir()
        (tmp_path / "exists" / "header.h").write_text("// ok")
        (tmp_path / ".doxygen-index.toml").write_text(
            '[project]\nname = "test"\ninput_paths = ["exists", "nope"]\n'
        )

        dirs = _find_project_source_dirs(tmp_path)
        resolved = [directory.relative_to(tmp_path) for directory in dirs]
        assert resolved == [Path("exists")]
