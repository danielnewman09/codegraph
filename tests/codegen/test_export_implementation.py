"""Unit tests for the implementation export (Tier-4).

Pins the machinery that carries implementation data from the index to
codegen so the round-trip can regenerate out-of-line / inline
definitions from the graph (not from raw file text):

- ``export_implementation`` on ``LayerGraph.serialize`` — MethodNode
  ``body`` is opt-in (dropped by default, included when the flag is
  set); ``body_file`` routes a body to its ``.cpp``/``.hpp``;
- INCLUDES edges carry the include spelling as relationship metadata
  (``edge_attrs``) through deserialize → serialize and the sqlite
  backend;
- codegen renders body-carrying methods into the source file their
  ``body_file`` names (semantic reconstruction, not verbatim passthrough).
"""

from __future__ import annotations

import json
import tempfile

from codegraph.codegen import generate
from codegraph.codegen.planner import FilePlanner
from codegraph.graph import LayerGraph


def _method(
    name: str,
    qname: str,
    *,
    body: str = "",
    body_file: str = "",
    line_number: int = 0,
    type_signature: str = "void",
    argsstring: str = "()",
    uid: str | None = None,
    body_start: int = 0,
) -> dict:
    data = {
        "type": "MethodNode", "name": name, "qualified_name": qname,
        "kind": "function", "type_signature": type_signature,
        "argsstring": argsstring, "definition": "", "visibility": "public",
        "source": "test", "tags": ["as-built"],
    }
    if body:
        data["body"] = body
    if body_file:
        data["body_file"] = body_file
    if line_number:
        data["line_number"] = line_number
    if body_start:
        data["body_start"] = body_start
    if uid:
        data["uid"] = uid
    return data


def _file(name: str, path: str, *, uid: str | None = None, edges=None) -> dict:
    data = {
        "type": "FileNode", "name": name, "qualified_name": path, "path": path,
        "kind": "file", "language": "cpp", "source": "test", "tags": ["as-built"],
    }
    if uid:
        data["uid"] = uid
    if edges:
        data["edges"] = edges
    return data


def _body_graph() -> LayerGraph:
    """A source file with one out-of-line method carrying a body."""
    cpp = _file("f.cpp", "src/f.cpp")
    method = _method(
        "f", "ns::C::f", body="int C::f() { return 1; }\n",
        body_file="src/f.cpp", type_signature="int", argsstring="()",
    )
    return LayerGraph.deserialize([cpp, method])


def _two_files_with_include(spelling: str = '"y.hpp"') -> LayerGraph:
    """Two FileNodes linked by an INCLUDES edge carrying the spelling."""
    y = _file("y.hpp", "include/y.hpp")
    gy = LayerGraph.deserialize([y])
    y_uid = next(iter(gy._all_entries())).node._uid_value()
    x = _file(
        "x.hpp", "include/x.hpp",
        edges=[{
            "relation_type": "INCLUDES", "target_uid": y_uid,
            "target_type": "FileNode", "include": spelling, "local": True,
        }],
    )
    return LayerGraph.deserialize([x, y])


class TestSerializeFlag:
    def test_default_export_strips_body(self):
        g = _body_graph()
        plain = g.serialize(fields="all")

        def walk(entries):
            for e in entries:
                yield e
                for c in e.get("composes", []):
                    yield from walk([c])

        methods = [e for e in walk(plain) if e["type"] == "MethodNode"]
        assert methods and all("body" not in m for m in methods)

    def test_export_implementation_includes_body(self):
        g = _body_graph()
        full = g.serialize(fields="all", export_implementation=True)

        def walk(entries):
            for e in entries:
                yield e
                for c in e.get("composes", []):
                    yield from walk([c])

        methods = [e for e in walk(full) if e["type"] == "MethodNode"]
        assert methods and any(m.get("body") == "int C::f() { return 1; }\n" for m in methods)

    def test_flag_is_opt_in_even_with_fields_all(self):
        """fields=\"all\" alone does not leak implementation data."""
        g = _body_graph()
        plain = g.serialize(fields="all")
        raw = json.dumps(plain)
        assert '"body"' not in raw

    def test_empty_body_not_exported(self):
        g = LayerGraph.deserialize([
            _file("f.cpp", "src/f.cpp"),
            _method("f", "ns::C::f", body_file="src/f.cpp"),
        ])
        raw = json.dumps(g.serialize(fields="all", export_implementation=True))
        assert '"body":' not in raw

    def test_body_file_is_routing_not_implementation(self):
        """body_file (a path) stays in the default export — it is routing
        metadata, not implementation text."""
        g = LayerGraph.deserialize([
            _file("f.cpp", "src/f.cpp"),
            _method("f", "ns::C::f", body_file="src/f.cpp"),
        ])
        plain = g.serialize(fields="all")
        raw = json.dumps(plain)
        assert "src/f.cpp" in raw  # the FileNode path and body_file both name it


