"""WP-92 against a real Postgres: the funds summary is stored, backfilled from the raw store and served on the call page;
who may apply is read from the call's own eligibility facts first, in the badge and in the filter alike.

No network and no model: calls, raw objects and eligibility rows are written here.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from dgate import api, db, stats, who_apply
from tests.integration.test_wp31 import doc, hold, put

pytestmark = pytest.mark.integration

TOPICS = json.loads((Path(__file__).parents[1] / "fixtures" / "eu_topic_descriptions.json").read_text(encoding="utf-8"))


@pytest.fixture(autouse=True)
def _fresh_cache():
    stats.reset_cache()
    yield
    stats.reset_cache()


@pytest.fixture()
def client(conn):
    with TestClient(api.app) as c:
        yield c


def test_the_migration_adds_the_columns(conn):
    cols = {r["column_name"] for r in conn.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_name = 'call'").fetchall()}
    assert {"funds_summary", "who_may_apply_doc", "sme_only", "who_may_apply_evidence"} <= cols


def test_the_topic_details_step_stores_the_summary(conn):
    from dgate.sources import eu_portal

    cid = put(conn, "usi", programme="EDF", topic="EDF-EDIP-USI-2026-SCS")
    fields = eu_portal.detail_fields(TOPICS["EDF-EDIP-USI-2026-SCS"], "EDF-EDIP-USI-2026-SCS")
    assert db.update_call_details(conn, cid, fields, "h-usi") == "changed"
    conn.commit()
    got = conn.execute("SELECT funds_summary FROM call WHERE id = %s", (cid,)).fetchone()["funds_summary"]
    assert got.startswith("The objective of this topic is to increase the production capacity")
    # the portal's real markup (topicdescriptionkind, Scope only): the aim sentence opening the Scope, nothing else
    real = TOPICS["REAL-EDF-2026-DA-AIR-FIGHTER"]
    cid2 = put(conn, "fighter", programme="EDF", topic=real["identifier"])
    db.update_call_details(conn, cid2, eu_portal.detail_fields(real, real["identifier"]), "h-fighter")
    conn.commit()
    assert conn.execute("SELECT funds_summary FROM call WHERE id = %s", (cid2,)).fetchone()["funds_summary"] == (
        "The objective of this topic is to follow up and complement previous activities in the field of smart technologies "
        "for next generation fighter systems.")


def test_the_backfill_reads_the_raw_store_reports_by_default_and_is_idempotent(conn, monkeypatch, tmp_path):
    from dgate import config
    from dgate.ops import funds_summary
    from dgate.rawstore import build_store

    monkeypatch.setenv("DGATE_RAW_BACKEND", "fs")
    monkeypatch.setenv("DGATE_RAW_DIR", str(tmp_path / "raw"))
    config.reset_cache()
    src = db.source_id(conn, "eu_portal")
    with_text = put(conn, "with_text", programme="EDF", topic="EDF-2026-RA-SENS-MSDT")
    none_pass = put(conn, "none_pass", programme="EDF", topic="EDF-2026-LS-RA-CHALLENGE")
    no_raw = put(conn, "no_raw", programme="EDF")
    for cid, h in ((with_text, "h-1"), (none_pass, "h-2"), (no_raw, "h-3")):
        conn.execute("UPDATE call SET details_hash = %s WHERE id = %s", (h, cid))
    store = build_store()
    for code, h in (("EDF-2026-RA-SENS-MSDT", "h-1"), ("EDF-2026-LS-RA-CHALLENGE", "h-2")):
        key = store.put(f"eu_portal/2026/10/23/{code}.json", TOPICS[code])
        db.record_raw(conn, src, code, h, key)
    conn.commit()

    report = funds_summary.run(write=False)
    assert (report.calls, report.with_summary, report.written, report.no_raw, report.failed) == (3, 1, 1, 1, 0)
    assert conn.execute("SELECT funds_summary FROM call WHERE id = %s", (with_text,)).fetchone()["funds_summary"] is None

    assert funds_summary.run(write=True).written == 1
    row = conn.execute("SELECT funds_summary, details_hash FROM call WHERE id = %s", (with_text,)).fetchone()
    assert row["funds_summary"].startswith("The aim is to strengthen the European defence technological")
    assert "150 km" not in row["funds_summary"] and "TRL" not in row["funds_summary"]
    assert row["details_hash"] == "h-1"
    assert conn.execute("SELECT funds_summary FROM call WHERE id = %s", (none_pass,)).fetchone()["funds_summary"] is None
    assert funds_summary.run(write=True).written == 0                      # a second run writes nothing
    config.reset_cache()


def test_the_call_page_serves_the_summary_and_never_the_description(client, conn):
    cid = put(conn, "srv", programme="EDF", topic="EDF-2026-RA-NAVAL")
    conn.execute("UPDATE call SET funds_summary = 'The objective is to support research on autonomous naval systems.' "
                 "WHERE id = %s", (cid,))
    conn.commit()
    body = client.get(f"/v1/funding/{cid}").json()
    assert body["fundsSummary"] == "The objective is to support research on autonomous naval systems."
    assert not any("description" in k.lower() for k in body)
    assert "fundsSummary" not in client.get("/v1/funding", params={"status": "all"}).json()["items"][0]
    # a source whose licence does not allow the text: not served
    conn.execute("UPDATE source SET commercial_ok = NULL WHERE code = 'eu_portal'")
    conn.commit()
    assert client.get(f"/v1/funding/{cid}").json()["fundsSummary"] is None
    conn.execute("UPDATE source SET commercial_ok = TRUE WHERE code = 'eu_portal'")
    conn.commit()


# ---------------------------------------------------------------- who may apply, from the call's own facts first

def badges(client, **params) -> dict[str, tuple]:
    r = client.get("/v1/funding", params={"status": "all", "pageSize": 50, **params})
    assert r.status_code == 200, r.text
    return {c["topicId"]: (c["whoMayApply"], c.get("smeOnly")) for c in r.json()["items"]}


def test_the_badge_follows_the_call_document_and_falls_back_to_the_programme(client, conn):
    a = "https://example.test/public.pdf"
    b = "https://example.test/sme.pdf"
    c = "https://example.test/unclear.pdf"
    put(conn, "pub", programme="EDF", topic="EDF-2026-DA-PUB", documents=[doc(a)])     # EDF rules alone: companies
    put(conn, "sme", topic="HORIZON-CL4-2026-SME", documents=[doc(b)])                    # Horizon: nothing alone
    put(conn, "unclear", programme="EDF", topic="EDF-2026-DA-UNC", documents=[doc(c)])
    put(conn, "plain", programme="EDF", topic="EDF-2026-DA-PLAIN")
    hold(conn, a, "call_document", entity_types=(["Member State procurement agencies", "Ministries of defence"],
                                                 "Only national procurement agencies may apply.", None))
    hold(conn, b, "call_document", sme_only=(True, "This call is reserved for SMEs.", None),
         entity_types=(["SMEs"], "This call is reserved for SMEs.", None))
    hold(conn, c, "call_document", entity_types=(["Universities"], "Universities may apply.", None))

    before = badges(client)
    assert before["EDF-2026-DA-PUB"] == ("companies", None) and before["HORIZON-CL4-2026-SME"] == (None, None)

    counts = who_apply.run(conn, write=True)
    assert (counts["public"], counts["companies"], counts["sme_only"], counts["changed"]) == (1, 1, 1, 2)
    after = badges(client)
    assert after["EDF-2026-DA-PUB"] == ("public", None)                 # the document says public buyers only
    assert after["HORIZON-CL4-2026-SME"] == ("companies", True)         # SMEs only
    assert after["EDF-2026-DA-UNC"] == ("companies", None)              # facts settle nothing: the EDF rules
    assert after["EDF-2026-DA-PLAIN"] == ("companies", None)            # no document: the EDF rules
    # the filter reads the same expression as the badge
    assert set(badges(client, who="public")) == {"EDF-2026-DA-PUB"}
    assert "EDF-2026-DA-PUB" not in badges(client, who="companies")
    assert "HORIZON-CL4-2026-SME" in badges(client, who="companies")
    row = conn.execute("SELECT who_may_apply_evidence FROM call WHERE topic_code = 'EDF-2026-DA-PUB'").fetchone()
    assert row["who_may_apply_evidence"] == "Only national procurement agencies may apply."
    assert who_apply.run(conn, write=True)["changed"] == 0               # a second run changes nothing
