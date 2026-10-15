"""Durable suppression (migration 0047): a notice, a buyer's name or a funding call removed
on request disappears from every public read, stays removed when it is collected again, and
leaves the archive alone.

Each public path the site reads is covered: the CSV export and the Atom feed are built by the
site from `/v1/tenders` and `/v1/changes`, so those two are what they can show.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import psycopg
import pytest
from fastapi.testclient import TestClient

from dgate import api, db, stats
from dgate.normalise import Call, Opportunity
from dgate.ops import data_request, suppress

pytestmark = pytest.mark.integration

NOW = datetime.now(timezone.utc)
FUTURE = NOW + timedelta(days=30)
TODAY = NOW.date()
WITHHELD = "Name withheld on request"


@pytest.fixture(autouse=True)
def _fresh_cache():
    stats.reset_cache()
    yield
    stats.reset_cache()


@pytest.fixture()
def client(conn):
    with TestClient(api.app) as c:
        yield c


def _opp(native_id: str, *, buyer: str = "Ministry of Defence", title: str = "Armoured vehicles",
         deadline: datetime = FUTURE) -> Opportunity:
    return Opportunity(
        source_code="ted", native_id=native_id, buyer_name_raw=buyer, title_original=title,
        country="FR", published_at=TODAY, deadline_at=deadline, cpv_codes=["35400000"],
        status="open", is_defence=True, sig_cpv=True, sig_cpv_military=True, dual_use=False,
        buyer_class="defence")


def _put(conn, native_id: str, **kw) -> int:
    opp = _opp(native_id, **kw)
    src = db.source_id(conn, "ted")
    opp.buyer_org_id = db.resolve_organisation(conn, opp.buyer_name_raw, "FR", src_id=src)
    oid, _ = db.upsert_opportunity(conn, opp, f"hash-{native_id}-{opp.title_original}-{opp.deadline_at}", src)
    conn.commit()
    return oid


def _suppress(conn, kind="notice", **kw) -> int:
    args = dict(kind=kind, source="ted" if kind == "notice" else None, native_id=None,
                organisation=None, reason="personal_data",
                requested_at=NOW, decided_by="Owner", note="")
    args.update(kw)
    entry = suppress.add(conn, **args)
    conn.commit()
    return entry


def _notice_ids(client, **params) -> list[str]:
    body = client.get("/v1/tenders", params={"status": "all", "scope": "all", **params}).json()
    return [t["noticeId"] for t in body["items"]]


def _versions(conn, oid) -> int:
    return conn.execute("SELECT count(*) AS n FROM opportunity_version WHERE opportunity_id = %s",
                        (oid,)).fetchone()["n"]


# ----------------------------------------------------------------- notices

def test_a_suppressed_notice_leaves_every_list_and_its_address_is_410(client, conn):
    keep, gone = _put(conn, "KEEP"), _put(conn, "GONE")
    before = _versions(conn, gone)
    _suppress(conn, native_id="GONE")

    assert _notice_ids(client) == ["KEEP"]
    assert [o["native_id"] for o in client.get("/v1/opportunities",
                                               params={"scope": "all"}).json()] == ["KEEP"]
    for path in (f"/v1/tenders/{gone}", f"/v1/tenders/{gone}-armoured-vehicles",
                 f"/v1/tenders/{gone}/versions", f"/v1/opportunities/{gone}",
                 f"/v1/opportunities/{gone}/versions"):
        r = client.get(path)
        assert r.status_code == 410, path
        assert r.json()["detail"] == "removed on request"
    assert client.get(f"/v1/tenders/{keep}").status_code == 200
    # An id that never existed is still a plain 404: only a removal is a 410.
    assert client.get("/v1/tenders/987654").status_code == 404
    # The archive is untouched.
    assert _versions(conn, gone) == before


def test_slugs_the_sitemap_reads_and_the_search_do_not_list_it(client, conn):
    _put(conn, "KEEP", title="Keep this")
    gone = _put(conn, "GONE", title="Remove this")
    _suppress(conn, native_id="GONE")
    slugs = [s["slug"] for s in client.get("/v1/tenders/slugs").json()]
    assert len(slugs) == 1 and not slugs[0].startswith(f"{gone}-")
    assert _notice_ids(client, q="Remove") == []
    assert _notice_ids(client, q="GONE") == []


def test_changes_feed_and_its_atom_source_do_not_show_it(client, conn):
    _put(conn, "KEEP")
    _put(conn, "GONE")
    # An amendment of the removed notice is not a change either.
    opp = replace(_opp("GONE"), deadline_at=FUTURE + timedelta(days=9))
    db.upsert_opportunity(conn, opp, "hash-GONE-moved", db.source_id(conn, "ted"))
    conn.commit()
    _suppress(conn, native_id="GONE")
    items = client.get("/v1/changes", params={"scope": "all"}).json()["items"]
    assert {i["tender"]["noticeId"] for i in items} == {"KEEP"}


def test_a_new_collection_cannot_publish_it_again(client, conn):
    oid = _put(conn, "GONE")
    _suppress(conn, native_id="GONE")
    # Collected again, with a change: a new version is archived, and it stays hidden.
    opp = replace(_opp("GONE"), deadline_at=FUTURE + timedelta(days=5), title_original="Changed")
    got, action = db.upsert_opportunity(conn, opp, "hash-GONE-v2", db.source_id(conn, "ted"))
    conn.commit()
    assert (got, action) == (oid, "changed") and _versions(conn, oid) == 2
    assert _notice_ids(client) == []
    assert client.get(f"/v1/tenders/{oid}").status_code == 410


def test_a_notice_suppressed_before_it_is_first_collected_is_hidden_from_the_start(client, conn):
    _suppress(conn, native_id="LATER")
    oid = _put(conn, "LATER")
    assert _notice_ids(client) == []
    assert client.get(f"/v1/tenders/{oid}").status_code == 410


def test_lifting_restores_it_and_the_history_is_kept(client, conn):
    oid = _put(conn, "GONE")
    entry = _suppress(conn, native_id="GONE")
    assert _notice_ids(client) == []
    assert suppress.lift(conn, entry, by="Owner", note="mistaken")
    conn.commit()
    assert _notice_ids(client) == ["GONE"]
    assert client.get(f"/v1/tenders/{oid}").status_code == 200
    row = conn.execute("SELECT lifted_at, lifted_by FROM suppression WHERE id = %s", (entry,)).fetchone()
    assert row["lifted_at"] is not None and row["lifted_by"] == "Owner"
    # and it can be suppressed again
    _suppress(conn, native_id="GONE")
    assert _notice_ids(client) == []


def test_the_market_figures_and_the_buyer_do_not_count_it(client, conn):
    _put(conn, "KEEP")
    gone = _put(conn, "GONE")
    org = conn.execute("SELECT buyer_org_id FROM opportunity WHERE id = %s", (gone,)).fetchone()["buyer_org_id"]
    before = client.get("/v1/buyers").json()["items"][0]["tenderCount"]
    assert before == 2
    _suppress(conn, native_id="GONE")
    stats.reset_cache()
    assert client.get("/v1/buyers").json()["items"][0]["tenderCount"] == 1
    profile = client.get(f"/v1/buyers/{org}/profile").json()
    assert profile["tenderCount"] == 1


def test_a_twin_does_not_lend_its_value_or_link_to_a_suppressed_notice(client, conn):
    ted = _opp("TED-1")
    ted.value_amount, ted.value_currency = 750000.0, "EUR"
    src = db.source_id(conn, "ted")
    ted.buyer_org_id = db.resolve_organisation(conn, ted.buyer_name_raw, "FR", src_id=src)
    db.upsert_opportunity(conn, ted, "hash-ted-1", src)
    national = replace(_opp("NAT-1"), source_code="nl_tenderned", ted_ref="TED-1")
    nat_src = db.source_id(conn, "nl_tenderned")
    national.buyer_org_id = db.resolve_organisation(conn, national.buyer_name_raw, "FR", src_id=nat_src)
    nat_id, _ = db.upsert_opportunity(conn, national, "hash-nat-1", nat_src)
    conn.commit()
    got = client.get(f"/v1/tenders/{nat_id}").json()
    assert got["sameNotice"] and got["estimatedValue"]["amount"] == 750000.0
    _suppress(conn, native_id="TED-1")
    got = client.get(f"/v1/tenders/{nat_id}").json()
    assert got["sameNotice"] == [] and got["estimatedValue"] is None


# ------------------------------------------------------------ organisations

def test_a_suppressed_organisation_is_named_withheld_on_its_notices_and_has_no_page(client, conn):
    oid = _put(conn, "N-1", buyer="Sole Trader Jan Kowalski", title="Repair of vehicles")
    _put(conn, "N-2", buyer="Ministry of Defence")
    org = conn.execute("SELECT buyer_org_id FROM opportunity WHERE id = %s", (oid,)).fetchone()["buyer_org_id"]
    _suppress(conn, kind="organisation", organisation=org)

    tender = client.get(f"/v1/tenders/{oid}").json()
    assert tender["buyerName"] == WITHHELD and tender["buyerId"] is None and tender["buyerSlug"] is None
    assert "Kowalski" not in client.get(f"/v1/tenders/{oid}").text
    listed = {t["noticeId"]: t for t in client.get(
        "/v1/tenders", params={"status": "all", "scope": "all"}).json()["items"]}
    assert listed["N-1"]["buyerName"] == WITHHELD and listed["N-2"]["buyerName"] == "Ministry of Defence"
    # the name is not searchable either
    assert _notice_ids(client, q="Kowalski") == []
    # the older API and its archive
    opp = client.get(f"/v1/opportunities/{oid}").json()
    assert opp["buyer"]["name"] == WITHHELD and opp["buyer"]["organisation_id"] is None
    snap = client.get(f"/v1/opportunities/{oid}/versions").json()["versions"][0]["snapshot"]
    assert snap["buyer_name_raw"] == WITHHELD
    # the buyer's own page, list, slugs and profile
    assert client.get(f"/v1/buyers/{org}").status_code == 410
    assert client.get(f"/v1/buyers/{org}/profile").status_code == 410
    assert [b["name"] for b in client.get("/v1/buyers").json()["items"]] == ["Ministry of Defence"]
    assert all(not s["slug"].startswith(f"{org}-") for s in client.get("/v1/buyers/slugs").json())
    assert client.get("/v1/organisations/resolve",
                      params={"name": "Sole Trader Jan Kowalski", "country": "FR"}).json()["match"] is None


def test_a_notice_collected_later_for_a_suppressed_organisation_is_withheld(client, conn):
    first = _put(conn, "N-1", buyer="Sole Trader Jan Kowalski")
    org = conn.execute("SELECT buyer_org_id FROM opportunity WHERE id = %s", (first,)).fetchone()["buyer_org_id"]
    _suppress(conn, kind="organisation", organisation=org)
    later = _put(conn, "N-2", buyer="Sole Trader Jan Kowalski")
    assert client.get(f"/v1/tenders/{later}").json()["buyerName"] == WITHHELD


# ------------------------------------------------------------------ funding

def test_a_suppressed_call_leaves_the_funding_lists_and_is_410(client, conn):
    for native in ("keep", "gone"):
        call = Call(programme_code="HORIZON", native_id=native, title=f"Call {native}",
                    topic_code=f"HORIZON-{native}", deadline_at=NOW + timedelta(days=20),
                    status="open", regime="defence")
        db.upsert_call(conn, call, f"hash-{native}", db.source_id(conn, "eu_portal"))
    conn.commit()
    gone_id = conn.execute("SELECT id FROM call WHERE native_id = 'gone'").fetchone()["id"]
    _suppress(conn, kind="document", source="HORIZON", native_id="gone")

    assert [c["title"] for c in client.get("/v1/funding", params={"status": "all"}).json()["items"]] == ["Call keep"]
    assert all(not s["slug"].startswith(f"{gone_id}-") for s in client.get("/v1/funding/slugs").json())
    assert client.get(f"/v1/funding/{gone_id}").status_code == 410
    assert client.get(f"/v1/calls/{gone_id}").status_code == 410
    assert [c["native_id"] for c in client.get("/v1/calls", params={"status": "all"}).json()] == ["keep"]
    # a re-collected call stays removed
    call = Call(programme_code="HORIZON", native_id="gone", title="Call gone, edited",
                topic_code="HORIZON-gone", deadline_at=NOW + timedelta(days=21),
                status="open", regime="defence")
    db.upsert_call(conn, call, "hash-gone-2", db.source_id(conn, "eu_portal"))
    conn.commit()
    assert client.get(f"/v1/funding/{gone_id}").status_code == 410


# ------------------------------------------------------------------ accounts

def test_an_account_shortlist_and_dashboard_do_not_serve_a_suppressed_notice(conn):
    from dgate import accounts

    gone = _put(conn, "GONE")
    keep = _put(conn, "KEEP")
    _suppress(conn, native_id="GONE")
    found = accounts._tenders_by_id(conn, [gone, keep])
    assert set(found) == {str(keep)}
    # nobody can add it to a shortlist now
    with pytest.raises(accounts.AccountError) as err:
        accounts._check_ref(conn, "tender", str(gone))
    assert err.value.status == 404
    assert accounts._check_ref(conn, "tender", str(keep)) == str(keep)


# ------------------------------------------------------------ tools and tables

def test_the_cli_is_a_dry_run_until_yes_and_the_tables_refuse_delete(conn, capsys):
    oid = _put(conn, "GONE")        # the `conn` fixture points DGATE_DSN at this database
    base = ["add", "--kind", "notice", "--source", "ted", "--native-id", "GONE", "--reason", "personal_data",
            "--requested-at", "2026-10-15", "--decided-by", "Owner"]
    assert suppress.main(base) == 0
    assert "dry run" in capsys.readouterr().out
    assert conn.execute("SELECT count(*) AS n FROM suppression").fetchone()["n"] == 0
    assert suppress.main(base + ["--yes"]) == 0
    assert "flags 1 serving row" in capsys.readouterr().out
    assert conn.execute("SELECT suppressed FROM opportunity WHERE id = %s", (oid,)).fetchone()["suppressed"]
    # the same subject twice is refused, not duplicated
    assert suppress.main(base + ["--yes"]) == 1
    assert suppress.main(["list"]) == 0
    assert "ted/GONE" in capsys.readouterr().out

    with pytest.raises(psycopg.errors.RaiseException):
        conn.execute("DELETE FROM suppression")
    conn.rollback()

    assert data_request.main(["add", "--kind", "erasure", "--received-at", "2026-10-14", "--yes"]) == 0
    assert data_request.main(["add", "--kind", "erasure", "--received-at", "2026-10-14"]) == 0
    assert conn.execute("SELECT count(*) AS n FROM data_request").fetchone()["n"] == 1
    assert data_request.main(["close", "1", "--status", "closed", "--note", "answered", "--yes"]) == 0
    row = conn.execute("SELECT status, closed_at, handler_note FROM data_request").fetchone()
    assert row["status"] == "closed" and row["closed_at"] and row["handler_note"] == "answered"
    assert data_request.main(["close", "1", "--status", "refused", "--yes"]) == 1   # already closed
    with pytest.raises(psycopg.errors.RaiseException):
        conn.execute("DELETE FROM data_request")
    conn.rollback()


def test_the_public_roles_cannot_read_what_the_owner_typed(conn):
    for role in ("dgate_api", "dgate_app"):
        for table in ("suppression", "data_request"):
            got = conn.execute("SELECT has_table_privilege(%s, %s, 'SELECT') AS ok",
                               (role, table)).fetchone()["ok"]
            assert got is False, (role, table)
