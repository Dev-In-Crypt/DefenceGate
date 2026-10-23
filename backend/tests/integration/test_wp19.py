"""WP-19: the funding frictions of the persona walk-through of 16 October 2026 (ux-funding).

F1 a call the source calls forthcoming, whose opening day has come and whose deadline is ahead, is open
F3 word search with synonyms and an "also searched" line       F13 a closed list is newest first
F6 the funder is named                                         F2/F9 who can apply, official documents
F5 new calls and moved dates are listed in /v1/changes
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from dgate import api, db, stats
from dgate.normalise import Call

pytestmark = pytest.mark.integration

NOW = datetime.now(timezone.utc)
TODAY = NOW.date()


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
        status: str = "open", opens: date | None = None, title: str | None = None, country: str | None = None,
        issuer: str | None = None, conditions: dict | None = None, text: str | None = None,
        tag: str = "a", deadline: datetime | None = None) -> int:
    call = Call(
        programme_code=programme, native_id=native_id, title=title or f"Call {native_id}",
        topic_code=f"{programme}-{native_id}",
        deadline_at=deadline or ((NOW + timedelta(days=days)) if days is not None else None),
        status=status, regime="defence", country=country, issuer=issuer, opens_at=opens,
        conditions_raw=conditions, eligibility_text=text)
    call_id, _, _ = db.upsert_call(conn, call, f"hash-{programme}-{native_id}-{tag}", db.source_id(conn, source))
    conn.commit()
    return call_id


def ids(client, **params) -> list[str]:
    body = client.get("/v1/funding", params={"status": "all", **params}).json()
    return [c["topicId"].split("-", 1)[1] for c in body["items"]]


# ------------------------------------------------------------------------------ F1

def test_a_forthcoming_call_whose_opening_day_has_passed_and_deadline_is_ahead_is_open(client, conn):
    put(conn, "pathfinder", status="forthcoming", opens=TODAY - timedelta(days=3), days=12)
    put(conn, "opens_today", status="forthcoming", opens=TODAY, days=40)
    put(conn, "later", status="forthcoming", opens=TODAY + timedelta(days=5), days=40)
    put(conn, "no_opening_date", status="forthcoming", opens=None, days=40)
    put(conn, "no_deadline", status="forthcoming", opens=TODAY - timedelta(days=3), days=None)
    put(conn, "lapsed", status="forthcoming", opens=TODAY - timedelta(days=30), days=-2)

    assert sorted(ids(client, status="open")) == ["opens_today", "pathfinder"]
    assert sorted(ids(client, status="forthcoming")) == ["later", "no_deadline", "no_opening_date"]
    assert ids(client, status="closed") == ["lapsed"]
    # inside thirty days: "Closing soon" holds the one that closes in 12 days
    assert ids(client, status="closing-soon") == ["pathfinder"]
    by_id = {c["topicId"]: c for c in client.get("/v1/funding", params={"status": "all"}).json()["items"]}
    # the source's own word travels with the effective status
    assert (by_id["HORIZON-pathfinder"]["status"], by_id["HORIZON-pathfinder"]["sourceStatus"]) == (
        "open", "forthcoming")


def test_the_calendar_reads_the_same_open_list(client, conn):
    """The web calendar and the .ics ask `status=open` (web/lib/calendar.ts): one list, one rule."""
    put(conn, "pathfinder", status="forthcoming", opens=TODAY - timedelta(days=1), days=12)
    items = client.get("/v1/funding", params={"status": "open", "pageSize": 500}).json()["items"]
    assert [c["topicId"] for c in items] == ["HORIZON-pathfinder"]
    assert items[0]["deadline"] is not None


# ------------------------------------------------------------------------------ F3

def test_search_folds_hyphens_and_knows_the_drone_synonyms_and_says_what_else_it_searched(client, conn):
    put(conn, "a", title="Unmanned systems and counter-unmanned systems")
    put(conn, "b", title="Counter-drone systems")
    put(conn, "c", title="Biodiversity and soil")
    for q in ("counter-drone", "counter drone", "Counter_Drone", "UAS"):
        assert sorted(ids(client, q=q)) == ["a", "b"], q
    body = client.get("/v1/funding", params={"status": "all", "q": "counter-drone"}).json()
    assert body["search"] == {"terms": ["counter", "drone"], "alsoSearched": ["uas", "uav", "unmanned", "rpas"]}
    assert client.get("/v1/funding", params={"status": "all"}).json()["search"] is None


def test_a_short_word_is_a_whole_word_not_a_piece_of_one(client, conn):
    put(conn, "ai", title="Cybersecure tools relying on AI")
    put(conn, "ai2", title="Artificial Intelligence for decisions")
    put(conn, "no", title="Protection against threats, available while maintaining services")
    assert sorted(ids(client, q="AI")) == ["ai", "ai2"]


def test_a_partial_identifier_still_finds_the_call_and_a_query_of_punctuation_finds_nothing(client, conn):
    put(conn, "x1", title="Something")
    assert ids(client, q="HORIZON-x") == ["x1"]
    assert ids(client, q="---") == []
    assert client.get("/v1/funding", params={"status": "all", "q": "---"}).json()["search"] == {
        "terms": [], "alsoSearched": []}


# ----------------------------------------------------------------------------- F13

def test_a_closed_list_is_newest_deadline_first_unless_the_caller_asks_otherwise(client, conn):
    put(conn, "old", status="closed", days=-100)
    put(conn, "recent", status="closed", days=-3)
    put(conn, "middle", status="closed", days=-40)
    assert ids(client, status="closed") == ["recent", "middle", "old"]
    assert ids(client, status="closed", sort="deadline-asc") == ["old", "middle", "recent"]
    put(conn, "o1", days=5)
    put(conn, "o2", days=2)
    assert ids(client, status="open") == ["o2", "o1"]


# ------------------------------------------------------------------------------ F6

def test_the_funder_is_named_from_the_issuer_or_the_commission(client, conn):
    put(conn, "eu")
    put(conn, "pl", programme="PL-NCBR", source="pl_ncbr", country="PL", issuer="Narodowe Centrum Badan i Rozwoju (NCBR)")
    put(conn, "fr", programme="FR-AID", source="fr_aid", country="FR")
    by_id = {c["topicId"]: c for c in client.get("/v1/funding", params={"status": "all"}).json()["items"]}
    assert by_id["HORIZON-eu"]["funder"] == "European Commission"
    assert by_id["HORIZON-eu"]["programmeName"] == "Horizon Europe"
    assert by_id["PL-NCBR-pl"]["funder"] == "Narodowe Centrum Badan i Rozwoju (NCBR)"
    assert by_id["FR-AID-fr"]["funder"] == by_id["FR-AID-fr"]["programmeName"]


# --------------------------------------------------------------------------- F2, F9

CONDITIONS = ("Conditions 1. Admissibility conditions: Proposal page limit described in section 5 of the call "
              "document . 2. Eligible countries described in section 6 of the call document . "
              "3. Other eligibility conditions described in section 6 of the call document . "
              "4. Financial and operational capacity described in section 7 of the call document .")
DOCS = [{"label": "Call document", "url": "https://ec.europa.eu/docs/call-fiche_x_en.pdf"},
        {"label": "Application form", "url": "https://ec.europa.eu/docs/af_en.pdf"},
        {"label": "Odd", "url": "javascript:alert(1)"}]


def test_the_detail_says_who_can_apply_in_the_sources_words_and_links_its_documents(client, conn):
    put(conn, "edf", programme="EDF", text=CONDITIONS, conditions={"documents": DOCS})
    put(conn, "bare", text=None)
    by_id = {c["topicId"]: c for c in client.get("/v1/funding", params={"status": "all"}).json()["items"]}
    edf = client.get(f"/v1/funding/{by_id['EDF-edf']['slug']}").json()
    assert {r["label"]: r["value"] for r in edf["whoCanApply"]} == {
        "Eligible countries": "Described in section 6 of the call document.",
        "Other eligibility conditions": "Described in section 6 of the call document."}
    assert [d["label"] for d in edf["documents"]] == ["Call document", "Application form"]
    bare = client.get(f"/v1/funding/{by_id['HORIZON-bare']['slug']}").json()
    assert bare["whoCanApply"] == [] and bare["documents"] == []
    # the list does not carry them
    assert "documents" not in by_id["EDF-edf"] and "whoCanApply" not in by_id["EDF-edf"]


def test_the_applicants_of_a_national_call_are_who_can_apply_too(client, conn):
    put(conn, "pl", programme="PL-NCBR", source="pl_ncbr", country="PL",
        conditions={"applicant_types": ["sme", "university"]})
    slug = client.get("/v1/funding", params={"status": "all"}).json()["items"][0]["slug"]
    assert client.get(f"/v1/funding/{slug}").json()["whoCanApply"] == [
        {"label": "Applicants", "value": "SME, University"}]


def test_documents_and_the_source_text_are_withdrawn_with_the_licence_flag(client, conn):
    put(conn, "edf", programme="EDF", text=CONDITIONS, conditions={"documents": DOCS})
    slug = client.get("/v1/funding", params={"status": "all"}).json()["items"][0]["slug"]
    try:
        conn.execute("UPDATE source SET commercial_ok = FALSE WHERE code = 'eu_portal'")
        conn.commit()
        gone = client.get(f"/v1/funding/{slug}").json()
        assert gone["conditionsText"] is None and gone["whoCanApply"] == [] and gone["documents"] == []
    finally:
        conn.execute("UPDATE source SET commercial_ok = TRUE WHERE code = 'eu_portal'")
        conn.commit()


# ------------------------------------------------------------------------------ F5

def test_a_call_collected_in_the_window_and_a_moved_deadline_are_listed_as_funding_changes(client, conn):
    put(conn, "fresh", days=40)
    moved_id = put(conn, "moved", days=40)
    # An old call: first seen before the window, then its closing date moves by the source.
    conn.execute("UPDATE call SET first_seen_at = now() - interval '60 days' WHERE id = %s", (moved_id,))
    conn.commit()
    put(conn, "moved", days=55, tag="b")                      # payload changed, date moved 15 days
    put(conn, "moved", days=55, tag="b")                      # unchanged payload: nothing recorded
    body = client.get("/v1/changes").json()
    by_kind = {(c["kind"], c["call"]["topicId"]): c for c in body["funding"]}
    assert set(by_kind) == {("call-new", "HORIZON-fresh"), ("call-amended", "HORIZON-moved")}
    amended = by_kind[("call-amended", "HORIZON-moved")]
    assert [(c["field"], c["label"]) for c in amended["changes"]] == [("deadline_at", "Deadline")]
    assert amended["changes"][0]["before"] == (NOW + timedelta(days=40)).date().isoformat()
    assert amended["changes"][0]["after"] == (NOW + timedelta(days=55)).date().isoformat()
    assert by_kind[("call-new", "HORIZON-fresh")]["changes"] == []
    assert body["fundingTotal"] == 2
    # the tender list and its counts are unchanged in shape
    assert body["items"] == [] and body["counts"] == {"new": 0, "amended": 0, "awards": 0}
    assert conn.execute("SELECT count(*) AS n FROM call_change").fetchone()["n"] == 1


def test_re_expressing_the_same_closing_day_is_not_a_move(client, conn):
    day = NOW + timedelta(days=30)
    cid = put(conn, "same", deadline=day.replace(hour=0, minute=0, second=0, microsecond=0))
    conn.execute("UPDATE call SET first_seen_at = now() - interval '60 days' WHERE id = %s", (cid,))
    conn.commit()
    put(conn, "same", deadline=day.replace(hour=21, minute=59, second=59, microsecond=0), tag="b")
    assert conn.execute("SELECT count(*) AS n FROM call_change").fetchone()["n"] == 0
    assert client.get("/v1/changes").json()["funding"] == []


def test_a_closed_call_or_one_outside_the_country_filter_is_not_funding_news(client, conn):
    put(conn, "gone", status="closed", days=-5)
    put(conn, "pl", programme="PL-NCBR", source="pl_ncbr", country="PL")
    put(conn, "eu")
    topics = {c["call"]["topicId"] for c in client.get("/v1/changes").json()["funding"]}
    assert topics == {"PL-NCBR-pl", "HORIZON-eu"}
    only_pl = client.get("/v1/changes", params={"country": "PL"}).json()["funding"]
    assert [c["call"]["topicId"] for c in only_pl] == ["PL-NCBR-pl"]
    assert client.get("/v1/changes", params={"scope": "supply"}).json()["funding"] == []
    assert client.get("/v1/changes", params={"page": 2}).json()["funding"] == []


# ------------------------------------------------------------- the tool for stored calls (F9)

def test_the_tool_fills_the_documents_of_stored_calls_from_the_raw_store_and_is_idempotent(
        conn, monkeypatch, tmp_path):
    from dgate import config
    from dgate.ops import call_documents
    from dgate.rawstore import build_store

    monkeypatch.setenv("DGATE_RAW_BACKEND", "fs")
    monkeypatch.setenv("DGATE_RAW_DIR", str(tmp_path / "raw"))
    config.reset_cache()
    html_ = ('<p>described in section 6 of the <a href="https://ec.europa.eu/docs/call-fiche_x_en.pdf">call document</a>'
             '</p><a href="https://example.com/x.pdf">elsewhere</a>')
    src = db.source_id(conn, "eu_portal")
    with_raw = put(conn, "has_raw", programme="EDF", conditions={"budget_line": {"keep": 1}})
    no_raw = put(conn, "no_raw", programme="EDF")
    for cid, h in ((with_raw, "h-1"), (no_raw, "h-2")):
        conn.execute("UPDATE call SET details_hash = %s WHERE id = %s", (h, cid))
    key = build_store().put("eu_portal/2026/10/16/EDF-has_raw.json", {"conditions": html_})
    db.record_raw(conn, src, "EDF-has_raw", "h-1", key)
    conn.commit()

    report = call_documents.run(write=False)
    assert (report.calls, report.written, report.no_raw, report.failed) == (2, 1, 1, 0)
    assert conn.execute("SELECT conditions_raw->'documents' AS d FROM call WHERE id = %s",
                        (with_raw,)).fetchone()["d"] is None            # a report writes nothing

    assert call_documents.run(write=True).written == 1
    row = conn.execute("SELECT conditions_raw, details_hash FROM call WHERE id = %s", (with_raw,)).fetchone()
    assert row["conditions_raw"]["documents"] == [{"label": "Call document",
                                                   "url": "https://ec.europa.eu/docs/call-fiche_x_en.pdf"}]
    assert row["conditions_raw"]["budget_line"] == {"keep": 1}           # the rest of the JSON stays
    assert row["details_hash"] == "h-1"
    assert call_documents.run(write=True).written == 0                   # a second run writes nothing
    config.reset_cache()
