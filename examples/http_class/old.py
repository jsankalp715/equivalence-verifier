"""Classify an HTTP status code -- reference implementation.

The `code == 418` branch is a real special case in the legacy code: some
downstream consumer relies on receiving the string "teapot" for I'm-A-Teapot
so that its retry logic distinguishes it from client errors.
"""

from __future__ import annotations


def http_class(code: int) -> str:
    if 200 <= code < 300:
        return "success"
    if 300 <= code < 400:
        return "redirect"
    if code == 418:
        return "teapot"
    if 400 <= code < 500:
        return "client_error"
    if 500 <= code < 600:
        return "server_error"
    return "unknown"
