"""PLACSP parser tests.

Covers the three defects found in the Phase 1 code review and fixed in plan
tasks M0-03 (status parsed but discarded), M0-04 (deadline timezone dropped)
and M0-05 (dataset 2, the regional buyers, never fetched).

The fixture is a realistic ATOM envelope with a CODICE payload, including one
malformed entry, because one bad entry must never kill a batch.
"""

from datetime import datetime, timedelta, timezone
from xml.etree import ElementTree as ET
from zoneinfo import ZoneInfo

from dgate.db import VERSIONED_FIELDS
from dgate.sources import placsp

ATOM = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"
      xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2"
      xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
      xmlns:cac-place-ext="urn:dgpe:names:draft:codice-place-ext:schema:xsd:CommonAggregateComponents-2"
      xmlns:cbc-place-ext="urn:dgpe:names:draft:codice-place-ext:schema:xsd:CommonBasicComponents-2">
  <link rel="next" href="https://example.test/page2.atom"/>
  <entry>
    <id>https://contrataciondelsectorpublico.gob.es/expediente/1001</id>
    <title>Expediente 1001</title>
    <updated>2026-08-14T09:00:00+02:00</updated>
    <link rel="alternate" href="https://contrataciondelsectorpublico.gob.es/expediente/1001"/>
    <cac-place-ext:ContractFolderStatus>
      <cbc:ContractFolderID>EXP-1001</cbc:ContractFolderID>
      <cbc-place-ext:ContractFolderStatusCode>PUB</cbc-place-ext:ContractFolderStatusCode>
      <cac:ProcurementProject>
        <cbc:Name>Suministro de equipos de comunicaciones tacticas</cbc:Name>
        <cbc:Description>Acuerdo marco. Se admite la subcontratacion parcial.</cbc:Description>
        <cac:BudgetAmount>
          <cbc:TotalAmount>4200000</cbc:TotalAmount>
        </cac:BudgetAmount>
        <cac:RequiredCommodityClassification>
          <cbc:ItemClassificationCode>35700000</cbc:ItemClassificationCode>
        </cac:RequiredCommodityClassification>
      </cac:ProcurementProject>
      <cac:TenderingProcess>
        <cac:TenderSubmissionDeadlinePeriod>
          <cbc:EndDate>2026-10-02</cbc:EndDate>
          <cbc:EndTime>12:00:00</cbc:EndTime>
        </cac:TenderSubmissionDeadlinePeriod>
      </cac:TenderingProcess>
      <cac-place-ext:LocatedContractingParty>
        <cac:Party>
          <cac:PartyName><cbc:Name>Ministerio de Defensa</cbc:Name></cac:PartyName>
        </cac:Party>
      </cac-place-ext:LocatedContractingParty>
    </cac-place-ext:ContractFolderStatus>
  </entry>
  <entry>
    <id>https://contrataciondelsectorpublico.gob.es/expediente/1002</id>
    <title>Expediente 1002</title>
    <updated>2026-08-15T09:00:00+02:00</updated>
    <cac-place-ext:ContractFolderStatus>
      <cbc:ContractFolderID>EXP-1002</cbc:ContractFolderID>
      <cbc-place-ext:ContractFolderStatusCode>ADJ</cbc-place-ext:ContractFolderStatusCode>
      <cac:ProcurementProject>
        <cbc:Name>Adjudicado</cbc:Name>
      </cac:ProcurementProject>
      <cac:TenderingProcess>
        <cac:TenderSubmissionDeadlinePeriod>
          <cbc:EndDate>2026-07-01</cbc:EndDate>
          <cbc:EndTime>13:30:00+05:00</cbc:EndTime>
        </cac:TenderSubmissionDeadlinePeriod>
      </cac:TenderingProcess>
    </cac-place-ext:ContractFolderStatus>
  </entry>
  <entry>
    <id>malformed</id>
    <title>No contract folder at all</title>
  </entry>
