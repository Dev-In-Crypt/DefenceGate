"""WP-31: cascade funding, eligibility of calls without a call document, the weekly digest.

Against a real Postgres. The language model is a fake client; nothing touches the network.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone

import httpx
import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg.types.json import Jsonb

from dgate import api, cascade, changes, config, db, eligibility, stats
from dgate import weekly_digest as W
from dgate.normalise import Call
from tests.integration.test_changes import age, amend, opp, store

pytestmark = pytest.mark.integration

NOW = datetime.now(timezone.utc)
ANNEXES = ("https://ec.europa.eu/info/funding-tenders/opportunities/docs/2021-2027/horizon/wp-call/2026-2027/"
           "wp-15-general-annexes_horizon-2026-2027_en.pdf")
TOPIC_TEXT = ("General conditions 1. Admissibility Conditions: described in Annex A. 2. Eligible Countries described in "
              "Annex B. 3. Other Eligible Conditions The following additional eligibility criteria apply: this topic "
              "requires the participation of at least 3 practitioners from at least 3 different Member States. "
              "4. Financial and operational capacity and exclusion described in Annex C. "
              "6. Legal and financial set-up of the grants The granting authority may object to a transfer of ownership of results. "
              "Beneficiaries may provide financial support to third parties. "
              "Specific conditions described in the [specific topic of the Work Programme] "
              "Application and evaluation forms and model grant agreement (MGA): "
              "Information on financial support to third parties (HE)")
TITLE_ONLY_TEXT = ("General conditions 3. Other Eligible Conditions described in Annex B. 4. Financial and operational "
                   "capacity described in Annex C. Application and evaluation forms Call-specific instructions "
                   "Detailed budget table (HE LS) Information on financial support to third parties (HE)")
GENERAL_TEXT = ("Annex B. Eligible countries. Legal entities established in Member States or associated countries. "
                "RIA and IA: at least three independent legal entities, each established in a different Member State "
                "or associated country.")


@pytest.fixture(autouse=True)
def _fresh_cache():
    stats.reset_cache()
    yield
    stats.reset_cache()


@pytest.fixture()
def client(conn):
    with TestClient(api.app) as c:
        yield c


def put(conn, native_id: str, *, programme: str = "HORIZON", source: str = "eu_portal", days: int | None = 20,
        status: str = "open", country: str | None = None, text: str | None = None, documents: list | None = None,
        opens=None, topic: str | None = None, conditions: dict | None = None) -> int:
    cond = {**(conditions or {}), **({"documents": documents} if documents is not None else {})} or None
    call = Call(programme_code=programme, native_id=native_id, title=f"Call {native_id}",
                topic_code=topic or f"{programme}-{native_id}", status=status, regime="defence", country=country,
                deadline_at=(NOW + timedelta(days=days)) if days is not None else None, opens_at=opens,
                eligibility_text=text, conditions_raw=cond)
    call_id, _, _ = db.upsert_call(conn, call, f"hash-{programme}-{native_id}", db.source_id(conn, source))
    conn.commit()
    return call_id


def fields(**given) -> dict:
    blank = {"value": None, "confidence": 0.0, "quote": None, "note": None, "verified": False}
    out = {name: dict(blank) for name in eligibility.FIELDS}
    for name, (value, quote, note) in given.items():
        out[name] = {"value": value, "confidence": 1.0, "quote": quote, "note": note, "verified": True}
    return out


def hold(conn, url: str, scope: str, **given) -> None:
    conn.execute("INSERT INTO call_document_text (url, sha256, pages, chars, text) VALUES (%s, 'x', 1, 1, 't') "
                 "ON CONFLICT DO NOTHING", (url,))
    conn.execute(
        """INSERT INTO call_eligibility (url, fields, model, prompt_version, input_tokens, output_tokens, cost_usd, scope)
           VALUES (%s, %s, 'm', %s, 1, 1, 0, %s)""",
        (url, Jsonb(fields(**given)), eligibility.PROMPT_VERSION, scope))
    conn.commit()


def doc(url: str, label: str = "Call document") -> dict:
    return {"label": label, "url": url}


# ======================================================================= migrations

def test_the_migrations_add_the_cascade_columns_the_scope_and_the_digest_table(conn):
    cols = {r["column_name"] for r in conn.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_name = 'call'").fetchall()}
    assert {"cascade", "cascade_reason", "cascade_evidence", "cascade_decided_at"} <= cols
    scope = conn.execute("SELECT column_default FROM information_schema.columns "
                         "WHERE table_name = 'call_eligibility' AND column_name = 'scope'").fetchone()
    assert "call_document" in scope["column_default"]
    assert conn.execute("SELECT count(*) AS n FROM digest_issue").fetchone()["n"] == 0
    with pytest.raises(psycopg.errors.CheckViolation):
        conn.execute("INSERT INTO call_eligibility (url, fields, model, prompt_version, input_tokens, output_tokens, "
                     "cost_usd, scope) VALUES ('u', '{}', 'm', 1, 1, 1, 0, 'nonsense')")
    conn.rollback()


# ======================================================================= cascade flags

def test_the_ops_tool_sets_the_flag_from_facts_and_text_and_leaves_the_rest_undecided(conn):
    with_fact = put(conn, "fact", documents=[doc("https://example.test/a.pdf")])
    hold(conn, "https://example.test/a.pdf", "call_document",
         cascade_funding=(True, "Financial support to third parties is allowed in all topics under this call.", None))
    refused = put(conn, "refused", documents=[doc("https://example.test/b.pdf")])
    hold(conn, "https://example.test/b.pdf", "call_document",
         cascade_funding=(False, "Financial support to third parties is not allowed.", None))
    stated = put(conn, "stated", text=TOPIC_TEXT, documents=[doc(ANNEXES, "Annex A")])
    title_only = put(conn, "title", text=TITLE_ONLY_TEXT)
    general_only = put(conn, "general", text=TITLE_ONLY_TEXT, documents=[doc(ANNEXES, "Annex A")])
    hold(conn, ANNEXES, "general", cascade_funding=(True, "FSTP may be allowed.", None))
    national = put(conn, "national", programme="PL-NCBR", source="pl_ncbr")

    before = cascade.run(conn, write=False)
    assert before["changed"] == 6 and conn.execute("SELECT count(*) AS n FROM call WHERE cascade_reason IS NOT NULL"
                                                   ).fetchone()["n"] == 0, "a report writes nothing"
    done = cascade.run(conn, write=True)
    assert done == {"calls": 6, "yes": 2, "no": 1, "undecided": 3, "changed": 6}

    got = {r["id"]: r for r in conn.execute(
        "SELECT id, cascade, cascade_reason, cascade_evidence FROM call").fetchall()}
    assert (got[with_fact]["cascade"], got[with_fact]["cascade_reason"]) == (True, "call_document")
    assert "allowed in all topics" in got[with_fact]["cascade_evidence"]
    assert (got[refused]["cascade"], got[refused]["cascade_reason"]) == (False, "call_document")
    assert (got[stated]["cascade"], got[stated]["cascade_reason"]) == (True, "call_text")
    assert got[stated]["cascade_evidence"] == "Beneficiaries may provide financial support to third parties."
    # The annex title is not a statement; the general annexes do not decide; a national call has none.
    for cid in (title_only, general_only, national):
        assert (got[cid]["cascade"], got[cid]["cascade_reason"]) == (None, "not_stated")


def test_the_ops_tool_is_idempotent_and_follows_a_changed_text(conn):
    cid = put(conn, "x", text=TOPIC_TEXT)
    assert cascade.run(conn, write=True)["changed"] == 1
    stamp = conn.execute("SELECT cascade_decided_at FROM call WHERE id = %s", (cid,)).fetchone()["cascade_decided_at"]
    assert cascade.run(conn, write=True)["changed"] == 0
    assert conn.execute("SELECT cascade_decided_at FROM call WHERE id = %s", (cid,)).fetchone()["cascade_decided_at"] == stamp
    conn.execute("UPDATE call SET eligibility_text = %s WHERE id = %s", (TITLE_ONLY_TEXT, cid))
    conn.commit()
    assert cascade.run(conn, write=True)["changed"] == 1
    assert conn.execute("SELECT cascade, cascade_reason FROM call WHERE id = %s", (cid,)).fetchone() == {
        "cascade": None, "cascade_reason": "not_stated"}


def test_a_new_reading_of_a_call_does_not_wipe_the_flag(conn):
    cid = put(conn, "keep", text=TOPIC_TEXT)
    cascade.run(conn, write=True)
    put(conn, "keep", text=TOPIC_TEXT, days=25)          # the portal moved the deadline: upsert_call runs again
    assert conn.execute("SELECT cascade FROM call WHERE id = %s", (cid,)).fetchone()["cascade"] is True


def test_the_list_filters_by_cascade_badges_it_and_counts_it_among_the_other_filters(client, conn):
    yes = put(conn, "yes", text=TOPIC_TEXT)
    closed_yes = put(conn, "old", text=TOPIC_TEXT, days=-3)
    put(conn, "no", text=TITLE_ONLY_TEXT)
    cascade.run(conn, write=True)

    everything = client.get("/v1/funding", params={"status": "all"}).json()
    assert everything["total"] == 3 and everything["cascadeTotal"] == 2
    only = client.get("/v1/funding", params={"status": "all", "cascade": "true"}).json()
    assert only["total"] == 2 and only["cascadeTotal"] == 2
    assert {c["id"] for c in only["items"]} == {str(yes), str(closed_yes)}
    assert all(c["cascade"] is True for c in only["items"])
    by_id = {c["id"]: c for c in everything["items"]}
    assert [c["cascade"] for c in everything["items"] if c["topicId"].endswith("-no")] == [None], "undecided is not 'no'"
    assert by_id[str(yes)]["cascade"] is True
    # The count follows the other filters: among the open calls there is one.
    openly = client.get("/v1/funding", params={"status": "open"}).json()
    assert openly["total"] == 2 and openly["cascadeTotal"] == 1
    assert client.get("/v1/funding", params={"status": "open", "cascade": "true"}).json()["total"] == 1
    assert client.get("/v1/funding", params={"cascade": "false"}).status_code == 422
    assert client.get("/v1/funding", params={"cascade": "yes"}).status_code == 422


def test_the_call_detail_says_how_the_flag_was_decided_only_when_it_was(client, conn):
    yes = put(conn, "yes", text=TOPIC_TEXT)
    none = put(conn, "none", text=TITLE_ONLY_TEXT)
    cascade.run(conn, write=True)
    body = client.get(f"/v1/funding/{yes}").json()
    assert body["cascade"] is True
    assert body["cascadeBasis"] == {"reason": "call_text",
                                    "evidence": "Beneficiaries may provide financial support to third parties."}
    quiet = client.get(f"/v1/funding/{none}").json()
    assert quiet["cascade"] is None and quiet["cascadeBasis"] is None


def test_the_saved_search_path_still_lists_funding_calls(conn):
    from dgate.accounts import _call_kwargs
    from dgate.funding import list_funding

    put(conn, "a", text=TOPIC_TEXT)
    cascade.run(conn, write=True)
    page = list_funding(sort="deadline-asc", pageSize=10, conn=conn, **_call_kwargs("call", {}))
    assert page["total"] == 1 and page["cascadeTotal"] == 1


# ======================================================================= calls without a call document

def _model(general_text: str = GENERAL_TEXT):
    """A fake model: it answers from the first words of what it is sent."""
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        user = json.loads(request.content)["input"]
        seen.append(user)
        blank = {"value": None, "confidence": 0.0, "quote": None, "note": None}
        out = {name: dict(blank) for name in eligibility.FIELDS}
        if user.startswith("General annexes"):
            out["min_entities"] = {"value": 3, "confidence": 0.9, "note": None,
                                   "quote": "at least three independent legal entities, each established in a different Member State or associated country."}
            out["eligible_countries"] = {"value": "Member States and associated countries", "confidence": 0.9, "note": None,
                                         "quote": "Legal entities established in Member States or associated countries."}
        else:
            out["min_entities"] = {"value": 6, "confidence": 0.9, "note": None,
                                   "quote": "at least 3 practitioners from at least 3 different Member States"}
            out["cascade_funding"] = {"value": True, "confidence": 1.0, "note": None,
                                      "quote": "Beneficiaries may provide financial support to third parties."}
            out["sme_only"] = {"value": True, "confidence": 0.9, "note": None, "quote": "only small firms may apply"}   # not in the text
        return httpx.Response(200, json={"status": "completed", "usage": {"input_tokens": 500, "output_tokens": 100},
                                         "output": [{"type": "message", "content": [{"type": "output_text", "text": json.dumps(out)}]}]})

    return httpx.Client(transport=httpx.MockTransport(handler)), seen


@pytest.fixture()
def model_on(monkeypatch):
    monkeypatch.setenv("DGATE_OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("DGATE_OPENAI_MODEL", "test-model")
    monkeypatch.setenv("DGATE_LLM_MONTHLY_CAP_USD", "5")
    config.reset_cache()
    monkeypatch.setattr(eligibility, "fetch_text", lambda url, client=None: ("abc", 40, GENERAL_TEXT))
    yield
    config.reset_cache()


def test_the_units_to_read_are_the_shared_annexes_once_and_each_topic_text(conn):
    put(conn, "t1", text=TOPIC_TEXT, documents=[doc(ANNEXES, "Annex A")])
    put(conn, "t2", text=TOPIC_TEXT.replace("3 practitioners", "5 practitioners"), documents=[doc(ANNEXES, "Annex A")], status="closed")
    put(conn, "t3", text=TITLE_ONLY_TEXT, documents=[doc(ANNEXES, "Annex A")])
    put(conn, "cd", documents=[doc("https://example.test/fiche.pdf")])
    units = eligibility.extraction_units(conn)
    by_scope = {}
    for u in units:
        by_scope.setdefault(u["scope"], []).append(u)
    [general] = by_scope["general"]
    assert general["url"] == ANNEXES and (general["calls"], general["open_calls"]) == (3, 2)
    assert len(by_scope["topic"]) == 2, "the pointer-only text adds no unit"
    assert all(u["text"] and u["url"].startswith("call-text:") for u in by_scope["topic"])
    assert [u["scope"] for u in by_scope["call_document"]] == ["call_document"]
    assert units[0]["open_calls"] >= units[-1]["open_calls"]


def test_a_call_without_a_document_gets_facts_from_the_annexes_and_its_own_text(client, conn, model_on):
    cid = put(conn, "t1", text=TOPIC_TEXT, documents=[doc(ANNEXES, "Annex A")], topic="HORIZON-CL3-2026-01-DEMO-01")
    lone = put(conn, "lone", programme="PL-NCBR", source="pl_ncbr")
    detail = client.get(f"/v1/funding/{cid}").json()
    assert detail["eligibilityState"] == "not_read" and detail["documentEligibility"] is None
    assert [(s["scope"], s["extractedAt"]) for s in detail["eligibilitySources"]] == [("general", None), ("topic", None)]
    assert client.get(f"/v1/funding/{lone}").json()["eligibilityState"] == "no_source"

    llm_client, seen = _model()
    reports = []
    for unit in eligibility.extraction_units(conn):
        reports.append(eligibility.extract_one(conn, unit["url"], scope=unit["scope"], text=unit["text"], llm_client=llm_client))
    assert [r["scope"] for r in reports] == ["general", "topic"] or {r["scope"] for r in reports} == {"general", "topic"}
    assert any(s.startswith("General annexes of the work programme") for s in seen)
    assert any(s.startswith("Conditions of one topic") for s in seen)
    rows = {r["scope"]: r for r in conn.execute("SELECT scope, url, fields FROM call_eligibility").fetchall()}
    assert rows["general"]["url"] == ANNEXES and rows["topic"]["url"].startswith("call-text:")
    assert rows["topic"]["fields"]["sme_only"]["verified"] is False, "a quote that is not in the text is not a fact"
    assert rows["general"]["fields"]["min_entities"]["note"].startswith("General rule of the work programme annexes")

    detail = client.get(f"/v1/funding/{cid}").json()
    assert detail["eligibilityState"] == "read"
    served = detail["documentEligibility"]
    assert served["basis"] == "work_programme" and served["documentUrl"] == ANNEXES
    facts = served["facts"]
    assert "sme_only" not in facts, "unverified facts are not served"
    assert facts["eligible_countries"]["scope"] == "general"
    assert facts["eligible_countries"]["note"].startswith("General rule")
    assert facts["cascade_funding"]["scope"] == "topic" and facts["cascade_funding"]["note"] == "Stated in this topic's own conditions."
    # A rule both state: the topic's own (its quote is in its text) wins over the general annexes' one.
    assert facts["min_entities"]["value"] == 6 and facts["min_entities"]["scope"] == "topic"
    assert {s["scope"] for s in detail["eligibilitySources"]} == {"general", "topic"}
    # A second run reads nothing again.
    for unit in eligibility.extraction_units(conn):
        assert eligibility.extract_one(conn, unit["url"], scope=unit["scope"], text=unit["text"],
                                       llm_client=llm_client)["status"] == "held"
    # And the cascade tool takes the topic fact (the general fact never decides it).
    cascade.run(conn, write=True)
    assert conn.execute("SELECT cascade, cascade_reason FROM call WHERE id = %s", (cid,)).fetchone() == {
        "cascade": True, "cascade_reason": "topic_text"}


def test_a_topic_fact_whose_quote_is_found_wins_over_the_general_one(conn, model_on):
    cid = put(conn, "t1", text=TOPIC_TEXT, documents=[doc(ANNEXES, "Annex A")])
    [general, topic] = eligibility.sources_of({"documents": [doc(ANNEXES, "Annex A")]}, TOPIC_TEXT)
    hold(conn, general.key, "general", min_entities=(3, "q", None))
    hold(conn, topic.key, "topic", min_entities=(5, "q", "Stated in this topic's own conditions."))
    got = eligibility.read_many(conn, [(cid, {"documents": [doc(ANNEXES, "Annex A")]}, TOPIC_TEXT)])[cid]
    assert got["facts"]["min_entities"]["value"] == 5 and got["facts"]["min_entities"]["scope"] == "topic"


def test_a_call_with_a_call_document_ignores_annexes_and_serves_as_before(client, conn):
    cid = put(conn, "cd", documents=[doc("https://example.test/fiche.pdf"), doc(ANNEXES, "Annex A")], text=TOPIC_TEXT)
    hold(conn, "https://example.test/fiche.pdf", "call_document", sme_only=(True, "Only SMEs may apply.", None))
    detail = client.get(f"/v1/funding/{cid}").json()
    served = detail["documentEligibility"]
    assert served["basis"] == "call_document" and served["documentUrl"] == "https://example.test/fiche.pdf"
    assert served["facts"]["sme_only"]["scope"] == "call_document" and served["facts"]["sme_only"]["note"] is None
    assert [s["scope"] for s in detail["eligibilitySources"]] == ["call_document"]


def test_an_unknown_scope_is_refused_before_anything_is_sent(conn, model_on):
    with pytest.raises(ValueError):
        eligibility.extract_one(conn, "u", scope="bogus")


# ======================================================================= the weekly digest

def week_under_test() -> tuple[str, datetime, datetime]:
    week = W.last_complete_week(NOW)
    start, end = W.week_bounds(week)
    return week, start, end


def place(conn, oid: int, at: datetime, *, version: int | None = None) -> None:
    """Make a notice's versions look as if they were observed at `at`."""
    age(conn, oid, (datetime.now(timezone.utc) - at).total_seconds() / 86400, version=version)


