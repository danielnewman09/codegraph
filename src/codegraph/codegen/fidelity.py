"""Source-tree fidelity primitives used by round-trip acceptance tests.

This module deliberately knows nothing about C++ parsing or rendering.  It
compares an explicit file manifest and reports transport failures separately
from content drift so a round-trip failure identifies the layer that lost
information.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable


ByteNormalizer = Callable[[Path, bytes], bytes]


@dataclass(frozen=True)
class FileDrift:
    """A manifest file whose expected and generated content differ."""

    path: str
    expected_bytes: int
    actual_bytes: int
    first_different_line: int | None


@dataclass(frozen=True)
class FidelityReport:
    """Structured result of comparing two trees over a declared manifest."""

    matched: tuple[str, ...]
    missing: tuple[str, ...]
    drift: tuple[FileDrift, ...]

    @property
    def is_identical(self) -> bool:
        return not self.missing and not self.drift

    def summarize(self) -> str:
        return (
            f"matched={len(self.matched)}, missing={len(self.missing)}, "
            f"drift={len(self.drift)}"
        )

    def describe(self) -> str:
        lines = [self.summarize()]
        lines.extend(f"missing: {path}" for path in self.missing)
        lines.extend(
            f"drift: {item.path} "
            f"(expected {item.expected_bytes} bytes, got {item.actual_bytes}; "
            f"first difference at line {item.first_different_line})"
            for item in self.drift
        )
        return "\n".join(lines)


def compare_manifest(
    expected_root: Path,
    actual_root: Path,
    manifest: Iterable[str],
    *,
    normalize: ByteNormalizer | None = None,
) -> FidelityReport:
    """Compare ``manifest`` paths under two roots.

    ``normalize`` may canonicalize language formatting before comparison.
    Missing generated files remain transport failures and are never passed to
    the normalizer.
    """

    matched: list[str] = []
    missing: list[str] = []
    drift: list[FileDrift] = []
    for relative in sorted(set(manifest)):
        expected_path = expected_root / relative
        actual_path = actual_root / relative
        if not expected_path.is_file():
            raise FileNotFoundError(f"manifest source is missing: {expected_path}")
        if not actual_path.is_file():
            missing.append(relative)
            continue
        expected = expected_path.read_bytes()
        actual = actual_path.read_bytes()
        if normalize is not None:
            expected = normalize(expected_path, expected)
            actual = normalize(actual_path, actual)
        if expected == actual:
            matched.append(relative)
        else:
            expected_lines = expected.splitlines(keepends=True)
            actual_lines = actual.splitlines(keepends=True)
            common = min(len(expected_lines), len(actual_lines))
            first_line = next(
                (
                    index + 1
                    for index in range(common)
                    if expected_lines[index] != actual_lines[index]
                ),
                common + 1,
            )
            drift.append(FileDrift(relative, len(expected), len(actual), first_line))
    return FidelityReport(tuple(matched), tuple(missing), tuple(drift))
