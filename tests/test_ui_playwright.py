"""Browser tests for the local viewer.

These need Playwright and a browser binary, so they skip cleanly when it is
not installed — the core suite stays dependency-free and offline:

    pip install playwright && playwright install chromium
    pytest tests/test_ui_playwright.py -q

Two of these are regressions for bugs that only a browser could have caught:
the drop bars rendered as empty rails (track and fill were inline spans,
which ignore height and percentage width), and a run's own run/ and build/
subdirectories were listed as separate builds because each carries its own
events.jsonl.
"""

from __future__ import annotations

import socket
import threading
import time

import pytest

pytest.importorskip("playwright", reason="playwright not installed")
from playwright.sync_api import ConsoleMessage, sync_playwright  # noqa: E402

import factory  # noqa: E402
import ui as ui_mod  # noqa: E402


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    """A real build of the bundled example corpus."""
    out = tmp_path_factory.mktemp("uiruns") / "example-build"
    rc = factory.main([
        "pipeline", "--registry", "examples/registry.json", "--out", str(out),
        "--sample-every", "1", "--eval-set", "examples/eval-set.jsonl",
        "--toxicity-lexicon-dir", "examples/lexicon", "--allow-refusals",
    ])
    assert rc == 0
    return out.parent


@pytest.fixture(scope="module")
def server(built):
    from http.server import ThreadingHTTPServer

    ui_mod.Handler.root = str(built)
    port = _free_port()
    httpd = ThreadingHTTPServer(("127.0.0.1", port), ui_mod.Handler)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    time.sleep(0.2)
    yield f"http://127.0.0.1:{port}"
    httpd.shutdown()
    httpd.server_close()


@pytest.fixture(scope="module")
def page_ctx():
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        yield browser
        browser.close()


@pytest.fixture
def page(page_ctx, server):
    ctx = page_ctx.new_context(viewport={"width": 1440, "height": 1000})
    p = ctx.new_page()
    errors: list[str] = []
    p.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    p.on("pageerror", lambda e: errors.append(str(e)))
    p.goto(server, wait_until="networkidle")
    p.wait_for_selector(".runitem", timeout=5000)
    p.wait_for_selector(".receipt", timeout=5000)
    p._shuddhi_errors = errors
    yield p
    ctx.close()


def test_page_loads_without_console_errors(page):
    assert "Shuddhi" in page.title()
    assert page._shuddhi_errors == [], f"console errors: {page._shuddhi_errors}"


def test_exactly_one_run_is_listed(page):
    """Regression: run/ and build/ each carry an events.jsonl and were being
    listed as separate builds."""
    items = page.locator(".runitem")
    assert items.count() == 1, [items.nth(i).inner_text() for i in range(items.count())]
    assert "example-build" in items.first.inner_text()


def test_all_three_receipts_are_shown_and_are_hashes(page):
    receipts = page.locator(".receipt")
    assert receipts.count() == 3
    labels = [receipts.nth(i).locator(".k").inner_text().lower() for i in range(3)]
    assert labels == ["corpus build hash", "filter config sha", "filtered build hash"]
    for i in range(3):
        code = receipts.nth(i).locator("code").inner_text().strip()
        assert len(code) == 64 and all(c in "0123456789abcdef" for c in code), code


def test_receipt_matches_the_manifest_on_disk(page, built):
    import json

    manifest = json.loads((built / "example-build" / "build" / "BUILD-MANIFEST.json").read_text())
    shown = page.locator(".receipt").nth(2).locator("code").inner_text().strip()
    assert shown == manifest["filtered_build_hash"]


def test_copy_buttons_exist_for_every_receipt(page):
    assert page.locator(".receipt .copy").count() == 3


def test_corpus_tiles_match_the_manifest(page, built):
    import json

    corpus = json.loads((built / "example-build" / "run" / "MANIFEST.json").read_text())
    tiles = page.locator(".tile")
    texts = [tiles.nth(i).inner_text() for i in range(tiles.count())]
    joined = " ".join(texts)
    assert f"{corpus['full_pass']['total_docs']:,}" in joined
    assert "documents" in joined and "unique" in joined
    assert "0.00 GB" not in joined, "small corpora must not render as 0.00 GB"


def test_drop_bars_actually_render(page):
    """Regression: .track/.fill were inline spans, so every bar was an empty
    rail — the numbers were right and the chart showed nothing."""
    fills = page.locator(".bar .fill")
    assert fills.count() > 0, "no drop bars rendered"
    widths = []
    for i in range(fills.count()):
        box = fills.nth(i).bounding_box()
        assert box is not None, "a bar fill has no layout box"
        widths.append(box["width"])
        assert box["height"] >= 4, f"bar {i} has no height: {box}"
    assert max(widths) > 40, f"bar fills are collapsed: {widths}"


def test_datasets_table_lists_the_shards(page):
    rows = page.locator("table tbody tr")
    assert rows.count() >= 2
    body = page.locator("table").inner_text()
    assert "sample_eng" in body and "sample_hin" in body
    assert "CC0-1.0" in body


def test_the_refused_shard_is_surfaced(page):
    """The provenance gate refusing customer data is the product's core
    claim; if the UI hides it the UI is lying by omission."""
    text = page.locator("main").inner_text()
    assert "customer_export" in text
    assert "never training" in text.lower() or "refused" in text.lower()


def test_downloads_are_offered_and_resolve(page, server):
    links = page.locator("a.dl")
    assert links.count() >= 2
    for i in range(links.count()):
        href = links.nth(i).get_attribute("href")
        resp = page.request.get(server + href)
        assert resp.status == 200, f"{href} -> {resp.status}"
        assert len(resp.body()) > 0


def test_no_horizontal_overflow_on_a_narrow_viewport(page):
    page.set_viewport_size({"width": 900, "height": 900})
    page.wait_for_timeout(300)
    overflow = page.evaluate(
        "() => document.documentElement.scrollWidth - document.documentElement.clientWidth")
    assert overflow <= 1, f"page scrolls horizontally by {overflow}px"


def test_accessibility_basics(page):
    assert page.locator("html").get_attribute("lang") == "en"
    assert page.locator("h1").count() == 1
    # every control a keyboard user must reach is a real button or anchor
    assert page.locator(".runitem").first.evaluate("e => e.tagName") == "BUTTON"
    assert page.locator(".copy").first.evaluate("e => e.tagName") == "BUTTON"


def test_theme_matches_the_swaraj_console(page):
    bg = page.evaluate(
        "() => getComputedStyle(document.body).backgroundColor")
    assert bg == "rgb(4, 5, 13)", f"background drifted from the Swaraj palette: {bg}"


def test_selecting_a_run_keeps_it_selected(page):
    first = page.locator(".runitem").first
    first.click()
    page.wait_for_timeout(200)
    assert "sel" in (first.get_attribute("class") or "")