def make_week(conn):
    """Notices and calls in, before and after the week; returns their ids."""
    week, start, end = week_under_test()
    inside = start + timedelta(days=2, hours=3)
    ids = {}
    ids["new_fr"] = store(conn, opp("W-NEW-FR", country="FR", published=inside.date()))
    place(conn, ids["new_fr"], inside)
    ids["new_es"] = store(conn, opp("W-NEW-ES", country="ES", published=inside.date()))
    place(conn, ids["new_es"], inside)
    ids["before"] = store(conn, opp("W-BEFORE", published=(start - timedelta(days=3)).date()))
    place(conn, ids["before"], start - timedelta(days=3))
    ids["after"] = store(conn, opp("W-AFTER", published=end.date()))
    place(conn, ids["after"], end + timedelta(hours=5))
    first = opp("W-AMENDED", country="FR")
    ids["amended"] = store(conn, first)
    place(conn, ids["amended"], start - timedelta(days=30), version=1)
    amend(conn, first, "b", deadline_at=NOW + timedelta(days=90))
    place(conn, ids["amended"], inside, version=2)
    return week, start, end, ids


def settle_calls(conn, start, end):
    inside = start + timedelta(days=1, hours=5)
    new_cal = put(conn, "new-es", country="ES", text=TOPIC_TEXT, documents=[doc("https://example.test/es.pdf")])
    conn.execute("UPDATE call SET first_seen_at = %s WHERE id = %s", (inside, new_cal))
    old = put(conn, "old-fr", country="FR")
    conn.execute("UPDATE call SET first_seen_at = %s WHERE id = %s", (start - timedelta(days=40), old))
    moved = put(conn, "moved-fr", country="FR")
    conn.execute("UPDATE call SET first_seen_at = %s WHERE id = %s", (start - timedelta(days=40), moved))
    conn.execute("INSERT INTO call_change (call_id, field, before_value, after_value, observed_at) "
                 "VALUES (%s, 'deadline_at', '2026-11-01', '2026-12-01', %s)", (moved, inside))
    opening = put(conn, "opening-fr", country="FR", status="forthcoming", opens=(start + timedelta(days=3)).date())
    conn.execute("UPDATE call SET first_seen_at = %s WHERE id = %s", (start - timedelta(days=20), opening))
    closing = put(conn, "closing-fr", country="FR", days=None)
    conn.execute("UPDATE call SET deadline_at = %s, first_seen_at = %s WHERE id = %s",
                 (end + timedelta(days=4), start - timedelta(days=60), closing))
    far = put(conn, "far-fr", country="FR", days=None)
    conn.execute("UPDATE call SET deadline_at = %s, first_seen_at = %s WHERE id = %s",
                 (end + timedelta(days=40), start - timedelta(days=60), far))
    rolling = put(conn, "rolling-fr", country="FR", days=None, conditions={"deadline_model": "multiple cut-off"})
    conn.execute("UPDATE call SET deadline_at = %s, first_seen_at = %s WHERE id = %s",
                 (end + timedelta(days=2), start - timedelta(days=60), rolling))
    conn.commit()
    hold(conn, "https://example.test/es.pdf", "call_document",
         min_entities=(3, "at least three", None), min_countries=(3, "three countries", None),
         cascade_funding=(True, "Financial support to third parties is allowed.", None))
    cascade.run(conn, write=True)
    return {"new": new_cal, "moved": moved, "opening": opening, "closing": closing, "far": far, "rolling": rolling}


