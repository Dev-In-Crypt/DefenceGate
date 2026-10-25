"""WP-71: backend fixes of the QA audit of 21 October 2026 (docs/verification/product/qa-full-backend.md).

Each test fails without the fix it names.
"""

from __future__ import annotations

import json
from datetime import date

import pytest

from dgate import awards, config, hardening
from dgate.normalise import EMAIL_PLACEHOLDER, strip_personal_data
from dgate.rawstore import FileRawStore, bundle_key

PERSON = awards.PERSON_PLACEHOLDER


# ------------------------------------------------------------------ H1: e-Zamowienia contractors

def _ezam(*contractors: dict) -> dict:
    return {"bzpNumber": "2026/BZP 00000001", "noticeType": "TenderResultNotice",
            "organizationName": "Gmina X", "contractors": list(contractors)}


def test_a_sole_trader_among_ezam_contractors_is_blanked_before_landing():
    clean = strip_personal_data(_ezam(
        {"contractorName": "Firma Handlowo-Usługowa Jan Kowalski", "contractorNationalId": "7010230780",
         "contractorCity": "Radom", "contractorProvince": "PL14", "contractorCountry": "PL"},
        {"contractorName": "Xentia sp. z o. o.", "contractorNationalId": "7010230781",
         "contractorCity": "Warszawa", "contractorProvince": "PL14", "contractorCountry": "PL"}))
    person, company = clean["contractors"]
    assert person == {"contractorName": PERSON, "contractorCountry": "PL"}
    assert company["contractorName"] == "Xentia sp. z o. o." and company["contractorNationalId"] == "7010230781"
    assert "Kowalski" not in json.dumps(clean, ensure_ascii=False) and "Radom" not in json.dumps(clean)


def test_a_pesel_marks_a_contractor_as_a_person_whatever_the_name():
    from dgate.normalise import contractor_is_person

    assert contractor_is_person({"contractorName": "KOWALSKI USŁUGI", "contractorNationalId": "44051401458"})
    assert contractor_is_person({"contractorName": "Anna Nowak", "contractorNationalId": "5252263747"})
    assert not contractor_is_person({"contractorName": "ZAKŁAD OBSŁUGI SYSTEMU MONITORINGU SP. Z O.O.",
                                     "contractorNationalId": "5252263747"})


def test_named_personal_fields_are_dropped_at_any_depth_for_every_source():
    rec = {"id": 1, "detail": {"KontaktLista": [{"Namn": "Anna"}], "rows": [{"userId": "u-1", "keep": 1}],
                               "contractor_name": "[Osoba fizyczna]"}}
    clean = strip_personal_data(rec)
    assert clean == {"id": 1, "detail": {"rows": [{"keep": 1}]}}


def test_eforms_person_elements_in_json_are_dropped_and_a_natural_person_keeps_only_its_number():
    body = {"EFORMS": {"ContractAwardNotice": {
        "efac:Organization": [
            {"efbc:NaturalPersonIndicator": "true",
             "efac:Company": {"cac:PartyName": {"cbc:Name": "Jean Dupont"},
                              "cac:PartyIdentification": {"cbc:ID": "123"},
                              "cac:PostalAddress": {"cbc:CityName": "Lyon"}}},
            {"efbc:NaturalPersonIndicator": "false",
             "efac:Company": {"cac:PartyName": {"cbc:Name": "Thales SA"}}}],
        "efac:UltimateBeneficialOwner": {"cbc:FamilyName": "Dupont"},
        "cac:Party": {"cbc:Telefax": "+33 1 00 00 00 00", "cbc:FirstName": "Jean"}}}}
    rec = {"idweb": "26-1", "donnees": json.dumps(body)}
    out = json.loads(strip_personal_data(rec)["donnees"])["EFORMS"]["ContractAwardNotice"]
    natural, company = out["efac:Organization"]
    assert natural["efac:Company"] == {"cac:PartyIdentification": {"cbc:ID": "123"}}
    assert company["efac:Company"]["cac:PartyName"]["cbc:Name"] == "Thales SA"
    assert "efac:UltimateBeneficialOwner" not in out and out["cac:Party"] == {}


