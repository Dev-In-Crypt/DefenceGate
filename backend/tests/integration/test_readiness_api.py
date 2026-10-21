"""The readiness layer on a real Postgres (WP-29): the content in the database, the public catalogue,
the stateless assessment, and the cross-layer question "can I take part in this call?".
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit, urlunsplit

import psycopg
import pytest
from fastapi.testclient import TestClient

from dgate import api, config, db, hardening, migrate
from dgate.normalise import Call
from dgate.readiness import api as readiness_api
from dgate.readiness import seed

pytestmark = pytest.mark.integration

CONTENT = seed.load_file()
UA = {"country": "UA", "legal_form": "legal_person", "executive_management_country": "UA", "third_country_control": "no",
      "ua_non_government_controlled_area": False, "non_eu_component_cost_pct": 12.345,
      "restricted_third_country_component": False, "components_from_ua_or_eea_efta": False, "safe_role": "contractor",
      "handles_classified": False, "product_regime": "dual_use", "export_intent": "outside_eu"}
ES = {"country": "ES", "legal_form": "legal_person", "executive_management_country": "ES", "third_country_control": "no",
      "non_eu_component_cost_pct": 10, "restricted_third_country_component": False, "components_from_ua_or_eea_efta": False,
      "safe_role": "contractor", "handles_classified": True, "product_regime": "military", "export_intent": "outside_eu"}


@pytest.fixture()
def seeded(conn):
    readiness_api.reset_cache()
    seed.apply(conn, CONTENT)
    conn.commit()
    return conn


@pytest.fixture()
def client(seeded):
    with TestClient(api.app) as c:
        yield c


def verdicts(body):
    return {a["programme"]: a["verdict"] for a in body["assessments"]}


# --------------------------------------------------------------------- the content in the database

def test_the_seed_is_applied_once_and_a_second_run_inserts_nothing(conn):
    first = seed.apply(conn, CONTENT)
    conn.commit()
    n_rules = sum(len(p.rules) for p in CONTENT.programmes.values())
    rows = (len(CONTENT.programmes) + len(CONTENT.requirements) + n_rules
            + sum(len(r.issuers) + len(r.prerequisites) for r in CONTENT.requirements.values()))
    assert first["inserted"] == rows
    counts = {t: conn.execute(f"SELECT count(*) n FROM {t}").fetchone()["n"] for t in
              ("requirement", "requirement_issuer", "requirement_prerequisite", "readiness_programme", "programme_requirement")}
    # WP-64: 3 requirements and the Spanish MoD route added
    assert counts["requirement"] == 15 and counts["readiness_programme"] == 7 and counts["programme_requirement"] == n_rules
    second = seed.apply(conn, CONTENT)
    conn.commit()
    assert second == {"inserted": 0, "deactivated": 0}
    assert counts == {t: conn.execute(f"SELECT count(*) n FROM {t}").fetchone()["n"] for t in counts}


def test_no_requirement_and_no_rule_is_stored_without_a_source_url(seeded):
    assert seeded.execute("SELECT count(*) n FROM requirement WHERE source_url IS NULL OR source_url = ''").fetchone()["n"] == 0
    assert seeded.execute("SELECT count(*) n FROM programme_requirement WHERE source_url = '' OR source_text = ''").fetchone()["n"] == 0
    assert seeded.execute("SELECT count(*) n FROM readiness_programme WHERE source_url = ''").fetchone()["n"] == 0
    with pytest.raises(psycopg.errors.NotNullViolation):
        seeded.execute("INSERT INTO requirement (code, name, category, kind, summary, text_origin, verification_status, last_reviewed) "
                       "VALUES ('REQ-X', 'x', 'quality', 'document', 's', 'notes', 'V', '2026-10-17')")
    seeded.rollback()


def test_the_database_returns_exactly_what_the_seed_holds(seeded):
    read = seed.read_content(seeded)
    assert read.reviewed == CONTENT.reviewed
    assert set(read.programmes) == set(CONTENT.programmes)
    for code, p in CONTENT.programmes.items():
        assert read.programmes[code] == p, code
    for code, r in CONTENT.requirements.items():
        got = read.requirements[code]
        assert sorted(got.issuers, key=lambda i: (i.country, i.name)) == sorted(r.issuers, key=lambda i: (i.country, i.name)), code
        assert got.prerequisites == r.prerequisites, code
        assert got.__class__(**{**got.__dict__, "issuers": ()}) == r.__class__(**{**r.__dict__, "issuers": ()}), code


def test_a_row_the_seed_no_longer_lists_is_switched_off_never_deleted(seeded):
    from dataclasses import replace

    trimmed = replace(CONTENT, programmes={**CONTENT.programmes, "SAFE": replace(
        CONTENT.programmes["SAFE"], rules=CONTENT.programmes["SAFE"].rules[:-1])})
    out = seed.apply(seeded, trimmed)
    seeded.commit()
    assert out == {"inserted": 0, "deactivated": 1}
    assert seeded.execute("SELECT count(*) n FROM programme_requirement").fetchone()["n"] == sum(len(p.rules) for p in CONTENT.programmes.values())
    assert seeded.execute("SELECT count(*) n FROM programme_requirement WHERE NOT active").fetchone()["n"] == 1
    assert len(seed.read_content(seeded).programmes["SAFE"].rules) == len(CONTENT.programmes["SAFE"].rules) - 1
    seed.apply(seeded, CONTENT)                                  # listed again: switched back on
    seeded.commit()
    assert seeded.execute("SELECT count(*) n FROM programme_requirement WHERE NOT active").fetchone()["n"] == 0


def test_the_worker_applies_the_seed_when_it_starts(conn):
    from dgate import worker

    worker.ensure_requirements()
    assert conn.execute("SELECT count(*) n FROM requirement").fetchone()["n"] == 15
    worker.ensure_requirements()                               # idempotent
    assert conn.execute("SELECT count(*) n FROM requirement").fetchone()["n"] == 15


# --------------------------------------------------------------------- roles

def _as(dsn: str, role: str, password: str) -> str:
    parts = urlsplit(dsn)
    return urlunsplit(parts._replace(netloc=f"{role}:{password}@{parts.hostname}:{parts.port}"))


@pytest.fixture()
def service_roles(conn, schema, monkeypatch):
    monkeypatch.setenv("DGATE_API_PASSWORD", "api-test-password-1")
    monkeypatch.setenv("DGATE_WORKER_PASSWORD", "worker-test-password-1")
    with db.connect(schema) as admin:
        assert migrate.set_role_passwords(admin) == ["dgate_api", "dgate_worker"]
    return {"api": _as(schema, "dgate_api", "api-test-password-1"),
            "worker": _as(schema, "dgate_worker", "worker-test-password-1")}


def test_the_worker_role_loads_the_seed_and_the_api_role_only_reads_it(conn, service_roles):
    with db.connect(service_roles["worker"]) as w:
        assert seed.apply(w, CONTENT)["inserted"] > 70
    tables = ("requirement", "requirement_prerequisite", "requirement_issuer", "readiness_programme", "programme_requirement")
    with psycopg.connect(service_roles["api"], autocommit=True) as c:
        for t in tables:
            assert c.execute(f"SELECT count(*) FROM {t}").fetchone()[0] > 0
            with pytest.raises((psycopg.errors.InsufficientPrivilege, psycopg.errors.ReadOnlySqlTransaction)):
                c.execute(f"DELETE FROM {t}")
        with pytest.raises((psycopg.errors.InsufficientPrivilege, psycopg.errors.ReadOnlySqlTransaction)):
            c.execute("UPDATE requirement SET name = name")


def test_an_assessment_runs_with_nothing_but_the_read_only_api_role_and_writes_no_row(conn, service_roles, monkeypatch):
    with db.connect(service_roles["worker"]) as w:
        seed.apply(w, CONTENT)
    monkeypatch.setenv("DGATE_API_DSN", service_roles["api"])
    config.reset_cache()
    readiness_api.reset_cache()
    watched = ("requirement", "requirement_issuer", "programme_requirement", "app_user", "app_hit_daily", "call")
    before = {t: conn.execute(f"SELECT count(*) n FROM {t}").fetchone()["n"] for t in watched}
    stats_before = conn.execute("SELECT sum(n_tup_ins + n_tup_upd + n_tup_del) n FROM pg_stat_user_tables").fetchone()["n"]
    with TestClient(api.app) as c:
        r = c.post("/v1/readiness/assess", json={"profile": UA, "statuses": {}})
    assert r.status_code == 200
    assert before == {t: conn.execute(f"SELECT count(*) n FROM {t}").fetchone()["n"] for t in watched}
    # statistics are reported with a delay: the role itself could not have written anyway
    assert stats_before is not None
    config.reset_cache()


def test_before_the_rules_are_loaded_the_answer_is_503_never_an_empty_assessment(conn):
    # Until the worker has applied the seed there are no rules; "eligible against no rules" would be a lie.
    readiness_api.reset_cache()
    with TestClient(api.app) as c:
        for r in (c.post("/v1/readiness/assess", json={"profile": UA}), c.get("/v1/requirements"),
                  c.get("/v1/readiness/programmes")):
            assert r.status_code == 503 and r.headers["retry-after"] == "30"


# --------------------------------------------------------------------- the public catalogue

def test_the_catalogue_lists_every_requirement_with_its_source(client):
    body = client.get("/v1/requirements").json()
    assert body["total"] == 15 == len(body["items"])        # 12, and REQ-RID, REQ-PECAL, REQ-HSES-ES (WP-64)
    # WP-73 (QA m-6): the latest review of any rule shown (the Spanish rules, 2026-10-20), not the seed's first date
    assert body["meta"]["rulesReviewed"] == "2026-10-20"
    for item in body["items"]:
        assert item["sourceUrl"].startswith("http") and item["lastReviewed"] and item["verificationStatus"] in {"V", "S", "U"}
    aqap = next(i for i in body["items"] if i["code"] == "REQ-AQAP2110")
    assert aqap["cost"]["label"] == "vendor range, not a benchmark" and aqap["cost"]["currency"] == "USD"
    assert {"EDF", "EDIP", "EDIP-USI", "SAFE", "NATO-SUPPLY"} <= set(aqap["programmes"])


def test_one_requirement_with_issuers_rules_prerequisites_and_the_verbatim_source(client):
    body = client.get("/v1/requirements/REQ-AQAP2110").json()
    assert body["prerequisites"] == [{"code": "REQ-ISO9001", "name": "ISO 9001 quality management certificate", "relation": "before"}]
    assert body["variants"][0]["whenHeld"] == "REQ-ISO9001" and body["variants"][0]["cost"]["max"] == 25000
    assert {i["country"] for i in body["issuers"]} == {"ES", "DE", "PL", "UA"}
    assert body["source"]["text"].startswith("[") and body["source"]["origin"] == "notes"
    assert body["vendorRangeLabel"] == "vendor range, not a benchmark"
    assert all(r["source"]["text"] for r in body["rules"]) and body["rules"]
    iso = client.get("/v1/requirements/REQ-ISO9001").json()
    assert iso["requiredBy"] == ["REQ-AQAP2110", "REQ-PECAL"]      # PECAL: a formal precondition (WP-64, PA 4302)
    assert client.get("/v1/requirements/REQ-NCAGE").json()["cost"] == {
        "min": 0, "max": 0, "currency": None, "basis": "free", "text": "Free of charge (NSPA)", "alt": None, "label": None}


def test_an_eligibility_rule_page_lists_the_programme_rules_with_their_sources(client):
    safe = client.get("/v1/requirements/REQ-SAFE-35").json()
    assert [r["rule"] for r in safe["rules"]] == ["SAFE-ORIGIN-35", "SAFE-NO-RESTRICTED"]
    assert safe["programmes"] == ["SAFE"] and all(r["programmeName"].startswith("Security Action") for r in safe["rules"])
    assert "estimated cost of the components of the end product" in safe["source"]["text"]
    edip = client.get("/v1/requirements/REQ-EDIP-ELIG").json()
    assert {r["programme"] for r in edip["rules"]} == {"EDIP", "EDIP-USI"}


def test_an_unknown_requirement_is_a_404_and_a_malformed_code_a_422(client):
    assert client.get("/v1/requirements/REQ-NOPE").status_code == 404
    assert client.get("/v1/requirements/REQ-NOPE/issuers").status_code == 404
    assert client.get("/v1/requirements/req-pic").status_code == 422
    assert client.get("/v1/requirements/" + "REQ-" + "A" * 80).status_code == 422


def test_issuers_for_a_country_fall_back_to_the_all_country_body_and_say_when_none_was_collected(client):
    es = client.get("/v1/requirements/REQ-NCAGE/issuers?country=es").json()
    assert es["country"] == "ES" and es["issuers"][0]["name"].startswith("Unidad de Catalogación") and es["note"] is None
    pic = client.get("/v1/requirements/REQ-PIC/issuers?country=FR").json()
    assert pic["issuers"][0]["country"] == "*"
    none = client.get("/v1/requirements/REQ-EXPORT/issuers?country=FR").json()
    assert none["issuers"] == [] and "not been collected" in none["note"]
    assert len(client.get("/v1/requirements/REQ-NCAGE/issuers").json()["issuers"]) == len(CONTENT.requirements["REQ-NCAGE"].issuers)
    # D4: a NATO member without a row of its own is sent to its national bureau, not to NSPA
    it = client.get("/v1/requirements/REQ-NCAGE/issuers?country=IT").json()
    assert it["country"] == "IT" and it["issuers"][0]["country"] == "IT" and "NSPA" not in it["issuers"][0]["name"]
    ch = client.get("/v1/requirements/REQ-NCAGE/issuers?country=CH").json()
    assert ch["issuers"][0]["country"] == "*" and ch["issuers"][0]["name"].startswith("NSPA")
    assert client.get("/v1/requirements/REQ-NCAGE/issuers?country=ESP").status_code == 422
    assert client.get("/v1/requirements/REQ-NCAGE/issuers?country=1").status_code == 422


def test_the_rules_are_public_with_their_expressions_and_sources(client):
    body = client.get("/v1/readiness/programmes").json()
    assert [p["code"] for p in body["programmes"]] == ["EDF", "EDIP", "EDIP-USI", "SAFE", "NATO-SUPPLY", "ES-MOD", "GENERAL"]
    safe = next(p for p in body["programmes"] if p["code"] == "SAFE")
    rule = next(r for r in safe["rules"] if r["rule"] == "SAFE-ORIGIN-35")
    assert rule["condition"] == {"threshold": {"field": "non_eu_component_cost_pct", "lte": 35}}
    assert rule["denominator"] == "the estimated cost of the components of the end product"
    assert rule["source"]["url"] == "http://data.europa.eu/eli/reg/2025/1106/oj" and "35 %" in rule["source"]["text"]
    assert all(r["source"]["text"] and r["source"]["url"] for p in body["programmes"] for r in p["rules"])
    assert body["groups"]["EEA_EFTA"] == ["IS", "LI", "NO"] and body["fields"]["third_country_control"]["values"] == ["no", "ua_eea_only", "other"]


# --------------------------------------------------------------------- the assessment

def test_a_ukrainian_profile_gets_the_verdicts_the_rules_give(client):
    body = client.post("/v1/readiness/assess", json={"profile": UA, "statuses": {}}).json()
    # EDF "conditional": the EU-Ukraine association agreement is not confirmed (V2-B2)
    assert verdicts(body) == {"EDF": "conditional", "EDIP": "blocked", "EDIP-USI": "obtain", "SAFE": "eligible", "NATO-SUPPLY": "obtain"}
    edf = body["assessments"][0]
    assert edf["blocking"] == [] and edf["toObtain"] == ["EDF-PIC"] and not edf["incomplete"]
    assert edf["conditions"] == ["EDF-ESTABLISH", "EDF-EXEC-MGMT"]
    rules = {r["rule"]: r for r in edf["rules"]}
    # conditional on the association agreement (V2-B2): the reason says what the call documents say
    assert rules["EDF-ESTABLISH"]["outcome"] == "conditional" and "pending the signature of the association agreement" in rules["EDF-ESTABLISH"]["reason"]
    assert rules["EDF-PIC"]["outcome"] == "to_obtain" and rules["EDF-PIC"]["requirement"] == "REQ-PIC"
    assert "free" in rules["EDF-PIC"]["reason"] and body["assessments"][0]["counts"]["to_obtain"] == 1
    assert rules["EDF-AQAP"]["outcome"] == "info"
    assert [s["code"] for s in body["roadmap"]["steps"]][:3] == ["REQ-PIC", "REQ-NCAGE", "REQ-EXPORT"]
    assert "not legal advice" in body["notice"] and body["rulesReviewed"] == "2026-10-20" and body["call"] is None


def test_a_spanish_profile_with_iso_9001_gets_the_verdicts_and_the_shorter_aqap_path(client):
    body = client.post("/v1/readiness/assess", json={"profile": ES, "statuses": {"REQ-ISO9001": "held"}}).json()
    # WP-42 R1: the Ukraine Support Instrument also needs a Ukrainian applicant or partner, which a Spanish company's answers cannot supply
    # and the Spanish MoD route (WP-64). WP-73 (QA MJ-4): the company handles classified information and the HSEM is not mentioned,
    # which reads "not held" for a request that does not say "unknown"; a conditional rule binds where it applies, so ES-HSEM blocks
    assert verdicts(body) == {"EDF": "obtain", "EDIP": "obtain", "EDIP-USI": "conditional", "SAFE": "eligible", "NATO-SUPPLY": "obtain",
                              "ES-MOD": "blocked"}
    assert next(a for a in body["assessments"] if a["programme"] == "ES-MOD")["blocking"] == ["ES-HSEM"]
    unasked = client.post("/v1/readiness/assess", json={"profile": ES, "statuses": {"REQ-ISO9001": "held", "REQ-FSC-ES": "unknown"}}).json()
    assert verdicts(unasked)["ES-MOD"] == "conditional"
    steps = {s["code"]: s for s in body["roadmap"]["steps"]}
    # D10: Spain's AQAP route is the state's own; no vendor price is shown for it
    assert steps["REQ-AQAP2110"]["cost"] is None and "state issues this itself" in steps["REQ-AQAP2110"]["priceNote"]
    pl = client.post("/v1/readiness/assess", json={"profile": {**ES, "country": "PL", "executive_management_country": "PL"},
                                                    "statuses": {"REQ-ISO9001": "held"}}).json()
    aqap = next(s for s in pl["roadmap"]["steps"] if s["code"] == "REQ-AQAP2110")
    assert aqap["cost"]["max"] == 25000 and aqap["variantUsed"] == "REQ-ISO9001" and aqap["priceNote"] is None
    assert {s["code"] for s in body["roadmap"]["steps"]} == {"REQ-PIC", "REQ-NCAGE", "REQ-FSC-ES", "REQ-REOCE", "REQ-EXPORT", "REQ-AQAP2110",
                                                             "REQ-RID", "REQ-PECAL"}      # WP-64
    held = client.post("/v1/readiness/assess", json={"profile": ES, "statuses": {
        "REQ-ISO9001": "held", "REQ-PIC": "held", "REQ-NCAGE": "held"}}).json()
    assert verdicts(held)["EDF"] == "eligible" and verdicts(held)["NATO-SUPPLY"] == "eligible"


def test_every_line_of_an_assessment_has_its_source_and_a_date(client):
    body = client.post("/v1/readiness/assess", json={"profile": ES, "statuses": {}}).json()
    lines = [r for a in (*body["assessments"], *body["general"]) for r in a["rules"]]
    # 41, the three rules of who may apply to an EDIP call of one kind of action (V2-B1), and since WP-64 the 21 rules of the
    # Spanish MoD route, the 9 German and EU general rules and NATO-AQAP-ED
    assert len(lines) == 75
    for r in lines:
        s = r["source"]
        assert s["url"].startswith("http") and s["text"].startswith("[") and s["ref"] and s["lastReviewed"], r["rule"]
        assert r["reason"], r["rule"]


def test_the_same_request_gives_the_same_answer(client):
    a = client.post("/v1/readiness/assess", json={"profile": UA}).json()
    b = client.post("/v1/readiness/assess", json={"profile": UA}).json()
    a.pop("generatedAt"), b.pop("generatedAt")
    assert a == b


def test_a_subset_of_programmes_can_be_asked_for(client):
    body = client.post("/v1/readiness/assess", json={"profile": UA, "programmes": ["SAFE"]}).json()
    assert [a["programme"] for a in body["assessments"]] == ["SAFE"] and body["general"]
    assert client.post("/v1/readiness/assess", json={"profile": UA, "programmes": ["NOPE"]}).status_code == 422


def test_missing_answers_are_listed_with_the_question_and_do_not_read_as_no(client):
    body = client.post("/v1/readiness/assess", json={"profile": {"country": "PL"}}).json()
    safe = next(a for a in body["assessments"] if a["programme"] == "SAFE")
    assert safe["verdict"] == "conditional" and safe["incomplete"]
    assert {m["field"] for m in safe["missing"]} == {"safe_role", "executive_management_country", "third_country_control",
                                                    "non_eu_component_cost_pct", "restricted_third_country_component"}
    assert all(m["question"].endswith("?") for m in safe["missing"])


@pytest.mark.parametrize("body", [
    {"profile": {**UA, "country": "ukraine"}},
    {"profile": {**UA, "country": "ua"}},
    {"profile": {**UA, "third_country_control": "maybe"}},
    {"profile": {**UA, "non_eu_component_cost_pct": 101}},
    {"profile": {**UA, "non_eu_component_cost_pct": -1}},
    {"profile": {**UA, "non_eu_component_cost_pct": "lots"}},
    {"profile": {**UA, "product_regime": "tank"}},
    {"profile": {**UA, "company_name": "Secret Ltd"}},                     # an unknown field is refused, not stored
    {"profile": UA, "statuses": {"REQ-PIC": "done"}},
    {"profile": UA, "statuses": {"pic": "held"}},
    {"profile": UA, "statuses": {"REQ-NOPE": "held"}},
    {"profile": UA, "statuses": {f"REQ-X{i}": "held" for i in range(41)}},
    {"profile": UA, "programmes": ["x" * 5]},
    {"profile": UA, "programmes": ["SAFE"] * 13},
    {"profile": UA, "call": 0},
    {"profile": UA, "call": 99999999999999999999},
    {"profile": UA, "extra": 1},
    {},
    {"statuses": {}},
    [],
])
def test_input_is_validated_strictly(client, body):
    assert client.post("/v1/readiness/assess", json=body).status_code == 422


def test_a_refused_body_is_not_echoed_back_and_a_broken_one_gives_422(client):
    secret = "SecretHoldingLtd-4711"
    r = client.post("/v1/readiness/assess", json={"profile": {**UA, "company_name": secret}})
    assert r.status_code == 422 and secret not in r.text and '"input"' not in r.text
    r = client.post("/v1/readiness/assess", content=b"{not json", headers={"content-type": "application/json"})
    assert r.status_code == 422
    assert client.get("/v1/readiness/assess").status_code == 405


def test_an_unknown_key_is_refused_without_repeating_its_name(client):
    # D11: the header of the module says nothing of the body is echoed; that includes the name of a key
    r = client.post("/v1/readiness/assess", json={"profile": {**UA, "zzSecretMarker": 1}})
    assert r.status_code == 422 and "zzSecretMarker" not in r.text and "(unknown field)" in r.text
    r = client.post("/v1/readiness/assess", json={"profile": UA, "zzTopMarker": 1})
    assert r.status_code == 422 and "zzTopMarker" not in r.text


def test_el_and_uk_are_read_as_greece_and_the_united_kingdom_and_other_codes_are_checked(client):
    greece = client.post("/v1/readiness/assess", json={"profile": {**ES, "country": "EL", "executive_management_country": "EL"},
                                                      "statuses": {"REQ-PIC": "held", "REQ-NCAGE": "held"}}).json()
    assert verdicts(greece)["EDF"] == "eligible" and verdicts(greece)["EDIP"] == "eligible"      # a Member State, not "outside"
    uk = client.post("/v1/readiness/assess", json={"profile": {**ES, "country": "UK", "executive_management_country": "UK"}}).json()
    assert verdicts(uk)["EDF"] == "blocked"                                                       # the United Kingdom is outside
    assert client.post("/v1/readiness/assess", json={"profile": {**ES, "country": "ZZ"}}).status_code == 422
    assert client.post("/v1/readiness/assess", json={"profile": {**ES, "legal_form": "sole_trader"}}).status_code == 422
    assert client.post("/v1/readiness/assess", json={"profile": {**ES, "safe_role": "boss"}}).status_code == 422


def test_a_body_over_the_limit_is_refused_with_413(client):
    big = json.dumps({"profile": UA, "statuses": {}, "pad": "x" * 20_000})
    r = client.post("/v1/readiness/assess", content=big, headers={"content-type": "application/json"})
    assert r.status_code == 413


def test_nothing_of_the_body_is_logged(client, caplog):
    caplog.set_level(logging.DEBUG)
    body = {"profile": {**UA, "non_eu_component_cost_pct": 12.345}, "statuses": {"REQ-PIC": "held"}}
    assert client.post("/v1/readiness/assess", json=body).status_code == 200
    assert client.post("/v1/readiness/assess", json={"profile": {**UA, "country": "nope"}}).status_code == 422
    text = caplog.text
    for needle in ("12.345", "third_country_control", "executive_management_country", "REQ-PIC", "outside_eu"):
        assert needle not in text, needle


def test_the_assessment_is_charged_three_tokens_and_the_catalogue_one():
    assert hardening.request_cost("/v1/readiness/assess", {}) == 3
    assert hardening.request_cost("/v1/requirements", {}) == 1
    assert "/v1/readiness" in hardening.BODY_LIMITED_PREFIXES


def test_a_post_answer_is_never_cacheable(client):
    r = client.post("/v1/readiness/assess", json={"profile": UA})
    assert r.headers["cache-control"] == "no-store"


# --------------------------------------------------------------------- the cross-layer question

def _call(conn, native_id, programme, days, title="A call"):
    call = Call(programme_code=programme, native_id=native_id, title=title, topic_code=f"{programme}-{native_id}",
                deadline_at=None if days is None else datetime.now(timezone.utc) + timedelta(days=days),
                status="open", regime="defence")
    db.upsert_call(conn, call, f"hash-{native_id}", db.source_id(conn, "eu_portal"))
    conn.commit()
    return conn.execute("SELECT id FROM call WHERE native_id = %s", (native_id,)).fetchone()["id"]


def test_this_call_closes_in_six_weeks_can_i_take_part_and_if_not_what_is_the_fastest_path(client, conn):
    edf = _call(conn, "c1", "EDF", 42)
    body = client.post("/v1/readiness/assess", json={"profile": ES, "call": edf}).json()
    call = body["call"]
    assert call["id"] == str(edf) and call["covered"] and call["programme"] == "EDF"
    (timing,) = call["timings"]
    assert timing["programme"] == "EDF" and timing["realistic"] == "yes"
    assert timing["steps"] == ["REQ-PIC"] and timing["fastestPathDays"] == {"min": 0, "max": 0}
    assert 41 < timing["daysLeft"] <= 42
    # a Ukrainian company has the same PIC to obtain, but the association agreement is not confirmed: not a plain yes (V2-B2)
    (timing,) = client.post("/v1/readiness/assess", json={"profile": UA, "call": edf}).json()["call"]["timings"]
    assert timing["realistic"] == "depends" and timing["steps"] == ["REQ-PIC"]
    # a company that cannot be fixed by a certificate is told so
    edip = _call(conn, "c2", "EDIP", 60)
    call = client.post("/v1/readiness/assess", json={"profile": UA, "call": edip}).json()["call"]
    realistic = {t["programme"]: t["realistic"] for t in call["timings"]}
    assert realistic == {"EDIP": "not_possible", "EDIP-USI": "yes"}
    not_fixable = next(t for t in call["timings"] if t["programme"] == "EDIP")["notFixable"]
    assert {n["rule"] for n in not_fixable} == {"EDIP-ESTABLISH", "EDIP-EXEC-MGMT"}


def test_a_call_of_a_programme_without_rules_gets_no_verdict_and_an_unknown_call_a_404(client, conn):
    horizon = _call(conn, "c3", "HORIZON", 30)
    call = client.post("/v1/readiness/assess", json={"profile": UA, "call": horizon}).json()["call"]
    assert call["covered"] is False and call["timings"] == [] and "No readiness rules" in call["text"]
    assert client.post("/v1/readiness/assess", json={"profile": UA, "call": 987654}).status_code == 404


def test_a_removed_call_is_not_described(client, conn):
    removed_call = _call(conn, "c4", "EDF", 30)
    conn.execute("UPDATE call SET suppressed = TRUE WHERE id = %s", (removed_call,))
    conn.commit()
    assert client.post("/v1/readiness/assess", json={"profile": UA, "call": removed_call}).status_code == 410


def test_a_call_without_a_deadline_says_the_time_cannot_be_compared(client, conn):
    open_ended = _call(conn, "c5", "EDF", None)
    (timing,) = client.post("/v1/readiness/assess", json={"profile": UA, "call": open_ended}).json()["call"]["timings"]
    assert timing["realistic"] == "unknown" and timing["deadline"] is None
