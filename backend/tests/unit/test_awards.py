"""The supplier map's reader (dgate/awards.py): which organisations won a notice, and who is not one."""

from __future__ import annotations

import json

import pytest

from dgate import awards
from dgate.awards import PERSON_PLACEHOLDER, person_reason, read_award


def record(winners: list[str], tenderers: list[tuple[str, str, str | None]], *, lang: str = "deu") -> dict:
    """What TED answers for one result notice: `winner-name` once per lot, the tenderer block in
    parallel lists, and `winner-country` / `winner-identifier` in an order of their own."""
    return {
        "publication-number": "100-2026",
        "winner-name": {lang: [w for w in winners for _ in range(2)]},           # once per lot
        "organisation-name-tenderer": {lang: [t[0] for t in tenderers]},
        "organisation-country-tenderer": [t[1] for t in tenderers],
        "organisation-identifier-tenderer": [t[2] for t in tenderers if t[2]],
        # not read: in a notice with several winners these do not follow the order of winner-name
        "winner-country": sorted({t[1] for t in tenderers}),
    }


def test_countries_come_from_the_tenderer_block_and_not_from_the_winner_fields():
    rec = record(["Zeta Systems GmbH", "Alfa Optics S.A."],
                 [("Alfa Optics S.A.", "FRA", "FR111"), ("Zeta Systems GmbH", "DEU", "DE222")])
    got = read_award(rec)
    assert [(w.name, w.country, w.identifier) for w in got.winners] == [
        ("Alfa Optics S.A.", "FR", "FR111"), ("Zeta Systems GmbH", "DE", "DE222")]
    assert got.winners_seen == 2


def test_a_tenderer_that_did_not_win_is_not_a_supplier():
    rec = record(["Alfa Optics S.A."],
                 [("Alfa Optics S.A.", "FRA", "FR111"), ("Beta Rival Ltd", "GBR", "GB333")])
    got = read_award(rec)
    assert [w.name for w in got.winners] == ["Alfa Optics S.A."]


def test_a_number_list_that_does_not_line_up_is_not_guessed():
    rec = record(["Alfa Optics S.A.", "Zeta Systems GmbH"],
                 [("Alfa Optics S.A.", "FRA", None), ("Zeta Systems GmbH", "DEU", "DE222")])
    got = read_award(rec)
    assert [w.identifier for w in got.winners] == [None, None]      # one number for two organisations


def test_one_organisation_takes_its_one_number_and_one_country_list_of_equal_entries_is_enough():
    rec = {"winner-name": ["Alfa Optics S.A."], "organisation-name-tenderer": ["Alfa Optics S.A."],
           "organisation-country-tenderer": ["FRA"], "organisation-identifier-tenderer": ["FR111", "FR111B"]}
    got = read_award(rec)
    assert [(w.country, w.identifier) for w in got.winners] == [("FR", "FR111")]
    many = {"winner-name": ["A GmbH", "B GmbH"], "organisation-name-tenderer": ["A GmbH", "B GmbH"],
            "organisation-country-tenderer": ["DEU"]}                # one entry for two organisations, equal
    assert [w.country for w in read_award(many).winners] == ["DE", "DE"]
    differing = {"winner-name": ["A GmbH", "B SA"], "organisation-name-tenderer": ["A GmbH", "B SA"],
                 "organisation-country-tenderer": ["DEU", "FRA", "ESP"]}
    got = read_award(differing)
    assert got.winners == [] and got.counts["skipped_no_country"] == 2


def test_a_notice_without_a_winner_name_has_no_supplier():
    got = read_award({"publication-number": "1-2026", "organisation-name-tenderer": ["X GmbH"]})
    assert got.winners == [] and got.counts["no_winner_name"] == 1 and got.winners_seen == 0
    got = read_award({"winner-name": ["X GmbH"]})
    assert got.winners == [] and got.counts["no_tenderer_block"] == 1