def issue(client, **params) -> dict:
    r = client.get("/v1/digest", params=params)
    assert r.status_code == 200, r.text
    return r.json()


def test_the_digest_of_a_week_has_the_counts_of_the_change_list_for_that_window(client, conn):
    week, start, end, ids = make_week(conn)
    events, since, until = changes.build_events(conn, scope=None, countries=[], now=end, days=7, bounded=True)
    got = issue(client, week=week)
    assert (got["week"], got["weekFrom"][:10], got["weekTo"][:10]) == (week, start.date().isoformat(), end.date().isoformat())
    assert got["counts"]["tendersNew"] == sum(1 for e in events if e["kind"] == "new") == 2
    assert got["counts"]["tendersAmended"] == sum(1 for e in events if e["kind"] == "amended") == 1
    titles = {t["id"] for t in got["tendersNew"]}
    assert titles == {str(ids["new_fr"]), str(ids["new_es"])}, "a notice seen before or after the week is not in it"
    [amended] = got["tendersAmended"]
    assert amended["id"] == str(ids["amended"]) and amended["changes"][0]["field"] == "deadline_at"
    assert amended["slug"] and amended["buyerName"] and amended["country"] == "FR"


def test_the_digest_counts_calls_new_moved_opened_and_closing_and_the_cascade_among_them(client, conn):
    week, start, end, _ = make_week(conn)
    c = settle_calls(conn, start, end)
    got = issue(client, week=week)
    assert got["counts"]["callsNew"] == 1 and [x["id"] for x in got["callsNew"]] == [str(c["new"])]
    assert got["counts"]["callsAmended"] == 1 and got["callsAmended"][0]["changes"][0]["after"] == "2026-12-01"
    assert [x["id"] for x in got["callsOpened"]] == [str(c["opening"])]
    assert [x["id"] for x in got["callsClosing"]] == [str(c["closing"])], \
        "a call closing in the next 14 days is listed; a far one and a rolling one are not"
    new = got["callsNew"][0]
    assert new["cascade"] is True and new["eligibilityState"] == "read"
    assert new["eligibility"].startswith("Consortium of at least 3 entities from 3 countries")
    assert got["cascadeCalls"][0]["id"] == str(c["new"]) and got["counts"]["cascade"] == 1
    assert got["closingUntil"][:10] == (end + timedelta(days=14)).date().isoformat()
    assert got["callsClosing"][0]["eligibilityState"] == "no_source" and got["callsClosing"][0]["eligibility"] is None


