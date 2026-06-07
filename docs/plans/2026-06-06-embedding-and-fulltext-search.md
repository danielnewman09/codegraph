# Embedding & Full-Text Search for Methods/Functions

> **Status:** Evaluation / Draft  
> **Date:** 2026-06-06  
> **Scope:** MethodNode, FunctionNode (member types with executable bodies)

---

## Problem

When code is parsed (e.g. from Doxygen XML or Sphinx), we currently store:

- **Signature** (`definition`: `"void Widget::draw(Canvas c)"`) — the declaration only
- **Documentation** (`brief_description`, `detailed_description`) — Doxygen/Sphinx doc strings
- **Metadata** (`type_signature`, `argsstring`, visibility flags, etc.)

We do **not** store the **implementation body** — the actual source code inside
`{ … }`. This means:

1. **Full-text search** cannot find methods that *use* a particular API,
   pattern, or identifier in their implementation.
2. **Semantic/vector search** cannot find methods that are *conceptually similar*
   but named differently — "find all methods that sort data" vs. finding
   `quicksort()`, `mergesort()`, `timsort()`.
3. The existing `doc_search` full-text index covers `name`, `qualified_name`,
   `brief_description`, and `detailed_description` — but skips `definition`
   (the signature) and has no implementation content at all.

---

## Proposed Changes

### 1. Add `implementation` field to `_MemberMixin`

A new `StringProperty` to store the full method/function body (source code
between `{` and `}`).

```python
# In _MemberMixin (member.py):

# --- Implementation ---
implementation = StringProperty(default="")
```

**Why `_MemberMixin` and not just `MethodNode`/`FunctionNode`?**

- `DefineNode` also has a macro body (`#define MAX_SIZE 1024`) that benefits
  from the same search capability.
- `AttributeNode` initializer expressions (e.g. `int count = 0`) are tiny but
  could be stored for completeness.
- A single field on the mixin is simpler than conditionally adding it to
  specific types, and an empty string costs nothing for types that don't use it.

**Impact on existing code:**

| Affected area | Change required |
|---|---|
| `member.py` `_MemberMixin` | Add `implementation = StringProperty(default="")` |
| `compound.py` `_CompoundMixin` | Add `implementation = StringProperty(default="")` (classes/enums may also benefit) |
| `constants.py` `CONSTRAINTS_AND_INDEXES` | Add full-text index for implementation |
| `examples/doxygen_to_neo4j.py` `add_member()` | Populate `implementation` from Doxygen `<programlisting>` or source extraction |
| `scripts/load_api_to_neo4j.py` | Optionally populate `implementation` from Sphinx source extraction |
| `tests/data/*_node_full.json` | Add `implementation` key to fixtures |
| `_llm_fields` on MethodNode, FunctionNode | Add `"implementation"` so it's included in `serialize()` |
| Neo4j migration | No migration needed — `StringProperty(default="")` is backwards-compatible |

**Population strategy (Doxygen):**

Doxygen XML wraps implementation code inside `<programlisting>` elements inside
`<detaileddescription>` or separate `<sectiondef>` blocks. The parser can extract
these, concatenate `<codeline>` text, and store the result as `implementation`.

For C/C++ source files, the `<location bodystart="57" bodyend="89">` attributes
give the line range, enabling extraction from the original source file.

**Population strategy (Sphinx / Python):**

Python `inspect.getsource()` can retrieve the implementation body at load time.
The Sphinx API extraction pipeline can include source text.

### 2. Add `doc_embedding` and `impl_embedding` vector fields

Two `ArrayProperty(FloatProperty())` fields for storing pre-computed vector
embeddings.

```python
# In _MemberMixin (member.py):

# --- Vector embeddings ---
doc_embedding = ArrayProperty(FloatProperty(), default=[])
impl_embedding = ArrayProperty(FloatProperty(), default=[])
```

**Why two separate embeddings?**

