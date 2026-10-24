"""WP-110 (round-4 re-check of 24 October 2026, search precision and stability), no database: the product groups, the
search SQL by main code and without the buyer for a product word, the CPV hints, the funding search's product words, the
subject's sentence that a "kal." does not end, the companies named first, and the search's parts degrading alone."""

from __future__ import annotations

import threading
import time

import pytest

from dgate import search, tenders, textsearch
from dgate import search_terms as S


def groups_of(q: str) -> list[str]:
    return [g.id for g in S.expand(tenders.search_words(q)).groups]


# ------------------------------------------------------------------------------------------- 1. precision of the groups

def test_wiring_harness_is_one_phrase_and_wiring_alone_any_cabling_is_no_group():
    e = S.expand(tenders.search_words("wiring harness"))
    assert [g.id for g in e.groups] == ["wiring"] and len(e.slots) == 1
    assert e.slots[0][0] == ["wiring", "harness"]
    terms = {" ".join(t) for t in e.slots[0][1:]}
    assert "wiring" not in terms and not terms & {"cableado", "câblage", "okablowanie", "cablaggio"}   # cabling, not harnesses
    assert groups_of("wiring") == [] and groups_of("okablowanie") == []


def test_ssi_is_no_cyber_word_and_machining_is_not_spare_parts():
    assert groups_of("SSI") == []                          # Système de Sécurité Incendie: fire alarms (p05)
    assert groups_of("Zerspanung") == groups_of("CNC") == groups_of("Drehteile") == ["machining"]
    assert groups_of("Ersatzteile") == ["spare-parts"]
    assert ["Ersatzteile"] not in S.expand(["CNC"]).slots[0]


def test_every_anchor_is_a_code_of_the_vocabulary_and_one_the_group_suggests_or_names():
    vocabulary = tenders._vocabulary()
    for g in S.groups():
        for a in g.anchors:
            assert any(code.startswith(a) for code in vocabulary), (g.id, a)


def test_a_product_word_reads_the_titles_and_the_main_code_never_the_buyer_or_a_secondary_code():
    where, params, _ = tenders._tender_filters("cyber", None, None, "open", "relevant", None, None, None, None, None, None, None)
    text = next(w for w in where if "opportunity_search ts" in w)
    assert "ts.buyer_name" not in text                      # the Polish cyberspace centre (p05: q=cyber 3,390)
    assert "ts.main_heads && %s::text[]" in text and "ts.cpv_heads" not in text
    assert ["4873", "4876", "7221273"] in params
    assert " ".join(where).count("%s") == len(params)
    # a word of no group still reads the buyer's name, and the codes its word begins by the main code only
    where, params, _ = tenders._tender_filters("radar", None, None, "open", "relevant", None, None, None, None, None, None, None)
    text = next(w for w in where if "opportunity_search ts" in w)
    assert "ts.buyer_name LIKE dg_word_pattern(%s)" in text and "ts.main_heads" in text and "ts.cpv_heads" not in text
    assert " ".join(where).count("%s") == len(params)
    # "wiring" names 45311000 Electrical wiring work by its title: read as a main code only
    where, params, _ = tenders._tender_filters("wiring", None, None, "open", "relevant", None, None, None, None, None, None, None)
    assert any(isinstance(p, list) and "45311000" in p for p in params)
    assert "ts.cpv_heads" not in " ".join(where)


def test_the_cpv_hints_name_the_codes_with_their_official_titles():
    hints = tenders.search_info("wiring harness")["cpvHints"]
    assert hints[0] == {"code": "31611000", "title": "Wiring sets", "prefix": "31611"}
    ersatz = tenders.search_info("Ersatzteile")["cpvHints"]
    assert {"code": "35400000", "title": "Military vehicles and associated parts", "prefix": "354"} in ersatz
    assert len(ersatz) <= tenders.MAX_CPV_HINTS
    assert tenders.search_info("radar")["cpvHints"][0]["code"] == "35722000"       # a word of no group: the codes its word begins
    assert tenders.search_info("220199-2026")["cpvHints"] == []
    assert tenders.search_info("Bundeswehr")["cpvHints"] == []
    # a buyer's name of several words names no code ("van": Vans, Vanadium on production before this rule)
    assert tenders.search_info("Ministerie van Defensie")["cpvHints"] == []
    assert tenders.search_info("van")["cpvHints"][0]["code"] == "34136000"                    # Vans: the word itself


