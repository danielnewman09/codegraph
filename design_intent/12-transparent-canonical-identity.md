# Transparent Canonical Identity

**Status:** Proposed direction  
**Established:** 2026-08-15

## Decision direction

Codegraph should replace SHA-1-based node UIDs with transparent canonical string
keys constructed from the node's proper identity fields.

The current SHA-1 value is deterministic, but the hash is not the identity. The
ordered fields supplied to the hash are the identity. Persisting a reversible,
canonical representation of those fields makes the graph easier to inspect,
debug, export, reconcile, and operate without weakening deterministic behavior.

### `DI-KEY-001` — Canonical fields are the identity

A node's identity shall be defined by an explicit, documented tuple of semantic
fields. The stored primary key should canonically encode that tuple rather than
replace it with an opaque digest.

### `DI-KEY-002` — Keys are transparent and reversible

An engineer or tool should be able to inspect a key and determine its node type,
scope, and identity fields without consulting a translation table or
recomputing candidate hashes.

### `DI-KEY-003` — Encoding is unambiguous

Canonical keys shall not use naïve concatenation with an escapable delimiter.
The encoding must distinguish all valid tuples, including fields containing
colons, slashes, templates, signatures, Unicode, or empty optional values.

A versioned URI-style encoding, escaped path segments, or a length-prefixed
canonical format are possible implementations. The specific syntax should be
selected and tested separately from the decision to remove hashing.

### `DI-KEY-004` — Node type participates in global identity

If a key is globally unique across the datastore, it should include the
canonical node type or artifact category. A namespace, class, requirement,
memory, and test with the same textual qualified name must not collide merely
because they occupy different backend labels.

### `DI-KEY-005` — Provenance is not silently conflated with identity

`source`, tags, extraction adapter, and design/as-built status describe
provenance. They should participate in canonical identity only when they
represent a genuine scope boundary, not merely because the node was observed by
a different pipeline.

### `DI-KEY-006` — Project scope is explicit

When identical qualified names in different projects must remain distinct, the
key should contain an explicit project or codebase scope with stable semantics.
That scope should not depend accidentally on a parser's source label or a
temporary generation run name.

### `DI-KEY-007` — Overloads retain canonical signatures

Callable identity should include a canonical signature component sufficient to
distinguish overloads. Normalization rules for parameter types, qualifiers,
templates, and language-specific syntax remain part of identity even after the
SHA-1 encoding is removed.

### `DI-KEY-008` — Cross-view correspondence is first-class

Design and as-built nodes that represent the same logical entity should either
share a canonical logical key or carry an explicit correspondence relationship.
The system should not require qualified-name heuristics merely because their
provenance fields caused different primary keys.

### `DI-KEY-009` — Identity changes are explicit migrations

Renaming, moving, changing a callable signature, or changing project scope may
change a canonical key. Indexing and reconciliation should report such changes
as rename, relocation, or signature-change candidates rather than presenting
only an unrelated deletion and creation.

### `DI-KEY-010` — Human readability does not replace validation

Transparent keys still require uniqueness constraints, canonicalization tests,
collision tests, and backend validation. Removing cryptographic hashing does not
permit informal or inconsistent key construction.

## Current behavior and debt

The present implementation computes:

```text
SHA1(source NUL identity_field_1 NUL identity_field_2 ...)
```

Typical identity fields are:

- compound, namespace, requirement, memory, and test: `qualified_name`;
- method or function: `qualified_name` plus normalized `argsstring`;
- file: `path`;
- parameter: `member_refid` plus position;
- implementation: `qualified_name` plus implementation kind.

The NUL-separated input avoids concatenation collisions before hashing, but the
stored digest discards the useful structure. In addition, node type is absent
from the tuple, and `source` currently acts simultaneously as project scope and
provenance. These concerns should be resolved in the new identity contract.

## Illustrative key shape

The following is illustrative, not yet a selected wire format:

```text
cg:v1:<project-scope>:class:<qualified-name>
cg:v1:<project-scope>:method:<qualified-name>:<canonical-signature>
cg:v1:requirement:<requirement-scope>:<qualified-name>
cg:v1:memory:<memory-type>:<qualified-name>
```

Every variable segment would require canonical escaping or length-prefixing.
The `v1` marker permits future evolution without guessing which identity rules
produced an existing key.

## Primary key versus logical correspondence

Two viable models should be evaluated explicitly:

1. **Shared logical key:** design and as-built representations of one entity use
   the same canonical key and coexist through tags/provenance.
2. **Scoped observation keys:** each representation has its own primary key and
   an explicit `REALIZES`, `OBSERVES`, or equivalent correspondence edge to a
   stable logical entity.

The current model attempts the first approach through multi-tagged nodes but
undermines it by including pipeline `source` in the UID. The replacement should
choose one model deliberately. For the current architecture, a shared logical
key is likely simpler where Codegraph already expects one node to carry both
`design` and `as-built` tags.

## Migration considerations

Changing UID representation affects every node, relationship endpoint, index,
fixture, serialized graph, repository lookup, memory link, requirement link,
test link, and external consumer. It should therefore be treated as a schema and
data migration rather than a local helper refactor.

A safe sequence is:

1. Specify canonical identity fields for every registered node type.
2. Decide project scope and cross-view identity semantics.
3. Select and version an unambiguous string encoding.
4. Add canonical keys alongside legacy SHA-1 UIDs.
5. Build a migration map from legacy UID to canonical key and validate it for
   duplicates and cross-type collisions.
6. Rewrite relationship endpoints transactionally in each backend.
7. Update JSON, Markdown metadata, fixtures, tools, and APIs to use canonical
   keys while accepting legacy UIDs during a compatibility window.
8. Run the connected `cpp-sqlite` golden tests to prove that code, tests,
   requirements, and memories retain their relationships.
9. Remove legacy UID support only after all stored graphs and consumers have
   migrated.

## Acceptance criteria

- Keys are deterministic, versioned, reversible, and unambiguous.
- Every registered node type has a documented identity tuple.
- Different node types cannot collide accidentally.
- Codebase scope and provenance have distinct semantics.
- Callable overloads remain distinct after normalization.
- Design/as-built correspondence no longer requires compensating for a hashed
  source-dependent UID.
- All relationship types survive migration in Neo4j, SQLite, memory, and
  portable graph snapshots.
- Existing legacy datasets produce a complete migration report, including any
  ambiguous or duplicate identities.

