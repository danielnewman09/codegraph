"""SQLite search — FTS5 full-text + numpy-exact vector search.

Full-text
~~~~~~~~~
``fts_nodes`` is an FTS5 shadow table populated on save (content +
qualified_name + tags).  ``fts_search`` runs ``MATCH`` with optional
label/tag post-filters via the join tables and ranks with ``bm25()``
(negated so higher = better, matching Neo4j's score ordering).

Vector
~~~~~~
Embeddings live canonically in ``node_embeddings`` as packed float32
BLOBs.  ``vector_search`` does **filter-then-KNN**: resolve the
label/tag filters to node ids first (indexed), then run a numpy BLAS
matmul over the normalized embedding matrix — exact cosine similarity,
deterministic parity with Neo4j's exact vector index, and no native
SQLite extension.  The in-memory matrix is a derived cache keyed by a
``(count, max updated_at)`` fingerprint; ``node_embeddings`` is the
single source of truth.

The ``VectorIndex`` interface leaves the ANN upgrade path (hnswlib /
FAISS) open: a future implementation can replace the matmul without
touching the schema or the repositories.
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
import sqlalchemy as sa

from codegraph.backends.sqlite.connection import SqliteConnection, row_to_dict
from codegraph.backends.sqlite.node_ops import _row_to_node

log = logging.getLogger(__name__)


# ── Embedding pack/unpack (float32 BLOBs) ────────────────────────────────


def pack_embedding(values: list[float]) -> bytes:
    """Pack a list of floats into a compact float32 BLOB."""
    return np.asarray(values, dtype=np.float32).tobytes()


def unpack_embedding(blob: bytes) -> np.ndarray:
    """Unpack a float32 BLOB into a numpy array."""
    return np.frombuffer(blob, dtype=np.float32)


# ── Label / tag resolution helpers ──────────────────────────────────────


def _resolve_node_ids(
    conn,
    *,
    labels: str = "",
    tag: str | None = None,
) -> list[int] | None:
    """Resolve label/tag filters to node ids.

    Returns None when no filter is given (meaning "all nodes"); an
    empty list when a filter matches nothing (search yields nothing).
    """
    if not labels and tag is None:
        return None
    sql = "SELECT DISTINCT n.id FROM nodes n "
    where: list[str] = []
    params: dict[str, Any] = {}
    if labels:
        label_names = [l for l in labels.split("|") if l]
        if label_names:
            binds = ", ".join(f":l{i}" for i in range(len(label_names)))
            sql += "JOIN node_labels nl ON nl.node_id = n.id "
            where.append(f"nl.label IN ({binds})")
            params.update({f"l{i}": l for i, l in enumerate(label_names)})
    if tag is not None:
        sql += "JOIN node_tags nt ON nt.node_id = n.id "
        where.append("nt.tag = :tag")
        params["tag"] = tag
    rows = list(conn.execute(sa.text(sql + " WHERE " + " AND ".join(where)), params))
    return [r[0] for r in rows]


def _inflate_from_ids(conn, node_ids: list[int]) -> dict[int, Any]:
    """Load and inflate nodes by id, keyed by id."""
    out: dict[int, Any] = {}
    if not node_ids:
        return out
    binds = ", ".join(f":i{n}" for n in range(len(node_ids)))
    params = {f"i{n}": nid for n, nid in enumerate(node_ids)}
    rows = list(
        conn.execute(
            sa.text(
                f"SELECT id, uid, labels, properties FROM nodes "
                f"WHERE id IN ({binds})"
            ),
            params,
        )
    )
    for row in rows:
        d = row_to_dict(row)
        node = _row_to_node(row, conn)
        if node is not None:
            out[d["id"]] = node
    return out


# ── Full-text search ─────────────────────────────────────────────────────


def fts_search(
    conn_obj: SqliteConnection,
    query: str,
    *,
    labels: str = "",
    tag: str | None = None,
    limit: int = 20,
) -> list[dict]:
    """Full-text search over ``fts_nodes``.

    Returns ``[{"node": CodeGraphNode, "score": float}]`` ordered by
    descending score.  Falls back to a LIKE scan (score 1.0) when the
    FTS5 MATCH syntax rejects the query.
    """
    if not query:
        return []

    with conn_obj.connect() as conn:
        node_ids = _resolve_node_ids(conn, labels=labels, tag=tag)
        if node_ids == []:
            return []
        if node_ids is None:
            id_filter_sql = ""
            params: dict[str, Any] = {}
        else:
            binds = ", ".join(f":n{i}" for i in range(len(node_ids)))
            id_filter_sql = f" AND n.id IN ({binds})"
            params = {f"n{i}": nid for i, nid in enumerate(node_ids)}

        try:
            rows = list(
                conn.execute(
                    sa.text(
                        "SELECT n.id, -bm25(fts_nodes) AS score "
                        "FROM fts_nodes "
                        "JOIN nodes n ON n.uid = fts_nodes.uid "
                        "WHERE fts_nodes MATCH :q"
                        + id_filter_sql
                        + " ORDER BY score DESC LIMIT :lim"
                    ),
                    {"q": query, "lim": limit, **params},
                )
            )
        except Exception:
            log.debug("FTS5 MATCH rejected %r — falling back to LIKE", query, exc_info=True)
            rows = list(
                conn.execute(
                    sa.text(
                        "SELECT n.id, 1.0 AS score FROM nodes n "
                        "WHERE lower(n.properties) LIKE :q "
                        + (id_filter_sql or "")
                        + " LIMIT :lim"
                    ),
                    {"q": f"%{query.lower()}%", "lim": limit, **params},
                )
            )

        nodes = _inflate_from_ids(conn, [r[0] for r in rows])
        return [
            {"node": nodes[r[0]], "score": r[1]}
            for r in rows
            if r[0] in nodes
        ]


# ── Vector search (numpy-exact) ──────────────────────────────────────────


class VectorIndex:
    """Numpy-exact vector search over ``node_embeddings``.

    Maintains a lazily rebuilt, L2-normalized embedding matrix as a
    derived in-process cache.  The canonical store is the
    ``node_embeddings`` table; the cache is keyed by a
    ``(count, max updated_at)`` fingerprint so saves/updates/deletes
    invalidate it cheaply without bookkeeping.
    """

    def __init__(self, conn: SqliteConnection):
        self._conn = conn
        self._matrix: np.ndarray | None = None
        self._node_ids: list[int] = []
        self._fingerprint: tuple[int, float] | None = None

    def _ensure_loaded(self) -> None:
        with self._conn.connect() as c:
            count = c.execute(
                sa.text("SELECT COUNT(*) FROM node_embeddings")
            ).scalar_one()
            max_ts = c.execute(
                sa.text(
                    "SELECT COALESCE(MAX(updated_at), 0.0) FROM node_embeddings"
                )
            ).scalar_one()
        fp = (int(count), float(max_ts))
        if self._matrix is not None and fp == self._fingerprint:
            return
        with self._conn.connect() as c:
            rows = list(
                c.execute(
                    sa.text(
                        "SELECT node_id, embedding, dim FROM node_embeddings"
                    )
                )
            )
        if not rows:
            self._matrix = None
            self._node_ids = []
            self._fingerprint = fp
            return
        dims = {r[2] for r in rows}
        if len(dims) > 1:
            log.warning("Mixed embedding dimensions in node_embeddings (%s)", dims)
        matrix = np.vstack([unpack_embedding(r[1]) for r in rows]).astype(np.float32)
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        self._matrix = matrix / norms
        self._node_ids = [r[0] for r in rows]
        self._fingerprint = fp

    def search(
        self,
        embedding: list[float],
        *,
        node_ids: list[int] | None = None,
        limit: int = 10,
    ) -> list[tuple[int, float]]:
        """Return ``[(node_id, cosine_similarity)]`` for the top-k hits.

        *node_ids* restricts the search to a subset (filter-then-KNN).
        """
        self._ensure_loaded()
        if self._matrix is None or not self._node_ids:
            return []
        q = np.asarray(embedding, dtype=np.float32)
        qn = q / (np.linalg.norm(q) + 1e-9)
        scores = self._matrix @ qn  # one GEMM (BLAS)
        order = np.argsort(-scores)
        if node_ids is not None:
            allowed = set(node_ids)
            order = np.array(
                [i for i in order if self._node_ids[i] in allowed],
                dtype=int,
            )
        top = order[:limit]
        result = []
        for i in top:
            if node_ids is None or self._node_ids[i] in allowed:
                result.append((self._node_ids[i], float(scores[i])))
        return result


def vector_search(
    conn_obj: SqliteConnection,
    embedding: list[float],
    *,
    labels: str = "",
    tag: str | None = None,
    limit: int = 10,
) -> list[dict]:
    """Vector similarity search with optional label/tag filters.

    Returns ``[{"node": CodeGraphNode, "score": float}]`` ordered by
    descending cosine similarity.
    """
    with conn_obj.connect() as conn:
        node_ids = _resolve_node_ids(conn, labels=labels, tag=tag)
        if node_ids == []:
            return []
    index = _get_vector_index(conn_obj)
    hits = index.search(embedding, node_ids=node_ids, limit=limit)
    if not hits:
        return []
    with conn_obj.connect() as conn:
        nodes = _inflate_from_ids(conn, [nid for nid, _ in hits])
    return [
        {"node": nodes[nid], "score": score}
        for nid, score in hits
        if nid in nodes
    ]


# ── Cache registry (one VectorIndex per connection) ──────────────────────

_index_cache: dict[int, VectorIndex] = {}


def _get_vector_index(conn_obj: SqliteConnection) -> VectorIndex:
    idx = _index_cache.get(id(conn_obj))
    if idx is None:
        idx = VectorIndex(conn_obj)
        _index_cache[id(conn_obj)] = idx
    return idx


def invalidate_vector_index(conn_obj: SqliteConnection) -> None:
    """Drop the cached VectorIndex for a connection (after wipe)."""
    _index_cache.pop(id(conn_obj), None)