def test_a_bare_telefax_and_a_nested_contact_are_dropped_outside_boamp():
    clean = strip_personal_data({"publicatieId": 1, "opdrachtgever": {"Telefax": "0201234567",
                                                                     "Contact": {"x": 1}, "naam": "Gemeente"}})
    assert clean["opdrachtgever"] == {"naam": "Gemeente"}


def test_stripping_twice_changes_nothing_more():
    rec = _ezam({"contractorName": "Jan Kowalski", "contractorNationalId": "1", "contractorCity": "Radom"})
    once = strip_personal_data(rec)
    assert strip_personal_data(once) == once


# ------------------------------------------------------------------ M6: TED award redaction

def test_a_person_named_only_as_winner_is_blanked_too():
    rec = {"winner-name": ["Radek Nečas"], "organisation-name-tenderer": ["Thales SA"],
           "organisation-country-tenderer": ["CZE"], "winner-identifier": ["850101/1234"]}
    red = awards.read_award(rec).redacted
    assert red["winner-name"] == [PERSON]
    assert "winner-identifier" not in red


def test_another_languages_spelling_of_a_person_is_blanked():
    rec = {"winner-name": {"eng": ["Thales SA"]},
           "organisation-name-tenderer": {"ces": ["Thales SA", "Radek Nečas"], "eng": ["Thales SA", "Radek Necas"]},
           "organisation-identifier-tenderer": {"ces": ["FR1", "850101"]}}
    red = awards.read_award(rec).redacted
    flat = json.dumps(red, ensure_ascii=False)
    assert "Nečas" not in flat and "Necas" not in flat and "Thales SA" in flat
    assert red["organisation-identifier-tenderer"] == {}


# ------------------------------------------------------------------ M9: IPv6 buckets and pruning

def test_the_bucket_table_is_pruned_at_most_every_few_seconds_and_stays_bounded(monkeypatch):
    monkeypatch.setattr(hardening, "MAX_BUCKETS", 100)
    t = [0.0]
    b = hardening.TokenBuckets(capacity=10, refill=0.001, clock=lambda: t[0])
    for i in range(150):
        b.take(f"k{i}", 1)
    assert len(b._buckets) <= 100            # pruned once, least recently seen evicted
    size = len(b._buckets)
    for i in range(150, 160):
        b.take(f"k{i}", 1)                   # same instant: no rebuild on every call
    assert len(b._buckets) == size + 10
    t[0] = 10.0
    b.take("late", 1)
    assert len(b._buckets) <= 100
    assert "late" in b._buckets


# ------------------------------------------------------------------ M10: the internal secret

def test_a_production_api_without_its_internal_secret_refuses_to_start(monkeypatch):
    monkeypatch.setenv("DGATE_ENV", "production")
    monkeypatch.setenv("DGATE_INTERNAL_SECRET", "")
    config.reset_cache()
    with pytest.raises(config.ConfigError, match="DGATE_INTERNAL_SECRET"):
        config.require_production_secrets()
    monkeypatch.setenv("DGATE_INTERNAL_SECRET", "s3")
    config.reset_cache()
    config.require_production_secrets()
    monkeypatch.delenv("DGATE_ENV")
    monkeypatch.setenv("DGATE_INTERNAL_SECRET", "")
    config.reset_cache()
    config.require_production_secrets()      # development and tests need none
    config.reset_cache()


def test_compose_trusts_forwarded_headers_from_caddy_only_and_requires_the_secret():
    from pathlib import Path

    root = Path(__file__).resolve().parents[3] / "infra"
    compose = (root / "docker-compose.yml").read_text(encoding="utf-8")
    assert '"--forwarded-allow-ips", "*"' not in compose
    assert '"--forwarded-allow-ips", "10.250.71.2"' in compose and "ipv4_address: 10.250.71.2" in compose
    assert "DGATE_INTERNAL_SECRET:-}" not in compose
    assert "reverse_proxy api-edge:8000" in (root / "caddy" / "Caddyfile").read_text(encoding="utf-8")
    env = (root / ".env.example").read_text(encoding="utf-8")
    assert "\nDGATE_INTERNAL_SECRET=\n" in env          # documented, no value