# ------------------------------------------------------------------------------------------- funding search

def test_the_funding_search_reads_the_product_words_of_every_language():
    q = textsearch.parse("cybersécurité", products=True)
    assert q.matches("Cybersecurity of critical infrastructure")
    assert not q.matches("Fire safety systems")
    assert not textsearch.parse("cybersécurité").matches("Cybersecurity of critical infrastructure")   # the organisations' search keeps its own
    assert textsearch.parse("Ersatzteile", products=True).matches("Spare parts for legacy platforms")


# ------------------------------------------------------------------------------------------- the subject's first sentence

@pytest.mark.parametrize("text, want", [
    ("Dostawa amunicji kal. 5,56 do karabinków. Termin dostawy 2027.", "Dostawa amunicji kal. 5,56 do karabinków."),
    ("Remont budynku nr 16. Zakres obejmuje dach.", "Remont budynku nr 16."),
    ("Dostawa ok. 300 sztuk hełmów, tj. Hełmy kevlarowe. Druga część.", "Dostawa ok. 300 sztuk hełmów, tj. Hełmy kevlarowe."),
    ("Lieferung von Ersatzteilen, z.B. Getriebe. Weitere Angaben folgen.", "Lieferung von Ersatzteilen, z.B. Getriebe."),
    ("Suministro de repuestos, aprox. 40 Unidades. Lote 2.", "Suministro de repuestos, aprox. 40 Unidades."),
    ("Supply of spare parts, ca. 200 Items, e.g. Gearboxes. Second sentence.", "Supply of spare parts, ca. 200 Items, e.g. Gearboxes."),
    ("Pièces de rechange réf. A4 pour véhicules. Lot unique.", "Pièces de rechange réf. A4 pour véhicules."),
    ("One sentence only", "One sentence only"),
])
def test_an_abbreviation_does_not_end_the_subject(text, want):
    assert tenders.first_sentence(text) == want
    assert tenders.commercial_subject(text) == want


LETTER_HEAD = """Öffentlicher Auftraggeber:

Bundesamt für Ausrüstung, Informationstechnik und Nutzung der Bundeswehr
Ferdinand-Sauerbruch-Str. 1
56073 Koblenz
Referat: I2.2Q

Auftragnehmer:

W+R Schirmungstechnik
Gewerbering 23
76287 Rheinstetten


Q/I2BQ/PA103/MA447 Beschaffung Schirmkabinen

Lieferdatum 30.10.2024


Schirmkabinen"""


@pytest.mark.parametrize("text, want", [
    # the BAAINBw texts of the open notices on production (24 October 2026), as the list showed them
    ("GELENKWELLE MIT AUSGLEICHSGELENK, FAHRZE 2520410039852", "GELENKWELLE MIT AUSGLEICHSGELENK"),
    ("3.564.000 EA", None),
    ("100 EA", None),
    ("18 EA GETRIEBE, MECHANISCH, FAHRZEUG (Vers.Art. 2520-124147925)", "18 EA GETRIEBE, MECHANISCH, FAHRZEUG"),
    ("Bei der zu beschaffenden Leistung handelt es sich um 12 EA Kugelventile für die U-Boote Klasse 212A der Deutschen Marine, "
     "Versorgungs-Artikel-Nummer 4810124237469.",
     "Bei der zu beschaffenden Leistung handelt es sich um 12 EA Kugelventile für die U-Boote Klasse 212A der Deutschen Marine"),
    (LETTER_HEAD, "Beschaffung Schirmkabinen Schirmkabinen"),
    ("Q/I2BM/QA111/GA739 - Beschaffung 10 x Iridium 9575\nbis 04.10.2024\nTelemar Electronics GmbH\n"
     "Bundesamt für Ausrüstung, Informationstechnik und Nutzung der Bundeswehr\nFerdinand Sauerbruch Straße 1\n56073 Koblenz\n\n"
     "Kommunikationstechnik", "Beschaffung 10 x Iridium 9575 Telemar Electronics GmbH Kommunikationstechnik"),
    # an ordinary description of several lines is not a letter head: unchanged
    ("Lieferung von Ersatzteilen\nfür Fahrzeuge der Bundeswehr.", "Lieferung von Ersatzteilen für Fahrzeuge der Bundeswehr."),
])
def test_a_subject_is_words_not_an_address_a_quantity_or_an_item_number(text, want):
    got = tenders.commercial_subject(text)
    assert got == want
    assert got is None or ("Koblenz" not in got and "56073" not in got and "Referat" not in got)


