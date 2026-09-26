#!/usr/bin/env python3
"""Capture build/test execution evidence for the Priority 5 Transaction slice.

WP5.4 of ``docs/plans/2026-09-16-priority-5-transaction-golden-slice.md``.
This is the *only supported author* of

    tests/indexing/preservation/fixtures/cpp-sqlite/transaction_slice/evidence.toml

and the retained logs beside it.  Ordinary test runs validate the committed
records; they never rebuild or rewrite them (plan step 6).

What it does, exactly once per invocation:

1. Builds the ``cpp-sqlite`` worktree with its declared Conan workflow
   (``conan build . --build=missing -s build_type=Release
   -o "&:build_testing=True"``) and retains the combined output.
2. Runs the resulting GoogleTest binary with a filter containing *exactly*
   the five frozen slice tests, from a throwaway working directory so the
   worktree is not polluted by test databases.
3. Writes ``evidence.toml`` + logs.  On any failure (build error, non-zero
   exit, unexpected test counts) the previously reviewed evidence is left
   untouched.

The reviewed evidence lives in the *codegraph* repository; the build runs in
the sibling ``cpp-sqlite`` worktree, whose ``cpp_sqlite/`` source tree is
digest-compared against the frozen fixture before anything executes — a
mismatch means the binary under test would not be the binary the slice
describes, and the capture refuses to proceed.

Usage:

    .venv/bin/python scripts/capture_transaction_slice_evidence.py \
        [--cpp-sqlite ~/dev/cpp-sqlite] [--force]
"""

from __future__ import annotations

import argparse
import hashlib
import platform
import re
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

CODEGRAPH_ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_DIR = (
    CODEGRAPH_ROOT
    / "tests/indexing/preservation/fixtures/cpp-sqlite/transaction_slice"
)
EVIDENCE_TOML = EVIDENCE_DIR / "evidence.toml"
BUILD_LOG = EVIDENCE_DIR / "logs/build-release.log"
TEST_LOG = EVIDENCE_DIR / "logs/test-transaction-filter.log"

#: The five frozen slice tests, in plan order (WP5.0 characterization).
FROZEN_TESTS: tuple[str, ...] = (
    "TransactionCommit",
    "TransactionRollback",
    "TransactionAutoRollbackOnDestruction",
    "NestedTransactionWithSavepoints",
    "NestedTransactionRollbackInner",
)

#: The fixture copy the built sources must agree with, byte for byte.
FIXTURE_SOURCE_DIR = (
    CODEGRAPH_ROOT
    / "tests/indexing/preservation/fixtures/cpp-sqlite/cpp_sqlite"
)

#: Golden gitlink recorded by FIXTURE_PROVENANCE.md (migration evidence only).
GOLDEN_REVISION = "4a1450a5e6a5b8edf7f3572b4eaa6085df37e571"

BUILD_COMMAND = [
    "conan", "build", ".",
    "--build=missing",
    "-s", "build_type=Release",
    "-o&:build_testing=True",
]

#: Edges are frozen by the plan vocabulary; the capture records them, it does
#: not invent them.
BUILD_EVIDENCES_CLASS = "cpp_sqlite::Transaction"
TEST_EVIDENCES_TESTS = tuple(
    f"testDatabase::DatabaseTest::{name}" for name in FROZEN_TESTS
)


class CaptureError(RuntimeError):
    """The capture could not produce honest evidence."""


def run(command: list[str], cwd: Path) -> tuple[int, float, str, str]:
    """Run *command*, returning (exit_code, duration, combined, start_iso)."""
    start = datetime.now(UTC)
    t0 = time.monotonic()
    proc = subprocess.run(
        command,
        cwd=cwd,
        capture_output=True,
        text=True,
        errors="replace",
        shell=False,
        check=False,  # the exit code is the evidence — never raise on it
    )
    combined = proc.stdout + (
        ("\n" + proc.stderr) if proc.stderr.strip() else ""
    )
    return proc.returncode, time.monotonic() - t0, combined, start.isoformat()


def source_tree_digest(root: Path) -> str:
    """Stable sha256 over the relative paths and contents of source files."""
    files = sorted(
        p for p in root.rglob("*")
        if p.is_file() and p.suffix in {".hpp", ".cpp"}
    )
    h = hashlib.sha256()
    for path in files:
        h.update(str(path.relative_to(root)).encode())
        h.update(path.read_bytes())
    return h.hexdigest()


def git_revision(repo: Path) -> str:
    proc = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True,
        text=True, check=False,
    )
    if proc.returncode != 0:
        raise CaptureError(f"git rev-parse failed in {repo}")
    return proc.stdout.strip()


