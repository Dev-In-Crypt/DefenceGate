"""The archive stops recording noise, the timeline stops showing it, and a bulk
correction can be annotated so it is never counted as an amendment.

Each test is a shape found by the audit of 12 October 2026 against production.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import psycopg
import pytest
from fastapi.testclient import TestClient

from dgate import api, db
from dgate.normalise import Opportunity

pytestmark = pytest.mark.integration

FUTURE = datetime.now(timezone.utc) + timedelta(days=30)
CEST = timezone(timedelta(hours=2))


@pytest.fixture()
def client(conn):
    with TestClient(api.app) as c:
        yield c


def _opp(native_id="N-1", **over) -> Opportunity:
    base = dict(source_code="ted", native_id=native_id, buyer_name_raw="Ministry of Defence",
                title_original="Armoured vehicles", country="PL", published_at=date(2026, 10, 1),
                deadline_at=FUTURE, cpv_codes=["35400000", "35410000"], status="open",
                is_defence=True, sig_cpv=True)
    base.update(over)
    return Opportunity(**base)


def _store(conn, opp: Opportunity, digest: str):
    src_id = db.source_id(conn, opp.source_code)
    opp.buyer_org_id = db.resolve_organisation(conn, opp.buyer_name_raw, opp.country, src_id=src_id)
    result = db.upsert_opportunity(conn, opp, digest, src_id)
    conn.commit()
    return result


def _versions(conn, opp_id):
    return conn.execute("SELECT id, version, changed_fields FROM opportunity_version "
                        "WHERE opportunity_id = %s ORDER BY version", (opp_id,)).fetchall()


# ------------------------------------------------------------- the write side

def test_a_cpv_list_re_ordered_by_the_source_writes_no_version(conn):
    opp_id, _ = _store(conn, _opp(), "h1")
    again = _opp(cpv_codes=["35410000", "35400000"])
    assert _store(conn, again, "h2") == (opp_id, "unchanged")
    assert len(_versions(conn, opp_id)) == 1


def test_a_deadline_written_with_another_offset_writes_no_version(conn):
    deadline = datetime(2026, 12, 9, 23, 59, tzinfo=CEST)
    opp_id, _ = _store(conn, _opp(deadline_at=deadline), "h1")
    same_moment = _opp(deadline_at=deadline.astimezone(timezone.utc))
    assert _store(conn, same_moment, "h2") == (opp_id, "unchanged")
    assert len(_versions(conn, opp_id)) == 1


def test_a_real_change_beside_a_re_ordering_lists_only_the_real_one(conn):
    opp_id, _ = _store(conn, _opp(), "h1")
    changed = _opp(cpv_codes=["35410000", "35400000"], value_amount=500000.0, value_currency="EUR")
    assert _store(conn, changed, "h2") == (opp_id, "changed")
    assert _versions(conn, opp_id)[1]["changed_fields"] == ["value_amount", "value_currency"]


def test_a_cpv_code_that_really_changes_is_still_recorded(conn):
    opp_id, _ = _store(conn, _opp(), "h1")
    assert _store(conn, _opp(cpv_codes=["35400000"]), "h2") == (opp_id, "changed")
    assert _versions(conn, opp_id)[1]["changed_fields"] == ["cpv_codes"]


def test_a_new_version_does_not_erase_a_link_or_attribute_set_outside_any_version(conn):
    """Review finding of 13 October 2026. `link_twins` sets `ted_ref` on a row with no
    version; the next version of that notice was built from a payload without it, wrote
    NULL over it, and left `twin_method` saying it had been linked."""
    opp_id, _ = _store(conn, _opp(source_code="fr_boamp"), "h1")
    conn.execute(
        """UPDATE opportunity SET ted_ref = '100-2026', twin_method = 'procedure_id',
                  twin_confidence = 0.98, procedure_identifier = 'proc-1', lot_count = 2,
                  buyer_identifier = '12345678', notice_subtype = '16', value_kind = 'estimated',
                  related_native_id = 'PARENT-1' WHERE id = %s""", (opp_id,))
    conn.commit()

    assert _store(conn, _opp(source_code="fr_boamp", value_amount=9.0, value_currency="EUR"),
                  "h2") == (opp_id, "changed")
    row = conn.execute("SELECT * FROM opportunity WHERE id = %s", (opp_id,)).fetchone()
    assert (row["ted_ref"], row["twin_method"]) == ("100-2026", "procedure_id")
    assert (row["procedure_identifier"], row["lot_count"], row["buyer_identifier"]) == (
        "proc-1", 2, "12345678")
    assert (row["notice_subtype"], row["value_kind"], row["related_native_id"]) == (
        "16", "estimated", "PARENT-1")
    assert float(row["value_amount"]) == 9.0

    # a version that does state a value replaces it
    assert _store(conn, _opp(source_code="fr_boamp", value_amount=10.0, value_currency="EUR",
                             ted_ref="200-2026"), "h3") == (opp_id, "changed")
    assert conn.execute("SELECT ted_ref FROM opportunity WHERE id = %s",
                        (opp_id,)).fetchone()["ted_ref"] == "200-2026"


# ---------------------------------------------------------------- the notes

def test_the_note_kind_remapped_is_accepted_and_the_old_kinds_still_are(conn):
    opp_id, _ = _store(conn, _opp(), "h1")
    version_id = _versions(conn, opp_id)[0]["id"]
    for kind in ("reread", "out_of_order", "correction", "remapped"):
        assert db.annotate_versions(conn, [version_id], kind, f"a {kind} note") == 1
    conn.commit()
    with pytest.raises(psycopg.errors.CheckViolation):
        db.annotate_versions(conn, [version_id], "bulk", "not a kind")
    conn.rollback()


def test_annotating_is_idempotent_and_takes_a_batch(conn):
    opp_id, _ = _store(conn, _opp(), "h1")
    _store(conn, _opp(value_amount=1.0, value_currency="EUR"), "h2")
    ids = [v["id"] for v in _versions(conn, opp_id)]
    assert db.annotate_versions(conn, ids, "remapped", "status re-derived") == 2
    assert db.annotate_versions(conn, ids, "remapped", "status re-derived") == 0
    assert db.annotate_versions(conn, [], "remapped", "nothing") == 0
    conn.commit()


# ------------------------------------------------------------ the timeline

def _tender(client, opp_id):
    return client.get(f"/v1/tenders/{opp_id}").json()


def test_a_remapped_version_is_not_counted_or_listed_as_an_amendment(client, conn):
    opp_id, _ = _store(conn, _opp(), "h1")
    _store(conn, _opp(status="awarded"), "h2")
    assert _tender(client, opp_id)["versionCount"] == 2
    assert _tender(client, opp_id)["amended"] is True

    ids = [v["id"] for v in _versions(conn, opp_id)]
    db.annotate_versions(conn, ids[1:], "remapped", "status re-derived from the same payload")
    conn.commit()

    tender = _tender(client, opp_id)
    assert (tender["versionCount"], tender["amended"]) == (1, False)
    # The history still shows the state the archive holds, marked as our correction (WP-59, data re-audit NEW-1).
    versions = client.get(f"/v1/tenders/{opp_id}/versions").json()
    assert [(v["version"], v["correction"]) for v in versions] == [(2, True), (1, False)]


def test_a_feed_date_move_is_not_an_amendment_and_the_count_agrees(client, conn):
    opp_id, _ = _store(conn, _opp(), "h1")
    _store(conn, _opp(published_at=date(2026, 10, 3)), "h2")
    assert _versions(conn, opp_id)[1]["changed_fields"] == ["published_at"]   # kept, honestly

    tender = _tender(client, opp_id)
    assert (tender["versionCount"], tender["amended"]) == (1, False)
    assert [v["version"] for v in client.get(f"/v1/tenders/{opp_id}/versions").json()] == [1]


def test_the_archive_endpoint_agrees_with_the_timeline_on_what_an_amendment_is(client, conn):
    """Review finding of 13 October 2026: `/v1/opportunities/{id}/versions` counted a
    version that only moved the publication date as an amendment, which the timeline and
    the pulse already hid."""
    opp_id, _ = _store(conn, _opp(), "h1")
    _store(conn, _opp(published_at=date(2026, 10, 3)), "h2")
    body = client.get(f"/v1/opportunities/{opp_id}/versions").json()
    assert body["version_count"] == 2 and body["amended"] is False

    _store(conn, _opp(published_at=date(2026, 10, 3), status="awarded"), "h3")
    body = client.get(f"/v1/opportunities/{opp_id}/versions").json()
    assert body["version_count"] == 3 and body["amended"] is True
    assert _tender(client, opp_id)["amended"] is True


def test_a_deadline_extension_is_listed_in_utc_with_its_label(client, conn):
    """Notice 2844: stored 23:59 at +02:00, which is 21:59 UTC."""
    first = datetime(2026, 9, 17, 23, 59, tzinfo=CEST)
    second = datetime(2026, 10, 9, 23, 59, tzinfo=CEST)
    opp_id, _ = _store(conn, _opp(deadline_at=first), "h1")
    _store(conn, _opp(deadline_at=second, published_at=date(2026, 10, 2)), "h2")

    versions = client.get(f"/v1/tenders/{opp_id}/versions").json()
    assert [v["version"] for v in versions] == [2, 1]
    lines = {c["field"]: (c["before"], c["after"]) for c in versions[0]["changes"]}
    assert lines["deadline_at"] == ("17 Sep 2026, 21:59 UTC", "9 Oct 2026, 21:59 UTC")
    assert [v["sequence"] for v in versions] == [2, 1]


def test_a_line_that_reads_the_same_before_and_after_is_not_served(client, conn):
    """Archived before the fix: a version that lists a CPV change whose two sides are
    the same codes in another order, beside a status change."""
    opp_id, _ = _store(conn, _opp(), "h1")
    _store(conn, _opp(status="awarded"), "h2")
    # Rewritten through the archive's own append path, as old runs did.
    latest = _versions(conn, opp_id)[-1]
    opp = _opp(status="cancelled", cpv_codes=["35410000", "35400000"])
    opp.buyer_org_id = None
    db.append_version(conn, opp_id, opp, "h3", ["status", "cpv_codes"], after=latest["version"])
    conn.commit()

    versions = client.get(f"/v1/tenders/{opp_id}/versions").json()
    newest = versions[0]
    assert newest["version"] == 3
    assert [c["field"] for c in newest["changes"]] == ["status"]


def test_a_version_archived_with_only_a_re_ordering_is_not_an_amendment(client, conn):
    opp_id, _ = _store(conn, _opp(), "h1")
    opp = _opp(cpv_codes=["35410000", "35400000"], published_at=date(2026, 10, 2))
    db.append_version(conn, opp_id, opp, "h2", ["published_at", "cpv_codes"], after=1)
    conn.commit()
    assert _tender(client, opp_id)["versionCount"] == 1
    assert [v["version"] for v in client.get(f"/v1/tenders/{opp_id}/versions").json()] == [1]


# ---------------------------------------------------------------- the buyer

def test_a_tender_names_its_buyer_as_the_notice_does_and_keeps_the_organisation(client, conn):
    """One organisation (the resolver folds case), two spellings in its notices: the
    notice shows its own, and the organisation's commonest rides beside it."""
    _store(conn, _opp("A-1", buyer_name_raw="Ministry of Defence"), "a1")
    _store(conn, _opp("A-2", buyer_name_raw="Ministry of Defence"), "a2")
    third, _ = _store(conn, _opp("A-3", buyer_name_raw="MINISTRY OF DEFENCE"), "a3")
    body = client.get("/v1/tenders", params={"status": "all", "scope": "all"}).json()["items"]
    by_id = {t["noticeId"]: t for t in body}
    assert by_id["A-3"]["buyerName"] == "MINISTRY OF DEFENCE"
    assert by_id["A-3"]["buyerCanonicalName"] == "Ministry of Defence"
    assert by_id["A-1"]["buyerName"] == by_id["A-1"]["buyerCanonicalName"] == "Ministry of Defence"
    assert by_id["A-3"]["buyerSlug"] == by_id["A-1"]["buyerSlug"]
    assert client.get(f"/v1/tenders/{third}").json()["buyerName"] == "MINISTRY OF DEFENCE"
    buyers = client.get("/v1/buyers").json()["items"]
    assert [b["name"] for b in buyers] == ["Ministry of Defence"]


