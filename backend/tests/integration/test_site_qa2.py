"""Site QA round 2 (14 October 2026), package WP-7, against a real Postgres: what the
public pages and the CSV were told that the data does not say.

N3 buyer "open now" equals the buyer's own list, N4 "last changed" is the source's change
and not our reprocessing, N5 a call that never opened is closed, N2 what qualified a notice,
N6 the months a source is short of, N9 a retired ministry name, N15 a source suffix on a
buyer name.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from dgate import api, db, stats
from dgate.normalise import Call, Opportunity, normalise_org_name
from dgate.ops import buyer_cleanup

pytestmark = pytest.mark.integration

FUTURE = datetime.now(timezone.utc) + timedelta(days=30)


@pytest.fixture(autouse=True)
def _fresh_cache():
    stats.reset_cache()
    yield
    stats.reset_cache()


@pytest.fixture()
def client(conn):
    with TestClient(api.app) as c:
        yield c


def _opp(native_id="N-1", **over) -> Opportunity:
    base = dict(source_code="ted", native_id=native_id, buyer_name_raw="Ministry of Defence",
                title_original="Armoured vehicles", country="PL", published_at=date(2026, 10, 1),
                deadline_at=FUTURE, cpv_codes=["35400000"], status="open", is_defence=True,
                sig_cpv=True, sig_cpv_military=True)
    base.update(over)
    return Opportunity(**base)


def _store(conn, opp: Opportunity, digest: str) -> int:
    src = db.source_id(conn, opp.source_code)
    opp.buyer_org_id = db.resolve_organisation(conn, opp.buyer_name_raw, opp.country, src_id=src)
    oid, _ = db.upsert_opportunity(conn, opp, digest, src)
    conn.commit()
    return oid


def _at(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


# ------------------------------------------------------------------ N4

def test_last_changed_is_when_the_source_changed_the_notice_not_when_we_reprocessed_it(client, conn):
    oid = _store(conn, _opp(), "h1")
    _store(conn, _opp(deadline_at=FUTURE + timedelta(days=3)), "h2")          # the source amended it
    _store(conn, _opp(deadline_at=FUTURE + timedelta(days=3), status="awarded"), "h3")
    rows = conn.execute("SELECT id, version, observed_at FROM opportunity_version "
                        "WHERE opportunity_id = %s ORDER BY version", (oid,)).fetchall()
    assert len(rows) == 3
    db.annotate_versions(conn, [rows[2]["id"]], "remapped", "status re-derived from the same payload")
    run = db.start_run(conn, "ted", expected_min=1)
    db.finish_run(conn, run, fetched=10, new=1, changed=0, status="success")
    conn.commit()

    tender = client.get(f"/v1/tenders/{oid}").json()
    assert _at(tender["source"]["retrievedAt"]) == rows[1]["observed_at"]
    assert _at(tender["source"]["retrievedAt"]) != rows[2]["observed_at"]
    # and, separately, when we last looked at that source
    assert tender["source"]["checkedAt"] is not None
    assert _at(tender["source"]["checkedAt"]) >= rows[2]["observed_at"]


def test_a_notice_whose_only_later_version_is_ours_is_last_changed_when_first_seen(client, conn):
    oid = _store(conn, _opp(), "h1")
    _store(conn, _opp(status="awarded"), "h2")
    rows = conn.execute("SELECT id, observed_at FROM opportunity_version WHERE opportunity_id = %s "
                        "ORDER BY version", (oid,)).fetchall()
    db.annotate_versions(conn, [rows[1]["id"]], "remapped", "re-derived")
    conn.commit()
    tender = client.get(f"/v1/tenders/{oid}").json()
    assert _at(tender["source"]["retrievedAt"]) == rows[0]["observed_at"]


# ------------------------------------------------------------------ N3

def test_a_buyers_open_count_is_what_its_own_list_shows(client, conn):
    """A national notice and its TED twin of one buyer were two in the counter and one in
    the list (201 against 169 on 14 October 2026); a re-publication likewise."""
    ted = _store(conn, _opp("100-2026", title_original="Armoured vehicles"), "t1")
    nat = _store(conn, _opp("NAT-1", source_code="fr_boamp", title_original="Armoured vehicles"), "n1")
    conn.execute("UPDATE opportunity SET ted_ref = '100-2026', twin_method = 'stated_ted_ref' "
                 "WHERE id = %s", (nat,))
    _store(conn, _opp("200-2026", title_original="Night vision"), "t2")
    _store(conn, _opp("300-2026", title_original="Boots", status="awarded"), "t3")
    conn.commit()
    assert ted != nat

    buyer_id = conn.execute("SELECT buyer_org_id FROM opportunity WHERE id = %s", (ted,)).fetchone()[
        "buyer_org_id"]
    listed = client.get("/v1/tenders", params={"buyer": buyer_id, "status": "open"}).json()["total"]
    buyer = client.get(f"/v1/buyers/{buyer_id}").json()
    assert listed == 2
    assert buyer["openCount"] == listed
    assert buyer["tenderCount"] == 4            # every core notice, as documented


# ------------------------------------------------------------------ N5

def _call(conn, native_id, *, status, deadline_days, opens_days=None):
    call = Call(programme_code="HORIZON", native_id=native_id, title=f"Call {native_id}",
                topic_code=f"HORIZON-{native_id}", status=status, regime="defence",
                deadline_at=datetime.now(timezone.utc) + timedelta(days=deadline_days),
                opens_at=(date.today() + timedelta(days=opens_days)) if opens_days is not None
                else None)
    db.upsert_call(conn, call, f"hash-{native_id}", db.source_id(conn, "eu_portal"))
    conn.commit()


def test_a_call_that_never_opened_and_whose_deadline_has_passed_is_closed(client, conn):
    _call(conn, "late", status="forthcoming", deadline_days=-3, opens_days=-30)
    _call(conn, "soon", status="forthcoming", deadline_days=20, opens_days=5)
    items = {c["topicId"]: c["status"] for c in client.get(
        "/v1/funding", params={"status": "all"}).json()["items"]}
    assert items == {"HORIZON-late": "closed", "HORIZON-soon": "forthcoming"}
    listed = client.get("/v1/funding", params={"status": "forthcoming"}).json()["items"]
    assert [c["topicId"] for c in listed] == ["HORIZON-soon"]


# ------------------------------------------------------------------ N2

def test_what_qualified_a_notice_is_the_signal_not_any_code_in_its_list(client, conn):
    # a military code among many on a school board's notice; only its buyer keeps it in the scope
    civil = _store(conn, _opp("CIV-1", buyer_name_raw="Donegal Education and Training Board",
                              cpv_codes=["39162100", "35811300", "30192000"], sig_buyer=True,
                              buyer_class="education", legal_basis="32014L0024"), "c1")
    plain = _store(conn, _opp("MIL-1", buyer_name_raw="Armed Forces Procurement",
                              cpv_codes=["35400000", "33100000"]), "m1")
    got = client.get(f"/v1/tenders/{civil}").json()
    assert got["qualifiedBy"] == ["buyer"] and got["militaryCpv"] == []
    got = client.get(f"/v1/tenders/{plain}").json()
    assert got["qualifiedBy"] == ["military_cpv"]
    assert got["militaryCpv"] == ["35400000"]


# ------------------------------------------------------------------ N6

def test_the_months_a_source_is_short_of_are_counted_from_the_data(client, conn):
    counts = {1: 1, 2: 20, 3: 20, 4: 2, 5: 20, 6: 20, 7: 1}
    for month, n in counts.items():
        for i in range(n):
            _store(conn, _opp(f"G-{month}-{i}", published_at=date(2026, month, 5 + (i % 20))),
                   f"g{month}-{i}")
    sources = {s["id"]: s for s in client.get("/v1/sources").json()["sources"]}
    ted = sources["ted"]
    assert ted["monthlyMedian"] == 20
    assert ted["gapMonths"] == ["2026-04"]      # January and July are partial months


# ------------------------------------------------------------------ N9

def _org(conn, name, country="FR", number=None):
    """One organisation row of its own, whatever the resolver would have made of the name."""
    org_id = conn.execute(
        """INSERT INTO organisation (canonical_name, country, national_reg_no, is_defence_buyer)
           VALUES (%s, %s, %s, TRUE) RETURNING id""",
        (normalise_org_name(name), country, number)).fetchone()["id"]
    conn.commit()
    return org_id


def test_a_retired_ministry_name_joins_the_one_current_twin_and_leaves_the_ambiguous(conn):
    new = _org(conn, "MINARM/DGA/DO/S2A")
    # as the resolver makes it, with the alias the notices that state this name resolve by
    old = db.resolve_organisation(conn, "MINDEF/DGA/DO/S2A", "FR")
    conn.commit()
    lonely = _org(conn, "MINDEF/EMA/SCA/Cesga")
    _org(conn, "MINARM/AIR/SIAE", number="22222222222222")
    _org(conn, "MINARM/AIR/SIAE", number="33333333333333")
    amb = _org(conn, "MINDEF/AIR/SIAE")
    other_number = _org(conn, "MINDEF/DICOM", number="44444444444444")
    _org(conn, "MINARM/DICOM", number="55555555555555")

    plan = {e["did"]: e for e in buyer_cleanup.rename_plan(conn)}
    assert plan[old]["action"] == "merge" and plan[old]["keep"] == new
    assert plan[lonely]["action"] == "none"
    assert plan[amb]["action"] == "ambiguous"
    assert plan[other_number]["action"] == "distinct"

    done = buyer_cleanup.run(conn, apply=True, out=lambda *_: None)
    assert done["renamed_merged"] == 1
    row = conn.execute("SELECT merged_into, merge_method, merge_confidence FROM organisation "
                       "WHERE id = %s", (old,)).fetchone()
    assert row["merged_into"] == new and row["merge_method"] == "ministry_rename"
    assert float(row["merge_confidence"]) == 0.90
    # the survivor stands for the old name now: a notice that still says it reaches it
    assert db.resolve_organisation(conn, "MINDEF/DGA/DO/S2A", "FR") == new
    again = buyer_cleanup.run(conn, apply=True, out=lambda *_: None)
    assert again["renamed_merged"] == 0


# ------------------------------------------------------------------ N15

def test_a_source_suffix_is_not_part_of_the_buyer_name_a_page_shows(client, conn):
    oid = _store(conn, _opp("IE-1", buyer_name_raw="Irish Defence Forces_1144", country="IE"), "i1")
    tender = client.get(f"/v1/tenders/{oid}").json()
    assert tender["buyerName"] == "Irish Defence Forces"
    buyers = client.get("/v1/buyers", params={"q": "irish"}).json()["items"]
    assert buyers and "_1144" not in buyers[0]["name"]
    stored = conn.execute("SELECT buyer_name_raw FROM opportunity WHERE id = %s", (oid,)).fetchone()
    assert stored["buyer_name_raw"] == "Irish Defence Forces_1144"      # the source's own words stay
