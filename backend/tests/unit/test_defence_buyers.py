"""M1-03: the defence buyer list, and the rules that decide what is on it.

The buyer signal is strong -- a listed buyer qualifies a notice on its own,
whatever it buys -- so every inclusion is a precision decision. These tests pin
the decisions that were argued over, so they are not quietly undone.
"""

from __future__ import annotations

import csv
from collections import Counter

import pytest

from dgate.ops import derive_buyers as d
from dgate.pipeline import SEEDS_FILE, load_seed_rows


def pl(name):
    return d.decide(name, d.PL_INCLUDE, d.PL_EXCLUDE)


def es(name):
    return d.decide(name, d.ES_INCLUDE, d.ES_EXCLUDE)


def pl_key(name):
    return d.pl_group(d.loose(name))


# ------------------------------------------------------------------ Poland

@pytest.mark.parametrize("name", [
    "Ministerstwo Obrony Narodowej",
    "Agencja Uzbrojenia",
    "2. Regionalna Baza Logistyczna",
    "31 Wojskowy Oddział Gospodarczy",
    "Skarb Państwa - Jednostka Wojskowa Nr 2305",
    "Wojskowa Akademia Techniczna im. Jarosława Dąbrowskiego",
    "Centrum Zasobów Cyberprzestrzeni Sił Zbrojnych",
    "Komenda Portu Wojennego Gdynia",
    "Wojskowy Instytut Techniczny Uzbrojenia",
])
def test_polish_defence_bodies_are_listed(name):
    assert pl(name).category is not None


@pytest.mark.parametrize("name", [
    # ~9,000 notices of drugs, food and cleaning, under healthcare rules.
    "10 Wojskowy Szpital Kliniczny z Polikliniką Samodzielny Publiczny Zakład Opieki Zdrowotnej",
    "Wojskowy Instytut Medyczny - Państwowy Instytut Badawczy",
    "Wojskowe Centrum Krwiodawstwa i Krwiolecznictwa SP ZOZ",
    # Estate management, 3,598 notices.
    "Agencja Mienia Wojskowego",
    # Police, caught by "centrum szkolenia" in a loose match.
    "Centrum Szkolenia Policji w Legionowie",
    # The military publishing house buys paper and printing.
    "Wojskowy Instytut Wydawniczy w Warszawie",
])
def test_military_adjacent_bodies_that_are_not_defence_buyers_are_not_listed(name):
    """Listing these would put a hospital's cleaning contract in the defence
    slice -- the fire-extinguisher failure the classifier has a test against."""
    assert pl(name).category is None


def test_a_unit_number_identifies_the_unit_whatever_else_the_name_says():
    assert pl_key("35 Wojskowy Oddział Gospodarczy") == pl_key(
        "35. Krakowski Wojskowy Oddział Gospodarczy")
    assert pl_key("2 Regionalna Baza Logistyczna") == pl_key("2. Regionalna Baza Logistyczna")
    assert pl_key("Jednostka Wojskowa Nr 2305") == pl_key(
        "Skarb Państwa - Jednostka Wojskowa Nr 2305")
    assert pl_key("Jednostka Wojskowa 4724") == pl_key("Jednostka Wojskowa nr 4724")


def test_different_unit_numbers_are_never_merged():
    assert pl_key("31 Wojskowy Oddział Gospodarczy") != pl_key("13 Wojskowy Oddział Gospodarczy")
    assert pl_key("Jednostka Wojskowa Nr 2063") != pl_key("Jednostka Wojskowa Nr 2305")


def test_the_economic_unit_rule_wins_over_the_unit_number_inside_it():
    """'16 WOG (jednostka wojskowa nr 3378)' is the 16th WOG, not unit 3378."""
    assert pl_key("16 Wojskowy Oddział Gospodarczy w Drawsku Pomorskim "
                  "(jednostka Wojskowa nr 3378)") == "16 wojskowy oddzial gospodarczy"


# ------------------------------------------------------------------- Spain

@pytest.mark.parametrize("name", [
    "Ministerio de Defensa",
    "Junta de Contratación del Ministerio de Defensa",
    "Jefatura de Asuntos Económicos del Mando de Apoyo Logístico",
    "Jefatura de la Sección Económico-Administrativa 27 - Base Aérea de Getafe",
    "Subdirección General de Adquisiciones de Armamento y Material DGAM",
])
def test_spanish_defence_bodies_are_listed(name):
    assert es(name).category is not None


@pytest.mark.parametrize("name", [
    "Jefatura de Asuntos Económicos de la Guardia Civil",
    "Jefatura de Unidad de Medios Internos - Área de Compras de la Compañía Española "
    "de Seguros de Crédito a la Exportación S.M.E. CESCE",
])
def test_spanish_non_defence_matches_are_not_listed(name):
    assert es(name).category is None


# --------------------------------------------------------------- seed file

def test_the_committed_seed_file_has_ten_buyers_for_each_national_source():
    groups = load_seed_rows(SEEDS_FILE)
    per_country = Counter(country for country, _ in groups)
    assert per_country["PL"] >= 10
    assert per_country["ES"] >= 10


def test_the_seed_file_contains_no_excluded_body():
    with SEEDS_FILE.open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            text = d.loose(row["raw_name"])
            assert "szpital" not in text
            assert "mienia wojskowego" not in text
            assert "polic" not in text
            assert "guardia civil" not in text


def test_every_hand_curated_buyer_survives_derivation():
    from dgate.pipeline import DEFENCE_BUYERS

    groups = load_seed_rows(SEEDS_FILE)
    seeded = {(c, d.loose(raw)) for (c, _), spellings in groups.items() for raw, _ in spellings}
    seeded |= {(c, d.loose(name)) for c, name in groups}
    for country, name in DEFENCE_BUYERS:
        assert (country, d.loose(name)) in seeded, name


def test_a_missing_seed_file_falls_back_to_the_built_in_list(tmp_path):
    groups = load_seed_rows(tmp_path / "absent.csv")
    assert ("PL", "Agencja Uzbrojenia") in groups