# ------------------------------------------------------------------------------------------- companies named first

class FakeConn:
    def __init__(self, rows):
        self.rows = rows

    def execute(self, sql, params=None):
        class R:
            def __init__(self, rows):
                self._rows = rows

            def fetchall(self):
                return self._rows
        return R(self.rows)


def test_a_company_found_by_a_published_name_comes_after_the_named_ones_and_says_that_name():
    items = [{"id": "426671", "name": "Leonardo S.p.A."}, {"id": "427616", "name": "Megmar Logistics & Consulting Sp. z o.o."},
             {"id": "412040", "name": "LEONARDO Germany GmbH"}]
    stated = "Konsorcjum: MEGMAR Logistics & Consulting Sp. z o.o. Leonardo Poland Sp. z o.o."
    conn = FakeConn([{"id": 427616, "n": "Megmar Logistics & Consulting sp. z o.o."}, {"id": 427616, "n": stated}])
    got = search.named_first(conn, "Leonardo", [dict(i) for i in items])
    assert [i["id"] for i in got] == ["426671", "412040", "427616"]
    assert got[2]["matchedAs"] == stated and "matchedAs" not in got[0]


# ------------------------------------------------------------------------------------------- the parts degrade alone

def test_the_parts_run_at_once_and_one_without_a_connection_is_busy_not_the_search(monkeypatch):
    started: list[float] = []

    class Gate:
        def acquire(self, timeout=None):
            return True

        def release(self):
            pass

    class NoConnection:
        def __enter__(self):
            raise search.db.PoolBusy("full")

        def __exit__(self, *a):
            return False

    def busy_connect(*a, **k):
        started.append(time.monotonic())
        return NoConnection()

    monkeypatch.setattr(search, "_PART_GATE", Gate())
    monkeypatch.setattr(search.db, "bounded_connect", busy_connect)
    body = search.search(q="radar", limit=5)
    assert all(body[g] == {"error": "busy"} for g in search.GROUPS)
    assert len(started) == len(search.GROUPS)


def test_a_part_that_misses_the_deadline_is_cancelled_and_answers_slow(monkeypatch):
    release = threading.Event()
    cancelled: list[bool] = []

    class Conn:
        def execute(self, sql, params=None):
            if sql.startswith("SET"):
                return None
            release.wait(5)
            raise search.psycopg.errors.QueryCanceled("cancelled")

        def cancel(self):
            cancelled.append(True)
            release.set()

    class Ctx:
        def __enter__(self):
            return Conn()

        def __exit__(self, *a):
            return False

    def page(**kw):
        kw["conn"].execute("SELECT pg_sleep(9)")
        return {"items": [], "total": 0}

    def quick(**kw):
        return {"items": [], "total": 0}

    monkeypatch.setattr(search.db, "bounded_connect", lambda *a, **k: Ctx())
    monkeypatch.setattr(search, "GROUPS", {"tenders": page, "funding": quick, "buyers": quick, "suppliers": quick,
                                           "organisations": quick})
    monkeypatch.setattr(search, "BUDGET_MS", 800)
    t = time.monotonic()
    body = search.search(q="Regionalna Baza Logistyczna", limit=5)
    assert time.monotonic() - t < 1.0
    assert body["tenders"] == {"error": "slow"} and cancelled == [True]
    assert body["funding"]["total"] == 0 and body["buyers"]["total"] == 0          # the other parts answered
