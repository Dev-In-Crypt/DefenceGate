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
# WP-120: how long past its time a kept list answer is still given while a background read renews it (`cache_list(stale=)`)
LIST_STALE_SECONDS = 10 * 60


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


def cache_list(name: str, ttl: float | None = None, *, snapshot: bool = False, stale: float = 0, large: int = 0,
               warm_next: bool = False):
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
    kept). The original function stays at `.__wrapped__` for the worker.

    WP-120: `stale` (seconds): an expired answer is given for that long more while one background read renews it
    (`stats.cached_stale`), so the request that finds it expired does not wait for the query (the default tender list was
    3.2 s on such a call). `large` (items): pages up to that size are kept too, in a small store of their own (the export).

    WP-172: `warm_next`: a first page asked over HTTP that has a second one starts that second page in the background
    (`stats.warm`, its own connection, after this answer is in hand), so its counts and rows are kept before the visitor asks
    for it. A first page given from memory or from a snapshot computes no count, and the second page then paid them all (3 s
    on production for a common word, 16 November 2026)."""
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

            asked = kwargs.get("conn")

            def compute(conn=asked, kw=kwargs):
                if (snapshot(kw) if callable(snapshot) else snapshot) and default > 0 and hasattr(conn, "execute"):
                    try:
                        row = conn.execute(
                            "SELECT body FROM list_snapshot WHERE key = %s "
                            "AND computed_at > now() - make_interval(hours => %s)",
                            (key_of(name, kw), hours)).fetchone()
                    except Exception:  # noqa: BLE001 - a snapshot is a shortcut, never a failure
                        conn.rollback()
                        row = None
                    if row:
                        return restore(row["body"])
                return fn(**kw) if conn is asked else fn(**{**kw, "conn": conn})

            # No size at all (the scope counts) is a small answer, and is kept. A larger page is not kept in memory, but a
            # snapshot of it is still read (WP-98c: the Atom feed reads pages of 200, and computed them on every request).
            # WP-120: `large`, pages up to `large` items are kept, in a store of their own (`stats._large_cache`, LARGE_CACHED).
            store, limit = stats._list_cache, stats.LIST_CACHED
            if size is not None and (not isinstance(size, int) or size > stats.LIST_MAX_PAGE):
                if not (large and isinstance(size, int) and size <= large):
                    return compute()
                store, limit = stats._large_cache, stats.LARGE_CACHED

            def frozen(kw):
                return tuple(sorted(
                    (k, (v is True) if k == "with_meta" else v if isinstance(v, scalars) else repr(v))
                    for k, v in kw.items() if k != "conn"))

            seconds = 0 if default <= 0 else (default if ttl is None else ttl)
            if stale and seconds > 0:
                # WP-120: past `seconds` the kept answer is still given for `stale` more while a background read renews it
                value = stats.cached_stale((name, frozen(kwargs)), compute, asked, seconds, stale,
                                           store=store, limit=limit)
            else:
                value = stats.cached((name, frozen(kwargs)), compute, seconds, store=store, limit=limit)
            # a visitor's request only (`with_meta` is True over HTTP): the account code and the sell report read one page
            if (warm_next and seconds > 0 and kwargs.get("page") == 1 and kwargs.get("with_meta") is True
                    and isinstance(value, dict) and (value.get("totalCapped") or (value.get("total") or 0) > (size or 0))):
                nxt = {**kwargs, "page": 2}
                stats.warm((name, frozen(nxt)), lambda c: compute(c, nxt), seconds, store=store, limit=limit)
            return value

        rebuilt = types.FunctionType(inner.__code__, fn.__globals__, fn.__name__,
                                     inner.__defaults__, inner.__closure__)
        rebuilt.__kwdefaults__ = inner.__kwdefaults__
        return functools.wraps(fn)(rebuilt)
    return wrap
