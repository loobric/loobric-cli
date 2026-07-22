# MIT License
# Copyright (c) 2025 sliptonic
# SPDX-License-Identifier: MIT
"""Loobric client — importable Python library for the Loobric Core API.

Speaks only the public REST API and depends on nothing from the server, so a
client (FreeCAD, future Fusion, scripts) can `pip install loobric-cli` and
reuse this rather than writing its own HTTP layer.
"""
from loobric.client import Client
from loobric.errors import (
    AuthRequired,
    ConnectionFailed,
    HTTPError,
    NotFound,
    LoobricClientError,
)

__all__ = [
    "Client",
    "LoobricClientError",
    "ConnectionFailed",
    "HTTPError",
    "NotFound",
    "AuthRequired",
]
