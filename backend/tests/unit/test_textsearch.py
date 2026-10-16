"""Funding search (ux-funding F3): folding, word boundaries, synonyms, the "also searched" line."""

from __future__ import annotations

import pytest

from dgate import textsearch


def hit(q: str, text: str) -> bool:
    query = textsearch.parse(q)
    assert query is not None
    return query.matches(text)


UNMANNED = "Unmanned systems and counter-unmanned systems"


def test_hyphen_and_space_are_the_same_search():
    assert hit("counter-drone", "Counter-drone systems")
    assert hit("counter drone", "Counter-drone systems")
    assert hit("COUNTER_DRONE", "counter drone systems")


def test_drone_finds_unmanned_and_uas_through_the_synonym_table():
    assert hit("drone", UNMANNED)
    assert hit("counter drone", UNMANNED)
    assert hit("UAS", UNMANNED)
    assert hit("unmanned", "Drone cargo")


def test_a_short_word_matches_whole_words_only():
    assert hit("AI", "Cybersecure tools relying on AI")
    assert hit("AI", "Artificial Intelligence for decision making")      # synonym phrase
    assert not hit("AI", "Protection against threats; available when maintaining")
    assert not hit("uas", "Persuasive pause")


def test_longer_words_match_inside_words():
    assert hit("logistic", "Military logistics")
    assert hit("cyber", "Cybersecurity capacities")
    assert hit("cybersec", "Cybersecurity capacities")


def test_four_letter_words_match_at_the_start_of_a_word():
    assert hit("fund", "European Defence Fund")
    assert not hit("fund", "Refund")


def test_every_word_must_match_and_stop_words_do_not_count():
    assert hit("AI for logistics", "Artificial intelligence in military mobility")
    assert not hit("drone logistics", "Drone cargo")
    assert hit("the", "the")                    # nothing but stop words: they are what is searched


def test_accents_and_special_letters_are_folded():
    assert hit("Białystok", "Oddział w Bialystok")
    assert hit("prevision", "Prévision")
    assert hit("Kobenhavn", "København")


def test_topic_codes_are_searched_by_their_parts():
    assert hit("EDF-2026-RA", "EDF-2026-RA-SENS-MSDT")
    assert not hit("EDF-2025", "EDF-2026-RA-SENS-MSDT")


@pytest.mark.parametrize("q", ["", "   ", "---", "!!!"])
def test_a_query_without_a_word_searches_nothing(q):
    assert textsearch.parse(q) is None


def test_also_searched_lists_the_synonyms_that_were_added_not_the_typed_words():
    q = textsearch.parse("counter-drone")
    assert q is not None and q.terms == ["counter", "drone"]
    assert q.also == ["uas", "uav", "unmanned", "rpas"]
    both = textsearch.parse("drone uav")
    assert both is not None and "uav" not in both.also and "drone" not in both.also
    assert textsearch.parse("fund").also == []


def test_identifiers_match_by_the_start_of_their_words_titles_do_not():
    q = textsearch.parse("HORIZON-CL3-2026-01-FC")
    assert q is not None
    assert q.matches("Fighting crime", "HORIZON-CL3-2026-01-FCT-01")
    assert not q.matches("HORIZON-CL3-2026-01-FCT-01", "")       # a title is words, not an identifier
    short = textsearch.parse("ai")
    assert short is not None and not short.matches("Against all odds", "HORIZON-X")