def test_the_country_filter_narrows_every_section_and_its_counts(client, conn):
    week, start, end, ids = make_week(conn)
    settle_calls(conn, start, end)
    es = issue(client, week=week, country="es")
    assert es["country"] == "ES"
    assert [t["country"] for t in es["tendersNew"]] == ["ES"] and es["counts"]["tendersNew"] == 1
    assert es["counts"]["tendersAmended"] == 0 and es["counts"]["callsNew"] == 1 and es["counts"]["callsClosing"] == 0
    fr = issue(client, week=week, country="FR")
    assert fr["counts"]["tendersNew"] == 1 and fr["counts"]["tendersAmended"] == 1 and fr["counts"]["callsClosing"] == 1
    nothing = issue(client, week=week, country="PL")
    assert nothing["counts"] == {k: 0 for k in nothing["counts"]} and nothing["tendersNew"] == []
    assert client.get("/v1/digest", params={"week": week, "country": "france"}).status_code == 422


def test_a_stored_issue_serves_the_same_page_and_a_second_run_changes_nothing(client, conn):
    week, start, end, ids = make_week(conn)
    settle_calls(conn, start, end)
    live = issue(client, week=week)
    live_es = issue(client, week=week, country="ES")
    stats.reset_cache()
    first = W.refresh(conn, now=NOW)
    assert first["built"] == min(8, len(W.all_weeks(NOW))) and first["rows"] >= 1
    rows = conn.execute("SELECT week, country FROM digest_issue ORDER BY week, country").fetchall()
    assert {"week": week, "country": ""} in rows and {"week": week, "country": "ES"} in rows
    stored = issue(client, week=week)
    stored_es = issue(client, week=week, country="ES")
    for a, b in ((live, stored), (live_es, stored_es)):
        for key in ("counts", "tendersNew", "tendersAmended", "callsNew", "callsAmended", "callsOpened", "callsClosing",
                    "cascadeCalls"):
            assert a[key] == b[key], key
    # A country that had nothing is answered from the stored week, as an empty issue.
    stats.reset_cache()
    pl = issue(client, week=week, country="PL")
    assert pl["counts"]["tendersNew"] == 0 and pl["week"] == week
    before = conn.execute("SELECT count(*) AS n FROM digest_issue").fetchone()["n"]
    W.refresh(conn, now=NOW)
    assert conn.execute("SELECT count(*) AS n FROM digest_issue").fetchone()["n"] == before


