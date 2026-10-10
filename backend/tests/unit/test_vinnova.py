"""The Swedish connector (Vinnova).

Fixtures are the shapes the open API returned on 10 October 2026: a public round of the
civil-military programme, the invited-only "extra" round that follows one, the civil
defence programme's round with a stated total budget, and a civil round that merely
mentions defence.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime

import pytest

from dgate.normalise import from_vinnova, strip_personal_data
from dgate.sources import vinnova as se

PROGRAMMES = [
    {"Diarienummer": "2024-01502", "Titel": "Innovationsprogrammet för civil-militära synergier",
     "TitelEngelska": "The Innovation Program for Civil-Military Synergies"},
    {"Diarienummer": "2026-00538", "Titel": "Nationellt innovationsprogram för civilt försvar",
     "TitelEngelska": "National Civil Defence Innovation Programme"},
    {"Diarienummer": "2023-00088", "Titel": "Nationella flygtekniska forskningsprogrammet",
     "TitelEngelska": "National Aeronautic Research Programme"},
    {"Diarienummer": "2022-00100", "Titel": "6G", "TitelEngelska": "6G"},
]
CALLS = [
    {"Diarienummer": "2024-01511", "DiarienummerProgram": "2024-01502",
     "Titel": "Civil-militära synergier", "TitelEngelska": "Civil-military synergies"},
    {"Diarienummer": "2026-00600", "DiarienummerProgram": "2026-00538",
     "Titel": "Skyddsrum", "TitelEngelska": "x"},
    {"Diarienummer": "2023-00898", "DiarienummerProgram": "2023-00088",
     "Titel": "NFFP8", "TitelEngelska": "NFFP8"},
    {"Diarienummer": "2025-00111", "DiarienummerProgram": "2022-00100",
     "Titel": "6G-utlysning", "TitelEngelska": "6G call"},
]
OPEN_ROUND = {
    "Diarienummer": "2026-01503", "DiarienummerUtlysning": "2024-01511",
    "Titel": "Stärkt ekosystem för civil-militär innovationssamverkan",
    "TitelEngelska": "Stronger ecosystem for civil-military innovation collaboration",
    "Oppningsdatum": "2026-07-02T00:00:00", "Stangningsdatum": "2026-10-13T14:00:00",
    "UppskattatBeslutsdatum": "2026-11-20T00:00:00", "Publik": 1, "Webbsida": 1,
    "WebTextLista": [
        {"TextID": 1, "TextSv": "Projekt som utvecklar metoder.", "TextEn": "Projects that develop methods."},
        {"TextID": 2, "TextSv": "Max 2 miljoner kr.", "TextEn": ""},
    ],
    "LankLista": [{"Beskrivning": "Ansök här", "URL": "https://ansok.vinnova.se/utlysning/abc"}],
    "DokumentLista": [{"Titel": "Utlysningstext", "fileURL": "https://data.vinnova.se/api/file/1",
                       "Lang": "Sv", "Primary": True}],
    "KontaktLista": [{"Namn": "Per Persson", "Telefon": "08 123 12 12",
                      "Epost": "per.persson@vinnova.se"}],
}
INVITED_ROUND = {**OPEN_ROUND, "Diarienummer": "2025-00979", "Publik": 0, "Webbsida": 0,
                 "Titel": "Behovsdriven försvarsinnovation extra", "WebTextLista": []}
CIVIL_DEFENCE_ROUND = {
    **OPEN_ROUND, "Diarienummer": "2026-00702", "DiarienummerUtlysning": "2026-00600",
    "Titel": "Morgondagens skyddsrum", "TitelEngelska": "",
    "Oppningsdatum": "2026-03-31T00:00:00", "Stangningsdatum": "2026-06-10T14:00:00",
    "WebTextLista": [{"TextSv": "Maximalt 800 000 kronor per projekt. "
                                "Den totala budgeten för utlysningen är 10 miljoner kronor.",
                      "TextEn": ""}],
}
AERO_ROUND = {**OPEN_ROUND, "Diarienummer": "2025-04680", "DiarienummerUtlysning": "2023-00898",
              "Titel": "Stärkt svensk flygteknisk forskning",
              "Oppningsdatum": "2026-01-13T00:00:00", "Stangningsdatum": "2026-03-17T14:00:00"}

SIXG_ROUND = {**OPEN_ROUND, "Diarienummer": "2026-00900", "DiarienummerUtlysning": "2025-00111",
              "Titel": "Rymdsektorn med AI och edge learning"}

JOINED = se.join([OPEN_ROUND, INVITED_ROUND, CIVIL_DEFENCE_ROUND, AERO_ROUND, SIXG_ROUND],
                 CALLS, PROGRAMMES)
OPEN, INVITED, CIVIL, AERO, SIXG = JOINED
TODAY = date(2026, 10, 10)


# ------------------------------------------------------------- the register

def test_each_round_names_its_call_and_programme():
    assert OPEN["utlysning"]["Diarienummer"] == "2024-01511"
    assert OPEN["program"]["TitelEngelska"].startswith("The Innovation Program")


def test_a_round_whose_call_is_unknown_is_kept_unjoined_not_dropped():
    orphan = se.join([{**OPEN_ROUND, "DiarienummerUtlysning": "9999-00000"}], CALLS, PROGRAMMES)
    assert orphan[0]["utlysning"] is None and orphan[0]["program"] is None
    assert se.regime(orphan[0]) is None


class _Client:
    def __init__(self, bodies):
        self.bodies, self.asked = bodies, []

    def get(self, url, timeout=None):
        self.asked.append(url)
        body = self.bodies[url.rsplit("/", 2)[1]]

        class _R:
            def raise_for_status(self):
                pass

            def json(self_inner):
                return body
        return _R()


def test_the_whole_register_is_three_requests(monkeypatch):
    monkeypatch.setattr(se.time, "sleep", lambda s: None)
    client = _Client({"program": PROGRAMMES, "utlysningar": CALLS,
                      "ansokningsomgangar": [OPEN_ROUND]})
    rounds = se.fetch_all(client=client)
    assert len(rounds) == 1 and len(client.asked) == 3
    assert all(u.endswith("/2000-01-01") for u in client.asked)


def test_an_empty_register_is_an_error_not_a_register_with_no_calls(monkeypatch):
    monkeypatch.setattr(se.time, "sleep", lambda s: None)
    client = _Client({"program": [], "utlysningar": CALLS, "ansokningsomgangar": [OPEN_ROUND]})
    with pytest.raises(RuntimeError, match="empty register"):
        se.fetch_all(client=client)


# ------------------------------------------------------------------ scope

def test_the_defence_programmes_and_nffp_are_named_and_nothing_else_is():
    assert se.regime(OPEN) == "defence"
    assert se.regime(CIVIL) == "dual_use"
    assert se.regime(AERO) == "dual_use"      # NFFP, by the owner's decision
    assert se.regime(SIXG) is None            # a space round inside a civil programme


def test_an_invited_only_round_is_not_one_a_supplier_can_answer():
    assert se.in_scope(OPEN, today=TODAY)
    assert not se.in_scope(INVITED, today=TODAY)


def test_a_round_closed_in_an_earlier_year_is_out_and_this_years_is_in():
    last_year = {**OPEN, "Stangningsdatum": "2025-06-10T14:00:00"}
    assert not se.in_scope(last_year, today=TODAY)
    assert se.in_scope(CIVIL, today=TODAY)       # closed 10 June 2026, still this year


def test_the_registers_placeholder_date_is_no_date():
    assert se.deadline({"Stangningsdatum": "1900-01-01T00:00:00"}) is None
    assert not se.in_scope({**OPEN, "Stangningsdatum": "1900-01-01T00:00:00"}, today=TODAY)


# ------------------------------------------------------------------ dates

def test_the_deadline_is_stockholm_time_not_utc():
    """14:00 on 13 October is summer time in Stockholm, UTC+2."""
    assert se.deadline(OPEN) == datetime(2026, 10, 13, 12, 0, tzinfo=UTC)
    assert se.opens_at(OPEN) == date(2026, 7, 2)


@pytest.mark.parametrize("now,expected", [
    (datetime(2026, 6, 1, tzinfo=UTC), "forthcoming"),
    (datetime(2026, 10, 10, tzinfo=UTC), "open"),
    (datetime(2026, 10, 14, tzinfo=UTC), "closed"),
])
def test_the_status_follows_the_dates(now, expected):
    assert se.status(OPEN, now=now) == expected


# ----------------------------------------------------------------- budget

def test_a_stated_total_budget_is_read_in_kronor():
    assert se.parse_total_budget(se.eligibility_text(CIVIL)) == 10_000_000.0
    assert se.parse_total_budget("Budgeten för utlysningen är 2 500 000 kronor.") == 2_500_000.0


@pytest.mark.parametrize("text", [
    "Projekt kan söka 1-7 miljoner kronor och pågå i maximalt 12 månader.",
    "Maximalt 800 000 kronor per projekt.",
    "Företag kan söka upp till 1 000 000 kr för utveckling.",
    "",
])
def test_a_ceiling_per_project_is_not_the_calls_budget(text):
    assert se.parse_total_budget(text) is None


# ---------------------------------------------------------------- mapping

def test_a_round_maps_completely():
    call = from_vinnova(OPEN, today=TODAY)
    assert (call.programme_code, call.native_id, call.country, call.issuer) == \
        ("SE-VINNOVA", "2026-01503", "SE", "Vinnova")
    assert call.call_identifier == "2024-01511"
    assert call.regime == "defence"
    assert call.title.startswith("Stronger ecosystem")        # the English title
    assert call.status == "open"
    assert call.source_url == "https://ansok.vinnova.se/utlysning/abc"
    assert call.eligibility_text == "Projects that develop methods. Max 2 miljoner kr."
    assert (call.budget, call.currency, call.budget_scope) == (None, None, None)
    assert call.conditions_raw["decision_expected"] == "2026-11-20T00:00:00"
    assert call.conditions_raw["documents"][0]["primary"] is True


def test_the_budget_is_read_from_the_swedish_text_when_the_english_one_is_shown():
    """The live round 2026-00702 has both: the English text is what is served, and
    "The total budget for the call for proposals is 10 million SEK" is not the pattern.
    Reading the English text left the budget empty on the one call that states one."""
    both = {**CIVIL, "WebTextLista": [{
        "TextSv": "Den totala budgeten för utlysningen är 10 miljoner kronor.",
        "TextEn": "The total budget for the call for proposals is 10 million SEK."}]}
    call = from_vinnova(both, today=TODAY)
    assert call.eligibility_text.startswith("The total budget")
    assert (call.budget, call.currency) == (10_000_000.0, "SEK")


def test_an_untranslated_title_falls_back_to_the_swedish_one():
    call = from_vinnova(CIVIL, today=TODAY)
    assert call.title == "Morgondagens skyddsrum"
    assert (call.budget, call.currency, call.budget_scope) == (10_000_000.0, "SEK", "call")


def test_a_round_outside_the_defence_programmes_is_refused():
    with pytest.raises(ValueError, match="not in a defence programme"):
        from_vinnova(SIXG, today=TODAY)


def test_contact_persons_are_removed_before_landing():
    clean = strip_personal_data(OPEN)
    assert "KontaktLista" not in clean
    assert "per.persson@vinnova.se" not in json.dumps(clean)
