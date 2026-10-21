"""WP-74: undo the merge batch of 21 October 2026, and never merge public bodies by a shared tax id."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from dgate import db
from dgate.normalise import Opportunity
from dgate.ops import accept_merge_candidates, buyer_families, undo_merges

pytestmark = pytest.mark.integration

FUTURE = datetime.now(timezone.utc) + timedelta(days=30)
QUIET = {"out": lambda *_: None}


def org(conn, name: str, *, country="ES", reg=None, method=None, defence=False) -> int:
    oid = conn.execute(
        """INSERT INTO organisation (canonical_name, country, confidence, review_status, national_reg_no,
                                     identifier_method, identifier_confidence, is_defence_buyer)
           VALUES (%s, %s, 0.95, 'auto', %s, %s, %s, %s) RETURNING id""",
        (name, country, reg, method, 0.90 if method else None, defence)).fetchone()["id"]
    conn.execute(
        """INSERT INTO organisation_alias (organisation_id, raw_name, normalised_name, country_hint,
                                           match_method, confidence)
           VALUES (%s, %s, %s, %s, 'exact_name', 0.95)""", (oid, name, name, country))
    return oid


def notice(conn, native_id: str, buyer: int, *, country="ES") -> int:
    opp = Opportunity(source_code="ted", native_id=native_id, buyer_name_raw=f"buyer {buyer}",
                      title_original="Armoured vehicles", country=country, published_at=date.today(),
                      deadline_at=FUTURE, cpv_codes=["35400000"], status="open", is_defence=True,
                      sig_cpv=True, sig_cpv_military=True, dual_use=False, buyer_class="defence")
    opp.buyer_org_id = buyer
    oid, _ = db.upsert_opportunity(conn, opp, f"hash-{native_id}", db.source_id(conn, "ted"))
    return oid


def candidate(conn, a: int, b: int) -> None:
    db.add_merge_candidate(conn, a, b, method="identifier", confidence=0.97,
                           evidence="carries identifier R1", detected_by="resolve_organisation")


def buyer_of(conn, oid: int) -> int:
    return conn.execute("SELECT buyer_org_id AS b FROM opportunity WHERE id = %s", (oid,)).fetchone()["b"]


def row(conn, oid: int) -> dict:
    return conn.execute("SELECT * FROM organisation WHERE id = %s", (oid,)).fetchone()


@pytest.fixture()
def batch(conn):
    """The WP-72 merge as it ran: three company-named rows sharing number R1 (held by `one`, which is
    a defence buyer), merged into `head` (most notices), and `old`, merged into `two` the week before
    and staying merged."""
    head = org(conn, "acme holding")
    one = org(conn, "acme one", reg="R1", method="identifier", defence=True)
    two = org(conn, "acme two")
    old = org(conn, "acme two old")
    n = {"head": [notice(conn, f"H-{i}", head) for i in range(3)], "one": notice(conn, "O-1", one),
         "old": notice(conn, "X-1", old)}
    db.merge_organisations(conn, two, old, method="name_key", confidence=0.95, evidence="same key",
                           detected_by="ops.org_dedupe")
    conn.execute("UPDATE organisation SET merged_at = now() - interval '7 days' WHERE id = %s", (old,))
    candidate(conn, head, one)
    candidate(conn, one, two)
    conn.commit()
    start = conn.execute("SELECT now() - interval '1 second' AS t").fetchone()["t"]
    # what `accept_merge_candidates --yes` did then, step by step (its rule now refuses this group:
    # `one` is a defence buyer)
    for member in (one, two):
        db.merge_organisations(conn, head, member, method="identifier", confidence=0.97,
                               evidence="carries identifier R1",
                               detected_by=accept_merge_candidates.DETECTED_BY)
    conn.execute("UPDATE organisation_merge_candidate SET status = 'merged', decided_at = now() "
                 "WHERE status = 'pending' AND match_method = 'identifier'")
    conn.commit()
    end = start + timedelta(hours=1)
    return {"head": head, "one": one, "two": two, "old": old, "n": n,
            "window": {"start": start.isoformat(), "end": end.isoformat(), "expected": 2}}


def test_the_merge_did_what_the_undo_must_reverse(conn, batch):
    b = batch
    assert row(conn, b["one"])["merged_into"] == b["head"] and row(conn, b["two"])["merged_into"] == b["head"]
    assert row(conn, b["head"])["national_reg_no"] == "R1" and row(conn, b["one"])["national_reg_no"] is None
    assert row(conn, b["head"])["is_defence_buyer"]
    assert {buyer_of(conn, b["n"]["one"]), buyer_of(conn, b["n"]["old"])} == {b["head"]}


def test_the_undo_reverses_exactly_the_batch_and_runs_once(conn, batch):
    b, w = batch, batch["window"]
    dry = undo_merges.run(conn, refresh=False, **w, **QUIET)
    assert (dry["rows"], dry["heads"], dry["notices"], dry["notices_kept_on_head"]) == (2, 1, 2, 3)
    assert (dry["aliases"], dry["numbers_restored"], dry["flags_cleared"]) == (3, 1, 1)
    assert (dry["candidates_pending"], dry["candidates_undone"]) == (2, 1)
    assert {s["notice"] for s in dry["sample"]} == {b["n"]["one"], b["n"]["old"]}
    assert row(conn, b["one"])["merged_into"] == b["head"]            # a dry run writes nothing

    done = undo_merges.run(conn, apply=True, **w, **QUIET)
    assert done["applied"] and done["directory_rows"] == 0
    for k in ("one", "two"):
        r = row(conn, b[k])
        assert (r["merged_into"], r["merge_method"], r["merge_confidence"], r["merged_at"]) == (None,) * 4
    assert row(conn, b["old"])["merged_into"] == b["two"]           # the earlier merge stays
    # notices go back to the row their archived version names, followed through the merges that stay
    assert buyer_of(conn, b["n"]["one"]) == b["one"] and buyer_of(conn, b["n"]["old"]) == b["two"]
    assert {buyer_of(conn, x) for x in b["n"]["head"]} == {b["head"]}
    aliases = {r["normalised_name"]: (r["organisation_id"], r["prev_organisation_id"]) for r in conn.execute(
        "SELECT normalised_name, organisation_id, prev_organisation_id FROM organisation_alias").fetchall()}
    assert aliases == {"acme holding": (b["head"], None), "acme one": (b["one"], None),
                       "acme two": (b["two"], None), "acme two old": (b["two"], b["old"])}
    # the number back on the row that held it, the flag off the head that never had one
    h, one = row(conn, b["head"]), row(conn, b["one"])
    assert (h["national_reg_no"], h["identifier_method"], h["identifier_confidence"]) == (None, None, None)
    assert (one["national_reg_no"], one["identifier_method"]) == ("R1", "identifier")
    assert not h["is_defence_buyer"] and one["is_defence_buyer"]
    status = sorted((r["detected_by"], r["status"]) for r in conn.execute(
        "SELECT detected_by, status FROM organisation_merge_candidate WHERE match_method = 'identifier'"))
    assert status == [("ops.accept_merge_candidates", "undone"),
                      ("resolve_organisation", "pending"), ("resolve_organisation", "pending")]
    # the archive is untouched: versions keep the ids they were written with
    assert conn.execute("SELECT count(*) AS n FROM opportunity_version").fetchone()["n"] == 5

    again = undo_merges.run(conn, apply=True, **w, **QUIET)
    assert again == {"rows": 0, "applied": False}


def test_the_undo_stops_when_the_window_does_not_hold_the_expected_batch(conn, batch):
    w = dict(batch["window"], expected=6641)
    with pytest.raises(undo_merges.BatchMismatch):
        undo_merges.run(conn, apply=True, **w, **QUIET)
    assert row(conn, batch["one"])["merged_into"] == batch["head"]


def test_a_head_seeded_as_a_defence_buyer_keeps_its_flag(conn, batch, monkeypatch):
    monkeypatch.setattr(undo_merges, "_seeded", lambda _c: {("ES", "acme holding")})
    undo_merges.run(conn, apply=True, refresh=False, **batch["window"], **QUIET)
    assert row(conn, batch["head"])["is_defence_buyer"]


def test_public_units_sharing_a_tax_id_become_one_buyer_family_and_companies_still_merge(conn):
    parent = org(conn, "gobierno vasco", reg="S4833001C")
    security = org(conn, "gobierno vasco departamento de seguridad")
    health = org(conn, "gobierno vasco departamento de salud")
    bec = org(conn, "bilbao exhibition centre", reg="A95135984")
    bec2 = org(conn, "bec bilbao exhibition centre s a")
    for i in range(2):
        notice(conn, f"S-{i}", security)
    notice(conn, "Z-0", health)
    notice(conn, "B-0", bec2)
    candidate(conn, parent, security)
    candidate(conn, parent, health)
    candidate(conn, bec, bec2)
    conn.commit()

    dry = accept_merge_candidates.run(conn, with_office_splits=False, **QUIET)
    assert dry["refused"] == {"public_body": 2} and dry["rows_to_merge"] == 1
    assert dry["families"]["members"] == 2 and len(dry["public_sample"]) == 2

    done = accept_merge_candidates.run(conn, apply=True, with_office_splits=False, **QUIET)
    assert done["merged"] == 1 and done["rejected_public_units"] == 2
    assert row(conn, bec)["merged_into"] == bec2          # the head holds the notice
    assert all(row(conn, x)["merged_into"] is None for x in (parent, security, health))
    fam = {r["org_id"]: (r["head_org_id"], r["method"]) for r in conn.execute(
        "SELECT org_id, head_org_id, method FROM buyer_family_member").fetchall()}
    assert fam == {security: (parent, "shared_tax_id"), health: (parent, "shared_tax_id")}
    assert {r["status"] for r in conn.execute(
        "SELECT status FROM organisation_merge_candidate WHERE organisation_id = %s", (parent,))} \
        == {"rejected_public_units"}
    # the daily family job keeps them (it rebuilds the table from the stored pairs)
    kept = buyer_families.run(conn, write=True)
    assert (kept["written"], kept["removed"], kept["members"]) == (0, 0, 2)
    assert accept_merge_candidates.run(conn, apply=True, with_office_splits=False, **QUIET)["merged"] == 0


def test_units_with_no_parent_row_stay_apart(conn):
    a = org(conn, "ayuntamiento de madrid area de gobierno de economia")
    b = org(conn, "ayuntamiento de madrid area de gobierno de seguridad")
    notice(conn, "A-0", a)
    notice(conn, "B-0", b)
    candidate(conn, a, b)
    conn.commit()
    accept_merge_candidates.run(conn, apply=True, with_office_splits=False, **QUIET)
    assert conn.execute("SELECT count(*) AS n FROM buyer_family_member").fetchone()["n"] == 0
    assert row(conn, a)["merged_into"] is None and row(conn, b)["merged_into"] is None
