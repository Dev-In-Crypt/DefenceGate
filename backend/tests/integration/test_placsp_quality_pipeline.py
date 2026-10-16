"""PLACSP against a real Postgres: a notice keeps its publication date through its
amendments, a held version is corrected and not mistaken for history, the live walk's
mark is kept only when the walk was complete, and the replay is safe to repeat.

Entries are the stripped real ones of `fixtures/placsp_live_entries.atom`. The defence
one, `2026/ETSAE0921/00001111E`, is the only one the classifier archives: it states
Directive 2009/81/EC.
"""

from __future__ import annotations

import dataclasses
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from dgate import config, db, pipeline
from dgate.sources import placsp

pytestmark = pytest.mark.integration

XML = (Path(__file__).resolve().parents[1] / "fixtures" / "placsp_live_entries.atom"
       ).read_text(encoding="utf-8")
NATIVE = "2026/ETSAE0921/00001111E"

# The same notice, amended on 12 October: a later deadline, and the call republished
# the same day, which is a second IssueDate on the same notice.
AMENDED = (XML
           .replace("<updated>2026-10-10T14:41:55.557+02:00</updated>",
                    "<updated>2026-10-12T09:15:00.000+02:00</updated>")
           .replace("<cbc:EndDate>2026-11-16</cbc:EndDate>", "<cbc:EndDate>2026-11-20</cbc:EndDate>")
           .replace("<cbc:IssueDate>2026-10-10</cbc:IssueDate>",
                    "<cbc:IssueDate>2026-10-10</cbc:IssueDate>"
                    "</cac-place-ext:AdditionalPublicationDocumentReference>"
                    "<cac-place-ext:AdditionalPublicationDocumentReference>"
                    "<cbc:IssueDate>2026-10-12</cbc:IssueDate>"))


def _opps(xml: str) -> list:
    return placsp.parse_feed(xml.encode("utf-8"))[0]


def _defence(xml: str):
    return next(o for o in _opps(xml) if o.native_id == NATIVE)


@pytest.fixture()
def raw_store(tmp_path, monkeypatch):
    monkeypatch.setenv("DGATE_RAW_BACKEND", "fs")
    monkeypatch.setenv("DGATE_RAW_DIR", str(tmp_path / "raw"))
    config.reset_cache()
    yield
    config.reset_cache()


def _versions(conn) -> list[dict]:
    return conn.execute(
        """SELECT v.version, v.changed_fields, v.payload,
                  array_remove(array_agg(n.kind), NULL) AS kinds
             FROM opportunity_version v
             LEFT JOIN opportunity_version_note n ON n.opportunity_version_id = v.id
            GROUP BY v.id ORDER BY v.version""").fetchall()


def _walk_reason(seen: dict | None = None, **kw):
    """A live walk's verdict callable, carrying the dict its generator would share."""
    seen = {} if seen is None else seen
    seen.update(kw)

    def reason():
        return None

    reason.seen = seen
    return reason


# ------------------------------------------------- the original finding

def test_an_amended_notice_keeps_its_original_publication_date_across_versions(conn, raw_store):
    pipeline._ingest_placsp([_defence(XML)], "es_placsp")
    pipeline._ingest_placsp([_defence(AMENDED)], "es_placsp")

    versions = _versions(conn)
    assert [v["version"] for v in versions] == [1, 2]
    assert [v["payload"]["published_at"] for v in versions] == ["2026-10-10", "2026-10-10"]
    assert versions[1]["changed_fields"] == ["deadline_at"]     # only what the buyer changed
    assert versions[1]["kinds"] == [], "a real amendment is not annotated as remapped"
    row = conn.execute("SELECT * FROM opportunity").fetchone()
    assert row["published_at"] == date(2026, 10, 10)
    assert row["deadline_at"].date() == date(2026, 11, 20)
    # the corrected fields land on the serving row
    assert float(row["value_amount"]) == 3020897.01 and row["value_currency"] == "EUR"
    assert row["procedure_type"] == "Negociado con publicidad"
    assert row["legal_basis"] == "32009L0081" and row["sig_legal_basis"] is True


def test_the_update_time_is_kept_in_the_archive_but_does_not_make_a_version(conn, raw_store):
    """Only the Atom time moved: nothing the notice says has changed."""
    only_time = XML.replace("<updated>2026-10-10T14:41:55.557+02:00</updated>",
                            "<updated>2026-10-12T09:15:00.000+02:00</updated>")
    pipeline._ingest_placsp([_defence(XML)], "es_placsp")
    pipeline._ingest_placsp([_defence(only_time)], "es_placsp")
    assert len(_versions(conn)) == 1


# --------------------------------------------- ordering by the update time

