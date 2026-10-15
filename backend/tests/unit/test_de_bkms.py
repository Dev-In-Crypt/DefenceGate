"""The German notice service (BKMS): connector, personal-data boundary, mapper.

Fixtures are hand-built after real files of 13 October 2026 (structure only; the names,
telephone numbers and addresses in them are invented and use the reserved `.invalid` TLD).
"""

from __future__ import annotations

import io
import json
import zipfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest

from dgate.classify import classify
from dgate.normalise import MAX_STRING, from_de_bkms, strip_eforms_xml, strip_personal_data
from dgate.sources import RateLimited, de_bkms

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "de_bkms"


def _xml(name: str) -> str:
    return (FIX / name).read_text(encoding="utf-8")


def _record(name: str, file: str | None = None, notice: str | None = None,
            version: str = "01") -> dict:
    return {"file": file or name, "notice_id": notice, "version": version, "xml": _xml(name)}


# ------------------------------------------------------------ personal data

def test_strip_removes_contacts_persons_and_addresses_in_prose():
    clean = strip_personal_data(_record("cn_standard_defence.xml"))["xml"]
    for gone in ("Erika Mustermann", "+49 261 000000", "erika.mustermann@example.invalid",
                 "beschaffung@example.invalid", "Contact>"):
        assert gone not in clean, gone
    assert "[email removed]" in clean            # the address typed into the description
    # What the product is for survives.
    assert "Bundeswehr" in clean and "80000000" in clean and "992-80002-47" in clean


def test_strip_removes_beneficial_owner_jury_and_natural_person_names():
    clean = strip_eforms_xml(_xml("can_standard_award.xml"))
    for gone in ("Eigentuemer", "Olga", "Juror", "Max Beispiel", "max@example.invalid",
                 "Hans Beispielmann", "Musterweg"):
        assert gone not in clean, gone
    assert "ORG-0002" in clean                   # the identifier stays: it names nobody
    assert "Bundeswehr-Dienstleistungszentrum Hamburg" in clean


def test_a_notice_longer_than_the_string_bound_is_not_cut():
    padded = _xml("cn_standard_defence.xml").replace(
        "Rahmenvereinbarung.", "Rahmenvereinbarung. " + "x" * (MAX_STRING + 5000))
    clean = strip_personal_data({"file": "a.xml", "notice_id": "a", "version": "01", "xml": padded})
    assert len(clean["xml"]) > MAX_STRING
    assert from_de_bkms(clean).native_id == "129f4d26-440e-4017-91b5-df3a10cf3f30"


@pytest.mark.parametrize("bad", [
    '<!DOCTYPE x [<!ENTITY a "b">]><ContractNotice/>', "<ContractNotice>", None, 12])
def test_a_file_that_cannot_be_scrubbed_is_not_kept(bad):
    assert strip_eforms_xml(bad) is None
    clean = strip_personal_data({"file": "a.xml", "notice_id": "a", "version": "01", "xml": bad})
    assert clean["xml"] is None
    with pytest.raises(ValueError):
        from_de_bkms(clean)


def test_the_stripped_record_hashes_the_same_when_read_twice():
    from dgate.sources.ted import content_hash

    a = strip_personal_data(_record("cn_standard_defence.xml"))
    b = strip_personal_data(_record("cn_standard_defence.xml"))
    assert content_hash(a) == content_hash(b)


# ----------------------------------------------------------------- mapping

