"""Integration test: LayerGraph JSON → HTML → rendered PNG screenshot.

Loads serialised LayerGraph fixtures from ``tests/data/*.json``, exports each to
self-contained interactive Cytoscape.js HTML via ``export_html_from_json``, serves
it on a local HTTP server (CDN scripts are blocked from ``file://``), opens it in
a headless Playwright Chromium browser, and captures a PNG screenshot.

The test asserts that the rendered page:
 - contains no JavaScript errors,
 - shows a non-empty stats badge (``"N nodes · M edges"``),
 - and produces a screenshot above a minimum size threshold (no blank canvas).

Saves artefacts to ``unit_test_data/`` named after each fixture stem.

Requires Playwright and a Playwright browser (``playwright install chromium``).
No Neo4j connection is required — graphs are loaded from the JSON fixtures.
"""

import http.server
import json
import re
import socket
import socketserver
import threading
from pathlib import Path
from typing import Any

import pytest

DATA_DIR = Path(__file__).resolve().parent / "data"
FIXTURE_DIR = Path(__file__).resolve().parent.parent / "unit_test_data"

# ── Fixture JSON paths (parametrized) ──────────────────────────────────────

FIXTURE_PATHS = [
    pytest.param(DATA_DIR / "design_graph.json", id="design_graph"),
    pytest.param(DATA_DIR / "cpp-sqlite_export.json", id="cpp_sqlite"),
]


# ── Playwright availability ────────────────────────────────────────────────


def _playwright_installed() -> bool:
    """Check whether the ``playwright`` package can be imported."""
    try:
        import playwright  # noqa: F401
        return True
    except ImportError:
        return False


def _browser_available() -> bool:
    """Check whether Playwright + Chromium cache is present."""
    if not _playwright_installed():
        return False
    cache_dir = Path.home() / "Library" / "Caches" / "ms-playwright"
    if not cache_dir.is_dir():
        return False
    chromium_dirs = list(cache_dir.glob("chromium-*"))
    return len(chromium_dirs) > 0


# ── HTTP server helper ──────────────────────────────────────────────────────