| Field | Content | Use Case |
|---|---|---|
| `doc_embedding` | Embedding of `brief_description` + `detailed_description` | "Find methods similar to this documentation" |
| `impl_embedding` | Embedding of `implementation` (source code body) | "Find methods that implement similar logic" |

Documentation and implementation describe the same function from different
angles. A method's docstring says *what* it does; its implementation says *how*.
Keeping them separate allows targeted semantic search.

**Dimension choices:**

| Embedding model | Dimensions | Notes |
|---|---|---|
| OpenAI `text-embedding-3-small` | 1536 | Default, widely used |
| OpenAI `text-embedding-3-large` | 3072 | Higher quality |
| `all-MiniLM-L6-v2` (local) | 384 | Fast, runs locally |
| `BAAI/bge-small-en-v1.5` (local) | 384 | Good quality/size trade-off |

The schema should not hardcode dimensions — they're specified at index
creation time in the Neo4j `CREATE VECTOR INDEX` DDL.

**Why `ArrayProperty(FloatProperty())` and not `JSONProperty`?**

- `ArrayProperty(FloatProperty())` stores as Neo4j `LIST<FLOAT>`, which is
  required for `CREATE VECTOR INDEX`.
- `JSONProperty` stores as Neo4j string, which can't be vector-indexed.

**Impact on existing code:**

| Affected area | Change required |
|---|---|
| `member.py` `_MemberMixin` | Add `doc_embedding`, `impl_embedding` fields |
| `compound.py` `_CompoundMixin` | Optionally add `doc_embedding` for class-level doc search |
| `constants.py` | Add `CREATE VECTOR INDEX` DDL statements |
| `models/__init__.py` | No change (exports unaffected) |
| Embedding computation | New module/pipeline needed (see Section 4) |
| `_llm_fields` | **Do NOT include** embedding fields — they're binary vectors, not LLM-visible text |
| Neo4j migration | Backwards-compatible — `ArrayProperty(default=[])` |

### 3. Expand full-text search index

Update the existing `doc_search` full-text index to include `definition` and
`implementation`.

```cypher
-- Current (in constants.py):
CREATE FULLTEXT INDEX doc_search IF NOT EXISTS
  FOR (n:Compound|Member) ON EACH [
    n.name, n.qualified_name,
    n.brief_description, n.detailed_description
  ]

-- Proposed:
CREATE FULLTEXT INDEX doc_search IF NOT EXISTS
  FOR (n:Compound|Member) ON EACH [
    n.name, n.qualified_name,
    n.brief_description, n.detailed_description,
    n.definition, n.implementation
  ]
```

**Note:** Full-text indexes in Neo4j 5.x cannot be altered — you must
drop and recreate them. This means adding `definition` and `implementation`
to the index requires a migration step.

**Impact:**

| Affected area | Change required |
|---|---|
| `constants.py` `CONSTRAINTS_AND_INDEXES` | Update `doc_search` index definition |
| `examples/doxygen_to_neo4j.py` `CONSTRAINTS_AND_INDEXES` | Update `doc_search` index definition |
| Migration script | Needed to drop/recreate the index in existing databases |

### 4. Add vector index DDL statements

New vector indexes for semantic similarity queries.

```cypher
-- Method/Function document embedding index
CREATE VECTOR INDEX member_doc_embedding IF NOT EXISTS
  FOR (n:Method|Function) ON (n.doc_embedding)
  OPTIONS {
    indexConfig: {
      `vector.dimensions`: 1536,
      `vector.similarity_function`: 'cosine'
    }
  }

-- Method/Function implementation embedding index
CREATE VECTOR_INDEX member_impl_embedding IF NOT EXISTS
  FOR (n:Method|Function) ON (n.impl_embedding)
  OPTIONS {
    indexConfig: {
      `vector.dimensions`: 1536,
      `vector.similarity_function`: 'cosine'
    }
  }
```

