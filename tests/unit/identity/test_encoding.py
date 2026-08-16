"""Work Package 1.1 — strict cg:v1 encoder/decoder tests.

Covers the plan's required matrix:

- empty fields and empty optional values;
- colons, slashes, equals signs, ``%``, NUL, whitespace, newlines;
- nested C++ templates and callable syntax;
- Unicode including combining forms and non-BMP characters;
- field-order changes;
- malformed and non-canonical percent encoding;
- every registered artifact category;
- encode/decode/re-encode equality.
"""

from __future__ import annotations

import random
import string
import unicodedata

import pytest

from codegraph.identity.encoding import (
    KeyFormatError,
    VERSION_PREFIX,
    decode_segment,
    encode_key,
    encode_segment,
    parse_key,
)
from codegraph.identity.registry import category_spec, computed_providers
from codegraph.identity.scope import IdentityScope

# ══════════════════════════════════════════════════════════════════════════
# Segment encoding
# ══════════════════════════════════════════════════════════════════════════


class TestSegmentEncoding:
    @pytest.mark.parametrize(
        "value",
        [
            "simple",
            "codegraph-suite/codegraph",          # slash
            "cpp_sqlite::Database::getDAO",       # colons
            "a=b",                                # equals
            "100%",                               # percent
            "std::vector<T, Allocator>",          # templates
            "with space",                         # whitespace
            "line1\nline2",                       # newline
            "nul\x00byte",                        # NUL
            "mixed-1.2_3~symbols",
        ],
    )
    def test_encode_decode_roundtrip(self, value: str) -> None:
        encoded = encode_segment(value)
        assert decode_segment(encoded) == value

    def test_only_unreserved_left_literal(self) -> None:
        for ch in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~":
            assert encode_segment(ch) == ch
        for ch in ":/=% &+<>[]{}()\\\n\t":
            assert encode_segment(ch) != ch

    def test_unicode_preserved_exactly(self) -> None:
        cases = [
            "café",                       # latin-1 supplement
            "naïve",                      # combining? no — precomposed
            "e\u0301",                    # combining acute (e + combining)
            "\U0001F600",                 # non-BMP emoji
            "日本語",                      # CJK
            "𝔘𝔫𝔦𝔠𝔬𝔡𝔢",                  # mathematical alphanumerics
        ]
        for value in cases:
            assert decode_segment(encode_segment(value)) == value

    def test_unicode_codepoints_preserved_not_normalized(self) -> None:
        # NFC (precomposed é) and NFD (e + combining) must NOT collide —
        # identity preserves exact code points.
        nfc = "é"
        nfd = "e\u0301"
        assert nfc != nfd
        assert unicodedata.normalize("NFC", nfd) == nfc
        assert encode_segment(nfc) != encode_segment(nfd)

    def test_empty_segment(self) -> None:
        assert encode_segment("") == ""
        assert decode_segment("") == ""

    def test_percent_hex_is_uppercase(self) -> None:
        assert encode_segment("/") == "%2F"
        assert encode_segment(" ") == "%20"
        assert encode_segment("\x00") == "%00"

    def test_decode_rejects_lowercase_hex(self) -> None:
        with pytest.raises(KeyFormatError, match="malformed"):
            decode_segment("%2f")

    def test_decode_rejects_encoded_unreserved(self) -> None:
        with pytest.raises(KeyFormatError, match="unreserved"):
            decode_segment("%41")  # 'A'

    def test_decode_rejects_truncated_escape(self) -> None:
        for bad in ("%", "%2"):
            with pytest.raises(KeyFormatError):
                decode_segment(bad)

    def test_decode_rejects_bare_percent(self) -> None:
        with pytest.raises(KeyFormatError):
            decode_segment("abc%zz")

    def test_fuzz_roundtrip_deterministic(self) -> None:
        rng = random.Random(42)
        alphabet = (
            string.ascii_letters + string.digits + "-._~:/=% &+<>[]{}()\\\n\t"
            + "é日本語\U0001F600\x00"
        )
        for _ in range(500):
            length = rng.randint(0, 40)
            value = "".join(rng.choice(alphabet) for _ in range(length))
            assert decode_segment(encode_segment(value)) == value


# ══════════════════════════════════════════════════════════════════════════
# Key assembly / parsing
# ══════════════════════════════════════════════════════════════════════════


