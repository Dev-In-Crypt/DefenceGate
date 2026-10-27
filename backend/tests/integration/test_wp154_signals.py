"""WP-154: company signals on a real Postgres. Growing, new markets and new EU defence funding over the award set and the
participations as the supplier map and the organisation pages read them: one procurement counted once, the supplier page's
count equal to the signal's, natural persons and removed organisations in no row; the paid part closed by its switch and
open only to an account whose plan allows it."""

# ruff: noqa: F811 - the fixtures `client` and `sent` come from test_accounts.py
from __future__ import annotations

from datetime import date, timedelta

import pytest

from dgate import config, db, signals
from dgate.normalise import Opportunity
from tests.integration.test_accounts import H, client, sent, sign_in  # noqa: F401
from tests.integration.test_billing_wp124 import _billing_env

pytestmark = pytest.mark.integration

TODAY = date.today()


def notice(conn, native_id: str, *, days_ago: int, country: str = "DE", buyer: str = "BAAINBw",
           procedure: str | None = None, value: float | None = None, cpv: str = "35400000") -> int:
    opp = Opportunity(source_code="ted", native_id=native_id, buyer_name_raw=buyer, title_original=f"Contract {native_id}",
                      title_en=f"Contract {native_id}", country=country, published_at=TODAY - timedelta(days=days_ago),
                      cpv_codes=[cpv], status="awarded", is_defence=True, sig_legal_basis=True, sig_cpv=True,
                      procedure_identifier=procedure, value_amount=value, value_currency="EUR" if value else None,
                      value_kind="total" if value else None, source_url=f"https://ted.example/{native_id}")
    src = db.source_id(conn, "ted")
    opp.buyer_org_id = db.resolve_organisation(conn, f"{buyer} {country}", country, src_id=src)
    oid, _ = db.upsert_opportunity(conn, opp, f"hash-{native_id}", src)
    return oid


def org(conn, name: str, country: str, *, person: bool = False) -> int:
    return conn.execute("INSERT INTO organisation (canonical_name, display_name, country, individual_reason) "
                        "VALUES (%s, %s, %s, %s) RETURNING id",
                        (name.lower(), name, country, "sole_trader" if person else None)).fetchone()["id"]


def win(conn, opp: int, who: int, country: str, value: float | None = None) -> None:
    conn.execute("""INSERT INTO award (opportunity_id, organisation_id, supplier_country, name_as_stated, winners_in_notice,
                                       cpv_main, resolution_method, resolution_confidence, value_amount, value_currency,
                                       value_kind)
                    VALUES (%s, %s, %s, (SELECT display_name FROM organisation WHERE id = %s), 1, '35400000',
                            'exact_name', 1.0, %s, %s, %s)""",
                 (opp, who, country, who, value, "EUR" if value else None, "contract" if value else None))


@pytest.fixture()
def world(conn):
    w = {}
    w["alpha"] = a = org(conn, "Alpha Defence GmbH", "DE")
    # Alpha: one win the year before (Germany); three procurements in the last 12 months, one of them published in two
    # notices of one procedure (counted once), one in Lithuania (a new market); a unit price of EUR 48 in no sum
    win(conn, notice(conn, "1-2025", days_ago=500), a, "DE", 500_000)
    win(conn, notice(conn, "2-2026", days_ago=30, procedure="proc-a"), a, "DE", 1_000_000)
    win(conn, notice(conn, "3-2026", days_ago=20, procedure="proc-a"), a, "DE", 1_000_000)
    win(conn, notice(conn, "4-2026", days_ago=60, country="LT", buyer="DPA"), a, "DE", 2_000_000)
    win(conn, notice(conn, "5-2026", days_ago=90), a, "DE", 48)
    # Bravo: two and two (not growing); Charlie: one against none (under MIN_RECENT), its first win anywhere (no market)
    w["bravo"] = b = org(conn, "Bravo SAS", "FR")
    for i, d in enumerate((40, 50, 400, 410)):
        win(conn, notice(conn, f"1{i}-b", days_ago=d, country="FR", buyer="DGA"), b, "FR")
    w["charlie"] = c = org(conn, "Charlie Sp. z o.o.", "PL")
    win(conn, notice(conn, "20-c", days_ago=10, country="ES", buyer="Ministerio"), c, "PL")
    # a sole trader with five recent wins and a win before: never in a row
    p = org(conn, "Jan Kowalski", "PL", person=True)
    for i in range(5):
        win(conn, notice(conn, f"3{i}-p", days_ago=10 + i, country="CZ", buyer="AVZ"), p, "PL")
    win(conn, notice(conn, "39-p", days_ago=600, country="PL", buyer="AU"), p, "PL")
    conn.commit()
    return w