def test_a_defence_call_maps_through_the_ted_mapper():
    opp = from_de_bkms(strip_personal_data(_record("cn_standard_defence.xml")))
    assert opp.source_code == "de_bkms"
    assert opp.native_id == "129f4d26-440e-4017-91b5-df3a10cf3f30"   # no version suffix
    assert opp.notice_version == 1
    assert opp.buyer_name_raw.startswith("Bundesamt fuer Ausruestung")
    assert opp.buyer_identifier == "992-80002-47"
    assert opp.country == "DE" and opp.original_language == "DE"
    assert opp.title_original == "Schulung Fuehrungsunterstuetzung"
    assert opp.legal_basis == "32009L0081"
    assert opp.procedure_type == "restricted"
    assert opp.notice_subtype == "18"
    assert opp.procedure_identifier == "d8e98b07-ad6e-4f35-92c6-0760efbc6039"   # lower case
    assert opp.cpv_codes == ["80000000", "80500000"]
    assert opp.status == "open" and opp.status_native == "cn-standard"
    assert opp.published_at == date(2026, 10, 13)
    # 12:00 at +01:00 as the lot states it, not the server's zone.
    assert opp.deadline_at == datetime(2026, 10, 26, 12, 0, tzinfo=timezone(timedelta(hours=1)))
    assert opp.security_clearance_required is True
    assert opp.value_amount == 250000.0 and opp.value_currency == "EUR"
    assert opp.source_url is None and opp.ted_ref is None
    assert opp.lot_count == 1


def test_an_award_states_its_ted_number_and_its_winner_status():
    opp = from_de_bkms(strip_personal_data(_record("can_standard_award.xml")))
    assert opp.status == "awarded"
    assert opp.notice_version == 2
    assert opp.ted_ref == "710974-2026"           # the leading zeros are TED's padding
    assert opp.value_amount == 1200000.0 and opp.value_kind == "total"
    assert opp.published_at == date(2026, 10, 14)  # the publication date, not the issue date
    assert opp.buyer_name_raw == "Bundeswehr-Dienstleistungszentrum Hamburg"


def test_a_legacy_national_form_maps_without_an_organisation_block():
    opp = from_de_bkms(strip_personal_data(_record("legacy_national.xml")))
    assert opp.native_id == "25920552"
    assert opp.buyer_name_raw == "Stadtwerke Beispielstadt - Einkauf -"
    assert opp.procedure_identifier is None       # empty ContractFolderID
    assert opp.legal_basis == "de-vol" and opp.country == "DE"


def test_two_versions_of_one_notice_share_the_identity():
    first = from_de_bkms(strip_personal_data(_record("cn_standard_defence.xml")))
    amended = _xml("cn_standard_defence.xml").replace("<cbc:VersionID>01<", "<cbc:VersionID>02<")
    second = from_de_bkms(strip_personal_data(
        {"file": "x-02.xml", "notice_id": "x", "version": "02", "xml": amended}))
    assert first.native_id == second.native_id
    assert (first.notice_version, second.notice_version) == (1, 2)


def test_a_file_without_a_document_is_a_value_error_not_a_crash():
    with pytest.raises(ValueError):
        from_de_bkms({"file": "a.xml", "notice_id": "a", "unreadable": "too large"})


# ----------------------------------------------------------- classification

def test_the_directive_alone_qualifies_and_municipal_fire_equipment_does_not():
    defence = from_de_bkms(strip_personal_data(_record("cn_standard_defence.xml")))
    sig = classify(legal_basis=defence.legal_basis, cpv_codes=defence.cpv_codes,
                   buyer_is_defence=False)
    assert sig.is_defence and sig.legal_basis

    fire = classify(legal_basis="de-vob", cpv_codes=["35110000"], buyer_is_defence=False)
    assert not fire.is_defence


def test_german_defence_buyers_in_the_sample_are_recognised_by_name():
    from dgate.buyer_vocab import effective_buyer_class

    for name in ("Bundesamt fuer Ausruestung, Informationstechnik und Nutzung der Bundeswehr",
                 "BAAINBw L2.1", "BAIUDBw", "Bundeswehr-Dienstleistungszentrum Hamburg",
                 "Bw Bekleidungsmanagement GmbH", "BWI GmbH"):
        assert effective_buyer_class(name, "DE", False) in {
            "defence", "procurement_agency", "defence_agency", "military_unit",
            "defence_enterprise", "defence_support", "armed_forces"}, name


