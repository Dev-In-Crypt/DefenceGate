"""WP-87 (UX audit of 22 October 2026, section 2), the parts that need no database: the deadline a notice shows, the order of
the default list, the address after a legal form, the supplier merge's public-body guard, text read with the wrong encoding."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dgate.ops.org_dedupe import plan
from dgate.resolution.names import key_of
from dgate.tenders import core_first, shown_deadline

NOW = datetime(2026, 10, 22, 12, tzinfo=timezone.utc)


def test_a_passed_first_deadline_keeps_the_notices_own_later_one():
    own, twin = NOW + timedelta(days=400), NOW - timedelta(days=700)
    assert shown_deadline(own, twin, NOW) == (own, None, True)


def test_a_twin_deadline_still_ahead_replaces_a_distant_national_one_as_before():
    own, twin = NOW + timedelta(days=400), NOW + timedelta(days=20)
    assert shown_deadline(own, twin, NOW) == (twin, "ted_twin", False)
    # both passed: the twin's, as before (the notice is closed either way)
    assert shown_deadline(NOW - timedelta(days=1), NOW - timedelta(days=200), NOW)[1] == "ted_twin"


def test_close_deadlines_and_missing_ones_are_left_alone():
    own = NOW + timedelta(days=10)
    assert shown_deadline(own, own + timedelta(days=30), NOW) == (own, None, False)
    assert shown_deadline(own, None, NOW) == (own, None, False)
    assert shown_deadline(None, own, NOW) == (None, None, False)


def test_only_the_default_open_view_leads_with_core_notices():
    assert core_first("open", "relevant", None) and core_first("open", "relevant", "core-first")
    assert not core_first("open", "relevant", "deadline-asc")
    assert not core_first("closed", "relevant", None) and not core_first("open", "core", None)


def test_an_address_after_the_legal_form_is_not_part_of_the_name():
    assert key_of("HENSOLDT NEXEYA FRANCE SAS 1 rue de la Chaussee 91300 Massy")[0] == key_of("Hensoldt Nexeya France")[0]
    assert key_of("Rheinmetall Landsysteme GmbH, Heinrich-Ehrhardt-Str. 2, 29345 Unterluss")[0] == "rheinmetall landsysteme"
    # a number that is part of the name, or a form with nothing after it, is not cut
    assert key_of("Airbus Defence and Space GmbH")[0] == "airbus defence and space"
    assert key_of("Jednostka Wojskowa 4220")[0] == "jednostka wojskowa 4220"
    assert key_of("3M Deutschland GmbH")[0] == "3m deutschland"
    # the legacy key (stored aliases are found by it) is unchanged
    assert key_of("HENSOLDT NEXEYA FRANCE SAS 1 rue de la Chaussee 91300 Massy")[1].endswith("91300 massy")


def _row(i: int, name: str, country: str = "DE", **kw) -> dict:
    return {"id": i, "country": country, "canonical": name.lower(), "display": name, "pic": None, "reg": None,
            "vat": None, "suppressed": False, **kw}


def test_winners_of_one_name_are_merged_and_public_bodies_brought_in_by_winners_are_not():
    rows = [_row(1, "Hensoldt Optronics GmbH"), _row(2, "HENSOLDT Optronics GmbH"),
            _row(3, "Gmina Kolbuszowa", "PL"), _row(4, "Gmina Kolbuszowa", "PL"),
            _row(5, "Universite du Luxembourg", "LU"), _row(6, "UNIVERSITEDULUXEMBOURG", "LU")]
    groups, left = plan(rows, focus={1, 2, 3, 4, 5, 6}, projects={5})
    heads = {g.head: [m[0] for m in g.members] for g in groups}
    assert sorted(heads.items()) == [(1, [2]), (5, [6])]          # the university comes with a project, as before
    assert left == {"public_body": 1}
    assert plan(rows, focus={1, 2}, projects=set())[0][0].members[0][1:] == ("name_key", 0.95)


def test_no_text_was_read_with_the_wrong_encoding():
    """'e-ZamГіwienia' and 'Santa BГЎrbara' were UTF-8 read as Windows-1251 in demand.py's served text."""
    # a Latin letter followed by the Windows-1251 reading of a UTF-8 lead byte and of a continuation byte; real
    # Cyrillic words (the Bulgarian vocabulary of buyer_family.py) never follow a Latin letter directly
    garbled = re.compile(r"[A-Za-z][\u0413\u0420\u0421][\u0400-\u040f\u0450-\u045f\u0490\u0491\u00a0-\u00bf\u2013-\u203a\u2116\u20ac]|\u00c3[\u0080-\u00bf]")
    root = Path(__file__).resolve().parents[2] / "dgate"
    allowed = {"awards.py"}            # names the pattern it refuses ("Ã©" in a comment)
    bad = [str(f.relative_to(root)) for f in root.rglob("*.py")
           if f.name not in allowed and garbled.search(f.read_text(encoding="utf-8"))]
    assert bad == []
