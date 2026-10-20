"""PLACSP award winners (WP-60): reading the results, blanking persons before landing, the Spanish
person rules, and the archive units. No database, no network.

Every name and number below is made up. The shapes are the live feed's of 20 October 2026: a winner
with a CIF and an address, a natural person whose NIF the publisher masked, a DNI in clear, a UTE,
a foreign winner with scheme OTROS, and a deserted lot.
"""

from __future__ import annotations

import io
import json
import zipfile
from datetime import date

import httpx
import pytest

from dgate import awards, db, placsp_awards
from dgate.ops import placsp_archives
from dgate.sources import placsp, ted

NS = ('xmlns="http://www.w3.org/2005/Atom" '
      'xmlns:cbc="urn:dgpe:names:draft:codice:schema:xsd:CommonBasicComponents-2" '
      'xmlns:cac="urn:dgpe:names:draft:codice:schema:xsd:CommonAggregateComponents-2" '
      'xmlns:cac-place-ext="urn:dgpe:names:draft:codice-place-ext:schema:xsd:CommonAggregateComponents-2" '
      'xmlns:cbc-place-ext="urn:dgpe:names:draft:codice-place-ext:schema:xsd:CommonBasicComponents-2"')


def party(name: str, ident: str, scheme: str = "NIF", country: str | None = "ES") -> str:
    where = (f"<cac:PhysicalLocation><cac:Address><cbc:CityName>Ciudad Inventada</cbc:CityName>"
             f"<cbc:PostalZone>99999</cbc:PostalZone><cac:AddressLine><cbc:Line>Calle Falsa 123</cbc:Line>"
             f"</cac:AddressLine><cac:Country><cbc:IdentificationCode>{country}</cbc:IdentificationCode>"
             f"</cac:Country></cac:Address></cac:PhysicalLocation>") if country else ""
    return (f"<cac:WinningParty><cac:PartyIdentification><cbc:ID schemeName=\"{scheme}\">{ident}</cbc:ID>"
            f"</cac:PartyIdentification><cac:PartyName><cbc:Name>{name}</cbc:Name></cac:PartyName>{where}"
            f"</cac:WinningParty>")


def result(code: str, lot: str, parties: str = "", value: str = "1000.00") -> str:
    return (f"<cac:TenderResult><cbc:ResultCode>{code}</cbc:ResultCode>"
            f"<cbc:Description>Texto libre que puede nombrar a una persona</cbc:Description>"
            f"<cbc:AwardDate>2026-09-15</cbc:AwardDate><cbc:ReceivedTenderQuantity>4</cbc:ReceivedTenderQuantity>"
            f"<cbc:SMEAwardedIndicator>true</cbc:SMEAwardedIndicator>{parties}"
            f"<cac:AwardedTenderedProject><cbc:ProcurementProjectLotID>{lot}</cbc:ProcurementProjectLotID>"
            f"<cac:LegalMonetaryTotal><cbc:TaxExclusiveAmount currencyID=\"EUR\">{value}</cbc:TaxExclusiveAmount>"
            f"<cbc:PayableAmount currencyID=\"EUR\">1210.00</cbc:PayableAmount></cac:LegalMonetaryTotal>"
            f"</cac:AwardedTenderedProject></cac:TenderResult>")


RESULTS = "".join([
    result("8", "1", party("TALLERES INVENTADOS DEL NORTE, S.L.", "B99999990")),
    result("8", "2", party("PEREZ GOMEZ ANTONIO", "***9999**")),
    result("8", "3", party("RUIZ MARTIN, LUCIA", "99999999R")),
    result("9", "4", party("UTE INVENTADA SISTEMAS SA - LOPEZ GARCIA JUAN", "U99999990")),
    result("8", "5", party("Nordic Example AB", "SE556000000001", "OTROS", "SE")),
    result("8", "6", party("TALLERES INVENTADOS DEL NORTE, S.L.", "B99999990")),
    result("3", "7"),
])


def entry(results: str = RESULTS, status: str = "RES", updated: str = "2026-09-20T10:00:00+02:00",
          folder: str = "2026/TEST/0001") -> str:
    return f"""<entry><id>https://example.test/{folder}</id><title>Suministro</title><updated>{updated}</updated>
  <cac-place-ext:ContractFolderStatus>
    <cbc:ContractFolderID>{folder}</cbc:ContractFolderID>
    <cbc-place-ext:ContractFolderStatusCode>{status}</cbc-place-ext:ContractFolderStatusCode>
    <cac:ProcurementProject><cbc:Name>Suministro de repuestos</cbc:Name>
      <cac:RequiredCommodityClassification><cbc:ItemClassificationCode>35400000</cbc:ItemClassificationCode>
      </cac:RequiredCommodityClassification></cac:ProcurementProject>
    {results}
    <cac-place-ext:LocatedContractingParty><cac:Party><cac:PartyName><cbc:Name>Ministerio de Defensa</cbc:Name>
    </cac:PartyName></cac:Party></cac-place-ext:LocatedContractingParty>
  </cac-place-ext:ContractFolderStatus></entry>"""


