"""WP-101 (persona round of 24 October 2026, search), against a real Postgres: the folded texts kept per notice by the
trigger of migration 0113, two words of one group, the new product words, a notice number in every status, and the
global search's tender part as the list reads it."""

from __future__ import annotations

from dataclasses import replace

import pytest

from tests.integration.test_changes import opp, store
from tests.integration.test_wp98 import _fresh_cache, client, get, ids, put  # noqa: F401 (fixtures)

pytestmark = pytest.mark.integration


def stored(conn, oid: int) -> dict:
    return conn.execute("SELECT * FROM opportunity_search WHERE id = %s", (oid,)).fetchone()


def test_the_trigger_keeps_the_folded_texts_of_every_notice(conn):
    o = replace(opp("FOLD-1", country="DE", title="Lieferung von Frästeilen"), title_en="Supply of MILLED parts",
                cpv_codes=["34330000"])
    oid = store(conn, o)
    row = stored(conn, oid)
    assert row["title_original"] == " lieferung von frasteilen" and row["title_en"] == " supply of milled parts"
    assert row["buyer_name"] == " ministry de" and row["native_id"] == "FOLD-1"
    assert "3433" in row["cpv_heads"] and "34330000" in row["cpv_heads"]
    # an amendment of the title is read again; the buyer withheld (suppression, migration 0047) is never searched
    store(conn, replace(o, title_original="Lieferung von Drehteilen"), "b")
    assert stored(conn, oid)["title_original"] == " lieferung von drehteilen"
    conn.execute("UPDATE opportunity SET buyer_withheld = true WHERE id = %s", (oid,))
    conn.commit()
    assert stored(conn, oid)["buyer_name"] is None
    # every notice has its row (the backfill, then the trigger)
    assert conn.execute("SELECT count(*) AS n FROM opportunity o WHERE NOT EXISTS "
                        "(SELECT 1 FROM opportunity_search s WHERE s.id = o.id)").fetchone()["n"] == 0


def test_two_words_of_one_group_find_what_either_finds(client, conn):  # noqa: F811
    put(conn, "M-1", "Fertigung von Drehteilen und Frästeilen")
    put(conn, "M-2", "Frästeile für Kettenfahrzeuge")
    put(conn, "M-3", "Ersatzteile Leopard 2")
    put(conn, "M-4", "Zerspanung von Bauteilen")
    put(conn, "M-5", "Reinigung der Kaserne")
    page = get(client, "/v1/tenders", q="Drehteile Frästeile")
    assert ids(page) == ["M-1", "M-2", "M-3", "M-4"]
    assert "Drehteile" not in page["alsoSearched"] and "Ersatzteile" in page["alsoSearched"]
    assert ids(get(client, "/v1/tenders", q="Frästeile Drehteile", status="all")) == ["M-1", "M-2", "M-3", "M-4"]
    assert ids(get(client, "/v1/tenders", q="CNC")) == ["M-1", "M-2", "M-3", "M-4"]


@pytest.mark.parametrize("q, want", [
    ("harness", ["W-ES", "W-PL"]),
    ("Kabelbaum", ["W-ES", "W-PL"]),
    ("cyber", ["C-DE", "C-FR"]),
    ("cybersecurity", ["C-DE", "C-FR"]),
    ("explosives", ["A-AU"]),          # AU's detonating cord, coded 24615000 (p04)
])
def test_the_product_words_of_the_personas(client, conn, q, want):  # noqa: F811
    put(conn, "W-ES", "Suministro de mazos de cables para vehículos", country="ES")
    put(conn, "W-PL", "Wiązki przewodów do pojazdów", country="PL")
    put(conn, "C-FR", "Prestations de cybersécurité", country="FR")
    put(conn, "C-DE", "Cybersicherheit der IT-Systeme")
    put(conn, "A-AU", "Dostawa lontu detonującego", country="PL", cpv=["24615000"])
    put(conn, "X-1", "Vehicle maintenance")
    assert ids(get(client, "/v1/tenders", q=q)) == want, q


def test_a_notice_number_is_found_in_every_status(client, conn):  # noqa: F811
    put(conn, "220199-2026", "Aeronaves para treino", country="PT", closed=True)
    assert ids(get(client, "/v1/tenders", q="220199-2026")) == []             # the list's Open, as asked
    assert ids(get(client, "/v1/tenders", q="220199-2026", status="all")) == ["220199-2026"]
    body = get(client, "/v1/search", q="220199-2026")
    assert body["tenders"]["total"] == 1 and body["tenders"]["items"][0]["noticeId"] == "220199-2026"


def test_the_global_search_counts_the_tenders_as_the_list(client, conn):  # noqa: F811
    for i in range(12):
        put(conn, f"E-{i}", f"Ersatzteile Los {i}")
    body = get(client, "/v1/search", q="Ersatzteile")
    page = get(client, "/v1/tenders", q="Ersatzteile")
    assert body["tenders"]["error"] is None
    assert (body["tenders"]["total"], body["tenders"]["atLeast"]) == (page["total"], page["totalCapped"]) == (12, False)

