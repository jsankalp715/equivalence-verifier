"""Phase 2 domain guard for the HTTP classifier."""

from __future__ import annotations

from crosshair import IgnoreAttempt

from . import new, old


def _in_domain(code: int) -> bool:
    return 100 <= code <= 599


def old_bounded(code: int) -> str:
    if not _in_domain(code):
        raise IgnoreAttempt
    return old.http_class(code)


def new_bounded(code: int) -> str:
    if not _in_domain(code):
        raise IgnoreAttempt
    return new.http_class(code)
