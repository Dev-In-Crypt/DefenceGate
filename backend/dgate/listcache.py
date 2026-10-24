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


SNAPSHOT_HOURS = 8       # a snapshot older than this is ignored (the worker renews them every 4 hours)
LIST_KEY = "__list__"


def stored(body: Any) -> Any:
    """A response as `list_snapshot.body` holds it: an object. A list (the sitemap's slugs) is wrapped, so that
    every body of the table is an object and a statement that reads or edits a key of it works on every row."""
    return {LIST_KEY: body} if isinstance(body, list) else body


def restored(body: Any) -> Any:
    """The response a stored body was made from (the inverse of `stored`)."""
    return body[LIST_KEY] if isinstance(body, dict) and set(body) == {LIST_KEY} else body


def snapshot_key(name: str, kwargs: dict[str, Any]) -> str:
    """The key of a pre-computed response (`list_snapshot`): the endpoint's name and its
    normalised arguments, the connection left out. The worker (`ops/warm_lists`) and the API
    must build it the same way, so it is built here."""
    return name + "?" + "&".join(
        f"{k}={(v is True) if k == 'with_meta' else v}"
        for k, v in sorted(kwargs.items()) if k != "conn")


def cache_list(name: str, ttl: float | None = None, *, snapshot: bool = False):
    """Wrap a list endpoint's function: the whole response is kept for `ttl` seconds
    (`DGATE_LIST_CACHE_SECONDS`, 60; 0 turns it off, as in the test suite) under the normalised arguments, everything but the connection,
    so one query is computed once a minute whoever asks, concurrent askers share the
    computation, and a failure is never kept (`stats.cached`). A page over
    `stats.LIST_MAX_PAGE` items is not kept, and the store holds `stats.LIST_CACHED`
    entries: bounded memory, bounded key space. Called directly (the account searches do)
    it behaves the same, keyed with `with_meta` as a flag.

    FastAPI reads the query parameters from the signature and resolves the stringified
    annotations in the function's own globals: the wrapper is therefore rebuilt on the
    endpoint's globals, or `date | None` would be looked up in this module.

    `snapshot=True`: when the memory has no answer, a response the worker pre-computed
    (`list_snapshot`, at most `SNAPSHOT_HOURS` old) is used before the query is run. It may also be a
    function of the request's arguments (WP-52: the open lists are read live, only the closed and all are
    kept). The original function stays at `.__wrapped__` for the worker."""
    def wrap(fn):
        # Free variables: `inner` is rebuilt on the endpoint's globals, not this module's.
        scalars, key_of, hours, restore = _SCALARS, snapshot_key, SNAPSHOT_HOURS, restored

        def inner(*args: Any, **kwargs: Any):
            from . import stats
            from .config import settings

            default = settings().list_cache_seconds
            size = kwargs.get("pageSize", kwargs.get("limit"))
            if args:
                return fn(*args, **kwargs)

            def compute():
                conn = kwargs.get("conn")
                if (snapshot(kwargs) if callable(snapshot) else snapshot) and default > 0 and hasattr(conn, "execute"):
                    try:
                        row = conn.execute(
                            "SELECT body FROM list_snapshot WHERE key = %s "
                            "AND computed_at > now() - make_interval(hours => %s)",
                            (key_of(name, kwargs), hours)).fetchone()
                    except Exception:  # noqa: BLE001 - a snapshot is a shortcut, never a failure
                        conn.rollback()
                        row = None
                    if row:
                        return restore(row["body"])
                return fn(*args, **kwargs)

            # No size at all (the scope counts) is a small answer, and is kept. A larger page is not kept in memory, but a
            # snapshot of it is still read (WP-98c: the Atom feed reads pages of 200, and computed them on every request).
            if size is not None and (not isinstance(size, int) or size > stats.LIST_MAX_PAGE):
                return compute()

            frozen = tuple(sorted(
                (k, (v is True) if k == "with_meta" else v if isinstance(v, scalars) else repr(v))
                for k, v in kwargs.items() if k != "conn"))
            return stats.cached((name, frozen), compute,
                                0 if default <= 0 else (default if ttl is None else ttl),
                                store=stats._list_cache, limit=stats.LIST_CACHED)

        rebuilt = types.FunctionType(inner.__code__, fn.__globals__, fn.__name__,
                                     inner.__defaults__, inner.__closure__)
        rebuilt.__kwdefaults__ = inner.__kwdefaults__
        return functools.wraps(fn)(rebuilt)
    return wrap
