"""PLACSP: what the connector reads as value, publication date, legal basis and
procedure, and how far a live walk goes (findings F11 and F18 of 12 October 2026).

The fixture, `fixtures/placsp_live_entries.atom`, is three real entries of the live
feed, read on 12 October 2026 and stripped to the elements the parser reads.
"""

from __future__ import annotations

import dataclasses
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest

from dgate import pipeline
from dgate.classify import classify
from dgate.db import opportunity_payload
from dgate.sources import placsp
from dgate.tenders import procedure_label

from .test_placsp import _entry, _page

FIXTURE = (Path(__file__).resolve().parents[1] / "fixtures" / "placsp_live_entries.atom")
XML = FIXTURE.read_text(encoding="utf-8")


def _by_id(xml: str = XML) -> dict:
    opps, _ = placsp.parse_feed(xml.encode("utf-8"))
    return {o.native_id: o for o in opps}


# ----------------------------------------------------------------- value

def test_the_value_is_the_estimated_overall_amount_not_the_years_budget_with_vat():
    """138/2026 is a five-year hunting lease: 35,470.55 estimated over its term,
    8,583.87 as the first year's budget with VAT. The row showed the second."""
    o = _by_id()["138/2026"]
    assert o.value_amount == 35470.55
    assert o.value_currency == "EUR"
    assert _by_id()["2026-032"].value_amount == 1304000.0


def test_an_entry_without_an_estimate_reads_the_budget_without_vat_first():
    """Changed on purpose, 14 October 2026 (data-correctness DC1): the fallback was
    TotalAmount (with VAT) and then TaxExclusiveAmount, which put 1.21 times the TED value
    on 25 of 103 September twin pairs. TED's values are net of VAT, so is the first now."""
    bare = XML.replace(
        '<cbc:EstimatedOverallContractAmount currencyID="EUR">35470.55'
        '</cbc:EstimatedOverallContractAmount>', "")
    assert _by_id(bare)["138/2026"].value_amount == 7094.11        # TaxExclusiveAmount
    no_net = bare.replace('<cbc:TaxExclusiveAmount currencyID="EUR">7094.11'
                          '</cbc:TaxExclusiveAmount>', "")
    assert _by_id(no_net)["138/2026"].value_amount == 8583.87      # then TotalAmount


def test_a_zero_estimate_does_not_hide_a_budget():
    zero = XML.replace(">35470.55<", ">0<")
    assert _by_id(zero)["138/2026"].value_amount == 7094.11        # the budget without VAT


def test_the_currency_is_the_one_the_figure_states():
    odd = XML.replace('<cbc:EstimatedOverallContractAmount currencyID="EUR">35470.55',
                      '<cbc:EstimatedOverallContractAmount currencyID="USD">35470.55')
    assert _by_id(odd)["138/2026"].value_currency == "USD"


# ----------------------------------------------------- publication date

def test_the_publication_date_is_the_call_notices_not_the_entrys_update():
    by_id = _by_id()
    # entry updated 11 October, notice published in the buyer profile on 7 October
    assert by_id["138/2026"].published_at == date(2026, 10, 7)
    assert by_id["138/2026"].source_updated_at == datetime.fromisoformat(
        "2026-10-11T19:54:50.934+02:00")
    assert by_id["2026/ETSAE0921/00001111E"].published_at == date(2026, 10, 10)


def test_an_amended_notice_keeps_its_first_publication_date():
    """2026-032 was republished on 3 and 11 June, and DOUE printed it on 18 May and
    4 June. The portal's own first publication is 16 May."""
    assert _by_id()["2026-032"].published_at == date(2026, 5, 16)


def _notices(*infos: tuple[str, str, list[str]]) -> str:
    """ValidNoticeInfo blocks: (notice type, medium, [issue dates])."""
    out = ""
    for kind, medium, dates in infos:
        refs = "".join(
            "<cac-place-ext:AdditionalPublicationDocumentReference>"
            f"<cbc:IssueDate>{d}</cbc:IssueDate>"
            "</cac-place-ext:AdditionalPublicationDocumentReference>" for d in dates)
        out += ("<cac-place-ext:ValidNoticeInfo>"
                f"<cbc-place-ext:NoticeTypeCode>{kind}</cbc-place-ext:NoticeTypeCode>"
                "<cac-place-ext:AdditionalPublicationStatus>"
                f"<cbc-place-ext:PublicationMediaName>{medium}</cbc-place-ext:PublicationMediaName>"
                f"{refs}</cac-place-ext:AdditionalPublicationStatus>"
                "</cac-place-ext:ValidNoticeInfo>")
    return out


