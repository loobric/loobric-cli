# MIT License
# Copyright (c) 2025 sliptonic
# SPDX-License-Identifier: MIT
"""HTTP transport and session state for the Loobric client. Stdlib only, so the
package can be vendored or run in constrained interpreters (e.g. FreeCAD)."""
import http.client
import json
import sys
import urllib.parse
from pathlib import Path
from typing import Any, Dict, Optional

from loobric.errors import (
    AuthRequired, ConnectionFailed, HTTPError, NotFound, LoobricClientError, _http_error,
)

# Module-level session/auth state, set by the CLI. A Client carries its own and
# overrides these per call.
SESSION_COOKIE: Optional[str] = None
API_KEY: Optional[str] = None
BASE_URL: str = ""
SESSION_DIR = Path.home() / ".loobric"
SESSION_FILE = SESSION_DIR / "session.json"


def load_session():
    """Load session cookie and base URL from file if it exists.
    
    Returns:
        dict: Session data including base_url, session_cookie, and email (if available)
    """
    global SESSION_COOKIE, BASE_URL
    if SESSION_FILE.exists():
        try:
            with open(SESSION_FILE, 'r') as f:
                data = json.load(f)
                # If BASE_URL is not set, use the one from session
                if not BASE_URL and data.get('base_url'):
                    BASE_URL = data.get('base_url')
                # Load session cookie if base URLs match
                if data.get('base_url') == BASE_URL:
                    SESSION_COOKIE = data.get('session_cookie')
                return data
        except (json.JSONDecodeError, IOError) as e:
            # Ignore errors loading session file
            pass
    return {}


def save_session(email: str = None):
    """Save session cookie and base URL to file.
    
    Args:
        email: Optional email to save with session
    """
    if SESSION_COOKIE:
        SESSION_DIR.mkdir(parents=True, exist_ok=True)
        try:
            session_data = {
                'base_url': BASE_URL,
                'session_cookie': SESSION_COOKIE
            }
            if email:
                session_data['email'] = email
            
            with open(SESSION_FILE, 'w') as f:
                json.dump(session_data, f)
            # Set restrictive permissions (owner read/write only)
            SESSION_FILE.chmod(0o600)
        except IOError as e:
            print(f"Warning: Could not save session: {e}", file=sys.stderr)


def save_base_url(base_url: str, email: str = None):
    """Persist just the base URL (and optional email) to the session file.

    `register` has no session cookie yet but should still pin the server it ran
    against, so the user's next command targets the same place without
    re-passing --base-url or re-exporting LOOBRIC_BASE_URL. Merges with any
    existing session so a prior login's cookie is preserved.
    """
    if not base_url:
        return
    SESSION_DIR.mkdir(parents=True, exist_ok=True)
    data = {}
    if SESSION_FILE.exists():
        try:
            with open(SESSION_FILE, 'r') as f:
                data = json.load(f)
        except (json.JSONDecodeError, IOError):
            data = {}
    data['base_url'] = base_url
    if email:
        data['email'] = email
    try:
        with open(SESSION_FILE, 'w') as f:
            json.dump(data, f)
        SESSION_FILE.chmod(0o600)
    except IOError as e:
        print(f"Warning: Could not save base URL: {e}", file=sys.stderr)


def clear_session():
    """Clear saved session file."""
    if SESSION_FILE.exists():
        try:
            SESSION_FILE.unlink()
        except IOError as e:
            print(f"Warning: Could not clear session file: {e}", file=sys.stderr)


def get_connection(base_url: Optional[str] = None):
    """Create an HTTP/HTTPS connection for the given base URL (or the global)."""
    base = base_url or BASE_URL
    parsed = urllib.parse.urlparse(base)
    if parsed.scheme == "https":
        return http.client.HTTPSConnection(parsed.netloc)
    elif parsed.scheme == "http":
        return http.client.HTTPConnection(parsed.netloc)
    else:
        raise LoobricClientError(f"Unsupported scheme in base URL: {parsed.scheme!r}")


def make_request(
    method: str,
    endpoint: str,
    body: Optional[Dict[str, Any]] = None,
    extra_headers: Optional[Dict[str, str]] = None,
    require_auth: bool = False,
    base_url: Optional[str] = None,
    api_key: Optional[str] = None,
    session_cookie: Optional[str] = None,
    raw_body: Optional[bytes] = None,
    content_type: Optional[str] = None,
) -> Dict[str, Any]:
    """Make an HTTP request to the Loobric API and return parsed JSON.

    The transport for both the CLI and the `Client` library. It NEVER prints or
    exits — on failure it raises a `LoobricClientError` subclass (`NotFound`,
    `AuthRequired`, `HTTPError`, `ConnectionFailed`). `base_url` / `api_key` /
    `session_cookie` override the module globals so a `Client` can carry its own
    config; when omitted the globals (set by the CLI) are used.

    Args:
        method: HTTP method (GET, POST, DELETE, …)
        endpoint: API path relative to /api/v1 (e.g. "/tool-set-records")
        body: Optional request body (JSON-encoded)
        extra_headers: Optional additional headers
        require_auth: reserved; auth is decided by the server (solo vs multi-user)
        base_url / api_key / session_cookie: per-call config overriding the globals

    Returns:
        Parsed JSON response (``{}`` for an empty 2xx body).
    """
    global SESSION_COOKIE, API_KEY

    conn = get_connection(base_url)
    path = urllib.parse.urljoin("/api/v1/", endpoint.lstrip("/"))
    headers = dict(extra_headers or {})
    headers["Accept"] = "application/json"
    if raw_body is None:
        headers["Content-Type"] = "application/json"
    elif content_type:
        headers["Content-Type"] = content_type

    # Prefer API key over session cookie. With neither, send anyway and let the
    # server decide: a solo-mode server (LOOBRIC_SOLO=1) accepts it; a multi-user
    # server returns 401. The client must not pre-judge auth.
    key = api_key if api_key is not None else API_KEY
    cookie = session_cookie if session_cookie is not None else SESSION_COOKIE
    if key:
        headers["Authorization"] = f"Bearer {key}"
    elif cookie:
        headers["Cookie"] = f"session={cookie}"

    # A raw body (e.g. a multipart upload) overrides the JSON path. Otherwise
    # send the body whenever one is given, including an empty {} — some POST
    # endpoints (e.g. record creation) require a JSON body even when it carries
    # only defaults. `if body` would wrongly drop {} as falsy.
    if raw_body is not None:
        send_body = raw_body
    else:
        send_body = json.dumps(body) if body is not None else None

    try:
        conn.request(method, path, body=send_body, headers=headers)
        response = conn.getresponse()
        status = response.status
        content = response.read().decode("utf-8")

        # Capture the session cookie from a login response (CLI session auth).
        set_cookie = response.getheader("set-cookie") or response.getheader("Set-Cookie")
        if set_cookie:
            for part in set_cookie.split(";"):
                part = part.strip()
                if part.startswith("session="):
                    SESSION_COOKIE = part.split("=", 1)[1]
                    break

        if 200 <= status < 300:
            return json.loads(content) if content.strip() else {}
        try:
            detail = json.loads(content).get("detail", content)
        except json.JSONDecodeError:
            detail = content
        raise _http_error(status, detail)
    except (http.client.HTTPException, ConnectionError, OSError) as e:
        raise ConnectionFailed(f"{e} (server at {base_url or BASE_URL})")
    finally:
        conn.close()
