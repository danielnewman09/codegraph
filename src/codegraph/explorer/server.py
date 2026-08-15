"""Codegraph Explorer — stdlib HTTP server (static SPA + JSON API).

Run::

    python -m codegraph.explorer.server --source fixture:tests/pipelines/unit_test_data/design_layergraph.json
    # open http://localhost:8765

API (all JSON except static files):

    GET /api/meta
    GET /api/namespaces?q=<search>
    GET /api/node/<qname>/children
    GET /api/node/<qname>/scope        # {puml, svg} — svg rendered via
                                       #   plantuml CLI and cached
    GET /api/node/<qname>/coverage

Sources: ``fixture:<path-to-layer-graph-json>`` (a serialized
LayerGraph) is the demo source; a live-backend source is a later step.
"""

from __future__ import annotations

import argparse
import functools
import json
import shutil
import subprocess
import sys
import tempfile
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from codegraph.explorer.api import GraphSource, LayerGraphSource

_STATIC_DIR = Path(__file__).resolve().parent / "static"


def load_source(spec: str) -> GraphSource:
    """Parse a ``--source`` spec into a GraphSource.

    Specs: ``fixture:<path>`` (serialized LayerGraph JSON) or
    ``sqlite:<path>:<tag>`` (a live codegraph sqlite database, loaded
    via the sqlite backend — e.g. a doxygen-index output).
    """
    kind, _, value = spec.partition(":")
    if kind == "fixture":
        from codegraph.graph import LayerGraph
        with open(value, encoding="utf-8") as f:
            graph = LayerGraph.deserialize(json.load(f))
        return LayerGraphSource(graph, source_name=Path(value).name)
    if kind == "sqlite":
        path, _, tag = value.rpartition(":")
        if not path or not tag:
            raise ValueError(
                f"sqlite source needs sqlite:<path>:<tag>, got {spec!r}"
            )
        from codegraph.backends.sqlite import SqliteBackend, SqliteConfig
        from codegraph.graph import LayerGraph
        backend = SqliteBackend(SqliteConfig(path=path))
        backend.initialize(SqliteConfig(path=path))
        try:
            graph = LayerGraph.from_backend(backend, tag)
        finally:
            backend.close()
        return LayerGraphSource(
            graph, source_name=f"{Path(path).name}:{tag}"
        )
    raise ValueError(
        f"unknown source {spec!r} "
        "(expected fixture:<path> or sqlite:<path>:<tag>)"
    )


class _Renderer:
    """Cached plantuml → svg rendering (class-scoped views)."""

    def __init__(self) -> None:
        self._cache: dict[str, str] = {}
        self._exe = shutil.which("plantuml")

    def render(self, puml: str) -> str | None:
        """Return SVG text for *puml*, or None when plantuml is
        unavailable or fails."""
        import hashlib
        key = hashlib.sha1(puml.encode()).hexdigest()
        if key in self._cache:
            return self._cache[key]
        if self._exe is None:
            return None
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "view.puml"
            src.write_text(puml, encoding="utf-8")
            subprocess.run(
                [self._exe, "-tsvg", "-o", tmp, str(src)],
                check=False, capture_output=True, timeout=120,
            )
            svg_path = Path(tmp) / "view.svg"
            if not svg_path.exists():
                return None
            svg = svg_path.read_text(encoding="utf-8")
        self._cache[key] = svg
        return svg


class ExplorerHandler(BaseHTTPRequestHandler):
    server_version = "CodegraphExplorer/0.1"

    def __init__(self, *args, source: GraphSource, renderer: _Renderer,
                 **kwargs):
        self.source = source
        self.renderer = renderer
        super().__init__(*args, **kwargs)

    # ---- plumbing -----------------------------------------------------

    def _send(self, status: int, body: bytes, ctype: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, payload: dict, status: int = 200) -> None:
        self._send(status, json.dumps(payload).encode(), "application/json")

    def _static(self, rel: str) -> None:
        rel = rel.lstrip("/")
        # path traversal guard
        target = (_STATIC_DIR / rel).resolve()
        if not target.is_relative_to(_STATIC_DIR.resolve()) or not target.is_file():
            self._send(404, b"not found", "text/plain")
            return
        ctype = {
            ".html": "text/html; charset=utf-8",
            ".js": "text/javascript; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".svg": "image/svg+xml",
        }.get(target.suffix, "application/octet-stream")
        self._send(200, target.read_bytes(), ctype)

    def log_message(self, fmt: str, *args) -> None:  # quieter logging
        sys.stderr.write("[explorer] %s\n" % (fmt % args))

    # ---- routing ------------------------------------------------------

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        if path == "/" or path == "/index.html":
            self._static("index.html")
            return
        if path.startswith("/static/"):
            self._static(path[len("/static/"):])
            return
        if path == "/api/meta":
            self._json(self.source.meta())
            return
        if path == "/api/namespaces":
            q = (query.get("q") or [""])[0]
            self._json({"namespaces": self.source.namespaces(q)})
            return
        node_path = "/api/node/"
        if path.startswith(node_path):
            rest = path[len(node_path):]
            # <qname>/children | <qname>/scope | <qname>/coverage
            qname, _, action = rest.rpartition("/")
            qname = urllib.parse.unquote(qname)
            if not qname or action not in ("children", "scope", "coverage"):
                self._json({"error": f"bad node path {path!r}"}, 400)
                return
            if action == "children":
                self._json(self.source.children(qname))
                return
            if action == "scope":
                result = self.source.scope(qname)
                if result.get("puml"):
                    result["svg"] = self.renderer.render(result["puml"])
                self._json(result)
                return
            if action == "coverage":
                self._json(self.source.coverage(qname))
                return
        self._json({"error": f"not found: {path}"}, 404)


def make_handler(source: GraphSource):
    renderer = _Renderer()
    return functools.partial(
        ExplorerHandler, source=source, renderer=renderer
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="codegraph-explorer",
        description="Interactive namespace → class → requirements/tests browser.",
    )
    parser.add_argument(
        "--source", required=True,
        help="Graph source: fixture:<path-to-layer-graph-json>",
    )
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args(argv)

    source = load_source(args.source)
    handler = make_handler(source)
    httpd = ThreadingHTTPServer((args.host, args.port), handler)
    print(f"Codegraph Explorer: http://{args.host}:{args.port}")
    print(f"  source: {args.source}")
    print("  Ctrl-C to stop")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nbye")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