def test_the_stored_issue_forgets_a_country_that_has_nothing_any_more(conn):
    week, start, end, ids = make_week(conn)
    W.refresh_week(conn, week, now=NOW)
    assert conn.execute("SELECT count(*) AS n FROM digest_issue WHERE week = %s AND country = 'ES'", (week,)).fetchone()["n"] == 1
    conn.execute("UPDATE opportunity SET suppressed = TRUE WHERE id = %s", (ids["new_es"],))
    conn.commit()
    W.refresh_week(conn, week, now=NOW)
    assert conn.execute("SELECT count(*) AS n FROM digest_issue WHERE week = %s AND country = 'ES'", (week,)).fetchone()["n"] == 0


def test_the_default_issue_is_the_last_complete_week_and_the_neighbours_are_linked(client, conn):
    week, *_ = week_under_test()
    got = issue(client)
    assert got["week"] == week and got["nextWeek"] is None
    weeks = W.all_weeks(NOW)
    assert got["previousWeek"] == (weeks[1] if len(weeks) > 1 else None)
    oldest = issue(client, week=weeks[-1])
    assert oldest["previousWeek"] is None and (oldest["nextWeek"] == weeks[-2] if len(weeks) > 1 else True)


@pytest.mark.parametrize("week", ["2026-W36", "2099-W01", "2026-W54", "2026-W00", "1999-W10"])
def test_a_week_outside_the_archive_or_not_ended_is_not_found(client, week):
    assert client.get("/v1/digest", params={"week": week}).status_code == 404


