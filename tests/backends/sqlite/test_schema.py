"""SQLite schema cutover policy tests."""

from __future__ import annotations

import sqlalchemy as sa
import pytest

from codegraph.backends.sqlite.schema import ensure_schema


def test_legacy_schema_is_rejected_without_mutation(tmp_path) -> None:
    """Legacy UID stores require a fresh re-index; they are never rewritten."""
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'legacy.sqlite3'}")
    with engine.begin() as conn:
        conn.execute(
            sa.text(
                "CREATE TABLE nodes ("
                "id INTEGER PRIMARY KEY, uid TEXT NOT NULL UNIQUE)"
            )
        )
        conn.execute(sa.text("INSERT INTO nodes (uid) VALUES ('legacy-sha1')"))
        conn.execute(sa.text("PRAGMA user_version = 2"))

    with pytest.raises(RuntimeError, match="requires a fresh store"):
        ensure_schema(engine)

    with engine.connect() as conn:
        columns = {
            row[1] for row in conn.execute(sa.text("PRAGMA table_info(nodes)"))
        }
        legacy_uid = conn.execute(sa.text("SELECT uid FROM nodes")).scalar_one()
        version = conn.execute(sa.text("PRAGMA user_version")).scalar_one()

    assert columns == {"id", "uid"}
    assert legacy_uid == "legacy-sha1"
    assert version == 2
