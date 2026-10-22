"""WP-76: staged merge batches that record what agreed, and the undo of one batch by its window."""

from __future__ import annotations

import pytest

from dgate import db
from dgate.ops import accept_merge_candidates

pytestmark = pytest.mark.integration

QUIET = {"out": lambda *_: None, "with_office_splits": False}


def org(conn, name: str, *, country="ES", reg=None) -> int:
    oid = conn.execute(
        """INSERT INTO organisation (canonical_name, country, confidence, review_status, national_reg_no)
           VALUES (%s, %s, 0.95, 'auto', %s) RETURNING id""", (name, country, reg)).fetchone()["id"]
    conn.execute(
        """INSERT INTO organisation_alias (organisation_id, raw_name, normalised_name, country_hint,
                                           match_method, confidence)
           VALUES (%s, %s, %s, %s, 'exact_name', 0.95)""", (oid, name, name, country))
    return oid


def candidate(conn, a: int, b: int) -> None:
    db.add_merge_candidate(conn, a, b, method="identifier", confidence=0.97,
                           evidence="carries the identifier", detected_by="resolve_organisation")


def merged(conn) -> dict[int, tuple]:
    return {r["id"]: (r["merged_into"], r["merge_method"], float(r["merge_confidence"]))
            for r in conn.execute("SELECT id, merged_into, merge_method, merge_confidence "
                                  "FROM organisation WHERE merged_into IS NOT NULL").fetchall()}


def test_batches_merge_in_steps_record_what_agreed_and_one_batch_is_undone_by_its_window(conn):
    groups = []
    for i, (name, other) in enumerate([("acme naval", "acme naval s a"), ("beta systems", "beta-systems"),
                                       ("gamma optics", "gamma optic")]):
        a, b = org(conn, name, reg=f"A{i}"), org(conn, other)
        candidate(conn, a, b)
        groups.append((a, b))
    # a number and nothing else that agrees: waits for a person
    p, q = org(conn, "posten norge", country="NO", reg="984661185"), org(conn, "posten bring", country="NO")
    candidate(conn, p, q)
    # a local authority's SIRET: refused as public, whatever the names
    c, d = org(conn, "acme ville", country="FR", reg="21370243400019"), org(conn, "acme ville bis", country="FR")
    candidate(conn, c, d)
    conn.commit()

    dry = accept_merge_candidates.run(conn, **QUIET)
    assert (dry["accepted_candidates"], dry["groups"], dry["left_pending"]) == (3, 3, 1)
    assert dry["refused"] == {"no_second_signal": 1, "public_body": 1}
    assert merged(conn) == {}

    first = accept_merge_candidates.run(conn, apply=True, limit=1, sample=5, **QUIET)
    assert first["merged"] == 1 and first["rejected_public_units"] == 1
    assert [s["method"] for s in first["batch_sample"]] == ["identifier+name"]
    a0, b0 = groups[0]
    assert merged(conn) == {b0: (a0, "identifier+name", 0.98)}
    second = accept_merge_candidates.run(conn, apply=True, limit=1, **QUIET)
    rest = accept_merge_candidates.run(conn, apply=True, **QUIET)
    assert (second["merged"], rest["merged"]) == (1, 1)
    assert len(merged(conn)) == 3
    assert accept_merge_candidates.run(conn, apply=True, **QUIET)["merged"] == 0

    # undo the second batch only: dry run first, then by its window
    window = second["batch_window"]
    assert accept_merge_candidates.undo_batch(conn, *window, out=lambda *_: None)["applied"] is False
    assert len(merged(conn)) == 3
    undone = accept_merge_candidates.undo_batch(conn, *window, apply=True, out=lambda *_: None)
    assert (undone["rows"], undone["aliases"], undone["candidates_pending"], undone["candidates_undone"]) \
        == (1, 1, 1, 1)
    a1, b1 = groups[1]
    assert b1 not in merged(conn) and {b0, groups[2][1]} == set(merged(conn))
    alias = conn.execute("SELECT organisation_id, prev_organisation_id FROM organisation_alias "
                         "WHERE normalised_name = 'beta-systems'").fetchone()
    assert (alias["organisation_id"], alias["prev_organisation_id"]) == (b1, None)
    status = {(r["match_method"], r["detected_by"]): r["status"] for r in conn.execute(
        "SELECT match_method, detected_by, status FROM organisation_merge_candidate "
        "WHERE organisation_id = %s AND candidate_org_id = %s", (min(a1, b1), max(a1, b1))).fetchall()}
    assert status == {("identifier", "resolve_organisation"): "pending",
                      ("identifier+name", accept_merge_candidates.DETECTED_BY): "undone"}
    # the lone number and the public pair were never touched by the undo
    assert {r["status"] for r in conn.execute(
        "SELECT status FROM organisation_merge_candidate WHERE organisation_id IN (%s, %s)", (p, c))} \
        == {"pending", "rejected_public_units"}
    # a second undo of the same window finds nothing
    assert accept_merge_candidates.undo_batch(conn, *window, apply=True, out=lambda *_: None)["rows"] == 0