def test_the_week_in_progress_is_not_an_issue(client):
    current = W.week_id(NOW.date())
    assert current not in W.all_weeks(NOW)
    assert client.get("/v1/digest", params={"week": current}).status_code == 404


@pytest.mark.parametrize("week", ["2026-41", "last", "2026-W4", "2026-W41; DROP", "x" * 500])
def test_a_malformed_week_is_refused_before_the_database(client, week):
    assert client.get("/v1/digest", params={"week": week}).status_code == 422


def test_the_week_list_names_the_issues_and_the_counts_of_the_stored_ones(client, conn):
    week, start, end, ids = make_week(conn)
    listed = client.get("/v1/digest/weeks").json()
    assert [w["week"] for w in listed] == W.all_weeks(NOW)[:52] and all(w["counts"] is None for w in listed)
    W.refresh(conn, now=NOW)
    listed = {w["week"]: w for w in client.get("/v1/digest/weeks", params={"limit": 3}).json()}
    assert listed[week]["counts"]["tendersNew"] == 2 and listed[week]["computedAt"]
    assert client.get("/v1/digest/weeks", params={"limit": 0}).status_code == 422


def test_a_section_lists_at_most_its_limit_and_still_counts_all(client, conn, monkeypatch):
    week, start, end, ids = make_week(conn)
    monkeypatch.setattr(W, "SECTION_LIMIT", 1)
    got = issue(client, week=week)
    assert got["counts"]["tendersNew"] == 2 and len(got["tendersNew"]) == 1 and got["sectionLimit"] == 1