</feed>
"""


def _parse():
    return placsp.parse_feed(ATOM.encode("utf-8"))


# ------------------------------------------------------- M0-03: status

def test_status_is_mapped_and_native_code_kept():
    opps, _ = _parse()
    by_id = {o.native_id: o for o in opps}
    assert by_id["EXP-1001"].status == "open"
    assert by_id["EXP-1001"].status_native == "PUB"
    assert by_id["EXP-1002"].status == "awarded"
    assert by_id["EXP-1002"].status_native == "ADJ"


def test_unknown_status_code_is_not_disguised_as_open():
    """An unmapped code must be visible, not silently served as an open tender."""
    assert placsp.map_status("XYZ") == "unknown"
    assert placsp.map_status(None) == "open"
    assert placsp.map_status("anul") == "cancelled"


def test_status_is_versioned():
    """A status change must create a new archive version, not vanish."""
    assert "status" in VERSIONED_FIELDS


# ---------------------------------------------------- M0-04: timezones

def test_deadline_without_offset_uses_spanish_local_time():
    opps, _ = _parse()
    d = {o.native_id: o for o in opps}["EXP-1001"].deadline_at
    assert d.tzinfo is not None, "naive datetime would be read in the server timezone"
    assert d == datetime(2026, 10, 2, 12, 0, tzinfo=ZoneInfo("Europe/Madrid"))
    assert d.astimezone(timezone.utc).hour == 10


def test_stated_offset_wins_over_the_default():
    opps, _ = _parse()
    d = {o.native_id: o for o in opps}["EXP-1002"].deadline_at
    assert d.utcoffset() == timedelta(hours=5)


# ------------------------------------------------------ parser robustness

def test_malformed_entry_is_skipped_not_fatal():
    opps, next_url = _parse()
    assert len(opps) == 2
    assert next_url == "https://example.test/page2.atom"


def test_subcontracting_text_survives_for_classification():
    opps, _ = _parse()
    o = {x.native_id: x for x in opps}["EXP-1001"]
    assert "subcontratacion" in (o.description or "")


# ------------------------------------------------- M0-05: two datasets

def test_two_datasets_are_declared_with_distinct_sources():
    assert placsp.MAIN.source_code == "es_placsp"
    assert placsp.AGGREGATED.source_code == "es_placsp_agg"
    assert placsp.MAIN.live_feed != placsp.AGGREGATED.live_feed
    assert placsp.MAIN.base != placsp.AGGREGATED.base


def test_parsed_entries_carry_the_dataset_source_code():
    entry = ET.fromstring(ATOM).findall("{http://www.w3.org/2005/Atom}entry")[0]
    assert placsp.parse_entry(entry, "es_placsp_agg").source_code == "es_placsp_agg"


def test_archive_urls_differ_per_dataset():
    assert placsp.MAIN.annual_archive_url(2024).endswith(
        "licitacionesPerfilesContratanteCompleto3_2024.zip")
    assert placsp.AGGREGATED.annual_archive_url(2024).endswith(
        "PlataformasAgregadasSinMenores_2024.zip")
    assert "sindicacion_1044" in placsp.AGGREGATED.annual_archive_url(2024)


def test_backfill_years_are_oldest_first():
    urls = list(placsp.backfill_years(2012, 2014))
    assert len(urls) == 3
    assert "2012" in urls[0] and "2014" in urls[-1]


# ------------------------------- namespaces (verified against the live feed)

# PLACSP publishes CODICE under the Spanish `dgpe` namespaces. The parser was
# written against the OASIS UBL ones, which fails silently: the `place-ext`
# lookups still match, so every entry parses and carries a status while CPV,
# deadline, value and identifier all come back empty. Against the live feed on
# 7 September 2026 that was 405 of 405 entries with no CPV code at all.
ATOM_DGPE = ATOM.replace(
    'xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2"',
    'xmlns:cbc="urn:dgpe:names:draft:codice:schema:xsd:CommonBasicComponents-2"',
).replace(
    'xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"',
    'xmlns:cac="urn:dgpe:names:draft:codice:schema:xsd:CommonAggregateComponents-2"',
)


def test_dgpe_namespaces_parse_every_field():
    """The namespace set the live platform actually uses."""
    opps, _ = placsp.parse_feed(ATOM_DGPE.encode("utf-8"))
    by_id = {o.native_id: o for o in opps}
    assert "EXP-1001" in by_id, "the contract folder id must be read, not the atom id"
    o = by_id["EXP-1001"]
    assert o.cpv_codes == ["35700000"]
    assert o.value_amount == 4200000.0
    assert o.deadline_at is not None
    assert o.buyer_name_raw == "Ministerio de Defensa"
    assert o.status == "open"


def test_oasis_namespaces_still_parse():
    """Older archive packages use the UBL namespaces; both must work."""
    opps, _ = placsp.parse_feed(ATOM.encode("utf-8"))
    o = {x.native_id: x for x in opps}["EXP-1001"]
    assert o.cpv_codes == ["35700000"] and o.value_amount == 4200000.0


def test_identifier_never_falls_back_to_a_url_when_the_folder_id_is_present():
    """A URL as native_id is the visible symptom of a namespace mismatch."""
    for payload in (ATOM, ATOM_DGPE):
        opps, _ = placsp.parse_feed(payload.encode("utf-8"))
        assert all(not o.native_id.startswith("http") for o in opps)