# --------------------------------------------------------------- connector

def _zip(files: dict[str, bytes | str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in files.items():
            z.writestr(name, data)
    return buf.getvalue()


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_split_name_handles_uuid_numeric_and_unpadded_versions():
    u = "6a06759e-fe07-4383-800c-b6236d96f2a0"
    assert de_bkms.split_name(f"{u}-02.xml") == (u, "02")
    assert de_bkms.split_name("25920552-1.xml") == ("25920552", "1")
    assert de_bkms.split_name("sub/15a70ad6-82b3-4037-a500-b5f382474774-1.xml")[1] == "1"
    assert de_bkms.split_name("readme.txt") is None


def test_a_day_is_read_in_name_order_and_every_entry_is_counted():
    u = "6a06759e-fe07-4383-800c-b6236d96f2a0"
    body = _zip({
        f"{u}-02.xml": "<a/>", f"{u}-01.xml": "<a/>", "25920552-1.xml": "<a/>",
        "evil-1.xml": '<!DOCTYPE a [<!ENTITY x "y">]><a/>', "notes.txt": "not a notice"})
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(dict(request.url.params))
        return httpx.Response(200, content=body)

    with de_bkms.open_day(date(2026, 10, 13), client=_client(handler)) as day:
        records = list(day.records())
    assert seen == [{"pubDay": "2026-10-13", "format": "eforms.zip"}]
    assert day.entries == 4 and len(records) == 4          # the .txt is not an entry
    assert [r["file"] for r in records] == [
        "25920552-1.xml", f"{u}-01.xml", f"{u}-02.xml", "evil-1.xml"]
    assert [r["version"] for r in records[1:3]] == ["01", "02"]
    refused = records[-1]
    assert "xml" not in refused and "document type" in refused["unreadable"]


def test_a_day_without_a_file_is_none_and_a_rate_refusal_is_rate_limited(monkeypatch):
    monkeypatch.setattr(de_bkms.time, "sleep", lambda s: None)
    assert de_bkms.open_day(
        date(2026, 10, 15), client=_client(lambda r: httpx.Response(404))) is None
    with pytest.raises(RateLimited):
        de_bkms.open_day(date(2026, 10, 13),
                         client=_client(lambda r: httpx.Response(429, headers={"retry-after": "7"})))


def test_a_body_that_is_not_a_zip_or_too_large_is_refused(monkeypatch):
    with pytest.raises(ValueError, match="not a zip"):
        de_bkms.open_day(date(2026, 10, 13),
                         client=_client(lambda r: httpx.Response(200, content=b"<html>")))
    monkeypatch.setattr(de_bkms, "MAX_ZIP_BYTES", 100)
    big = _zip({"a-1.xml": "x" * 5000})
    with pytest.raises(RuntimeError, match="passed"):
        de_bkms.open_day(date(2026, 10, 13),
                         client=_client(lambda r: httpx.Response(200, content=big)))


def test_an_entry_over_the_ceiling_is_a_record_not_read_into_memory(monkeypatch):
    monkeypatch.setattr(de_bkms, "MAX_ENTRY_BYTES", 50)
    body = _zip({"a-1.xml": "<a>" + "x" * 500 + "</a>", "b-1.xml": "<b/>"})
    with de_bkms.open_day(date(2026, 10, 13),
                          client=_client(lambda r: httpx.Response(200, content=body))) as day:
        records = list(day.records())
    assert "too large" in records[0]["unreadable"] and records[1]["xml"] == "<b/>"


def test_window_is_oldest_first_and_includes_today():
    assert de_bkms.window_days(2, date(2026, 10, 15)) == [
        date(2026, 10, 13), date(2026, 10, 14), date(2026, 10, 15)]


def test_a_record_is_json_serialisable_after_stripping():
    json.dumps(strip_personal_data(_record("can_standard_award.xml")))
