"""Schema DDL — constraints and indexes for memory nodes.

Provides the DDL statements for Neo4j constraints, indexes, full-text
search, and vector search on memory node types.  Call ``apply_schema()``
to create all constraints and indexes.
"""

from __future__ import annotations

from codegraph.backends import get_backend

MEMORY_CONSTRAINTS_AND_INDEXES: list[str] = [
    # ── Uniqueness constraints ─────────────────────────────────────
    "CREATE CONSTRAINT memory_decision_uid IF NOT EXISTS "
    "FOR (m:DecisionNode) REQUIRE m.canonical_key IS UNIQUE",
    "CREATE CONSTRAINT memory_constraint_uid IF NOT EXISTS "
    "FOR (m:ConstraintNode) REQUIRE m.canonical_key IS UNIQUE",
    "CREATE CONSTRAINT memory_rationale_uid IF NOT EXISTS "
    "FOR (m:RationaleNode) REQUIRE m.canonical_key IS UNIQUE",
    "CREATE CONSTRAINT memory_assumption_uid IF NOT EXISTS "
    "FOR (m:AssumptionNode) REQUIRE m.canonical_key IS UNIQUE",
    "CREATE CONSTRAINT memory_tradeoff_uid IF NOT EXISTS "
    "FOR (m:TradeoffNode) REQUIRE m.canonical_key IS UNIQUE",
    "CREATE CONSTRAINT memory_insight_uid IF NOT EXISTS "
    "FOR (m:InsightNode) REQUIRE m.canonical_key IS UNIQUE",

    # ── Tag indexes (array membership, matching codegraph pattern) ─
    "CREATE INDEX decision_tags IF NOT EXISTS "
    "FOR (d:DecisionNode) ON (d.tags)",
    "CREATE INDEX constraint_tags IF NOT EXISTS "
    "FOR (c:ConstraintNode) ON (c.tags)",
    "CREATE INDEX rationale_tags IF NOT EXISTS "
    "FOR (r:RationaleNode) ON (r.tags)",
    "CREATE INDEX assumption_tags IF NOT EXISTS "
    "FOR (a:AssumptionNode) ON (a.tags)",
    "CREATE INDEX tradeoff_tags IF NOT EXISTS "
    "FOR (t:TradeoffNode) ON (t.tags)",
    "CREATE INDEX insight_tags IF NOT EXISTS "
    "FOR (i:InsightNode) ON (i.tags)",

    # ── Source provenance ─────────────────────────────────────────
    "CREATE INDEX decision_source IF NOT EXISTS "
    "FOR (d:DecisionNode) ON (d.source)",
    "CREATE INDEX constraint_source IF NOT EXISTS "
    "FOR (c:ConstraintNode) ON (c.source)",
    "CREATE INDEX rationale_source IF NOT EXISTS "
    "FOR (r:RationaleNode) ON (r.source)",
    "CREATE INDEX assumption_source IF NOT EXISTS "
    "FOR (a:AssumptionNode) ON (a.source)",
    "CREATE INDEX tradeoff_source IF NOT EXISTS "
    "FOR (t:TradeoffNode) ON (t.source)",
    "CREATE INDEX insight_source IF NOT EXISTS "
    "FOR (i:InsightNode) ON (i.source)",

    # ── Qualified name indexes ────────────────────────────────────
    "CREATE INDEX decision_qualified IF NOT EXISTS "
    "FOR (d:DecisionNode) ON (d.qualified_name)",
    "CREATE INDEX constraint_qualified IF NOT EXISTS "
    "FOR (c:ConstraintNode) ON (c.qualified_name)",
    "CREATE INDEX rationale_qualified IF NOT EXISTS "
    "FOR (r:RationaleNode) ON (r.qualified_name)",
    "CREATE INDEX assumption_qualified IF NOT EXISTS "
    "FOR (a:AssumptionNode) ON (a.qualified_name)",
    "CREATE INDEX tradeoff_qualified IF NOT EXISTS "
    "FOR (t:TradeoffNode) ON (t.qualified_name)",
    "CREATE INDEX insight_qualified IF NOT EXISTS "
    "FOR (i:InsightNode) ON (i.qualified_name)",

    # ── Confidence index (for prioritizing memories) ───────────────
    "CREATE INDEX decision_confidence IF NOT EXISTS "
    "FOR (d:DecisionNode) ON (d.confidence)",
    "CREATE INDEX assumption_confidence IF NOT EXISTS "
    "FOR (a:AssumptionNode) ON (a.confidence)",

    # ── Full-text search across all memory content ────────────────
    "CREATE FULLTEXT INDEX memory_search IF NOT EXISTS "
    "FOR (n:DecisionNode|RationaleNode|ConstraintNode|"
    "AssumptionNode|TradeoffNode|InsightNode) "
    "ON EACH [n.content, n.qualified_name]",

    # ── Vector search (reuses codegraph's 1536-dim infrastructure) ─
    # Neo4j vector indexes don't support multi-label syntax, so create
    # separate indexes for each memory label that carries embeddings.
    "CREATE VECTOR INDEX memory_decision_embedding IF NOT EXISTS "
    "FOR (n:DecisionNode) ON (n.doc_embedding) "
    "OPTIONS {indexConfig: {"
    "`vector.dimensions`: 1536, "
    "`vector.similarity_function`: 'cosine'"
    "}}",
    "CREATE VECTOR INDEX memory_rationale_embedding IF NOT EXISTS "
    "FOR (n:RationaleNode) ON (n.doc_embedding) "
    "OPTIONS {indexConfig: {"
    "`vector.dimensions`: 1536, "
    "`vector.similarity_function`: 'cosine'"
    "}}",
    "CREATE VECTOR INDEX memory_insight_embedding IF NOT EXISTS "
    "FOR (n:InsightNode) ON (n.doc_embedding) "
    "OPTIONS {indexConfig: {"
    "`vector.dimensions`: 1536, "
    "`vector.similarity_function`: 'cosine'"
    "}}",
]


def apply_schema() -> None:
    """Apply all memory node constraints and indexes to Neo4j.

    Idempotent — uses ``IF NOT EXISTS`` on every statement.
    Safe to call multiple times.  No-op for non-Neo4j backends
    (SQLite manages its own schema in ``backends/sqlite/schema.py``).
    """
    backend = get_backend()
    if type(backend).__name__ != "Neo4jBackend":
        return
    for stmt in MEMORY_CONSTRAINTS_AND_INDEXES:
        try:
            get_backend().execute_raw(stmt)
        except Exception as e:
            # Index/constraint may already exist or syntax may differ
            # across Neo4j versions — log but don't crash.
            import logging
            logging.getLogger(__name__).warning(
                "Schema DDL failed (may already exist): %s — %s",
                stmt.split(" IF NOT EXISTS")[0][:60],
                e,
            )