# ------------------------------------------------------- lots, anomalies

def test_lots_come_from_the_stored_count_and_are_null_without_one(client, conn):
    with_lots, _ = _store(conn, _opp("L-1"), "l1")
    without, _ = _store(conn, _opp("L-2"), "l2")
    conn.execute("UPDATE opportunity SET lot_count = 4 WHERE id = %s", (with_lots,))
    conn.commit()
    assert _tender(client, with_lots)["lots"] == 4
    assert _tender(client, without)["lots"] is None


def test_the_anomalies_are_computed_and_named(client, conn):
    today = date.today()
    before_publication, _ = _store(
        conn, _opp("D-1", published_at=today - timedelta(days=2),
                   deadline_at=datetime.now(timezone.utc) - timedelta(days=5)), "d1")
    far, _ = _store(conn, _opp("D-2", deadline_at=datetime.now(timezone.utc)
                               + timedelta(days=365 * 6)), "d2")
    normal, _ = _store(conn, _opp("D-3"), "d3")
    assert _tender(client, before_publication)["anomalies"] == ["deadline-before-publication"]
    assert _tender(client, far)["anomalies"] == ["deadline-more-than-3y"]
    assert _tender(client, normal)["anomalies"] == []


def test_the_procedure_is_served_in_source_casing_and_ted_codes_are_spelled_out(client, conn):
    nc, _ = _store(conn, _opp("P-1", procedure_type="Procédure NC"), "p1")
    code, _ = _store(conn, _opp("P-2", procedure_type="neg-w-call"), "p2")
    assert _tender(client, nc)["procedure"] == "Procédure NC"
    assert _tender(client, code)["procedure"] == "Negotiated procedure with prior call for competition"


def test_the_public_amended_share_ignores_a_feed_date_move_and_a_remapped_version(conn):
    from dgate import accounts

    _store(conn, _opp("M-1"), "m1")
    _store(conn, _opp("M-1", published_at=date(2026, 10, 3)), "m2")      # feed date only
    remapped, _ = _store(conn, _opp("M-2"), "r1")
    _store(conn, _opp("M-2", status="awarded"), "r2")
    _store(conn, _opp("M-3"), "x1")
    _store(conn, _opp("M-3", value_amount=7.0, value_currency="EUR"), "x2")
    db.annotate_versions(conn, [v["id"] for v in _versions(conn, remapped)[1:]],
                         "remapped", "status re-derived")
    conn.execute("UPDATE opportunity SET published_at = %s", (date.today(),))
    conn.commit()
    accounts._cache.clear()
    assert accounts.pulse(conn)["amendedShare30d"] == round(1 / 3, 3)