**Note:** Neo4j vector indexes require that:
1. All nodes with the target labels have the embedding property, OR
2. Empty embeddings `[]` are handled gracefully.

Since we default to `[]`, vectors of length 0 won't be indexed but also
won't cause errors. Only nodes with populated embeddings participate in
vector search.

**Neo4j version requirement:** Vector indexes require Neo4j 5.11+.

---

## Alternative: Separate Embedding Node Approach

Instead of storing embeddings directly on MethodNode/FunctionNode, create
a separate `EmbeddingNode`:

```cypher
(:EmbeddingNode {
  text_hash: "sha256:abc...",
  text_content: "void Widget::draw(Canvas c) { ... }",
  text_kind: "implementation",       -- "documentation" | "implementation" | "signature"
  embedding: [0.1, 0.2, ...],
  dimensions: 1536,
  model: "text-embedding-3-small"
})

(:MethodNode)-[:HAS_EMBEDDING]->(:EmbeddingNode)
```

**Pros:**
- Clean separation of concerns — MethodNode stays focused on code metadata
- Embedding can be regenerated without touching the method node
- Multiple embeddings per method (different models, different text kinds)
- Works for classes, namespaces, etc. without adding fields to each

**Cons:**
- More complex queries (traversal required)
- Embedding generation and storage are less co-located
- Requires managing `HAS_EMBEDDING` relationship lifecycle

**Recommendation:** Start with the inline `ArrayProperty` approach (simpler,
direct). Migrate to separate nodes only if/when embedding management becomes
complex (e.g. multiple models, versioning).

---

## Implementation Plan

### Phase 1: Storage Layer (no embedding computation)

Add the fields and indexes. Data population comes later.

#### Step 1: Add `implementation` field to `_MemberMixin` and `_CompoundMixin`

**File:** `src/codegraph/models/member.py`

```python
class _MemberMixin(StructuredNode, CodeGraphNode):
    # ... existing fields ...

    # --- Implementation ---
    implementation = StringProperty(
        default="",
        help_text="Full source code body of the method/function.",
    )

    # --- Vector embeddings ---
    doc_embedding = ArrayProperty(FloatProperty(), default=[])
    impl_embedding = ArrayProperty(FloatProperty(), default=[])
```

**File:** `src/codegraph/models/compound.py`

```python
class _CompoundMixin(StructuredNode, CodeGraphNode):
    # ... existing fields ...

    # --- Implementation ---
    implementation = StringProperty(
        default="",
        help_text="Full source code body (e.g. for inline-defined classes).",
    )

    # --- Vector embeddings ---
    doc_embedding = ArrayProperty(FloatProperty(), default=[])
```

#### Step 2: Update `_llm_fields` for MethodNode and FunctionNode

Add `"implementation"` to the LLM-visible fields so it's included in
`serialize()` output (useful for LLM consumers that need source code).

**File:** `src/codegraph/models/member.py`

```python
class MethodNode(_MemberMixin):
    _llm_fields = {
        "qualified_name", "name", "kind", "brief_description",
        "type_signature", "argsstring", "visibility", "implementation",
    }

class FunctionNode(_MemberMixin):
    _llm_fields = {
        "qualified_name", "name", "kind", "brief_description",
        "type_signature", "argsstring", "visibility", "implementation",
    }
```

**NOTE:** Intentionally do NOT add `"doc_embedding"` or `"impl_embedding"`
to `_llm_fields` — vector floats are not useful as LLM context.

#### Step 3: Update `CONSTRAINTS_AND_INDEXES` in `constants.py`

Replace the existing `doc_search` full-text index and add vector indexes:

