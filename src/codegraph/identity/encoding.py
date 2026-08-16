"""Strict encoder/decoder for the ``cg:v1`` canonical key grammar.

Logical grammar (before percent-encoding)::

    cg:v1:<scope-kind>:<scope-id>:<artifact-category>:<field>=<value>:...

Encoding rules (fixed architectural decision 4 of the Priority 2 plan):

- Every *variable* segment is UTF-8 percent-encoded with only RFC 3986
  unreserved characters (``A-Z a-z 0-9 - . _ ~``) left literal.
- Colons, equals signs, slashes, percent signs, template brackets,
  Unicode bytes, and whitespace are encoded.
- Empty values are represented by an empty value after ``=``.
- Fields occur in the exact order registered for the artifact category
  (enforced by :mod:`codegraph.identity.registry`, not here).
- The ``cg:v1:`` prefix is literal and never encoded.

The decoder is *strict*: it rejects malformed percent escapes,
non-canonical encodings (encoded unreserved characters, lowercase hex),
and structural violations, so a decoded key always re-encodes to the
identical string.  Unknown versions, scope kinds, and artifact categories
are validated at the registry layer (:func:`codegraph.identity.registry.
CanonicalIdentity.from_key`), which owns the typed value object.

Example shapes (logical, before encoding)::

    cg:v1:repository:codegraph-suite/codegraph:class:qualified_name=codegraph.graph.LayerGraph
    cg:v1:repository:cpp-suite/cpp-sqlite:method:qualified_name=cpp_sqlite::Database::getDAO:signature=()<T>&
    cg:v1:project:codegraph-suite:requirement-hlr:qualified_name=Architecture Diagram Generator
"""

from __future__ import annotations

import re
from dataclasses import dataclass

__all__ = [
    "KeyFormatError",
    "ParsedKey",
    "VERSION_PREFIX",
    "encode_segment",
    "decode_segment",
    "encode_key",
    "parse_key",
]

#: The literal key prefix: scheme ``cg`` + version ``v1``.
VERSION_PREFIX = "cg:v1:"

#: Supported key versions (the integer after ``v`` in the prefix).
SUPPORTED_VERSIONS = frozenset({1})

#: RFC 3986 unreserved characters — the only characters left literal.
_UNRESERVED = frozenset(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~"
)

_HEX = frozenset("0123456789ABCDEF")
_HEX_RE = re.compile(r"%[0-9A-Fa-f]{2}")


class KeyFormatError(ValueError):
    """Raised when a canonical key violates the ``cg:v1`` grammar."""


@dataclass(frozen=True)
class ParsedKey:
    """Grammar-level parsed form of a canonical key.

    Fields are returned in wire order and may be reordered or missing
    relative to the registered artifact spec; the registry validates
    that.  ``fields`` is a tuple of ``(name, value)`` pairs.
    """

    version: int
    scope_kind: str
    scope_id: str
    category: str
    fields: tuple[tuple[str, str], ...]

    def field_map(self) -> dict[str, str]:
        """Return the fields as a dict.

        Raises:
            KeyFormatError: if a field name repeats (a repeated field is
                never valid, regardless of the registered spec).
        """
        result: dict[str, str] = {}
        for name, value in self.fields:
            if name in result:
                raise KeyFormatError(
                    f"repeated field {name!r} in canonical key"
                )
            result[name] = value
        return result


# ── Segment encoding ──────────────────────────────────────────────────────


def encode_segment(value: str) -> str:
    """Percent-encode one variable segment of a canonical key.

    Only RFC 3986 unreserved characters survive literal; every other
    Unicode code point is UTF-8 encoded and emitted as uppercase ``%XX``.

    Args:
        value: The logical segment value (may be empty).

    Returns:
        The encoded segment.
    """
    out: list[str] = []
    for byte in value.encode("utf-8"):
        ch = chr(byte)
        if ch in _UNRESERVED:
            out.append(ch)
        else:
            out.append(f"%{byte:02X}")
    return "".join(out)