def test_an_older_entry_arriving_later_is_history_not_a_change(conn, raw_store):
    """With the publication date the same on every version, the update time is what
    tells a re-read of an earlier amendment from a new one."""
    pipeline._ingest_placsp([_defence(AMENDED)], "es_placsp")
    pipeline._ingest_placsp([_defence(XML)], "es_placsp")

    assert len(_versions(conn)) == 1
    row = conn.execute("SELECT deadline_at FROM opportunity").fetchone()
    assert row["deadline_at"].date() == date(2026, 11, 20)      # the amended one stands


def _held_before_the_correction(conn, xml: str):
    """What the archive held before this change: the Atom time as the publication
    date, the budget with VAT, a bare procedure code, no legal basis."""
    new = _defence(xml)
    old = dataclasses.replace(
        new, published_at=new.source_updated_at.date(), source_updated_at=None,
        value_amount=3655285.38, procedure_type="4", legal_basis=None, is_defence=True,
        sig_cpv=True)
    old_hash = "held-before-the-correction"
    db.upsert_opportunity(conn, old, old_hash, db.source_id(conn, "es_placsp"))
    conn.commit()


def test_a_held_version_is_corrected_by_the_entry_that_produced_it(conn, raw_store):
    _held_before_the_correction(conn, XML)
    held = conn.execute("SELECT published_at FROM opportunity").fetchone()["published_at"]
    assert held == date(2026, 10, 10)

    pipeline._ingest_placsp([_defence(XML)], "es_placsp")

    versions = _versions(conn)
    assert len(versions) == 2
    assert set(versions[1]["changed_fields"]) == {"value_amount", "procedure_type", "legal_basis"}
    # Added on 13 October 2026 (review): the entry's update stamp is the held version's
    # day and only mapper-owned fields moved, so this is our correction, not an amendment.
    assert versions[1]["kinds"] == ["remapped"]
    row = conn.execute("SELECT value_amount, legal_basis FROM opportunity").fetchone()
    assert float(row["value_amount"]) == 3020897.01 and row["legal_basis"] == "32009L0081"


def test_a_live_walk_reading_a_held_entry_again_after_the_mapper_changed_is_remapped(
        conn, raw_store):
    """The held record carries the stamp already (written by the mapper before a later
    correction of a field): the same entry read again, a field the mapper owns moved."""
    new = _defence(XML)
    held = dataclasses.replace(new, value_amount=3655285.38, procedure_type="4",
                               is_defence=True, sig_cpv=True)
    db.upsert_opportunity(conn, held, "held-under-the-previous-mapper",
                          db.source_id(conn, "es_placsp"))
    conn.commit()

    pipeline._ingest_placsp([_defence(XML)], "es_placsp-live")

    versions = _versions(conn)
    assert len(versions) == 2
    assert set(versions[1]["changed_fields"]) == {"value_amount", "procedure_type"}
    assert versions[1]["kinds"] == ["remapped"]


def test_a_status_the_mapper_now_reads_differently_is_remapped_a_status_the_source_moved_is_not(
        conn, raw_store):
    """PRE (anuncio previo) was `open` and is `forthcoming`: same code, same stamp."""
    src = db.source_id(conn, "es_placsp")
    stamp = datetime(2026, 10, 5, 12, 0, tzinfo=timezone.utc)
    base = _defence(XML)
    held = dataclasses.replace(base, status="open", status_native="PRE", source_updated_at=stamp,
                               is_defence=True, sig_cpv=True)
    opp_id, _ = db.upsert_opportunity(conn, held, "pre-open", src)
    now = dataclasses.replace(held, status="forthcoming")
    assert db.upsert_opportunity(conn, now, "pre-forthcoming", src) == (opp_id, "changed")
    # the publisher moved it: a new code and a later stamp
    awarded = dataclasses.replace(held, status="awarded", status_native="ADJ",
                                  source_updated_at=stamp + timedelta(days=3))
    assert db.upsert_opportunity(conn, awarded, "adj", src) == (opp_id, "changed")
    conn.commit()
    kinds = [v["kinds"] for v in _versions(conn)]
    assert kinds == [[], ["remapped"], []]


def test_a_change_of_the_value_under_a_newer_stamp_is_the_publishers_and_not_remapped(
        conn, raw_store):
    new = _defence(XML)
    held = dataclasses.replace(
        new, value_amount=3655285.38, is_defence=True, sig_cpv=True,
        source_updated_at=new.source_updated_at - timedelta(days=2))
    db.upsert_opportunity(conn, held, "held-two-days-earlier", db.source_id(conn, "es_placsp"))
    conn.commit()

    pipeline._ingest_placsp([_defence(XML)], "es_placsp-live")

    versions = _versions(conn)
    assert [v["changed_fields"] for v in versions[1:]] == [["value_amount"]]
    assert versions[1]["kinds"] == []