PERSONS = [
    ("Radek Nečas", "CZ"), ("Miroslav Mondek", "CZ"), ("František Čmolík", "CZ"), ("Jean-Pierre Martin", "FR"),
    ("Markus F. Strieder", "DE"), ("DUPONT Jean", "FR"), ("Jan NOVAK", "CZ"), ("Bernardo Rodríguez Benítez", "ES"),
    ("P.P.H.U. Krismark Krystyna Łopuszańska", "PL"), ("Przedsiębiorstwo Wielobranżowe \"SOBCZAK\" Jadwiga Sobczak", "PL"),
    ("Krzysztof Trojanowski MAXI-CARGO", "PL"), ("TRANSWAY USŁUGI PRZEWOZOWE GRZEGORZ HUNKIEWICZ", "PL"),
    ("ЕТ ЕЛ ТРАНС ИНЖЕНЕРИНГ - ВАЛЕНТИН МАЧИКОВ", "BG"), ("Wunsch&Rudolph e.K.", "DE"),
    ("Erem Serwis s.c. R. Parol, R.M. Danielak", "PL"), ("Tomasz Boruk Agencja Ochrony „TOM”, ul. 6 Marca 6, 72-300 Gryfice", "PL"),
    ("Osoba fizyczna", "PL"), (PERSON_PLACEHOLDER, "DE"),
]
COMPANIES = [
    ("Rheinmetall Landsysteme GmbH", "DE"), ("KNDS Deutschland GmbH & Co. KG", "DE"), ("Indra Sistemas, S.A.", "ES"),
    ("Santa Bárbara Sistemas, S.A.U.", "ES"), ("Polska Grupa Zbrojeniowa S.A.", "PL"), ("Sign Polska Sp. z o.o., ul. Szafera 3, 71-245 Szczecin", "PL"),
    ("Explosia a.s.", "CZ"), ("SIA Latvijas Mobilais Telefons", "LV"), ("Aktsiaselts Merko Ehitus Eesti", "EE"),
    ("Nammo Raufoss AS", "NO"), ("Airbus Defence and Space", "DE"), ("DAHER", "FR"), ("HECKLER & KOCH", "DE"),
    ("Thales", "FR"), ("Ministerstwo Obrony Narodowej", "PL"), ("Vojenský výzkumný ústav, s.p.", "CZ"),
    ("ЕСРИ-БЪЛГАРИЯ ООД", "BG"), ("Fraunhofer-Gesellschaft", "DE"),
]


@pytest.mark.parametrize("name,country", PERSONS)
def test_a_natural_person_is_not_a_supplier(name, country):
    assert person_reason(name, "123456789", country) is not None


@pytest.mark.parametrize("name,country", COMPANIES)
def test_a_legal_entity_is_a_supplier(name, country):
    assert person_reason(name, "123456789", country) is None


def test_a_person_never_reaches_the_winner_list_the_counts_or_the_record_to_be_landed():
    rec = record(["Radek Nečas", "Zeta Systems GmbH"],
                 [("Radek Nečas", "CZE", "11223344"), ("Zeta Systems GmbH", "DEU", "DE222"),
                  ("Josef Rival", "CZE", "55667788")])         # a losing tenderer who is a person too
    got = read_award(rec)
    assert [w.name for w in got.winners] == ["Zeta Systems GmbH"]
    assert got.counts["skipped_person"] == 1 and got.winners_seen == 2
    landed = json.dumps(got.redacted, ensure_ascii=False)
    assert "Nečas" not in landed and "Josef Rival" not in landed and "11223344" not in landed
    assert "Zeta Systems GmbH" in landed and PERSON_PLACEHOLDER in landed
    # positions are kept: the blanked block still lines up with the other lists
    assert len(got.redacted["organisation-name-tenderer"]["deu"]) == len(got.redacted["organisation-country-tenderer"])


def test_a_record_with_no_person_is_landed_as_received():
    rec = record(["Zeta Systems GmbH"], [("Zeta Systems GmbH", "DEU", "DE222")])
    assert read_award(rec).redacted == rec


def test_the_cpv_a_profile_files_a_notice_under_is_the_first_military_code():
    assert awards._main_cpv(["45000000", "35400000", "35100000"]) == "35400000"
    assert awards._main_cpv(["45000000", "50000000"]) == "45000000"
    assert awards._main_cpv([]) is None


def test_the_awards_command_passes_its_window_to_the_loader(monkeypatch):
    from collections import Counter
    from datetime import date

    from dgate import pipeline

    seen = {}

    def fake(**kw):
        seen.update(kw)
        return Counter(fetched=0)

    monkeypatch.setattr(awards, "run_awards", fake)
    pipeline.main(["awards", "--since", "2025-01-01", "--limit", "5"])
    assert seen == {"limit": 5, "since": date(2025, 1, 1)}
    seen.clear()
    pipeline.main(["awards"])
    assert seen == {"limit": None}


@pytest.mark.parametrize("a,b", [
    ("27577171", "2757717"), ("0148284", "01482840"), ("481250", "HRB481250"), ("811127845", "811137845"),
    ("556204190401", "5562041904"), ("423039962", "0423039962"), ("FN462693G", "FN462683G"),
    ("ESB93350130", "B93350130"), ("6061578", "06061578"), ("129273267", "USTDE129273267"),
    ("811894240", "HRB100283"), ("ATU37043800", "FN99220M"),
])
def test_two_spellings_of_one_number_are_not_a_conflict(a, b):
    assert not awards.numbers_conflict(a, b)


@pytest.mark.parametrize("a,b", [
    ("815022240", "815896405"), ("221174497", "331224181"), ("111111111", "222222222"), ("HRB100283", "HRB204123"),
])
def test_two_different_numbers_of_one_kind_are_a_conflict(a, b):
    assert awards.numbers_conflict(a, b)


def test_only_publication_numbers_go_into_a_ted_query():
    from dgate.sources import ted

    with pytest.raises(ValueError):
        ted.fetch_by_numbers(["12-2026) OR publication-date>=20000101"])
    with pytest.raises(ValueError):
        ted.fetch_by_numbers([f"{n}-2026" for n in range(ted.AWARD_BATCH + 1)])
    assert ted.fetch_by_numbers([]) == {}
