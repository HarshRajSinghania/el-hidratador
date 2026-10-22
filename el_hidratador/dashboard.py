"""Local dashboard preview.

The dashboard is a local operator surface, not a public API. This adapter is
deliberately narrow:

* HTTP only — never HTTPS, never a remote host.
* Loopback only — `localhost`, `127.0.0.1`, and `::1`.
* No redirects are followed.
* At most 8 MiB is read.
* At most 10 seconds is spent.
* Credentials in the URL are refused outright.

None of these limits are advisory. They are enforced before the socket opens.
"""

from __future__ import annotations

import json
from typing import Any
from urllib import error as urlerror
from urllib import request as urlrequest
from urllib.parse import urlparse

from .errors import AdapterError, ValidationError

#: Hosts a preview may talk to.
ALLOWED_HOSTS = ("localhost", "127.0.0.1", "::1", "[::1]")

#: Maximum response size read from the dashboard.
MAX_BYTES = 8 * 1024 * 1024

#: Maximum time spent waiting for the dashboard.
TIMEOUT = 10


def validate_url(url: str) -> str:
    """Validate a dashboard URL against the local-only boundary."""
    text = str(url or "").strip()
    if not text:
        raise ValidationError("dashboard url must be nonempty")
    parsed = urlparse(text)
    if parsed.scheme != "http":
        raise ValidationError("dashboard url must use http on loopback")
    if parsed.username or parsed.password:
        raise ValidationError("dashboard url must not carry credentials")
    host = (parsed.hostname or "").lower()
    if host not in ALLOWED_HOSTS:
        raise ValidationError(f"dashboard host {host!r} is not loopback")
    return text


class _NoRedirect(urlrequest.HTTPRedirectHandler):
    """Refuse every redirect."""

    def redirect_request(
        self,
        req: Any,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> None:
        """Refuse every redirect instead of following it."""
        raise urlerror.HTTPError(req.full_url, code, "redirects are not allowed", headers, fp)


def fetch(url: str, timeout: int = TIMEOUT, max_bytes: int = MAX_BYTES) -> dict[str, Any]:
    """Fetch a dashboard payload under the local-only boundary."""
    target = validate_url(url)
    opener = urlrequest.build_opener(_NoRedirect)
    request = urlrequest.Request(target, headers={"Accept": "application/json"})
    try:
        with opener.open(request, timeout=timeout) as response:
            payload = response.read(max_bytes + 1)
            status = getattr(response, "status", 200)
            content_type = response.headers.get("Content-Type", "")
    except urlerror.HTTPError as exc:
        raise AdapterError(f"dashboard returned HTTP {exc.code}") from exc
    except urlerror.URLError as exc:
        raise AdapterError(f"dashboard unreachable: {exc.reason}") from exc
    except TimeoutError as exc:
        raise AdapterError("dashboard request timed out") from exc
    if len(payload) > max_bytes:
        raise AdapterError("dashboard response exceeded the 8 MiB limit")
    try:
        data = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AdapterError("dashboard response was not valid JSON") from exc
    return {"url": target, "status": status, "content_type": content_type, "data": data}


def preview(
    url: str,
    status: str = "planned",
    offset: int = 0,
    limit: int = 50,
    timeout: int = TIMEOUT,
) -> dict[str, Any]:
    """Fetch and normalize a dashboard window for operator review."""
    if not isinstance(offset, int) or offset < 0:
        raise ValidationError("offset must be a nonnegative integer")
    if not isinstance(limit, int) or limit <= 0:
        raise ValidationError("limit must be a positive integer")
    result = fetch(url, timeout=timeout)
    data = result["data"]
    if isinstance(data, dict):
        rows = data.get("items") or data.get("rows") or data.get("results") or []
    elif isinstance(data, list):
        rows = data
    else:
        rows = []
    window = rows[offset : offset + limit]
    return {
        "url": result["url"],
        "http_status": result["status"],
        "content_type": result["content_type"],
        "status_filter": status,
        "offset": offset,
        "limit": limit,
        "total": len(rows),
        "returned": len(window),
        "items": window,
        "note": "Preview reflects a local operator surface; it is not a source of truth.",
    }


def health(url: str, timeout: int = TIMEOUT) -> dict[str, Any]:
    """Check whether a local dashboard answers."""
    try:
        result = fetch(url, timeout=timeout)
    except AdapterError as exc:
        return {"url": url, "reachable": False, "error": str(exc)}
    return {
        "url": result["url"],
        "reachable": True,
        "http_status": result["status"],
        "content_type": result["content_type"],
    }