def _find_free_port() -> int:
    """Find an available TCP port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


class ThreadingHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    """HTTP server that handles requests in separate threads."""
    daemon_threads = True


def _serve_directory(serve_dir: Path, port: int) -> ThreadingHTTPServer:
    """Start a multi-threaded SimpleHTTPRequestHandler in the background."""

    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(serve_dir), **kwargs)

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


# ── Shared helpers ──────────────────────────────────────────────────────────


def _render_and_assert(
    html_path: Path,
    tmp_path: Path,
    png_path: Path,
    *,
    size: str = "large",
    viewport: dict[str, int] | None = None,
    min_png_kb: int = 20,
) -> tuple[str, list[str], list[dict[str, Any]]]:
    """Serve *html_path* via HTTP, render in headless Chromium, and return
    the stats text, JS error messages, and console messages for assertions.

    The HTML file must already have been written by the caller.
    """
    if viewport is None:
        viewport = {"width": 1920, "height": 1080} if size == "large" else {"width": 800, "height": 600}

    port = _find_free_port()
    server = _serve_directory(tmp_path, port)
    try:
        url = f"http://127.0.0.1:{port}/{html_path.name}"

        from playwright.sync_api import sync_playwright

        js_errors: list[str] = []
        console_msgs: list[dict[str, Any]] = []

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport=viewport)
            page.on("pageerror", lambda err: js_errors.append(str(err)))
            page.on("console", lambda msg: console_msgs.append({"type": msg.type, "text": msg.text}))

            page.goto(url, wait_until="networkidle", timeout=30_000)
            page.wait_for_selector("#cy", timeout=15_000)
            page.wait_for_timeout(5_000)

            stats_text = page.evaluate("document.getElementById('stats').textContent").strip()

            page.screenshot(path=str(png_path), full_page=False)
            browser.close()
    finally:
        server.shutdown()

    # ── Assertions ──────────────────────────────────────────────────────

    # No JavaScript errors should have occurred during rendering
    assert len(js_errors) == 0, f"JavaScript errors: {js_errors}"

    # The stats badge must report nodes & edges (e.g. "9 nodes · 4 edges")
    stats_pattern = re.compile(r"(\d+)\s+nodes?\s*·\s*(\d+)\s+edges?")
    m = stats_pattern.match(stats_text)
    assert m is not None, f"Stats badge missing or malformed: {stats_text!r}"
    node_count = int(m.group(1))
    edge_count = int(m.group(2))

    assert node_count > 0, f"Graph has 0 visible nodes — rendering may be broken"
    assert edge_count > 0, f"Graph has 0 visible edges — rendering may be broken"

    # PNG screenshot must exist and be above the minimum size (not a blank canvas)
    assert png_path.exists(), f"PNG not written to {png_path}"
    png_kb = png_path.stat().st_size / 1024
    assert png_kb >= min_png_kb, (
        f"PNG screenshot too small ({png_kb:.0f} KB, min {min_png_kb} KB) — "
        f"likely a blank or empty canvas"
    )

    return stats_text, js_errors, console_msgs


# ── Integration tests ───────────────────────────────────────────────────────


@pytest.mark.browser
@pytest.mark.skipif(not _browser_available(), reason="Playwright + Chromium not available")
class TestHtmlScreenshot:
    """End-to-end: load a fixture JSON, export to HTML, render, screenshot,
    and assert the rendered graph is non-trivial."""

    @classmethod
    def setup_class(cls):
        FIXTURE_DIR.mkdir(parents=True, exist_ok=True)

    # codegraph:test-desc test_viz_integration.TestHtmlScreenshot.test_json_to_html_to_png
    # Verifies that the full pipeline — loading a serialised LayerGraph from JSON,
    # exporting to self-contained Cytoscape.js HTML, and rendering it in a headless
    # browser — produces a valid, non-empty PNG screenshot with visible nodes and edges.
    @pytest.mark.parametrize("fixture_path", FIXTURE_PATHS)
    def test_json_to_html_to_png(self, fixture_path: Path, tmp_path: Path):
        from codegraph.export.viz import export_html_from_json

        fixture_stem = fixture_path.stem

        # 1. Export HTML from the fixture JSON
        html_path = tmp_path / f"{fixture_stem}.html"
        export_html_from_json(
            str(fixture_path), str(html_path), title=fixture_stem, size="large"
        )
        assert html_path.exists()
        assert html_path.stat().st_size > 0

        # Basic HTML structure checks (before browser rendering)
        html = html_path.read_text(encoding="utf-8")
        # codegraph:test-desc test_viz_integration.TestHtmlScreenshot.test_json_to_html_to_png::post_0
        # Checks that the exported HTML begins with a DOCTYPE declaration,
        # confirming the output is a valid HTML document.
        assert "<!DOCTYPE html>" in html
        # codegraph:test-desc test_viz_integration.TestHtmlScreenshot.test_json_to_html_to_png::post_1
        # Checks that the HTML references Cytoscape.js, confirming the visualisation
        # library is properly included.
        assert "cytoscape" in html.lower()
        # codegraph:test-desc test_viz_integration.TestHtmlScreenshot.test_json_to_html_to_png::post_2
        # Checks that the HTML contains the graph container element with id="cy",
        # confirming the rendering target is present.
        assert 'id="cy"' in html

        # 2. Render in browser and assert meaningful graph content
        png_path = FIXTURE_DIR / f"{fixture_stem}_screenshot.png"
        stats_text, _js_errors, _console = _render_and_assert(
            html_path, tmp_path, png_path, size="large", min_png_kb=20,
        )
        # codegraph:test-desc test_viz_integration.TestHtmlScreenshot.test_json_to_html_to_png::post_3
        # Records the actual rendered stats for this fixture (node/edge counts vary
        # by fixture but must be non-zero).
        print(f"[{fixture_stem}] {stats_text}")


@pytest.mark.browser
@pytest.mark.skipif(not _browser_available(), reason="Playwright + Chromium not available")
class TestHtmlScreenshotSmall:
    """Small-size (compact) export with browser screenshot — parametrized
    over the same fixture files."""

    @classmethod
    def setup_class(cls):
        FIXTURE_DIR.mkdir(parents=True, exist_ok=True)

    # codegraph:test-desc test_viz_integration.TestHtmlScreenshotSmall.test_small_size_html_to_png
    # Verifies that the "small" layout size produces a valid, non-empty PNG screenshot
    # with visible nodes and edges, ensuring the compact rendering mode works correctly.
    @pytest.mark.parametrize("fixture_path", FIXTURE_PATHS)
    def test_small_size_html_to_png(self, fixture_path: Path, tmp_path: Path):
        from codegraph.export.viz import export_html_from_json

        fixture_stem = fixture_path.stem

        html_path = tmp_path / f"{fixture_stem}_small.html"
        export_html_from_json(
            str(fixture_path), str(html_path), title=f"{fixture_stem} (small)", size="small"
        )
        assert html_path.exists()

        png_path = FIXTURE_DIR / f"{fixture_stem}_small_screenshot.png"
        stats_text, _js_errors, _console = _render_and_assert(
            html_path, tmp_path, png_path, size="small",
            viewport={"width": 800, "height": 600},
            min_png_kb=15,
        )
        # codegraph:test-desc test_viz_integration.TestHtmlScreenshotSmall.test_small_size_html_to_png::post_0
        # Records the actual rendered stats for the small‑size rendering of this
        # fixture — node/edge counts vary but must be non‑zero.
        print(f"[{fixture_stem} small] {stats_text}")