def test_a_corrected_publication_date_is_a_version_not_history(conn, raw_store):
    """The held record says 12 October (the amendment's feed time); the notice was
    published on the 10th. 10 < 12, which the old comparison read as late history."""
    _held_before_the_correction(conn, AMENDED)
    assert conn.execute("SELECT published_at FROM opportunity").fetchone()[
        "published_at"] == date(2026, 10, 12)

    pipeline._ingest_placsp([_defence(AMENDED)], "es_placsp")

    versions = _versions(conn)
    assert len(versions) == 2 and "published_at" in versions[1]["changed_fields"]
    assert versions[1]["kinds"] == ["remapped"]       # added 13 October 2026 (review)
    assert conn.execute("SELECT published_at FROM opportunity").fetchone()[
        "published_at"] == date(2026, 10, 10)


def test_an_earlier_entry_does_not_overwrite_a_later_held_version(conn, raw_store):
    """The replay reads a month oldest first, but an archive of an earlier month can
    still arrive after a later one is held (written before this change)."""
    _held_before_the_correction(conn, AMENDED)         # held: updated 12 October
    pipeline._ingest_placsp([_defence(XML)], "es_placsp")     # entry updated 10 October
    assert len(_versions(conn)) == 1
    assert conn.execute("SELECT deadline_at FROM opportunity").fetchone()[
        "deadline_at"].date() == date(2026, 11, 20)    # the held, later one stands


# --------------------------------------------------- the live walk's mark

def _marks(conn) -> list:
    return [r["newest_entry_at"] for r in conn.execute(
        "SELECT newest_entry_at FROM ingest_run ORDER BY id")]


def test_a_complete_walk_leaves_its_newest_entry_for_the_next_one(conn, raw_store):
    newest = datetime(2026, 10, 11, 17, 54, 50, tzinfo=timezone.utc)
    pipeline._ingest_placsp([_defence(XML)], "es_placsp-live", placsp.MAIN,
                            stale_reason=_walk_reason(newest=newest))
    assert _marks(conn) == [newest]

    seen: dict = {}
    pipeline._ingest_placsp([], "es_placsp-live", placsp.MAIN, stale_reason=_walk_reason(seen))
    assert seen["until"] == newest        # handed to the walk before it started


def test_a_capped_walk_leaves_no_mark_so_the_older_one_stands(conn, raw_store):
    first = datetime(2026, 10, 5, 18, 4, tzinfo=timezone.utc)
    later = datetime(2026, 10, 12, 4, 0, tzinfo=timezone.utc)
    pipeline._ingest_placsp([], "es_placsp-live", placsp.MAIN,
                            stale_reason=_walk_reason(newest=first))
    pipeline._ingest_placsp([], "es_placsp-live", placsp.MAIN,
                            stale_reason=_walk_reason(newest=later, capped=True))
    pipeline._ingest_placsp([], "es_placsp-live", placsp.MAIN,
                            stale_reason=_walk_reason(newest=later, refused="https://x.test/a"))
    assert _marks(conn) == [first, None, None]

    seen: dict = {}
    pipeline._ingest_placsp([], "es_placsp-live", placsp.MAIN, stale_reason=_walk_reason(seen))
    assert seen["until"] == first


def test_each_dataset_has_its_own_mark(conn, raw_store):
    newest = datetime(2026, 10, 11, 17, 0, tzinfo=timezone.utc)
    pipeline._ingest_placsp([], "es_placsp-live", placsp.MAIN,
                            stale_reason=_walk_reason(newest=newest))
    seen: dict = {}
    pipeline._ingest_placsp([], "es_placsp_agg-live", placsp.AGGREGATED,
                            stale_reason=_walk_reason(seen))
    assert seen["until"] is None


# ------------------------------------------------------------- the replay

UTC = timezone.utc
AFTERNOON = datetime(2026, 10, 12, 14, 0, tzinfo=UTC)


@pytest.fixture()
def archive(monkeypatch):
    """`fetch_archive` replaced by the fixture's entries, remembering what it was asked."""
    asked: list[tuple[str, datetime | None]] = []

    def fake(url, dataset=placsp.MAIN, *, since=None, **kw):
        asked.append((url.rsplit("/", 1)[-1], since))
        return iter(_opps(XML))

    monkeypatch.setattr(placsp, "fetch_archive", fake)
    return asked


def _replay(**kw):
    kw.setdefault("now", AFTERNOON)
    return pipeline.run_placsp_replay((2026, 10), (2026, 10), [placsp.MAIN], pause=0,
                                      sleep=lambda s: None, **kw)


