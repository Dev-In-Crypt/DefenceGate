"""WP-132 against a real Postgres: a call the EU portal stops listing becomes `unlisted` after two complete runs and comes back when it is
listed again; the ops step counts the calls already held from the run history; out-of-scope calls leave the sitemap and say so; the
"Minimum consortium" row is built from the facts; a stored quote whose parts are in the document is verified again.

No network and no model: calls, runs and eligibility rows are written here.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from psycopg.types.json import Jsonb

from dgate import api, db, eligibility, stats, who_apply
from dgate.normalise import Call
from dgate.ops import wp132_funding
from tests.integration.test_wp31 import doc, hold, put
from tests.unit.test_wp132 import KEC_QUOTE, KEC_TEXT

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _fresh_cache():
    stats.reset_cache()
    yield
    stats.reset_cache()


@pytest.fixture()
def client(conn):
    with TestClient(api.app) as c:
        yield c


def listed(client, **params):
    return {c["id"]: c["status"] for c in client.get("/v1/funding", params={"pageSize": 100, **params}).json()["items"]}


def nightly(conn, *seen: str) -> int:
    """One complete eu_portal run that lists the calls named in `seen` (as run_eu_portal does, without the fetch)."""
    run = db.start_run(conn, "eu_portal", 1)
    for native in seen:
        call = Call(programme_code="HORIZON", native_id=native, title=f"Call {native}", topic_code=f"HORIZON-{native}", status="open",
                    regime="defence", deadline_at=datetime.now(timezone.utc) + timedelta(days=20))
        db.upsert_call(conn, call, f"hash-HORIZON-{native}", db.source_id(conn, "eu_portal"))
    n = db.count_unlisted(conn, db.source_id(conn, "eu_portal"), run)
    db.finish_run(conn, run, fetched=len(seen), new=0, changed=0)
    return n


def test_the_migration_adds_the_columns(conn):
    cols = {r["column_name"] for r in conn.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_name = 'call'").fetchall()}
    assert {"unlisted_runs", "consortium_rule"} <= cols


def test_a_call_the_portal_stops_listing_is_unlisted_after_two_runs_and_open_again_when_listed(client, conn):
    kept = put(conn, "kept")
    gone = put(conn, "gone")
    closed = put(conn, "closed", status="closed", days=-3)
    scoped_out = put(conn, "out")
    conn.execute("UPDATE call SET out_of_scope = true WHERE id = %s", (scoped_out,))
    conn.commit()

    assert nightly(conn, "kept") == 1, "only the open call the run did not list (not the closed one, not the out-of-scope one)"
    assert listed(client)[str(gone)] == "open", "one run without it is not enough"
    assert nightly(conn, "kept") == 1
    open_now = listed(client)
    assert str(gone) not in open_now and open_now[str(kept)] == "open"
    assert listed(client, status="all")[str(gone)] == "unlisted"
    assert str(gone) not in listed(client, status="closed") and str(gone) not in listed(client, status="open-forthcoming")
    body = client.get(f"/v1/funding/{gone}").json()
    assert body["status"] == "unlisted" and body["sourceStatus"] == "open"
    rows = {r["id"]: r for r in conn.execute("SELECT id, unlisted_runs FROM call").fetchall()}
    assert (rows[gone]["unlisted_runs"], rows[kept]["unlisted_runs"], rows[closed]["unlisted_runs"], rows[scoped_out]["unlisted_runs"]) == (2, 0, 0, 0)

    nightly(conn, "kept", "gone")                                   # the portal lists it again
    assert listed(client)[str(gone)] == "open"
    assert conn.execute("SELECT unlisted_runs FROM call WHERE id = %s", (gone,)).fetchone()["unlisted_runs"] == 0


def test_the_ops_step_counts_the_held_calls_from_the_run_history(conn):
    gone = put(conn, "gone")
    seen = conn.execute("SELECT last_seen_at FROM call WHERE id = %s", (gone,)).fetchone()["last_seen_at"]
    src = db.source_id(conn, "eu_portal")
    for hours, status, floor, fetched in ((1, "success", 50, 150), (25, "success", 50, 150), (26, "success", None, 4),
                                          (49, "partial", 50, 20), (50, "success", 50, 10)):
        conn.execute("INSERT INTO ingest_run (source_id, started_at, finished_at, status, records_fetched, expected_min) "
                     "VALUES (%s, %s, %s, %s, %s, %s)", (src, seen + timedelta(hours=hours), seen + timedelta(hours=hours, minutes=1),
                                                         status, fetched, floor))
    conn.commit()
    plan = {r["id"]: r["runs"] for r in wp132_funding.unlisted_plan(conn)}
    assert plan[gone] == 2, "the two complete runs; not the detail run, the partial run or the run under its minimum"
    report = wp132_funding.run(write=False)
    assert report[0].startswith("unlisted runs to set: 1; served as unlisted from 2 runs: 1")
    assert conn.execute("SELECT unlisted_runs FROM call WHERE id = %s", (gone,)).fetchone()["unlisted_runs"] == 0, "a report writes nothing"
    wp132_funding.run(write=True)
    assert conn.execute("SELECT unlisted_runs FROM call WHERE id = %s", (gone,)).fetchone()["unlisted_runs"] == 2
    assert wp132_funding.run(write=False)[0].startswith("unlisted runs to set: 0"), "a second run changes nothing"


def test_an_out_of_scope_call_leaves_the_sitemap_and_its_page_says_so(client, conn):
    kept = put(conn, "kept")
    out = put(conn, "out")
    conn.execute("UPDATE call SET out_of_scope = true WHERE id = %s", (out,))
    conn.commit()
    slugs = [s["slug"] for s in client.get("/v1/funding/slugs").json()]
    assert any(s.startswith(f"{kept}-") for s in slugs) and not any(s.startswith(f"{out}-") for s in slugs)
    assert client.get(f"/v1/funding/{out}").json()["outOfScope"] is True
    assert client.get(f"/v1/funding/{kept}").json()["outOfScope"] is False


def test_the_minimum_consortium_row_is_built_from_the_facts(client, conn):
    url = "https://example.test/fct-03.pdf"
    cid = put(conn, "fct", documents=[doc(url)], text="This topic requires at least 2 Civil Society Organisations from at least 3 different "
                                                      "EU Member States.")
    conn.execute("UPDATE call SET min_consortium_size = 2, min_member_states = 3 WHERE id = %s", (cid,))
    conn.commit()
    hold(conn, url, "call_document", min_entities=(5, "at least 3 Police Authorities and at least 2 Civil Society Organisations", None),
         min_countries=(3, "from at least 3 different EU Member States", None))
    before = client.get(f"/v1/funding/{cid}").json()["eligibility"]
    assert {"label": "Minimum consortium", "value": "2 legal entities from 3 Member States (the topic's conditions)"} in before
    counts = who_apply.run(conn, write=True)
    assert counts["consortium_changed"] == 1
    row = next(r for r in client.get("/v1/funding", params={"status": "all"}).json()["items"] if r["id"] == str(cid))
    assert {"label": "Minimum consortium", "value": "At least 5 legal entities from at least 3 countries (the call document)"} in row["eligibility"]
    assert who_apply.run(conn, write=True)["consortium_changed"] == 0


def test_a_stored_quote_whose_parts_are_in_the_document_is_verified_again(conn):
    url = "https://example.test/call-fiche_edf-edip-p-2027-ls-ira_en.pdf"
    conn.execute("INSERT INTO call_document_text (url, sha256, pages, chars, text) VALUES (%s, 'x', 1, %s, %s)", (url, len(KEC_TEXT), KEC_TEXT))
    blank = {"value": None, "confidence": 0.0, "quote": None, "note": None, "verified": False}
    fields = {name: dict(blank) for name in eligibility.FIELDS}
    fields["eligible_countries"] = {"value": "EU Member States, EEA and EDIP associated countries", "quote": KEC_QUOTE, "note": None,
                                    "confidence": 0.3, "verified": False}
    conn.execute("""INSERT INTO call_eligibility (url, fields, model, prompt_version, input_tokens, output_tokens, cost_usd, scope, document_url)
                    VALUES (%s, %s, 'm', %s, 1, 1, 0, 'call_document', %s)""",
                 (f"{url}#EDF-EDIP-P-2027-LS-IRA-KEC", Jsonb(fields), eligibility.PROMPT_VERSION, url))
    conn.commit()
    report = eligibility.reverify_stored(conn, write=False)
    assert (report["unverified"], report["found"]) == (1, 1)
    assert conn.execute("SELECT fields->'eligible_countries'->>'verified' AS v FROM call_eligibility").fetchone()["v"] == "false"
    eligibility.reverify_stored(conn, write=True)
    got = conn.execute("SELECT fields->'eligible_countries' AS f FROM call_eligibility").fetchone()["f"]
    assert got["verified"] is True and got["quote"] == KEC_QUOTE and got["value"] == "EU Member States, EEA and EDIP associated countries"
    assert eligibility.reverify_stored(conn, write=True)["found"] == 0