def feed(*entries: str) -> bytes:
    return f'<?xml version="1.0" encoding="UTF-8"?><feed {NS}>{"".join(entries)}</feed>'.encode()


def payload() -> dict:
    found: list = []
    placsp.parse_feed(feed(entry()), results=found)
    return found[0]


# ------------------------------------------------------------------ the connector

def test_the_results_are_read_per_lot_with_winner_value_date_and_tenders():
    p = payload()
    assert p["folder_id"] == "2026/TEST/0001" and p["status_native"] == "RES"
    assert [r["lot_id"] for r in p["results"]] == ["1", "2", "3", "4", "5", "6", "7"]
    first = p["results"][0]
    assert first["result_code"] == "8" and first["award_date"] == "2026-09-15"
    assert first["received_tenders"] == 4 and first["value"] == 1000.0 and first["currency"] == "EUR"
    assert first["value_with_vat"] == 1210.0
    assert first["winners"] == [{"name": "TALLERES INVENTADOS DEL NORTE, S.L.", "identifier": "B99999990",
                                 "scheme": "NIF", "country": "ES"}]
    assert p["results"][6]["winners"] == []                      # deserted lot
    # what is not read at all: the free text, the street, the city, the postcode
    blob = json.dumps(p, ensure_ascii=False)
    assert "Texto libre" not in blob and "Calle Falsa" not in blob and "99999" not in blob.replace("B99999990", "") \
        .replace("U99999990", "").replace("99999999R", "").replace("***9999**", "")


def test_collecting_the_results_does_not_move_the_notice_payload_or_its_hash():
    """Awards travel next to the record, never inside it: the hash of every held record stays put."""
    plain, _ = placsp.parse_feed(feed(entry()))
    found: list = []
    with_awards, _ = placsp.parse_feed(feed(entry()), results=found)
    a, b = db.opportunity_payload(plain[0]), db.opportunity_payload(with_awards[0])
    assert a == b and ted.content_hash(a) == ted.content_hash(b)
    assert not {"results", "winners", "award_date", "winner"} & set(a)
    assert "TALLERES" not in json.dumps(a)


def test_an_entry_without_results_has_no_award_payload():
    found: list = []
    placsp.parse_feed(feed(entry(results="", status="PUB")), results=found)
    assert found == [None]


# ------------------------------------------------------------------ blanking persons before landing

def test_persons_are_blanked_before_landing_and_counted_once():
    landed = placsp_awards.redact(payload())
    blob = json.dumps(landed, ensure_ascii=False)
    for secret in ("PEREZ", "GOMEZ ANTONIO", "***9999**", "RUIZ", "LUCIA", "99999999R", "LOPEZ GARCIA JUAN",
                   "Calle Falsa", "Ciudad Inventada"):
        assert secret not in blob, secret
    winners = [w for r in landed["results"] for w in r["winners"]]
    assert winners[1] == {"natural_person": True} and winners[2] == {"natural_person": True}
    assert landed["natural_persons"] == 2
    ute = winners[3]
    assert ute["joint_venture"] and ute["name"] == "UTE INVENTADA SISTEMAS SA - [natural person]"
    assert ute["identifier"] == "U99999990"
    assert winners[4]["country"] == "SE" and winners[4]["identifier"] == "SE556000000001"


def test_the_winners_of_a_folder_are_its_companies_and_ute_once_each():
    got = placsp_awards.read(placsp_awards.redact(payload()))
    assert [(w.name, w.country, w.identifier) for w in got.winners] == [
        ("TALLERES INVENTADOS DEL NORTE, S.L.", "ES", "B99999990"),
        ("UTE INVENTADA SISTEMAS SA - [natural person]", "ES", "U99999990"),
        ("Nordic Example AB", "SE", "SE556000000001"),
    ]
    assert got.counts["skipped_person"] == 2 and got.winners_seen == 5
    assert got.counts["joint_ventures"] == 1


def test_a_folder_whose_every_lot_was_deserted_names_no_winner():
    got = placsp_awards.read(placsp_awards.redact(
        {"results": [{"result_code": "3", "winners": []}, {"result_code": "4", "winners": []}]}))
    assert got.winners == [] and got.winners_seen == 0 and got.counts["no_winner_result"] == 1


def test_a_landed_payload_is_not_redacted_twice():
    """Read back from the store, the count of persons stands; redacting again would lose it."""
    landed = placsp_awards.redact(payload())
    assert placsp_awards.read(landed).counts["skipped_person"] == 2
    assert ted.content_hash(json.loads(json.dumps(landed))) == ted.content_hash(landed)


# ------------------------------------------------------------------ the Spanish person rules

