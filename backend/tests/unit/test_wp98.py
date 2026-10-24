"""WP-98 (persona round of 23 October 2026, section C, items 1 to 4): the keyword map of other languages, the buyers'
abbreviations, and how the tender search writes them (no database)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dgate import search_terms as S
from dgate import tenders
from dgate.cpv_labels import codes_for_word, codes_for_words

WEB_COPY = Path(__file__).resolve().parents[3] / "web" / "lib" / "data" / "search-terms.json"
CPV = json.loads((Path(S.__file__).parent / "data" / "cpv-full.json").read_text(encoding="utf-8"))["codes"]


def test_the_api_and_the_site_read_the_same_map():
    assert S.DATA.read_bytes() == WEB_COPY.read_bytes()


def test_every_code_of_a_group_is_under_a_code_of_the_vocabulary():
    for g in S.groups():
        assert g.cpv, g.id
        for p in g.cpv:
            assert any(code.startswith(p) for code in CPV), (g.id, p)
        assert len({t for t in g.folded}) == len(g.folded), f"{g.id}: a term twice"


@pytest.mark.parametrize("language, words, group", [
    ("pt", "fardamento", "uniforms"), ("pt", "botas", "uniforms"), ("pt", "calçado", "uniforms"),
    ("pt", "peças sobressalentes", "spare-parts"), ("pt", "munições", "ammunition"),
    ("es", "uniformes", "uniforms"), ("es", "recambios", "spare-parts"), ("es", "repuestos", "spare-parts"),
    ("es", "combustible", "fuel"), ("es", "logística", "logistics"), ("es", "municiones", "ammunition"),
    ("fr", "vêtements", "uniforms"), ("fr", "pièces détachées", "spare-parts"), ("fr", "carburant", "fuel"),
    ("fr", "explosifs", "ammunition"), ("fr", "vision nocturne", "night-vision"), ("fr", "gilets pare-balles", "body-armour"),
    ("de", "Bekleidung", "uniforms"), ("de", "Stiefel", "uniforms"), ("de", "Ersatzteile", "spare-parts"),
    ("de", "Drehteile", "spare-parts"), ("de", "Frästeile", "spare-parts"), ("de", "Drohnen", "drones"),
    ("de", "Kraftstoff", "fuel"), ("de", "Logistik", "logistics"), ("de", "Munition", "ammunition"),
    ("de", "Sprengstoff", "ammunition"), ("de", "Schutzwesten", "body-armour"), ("de", "Nachtsicht", "night-vision"),
    ("pl", "odzież", "uniforms"), ("pl", "mundury", "uniforms"), ("pl", "obuwie", "uniforms"),
    ("pl", "części zamienne", "spare-parts"), ("pl", "drony", "drones"), ("pl", "paliwo", "fuel"),
    ("pl", "amunicja", "ammunition"), ("pl", "materiały wybuchowe", "ammunition"), ("pl", "noktowizor", "night-vision"),
    ("nl", "kleding", "uniforms"), ("nl", "brandstof", "fuel"), ("nl", "logistiek", "logistics"),
    ("nl", "munitie", "ammunition"),
    ("en", "spare parts", "spare-parts"), ("en", "UAV", "drones"), ("en", "unmanned", "drones"), ("en", "RPAS", "drones"),
    ("en", "night vision", "night-vision"), ("en", "body armour", "body-armour"), ("en", "explosives", "ammunition"),
])
def test_a_word_of_each_language_is_read_as_its_group(language, words, group):
    e = S.expand(tenders.search_words(words))
    assert [g.id for g in e.groups] == [group], (language, words)
    assert len(e.slots) == 1 and len(e.slots[0]) > 1


def test_the_other_words_stay_slots_of_their_own_in_any_order():
    e = S.expand(["counter", "drone", "Bayern"])
    assert [len(s) for s in e.slots][0] == 1 and e.slots[0] == [["counter"]] and e.slots[2] == [["Bayern"]]
    assert "UAV" in e.also and "drone" not in e.also
    assert S.expand(["Drohnendetektoren"]).slots == [[["Drohnendetektoren"]]]
    # a term that another term already covers (a word matches by its start) is not searched twice
    assert ["uniformes"] not in S.expand(["fardamento"]).slots[0] and ["uniform"] in S.expand(["fardamento"]).slots[0]


def test_a_run_of_words_is_read_against_the_code_titles_together():
    assert codes_for_word("parts") == ()                       # in too many titles to narrow anything alone
    assert "34330000" in codes_for_words(("spare", "parts"))
    assert codes_for_words(("spare", "of")) == ()


@pytest.mark.parametrize("typed", ["BAAINBw", "baainbw", "DMO", "DGA", "JAE MALE", "JAEMALE", "jae-male", "FMV"])
def test_an_abbreviation_names_its_buyer(typed):
    assert S.buyer_names(typed)


def test_a_word_that_is_no_abbreviation_names_nothing():
    assert S.buyer_names("DMOS") == [] and S.buyer_names("BAAINBw Koblenz") == [] and S.buyer_names("") == []


def test_the_search_sql_of_a_group_is_a_few_regular_expressions_over_the_titles():
    where, params, _ = tenders._tender_filters("fardamento", None, None, "open", "relevant", None, None, None, None, None,
                                               None, None)
    search = next(w for w in where if "ts.title_en" in w)              # WP-101: the folded titles stored for the search
    rx = [p for p in params if isinstance(p, str) and p.startswith(" (?:")]
    assert rx and all(p.count("|") < tenders.RX_TERMS for p in rx)
    assert "buyer_name ~" not in search                           # a product word names no buyer
    assert " ".join(where).count("%s") == len(params)              # every placeholder has its value
    # the typed word still reads the buyer's name as before
    assert "ts.buyer_name LIKE dg_word_pattern(%s)" in search
    info = tenders.search_info("fardamento")
    assert info["searchGroups"][0]["id"] == "uniforms" and "Bekleidung" in info["alsoSearched"]
    assert tenders.search_info(None) == {"alsoSearched": [], "searchGroups": []}
