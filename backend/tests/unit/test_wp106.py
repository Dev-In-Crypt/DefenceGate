"""WP-106 (persona round of 24 October 2026: tender pages, lists, exports) without a database: the subject of a notice
whose description carries part numbers or only says what changed, the list's new orders and their indexes, the CPV titles."""

from __future__ import annotations

from pathlib import Path

import pytest

from dgate import tenders

MIGRATION = Path(__file__).resolve().parents[2] / "migrations" / "0118_wp106_list_sorts.sql"


@pytest.mark.parametrize("text, subject", [
    # BAAINBw 37631: the part's name and its NATO stock number (13 digits): the number goes, the name stays
    ("GELENKWELLE MIT AUSGLEICHSGELENK, FAHRZE 2520410039852", "GELENKWELLE MIT AUSGLEICHSGELENK, FAHRZE"),
    ("6003114831-BAAINBw Ersatzteile Leopard 2", "BAAINBw Ersatzteile Leopard 2"),
    # BOAMP 269322: the description of a change notice is not the subject
    ("Modification de la date limite de réception des offres", None),
    ("Änderung der Angebotsfrist.", None),
    ("Corrigendum: extension of the time limit.", None),
    # a phone number stays a contact: never shown, with or without separators
    ("Questions: +49 30 1234 5678.", None),
    ("Questions to Mr Huber, tel. 030 1234 5678.", None),
    # a short number is not taken out (a lot or a quantity)
    ("Supply of 400 helmets in 3 lots.", "Supply of 400 helmets in 3 lots."),
])
def test_the_subject_drops_part_numbers_and_change_texts(text, subject):
    assert tenders.commercial_subject(text) == subject


def test_the_list_can_be_ordered_by_value_and_by_code_and_each_order_has_its_index():
    eff = "EFF"
    assert tenders.tender_order("value-desc", "all", eff) == tenders.ORDER_VALUE_DESC
    assert tenders.tender_order("cpv-asc", "closed", eff) == tenders.ORDER_CPV_ASC
    # EUR first, each other currency by itself, placeholders (0, 0.01, 1) with the notices that state none
    cur = f"(CASE WHEN o.value_amount > {tenders.PLACEHOLDER_VALUE_MAX} THEN o.value_currency END)"
    assert tenders.ORDER_VALUE_DESC.startswith(f"({cur} IS DISTINCT FROM 'EUR'), {cur} ASC NULLS LAST,")
    # the index of migration 0118 is over the order's own expressions (without the alias), or the planner sorts
    sql = " ".join(MIGRATION.read_text(encoding="utf-8").split())
    for order in (tenders.ORDER_VALUE_DESC, tenders.ORDER_CPV_ASC):
        assert order.replace("o.", "") in sql
    for value in ("open-first", "value-desc", "cpv-asc", "core-first", "published-desc"):
        assert value in tenders.SORT_PATTERN


def test_cpv_titles_come_from_the_full_vocabulary():
    got = tenders.cpv_titles(["34330000", "24615000", "99999999"])
    assert set(got) == {"34330000", "24615000"}            # a code the vocabulary does not hold is left out
    assert got["34330000"].lower().startswith("spare parts")