# ------------------------------------------------------------------ M15: date bounds in UTC

def test_a_date_filter_covers_the_whole_day_in_utc():
    from datetime import datetime, timezone

    from dgate.api import day_end, day_start

    d = date(2026, 10, 21)
    assert day_start(d) == datetime(2026, 10, 21, tzinfo=timezone.utc)
    assert day_end(d) > datetime(2026, 10, 21, 23, 59, 59, tzinfo=timezone.utc)
    assert day_end(d).utcoffset().total_seconds() == 0


# ------------------------------------------------------------------ M7: PLACSP quarantined entries

def test_a_placsp_entry_that_fails_to_parse_is_counted(monkeypatch):
    from dgate.sources import placsp

    feed = (b'<feed xmlns="http://www.w3.org/2005/Atom"><entry><id>a</id></entry>'
            b'<entry><id>b</id></entry></feed>')

    def boom(entry, source_code):
        raise ValueError("bad entry")

    monkeypatch.setattr(placsp, "parse_entry", boom)
    counts: dict = {}
    opps, _ = placsp.parse_feed(feed, counts=counts)
    assert opps == [] and counts == {"entries_failed": 2}


# ------------------------------------------------------------------ the re-strip tool

def test_restrip_raw_rewrites_a_bundle_in_place_only_with_yes(tmp_path):
    from dgate.ops import restrip

    store = FileRawStore(tmp_path)
    key = bundle_key("pl_ezam", date(2026, 10, 1))
    person = _ezam({"contractorName": "Jan Kowalski", "contractorNationalId": "7010230780",
                    "contractorCity": "Radom"})
    company = _ezam({"contractorName": "Xentia sp. z o. o.", "contractorNationalId": "7010230781"})
    store.put_records(key, [company, person])
    store.put_records(bundle_key("pl_ezam", date(2026, 10, 21)), [person])     # today's: left alone
    today = date(2026, 10, 21)

    report = restrip.restrip_raw(store, "pl_ezam", write=False, today=today)
    assert report["records_with_personal_data"] == 1 and report["bundles_to_rewrite"] == 1
    assert report["bundles_skipped_recent"] == 1 and "bundles_rewritten" not in report
    assert "Kowalski" in json.dumps(FileRawStore(tmp_path).get(key + "#1"))

    restrip.restrip_raw(store, "pl_ezam", write=True, today=today)
    fresh = FileRawStore(tmp_path)
    assert fresh.get(key + "#0") == strip_personal_data(company)            # line positions kept
    assert fresh.get(key + "#1")["contractors"][0]["contractorName"] == PERSON
    again = restrip.restrip_raw(fresh, "pl_ezam", write=False, today=today)
    assert again["records_with_personal_data"] == 0                         # idempotent
    with pytest.raises(SystemExit):
        restrip.restrip_raw(store, "de_bkms", write=False)


def test_the_break_glass_sql_is_guarded_per_row_and_carries_no_address():
    from dgate.ops import restrip

    clean = strip_personal_data({"description": "write to a.b@mil.dk", "title_original": "O'Brien"})
    sql = restrip.break_glass_sql([(7, "abc", clean)])
    assert "a.b@mil.dk" not in sql and EMAIL_PLACEHOLDER in sql
    assert "WHERE id = 7 AND md5(payload::text) = 'abc';" in sql
    assert "O''Brien" in sql
    assert sql.index("DISABLE TRIGGER opportunity_version_append_only") < sql.index("UPDATE opportunity_version SET")
    assert sql.index("ENABLE TRIGGER") > sql.index("UPDATE opportunity_version SET") and sql.rstrip().endswith("-- 'O'")
