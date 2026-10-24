"""WP-98c (production timings after the WP-98b deploy) against a real Postgres: the supplier list's value orders are read from
sums the worker stores (renewed with every award load), equal to the profile's sums, said to be behind when an award load
finished after them and ignored when too old or computed under the other PLACSP switch; a filtered value order is summed live;
the worker keeps the API pages of the Atom feed's first page."""

from __future__ import annotations

import pytest
from psycopg.types.json import Jsonb

from dgate import awards, changes, stats, suppliers
from dgate.listcache import snapshot_key
from dgate.ops import warm_lists
from tests.integration.test_warm_lists import _put
from tests.integration.test_wp95 import award, client, env, madzeal, notice, org  # noqa: F401 - fixtures

pytestmark = pytest.mark.integration


def get(c, path: str, **params) -> dict:
    r = c.get(path, params=params)
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture
def three(conn, madzeal):  # noqa: F811
    """madzeal (EUR 1,243,802 in contract values), Mesko (PLN 7,000,000), Small Parts (EUR 30,000)."""
    jae = org(conn, "agencja uzbrojenia", "PL", is_defence_buyer=True)
    pl = org(conn, "mesko", "PL")
    small = org(conn, "small parts", "ES")
    for i, amount in enumerate((3_000_000.0, 4_000_000.0)):
        award(conn, notice(conn, "ted", f"90{i}-2026", buyer=jae, country="PL"), pl, "MESKO S.A.",
              value=(amount, "PLN", "contract"), country="PL")
    for i in range(3):
        award(conn, notice(conn, "ted", f"80{i}-2026", buyer=jae), small, "Small Parts SL", value=(10_000.0, "EUR", "contract"))
    conn.commit()
    return {"madzeal": madzeal["org"], "mesko": pl, "small": small}


def names(page: dict) -> list[str]:
    return [i["name"].lower().split()[0].strip(",") for i in page["items"]]


def test_the_stored_order_is_the_live_one_and_its_sums_are_the_profiles(client, conn, three):  # noqa: F811
    live = get(client, "/v1/suppliers", sort="value-EUR")
    assert live["valuesAsOf"] is None and live["valuesBehind"] is False      # nothing stored yet: summed now
    awards.refresh_award_twins(conn)                                         # an award load renews the stored orders
    conn.commit()
    stored = get(client, "/v1/suppliers", sort="value-EUR")
    assert stored["valuesAsOf"] is not None and stored["valuesBehind"] is False
    assert names(stored) == names(live) == ["madzeal", "small", "mesko"]
    assert stored["items"] == live["items"]
    assert names(get(client, "/v1/suppliers", sort="value-PLN"))[0] == "mesko"
    # every stored sum is the profile's (the truth), per currency
    body = conn.execute("SELECT body FROM list_snapshot WHERE key = %s", (suppliers.value_order_key(False),)).fetchone()["body"]
    for currency, (orgs, amounts) in body["byCurrency"].items():
        for o, amount in zip(orgs, amounts, strict=True):
            sums = {s["currency"]: s["amount"] for s in get(client, f"/v1/suppliers/{o}")["values"]["byCurrency"]}
            assert sums[currency] == amount, (o, currency)
    # the TED-only order is stored too: madzeal's TED rows hold no contract value
    ted = conn.execute("SELECT body FROM list_snapshot WHERE key = %s", (suppliers.value_order_key(True),)).fetchone()["body"]
    assert three["madzeal"] not in ted["byCurrency"]["EUR"][0]
    assert names(get(client, "/v1/suppliers", sort="value-EUR", source="ted")) == ["small", "madzeal", "mesko"]