class TestEdgeAttrs:
    def test_include_spelling_survives_deserialize_serialize(self):
        g = _two_files_with_include()
        out = g.serialize(fields="all", export_implementation=True)
        x = next(e for e in out if e["type"] == "FileNode" and e["path"] == "include/x.hpp")
        inc = [e for e in x["edges"] if e["relation_type"] == "INCLUDES"]
        assert inc and inc[0].get("include") == '"y.hpp"'
        assert inc[0].get("local") is True

    def test_edge_attrs_survive_sqlite_round_trip(self):
        from codegraph.backends import get_backend, set_backend
        from codegraph.backends.sqlite import SqliteBackend, SqliteConfig

        g = _two_files_with_include()
        db = tempfile.mktemp(suffix=".sqlite3")
        set_backend(SqliteBackend(SqliteConfig(path=db)))
        g.to_backend(get_backend())
        g2 = LayerGraph.from_backend(get_backend(), "as-built")

        x = next(
            e for e in g2._all_entries()
            if getattr(e.node, "path", "") == "include/x.hpp"
        )
        attrs = [v for (rt, _k), v in x.edge_attrs.items() if rt == "INCLUDES"]
        assert attrs and attrs[0].get("include") == '"y.hpp"'

    def test_edge_attrs_serialize_after_backend_load(self):
        from codegraph.backends import get_backend, set_backend
        from codegraph.backends.sqlite import SqliteBackend, SqliteConfig

        g = _two_files_with_include()
        db = tempfile.mktemp(suffix=".sqlite3")
        set_backend(SqliteBackend(SqliteConfig(path=db)))
        g.to_backend(get_backend())
        g2 = LayerGraph.from_backend(get_backend(), "as-built")
        out = g2.serialize(fields="all", export_implementation=True)
        x = next(e for e in out if e["type"] == "FileNode" and e["path"] == "include/x.hpp")
        inc = [e for e in x["edges"] if e["relation_type"] == "INCLUDES"]
        assert inc and inc[0].get("include") == '"y.hpp"'


class TestCodegenSemanticBodies:
    def test_body_renders_into_source_file(self):
        g = _body_graph()
        result = generate(g.serialize(fields="all", export_implementation=True))
        text = result.files["src/f.cpp"]
        assert "int C::f() { return 1; }" in text
        assert "TODO(codegen): implementation body" not in text

    def test_body_routes_to_its_body_file(self):
        """A body whose body_file names a different .cpp does not leak
        into the wrong source file."""
        g = LayerGraph.deserialize([
            _file("a.cpp", "src/a.cpp"),
            _file("b.cpp", "src/b.cpp"),
            _method("f", "ns::C::f", body="int C::f() { return 1; }\n",
                    body_file="src/a.cpp"),
        ])
        result = generate(g.serialize(fields="all", export_implementation=True))
        assert "int C::f() { return 1; }" in result.files["src/a.cpp"]
        assert "int C::f() { return 1; }" not in result.files["src/b.cpp"]

    def test_no_body_emits_nothing_in_source_file(self):
        """A body-less method is a declaration, not an out-of-line
        definition — the source file gets no body text for it."""
        g = LayerGraph.deserialize([
            _file("f.cpp", "src/f.cpp"),
            _method("f", "ns::C::f", body_file="src/f.cpp"),
        ])
        result = generate(g.serialize(fields="all", export_implementation=True))
        assert "C::f" not in result.files["src/f.cpp"]

    def test_bodies_ordered_by_source_line(self):
        """Implementation body_start wins over header declaration order."""
        g = LayerGraph.deserialize([
            _file("f.cpp", "src/f.cpp"),
            _method("b", "ns::C::b", body="void C::b() {}\n",
                    body_file="src/f.cpp", line_number=10, body_start=20),
            _method("a", "ns::C::a", body="void C::a() {}\n",
                    body_file="src/f.cpp", line_number=20, body_start=10),
        ])
        result = generate(g.serialize(fields="all", export_implementation=True))
        text = result.files["src/f.cpp"]
        assert text.index("C::a()") < text.index("C::b()")


class TestJsonRoundTrip:
    def test_impl_export_deserializes_cleanly(self):
        """A serialized impl export round-trips through deserialize with
        body intact."""
        g = _body_graph()
        data = g.serialize(fields="all", export_implementation=True)
        g2 = LayerGraph.deserialize(json.loads(json.dumps(data)))
        methods = [e for e in g2._all_entries() if type(e.node).__name__ == "MethodNode"]
        assert methods and getattr(methods[0].node, "body", "") == "int C::f() { return 1; }\n"