def test_growing_counts_procurements_as_the_supplier_page_does_and_sums_contract_values(conn, client, world):
    r = client.get("/v1/signals/growing").json()
    assert r["note"] == "Facts from public records, not investment advice." and r["fullOpen"] is False
    assert r["total"] == 1 and [i["company"]["name"] for i in r["items"]] == ["Alpha Defence GmbH"]
    row = r["items"][0]
    assert (row["recent"], row["prior"]) == (3, 1)
    # EUR 48 is a unit price: counted as a procurement, in no sum (`suppliers.value_totals`)
    assert row["comparable"] == {"currency": "EUR", "recent": 3_000_000.0, "recentCount": 2, "prior": 500_000.0,
                                 "priorCount": 1}
    assert row["latest"]["noticeId"] == "3-2026" and row["latest"]["sourceUrl"] == "https://ted.example/3-2026"
    # the company's page counts the same procurements (four in the window, the two notices of proc-a once)
    page = client.get(f"/v1/suppliers/{row['company']['slug']}").json()
    assert page["noticeCount"] == row["recent"] + row["prior"] and page["slug"] == row["company"]["slug"]
    # filters are the supplier map's: the supplier's country, a CPV prefix
    assert client.get("/v1/signals/growing?country=FR").json()["total"] == 0
    assert client.get("/v1/signals/growing?country=Germany&cpv=354").json()["total"] == 1
    assert client.get("/v1/signals/growing?cpv=3310").json()["total"] == 0
    assert client.get("/v1/signals/growing?programme=EDF").status_code == 422
    assert client.get("/v1/signals/growing?country=Atlantis").status_code == 422
    assert client.get("/v1/signals/growing?sort=x").status_code == 422
    assert client.get("/v1/signals/rumours").status_code == 404


def test_new_markets_need_a_win_elsewhere_before_and_name_the_first_notice(conn, client, world):
    r = client.get("/v1/signals/markets").json()
    rows = [(i["company"]["name"], i["market"], i["winsThere"], i["winsBefore"]) for i in r["items"]]
    # Alpha in Lithuania; not Germany (won there before); not Charlie (no win before); not the sole trader
    assert rows == [("Alpha Defence GmbH", "LT", 1, 1)]
    assert r["items"][0]["firstWin"]["noticeId"] == "4-2026"
    assert r["windowFrom"] == signals.since(TODAY).isoformat()


def test_no_person_and_no_removed_company_in_any_row(conn, client, world):
    conn.execute("UPDATE organisation SET suppressed = TRUE WHERE id = %s", (world["alpha"],))
    conn.commit()
    for kind in ("growing", "markets"):
        body = client.get(f"/v1/signals/{kind}").text
        assert "Kowalski" not in body and "Alpha" not in body


def project(conn, native: str, programme: str, year: int, acronym: str) -> int:
    return conn.execute(
        """INSERT INTO project (source_id, programme_id, native_id, acronym, title, call_year)
           VALUES ((SELECT id FROM source WHERE code = 'edf_factsheets'), (SELECT id FROM programme WHERE code = %s),
                   %s, %s, %s, %s) RETURNING id""", (programme, native, acronym, f"{acronym} project", year)).fetchone()["id"]


def join(conn, proj: int, o: int, role: str = "participant", active: bool = True) -> None:
    conn.execute("""INSERT INTO participation (project_id, organisation_id, role, resolution_method, resolution_confidence,
                                               active) VALUES (%s, %s, %s, 'exact_name', 1.0, %s)""", (proj, o, role, active))