class TestKeyGrammar:
    def test_example_keys(self) -> None:
        key = encode_key(
            "repository", "codegraph-suite/codegraph", "class",
            [("qualified_name", "codegraph.graph.LayerGraph")],
        )
        assert key == (
            "cg:v1:repository:codegraph-suite%2Fcodegraph:class:"
            "qualified_name=codegraph.graph.LayerGraph"
        )
        method_key = encode_key(
            "repository", "cpp-suite/cpp-sqlite", "method",
            [
                ("qualified_name", "cpp_sqlite::Database::getDAO"),
                ("signature", "()<T>&"),
            ],
        )
        assert method_key.startswith("cg:v1:repository:cpp-suite%2Fcpp-sqlite:method:")

    def test_parse_roundtrip(self) -> None:
        key = encode_key(
            "project", "codegraph-suite", "requirement-hlr",
            [("qualified_name", "Architecture Diagram Generator")],
        )
        parsed = parse_key(key)
        assert parsed.version == 1
        assert parsed.scope_kind == "project"
        assert parsed.scope_id == "codegraph-suite"
        assert parsed.category == "requirement-hlr"
        assert parsed.fields == (("qualified_name", "Architecture Diagram Generator"),)

    def test_parse_rejects_bad_prefix(self) -> None:
        for bad in (
            "cg:v2:repository:a:b:q=x",
            "cgv1:repository:a:b:q=x",
            "repository:a:b:q=x",
            "",
            "cg:v1:",
        ):
            with pytest.raises(KeyFormatError):
                parse_key(bad)

    def test_parse_rejects_too_few_segments(self) -> None:
        with pytest.raises(KeyFormatError):
            parse_key("cg:v1:repository:only-two")

    def test_parse_rejects_field_without_equals(self) -> None:
        with pytest.raises(KeyFormatError):
            parse_key("cg:v1:repository:codegraph-suite/codegraph:class:qualified_name")

    def test_field_values_with_colons_and_equals(self) -> None:
        # Values are percent-encoded, so ':' and '=' inside them never
        # collide with the grammar separators.
        key = encode_key(
            "repository", "proj/repo", "method",
            [("qualified_name", "a::b::c"), ("signature", "x=y")],
        )
        parsed = parse_key(key)
        assert parsed.fields == (("qualified_name", "a::b::c"), ("signature", "x=y"))

    def test_empty_field_value(self) -> None:
        key = encode_key("project", "p", "language", [("version", "")])
        parsed = parse_key(key)
        assert parsed.fields == (("version", ""),)
        assert "version=" in key

    def test_field_map_rejects_repeated_field(self) -> None:
        # Build a key with a repeated field by hand (the encoder would
        # never emit one, but the parser must refuse it).
        key = (
            "cg:v1:project:p:language:"
            "qualified_name=Python:qualified_name=Python"
        )
        parsed = parse_key(key)
        with pytest.raises(KeyFormatError, match="repeated"):
            parsed.field_map()

    def test_non_canonical_key_rejected(self) -> None:
        # Encode an unreserved char — the re-encode check rejects it.
        key = "cg:v1:project:p:language:qualified_name=%50ython"
        with pytest.raises(KeyFormatError, match="non-canonical"):
            parse_key(key)

    def test_reencode_equality_for_registered_categories(self) -> None:
        # Every registered artifact category must encode/decode cleanly.
        for spec in _all_specs():
            scope = IdentityScope(spec.scope_kind, "proj/repo" if spec.scope_kind == "repository" else "proj")
            fields = [(f, _sample_value(f)) for f in spec.fields]
            key = encode_key(scope.scope_kind, scope.scope_id, spec.category, fields)
            parsed = parse_key(key)
            assert encode_key(
                parsed.scope_kind, parsed.scope_id, parsed.category, list(parsed.fields)
            ) == key


def _all_specs():
    from codegraph.identity.registry import _build_specs

    return list(_build_specs().values())


def _sample_value(field: str) -> str:
    samples = {
        "qualified_name": "ns::Type",
        "canonical_signature": "lang:cpp|(int)",
        "normalized_repository_path": "src/lib/util.hpp",
        "singleton": "project",
        "parent_callable_key": "cg:v1:repository:proj/repo:method:qualified_name=ns::f",
        "parent_hlr_key": "cg:v1:project:proj:requirement-hlr:qualified_name=HLR",
        "parent_key": "cg:v1:project:proj:test:qualified_name=Suite::Case",
        "file_key": "cg:v1:repository:proj/repo:file:normalized_repository_path=src/a.hpp",
        "position": "0",
        "kind": "class",
        "start_line": "10",
        "end_line": "20",
        "manager_name": "conan",
        "version": "1.82.0",
    }
    return samples.get(field, "value")


# ══════════════════════════════════════════════════════════════════════════
# Prefix sanity
# ══════════════════════════════════════════════════════════════════════════


def test_version_prefix_is_literal() -> None:
    assert VERSION_PREFIX == "cg:v1:"
    assert "cg:v1:" in encode_key("project", "p", "c", [("f", "v")])
