"""WP-36: the rules block on the call page, the "open to Ukraine" flag and filter, the regulatory tracker.

Against a real Postgres. No language model and no network: the eligibility facts are rows written by the test.
"""

from __future__ import annotations

import json

import psycopg
import psycopg.rows
import pytest
from fastapi.testclient import TestClient

from dgate import api, regulation, stats, ukraine, worker
from dgate.readiness import api as readiness_api
from dgate.readiness.seed import apply as apply_rules
from dgate.readiness.seed import load_file as load_rules
from tests.integration.test_wp31 import ANNEXES, doc, hold, put

pytestmark = pytest.mark.integration

DOC_USI = "https://ec.europa.eu/info/funding-tenders/opportunities/docs/2021-2027/edf/wp-call/2026/call-fiche_edf-usi.pdf"
DOC_EDF = "https://ec.europa.eu/info/funding-tenders/opportunities/docs/2021-2027/edf/wp-call/2026/call-fiche_edf-da.pdf"
USI_QUOTE = "be established in one of the eligible countries, i.e.: − EU Member States (including OCTs) − non-EU countries: − Ukraine"
EDF_QUOTE = "listed EEA countries and countries associated to the EDF Programme (‘EDF associated countries’)"


@pytest.fixture(autouse=True)
def _fresh_cache():
    stats.reset_cache()
    readiness_api.reset_cache()
    yield
    stats.reset_cache()
    readiness_api.reset_cache()


@pytest.fixture()
def client(conn):
    with TestClient(api.app) as c:
        yield c


@pytest.fixture()
def rules(conn):
    apply_rules(conn, load_rules())


def fields_for(quote: str) -> dict:
    return {"eligible_countries": (quote, quote, None)}


# ======================================================================= the flag

