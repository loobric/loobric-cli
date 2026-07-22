# MIT License
# Copyright (c) 2025 sliptonic
# SPDX-License-Identifier: MIT
"""Typed client errors, raised by the transport and library layers (never printed)."""
from typing import Any


class LoobricClientError(Exception):
    """Base class for every error the loobric library raises."""


class ConnectionFailed(LoobricClientError):
    """The server could not be reached (network/DNS/refused/timeout)."""


class HTTPError(LoobricClientError):
    """The server returned a non-2xx status. Carries .status and .detail."""

    def __init__(self, status: int, detail: Any):
        self.status = status
        self.detail = detail
        super().__init__(f"HTTP {status}: {detail}")


class NotFound(HTTPError):
    """404 — the resource does not exist."""


class AuthRequired(HTTPError):
    """401/403 — authentication is missing or insufficient."""


def _http_error(status: int, detail: Any) -> HTTPError:
    if status == 404:
        return NotFound(status, detail)
    if status in (401, 403):
        return AuthRequired(status, detail)
    return HTTPError(status, detail)