def _one(notices: str, updated: str = "2026-10-11T19:54:50+02:00"):
    entry = (f"<entry><id>x</id><title>t</title><updated>{updated}</updated>"
             "<cac-place-ext:ContractFolderStatus><cbc:ContractFolderID>F-1</cbc:ContractFolderID>"
             "<cac:ProcurementProject><cbc:Name>t</cbc:Name></cac:ProcurementProject>"
             f"{notices}</cac-place-ext:ContractFolderStatus></entry>")
    opps, _ = placsp.parse_feed(_page(entry, None))
    return opps[0]


def test_a_gazette_date_is_the_fallback_when_the_portal_has_none():
    o = _one(_notices(("DOC_CN", "DOUE", ["2026-03-30"]), ("DOC_CN", "BOE", ["2026-04-02"])))
    assert o.published_at == date(2026, 3, 30)


def test_the_portals_own_medium_wins_over_a_gazette_a_day_earlier():
    """DOUE can print a day before the buyer profile's date (22/2026: 11 and 12 August)."""
    o = _one(_notices(("DOC_CN", "DOUE", ["2026-08-11"]),
                      ("DOC_CN", "Perfil del contratante", ["2026-08-12"]),
                      ("DOC_CN", "PCPCM – Perfil contratante", ["2026-08-14"])))
    assert o.published_at == date(2026, 8, 12)


def test_prior_information_is_the_date_only_when_there_is_no_call():
    pin = ("DOC_PIN", "Perfil del contratante", ["2026-01-10"])
    cn = ("DOC_CN", "Perfil del contratante", ["2026-03-01"])
    assert _one(_notices(pin)).published_at == date(2026, 1, 10)
    assert _one(_notices(pin, cn)).published_at == date(2026, 3, 1)


def test_an_entry_with_only_later_notices_has_no_publication_date():
    """The call was published before the feed existed; the entry carries the award and
    the formalisation. Until 13 October 2026 the earliest of them was taken as the
    publication (2026-09-18 here), which put 288 of 1,349 entries after their own
    deadline: an award is not the tender's publication, and the date is left empty."""
    o = _one(_notices(("DOC_FORM", "Perfil del contratante", ["2026-10-11"]),
                      ("DOC_CAN_ADJ", "Perfil del contratante", ["2026-09-18", "2026-09-23"])))
    assert o.published_at is None


def test_a_date_with_an_offset_is_still_a_date():
    o = _one(_notices(("DOC_CN", "Perfil del contratante", ["2026-10-07+02:00"])))
    assert o.published_at == date(2026, 10, 7)


def test_without_any_publication_date_published_at_stays_empty():
    """The Atom time is when the entry last changed. It is kept, apart."""
    o = _one("")
    assert o.published_at is None
    assert o.source_updated_at == datetime.fromisoformat("2026-10-11T19:54:50+02:00")
    unreadable = _one("", updated="not a time")
    assert unreadable.source_updated_at is None


def test_the_update_time_does_not_enter_the_hash_of_other_sources():
    """`source_updated_at` is left out of the payload while empty, as `ted_ref` is."""
    from dgate.normalise import Opportunity

    bare = Opportunity(source_code="ted", native_id="1-2026", buyer_name_raw="x",
                       title_original="t")
    assert "source_updated_at" not in opportunity_payload(bare)
    held = _by_id()["138/2026"]
    assert opportunity_payload(held)["source_updated_at"].startswith("2026-10-11T19:54:50")


# ----------------------------------------------------------- legal basis

def test_a_directive_becomes_the_celex_number_every_source_uses():
    by_id = _by_id()
    assert by_id["2026/ETSAE0921/00001111E"].legal_basis == "32009L0081"
    assert by_id["2026-032"].legal_basis == "32014L0025"
    for text, celex in (("2009/81/CE", "32009L0081"), ("2014/24/UE", "32014L0024"),
                        ("2014/23/EU", "32014L0023")):
        assert placsp.map_legal_basis(text, "3") == celex


def test_the_defence_directive_reaches_the_classifier_as_a_signal():
    o = _by_id()["2026/ETSAE0921/00001111E"]
    sig = classify(legal_basis=o.legal_basis, cpv_codes=o.cpv_codes, buyer_is_defence=False)
    assert sig.legal_basis and sig.is_defence
    civil = _by_id()["2026-032"]
    assert not classify(legal_basis=civil.legal_basis, cpv_codes=civil.cpv_codes,
                        buyer_is_defence=False).legal_basis