def test_new_funding_is_the_latest_call_year_first_participations_first(conn, client):
    new = org(conn, "Echo Robotics", "EE")
    old = org(conn, "Foxtrot Aerospace", "IT")
    merged = org(conn, "Golf Old Name", "NL")
    live = org(conn, "Golf Systems BV", "NL")
    conn.execute("UPDATE organisation SET merged_into = %s WHERE id = %s", (live, merged))
    person = org(conn, "Piet Jansen", "NL", person=True)
    gone = org(conn, "Hotel Ltd", "IE")
    conn.execute("UPDATE organisation SET suppressed = TRUE WHERE id = %s", (gone,))
    p25, p25b = project(conn, "EDF-2025-A", "EDF", 2025, "ALPHA"), project(conn, "EDF-2025-B", "EDF", 2025, "BRAVO")
    p20 = project(conn, "EDIDP-2020-A", "EDIDP", 2020, "OLDIE")
    h22 = project(conn, "HE-2022", "HORIZON", 2022, "CIVIL")            # not a defence programme
    for o in (new, person, gone, merged):
        join(conn, p25, o)
    join(conn, p25b, old, "coordinator")
    join(conn, p20, old)
    join(conn, h22, live)
    join(conn, project(conn, "EDF-2025-C", "EDF", 2025, "GONE"), new, active=False)   # history, not a member
    conn.commit()
    r = client.get("/v1/signals/funding").json()
    rows = [(i["company"]["name"], i["year"], i["first"], i["newProjects"], i["earlierProjects"]) for i in r["items"]]
    assert sorted(rows[:2]) == [("Echo Robotics", 2025, True, 1, 0), ("Golf Systems BV", 2025, True, 1, 0)]
    assert rows[2] == ("Foxtrot Aerospace", 2025, False, 1, 1)
    assert len(rows) == 3 and "Jansen" not in str(r) and "Hotel" not in str(r)
    assert r["items"][2]["projects"][0]["acronym"] == "BRAVO" and r["items"][2]["projects"][0]["role"] == "coordinator"
    assert {s["code"] for s in r["sources"]} >= {"edf_factsheets"}
    assert client.get("/v1/signals/funding?programme=EDIDP").json()["total"] == 0     # its latest year is not new
    assert client.get("/v1/signals/funding?country=EE").json()["total"] == 1
    assert client.get("/v1/signals/funding?cpv=35").status_code == 422
    assert client.get("/v1/signals/funding?programme=NATO").status_code == 422


def test_the_first_rows_are_public_and_the_rest_is_the_paid_part(conn, client, sent, world, monkeypatch):
    many = []
    for i in range(signals.FREE_ROWS + 2):
        o = org(conn, f"Company {i:02d} AS", "NO")
        many.append(o)
        for d in (5, 6):
            win(conn, notice(conn, f"9{i:02d}-{d}", days_ago=d, country="NO", buyer="FMA"), o, "NO")
    conn.commit()
    public = client.get("/v1/signals/growing").json()
    assert public["total"] == signals.FREE_ROWS + 3 and len(public["items"]) == signals.FREE_ROWS
    assert client.get("/v1/signals/growing?page=2").status_code == 422            # no paging on the public answer

    session, _ = sign_in(client, sent)
    assert client.get("/v1/account/signals/growing").status_code == 401           # no session
    closed = client.get("/v1/account/signals/growing", headers=H(session))
    assert closed.status_code == 404 and closed.json()["error"] == "not_open"      # the switch is off by default

    monkeypatch.setenv("DGATE_SIGNALS_FULL_OPEN", "true")
    config.reset_cache()
    # no plan on sale yet: every account may (as billing.may)
    full = client.get("/v1/account/signals/growing?page=2&pageSize=10", headers=H(session))
    assert full.status_code == 200 and full.json()["total"] == signals.FREE_ROWS + 3 and len(full.json()["items"]) == 3
    assert full.headers["cache-control"] == "private, no-store"
    every = client.get(f"/v1/account/signals/growing?pageSize={signals.MAX_PAGE_SIZE}", headers=H(session)).json()
    assert [i["company"]["id"] for i in every["items"][:signals.FREE_ROWS]] == [i["company"]["id"] for i in public["items"]]

    # plans on sale: a free account is refused, a paying one is served
    _billing_env(monkeypatch)
    assert client.get("/v1/signals/growing").json()["fullOpen"] is True
    refused = client.get("/v1/account/signals/growing", headers=H(session))
    assert refused.status_code == 402 and refused.json()["error"] == "plan_required"
    conn.execute("""INSERT INTO billing_subscription (account_id, plan, period, status, last_event_id, last_event_at)
                    SELECT id, 'team', 'yearly', 'active', 'evt_test', now() FROM app_user""")
    conn.commit()
    assert client.get("/v1/account/signals/growing", headers=H(session)).status_code == 200