def tool_version(command: list[str]) -> str:
    try:
        proc = subprocess.run(
            command, capture_output=True, text=True, timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "unavailable"
    first = (proc.stdout or proc.stderr).strip().splitlines()
    return first[0] if first else "unavailable"


def environment_summary() -> list[str]:
    uname = platform.uname()
    return [
        f"platform={uname.system}-{uname.release}",
        f"machine={uname.machine}",
        f"processor={uname.processor or 'unknown'}",
        f"compiler={tool_version(['clang++', '--version'])}",
        f"cmake={tool_version(['cmake', '--version']).splitlines()[0]}",
        f"conan={tool_version(['conan', '--version']).splitlines()[0]}",
        "build_type=Release",
    ]


def parse_test_summary(combined: str) -> tuple[int, int]:
    """Extract (ran, passed) counts from GoogleTest output.

    Raises CaptureError when the summary lines are absent — an unparseable
    run is an error, never a silent zero.  All bracket markers are escaped
    literals: an unescaped ``[ FAILED ]`` is a character class that matches
    the substring ``ated T`` inside ``NestedTransactionated...`` — i.e. the
    gtest *filter line itself*.
    """
    ran = re.search(
        r"\[=+\] (\d+) tests? from \d+ test suites? ran\.", combined
    )
    passed = re.search(r"\[\s+PASSED\s+\] (\d+) tests?\.", combined)
    failed = re.search(r"\[\s+FAILED\s+\] (\d+) tests?", combined)
    if failed:
        return (int(ran.group(1)) if ran else 0), 0
    if not ran or not passed:
        head = "\n".join(combined.splitlines()[:20])
        raise CaptureError(
            "GoogleTest summary lines missing from output:\n"
            f"{head}\n...[{len(combined)} chars total]"
        )
    return int(ran.group(1)), int(passed.group(1))


def check_each_frozen_test_ran_and_passed(combined: str) -> None:
    for name in FROZEN_TESTS:
        ok = re.search(
            rf"\[\s+OK\s+\] DatabaseTest\.{name} \(\d+ ms\)", combined
        ) or re.search(rf"\[\s+PASSED\s+\] DatabaseTest\.{name}\.", combined)
        if not ok:
            raise CaptureError(
                f"frozen test {name!r} did not report OK in the filtered run"
            )


def write_log(path: Path, combined: str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = combined.encode("utf-8")
    path.write_bytes(data)
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def toml_quote(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def render_entry(
    *,
    qualified_name: str,
    evidence_type: str,
    status: str,
    command: str,
    exit_code: int,
    executed_at: str,
    duration: float,
    environment: list[str],
    revision: str,
    output_digest: str,
    log_path: str,
    extra_lines: list[str],
) -> str:
    env = ", ".join(toml_quote(item) for item in environment)
    lines = [
        "[[evidence]]",
        f"qualified_name = {toml_quote(qualified_name)}",
        f"evidence_type = {toml_quote(evidence_type)}",
        f"status = {toml_quote(status)}",
        f"command = {toml_quote(command)}",
        f"exit_code = {exit_code}",
        f"executed_at = {toml_quote(executed_at)}",
        f"duration_seconds = {duration:.3f}",
        f"environment = [{env}]",
        f"revision = {toml_quote(revision)}",
        f"output_digest = {toml_quote(output_digest)}",
        f"log_path = {toml_quote(log_path)}",
        'tags = ["evidence", "as-built"]',
        'source = "cpp-sqlite"',
    ]
    lines.extend(extra_lines)
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--cpp-sqlite",
        type=Path,
        default=Path.home() / "dev/cpp-sqlite",
        help="cpp-sqlite worktree to build (default: ~/dev/cpp-sqlite)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="overwrite reviewed evidence even if its revision/digest match",
    )
    args = parser.parse_args()
    repo = args.cpp_sqlite.expanduser().resolve()
    if not (repo / "conanfile.py").is_file():
        raise CaptureError(f"{repo} is not the cpp-sqlite worktree")

    if EVIDENCE_TOML.exists() and not args.force:
        prior = EVIDENCE_TOML.read_text(encoding="utf-8")
        tree_digest = source_tree_digest(repo / "cpp_sqlite")
        if f"sha256:{tree_digest}" in prior:
            raise CaptureError(
                "reviewed evidence already records this source digest; "
                "pass --force to recapture deliberately"
            )

    # Integrity gate: the binary we are about to certify must be built from
    # sources identical to the frozen fixture the slice describes.
    upstream_digest = source_tree_digest(repo / "cpp_sqlite")
    fixture_digest = source_tree_digest(FIXTURE_SOURCE_DIR)
    if upstream_digest != fixture_digest:
        raise CaptureError(
            "cpp_sqlite/ sources differ from the frozen fixture "
            f"(upstream {upstream_digest[:12]}… != fixture "
            f"{fixture_digest[:12]}…); refresh the fixture through its "
            "declared sync path first"
        )
    revision = (
        f"git:{git_revision(repo)};"
        f"tree-sha256:{upstream_digest};"
        f"golden:{GOLDEN_REVISION}"
    )

    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Build
    build_code, build_dur, build_out, build_at = run(BUILD_COMMAND, repo)
    build_digest = write_log(BUILD_LOG, build_out)
    build_status = "passed" if build_code == 0 else "failed"
    if build_code != 0:
        # Log retained for diagnosis, but prior reviewed evidence untouched.
        print(build_out[-4000:], file=sys.stderr)
        raise CaptureError(
            f"build failed with exit code {build_code}; "
            "prior reviewed evidence left in place"
        )

    # 2. Filtered test run from a throwaway cwd (tests write *.db locally).
    binary = repo / "build/Release/cpp_sqlite/test/cpp_sqlite_test"
    if not binary.is_file():
        raise CaptureError(f"test binary missing: {binary}")
    filter_spec = ":".join(f"DatabaseTest.{name}" for name in FROZEN_TESTS)
    import tempfile

    with tempfile.TemporaryDirectory(prefix="cgslice-evidence-") as tmp:
        test_code, test_dur, test_out, test_at = run(
            [str(binary), f"--gtest_filter={filter_spec}"], Path(tmp)
        )
    test_digest = write_log(TEST_LOG, test_out)
    ran, passed = parse_test_summary(test_out)
    if ran != len(FROZEN_TESTS) or passed != len(FROZEN_TESTS):
        raise CaptureError(
            f"filtered run must cover exactly {len(FROZEN_TESTS)} tests and "
            f"pass them all (ran={ran}, passed={passed}); "
            "prior reviewed evidence left in place"
        )
    check_each_frozen_test_ran_and_passed(test_out)
    if test_code != 0:
        raise CaptureError(
            f"test run exited {test_code}; prior reviewed evidence untouched"
        )

    # 3. Author the reviewed evidence.
    environment = environment_summary()
    build_entry = render_entry(
        qualified_name="evidence::cpp-sqlite::release-build",
        evidence_type="build",
        status=build_status,
        command=" ".join(BUILD_COMMAND),
        exit_code=build_code,
        executed_at=build_at,
        duration=build_dur,
        environment=environment,
        revision=revision,
        output_digest=build_digest,
        log_path=str(BUILD_LOG.relative_to(CODEGRAPH_ROOT)),
        extra_lines=[
            "",
            "# EVIDENCES -> ClassNode",
            f'evidences = [{toml_quote(BUILD_EVIDENCES_CLASS)}]',
        ],
    )
    test_entry = render_entry(
        qualified_name="evidence::cpp-sqlite::transaction-test-run",
        evidence_type="test",
        status="passed",
        command=f"cpp_sqlite_test --gtest_filter={filter_spec}",
        exit_code=test_code,
        executed_at=test_at,
        duration=test_dur,
        environment=environment,
        revision=revision,
        output_digest=test_digest,
        log_path=str(TEST_LOG.relative_to(CODEGRAPH_ROOT)),
        extra_lines=[
            "",
            "# EVIDENCES -> TestNode (the five frozen tests); DEPENDS_ON -> build",
            "evidences = ["
            + ", ".join(toml_quote(q) for q in TEST_EVIDENCES_TESTS)
            + "]",
            'depends_on = "evidence::cpp-sqlite::release-build"',
        ],
    )
    header = (
        "# Execution evidence for the Priority 5 Transaction golden slice.\n"
        "# Generated by scripts/capture_transaction_slice_evidence.py — do "
        "not hand-edit.\n"
        "# Tests validate these records against the retained logs; they are "
        "never\n# rewritten by ordinary test runs.\n\n"
    )
    text = header + build_entry + "\n" + test_entry
    EVIDENCE_TOML.write_text(text, encoding="utf-8")
    print(f"wrote {EVIDENCE_TOML.relative_to(CODEGRAPH_ROOT)}")
    print(f"  build: exit={build_code} duration={build_dur:.2f}s "
          f"digest={build_digest[:19]}…")
    print(f"  test:  ran={ran} passed={passed} duration={test_dur:.2f}s "
          f"digest={test_digest[:19]}…")
    return 0


if __name__ == "__main__":
    sys.exit(main())