def decode_segment(value: str) -> str:
    """Strictly decode one percent-encoded segment.

    Rejects:
    - a bare ``%`` not followed by two hex digits;
    - lowercase hex digits (``%2f``) — the canonical form is uppercase;
    - percent-encoded unreserved characters (``%41`` for ``A``), which
      would re-encode differently.

    Args:
        value: The encoded segment.

    Returns:
        The decoded logical value.

    Raises:
        KeyFormatError: if the segment is not canonically encoded.
    """
    raw = bytearray()
    i = 0
    n = len(value)
    while i < n:
        ch = value[i]
        if ch != "%":
            raw.extend(ch.encode("utf-8"))
            i += 1
            continue
        if i + 3 > n:
            raise KeyFormatError(
                f"truncated percent escape at offset {i} in segment {value!r}"
            )
        hex_digits = value[i + 1 : i + 3]
        if any(d not in _HEX for d in hex_digits):
            raise KeyFormatError(
                f"malformed percent escape '%{hex_digits}' in segment {value!r}"
            )
        byte_val = int(hex_digits, 16)
        decoded = chr(byte_val)
        if decoded in _UNRESERVED:
            raise KeyFormatError(
                f"non-canonical percent escape '%{hex_digits}' encodes the "
                f"unreserved character {decoded!r}; write it literally"
            )
        raw.append(byte_val)
        i += 3
    return bytes(raw).decode("utf-8")


# ── Key assembly / parsing ────────────────────────────────────────────────


def encode_key(
    scope_kind: str,
    scope_id: str,
    category: str,
    fields: list[tuple[str, str]] | tuple[tuple[str, str], ...],
) -> str:
    """Assemble a canonical ``cg:v1`` key from logical values.

    Args:
        scope_kind: ``project``, ``repository``, or ``ecosystem``.
        scope_id: The scope identifier (e.g. ``codegraph-suite/codegraph``).
        category: The stable artifact category (e.g. ``class``).
        fields: ``(name, value)`` pairs in registered order.

    Returns:
        The canonical key string.
    """
    encoded = [
        encode_segment(scope_kind),
        encode_segment(scope_id),
        encode_segment(category),
    ]
    for name, value in fields:
        encoded.append(f"{encode_segment(name)}={encode_segment(value)}")
    return VERSION_PREFIX + ":".join(encoded)


def parse_key(key: str) -> ParsedKey:
    """Strictly parse a canonical key into its grammar-level parts.

    The version is pinned by the prefix; scope kinds/categories and field
    order/count are validated by the registry, not here.

    Args:
        key: A ``cg:v1`` canonical key string.

    Returns:
        A :class:`ParsedKey`.

    Raises:
        KeyFormatError: on any grammar or canonicality violation.
    """
    if not isinstance(key, str):
        raise KeyFormatError(f"canonical key must be a str, got {type(key).__name__}")
    if not key.startswith(VERSION_PREFIX):
        raise KeyFormatError(
            f"canonical key must start with {VERSION_PREFIX!r}: {key[:40]!r}"
        )
    tail = key[len(VERSION_PREFIX) :]
    if not tail:
        raise KeyFormatError("canonical key is missing scope/category segments")

    segments = tail.split(":")
    if len(segments) < 3:
        raise KeyFormatError(
            f"canonical key needs scope-kind, scope-id, and category: {key!r}"
        )

    scope_kind = decode_segment(segments[0])
    scope_id = decode_segment(segments[1])
    category = decode_segment(segments[2])

    fields: list[tuple[str, str]] = []
    for seg in segments[3:]:
        if "=" not in seg:
            raise KeyFormatError(
                f"field segment missing '=': {seg!r} in key {key!r}"
            )
        name, value = seg.split("=", 1)
        fields.append((decode_segment(name), decode_segment(value)))

    parsed = ParsedKey(
        version=1,
        scope_kind=scope_kind,
        scope_id=scope_id,
        category=category,
        fields=tuple(fields),
    )

    # Canonicality is a *property of the whole key*, not just of each
    # segment: re-encoding the parsed form must reproduce the input
    # byte-for-byte.  This catches segment-boundary tricks (e.g. an
    # encoded ':' smuggled in as a literal separator).
    rebuilt = encode_key(
        parsed.scope_kind, parsed.scope_id, parsed.category, list(parsed.fields)
    )
    if rebuilt != key:
        raise KeyFormatError(
            f"non-canonical key {key!r}: re-encoding produces {rebuilt!r}"
        )

    return parsed
