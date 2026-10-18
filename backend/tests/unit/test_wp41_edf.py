"""WP-41, N6: the EDF factsheet reader loses members whose names wrap or whose spaces the layout collapses.

The texts are the consortium tables of three real factsheets as the PDF reader returned them on
17 October 2026 (ARCHER 2023, AVALON 2023, EMISSARY 2023; cut to the table; organisation names only)."""

from __future__ import annotations

from dgate.sources import edf_factsheets as edf

ARCHER_LAYOUT = """
NAME                                                               COUNTRY
OF THE ENTITY

AIRBUS DEFENCE   AND SPACE  SAS (Coordinator)                         France


ATHINA -
EREVNITIKO KENTRO KAINOTOMIAS  STISTECHNOLOGIES  TISPLIROF            Greece
ORIAS,TON EPIKOINONION KAI TISGNOSIS


ACADEMIA  TEHNICA  MILITARA "FERDINAND   I"                           Romania


FRAUNHOFER   GESELLSCHAFT    ZUR FORDERUNG    DER  ANGEWA             Germany
NDTEN  FORSCHUNG   EV


VYSOKE  UCENI  TECHNICKE  V BRNE                                      Czechia
"""

ARCHER_PLAIN = """NAME
OF THE ENTITY
COUNTRY
Members of the consortium and
country of establishment:
AIRBUS DEFENCE AND SPACE SAS (Coordinator) France
ATHINA -
EREVNITIKO KENTRO KAINOTOMIAS STIS TECHNOLOGIES TIS PLIROF
ORIAS, TON EPIKOINONION KAI TIS GNOSIS
Greece
ACADEMIA TEHNICA MILITARA "FERDINAND I" Romania
FRAUNHOFER GESELLSCHAFT ZUR FORDERUNG DER ANGEWA
NDTEN FORSCHUNG EV Germany
VYSOKE UCENI TECHNICKE V BRNE Czechia
"""

ATHINA = "ATHINA - EREVNITIKO KENTRO KAINOTOMIAS STIS TECHNOLOGIES TIS PLIROFORIAS, TON EPIKOINONION KAI TIS GNOSIS"

AVALON_LAYOUT = """
NAME                                                     COUNTRY
OF THE ENTITY
UNIVERSITEDULUXEMBOURG                                     Luxembourg
"""
AVALON_PLAIN = """NAME
OF THE ENTITY
COUNTRY
UNIVERSITE DU LUXEMBOURG Luxembourg
"""

EMISSARY_LAYOUT = """
NAME                                                               COUNTRY
OF THE ENTITY
INDRA SISTEMAS  SA                                                   Spain
ISDLYSEIS  OLOKRIROMENON    SYSTIMA                                  Greece
TON ANONYMOS    ETAIREIA
ISTITUTO AFFARI INTERNAZIONALI                                       Italy
"""
EMISSARY_PLAIN = """NAME
OF THE ENTITY
COUNTRY
INDRA SISTEMAS SA Spain
ISD LYSEIS OLOKRIROMENON SYSTIMA
TON ANONYMOS ETAIREIA Greece
ISTITUTO AFFARI INTERNAZIONALI Italy
"""


def _p(name, country, role="participant"):
    return {"name": name, "country": country, "role": role, "is_sme": None}


def _text(layout, plain):
    return edf.FactsheetText("h", 2, layout, plain)


def test_a_name_wrapped_over_three_lines_and_glued_by_the_layout_is_kept():
    answer = {"coordinator": None, "participants": [
        _p("AIRBUS DEFENCE AND SPACE SAS", "France", "coordinator"), _p(ATHINA, "Greece"),
        _p("VYSOKE UCENI TECHNICKE V BRNE", "Czechia")]}
    kept, dropped = edf.check_names(answer, _text(ARCHER_LAYOUT, ARCHER_PLAIN))
    assert ATHINA in [p["name"] for p in kept["participants"]]
    assert dropped["not_in_text"] == 0


def test_a_name_broken_inside_a_word_by_the_table_is_kept():
    answer = {"coordinator": None, "participants": [
        _p("ISD LYSEIS OLOKRIROMENON SYSTIMATON ANONYMOS ETAIREIA", "Greece"), _p("INDRA SISTEMAS SA", "Spain")]}
    kept, dropped = edf.check_names(answer, _text(EMISSARY_LAYOUT, EMISSARY_PLAIN))
    assert len(kept["participants"]) == 2 and dropped["not_in_text"] == 0
    assert dropped["missing_from_answer"] == 1          # ISTITUTO AFFARI INTERNAZIONALI, left out by the answer