def test_without_a_directive_the_national_regime_is_stored():
    assert _by_id()["138/2026"].legal_basis == "Ley 9/2017 (LCSP)"
    assert placsp.map_legal_basis("N/A", "2") == "Ley 24/2011 (defensa y seguridad)"
    # a code nobody verified is kept as the code, not as a guess at its meaning
    assert placsp.map_legal_basis(None, "0") == "ES legislation code 0"
    assert placsp.map_legal_basis("N/A", None) is None
    assert placsp.map_legal_basis(None, None) is None


# ------------------------------------------------------------- procedure

def test_verified_procedure_codes_are_named_and_readable_by_the_api():
    by_id = _by_id()
    assert by_id["138/2026"].procedure_type == "Abierto"
    assert by_id["2026/ETSAE0921/00001111E"].procedure_type == "Negociado con publicidad"
    assert procedure_label(by_id["138/2026"].procedure_type) == "Abierto"
    assert procedure_label("Negociado sin publicidad") == "Negociado sin publicidad"


def test_a_code_nobody_verified_stays_the_code():
    assert placsp.map_procedure("3") == "Negociado sin publicidad"
    assert placsp.map_procedure("9") == "Abierto simplificado"
    assert placsp.map_procedure("100") == "Normas internas"
    assert placsp.map_procedure("5") == "5"          # seen once; not enough to name
    assert placsp.map_procedure("7") == "7"          # not seen at all
    assert placsp.map_procedure(None) is None
    assert placsp.map_procedure("  ") is None


# ------------------------------------------------------------ the walk

PORTAL = "https://contrataciondelestado.es/sindicacion/sindicacion_643"
OWN = "https://contrataciondelsectorpublico.gob.es/sindicacion/sindicacion_643"


def _pages(spec: dict[str, tuple[list[str], str | None]]):
    """{path: (stamps, next link)} -> a client, and the list of requested URLs."""
    asked: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        asked.append(str(request.url))
        stamps, link = spec[request.url.path]
        body = "".join(_entry(f"E-{request.url.path[-8:]}-{i}", "PUB", s)
                       for i, s in enumerate(stamps))
        return httpx.Response(200, content=_page(body, link))

    return httpx.Client(transport=httpx.MockTransport(handler)), asked


def _walk(spec, **kw):
    client, asked = _pages(spec)
    seen: dict = dict(kw.pop("observe", {}))
    with client:
        got = list(placsp.fetch_live(placsp.MAIN, client=client, observe=seen, **kw))
    return got, seen, asked


def _stamp(hour: int) -> str:
    return f"2026-10-11T{hour:02d}:00:00+02:00"


CHAIN = {
    "/sindicacion/sindicacion_643/licitacionesPerfilesContratanteCompleto3.atom":
        ([_stamp(12), _stamp(10)], f"{PORTAL}/p2.atom"),
    "/sindicacion/sindicacion_643/p2.atom": ([_stamp(9), _stamp(8)], f"{PORTAL}/p3.atom"),
    "/sindicacion/sindicacion_643/p3.atom": ([_stamp(7), _stamp(6)], f"{PORTAL}/p4.atom"),
    "/sindicacion/sindicacion_643/p4.atom": ([_stamp(5)], None),
}


def test_the_portal_host_is_never_requested():
    """Every next link the live feed carries is written with the portal's host, whose
    robots.txt is `Disallow: /`. The walk reads the same file from the syndication
    host, and before this it refused the link and stopped after one page."""
    got, seen, asked = _walk(CHAIN, max_pages=5)
    assert len(got) == 7 and seen["pages"] == 4
    assert {httpx.URL(u).host for u in asked} == {"contrataciondelsectorpublico.gob.es"}
    assert asked[1] == f"{OWN}/p2.atom"


def test_a_link_to_another_host_or_directory_is_refused_and_reported():
    for link in ("https://example.test/sindicacion/sindicacion_643/p2.atom",
                 "https://contrataciondelestado.es/sindicacion/sindicacion_1044/p2.atom",
                 "http://contrataciondelestado.es/sindicacion/sindicacion_643/p2.atom",
                 "https://contrataciondelestado.es/other/p2.atom"):
        spec = {"/sindicacion/sindicacion_643/licitacionesPerfilesContratanteCompleto3.atom":
                ([_stamp(12)], link)}
        _, seen, asked = _walk(spec, max_pages=5)
        assert seen["pages"] == 1 and seen["refused"], link
        assert len(asked) == 1


def test_without_a_mark_the_walk_is_the_page_count_it_always_was():
    got, seen, _ = _walk(CHAIN, max_pages=2)
    assert seen["pages"] == 2 and len(got) == 4 and not seen["capped"]