```python
CONSTRAINTS_AND_INDEXES: list[str] = [
    # ... existing constraints and indexes ...

    # Full-text search — expanded to include definition and implementation
    "CREATE FULLTEXT INDEX doc_search IF NOT EXISTS FOR (n:Compound|Member) ON EACH [n.name, n.qualified_name, n.brief_description, n.detailed_description, n.definition, n.implementation]",

    # Vector search — method/function documentation embeddings
    "CREATE VECTOR INDEX member_doc_embedding IF NOT EXISTS FOR (n:Method|Function) ON (n.doc_embedding) OPTIONS {indexConfig: {`vector.dimensions`: 1536, `vector.similarity_function`: 'cosine'}}",

    # Vector search — method/function implementation embeddings
    "CREATE VECTOR INDEX member_impl_embedding IF NOT EXISTS FOR (n:Method|Function) ON (n.impl_embedding) OPTIONS {indexConfig: {`vector.dimensions`: 1536, `vector.similarity_function`: 'cosine'}}",
]
```

**Note:** The `CREATE FULLTEXT INDEX ... IF NOT EXISTS` won't modify an existing
index. To add new fields to an existing full-text index, you must drop and
recreate it:

```cypher
DROP INDEX doc_search IF EXISTS;
CREATE FULLTEXT INDEX doc_search FOR (n:Compound|Member) ON EACH [...];
```

This should be documented as a migration step.

#### Step 4: Update `examples/doxygen_to_neo4j.py` to match

Update the `CONSTRAINTS_AND_INDEXES` list in the Doxygen ingester to include
the same expanded full-text index and vector indexes.

#### Step 5: Update test fixtures

Add `"implementation"` key to `tests/data/method_node_full.json` and
`tests/data/function_node_full.json`:

```json
{
  "type": "MethodNode",
  "qualified_name": "Widget::draw(Canvas)",
  ...
  "implementation": "void Widget::draw(Canvas c) {\n  c.beginDraw();\n  render(c);\n  c.endDraw();\n}"
}
```

#### Step 6: Add unit tests for new fields

Test that `implementation`, `doc_embedding`, and `impl_embedding`
serialize/deserialize correctly, appear/not in LLM fields as appropriate,
and default to empty values.

### Phase 2: Embedding Computation Pipeline

Separate from the storage layer. Creates a new module for computing embeddings.

#### Step 1: Create `src/codegraph/embedding.py`

```python
"""Embedding computation for codegraph nodes.

Provides utilities for computing vector embeddings of method/function
documentation and implementation text, and persisting them to Neo4j.
"""

from codegraph.models.member import MethodNode, FunctionNode
from codegraph.connection import cypher_query

SUPPORTED_MODELS = {
    "text-embedding-3-small": {"dimensions": 1536, "provider": "openai"},
    "text-embedding-3-large": {"dimensions": 3072, "provider": "openai"},
    "all-MiniLM-L6-v2": {"dimensions": 384, "provider": "local"},
    "BAAI/bge-small-en-v1.5": {"dimensions": 384, "provider": "local"},
}


def compute_doc_embedding(node: MethodNode | FunctionNode) -> list[float]:
    """Compute an embedding from the node's documentation text.

    Concatenates brief_description and detailed_description,
    then computes the embedding vector.
    """
    text = f"{node.brief_description}\n\n{node.detailed_description}".strip()
    if not text:
        return []
    # Defer to embedding provider (Phase 2 implementation)
    ...


def compute_impl_embedding(node: MethodNode | FunctionNode) -> list[float]:
    """Compute an embedding from the node's implementation source code.

    Uses the implementation field (method body).
    """
    text = node.implementation
    if not text:
        return []
    # Defer to embedding provider (Phase 2 implementation)
    ...


def search_similar_by_doc(
    query_embedding: list[float],
    limit: int = 10,
    node_labels: list[str] | None = None,
) -> list[dict]:
    """Find nodes with similar documentation embeddings.

    Uses Neo4j's vector index for approximate nearest neighbor search.
    """
    labels = node_labels or ["Method", "Function"]
    label_expr = ":".join(labels)

    results, _ = cypher_query(
        """
        CALL db.index.vector.queryNodes($index_name, $limit, $query_embedding)
        YIELD node, score
        RETURN node.qualified_name AS qualified_name,
               node.name AS name,
               node.kind AS kind,
               node.brief_description AS brief_description,
               score
        ORDER BY score DESC
        """,
        params={
            "index_name": "member_doc_embedding",
            "limit": limit,
            "query_embedding": query_embedding,
        },
    )
    return results


def search_similar_by_impl(
    query_embedding: list[float],
    limit: int = 10,
    node_labels: list[str] | None = None,
) -> list[dict]:
    """Find nodes with similar implementation embeddings.

    Uses Neo4j's vector index for approximate nearest neighbor search.
    """
    labels = node_labels or ["Method", "Function"]
    label_expr = ":".join(labels)

    results, _ = cypher_query(
        """
        CALL db.index.vector.queryNodes($index_name, $limit, $query_embedding)
        YIELD node, score
        RETURN node.qualified_name AS qualified_name,
               node.name AS name,
               node.kind AS kind,
               node.brief_description AS brief_description,
               score
        ORDER BY score DESC
        """,
        params={
            "index_name": "member_impl_embedding",
            "limit": limit,
            "query_embedding": query_embedding,
        },
    )
    return results


def fulltext_search(query: str, limit: int = 10) -> list[dict]:
    """Search methods/functions by documentation, name, or implementation text.

    Uses Neo4j's full-text index.
    """
    results, _ = cypher_query(
        """
        CALL db.index.fulltext.queryNodes('doc_search', $query)
        YIELD node, score
        WHERE node:Method OR node:Function
        RETURN node.qualified_name AS qualified_name,
               node.name AS name,
               node.kind AS kind,
               node.brief_description AS brief_description,
               node.implementation AS implementation,
               score
        ORDER BY score DESC
        LIMIT $limit
        """,
        params={"query": query, "limit": limit},
    )
    return results
```