def test_a_name_the_model_copied_glued_is_stored_with_the_spaces_the_plain_text_prints():
    answer = {"coordinator": None, "participants": [_p("UNIVERSITEDULUXEMBOURG", "Luxembourg")]}
    kept, _ = edf.check_names(answer, _text(AVALON_LAYOUT, AVALON_PLAIN))
    assert kept["participants"][0]["name"] == "UNIVERSITE DU LUXEMBOURG"


def test_a_name_the_model_already_spaced_is_not_undone_and_a_made_up_one_is_still_dropped():
    answer = {"coordinator": None, "participants": [
        _p("UNIVERSITE DU LUXEMBOURG", "Luxembourg"), _p("UNIVERSITE DE LIMBOURG", "Luxembourg")]}
    kept, dropped = edf.check_names(answer, _text(AVALON_LAYOUT, AVALON_PLAIN))
    assert [p["name"] for p in kept["participants"]] == ["UNIVERSITE DU LUXEMBOURG"]
    assert dropped["not_in_text"] == 1


def test_a_name_the_plain_text_garbles_is_not_replaced_by_the_garbled_spelling():
    # the plain text of some sheets prints "SAS" as "SA S"; the model's spelling is right and stays
    plain = "AIRBUS DEFENCE AND SPACE SA S France"
    assert edf.printed_spelling("AIRBUS DEFENCE AND SPACE SAS", plain) == "AIRBUS DEFENCE AND SPACE SAS"
    # but a word run together by the layout is spaced from the plain text
    assert edf.printed_spelling("PrismaElectronics ABEE", "Prisma Electronics ABEE Greece") == "Prisma Electronics ABEE"
    assert edf.printed_spelling("Forsvaretsforskningsinstitutt", "Forsvarets forskningsinstitutt Norway") == "Forsvarets forskningsinstitutt"


def test_a_printed_spelling_that_wraps_is_not_used_for_a_name_the_model_gave():
    # the break between PLIROF and ORIAS is not a space of the name: the model's spelling stays
    assert edf.printed_spelling(ATHINA, ARCHER_PLAIN) == ATHINA


def test_a_very_short_name_is_never_taken_from_the_text():
    assert edf.printed_spelling("AB", "xx AB yy") == "AB"
    kept, dropped = edf.check_names({"coordinator": None, "participants": [_p("AB", "France")]},
                                    _text(ARCHER_LAYOUT, ARCHER_PLAIN))
    assert kept["participants"] == [] and dropped["not_in_text"] == 1


def test_the_rows_the_answer_lost_are_recovered_from_the_table_without_a_model():
    have = [{"name": "AIRBUS DEFENCE AND SPACE SAS", "role": "coordinator"},
            {"name": "ACADEMIA TEHNICA MILITARA \"FERDINAND I\"", "role": "participant"}]
    got = edf.recover_missing(have, _text(ARCHER_LAYOUT, ARCHER_PLAIN))
    names = {p["name"]: p for p in got}
    assert set(names) == {"ATHINA - EREVNITIKO KENTRO KAINOTOMIAS STIS TECHNOLOGIES TIS PLIROF ORIAS, TON EPIKOINONION KAI TIS GNOSIS",
                          "FRAUNHOFER GESELLSCHAFT ZUR FORDERUNG DER ANGEWA NDTEN FORSCHUNG EV",
                          "VYSOKE UCENI TECHNICKE V BRNE"}
    athina = next(p for n, p in names.items() if n.startswith("ATHINA"))
    assert athina["country_iso"] == "GR" and athina["role"] == "participant" and athina["recovered"] is True
    assert names["VYSOKE UCENI TECHNICKE V BRNE"]["country_iso"] == "CZ"


def test_recovery_keeps_the_coordinator_mark_of_the_table_and_never_makes_a_second_coordinator():
    got = edf.recover_missing([], _text(ARCHER_LAYOUT, ARCHER_PLAIN))
    assert [p["role"] for p in got].count("coordinator") == 1
    assert next(p for p in got if p["name"].startswith("AIRBUS"))["role"] == "coordinator"
    other = [{"name": "SOMEONE ELSE", "role": "coordinator"}]
    assert {p["role"] for p in edf.recover_missing(other, _text(ARCHER_LAYOUT, ARCHER_PLAIN))} == {"participant"}


def test_recovery_is_idempotent_and_counts_a_glued_stored_name_as_present():
    first = edf.recover_missing([], _text(ARCHER_LAYOUT, ARCHER_PLAIN))
    assert edf.recover_missing(first, _text(ARCHER_LAYOUT, ARCHER_PLAIN)) == []
    # a participant stored with the glued spelling is the same row as the table's
    assert edf.recover_missing([{"name": "UNIVERSITEDULUXEMBOURG", "role": "participant"}],
                               _text(AVALON_LAYOUT, AVALON_PLAIN)) == []


def test_recovery_takes_nothing_from_a_layout_it_cannot_read():
    assert edf.recover_missing([], _text("no table here", "no table here")) == []
