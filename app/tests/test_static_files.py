"""
Tests for app/static_files.py — PrecompressedStaticFiles.

Verifies the Accept-Encoding negotiation: the right variant is served,
with the right Content-Type and Content-Encoding, and falls back
correctly when the client doesn't opt in or no compressed variant
exists.
"""
from __future__ import annotations

import asyncio
import gzip
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from starlette.applications import Starlette

from app.static_files import PrecompressedStaticFiles, _client_accepts


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def static_root(tmp_path: Path) -> Path:
    """Build a tiny ``ui/`` lookalike with raw + pre-compressed siblings.

    Layout::

        <tmp>/index.html                      ("RAW INDEX")
        <tmp>/assets/app.js                   ("RAW JS")
        <tmp>/assets/app.js.br                (compressed-ish placeholder)
        <tmp>/assets/app.js.gz                (real gzip of RAW JS)
        <tmp>/assets/styles.css               ("RAW CSS")
        <tmp>/assets/styles.css.br            (placeholder)
        <tmp>/assets/bare.txt                 ("RAW BARE", no siblings)
        <tmp>/assets/only-gz.js               ("ONLY GZ JS")
        <tmp>/assets/only-gz.js.gz            (gzip only, no .br)

    Brotli payloads are placeholders (this test doesn't decompress them);
    we only assert the response headers + body bytes match the file on
    disk. The gzip payload is real because some tests round-trip it.
    """
    root = tmp_path
    assets = root / "assets"
    assets.mkdir()

    (root / "index.html").write_bytes(b"RAW INDEX")

    (assets / "app.js").write_bytes(b"RAW JS")
    (assets / "app.js.br").write_bytes(b"BR-COMPRESSED-PLACEHOLDER")
    (assets / "app.js.gz").write_bytes(gzip.compress(b"RAW JS"))

    (assets / "styles.css").write_bytes(b"RAW CSS")
    (assets / "styles.css.br").write_bytes(b"BR-CSS-PLACEHOLDER")

    (assets / "bare.txt").write_bytes(b"RAW BARE")

    (assets / "only-gz.js").write_bytes(b"ONLY GZ JS")
    (assets / "only-gz.js.gz").write_bytes(gzip.compress(b"ONLY GZ JS"))

    return root


@pytest.fixture
def app_client(static_root: Path):
    """Build a Starlette app that mounts ``PrecompressedStaticFiles`` and
    return an httpx AsyncClient wired to it via ASGITransport.

    Following the same pattern as conftest.py (run loop manually) so the
    test functions stay synchronous.
    """
    app = Starlette()
    app.mount(
        "/",
        PrecompressedStaticFiles(directory=str(static_root), html=True),
        name="ui",
    )

    transport = ASGITransport(app=app)
    loop = asyncio.new_event_loop()
    try:
        client = loop.run_until_complete(
            AsyncClient(transport=transport, base_url="http://test").__aenter__()
        )
        yield client, loop
    finally:
        loop.run_until_complete(client.__aexit__(None, None, None))
        loop.close()


def _get(app_client, path: str, accept_encoding: str | None = None):
    """Issue a GET, forcing the Accept-Encoding header.

    Pass ``accept_encoding=None`` to send ``identity`` (no compression
    accepted). Without this override, httpx auto-sets
    ``Accept-Encoding: gzip, deflate, br`` on every request, which
    would make it impossible to test the "client doesn't accept
    compression" path.

    Note: httpx automatically decompresses ``gzip``/``deflate``
    response bodies if the server set ``Content-Encoding`` accordingly,
    so tests comparing bodies after gzip negotiation see the *decoded*
    payload. Brotli decoding requires the ``brotli`` package which is
    not in our dependencies — so brotli responses come back as raw
    bytes (the on-disk ``.br`` payload).
    """
    client, loop = app_client
    headers = {"Accept-Encoding": accept_encoding if accept_encoding is not None else "identity"}
    return loop.run_until_complete(client.get(path, headers=headers))


# ---------------------------------------------------------------------------
# _client_accepts unit tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "header, encoding, expected",
    [
        ("br, gzip", "br", True),
        ("br, gzip", "gzip", True),
        ("gzip", "br", False),
        ("", "br", False),
        ("identity", "br", False),
        ("br;q=0", "br", False),  # explicit rejection
        ("br;q=0.0", "br", False),
        ("br;q=0.5", "br", True),  # any positive q accepts
        ("BR, GZIP", "br", True),  # case-insensitive
        ("gzip;q=0.5, br;q=0.9", "br", True),
        # Wildcard is intentionally NOT honored — we only opt in on named tokens.
        ("*", "br", False),
        ("deflate", "br", False),
    ],
)
def test_client_accepts(header, encoding, expected):
    assert _client_accepts(header, encoding) is expected