def test_the_migration_adds_the_flag_columns_and_the_tracker_table(conn):
    cols = {r["column_name"] for r in conn.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'call'").fetchall()}
    assert {"open_to_ukraine", "open_to_ukraine_reason", "open_to_ukraine_evidence", "open_to_ukraine_decided_at"} <= cols
    assert conn.execute("SELECT count(*) AS n FROM regulation_entry").fetchone()["n"] == 0
    with pytest.raises(psycopg.errors.CheckViolation):
        conn.execute("INSERT INTO regulation_entry (code, instrument, title, what_changed, event_date, status, affected, source_url, "
                     "source_ref, source_quote, checked_on) VALUES ('x','i','t','w','2026-01-01','nonsense','a','u','r','q','2026-01-01')")
    conn.rollback()


def test_the_flag_is_decided_from_the_document_then_the_regulation_and_a_second_run_changes_nothing(conn):
    usi = put(conn, "usi", programme="EDF", topic="EDF-EDIP-USI-2026-LS-IRA-X", documents=[doc(DOC_USI)])
    hold(conn, DOC_USI, "call_document", **fields_for(USI_QUOTE))
    usi_bare = put(conn, "usi2", programme="EDF", topic="EDF-EDIP-USI-2027-LS-IRA-Y")
    edip = put(conn, "edip", programme="EDF", topic="EDF-EDIP-P-2026-FNLC-CPA-AMEW")
    edf = put(conn, "edf", programme="EDF", topic="EDF-2026-DA-GROUND-MBT", documents=[doc(DOC_EDF)])
    hold(conn, DOC_EDF, "call_document", **fields_for(EDF_QUOTE))
    hz = put(conn, "hz", documents=[doc(ANNEXES, "Work programme general annexes")])
    hold(conn, ANNEXES, "general", **fields_for("Annex B lists the associated countries: Norway, Ukraine"))

    before = ukraine.run(conn, write=False)
    assert before["changed"] == 5 and before["calls"] == 5
    assert conn.execute("SELECT count(*) AS n FROM call WHERE open_to_ukraine_reason IS NOT NULL").fetchone()["n"] == 0, "a report writes nothing"
    done = ukraine.run(conn, write=True)
    assert (done["yes"], done["no"], done["unknown"]) == (2, 1, 2)
    got = {r["id"]: r for r in conn.execute("SELECT id, open_to_ukraine AS flag, open_to_ukraine_reason AS reason, "
                                            "open_to_ukraine_evidence AS evidence FROM call").fetchall()}
    assert (got[usi]["flag"], got[usi]["reason"], got[usi]["evidence"]) == (True, "call_document", "Ukraine")
    assert (got[usi_bare]["flag"], got[usi_bare]["reason"]) == (True, "programme_rule")
    assert (got[edip]["flag"], got[edip]["reason"]) == (False, "programme_rule")
    assert (got[edf]["flag"], got[edf]["reason"]) == (None, "edf_association_unconfirmed"), "unknown is not no"
    assert (got[hz]["flag"], got[hz]["reason"]) == (None, "not_stated"), "the general annexes never decide it"

    stamp = conn.execute("SELECT open_to_ukraine_decided_at AS t FROM call WHERE id = %s", (usi,)).fetchone()["t"]
    assert ukraine.run(conn, write=True)["changed"] == 0
    assert conn.execute("SELECT open_to_ukraine_decided_at AS t FROM call WHERE id = %s", (usi,)).fetchone()["t"] == stamp


def test_a_new_reading_of_a_call_does_not_wipe_the_flag(conn):
    cid = put(conn, "keep", programme="EDF", topic="EDF-EDIP-USI-2026-LS-IRA-Z")
    ukraine.run(conn, write=True)
    put(conn, "keep", programme="EDF", topic="EDF-EDIP-USI-2026-LS-IRA-Z", days=25)      # the portal moved the deadline
    assert conn.execute("SELECT open_to_ukraine FROM call WHERE id = %s", (cid,)).fetchone()["open_to_ukraine"] is True


def test_the_list_filters_badges_and_counts_calls_open_to_ukraine(client, conn):
    yes = put(conn, "yes", programme="EDF", topic="EDF-EDIP-USI-2026-LS-IRA-A")
    closed_yes = put(conn, "old", programme="EDF", topic="EDF-EDIP-USI-2026-LS-IRA-B", days=-3)
    put(conn, "no", programme="EDF", topic="EDF-EDIP-P-2026-FNLC-CPA-C")
    put(conn, "unknown", programme="EDF", topic="EDF-2026-DA-D")
    ukraine.run(conn, write=True)

    everything = client.get("/v1/funding", params={"status": "all"}).json()
    assert everything["total"] == 4 and everything["ukraineTotal"] == 2
    only = client.get("/v1/funding", params={"status": "all", "ukraine": "true"}).json()
    assert only["total"] == 2 and {c["id"] for c in only["items"]} == {str(yes), str(closed_yes)}
    assert all(c["openToUkraine"] is True for c in only["items"])
    by_topic = {c["topicId"]: c["openToUkraine"] for c in everything["items"]}
    assert by_topic["EDF-EDIP-P-2026-FNLC-CPA-C"] is False and by_topic["EDF-2026-DA-D"] is None, "false and unknown stay apart"
    # The count follows the other filters; only `true` is a filter.
    openly = client.get("/v1/funding", params={"status": "open"}).json()
    assert openly["total"] == 3 and openly["ukraineTotal"] == 1
    assert client.get("/v1/funding", params={"status": "open", "ukraine": "true"}).json()["total"] == 1
    assert client.get("/v1/funding", params={"ukraine": "false"}).status_code == 422
    assert client.get("/v1/funding", params={"ukraine": "yes"}).status_code == 422
    both = client.get("/v1/funding", params={"status": "all", "ukraine": "true", "cascade": "true"}).json()
    assert both["total"] == 0 and both["ukraineTotal"] == 0 and both["cascadeTotal"] == 0, "each count follows the other filter"


def test_the_call_detail_says_how_the_flag_was_decided_and_carries_the_rules_block(client, conn, rules):
    usi = put(conn, "usi", programme="EDF", topic="EDF-EDIP-USI-2026-LS-IRA-A")
    edf = put(conn, "edf", programme="EDF", topic="EDF-2026-DA-D")
    hz = put(conn, "hz")
    ukraine.run(conn, write=True)

    body = client.get(f"/v1/funding/{usi}").json()
    assert body["openToUkraine"] is True and body["ukraineBasis"]["reason"] == "programme_rule"
    assert "Article 26(1)" in body["ukraineBasis"]["evidence"]
    block = body["rulesApply"]
    assert block["regime"]["code"] == "EDIP-USI" and block["encoded"] is True
    assert "USI-TERRITORY" in [r["rule"] for r in block["rules"]]
    assert all(r["source"]["url"] and r["source"]["text"] and r["source"]["lastReviewed"] for r in block["rules"])
    assert block["alsoRead"]["ref"].startswith("Regulation (EU) 2025/2643, Article 27(3)")
    assert "legal advice" in block["notice"]

    unconfirmed = client.get(f"/v1/funding/{edf}").json()
    assert unconfirmed["openToUkraine"] is None and unconfirmed["ukraineBasis"]["reason"] == "edf_association_unconfirmed"
    assert [r["rule"] for r in unconfirmed["rulesApply"]["rules"]] == ["EDF-ESTABLISH", "EDF-EXEC-MGMT", "EDF-CONTROL"]

    horizon = client.get(f"/v1/funding/{hz}").json()
    assert horizon["rulesApply"]["regime"]["code"] == "HORIZON" and horizon["rulesApply"]["encoded"] is False
    assert horizon["rulesApply"]["rules"] == [] and horizon["ukraineBasis"]["reason"] == "not_stated"


def test_the_block_names_the_regime_even_when_the_rules_are_not_loaded_yet(client, conn):
    cid = put(conn, "edf", programme="EDF", topic="EDF-2026-DA-D")
    body = client.get(f"/v1/funding/{cid}").json()
    assert body["rulesApply"]["regime"]["code"] == "EDF" and body["rulesApply"]["encoded"] is False


def test_the_ukraine_flag_does_not_break_the_saved_search_path(conn):
    from dgate.accounts import _call_kwargs
    from dgate.funding import list_funding

    kwargs = _call_kwargs("call", {})
    assert kwargs["ukraine"] is None
    put(conn, "usi", programme="EDF", topic="EDF-EDIP-USI-2026-LS-IRA-A")
    ukraine.run(conn, write=True)
    page = list_funding(sort="deadline-asc", pageSize=10, conn=conn, **kwargs)
    assert page["total"] == 1 and page["ukraineTotal"] == 1


def test_the_worker_job_fills_the_flag_with_the_cascade_flags(conn):
    cid = put(conn, "usi", programme="EDF", topic="EDF-EDIP-USI-2026-LS-IRA-A")
    result = worker.job_cascade_flags()
    assert result.status != "failed", result.detail
    assert conn.execute("SELECT open_to_ukraine FROM call WHERE id = %s", (cid,)).fetchone()["open_to_ukraine"] is True


# ======================================================================= the regulatory tracker

def test_the_seed_is_applied_idempotently_and_a_removed_entry_is_switched_off_not_deleted(conn):
    entries = regulation.load_file()
    first = regulation.apply(conn, entries)
    assert first == {"inserted": len(entries), "deactivated": 0}
    assert regulation.apply(conn, entries) == {"inserted": 0, "deactivated": 0}
    assert regulation.apply(conn, entries[1:]) == {"inserted": 0, "deactivated": 1}
    row = conn.execute("SELECT active FROM regulation_entry WHERE code = %s", (entries[0]["code"],)).fetchone()
    assert row["active"] is False, "switched off, never deleted"
    assert conn.execute("SELECT count(*) AS n FROM regulation_entry").fetchone()["n"] == len(entries)
    assert regulation.apply(conn, entries) == {"inserted": 0, "deactivated": 0}
    assert conn.execute("SELECT active FROM regulation_entry WHERE code = %s", (entries[0]["code"],)).fetchone()["active"] is True


def test_the_worker_applies_the_tracker_on_start(conn):
    worker.ensure_regulation()
    worker.ensure_regulation()
    assert conn.execute("SELECT count(*) AS n FROM regulation_entry WHERE active").fetchone()["n"] == len(regulation.load_file())


def test_the_api_serves_the_entries_newest_first_with_source_quote_and_check_date(client, conn):
    regulation.apply(conn, regulation.load_file())
    body = client.get("/v1/regulation").json()
    assert body["lastChecked"] == "2026-10-18" and "legal advice" in body["notice"]
    days = [e["eventDate"] for e in body["entries"]]
    assert days == sorted(days, reverse=True)
    for e in body["entries"]:
        assert e["source"]["url"] and e["source"]["quote"] and e["checkedOn"] and e["status"]
    assert {e["status"] for e in body["entries"]} >= {"in_force", "adopted", "unconfirmed", "announced", "proposed"}
    assert body == regulation.payload(regulation.load_file()), "the database serves what the seed says"


def test_a_switched_off_entry_is_not_served(client, conn):
    regulation.apply(conn, regulation.load_file())
    conn.execute("UPDATE regulation_entry SET active = FALSE WHERE code = 'safe-canada'")
    conn.commit()
    assert "safe-canada" not in [e["code"] for e in client.get("/v1/regulation").json()["entries"]]


def test_the_api_role_reads_the_tracker_and_cannot_write_it(conn):
    import os

    regulation.apply(conn, regulation.load_file())
    cfg_dsn = os.environ["DGATE_TEST_DSN"]
    with psycopg.connect(cfg_dsn, autocommit=True, row_factory=psycopg.rows.dict_row) as admin:
        has = admin.execute("SELECT has_table_privilege('dgate_api', 'regulation_entry', 'SELECT') AS r, "
                            "has_table_privilege('dgate_api', 'regulation_entry', 'INSERT') AS w, "
                            "has_table_privilege('dgate_worker', 'regulation_entry', 'INSERT') AS ww").fetchone()
    assert tuple(has.values()) == (True, False, True)


def test_the_tracker_endpoint_answers_in_the_time_budget(client, conn):
    import time

    regulation.apply(conn, regulation.load_file())
    started = time.perf_counter()
    assert client.get("/v1/regulation").status_code == 200
    assert time.perf_counter() - started < 1.0
    assert json.dumps(client.get("/v1/regulation").json()).count("@") == 0, "no e-mail address in the tracker"