ES_PERSONS = [
    ("GARCIA LOPEZ JUAN", None), ("JOSE LUIS FERNANDEZ RUIZ", None), ("FERNANDEZ RUIZ JOSE LUIS", None),
    ("MARTINEZ SANCHEZ, ANTONIO", None), ("MARIA DEL CARMEN DE LA FUENTE", None), ("RECAMBIOS GOMEZ", None),
    ("ANY NAME AT ALL S.L.", "12345678Z"), ("ANY NAME", "X1234567L"), ("ANY NAME", "***1234**"),
    ("Juan García López", None),
]
ES_COMPANIES = [
    ("TALLERES HERMANOS PEREZ S.L.", None), ("INDRA SISTEMAS, S.A.", None), ("GARCIA LOPEZ JUAN", "B12345678"),
    ("NAVANTIA", None), ("UTE INDRA - ISDEFE", "U12345678"), ("UNION TEMPORAL DE EMPRESAS ALFA Y BETA", None),
    ("Indra Sistemas, S.A.", "ESA28599033"),
]


@pytest.mark.parametrize("name,ident", ES_PERSONS)
def test_a_spanish_natural_person_is_not_a_supplier(name, ident):
    assert awards.person_reason(name, ident, "ES") is not None


@pytest.mark.parametrize("name,ident", ES_COMPANIES)
def test_a_spanish_legal_entity_is_a_supplier(name, ident):
    assert awards.person_reason(name, ident, "ES") is None


def test_the_tax_number_rules_are_spanish_except_the_publishers_mask():
    assert awards.es_tax_kind("12345678Z", "DE") is None          # not read as a DNI outside Spain
    assert awards.es_tax_kind("***1234**", "PT") == "person"
    assert awards.es_tax_kind("B-12345678", "ES") == "entity"
    assert awards.es_tax_kind("ES B12345678", None) == "entity"


def test_a_utes_member_that_is_a_person_is_blanked_and_its_companies_kept():
    assert awards.joint_venture_name("UTE INDRA - ISDEFE") == "UTE INDRA - ISDEFE"
    assert awards.joint_venture_name("UTE ALFA SL - GARCIA LOPEZ JUAN") == "UTE ALFA SL - [natural person]"
    assert awards.joint_venture_name("UNION TEMPORAL DE EMPRESAS ALFA SA Y RUIZ MARTIN LUCIA") == \
        "UNION TEMPORAL DE EMPRESAS ALFA SA - [natural person]"
    assert awards.clean_supplier_name("UTE INDRA - ISDEFE")[0] is None      # not a "consortium string"


# ------------------------------------------------------------------ the archive walk

def _zip(*members: bytes) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for i, m in enumerate(members):
            zf.writestr(f"part{i}.atom", m)
    return buf.getvalue()


def _client(body: bytes) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, content=body)))


def test_the_archive_walk_hands_each_record_on_with_its_award_payload():
    body = _zip(feed(entry(), entry(results="", status="PUB", folder="2026/TEST/0002",
                                    updated="2026-09-01T10:00:00+02:00")))
    items = list(placsp.fetch_archive("https://example.test/a.zip", client=_client(body), with_results=True))
    assert [(o.native_id, a is not None) for o, a in items] == [("2026/TEST/0002", False), ("2026/TEST/0001", True)]
    plain = list(placsp.fetch_archive("https://example.test/a.zip", client=_client(body)))
    assert [o.native_id for o in plain] == ["2026/TEST/0002", "2026/TEST/0001"]


def test_the_archive_walk_stops_before_the_disk_falls_under_its_floor():
    body = _zip(feed(entry()))
    with pytest.raises(placsp.DiskLow):
        list(placsp.fetch_archive("https://example.test/a.zip", client=_client(body), with_results=True,
                                  min_free_bytes=10**18))


def test_the_units_are_the_annual_files_of_past_years_and_the_months_of_this_one():
    got = placsp_archives.units((2023, 1), (2026, 10), placsp.MAIN, date(2026, 10, 20))
    assert [u.name for u in got] == ["es_placsp-2023", "es_placsp-2024", "es_placsp-2025"] + [
        f"es_placsp-2026{m:02d}" for m in range(1, 11)]
    assert got[2].url.endswith("licitacionesPerfilesContratanteCompleto3_2025.zip")
    assert got[-1].url.endswith("_202610.zip") and got[-1].since.month == 10


def test_the_plan_states_sizes_and_whether_the_disk_suffices(monkeypatch):
    monkeypatch.setattr(placsp_archives, "free_bytes", lambda: 7 * 2**30)
    todo = placsp_archives.units((2026, 9), (2026, 9), placsp.MAIN, date(2026, 10, 20))
    todo[0].size = 400 * 2**20
    text = placsp_archives.plan(todo, set(), 3 * 2**30)
    assert "es_placsp-202609" in text and "0.39 GiB" in text and "enough" in text
    monkeypatch.setattr(placsp_archives, "free_bytes", lambda: 3 * 2**30)
    assert "NOT enough" in placsp_archives.plan(todo, set(), 3 * 2**30)
