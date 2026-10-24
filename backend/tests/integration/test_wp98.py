"""WP-98 (persona round of 23 October 2026, section C, items 1 to 4), against a real Postgres: every word in any order,
the words of other languages, the buyers' abbreviations, the company search by name first, the global search's buyer
first, and a rare word over every status read by its matches (the `q=drone&status=all` 503)."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from dgate import api, stats, tenders
from tests.integration.test_changes import opp, store
from tests.integration.test_supplier_map import env, run, scenario  # noqa: F401 (env is a fixture)

pytestmark = pytest.mark.integration

PAST = datetime.now(timezone.utc) - timedelta(days=200)


@pytest.fixture(autouse=True)
def _fresh_cache():
    stats.reset_cache()
    yield
    stats.reset_cache()


@pytest.fixture()
def client(conn):
    with TestClient(api.app) as c:
        yield c


def get(client, path: str, **params) -> dict:
    r = client.get(path, params=params)
    assert r.status_code == 200, r.text
    return r.json()


def ids(page: dict) -> list[str]:
    return sorted(i["noticeId"] for i in page["items"])


def put(conn, native_id: str, title: str, *, cpv: list[str] | None = None, country: str = "DE", buyer: str | None = None,
        closed: bool = False, title_en: str | None = None) -> int:
    o = replace(opp(native_id, country=country, title=title, deadline=PAST if closed else opp("x").deadline_at),
                cpv_codes=cpv or ["35400000"], title_en=title_en)
    if buyer:
        o = replace(o, buyer_name_raw=buyer)
    return store(conn, o)


# ======================================================================= 1. every word, in any order

def test_every_word_in_any_order_and_a_run_of_words_against_the_code_titles(client, conn):
    put(conn, "SP-1", "Spare parts for the Boxer")
    put(conn, "SP-2", "Parts, spare, for trucks")
    put(conn, "SP-3", "6003106689-Ersatzteile Din & Iso", cpv=["34330000"])   # German title, CPV "Spare parts for goods vehicles"
    put(conn, "SP-4", "Spare tyres")
    assert ids(get(client, "/v1/tenders", q="spare parts")) == ["SP-1", "SP-2", "SP-3"]
    assert ids(get(client, "/v1/tenders", q="parts spare")) == ["SP-1", "SP-2", "SP-3"]
    assert ids(get(client, "/v1/tenders", q="spare parts", country="DE")) == ["SP-1", "SP-2", "SP-3"]
    assert ids(get(client, "/v1/tenders", q="Boxer spare")) == ["SP-1"]


# ======================================================================= 2. the words of other languages

@pytest.mark.parametrize("q, want", [
    ("fardamento", ["U-DE", "U-EN", "U-FR", "U-PL", "U-PT"]),        # Portuguese
    ("uniforms", ["U-DE", "U-EN", "U-FR", "U-PL", "U-PT"]),          # English
    ("Bekleidung", ["U-DE", "U-EN", "U-FR", "U-PL", "U-PT"]),        # German
    ("vêtements", ["U-DE", "U-EN", "U-FR", "U-PL", "U-PT"]),         # French
    ("mundury", ["U-DE", "U-EN", "U-FR", "U-PL", "U-PT"]),           # Polish
    ("Drohnen", ["D-EN", "D-PL"]),
    ("drone", ["D-EN", "D-PL"]),
    ("brandstof", ["F-ES", "F-NL"]),                                   # Dutch
    ("combustible", ["F-ES", "F-NL"]),                                 # Spanish
    ("materiały wybuchowe", ["A-DE", "A-PL"]),
    ("Munition", ["A-DE", "A-PL"]),
    ("night vision", ["N-DE"]),
    ("body armour", ["B-FR"]),
])
def test_a_product_word_finds_the_titles_of_other_languages(client, conn, q, want):
    put(conn, "U-PT", "Aquisição de fardamento", country="PT")
    put(conn, "U-DE", "Lieferung von Bekleidung für die Bundeswehr")
    put(conn, "U-EN", "Combat uniforms", country="IE")
    put(conn, "U-FR", "Fourniture de vêtements", country="FR")
    put(conn, "U-PL", "Dostawa umundurowania i mundury", country="PL")
    put(conn, "D-EN", "Counter-drone systems", country="NO")
    put(conn, "D-PL", "Dostawa dronów, drony rozpoznawcze", country="PL")
    put(conn, "F-NL", "Levering brandstoffen", country="NL")
    put(conn, "F-ES", "Suministro de combustible", country="ES")
    put(conn, "A-DE", "Munition 155 mm")
    put(conn, "A-PL", "Dostawa materiałów... materiały wybuchowe", country="PL")
    put(conn, "N-DE", "Nachtsichtgeräte")
    put(conn, "B-FR", "Gilets pare-balles", country="FR")
    put(conn, "X-1", "Vehicle maintenance")
    page = get(client, "/v1/tenders", q=q)
    assert ids(page) == want, q
    assert page["searchGroups"] and page["alsoSearched"]


def test_what_else_was_searched_is_said_and_a_word_of_no_group_searches_as_before(client, conn):
    put(conn, "D-1", "Drohnenabwehr")
    page = get(client, "/v1/tenders", q="Drohnen")
    assert ids(page) == ["D-1"]
    assert "UAV" in page["alsoSearched"] and [g["id"] for g in page["searchGroups"]] == ["drones"]
    assert page["searchGroups"][0]["cpv"] == ["35613"]
    plain = get(client, "/v1/tenders", q="Drohnenabwehr")
    assert ids(plain) == ["D-1"] and plain["alsoSearched"] == [] and plain["searchGroups"] == []
    # the export, the scope counts and the calendar read the words the same way
    assert [i["noticeId"] for i in get(client, "/v1/tenders/export", q="drone")["items"]] == ["D-1"]
    assert get(client, "/v1/tenders/scope-counts", q="drone")["core"] == 1


# ======================================================================= 3. a buyer by its abbreviation

def test_an_abbreviation_finds_the_buyer_and_it_comes_first(client, conn):
    for i in range(3):
        put(conn, f"DGA-X{i}", "Prestations diverses", country="FR", buyer="DGA consulting de la Région")   # a bigger namesake
    put(conn, "DGA-1", "Munitions", country="FR", buyer="Direction générale de l'armement")
    put(conn, "BE-1", "Fournitures", country="BE", buyer="Ministère de la Défense")
    for i in range(3):
        put(conn, f"BE-X{i}", "Fournitures", country="FR", buyer="Ministère de la Défense et des anciens combattants")
    put(conn, "JM-1", "Repuestos", country="ES", buyer="JAEMALE")
    names = [b["name"].lower() for b in get(client, "/v1/buyers", q="DGA")["items"]]
    assert names[0].startswith("direction generale de l") or names[0].startswith("direction générale de l"), names
    assert len(names) == 2
    assert [b["country"] for b in get(client, "/v1/buyers", q="Ministère de la Défense")["items"]][0] == "BE"
    assert len(get(client, "/v1/buyers", q="JAE MALE")["items"]) == 1
    # the global search: the buyer the words name is first and is said to be it
    body = get(client, "/v1/search", q="DGA")
    assert body["buyerNamed"] is True and body["buyers"]["items"][0]["country"] == "FR"
    assert get(client, "/v1/search", q="Ministère de la Défense")["buyerNamed"] is True
    assert get(client, "/v1/search", q="Fournitures")["buyerNamed"] is False


# ======================================================================= 4. the company search, the global search

def test_the_company_search_finds_every_word_of_a_name_in_any_order(conn, env, client):  # noqa: F811
    run(scenario(conn))
    for q in ("Rheinmetall", "landsysteme rheinmetall", "Nammo Raufoss", "raufoss"):
        page = get(client, "/v1/suppliers", q=q)
        assert page["total"] == 1, q
    assert get(client, "/v1/suppliers", q="Rheinmetall Nammo")["total"] == 0
    # a word of the name as a buyer published it ("Indra Sistemas, S.A.")
    assert get(client, "/v1/suppliers", q="Indra Sistemas")["total"] == 1
    body = get(client, "/v1/search", q="Rheinmetall")
    assert body["suppliers"]["error"] is None and body["suppliers"]["total"] == 1


def test_a_rare_word_over_every_status_is_read_by_its_matches(client, conn, monkeypatch):
    for i in range(6):
        put(conn, f"OLD-{i}", f"Drone spare batch {i}", closed=True)
    put(conn, "NEW-1", "Drone open")
    for i in range(30):
        put(conn, f"OTHER-{i}", "Vehicle maintenance", closed=True)
    seen = []
    real = tenders._rows

    def spy(*a, **kw):
        seen.append(kw.get("few", False))
        return real(*a, **kw)

    monkeypatch.setattr(tenders, "_rows", spy)
    page = get(client, "/v1/tenders", q="drone", status="all", pageSize=3)
    assert page["total"] == 7 and page["totalCapped"] is False
    assert [i["noticeId"] for i in page["items"]][0] == "NEW-1"
    assert seen[-1] is True                                  # the closed part was read by its matches
    # the order of the closed part is the list's own (deadline, then id), page after page
    rest = [i["noticeId"] for p in (1, 2, 3) for i in get(client, "/v1/tenders", q="drone", status="all", pageSize=3,
                                                         page=p)["items"]]
    # WP-106: the rest of All runs newest first (deadline, publication, id, all descending); oldest first when asked for
    assert rest == ["NEW-1"] + [f"OLD-{i}" for i in reversed(range(6))]
    asc = [i["noticeId"] for p in (1, 2, 3) for i in get(client, "/v1/tenders", q="drone", status="all", pageSize=3,
                                                        sort="deadline-asc", page=p)["items"]]
    assert asc == ["NEW-1"] + [f"OLD-{i}" for i in range(6)]
    closed = get(client, "/v1/tenders", q="drone", status="closed")
    assert closed["total"] == 6
    # a common word is read along the index as before (no `few`)
    seen.clear()
    monkeypatch.setattr(tenders, "FEW_ROWS", 3)
    assert get(client, "/v1/tenders", q="maintenance", status="closed")["total"] == 30
    assert seen == [False]