def test_the_digest_serves_no_contact_data_and_no_text_of_the_call(client, conn):
    week, start, end, _ = make_week(conn)
    settle_calls(conn, start, end)
    body = client.get("/v1/digest", params={"week": week}).text
    assert "@" not in body.replace("@type", "")
    assert "Beneficiaries may provide" not in body and "General conditions" not in body


def test_an_issue_is_built_and_served_well_inside_the_budget(client, conn):
    week, start, end, _ = make_week(conn)
    settle_calls(conn, start, end)
    started = time.monotonic()
    issue(client, week=week)
    assert time.monotonic() - started < 1.5
    W.refresh(conn, now=NOW)
    stats.reset_cache()
    started = time.monotonic()
    issue(client, week=week)
    assert time.monotonic() - started < 0.5, "a stored issue is one row"


def test_the_changes_list_is_unchanged_by_the_bounded_window(client, conn):
    """/v1/changes still reaches to now: `bounded` is only for the digest of a past week."""
    store(conn, opp("LIVE-1"))
    first = client.get("/v1/changes").json()
    assert first["counts"] == {"new": 1, "amended": 0, "awards": 0}
    events, _, _ = changes.build_events(conn, scope=None, countries=[], now=NOW + timedelta(days=1), days=14, bounded=True)
    assert len(events) == 1
    events, _, _ = changes.build_events(conn, scope=None, countries=[], now=NOW - timedelta(days=1), days=14, bounded=True)
    assert events == [], "a window that ended before the notice was seen does not list it"
