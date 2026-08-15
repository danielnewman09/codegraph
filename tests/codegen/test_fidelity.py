from pathlib import Path

import pytest

from codegraph.codegen.fidelity import compare_manifest


def _write(root: Path, relative: str, content: bytes) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def test_compare_manifest_reports_each_failure_kind(tmp_path: Path):
    expected = tmp_path / "expected"
    actual = tmp_path / "actual"
    _write(expected, "same.hpp", b"same\n")
    _write(actual, "same.hpp", b"same\n")
    _write(expected, "changed.cpp", b"before\n")
    _write(actual, "changed.cpp", b"after\n")
    _write(expected, "missing.hpp", b"source\n")

    report = compare_manifest(
        expected, actual, ["missing.hpp", "same.hpp", "changed.cpp"]
    )

    assert report.matched == ("same.hpp",)
    assert report.missing == ("missing.hpp",)
    assert [item.path for item in report.drift] == ["changed.cpp"]
    assert report.drift[0].first_different_line == 1
    assert not report.is_identical
    assert "matched=1, missing=1, drift=1" in report.describe()


def test_compare_manifest_supports_canonicalization(tmp_path: Path):
    expected = tmp_path / "expected"
    actual = tmp_path / "actual"
    _write(expected, "value.hpp", b"int  value;\n")
    _write(actual, "value.hpp", b"int value;\n")

    def collapse_spaces(_path: Path, content: bytes) -> bytes:
        return content.replace(b"  ", b" ")

    report = compare_manifest(
        expected, actual, ["value.hpp"], normalize=collapse_spaces
    )
    assert report.is_identical


def test_compare_manifest_rejects_stale_manifest(tmp_path: Path):
    with pytest.raises(FileNotFoundError, match="manifest source is missing"):
        compare_manifest(tmp_path / "expected", tmp_path / "actual", ["gone.hpp"])