def test_the_walk_goes_past_the_page_count_until_it_reaches_the_previous_runs_newest():
    until = datetime.fromisoformat(_stamp(7)) + timedelta(minutes=30)       # 07:30
    got, seen, _ = _walk(CHAIN, max_pages=1, observe={"until": until, "hard_cap": 10})
    assert seen["pages"] == 3 and not seen["capped"]                        # 06:00 <= 07:30
    assert len(got) == 6
    assert seen["newest"] == datetime.fromisoformat(_stamp(12))


def test_a_walk_that_hits_the_cap_before_the_mark_says_so():
    until = datetime.fromisoformat(_stamp(5)) - timedelta(minutes=30)
    got, seen, _ = _walk(CHAIN, max_pages=1, observe={"until": until, "hard_cap": 2})
    assert seen["pages"] == 2 and seen["capped"] is True
    assert len(got) == 4


def test_a_page_whose_stamps_cannot_be_read_does_not_end_the_walk():
    chain = {k: v for k, v in CHAIN.items()}
    first = "/sindicacion/sindicacion_643/licitacionesPerfilesContratanteCompleto3.atom"
    chain[first] = (["not a time", "also not"], f"{PORTAL}/p2.atom")
    until = datetime.fromisoformat(_stamp(12))
    _, seen, _ = _walk(chain, max_pages=1, observe={"until": until, "hard_cap": 10})
    assert seen["pages"] == 2          # page 2 is 09:00, which is before the mark


def test_the_chain_ending_before_the_mark_is_not_a_gap():
    until = datetime.fromisoformat(_stamp(1))
    _, seen, _ = _walk(CHAIN, max_pages=1, observe={"until": until, "hard_cap": 10})
    assert seen["pages"] == 4 and not seen["capped"] and not seen["refused"]


# ------------------------------------------------- what the run reports

NOW = datetime(2026, 10, 12, 7, 0, tzinfo=timezone.utc)


def _live(monkeypatch, **observed):
    calls: list[tuple[str, str | None]] = []
    sent: list[str] = []
    archives: list[str] = []

    def fake_live(ds, max_pages, observe, **kw):
        assert observe["hard_cap"] >= max_pages
        observe.update(observed)
        return iter(())

    def fake_ingest(opps, label, ds, stale_reason=None, **kw):
        list(opps)
        calls.append((label, stale_reason() if stale_reason else None))

    monkeypatch.setattr(placsp, "fetch_live", fake_live)
    monkeypatch.setattr(placsp, "fetch_archive",
                        lambda url, *a, **k: archives.append(url) or iter(()))
    monkeypatch.setattr(pipeline, "_ingest_placsp", fake_ingest)
    monkeypatch.setattr("dgate.ops.notify.notify", lambda text: sent.append(text))
    pipeline.run_placsp_live(datasets=[placsp.MAIN], now=NOW)
    return calls, sent, archives


def test_a_capped_walk_is_partial_loud_and_names_the_command(monkeypatch):
    until = datetime(2026, 10, 5, 20, 4, tzinfo=timezone.utc)
    calls, sent, archives = _live(
        monkeypatch, capped=True, pages=120, until=until,
        newest=datetime(2026, 10, 12, 6, 0, tzinfo=timezone.utc))
    _, reason = calls[0]
    assert reason and "cap of 120 pages" in reason
    assert "placsp-backfill --from 2026-10" in reason
    assert sent and "placsp-backfill" in sent[0]
    assert archives == []              # the newest entry is fresh: not the frozen-feed path


def test_a_refused_link_is_partial_and_loud(monkeypatch):
    calls, sent, _ = _live(monkeypatch, refused="https://example.test/x.atom",
                           newest=datetime(2026, 10, 12, 6, 0, tzinfo=timezone.utc))
    assert calls[0][1] and "left the feed's directory" in calls[0][1]
    assert sent


def test_a_complete_walk_is_not_reported(monkeypatch):
    calls, sent, _ = _live(monkeypatch, capped=False, pages=3,
                           newest=datetime(2026, 10, 12, 6, 0, tzinfo=timezone.utc))
    assert calls == [("es_placsp-live", None)] and sent == []


# ------------------------------------------------------------ the replay

@pytest.mark.parametrize("hour, minute, inside", [
    (6, 19, False), (6, 20, True), (6, 30, True), (8, 30, True), (8, 31, False), (14, 0, False),
])
def test_the_replay_keeps_out_of_the_live_walks_window(hour, minute, inside):
    cfg = dataclasses.make_dataclass("Cfg", [("placsp_hour", int), ("placsp_minute", int)])(6, 30)
    assert pipeline._in_live_window(
        datetime(2026, 10, 12, hour, minute, tzinfo=timezone.utc), cfg) is inside
