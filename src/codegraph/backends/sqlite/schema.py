"""SQLite schema — SQLAlchemy Core table metadata + DDL helpers.

The storage model mirrors Neo4j's internal node-store + relationship-store:

- One ``nodes`` table holds every node type (ClassNode, HLR, DecisionNode,
  Component, ...) as a JSON ``properties`` blob plus a few STORED generated
  columns that expose the hot filter keys (``source`` / ``qualified_name`` /
  ``kind``) as indexable columns derived automatically from the JSON —
  single source of truth, zero hand-synced denormalization.
- One ``edges`` table holds every relationship.  The UNIQUE triple
  ``(source_id, rel_type, target_id)`` gives idempotent MERGE semantics via
  ``INSERT OR IGNORE``; composite indexes cover both traversal directions
  and type-wide queries.
- ``node_labels`` / ``node_tags`` join tables give exact, indexed
  membership for label/tag-filtered queries (no JSON LIKE-scans).
- ``fts_nodes`` is an FTS5 shadow table for full-text search.
- ``node_embeddings`` stores canonical float32 BLOBs (the numpy search
  matrix is a derived in-process cache, not stored here).

Schema versioning uses ``PRAGMA user_version``. ``create_all()`` initializes a
fresh canonical schema; legacy UID schemas are rejected without mutation and
must be rebuilt by re-indexing authoritative sources.
"""

from __future__ import annotations

import logging

import sqlalchemy as sa

log = logging.getLogger(__name__)

SCHEMA_VERSION = 3

# ── Table metadata (SQLAlchemy Core) ─────────────────────────────────────

metadata = sa.MetaData()

nodes = sa.Table(
    "nodes",
    metadata,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    # Canonical key — the sole storage identity (WP C).  A real column
    # (not a generated view) so it is the upsert target; the properties
    # JSON also carries it for round-trips.
    sa.Column("canonical_key", sa.Text, nullable=False, unique=True),
    # JSON array of the inherited label chain, e.g. ["ClassNode","CompoundNode"].
    sa.Column("labels", sa.Text, nullable=False),
    # JSON object of every declared Property value.
    sa.Column("properties", sa.Text, nullable=False),
    # STORED generated columns — derived from properties JSON, indexable,
    # and free of sync drift.  `persisted=True` emits GENERATED ... STORED.
    sa.Column(
        "source",
        sa.Text,
        sa.Computed("json_extract(properties, '$.source')", persisted=True),
    ),
    sa.Column(
        "qualified_name",
        sa.Text,
        sa.Computed("json_extract(properties, '$.qualified_name')", persisted=True),
    ),
    sa.Column(
        "kind",
        sa.Text,
        sa.Computed("json_extract(properties, '$.kind')", persisted=True),
    ),
)

sa.Index("idx_nodes_source", nodes.c.source)
sa.Index("idx_nodes_qname", nodes.c.qualified_name)
sa.Index("idx_nodes_kind", nodes.c.kind)
node_labels = sa.Table(
    "node_labels",
    metadata,
    sa.Column("node_id", sa.Integer, sa.ForeignKey("nodes.id", ondelete="CASCADE"), nullable=False),
    sa.Column("label", sa.Text, nullable=False),
    sa.PrimaryKeyConstraint("node_id", "label"),
)
sa.Index("idx_node_labels_label", node_labels.c.label)

node_tags = sa.Table(
    "node_tags",
    metadata,
    sa.Column("node_id", sa.Integer, sa.ForeignKey("nodes.id", ondelete="CASCADE"), nullable=False),
    sa.Column("tag", sa.Text, nullable=False),
    sa.PrimaryKeyConstraint("node_id", "tag"),
)
sa.Index("idx_node_tags_tag", node_tags.c.tag)

edges = sa.Table(
    "edges",
    metadata,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("source_id", sa.Integer, sa.ForeignKey("nodes.id", ondelete="CASCADE"), nullable=False),
    sa.Column("rel_type", sa.Text, nullable=False),
    sa.Column("target_id", sa.Integer, sa.ForeignKey("nodes.id", ondelete="CASCADE"), nullable=False),
    sa.Column("properties", sa.Text, nullable=False, server_default="{}"),
    # Idempotent MERGE semantics: INSERT OR IGNORE on this triple.
    sa.UniqueConstraint("source_id", "rel_type", "target_id"),
)
sa.Index("idx_edges_source", edges.c.source_id, edges.c.rel_type)
sa.Index("idx_edges_target", edges.c.target_id, edges.c.rel_type)
sa.Index("idx_edges_reltype", edges.c.rel_type)

node_embeddings = sa.Table(
    "node_embeddings",
    metadata,
    sa.Column("node_id", sa.Integer, sa.ForeignKey("nodes.id", ondelete="CASCADE"), primary_key=True),
    sa.Column("dim", sa.Integer, nullable=False),
    sa.Column("embedding", sa.LargeBinary, nullable=False),
    sa.Column("updated_at", sa.Float, nullable=False, server_default=sa.text("(unixepoch())")),
)

# ── FTS5 virtual table (not part of `metadata` — SQLAlchemy has no FTS5) ──

_FTS5_DDL = (
    "CREATE VIRTUAL TABLE IF NOT EXISTS fts_nodes USING fts5("
    "canonical_key, content, qualified_name, tags"
    ")"
)


# ── DDL helpers ──────────────────────────────────────────────────────────


def _set_user_version(conn) -> None:
    conn.execute(sa.text(f"PRAGMA user_version = {SCHEMA_VERSION}"))


def create_all(conn) -> None:
    """Create the schema on *conn* (an SQLAlchemy Connection).

    Sets ``page_size`` first (immutable after the first write), then
    creates tables + indexes, the FTS5 virtual table, and stamps
    ``PRAGMA user_version``.
    """
    # page_size can only be set before any table is created; on an
    # existing file it is a silent no-op.  Modern SQLite defaults to
    # 4096 anyway — this guards against older builds / explicit dbs.
    conn.execute(sa.text("PRAGMA page_size = 4096"))
    metadata.create_all(conn)
    conn.execute(sa.text(_FTS5_DDL))
    _set_user_version(conn)
    conn.commit()


def _migrate(conn) -> None:
    """Reject stale schemas (WP F — old databases are rejected, not
    converted).

    v1/v2 databases carry the legacy ``uid`` node column.  Under the
    canonical-only cutover the ``nodes`` table is keyed by
    ``canonical_key``; opening an old database without mutating it is
    impossible with the new schema, so a targeted error explains the
    cutover instead of silently converting.
    """
    row = conn.execute(sa.text("PRAGMA user_version")).scalar_one()
    version = int(row)
    if version >= SCHEMA_VERSION:
        return
    if version == 0:
        # Brand-new database — create the canonical schema.
        create_all(conn)
        return
    raise RuntimeError(
        f"SQLite database uses the legacy schema (user_version={version}); "
        f"the canonical-only cutover (WP F) requires a fresh store — "
        f"reindex sources into a new database instead of converting"
    )


def ensure_schema(engine: sa.Engine) -> None:
    """Create or migrate the schema on a fresh connection.

    Call once at backend initialization.  Uses ``engine.connect()`` so
    the pragmas installed by the connect event apply.
    """
    with engine.connect() as conn:
        exists = _table_exists(conn, "nodes")
        if exists:
            _migrate(conn)
        else:
            create_all(conn)


def _table_exists(conn, name: str) -> bool:
    row = conn.execute(
        sa.text(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=:name"
        ),
        {"name": name},
    ).first()
    return row is not None
