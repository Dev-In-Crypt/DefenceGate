"""The response cache of the list endpoints, as a decorator.

Kept in a module of its own because `stats` imports `tenders` and `api` imports both: this
one imports nothing at start-up and reaches `stats` (where the single-flight cache lives)
when a request first needs it.
"""

from __future__ import annotations

import functools
import types
from datetime import date, datetime
from typing import Any

_SCALARS = (str, int, float, bool, date, datetime, type(None))


def cache_list(name: str, ttl: float | None = None):
    """Wrap a list endpoint's function: the whole response is kept for `ttl` seconds
    (`DGATE_LIST_CACHE_SECONDS`, 60; 0 turns it off, as in the test suite) under the normalised arguments, everything but the connection,
    so one query is computed once a minute whoever asks, concurrent askers share the
    computation, and a failure is never kept (`stats.cached`). A page over
    `stats.LIST_MAX_PAGE` items is not kept, and the store holds `stats.LIST_CACHED`
    entries: bounded memory, bounded key space. Called directly (the account searches do)
    it behaves the same, keyed with `with_meta` as a flag.

    FastAPI reads the query parameters from the signature and resolves the stringified
    annotations in the function's own globals: the wrapper is therefore rebuilt on the
    endpoint's globals, or `date | None` would be looked up in this module."""
    def wrap(fn):
        scalars = _SCALARS            # a free variable: `inner` is rebuilt on other globals

        def inner(*args: Any, **kwargs: Any):
            from . import stats
            from .config import settings

            default = settings().list_cache_seconds
            size = kwargs.get("pageSize", kwargs.get("limit"))
            if args or not isinstance(size, int) or size > stats.LIST_MAX_PAGE:
                return fn(*args, **kwargs)
            frozen = tuple(sorted(
                (k, (v is True) if k == "with_meta" else v if isinstance(v, scalars) else repr(v))
                for k, v in kwargs.items() if k != "conn"))
            return stats.cached((name, frozen), lambda: fn(*args, **kwargs),
                                0 if default <= 0 else (default if ttl is None else ttl),
                                store=stats._list_cache, limit=stats.LIST_CACHED)

        rebuilt = types.FunctionType(inner.__code__, fn.__globals__, fn.__name__,
                                     inner.__defaults__, inner.__closure__)
        rebuilt.__kwdefaults__ = inner.__kwdefaults__
        return functools.wraps(fn)(rebuilt)
    return wrap
