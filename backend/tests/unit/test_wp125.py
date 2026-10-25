"""WP-125 (verification round 6, 25 October 2026, personas problems.csv: "castings" found two Horizon climate-security calls and a Swiss
water-pipe tender): the keyword map's "typed only" words and the funding search's word start for product words (no database)."""

from __future__ import annotations

import pytest

from dgate import search_terms as S
from dgate import tenders, textsearch

PLACE_WORDS = {"foundry", "fonderie", "giesserei", "odlewnia"}


def _alternatives(word: str) -> set[str]:
    return {" ".join(S.fold_words(" ".join(a))) for a in S.expand(tenders.search_words(word)).slots[0][1:]}


def test_castings_no_longer_searches_the_place_where_castings_are_made():
    # the Swiss tender was found through TED's code title "Foundry moulds" (CPV 43415000): "foundry" was a term of the group
    assert not _alternatives("castings") & PLACE_WORDS
    assert not set(S.expand(["castings"]).also) & {"foundry", "fonderie", "Gießerei", "odlewnia"}
    assert {"gussteile", "druckguss", "pieces de fonderie", "odlewy"} <= _alternatives("castings")


@pytest.mark.parametrize("typed", ["foundry", "Gießerei", "fonderie", "odlewnia"])
def test_typed_a_place_word_still_searches_the_whole_group(typed):
    # no loss for a real match: the word itself (the typed slot) and every term of the group
    e = S.expand(tenders.search_words(typed))
    assert [g.id for g in e.groups] == ["castings"]
    assert e.slots[0][0] == [typed]
    assert {"casting", "gussteile", "pieces de fonderie"} <= _alternatives(typed)     # ("castings" begins with "casting": one term)


# ------------------------------------------------------------------------------------------- the funding search

CLIMATE = ("Climate security and civil preparedness – new ways to develop pre- and post-crisis climate-change related scenarios "
           "for a more resilient Europe European Commission Forecasting Scenario building")
CASCADING = "Multi-hazard approach and cumulative / cascading impacts European Commission Weather forecasting Broadcasting"


@pytest.mark.parametrize("q", ["castings", "casting", "foundry", "Gussteile"])
def test_a_product_word_never_matches_inside_another_word(q):
    query = textsearch.parse(q, products=True)
    assert not query.matches(CLIMATE), q          # "casting" inside "forecasting"
    assert not query.matches(CASCADING), q


@pytest.mark.parametrize("q, text", [
    ("castings", "Advanced castings for land vehicles"),
    ("castings", "Aluminium casting technologies for defence platforms"),
    ("castings", "Lightweight die casting of armour parts"),
    ("foundry", "Iron castings for naval propulsion"),
    ("castings", "Gussteile für Fahrzeuge"),
])
def test_a_real_casting_call_is_still_found(q, text):
    assert textsearch.parse(q, products=True).matches(text)


def test_the_funding_words_of_its_own_table_keep_their_rules():
    # WP-91: "cyber" (5 letters, its own synonym row) still finds "cybersecurity" inside a word; the product rule is only for product words
    assert textsearch.parse("cyber", products=True).matches("European cybersecurity competence")
    assert textsearch.parse("logistic", products=True).matches("Military logistics")
    assert textsearch.parse("drone", products=True).matches("Counter-drone systems")