def test_the_replay_archives_corrected_records_without_a_collection_run(
        conn, raw_store, archive):
    _held_before_the_correction(conn, XML)

    result = _replay()

    assert result["done"] == ["es_placsp-202610"] and not result["failed"]
    assert archive[0][0].endswith("_202610.zip")
    assert archive[0][1] == datetime(2026, 10, 1, tzinfo=UTC)    # the month's own entries only
    assert len(_versions(conn)) == 2
    # added 13 October 2026 (review); and, since WP-20, `history`: a replay is a load of the past
    assert sorted(_versions(conn)[1]["kinds"]) == ["history", "remapped"]
    # not a collection run: catch-up must not read it as today's ingest
    assert conn.execute("SELECT count(*) n FROM ingest_run").fetchone()["n"] == 0
    # only the record it archived was landed, not the two civil entries beside it
    assert conn.execute("SELECT count(*) n FROM raw_ingest").fetchone()["n"] == 1


def test_a_finished_month_is_marked_and_skipped_the_current_one_is_not(conn, raw_store, archive):
    _replay()
    assert conn.execute("SELECT count(*) n FROM backfill_day").fetchone()["n"] == 0

    november = datetime(2026, 11, 15, 14, 0, tzinfo=UTC)
    assert _replay(now=november)["done"] == ["es_placsp-202610"]
    marks = conn.execute("SELECT source_code, day FROM backfill_day").fetchall()
    assert [(m["source_code"], m["day"]) for m in marks] == [("es_placsp-replay", date(2026, 10, 1))]

    again = _replay(now=november)
    assert again["skipped"] == ["es_placsp-202610"] and again["done"] == []
    assert len(archive) == 2            # the second run asked for nothing
    assert _replay(now=november, resume=False)["done"] == ["es_placsp-202610"]


def test_repeating_a_replay_changes_nothing(conn, raw_store, archive):
    _replay()
    before = len(_versions(conn))
    _replay()
    assert len(_versions(conn)) == before == 1


def test_the_replay_does_not_start_inside_the_live_walks_window(conn, raw_store, archive):
    inside = datetime(2026, 10, 12, 6, 45, tzinfo=UTC)
    result = _replay(now=inside)
    assert result["stopped"] == ["es_placsp-202610"] and archive == []


def test_the_replay_does_not_start_while_a_live_run_is_in_progress(conn, raw_store, archive):
    conn.execute("INSERT INTO ingest_run (source_id, status) VALUES (%s, 'running')",
                 (db.source_id(conn, "es_placsp_agg"),))
    conn.commit()
    assert _replay()["stopped"] == ["es_placsp-202610"] and archive == []


def test_a_month_that_fails_is_reported_and_the_next_is_still_read(conn, raw_store, monkeypatch):
    calls: list[str] = []

    def fake(url, dataset=placsp.MAIN, *, since=None, **kw):
        calls.append(url.rsplit("/", 1)[-1])
        if url.endswith("_202609.zip"):
            raise RuntimeError("archive is not there")
        return iter(_opps(XML))

    monkeypatch.setattr(placsp, "fetch_archive", fake)
    result = pipeline.run_placsp_replay((2026, 9), (2026, 10), [placsp.MAIN], pause=0,
                                        sleep=lambda s: None, now=AFTERNOON)
    assert result["failed"] == ["es_placsp-202609"]
    assert result["done"] == ["es_placsp-202610"]
    assert conn.execute("SELECT count(*) n FROM backfill_day").fetchone()["n"] == 0
    assert calls == ["licitacionesPerfilesContratanteCompleto3_202609.zip",
                     "licitacionesPerfilesContratanteCompleto3_202610.zip"]


def test_a_rate_limit_ends_the_replay(conn, raw_store, monkeypatch):
    import httpx

    def fake(url, dataset=placsp.MAIN, *, since=None, **kw):
        request = httpx.Request("GET", url)
        raise httpx.HTTPStatusError("slow down", request=request,
                                    response=httpx.Response(429, request=request))

    monkeypatch.setattr(placsp, "fetch_archive", fake)
    result = pipeline.run_placsp_replay((2026, 9), (2026, 10), [placsp.MAIN], pause=0,
                                        sleep=lambda s: None, now=AFTERNOON)
    assert result["stopped"] == ["es_placsp-202609"] and result["done"] == []


def test_the_replay_waits_between_requests(conn, raw_store, archive):
    slept: list[float] = []
    pipeline.run_placsp_replay((2026, 10), (2026, 10), [placsp.MAIN], pause=1.0,
                               sleep=slept.append, now=AFTERNOON)
    assert slept == [1.0]
