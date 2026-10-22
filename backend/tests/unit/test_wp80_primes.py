"""WP-80: which winners "who to approach" marks as a prime contractor or large defence group (`demand.prime_of`), read on normalised
names as `organisation.canonical_name` stores them; the names are winners on production on 22 October 2026."""

from __future__ import annotations

import pytest

from dgate import demand
from dgate.normalise import normalise_org_name


@pytest.mark.parametrize("name, group", [
    ("indra sistemas", "Indra"), ("indra soluciones tecnologias de la informacion slu", "Indra"),
    ("navantia sme", "Navantia"), ("santa barbara sistemas", "General Dynamics (GDELS)"),
    ("general dynamics european land systems bridge systems", "General Dynamics (GDELS)"),
    ("airbus helicopters espana", "Airbus"), ("airbus defence and space", "Airbus"),
    ("rheinmetall expal munitions", "Rheinmetall"), ("rheinmetall man military vehicles", "Rheinmetall"),
    ("thales espana sistemas", "Thales"), ("knds deutschland maintenance", "KNDS"), ("krauss maffei wegmann co", "KNDS"),
    ("nexter", "KNDS"), ("hensoldt optronics", "Hensoldt"), ("kongsberg maritime spain", "Kongsberg"),
    ("rolls royce solutions", "Rolls-Royce"), ("mbda espana", "MBDA"), ("saab", "Saab"), ("naval group", "Naval Group"),
    ("leonardo pzl swidnik", "Leonardo"), ("diehl defence co", "Diehl"), ("thyssenkrupp marine systems", "ThyssenKrupp Marine Systems"),
    ("pgz stocznia wojenna", "PGZ (Polska Grupa Zbrojeniowa)"), ("safran electronics defense", "Safran"),
    ("babcock international france aviation", "Babcock International"), ("dassault aviation", "Dassault Aviation"),
    ("bae systems hagglunds", "BAE Systems"), ("fincantieri", "Fincantieri"),
])
def test_a_group_member_that_carries_the_group_name_is_marked(name, group):
    p = demand.prime_of(name)
    assert p is not None and p["group"] == group
    assert p["source"] and p["sourceUrl"].startswith("https://")


@pytest.mark.parametrize("name", [
    "advanced telecommunications lambda europa atl europa",       # "mbda" inside a word
    "fundacion santa barbara", "kongsberg automotive", "rolls royce motor cars", "saab automobile parts",
    "leonardo hotels", "babcock wanson", "thyssenkrupp rothe erde", "dassault systemes",
    "iveco espana", "nammo palencia", "escribano mechanical engineering", "talleres norte", "", None,
])
def test_other_names_are_not_marked(name):
    assert demand.prime_of(name) is None


def test_a_spanish_joint_venture_with_a_prime_says_so():
    p = demand.prime_of("ute indra sistemas thales programas de electronica")
    assert p["group"] == "Thales"            # the first group of the list that the name carries
    assert p["jointVenture"]
    assert demand.prime_of("babel sistemas de informacion indra sistemas union temporal de empresas ley 18 1982")["jointVenture"]
    assert not demand.prime_of("indra sistemas")["jointVenture"]


def test_the_patterns_read_the_stored_normal_form():
    # the stored key: lower case, accents folded, legal form off; a raw spelling reaches the same group once normalised
    for raw, group in [("Rheinmetall Landsysteme GmbH", "Rheinmetall"), ("Indra Sistemas, S.A.", "Indra"),
                       ("KNDS Deutschland GmbH & Co. KG", "KNDS"), ("Santa Bárbara Sistemas, S.A.", "General Dynamics (GDELS)")]:
        assert demand.prime_of(normalise_org_name(raw))["group"] == group


def test_every_source_is_named_and_linked():
    for group, _rx, (source, url) in demand.PRIMES:
        assert group and source and url.startswith("https://"), group