def test_the_stored_order_is_what_the_list_reads(client, conn, three):  # noqa: F811
    suppliers.store_value_orders(conn)
    conn.commit()
    # a marker in the stored body: Mesko first in EUR, which no live sum would say
    key = suppliers.value_order_key(False)
    body = conn.execute("SELECT body FROM list_snapshot WHERE key = %s", (key,)).fetchone()["body"]
    body["byCurrency"]["EUR"] = [[three["mesko"]], [9e9]]
    conn.execute("UPDATE list_snapshot SET body = %s WHERE key = %s", (Jsonb(body), key))
    conn.commit()
    assert names(get(client, "/v1/suppliers", sort="value-EUR"))[0] == "mesko"
    # a filter is summed now, never from the stored order
    filtered = get(client, "/v1/suppliers", sort="value-EUR", buyerCountry="ES")
    assert filtered["valuesAsOf"] is None and names(filtered)[0] == "madzeal"
    # too old, or computed under the other PLACSP switch: summed now
    conn.execute("UPDATE list_snapshot SET computed_at = now() - interval '9 hours' WHERE key = %s", (key,))
    conn.commit()
    assert names(get(client, "/v1/suppliers", sort="value-EUR"))[0] == "madzeal"
    conn.execute("UPDATE list_snapshot SET computed_at = now(), body = jsonb_set(body, '{placspPublic}', 'false') WHERE key = %s",
                 (key,))
    conn.commit()
    assert get(client, "/v1/suppliers", sort="value-EUR")["valuesAsOf"] is None


def test_an_award_load_after_the_stored_order_is_said(client, conn, three):  # noqa: F811
    suppliers.store_value_orders(conn)
    conn.commit()
    assert get(client, "/v1/suppliers", sort="value-EUR")["valuesBehind"] is False
    o = notice(conn, "ted", "700-2026")
    conn.execute("INSERT INTO award_notice (opportunity_id, status, winners_seen, winners_kept, read_at) "
                 "VALUES (%s, 'loaded', 1, 1, now() + interval '1 minute')", (o,))
    conn.commit()
    page = get(client, "/v1/suppliers", sort="value-EUR")
    assert page["valuesBehind"] is True and page["valuesAsOf"] is not None


def test_the_worker_keeps_the_value_orders_and_the_feeds_first_page(client, conn, monkeypatch):  # noqa: F811
    monkeypatch.setenv("DGATE_LIST_CACHE_SECONDS", "60")
    from dgate import config
    config.reset_cache()
    stats.reset_cache()
    try:
        _put(conn, "W-98c", status="closed")
        assert warm_lists.run(conn, write=True)["failed"] == 0
        keys = {r["key"] for r in conn.execute("SELECT key FROM list_snapshot").fetchall()}
        assert {suppliers.value_order_key(False), suppliers.value_order_key(True)} <= keys
        base = {**warm_lists._defaults(changes.list_changes.__wrapped__), "with_meta": True, "pageSize": 200}
        for page in (1, 2):
            assert snapshot_key("changes", {**base, "page": page}) in keys
        # the API serves the feed's second page from the snapshot (a marker in its body)
        key = snapshot_key("changes", {**base, "page": 2})
        conn.execute("UPDATE list_snapshot SET body = jsonb_set(body, '{total}', '4242') WHERE key = %s", (key,))
        conn.commit()
        assert get(client, "/v1/changes", pageSize=200, page=2)["total"] == 4242
    finally:
        monkeypatch.setenv("DGATE_LIST_CACHE_SECONDS", "0")
        config.reset_cache()
        stats.reset_cache()


def test_the_worker_start_writes_the_first_views_only_when_missing(conn):
    _put(conn, "W-98c-2", status="closed")
    first = warm_lists.run_first(conn)
    assert first["failed"] == 0 and first["written"] == first["views"] == 6     # 4 change pages, 2 value orders
    keys = {r["key"] for r in conn.execute("SELECT key FROM list_snapshot").fetchall()}
    assert {suppliers.value_order_key(False), suppliers.value_order_key(True)} <= keys
    assert not any(k.startswith("tenders?") for k in keys)                      # not the whole run
    assert warm_lists.run_first(conn)["views"] == 0                              # fresh: nothing to do
