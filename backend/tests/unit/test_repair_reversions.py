"""Planning the repair of histories that recorded re-read content as change.

The fixture is the real notice found on 13 September 2026: one change -- open on
the 7th, awarded on the 8th -- archived as twelve versions alternating between
the same two payloads, with "open" left current.
"""

from __future__ import annotations

from dgate.ops.repair_reversions import plan_repair

AWARDED = {"published_at": "2026-09-08", "status": "awarded"}
OPEN = {"published_at": "2026-09-07", "status": "open"}


def history(*states):
    return [{"id": 100 + i, "version": i + 1, "raw_hash": h, "payload": p}
            for i, (h, p) in enumerate(states)]


def test_the_real_flipping_history_is_planned_correctly():
    rows = history(*[("A", AWARDED), ("B", OPEN)] * 6)
    plan = plan_repair(1, "2026/ETSAE0906/00002554E", rows)

    kinds = {v: kind for v, kind, _ in plan.notes}
    # v2 is the first sight of the older call: history arriving late.
    assert kinds[2] == "out_of_order"
    # Every later version re-reads content already archived.
    assert all(kinds[v] == "reread" for v in range(3, 13))
    assert 1 not in kinds
    # The award is the true current state, and v12 says otherwise.
    assert plan.correct_to == 1


def test_a_history_in_the_right_order_is_left_alone():
    plan = plan_repair(1, "x", history(("B", OPEN), ("A", AWARDED)))
    assert plan.notes == []
    assert plan.correct_to is None


def test_a_flipping_history_that_ends_on_the_right_state_gets_notes_but_no_correction():
    plan = plan_repair(1, "x", history(("B", OPEN), ("A", AWARDED), ("B", OPEN), ("A", AWARDED)))
    assert plan.correct_to is None
    assert [kind for _, kind, _ in plan.notes] == ["reread", "reread"]


def test_same_day_contents_prefer_the_one_archived_last():
    morning = {"published_at": "2026-09-08", "status": "open"}
    evening = {"published_at": "2026-09-08", "status": "awarded"}
    plan = plan_repair(1, "x", history(("M", morning), ("E", evening), ("M", morning)))
    assert plan.correct_to == 2


def test_a_correction_is_never_marked_as_a_reread():
    """A correction repeats the content it restores. The first version of this
    repair, run twice, marked all 53 corrections `reread` -- telling clients to
    hide the only right version of each notice."""
    rows = history(("A", AWARDED), ("B", OPEN), ("A", AWARDED))
    rows[2]["is_correction"] = True
    plan = plan_repair(1, "x", rows)
    assert all(v != 3 for v, _, _ in plan.notes)
    assert plan.correct_to is None
