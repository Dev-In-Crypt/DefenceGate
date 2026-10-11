"""The Finnish connector (MATINE, the Ministry of Defence's advisory board).

The text is the page `maararahahaku-2027` as it read on 11 October 2026, shortened.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from dgate.normalise import from_matine, strip_personal_data
from dgate.sources import matine

PAGE_TEXT = (
    "Määrärahahaku 2027 Maanpuolustuksen tieteellinen neuvottelukunta (MATINE) edistää ja "
    "rahoittaa tieteellistä tutkimusta. Vuonna 2027 MATINE varautuu käynnistämään 10-20 "
    "tutkimushanketta, yhteisarvoltaan enintään 1 850 000 euroa, joilla pyritään uusiin "
    "tieteellisiin avauksiin. Tutkimusmäärärahojen sähköisten hakemusten viimeinen "
    "lähetysaika sekä paperisten hakemusten (postileima) määräaika on torstai 11.6.2026 "
    "klo 16:00. MATINE päättää kokouksessaan 3.12.2026 hankkeet, joita se esittää "
    "puolustusministeriölle käynnistettäväksi helmikuussa 2027."
)
PAGE_HTML = """<html><head><meta property="og:title" content="Määrärahahaku 2027 - Puolustusministeriö" />
</head><body><header>valikko</header><main><h1>Määrärahahaku 2027</h1><p>%s</p>
<p>Lisätietoja Hakuun liittyen MATINEn sihteeristö antaa tarvittaessa lisätietoja:
matine.plm (at) gov.fi Pääsihteeri Matti Meikäläinen +358 295 140 114</p></main></body></html>
""" % PAGE_TEXT


# ------------------------------------------------------------------ parsing

def test_the_deadline_is_helsinki_time_not_utc():
    """16:00 on 11 June is summer time in Helsinki, UTC+3."""
    assert matine.deadline(PAGE_TEXT) == datetime(2026, 6, 11, 13, 0, tzinfo=UTC)


def test_the_sum_is_the_total_for_all_projects():
    assert matine.total_budget(PAGE_TEXT) == 1_850_000.0
    assert matine.project_range(PAGE_TEXT) == (10, 20)
    assert matine.decision_date(PAGE_TEXT) == date(2026, 12, 3)


def test_a_page_without_the_sentences_has_nothing_rather_than_a_guess():
    assert matine.deadline("Haku avataan keväällä.") is None
    assert matine.total_budget("Haku avataan keväällä.") is None
    assert matine.project_range("") is None


@pytest.mark.parametrize("now,expected", [
    (datetime(2026, 5, 1, tzinfo=UTC), "open"),
    (datetime(2026, 10, 11, tzinfo=UTC), "closed"),
])
def test_the_status_follows_the_deadline(now, expected):
    assert matine.status({"text": PAGE_TEXT}, now=now) == expected


def test_a_call_closed_in_an_earlier_year_is_out():
    assert matine.in_scope({"text": PAGE_TEXT}, today=date(2026, 10, 11))
    assert not matine.in_scope({"text": PAGE_TEXT}, today=date(2027, 3, 1))


# ------------------------------------------------------------------ fetching

class _Client:
    def __init__(self, pages):
        self.pages = pages

    def get(self, url, timeout=None):
        class _R:
            text = self.pages[url]

            def raise_for_status(self):
                pass
        return _R()


LANDING_URL = matine.SITE + matine.LANDING
CALL_URL = LANDING_URL + "/maararahahaku-2027"


def test_the_calls_are_the_pages_the_landing_page_links(monkeypatch):
    monkeypatch.setattr(matine.time, "sleep", lambda s: None)
    landing = f'<a href="{CALL_URL}">Määrärahahaku 2027</a><a href="{LANDING_URL}/blogi">blogi</a>'
    records = matine.fetch_all(client=_Client({LANDING_URL: landing, CALL_URL: PAGE_HTML}))
    assert [r["slug"] for r in records] == ["maararahahaku-2027"]
    assert records[0]["year"] == 2027
    assert records[0]["title"] == "Määrärahahaku 2027 - Puolustusministeriö"


def test_the_page_is_cut_before_the_officials_and_their_numbers(monkeypatch):
    monkeypatch.setattr(matine.time, "sleep", lambda s: None)
    landing = f'<a href="{CALL_URL}">x</a>'
    record = matine.fetch_all(client=_Client({LANDING_URL: landing, CALL_URL: PAGE_HTML}))[0]
    assert "Meikäläinen" not in record["text"] and "+358" not in record["text"]
    assert "11.6.2026" in record["text"]


def test_a_landing_page_with_no_call_link_is_an_error_not_no_calls(monkeypatch):
    monkeypatch.setattr(matine.time, "sleep", lambda s: None)
    with pytest.raises(RuntimeError, match="page changed shape"):
        matine.fetch_all(client=_Client({LANDING_URL: "<main>tyhjä</main>"}))


# ------------------------------------------------------------------ mapping

def test_a_page_maps_completely():
    record = {"url": CALL_URL, "slug": "maararahahaku-2027", "year": 2027,
              "title": "Määrärahahaku 2027 - Puolustusministeriö", "text": PAGE_TEXT}
    call = from_matine(record, today=date(2026, 10, 11))
    assert (call.programme_code, call.native_id, call.country, call.regime) == \
        ("FI-MATINE", "maararahahaku-2027", "FI", "defence")
    assert call.title == "MATINE määrärahahaku 2027 (research funding call)"
    assert (call.budget, call.currency, call.budget_scope) == (1_850_000.0, "EUR", "call")
    assert call.deadline_at == datetime(2026, 6, 11, 13, 0, tzinfo=UTC)
    assert call.status == "closed"
    assert call.type_of_action == "research grant"
    assert call.conditions_raw["projects"] == [10, 20]
    assert call.conditions_raw["decision_date"] == "2026-12-03"
    assert call.source_url == CALL_URL


def test_a_record_without_a_year_is_refused():
    with pytest.raises(ValueError, match="no slug or year"):
        from_matine({"slug": "x", "text": ""})


def test_an_address_in_the_page_is_removed_before_landing():
    clean = strip_personal_data({"slug": "x", "year": 2027,
                                 "text": "kysy matine@example.fi lisää"})
    assert "matine@example.fi" not in clean["text"]