---

## Summary of Changes

| Change | Files | Complexity | Neo4j Version |
|---|---|---|---|
| Add `implementation` field | `member.py`, `compound.py` | Low | Any |
| Add `doc_embedding`, `impl_embedding` fields | `member.py`, `compound.py` | Low | Any |
| Update `_llm_fields` (add `implementation`) | `member.py` | Low | Any |
| Update full-text index DDL | `constants.py`, `doxygen_to_neo4j.py` | Low | Any |
| Add vector index DDL | `constants.py`, `doxygen_to_neo4j.py` | Low | 5.11+ |
| Populate `implementation` in Doxygen parser | `doxygen_to_neo4j.py` | Medium | Any |
| Populate embeddings | New module `embedding.py` | Medium | 5.11+ |
| Vector search queries | New module `embedding.py` or `repository.py` | Medium | 5.11+ |
| Update test fixtures | `tests/data/*.json` | Low | Any |
| Migration: drop/recreate `doc_search` index | Migration script | Low | Any |

## Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Large implementation bodies bloat Neo4j property storage | Compress or truncate implementations >10KB; use a separate `ImplementationStore` for very large bodies |
| Vector indexes require Neo4j 5.11+ | Feature-gate vector search behind a config flag; gracefully degrade to full-text only |
| neomodel `ArrayProperty(FloatProperty())` may have edge cases with empty lists | Test thoroughly; default to `[]` and skip nodes with empty embeddings in vector search |
| Full-text index rebuild required to add fields | Document as a migration step; provide a script |
| Embedding computation is expensive | Compute embeddings offline in a batch pipeline, not at ingestion time |

## Recommendation

**Start with Phase 1** (storage layer) — add the `implementation`, `doc_embedding`,
and `impl_embedding` fields plus updated index DDL. This is low-risk,
backwards-compatible, and enables immediate full-text search over implementation
code once the Doxygen parser populates `implementation`.

**Defer Phase 2** (embedding computation) until there's a concrete consumer
(LLM query pipeline, semantic search UI, etc.). The fields are ready to be
populated whenever the pipeline is built.