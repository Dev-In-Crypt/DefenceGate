"""WP-159: the contract period a notice states (one eForms reader for TED, BKMS and BOAMP, PLACSP's CODICE), kept out
of the versioned facts, and the data API's default source list."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from dgate import config, db
from dgate.normalise import (
    CONTRACT_PERIOD_FIELDS,
    Opportunity,
    contract_period,
    from_boamp,
    from_de_bkms,
    from_ted,
)
from dgate.ops import contract_periods
from dgate.ops.repair_ted import REMAPPED, plan_change
from dgate.sources import placsp, ted

from .test_placsp import _page

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "de_bkms"


def _g(**kw):
    return {k.replace("_", "-"): v for k, v in kw.items()}.get


# ------------------------------------------------------------------ the reader

def test_several_lots_give_the_earliest_start_the_latest_end_and_the_longest_duration():
    got = contract_period(_g(duration_period_value_lot=["12", "3"], duration_period_unit_lot=["MONTH", "YEAR"],
                             contract_duration_start_date_lot=["2027-01-01+01:00", "2026-12-01+01:00"],
                             contract_duration_end_date_lot=["2027-12-31+01:00", "2029-11-30Z"],
                             renewal_maximum_lot=["2", "0"]))
    assert got == {"contract_start": date(2026, 12, 1), "contract_end": date(2029, 11, 30), "contract_duration": 3,
                   "contract_duration_unit": "YEAR", "contract_renewals_max": 2, "contract_renewal": True}


def test_a_notice_without_a_period_gives_nothing():
    assert contract_period(_g(notice_type="cn-standard")) == {}
    # BT-58 of 0 says no renewal; it is kept as stated and is no renewal flag
    assert contract_period(_g(renewal_maximum_lot=["0"])) == {"contract_renewals_max": 0}


@pytest.mark.parametrize("values,units,expected", [
    (["24"], ["month"], (24, "MONTH")),                 # unit case does not matter
    (["1.5"], ["YEAR"], (18, "MONTH")),                 # a fraction becomes whole months
    (["90", "6"], ["DAY", "MON"], (6, "MONTH")),        # CODICE's UN/ECE code; 6 months is longer than 90 days
    (["10", "20"], ["MONTH"], (20, "MONTH")),           # one unit stated once applies to every lot
    (["10", "20"], ["MONTH", "YEAR", "DAY"], None),     # lists that do not line up are not guessed
    (["0"], ["MONTH"], None), (["x"], ["MONTH"], None), (["24"], ["FORTNIGHT"], None),
    (["5000"], ["YEAR"], None),                          # a typo, not a contract
])
def test_the_duration_is_read_as_stated(values, units, expected):
    got = contract_period(_g(duration_period_value_lot=values, duration_period_unit_lot=units))
    assert (got.get("contract_duration"), got.get("contract_duration_unit")) == (expected or (None, None))


def test_an_end_before_the_start_and_an_impossible_year_are_not_read():
    got = contract_period(_g(contract_duration_start_date_lot="2027-01-01", contract_duration_end_date_lot="2026-01-01"))
    assert got == {"contract_start": date(2027, 1, 1)}
    assert contract_period(_g(contract_duration_end_date_lot="0201-01-01")) == {}


def test_a_renewal_described_without_a_number_is_a_renewal():
    assert contract_period(_g(renewal_description_lot={"deu": ["Zweimal ein Jahr"]})) == {"contract_renewal": True}
    assert contract_period(_g(renewal_description_lot={})) == {}


# ------------------------------------------------------------------ the sources

def test_ted_asks_for_the_period_fields_and_maps_them():
    assert set(CONTRACT_PERIOD_FIELDS) <= set(ted.TED_FIELDS)
    opp = from_ted({"publication-number": "1-2026", "notice-title": {"eng": "t"}, "buyer-name": "b",
                    "notice-type": "can-standard", "duration-period-value-lot": ["48"],
                    "duration-period-unit-lot": ["MONTH"], "contract-duration-end-date-lot": ["2030-04-30+02:00"]})
    assert (opp.contract_duration, opp.contract_duration_unit, opp.contract_end) == (48, "MONTH", date(2030, 4, 30))


def _bkms(lot_extra: str) -> dict:
    xml = (FIX / "cn_standard_defence.xml").read_text(encoding="utf-8")
    xml = xml.replace("<cbc:Name languageID=\"DEU\">Los 1</cbc:Name>",
                      "<cbc:Name languageID=\"DEU\">Los 1</cbc:Name>" + lot_extra)
    return {"file": "x-01.xml", "notice_id": "x", "version": "01", "xml": xml}


def test_germany_reads_the_period_through_the_ted_mapper():
    opp = from_de_bkms(_bkms(
        '<cac:PlannedPeriod><cbc:StartDate>2027-01-01+01:00</cbc:StartDate><cbc:EndDate>2030-12-31+01:00</cbc:EndDate>'
        '<cbc:DurationMeasure unitCode="YEAR">4</cbc:DurationMeasure></cac:PlannedPeriod>'
        '<cac:ContractExtension><cbc:MaximumNumberNumeric>2</cbc:MaximumNumberNumeric>'
        '<cac:Renewal><cac:Period><cbc:Description languageID="DEU">je ein Jahr</cbc:Description></cac:Period>'
        '</cac:Renewal></cac:ContractExtension>'))
    assert (opp.contract_start, opp.contract_end, opp.contract_duration, opp.contract_duration_unit,
            opp.contract_renewal, opp.contract_renewals_max) == (
        date(2027, 1, 1), date(2030, 12, 31), 4, "YEAR", True, 2)


def test_a_german_notice_without_a_period_states_none():
    opp = from_de_bkms(_bkms(""))
    assert all(getattr(opp, c) is None for c in db.CONTRACT_PERIOD_COLUMNS)


def _boamp(lots) -> dict:
    body = {"EFORMS": {"ContractNotice": {"cac:ProcurementProjectLot": lots}}}
    return {"idweb": "26-1", "nomacheteur": "SID", "objet": "Travaux", "perimetre": "DIRECTIVE-81",
            "nature": "APPEL_OFFRE", "dateparution": "2026-10-13", "donnees": json.dumps(body)}


def test_france_reads_the_eforms_body():
    lot = {"cbc:ID": {"@schemeName": "Lot", "#text": "LOT-0001"},
           "cac:ProcurementProject": {
               "cac:PlannedPeriod": {"cbc:DurationMeasure": {"@unitCode": "MONTH", "#text": "48"}},
               "cac:ContractExtension": {"cbc:MaximumNumberNumeric": "3"}}}
    part = {"cbc:ID": {"@schemeName": "Part", "#text": "PAR-0001"},
            "cac:ProcurementProject": {"cac:PlannedPeriod": {"cbc:DurationMeasure": {"@unitCode": "YEAR", "#text": "9"}}}}
    opp = from_boamp(_boamp([lot, part]))
    assert (opp.contract_duration, opp.contract_duration_unit, opp.contract_renewals_max, opp.contract_renewal) == (
        48, "MONTH", 3, True)
    assert from_boamp(_boamp(lot)).contract_duration == 48          # one lot is a dict, not a list
    assert from_boamp(_boamp([])).contract_duration is None


def _placsp(project: str, lots: str = "") -> placsp.Opportunity:
    entry = ("<entry><id>x</id><title>t</title><updated>2026-10-11T19:54:50+02:00</updated>"
             "<cac-place-ext:ContractFolderStatus><cbc:ContractFolderID>F-1</cbc:ContractFolderID>"
             "<cbc-place-ext:ContractFolderStatusCode>PUB</cbc-place-ext:ContractFolderStatusCode>"
             f"<cac:ProcurementProject><cbc:Name>t</cbc:Name>{project}</cac:ProcurementProject>{lots}"
             "</cac-place-ext:ContractFolderStatus></entry>")
    opps, _ = placsp.parse_feed(_page(entry, None))
    return opps[0]


def test_spain_reads_planned_period_and_contract_extension():
    opp = _placsp('<cac:PlannedPeriod><cbc:DurationMeasure unitCode="MON">24</cbc:DurationMeasure></cac:PlannedPeriod>'
                  "<cac:ContractExtension><cbc:OptionsDescription>Prorroga de 12 meses</cbc:OptionsDescription>"
                  "</cac:ContractExtension>",
                  "<cac:ProcurementProjectLot><cbc:ID>1</cbc:ID><cac:ProcurementProject><cac:PlannedPeriod>"
                  "<cbc:StartDate>2027-02-01</cbc:StartDate><cbc:EndDate>2029-01-31</cbc:EndDate>"
                  "</cac:PlannedPeriod></cac:ProcurementProject></cac:ProcurementProjectLot>")
    assert (opp.contract_duration, opp.contract_duration_unit, opp.contract_start, opp.contract_end,
            opp.contract_renewal) == (24, "MONTH", date(2027, 2, 1), date(2029, 1, 31), True)


def test_spain_an_extension_that_says_none_is_no_renewal():
    opp = _placsp("<cac:ContractExtension><cbc:OptionsDescription>No</cbc:OptionsDescription></cac:ContractExtension>")
    assert opp.contract_renewal is None


# ------------------------------------------------------------------ the archive

def _opp(**kw) -> Opportunity:
    return Opportunity(source_code="es_placsp", native_id="F-1", buyer_name_raw="B", title_original="T", **kw)


def test_the_period_is_absent_from_the_payload_while_empty_so_no_hash_moves():
    payload = db.opportunity_payload(_opp())
    assert not set(db.CONTRACT_PERIOD_COLUMNS) & set(payload)
    assert set(db.CONTRACT_PERIOD_COLUMNS).isdisjoint(db.VERSIONED_FIELDS)
    assert set(db.CONTRACT_PERIOD_COLUMNS) <= db.KEPT_WHEN_ABSENT


def test_a_stored_period_reads_back_as_dates():
    opp = _opp(contract_start=date(2027, 1, 1), contract_end=date(2028, 1, 1), contract_duration=12,
               contract_duration_unit="MONTH")
    back = db.opportunity_from_payload(json.loads(json.dumps(db.opportunity_payload(opp))))
    assert (back.contract_start, back.contract_end, back.contract_duration) == (date(2027, 1, 1), date(2028, 1, 1), 12)


def test_a_ted_refetch_writes_the_period_without_a_version_and_never_erases_one():
    stored = db.opportunity_payload(Opportunity(source_code="ted", native_id="1-2026", buyer_name_raw="b",
                                                title_original="t", status="awarded", status_native="can-standard"))
    serving = {"is_defence": True, "status_native": "can-standard", **{c: None for c in db.CONTRACT_PERIOD_COLUMNS}}
    base = {"publication-number": "1-2026", "notice-title": {"eng": "t"}, "buyer-name": "b",
            "notice-type": "can-standard"}
    new = from_ted({**base, "contract-duration-end-date-lot": "2030-04-30"})
    change = plan_change(stored, serving, new, REMAPPED)
    assert change.changed == [] and change.direct == {"contract_end": date(2030, 4, 30)}
    held = {**serving, "contract_end": date(2030, 4, 30)}
    assert plan_change(stored, held, from_ted(base), REMAPPED).nothing


def test_the_backfill_moves_only_what_the_payload_states():
    held = {"contract_end": date(2030, 1, 1), "contract_duration": None}
    assert contract_periods.moves(held, {"contract_end": None, "contract_duration": 12}) == {"contract_duration": 12}
    assert contract_periods.moves(held, {"contract_end": date(2030, 1, 1)}) == {}


# ------------------------------------------------------------------ the data API

def test_a_key_reads_ted_and_tenderned_by_default(monkeypatch):
    monkeypatch.delenv("DGATE_API_KEY_SOURCES", raising=False)
    config.reset_cache()
    try:
        assert config.settings().api_key_sources == ("ted", "nl_tenderned")
    finally:
        config.reset_cache()
