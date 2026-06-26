#!/usr/bin/env python3
"""Re-ingest LLM-enriched test descriptions from previous enrichment logs.

Reads ``_response.md`` files from ``codegraph/logs/`` (produced by a
prior ``codegraph-enrich --all`` run), parses the description JSON from
each file, and writes the descriptions back to the corresponding Neo4j
nodes in a single batch UPDATE.  This bypasses the LLM call step, making
it fast to recover enrichment data after a re-index.

Usage::

    python scripts/reingest_enrichment.py [--logs-dir codegraph/logs] [--dry-run]
"""

import argparse
import json
import logging
import re
import sys
from pathlib import Path

# Load .env from the project root so Neo4j credentials are available.
_PROJECT_DIR = Path(__file__).resolve().parent.parent
_dotenv_path = _PROJECT_DIR / ".env"
if _dotenv_path.exists():
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=_dotenv_path, override=False)

# ── logging ────────────────────────────────────────────────────────────

log = logging.getLogger("reingest_enrichment")
logging.basicConfig(level=logging.INFO, format="%(message)s")

# ── reasoning-tag stripping ────────────────────────────────────────────

_REASONING_TAG_RE = re.compile(r"<reasoning>.*?</reasoning>", re.DOTALL)
_THINK_TAG_RE = re.compile(r"<think>.*?</think>", re.DOTALL)


def _clean_description(text: str) -> str:
    text = _REASONING_TAG_RE.sub("", text)
    text = _THINK_TAG_RE.sub("", text)
    return text.strip()


# ── main ───────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Re-ingest LLM-enriched descriptions from previous enrichment logs"
    )
    parser.add_argument(
        "--logs-dir", default="codegraph/logs",
        help="Directory containing enrichment _response.md files (default: codegraph/logs)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Parse logs and report what would change without writing to Neo4j",
    )
    args = parser.parse_args()

    logs_dir = Path(args.logs_dir)
    if not logs_dir.is_dir():
        print(f"Error: logs directory not found: {logs_dir}", file=sys.stderr)
        sys.exit(1)

    response_files = sorted(logs_dir.glob("*_response.md"))
    if not response_files:
        print(f"No _response.md files found in {logs_dir}", file=sys.stderr)
        sys.exit(0)

    # ── Phase 1: parse all response files ──────────────────────────────
    print(f"Parsing {len(response_files)} response files...")
    wanted: dict[str, str] = {}      # qualified_name → cleaned description
    parse_errors = 0

    for rf in response_files:
        try:
            with open(rf, encoding="utf-8") as fh:
                data = json.load(fh)
        except json.JSONDecodeError as exc:
            log.warning("  Parse error: %s — %s", rf.name, exc)
            parse_errors += 1
            continue

        if not isinstance(data, dict):
            log.warning("  Unexpected content in %s (not a dict)", rf.name)
            parse_errors += 1
            continue

        for qname, raw_desc in data.items():
            desc = _clean_description(raw_desc)
            if qname and desc:
                wanted[qname] = desc

    print(f"  Parsed {len(wanted)} descriptions ({parse_errors} parse errors)")

    if not wanted:
        print("No descriptions to apply.")
        return

    # ── Phase 2: find matching nodes in Neo4j ──────────────────────────
    import codegraph.persistence.config  # noqa: F401 — sets DATABASE_URL
    from neomodel import db

    qnames = list(wanted.keys())
    print(f"Looking up {len(qnames)} qualified names in Neo4j...")

    # Single batch query to find all nodes + their current descriptions
    query = """
        UNWIND $qnames AS qname
        MATCH (n)
        WHERE n.qualified_name = qname
        RETURN n.qualified_name AS qualified_name, n.description AS description
    """
    results, _ = db.cypher_query(query, {"qnames": qnames})

    existing: dict[str, str] = {row[0]: (row[1] or "") for row in results}

    not_found = len(wanted) - len(existing)
    if not_found:
        print(f"  ⚠  {not_found} qualified names not found in Neo4j")

    # ── Phase 3: determine what actually needs updating ─────────────────
    changed: dict[str, str] = {}
    already_set = 0

    for qname, new_desc in wanted.items():
        old_desc = existing.get(qname)
        if old_desc is None:
            continue  # not found
        if old_desc.strip() == new_desc:
            already_set += 1
        else:
            changed[qname] = new_desc

    print(f"  Already set (no change): {already_set}")
    print(f"  Need update:             {len(changed)}")

    if not changed:
        print("\nNothing to do.")
        _print_summary(len(wanted), already_set, not_found, parse_errors)
        return

    if args.dry_run:
        print("\n(dry-run — would update the following)")
        for qname, desc in sorted(changed.items())[:10]:
            print(f"  {qname}")
        if len(changed) > 10:
            print(f"  ... and {len(changed) - 10} more")
        _print_summary(len(wanted), already_set, not_found, parse_errors,
                       changed=len(changed))
        return

    # ── Phase 4: batch update ──────────────────────────────────────────
    print(f"\nApplying {len(changed)} description updates...")
    update_query = """
        UNWIND $updates AS entry
        MATCH (n {qualified_name: entry.qname})
        SET n.description = entry.description
        RETURN count(n) AS updated
    """
    updates = [{"qname": q, "description": d} for q, d in changed.items()]
    result, _ = db.cypher_query(update_query, {"updates": updates})
    updated_count = result[0][0] if result else 0
    print(f"  Updated: {updated_count} nodes")

    # ── Summary ────────────────────────────────────────────────────────
    _print_summary(len(wanted), already_set, not_found, parse_errors,
                   changed=updated_count)


def _print_summary(total: int, already_set: int, not_found: int,
                   parse_errors: int, changed: int = 0) -> None:
    print()
    print("─" * 50)
    print("Summary:")
    items = [
        ("Parsed from logs", total),
        ("Updated", changed),
        ("Already set (no change)", already_set),
        ("Not found in Neo4j", not_found),
        ("Parse errors (files)", parse_errors),
    ]
    for label, value in items:
        if value:
            print(f"  {label:30s}: {value}")
    print("─" * 50)


if __name__ == "__main__":
    main()
