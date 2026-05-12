"""
PrecompressedStaticFiles — Accept-Encoding-aware static serving.

The Vite build (`vite-plugin-compression`) emits Brotli and gzip siblings
next to every raw JS/CSS asset in ``app/ui/assets/``:

    index-XYZ.js
    index-XYZ.js.br
    index-XYZ.js.gz

Starlette's stock ``StaticFiles`` ignores ``Accept-Encoding`` and always
serves the file at the exact path requested. This subclass adds
negotiation: when the client advertises ``br`` (or ``gzip``) and a
matching sibling exists on disk, it's served with the right
``Content-Encoding`` header and the *original* media-type — so the
browser transparently decompresses and parses the asset normally.

Falls back to the parent class's behavior when no compressed variant is
acceptable or present (so raw assets and ``index.html`` still work).
"""

from __future__ import annotations

import mimetypes
import stat as stat_mod

import anyio.to_thread
from starlette.datastructures import Headers
from starlette.responses import FileResponse, Response
from starlette.staticfiles import NotModifiedResponse, StaticFiles
from starlette.types import Scope

# Order matters: prefer Brotli when both are accepted (better ratio).
_ENCODINGS: tuple[tuple[str, str], ...] = (
    ("br", ".br"),
    ("gzip", ".gz"),
)


def _client_accepts(accept_encoding: str, encoding: str) -> bool:
    """Return True if ``Accept-Encoding`` allows ``encoding``.

    Recognizes ``;q=0`` as an explicit rejection. Does NOT treat ``*``
    as a wildcard accept — we only opt in when the encoding is named,
    because some clients send ``*`` while not actually supporting
    Brotli.
    """
    if not accept_encoding:
        return False
    for raw in accept_encoding.split(","):
        token, _, params = raw.strip().lower().partition(";")
        if token != encoding:
            continue
        q = 1.0
        for param in params.split(";"):
            param = param.strip()
            if param.startswith("q="):
                try:
                    q = float(param[2:])
                except ValueError:
                    q = 0.0
                break
        return q > 0
    return False


class PrecompressedStaticFiles(StaticFiles):
    """Serve ``.br``/``.gz`` siblings when the client opts in.

    On a GET/HEAD for ``foo.js``, if the client's ``Accept-Encoding`` lists
    ``br`` and ``foo.js.br`` exists, that file is returned with:
      - ``Content-Encoding: br``
      - ``Content-Type`` of ``foo.js`` (NOT of ``foo.js.br``)
      - ``Vary: Accept-Encoding`` (so caches/CDNs don't mix variants)

    Same for gzip via ``.gz``. If no compressed variant is acceptable or
    on disk, falls back to the parent's behavior (raw file or 404).
    """

    async def get_response(self, path: str, scope: Scope) -> Response:
        method = scope.get("method", "GET")
        if method not in ("GET", "HEAD"):
            return await super().get_response(path, scope)

        accept_encoding = Headers(scope=scope).get("accept-encoding", "")

        for encoding, ext in _ENCODINGS:
            if not _client_accepts(accept_encoding, encoding):
                continue
            candidate = path + ext
            try:
                full_path, stat_result = await anyio.to_thread.run_sync(
                    self.lookup_path, candidate
                )
            except (PermissionError, OSError):
                # Don't bail on the whole request — try the next encoding,
                # and ultimately fall back to the raw file.
                continue

            if stat_result is None or not stat_mod.S_ISREG(stat_result.st_mode):
                continue

            # Mime type from the ORIGINAL path so the browser decodes correctly.
            # mimetypes.guess_type('foo.js.br') returns ('application/javascript',
            # 'br') — we want only the type, never the encoding-derived guess.
            media_type, _ = mimetypes.guess_type(path)
            if media_type is None:
                media_type = "application/octet-stream"

            response = FileResponse(
                full_path,
                stat_result=stat_result,
                media_type=media_type,
            )
            response.headers["content-encoding"] = encoding

            existing_vary = response.headers.get("vary", "")
            if "accept-encoding" not in existing_vary.lower():
                response.headers["vary"] = (
                    f"{existing_vary}, Accept-Encoding"
                    if existing_vary
                    else "Accept-Encoding"
                )

            # Honor If-None-Match / If-Modified-Since against the compressed
            # variant's mtime/etag (so cache revalidation works correctly).
            request_headers = Headers(scope=scope)
            if self.is_not_modified(response.headers, request_headers):
                return NotModifiedResponse(response.headers)
            return response

        # No acceptable compressed variant — fall through to raw.
        return await super().get_response(path, scope)