# ---------------------------------------------------------------------------
# Negotiation tests
# ---------------------------------------------------------------------------


def test_no_accept_encoding_serves_raw(app_client):
    resp = _get(app_client, "/assets/app.js")
    assert resp.status_code == 200
    assert resp.content == b"RAW JS"
    assert "content-encoding" not in {k.lower() for k in resp.headers}
    assert resp.headers["content-type"].startswith(
        ("application/javascript", "text/javascript")
    )


def test_brotli_preferred_when_both_accepted(app_client):
    resp = _get(app_client, "/assets/app.js", accept_encoding="br, gzip")
    assert resp.status_code == 200
    assert resp.content == b"BR-COMPRESSED-PLACEHOLDER"
    assert resp.headers["content-encoding"] == "br"
    # Content-Type is the ORIGINAL js type, not the .br
    assert resp.headers["content-type"].startswith(
        ("application/javascript", "text/javascript")
    )
    assert "accept-encoding" in resp.headers["vary"].lower()


def test_gzip_when_only_gzip_accepted(app_client):
    resp = _get(app_client, "/assets/app.js", accept_encoding="gzip")
    assert resp.status_code == 200
    # httpx auto-decompresses gzip — the body is the decoded payload.
    assert resp.content == b"RAW JS"
    assert resp.headers["content-encoding"] == "gzip"
    assert resp.headers["content-type"].startswith(
        ("application/javascript", "text/javascript")
    )
    assert "accept-encoding" in resp.headers["vary"].lower()


def test_br_q0_falls_back_to_gzip(app_client):
    """``br;q=0`` is an explicit rejection — should serve gzip instead."""
    resp = _get(app_client, "/assets/app.js", accept_encoding="gzip, br;q=0")
    assert resp.status_code == 200
    assert resp.headers["content-encoding"] == "gzip"


def test_css_brotli_negotiation(app_client):
    """Verify CSS gets the right Content-Type when served compressed."""
    resp = _get(app_client, "/assets/styles.css", accept_encoding="br")
    assert resp.status_code == 200
    assert resp.content == b"BR-CSS-PLACEHOLDER"
    assert resp.headers["content-encoding"] == "br"
    assert resp.headers["content-type"].startswith("text/css")


def test_falls_back_to_raw_when_no_compressed_variant(app_client):
    """``bare.txt`` has no .br/.gz — should serve raw even with Accept-Encoding."""
    resp = _get(app_client, "/assets/bare.txt", accept_encoding="br, gzip")
    assert resp.status_code == 200
    assert resp.content == b"RAW BARE"
    assert "content-encoding" not in {k.lower() for k in resp.headers}


def test_uses_gzip_when_br_missing_but_gzip_present(app_client):
    """``only-gz.js`` has .gz but no .br — Brotli-aware client gets gzip."""
    resp = _get(app_client, "/assets/only-gz.js", accept_encoding="br, gzip")
    assert resp.status_code == 200
    assert resp.headers["content-encoding"] == "gzip"
    # httpx auto-decompresses gzip.
    assert resp.content == b"ONLY GZ JS"


def test_404_for_nonexistent(app_client):
    resp = _get(app_client, "/assets/does-not-exist.js", accept_encoding="br, gzip")
    assert resp.status_code == 404


def test_html_root_still_works(app_client):
    """index.html (no .br/.gz) should still be served via parent fallback."""
    resp = _get(app_client, "/", accept_encoding="br, gzip")
    assert resp.status_code == 200
    assert resp.content == b"RAW INDEX"
    assert "content-encoding" not in {k.lower() for k in resp.headers}


def test_head_request_serves_compressed_headers(app_client):
    """HEAD should expose the same Content-Encoding/Type as GET."""
    client, loop = app_client
    resp = loop.run_until_complete(
        client.head("/assets/app.js", headers={"Accept-Encoding": "br"})
    )
    assert resp.status_code == 200
    assert resp.headers["content-encoding"] == "br"
    assert resp.headers["content-type"].startswith(
        ("application/javascript", "text/javascript")
    )


def test_vary_set_on_compressed_response(app_client):
    """Caches/CDNs need Vary: Accept-Encoding so they don't mix variants."""
    resp = _get(app_client, "/assets/app.js", accept_encoding="br")
    assert "accept-encoding" in resp.headers.get("vary", "").lower()
