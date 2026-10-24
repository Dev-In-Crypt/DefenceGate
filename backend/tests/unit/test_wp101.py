"""WP-101 (persona round of 24 October 2026, search): a run of one group's terms is one slot, the product words and buyer
abbreviations the personas typed, the notice number in every status, and the search SQL over the folded texts stored
once per notice (migration 0113), never `dg_fold` of a title per term (no database)."""

from __future__ import annotations

import re

import pytest

from dgate import search, tenders
from dgate import search_terms as S


def test_a_run_of_terms_of_one_group_is_one_slot():
    e = S.expand(tenders.search_words("Drehteile Frästeile"))
    assert len(e.slots) == 1                                  # was two slots of the same 17 terms: 12.6 s, a 503
    typed, *terms = e.slots[0]
    assert typed == ["Drehteile", "Frästeile"]                # both words, in any order ...
    # ... or any term of the group. WP-110: machining is a group of its own (general spare parts came first, p03)
    assert ["Zerspanung"] in terms and ["Drehteile"] in terms and ["Frästeile"] in terms and ["Ersatzteile"] not in terms
    assert "Drehteile" not in e.also and "Frästeile" not in e.also and "Zerspanung" in e.also
    assert [g.id for g in e.groups] == ["machining"]
    assert len(S.expand(["spare", "parts", "Ersatzteile"]).slots) == 1
    # terms of two groups, or a word of no group between them, stay slots of their own
    assert len(S.expand(["Drehteile", "Munition"]).slots) == 2
    assert len(S.expand(["Drehteile", "Boxer", "Frästeile"]).slots) == 3


@pytest.mark.parametrize("words, group", [
    # WP-110: machining is a group of its own; "wiring" alone (any cabling) is no longer a term of the harness group, "SSI"
    # (French: fire safety system) no longer cyber -- see test_wp110
    ("Zerspanung", "machining"), ("CNC", "machining"), ("Präzisionsteile", "machining"), ("mecanizado", "machining"),
    ("harness", "wiring"), ("wiring harness", "wiring"), ("Kabelbaum", "wiring"), ("mazo de cables", "wiring"),
    ("stamping", "stampings"), ("Stanzteile", "stampings"), ("emboutissage", "stampings"),
    ("castings", "castings"), ("Gussteile", "castings"), ("fonderie", "castings"),
    ("cyber", "cyber"), ("cybersecurity", "cyber"), ("cybersécurité", "cyber"), ("Cybersicherheit", "cyber"),
    ("detonators", "ammunition"), ("lont", "ammunition"), ("detonating cord", "ammunition"),
])
def test_the_product_words_of_the_personas_have_a_group(words, group):
    e = S.expand(tenders.search_words(words))
    assert [g.id for g in e.groups] == [group], words
    assert len(e.slots[0]) > 1


def test_cyber_typed_any_way_finds_the_same_notices():
    # "cybersecurity" found 3 where "cyber" found 203 (p05): each of the group's words now searches every other one
    for typed in ("cybersecurity", "cybersécurité", "Cybersicherheit"):
        assert ["cyber"] in S.expand([typed]).slots[0]


@pytest.mark.parametrize("typed, name", [
    ("RBLog", "regionalna"), ("AU", "agencja"), ("WOG", "wojskowy"), ("JW", "jednostka"),
    ("NAVARM", "navali"), ("TERRARM", "terrestri"), ("ARMAEREO", "aeronautici"),
])
def test_the_abbreviations_of_polish_and_italian_buyers(typed, name):
    assert any(name in n for n in S.buyer_names(typed)), typed
    assert S.buyer_names(typed.lower()) == S.buyer_names(typed)


def test_a_notice_number_is_looked_for_in_every_status():
    for q in ("220199-2026", "2026/S 203-724451", "2026/s 203-724451"):
        assert tenders.NOTICE_NUMBER.match(q), q
        assert search.opens_on("tenders", q)["status"] == "all"
    for q in ("35613000", "drone", "220199-2026 x", "2026", "12-34"):
        assert not tenders.NOTICE_NUMBER.match(q), q
    assert "status" not in search.opens_on("tenders", "drone")
    assert "status" not in search.opens_on("funding", "220199-2026")
    assert search.opens_on("organisations", "x")["programme"]


def test_the_search_reads_the_stored_folded_texts_never_a_fold_per_term():
    where, params, _ = tenders._tender_filters("Drehteile Frästeile", None, None, "open", "relevant", None, None, None, None,
                                               None, None, None)
    text = next(w for w in where if "opportunity_search ts" in w)
    assert "dg_fold(" not in text and "dgate_cpv_heads(" not in text
    assert re.search(r"\bts\.id = o\.id\b", text)              # correlated: the collapse rules read the twin's own row
    assert text.count(" AND ") >= 1 and " ~ %s" in text
    assert " ".join(where).count("%s") == len(params)
    # a collapse rule rewrites `o.` for the twin, and the search follows it to the twin's own stored row
    assert "ts.id = t.id" in tenders.collapse_clauses(where)


def test_every_group_stays_inside_the_alternatives_cap():
    for g in S.groups():
        assert len(g.terms) + 1 <= S.MAX_ALTERNATIVES, g.id
