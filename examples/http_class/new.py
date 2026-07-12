"""Rewrite -- the teapot special case was dropped.

The rewriter saw a "weird one-off branch" and cleaned it up. For code == 418,
new returns "client_error" instead of "teapot".
"""

from __future__ import annotations


def http_class(code: int) -> str:
    if 200 <= code < 300:
        return "success"
    if 300 <= code < 400:
        return "redirect"
    if 400 <= code < 500:
        return "client_error"
    if 500 <= code < 600:
        return "server_error"
    return "unknown"
