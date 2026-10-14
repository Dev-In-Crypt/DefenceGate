"""Work package WP-6 (fixes of the second verification round, 14 October 2026), unit level.

PLACSP archives streamed to disk under their own ceiling, the legacy BOAMP deadline and
the end-of-diffusion rule, the worker's new jobs, the run guard that keeps a catch-up and a
slot from starting one job twice, and the read-side borrowing of procedure and deadline.
"""

from __future__ import annotations

import io
import zipfile
from datetime import date, datetime, timedelta, timezone

import httpx
import pytest

from dgate import sources, worker
from dgate.normalise import from_boamp
from dgate.sources import ResponseTooLarge, placsp

from .test_placsp import _entry, _page

# ----------------------------------------------------- PLACSP archive on disk


def _archive_bytes(padding: int = 0) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as zf:
        zf.writestr("a.atom", _page(_entry("EXP-1", "PUB", "2026-09-05T10:00:00+02:00"), None))
        if padding:
            zf.writestr("pad.bin", b"x" * padding)
    return buf.getvalue()


def _default_client_answers(monkeypatch, body: bytes) -> None:
    """`fetch_archive` builds its own client when none is given: have it talk to `body`."""
    original = httpx.Client
    transport = httpx.MockTransport(lambda request: httpx.Response(200, content=body))
    monkeypatch.setattr(httpx, "Client", lambda **kw: original(transport=transport, **kw))


def test_an_archive_larger_than_the_response_ceiling_is_read_from_disk(monkeypatch):
    """The September 2026 archive is over the 256 MiB every other connector keeps. The
    global ceiling is not raised: the archive has its own, and a body goes to a file."""
    body = _archive_bytes(padding=50_000)
    monkeypatch.setattr(sources, "MAX_BODY_BYTES", 10_000)
    assert len(body) > sources.MAX_BODY_BYTES
    _default_client_answers(monkeypatch, body)
    opps = list(placsp.fetch_archive("https://example.test/x_202609.zip", placsp.MAIN))
    assert [o.native_id for o in opps] == ["EXP-1"]


def test_an_archive_past_its_own_ceiling_is_refused_while_it_is_read(monkeypatch):
    monkeypatch.setattr(placsp, "MAX_ARCHIVE_BYTES", 10_000)
    _default_client_answers(monkeypatch, _archive_bytes(padding=50_000))
    with pytest.raises(ResponseTooLarge):
        list(placsp.fetch_archive("https://example.test/x_202609.zip", placsp.MAIN))


def test_the_archive_download_leaves_no_file_behind(monkeypatch, tmp_path):
    monkeypatch.setattr("tempfile.tempdir", str(tmp_path))
    _default_client_answers(monkeypatch, _archive_bytes(padding=1_000))
    list(placsp.fetch_archive("https://example.test/x_202609.zip", placsp.MAIN))
    assert list(tmp_path.iterdir()) == []


# ------------------------------------------------- BOAMP legacy deadline


def _legacy(received: str | None, *, diffusion_end: str | None = None,
            column: str | None = None, nature: str = "APPEL_OFFRE") -> dict:
    body = {"CONDITION_DELAI": {"RECEPT_OFFRES": received}} if received else {}
    return {"idweb": "21-35386", "objet": "Marche", "nomacheteur": "Acheteur",
            "dateparution": "2021-03-18", "datelimitereponse": column,
            "datefindiffusion": diffusion_end, "perimetre": "DIRECTIVE-24",
            "nature": nature, "donnees": body}


def test_a_legacy_notice_states_its_deadline_in_the_conditions_of_delay():
    o = from_boamp(_legacy("2021-04-16T16:00:00+01:00"))
    assert o.deadline_at == datetime(2021, 4, 16, 14, 0, tzinfo=timezone.utc)   # 16:00 Paris, CEST
    assert o.deadline_at.utcoffset() == timedelta(hours=2)


def test_the_fixed_offset_the_converter_writes_is_not_read_as_information():
    """22 of 22 sampled legacy notices carry +01:00, July dates included."""
    winter = from_boamp(_legacy("2021-01-20T12:00:00+01:00"))
    assert winter.deadline_at == datetime(2021, 1, 20, 11, 0, tzinfo=timezone.utc)
    summer = from_boamp(_legacy("2021-07-09T12:00:00+01:00"))
    assert summer.deadline_at == datetime(2021, 7, 9, 10, 0, tzinfo=timezone.utc)


def test_an_offset_the_notice_states_itself_is_kept():
    o = from_boamp(_legacy("2021-07-09T12:00:00+03:00"))
    assert o.deadline_at == datetime(2021, 7, 9, 9, 0, tzinfo=timezone.utc)


def test_the_column_still_wins_over_the_body_for_a_notice_that_has_both():
    o = from_boamp(_legacy("2021-04-16T16:00:00+01:00", column="2021-04-20T10:00:00+00:00"))
    assert o.deadline_at == datetime(2021, 4, 20, 10, 0, tzinfo=timezone.utc)


def test_a_call_with_no_deadline_that_is_no_longer_published_is_not_open():
    over = from_boamp(_legacy(None, diffusion_end="2026-04-01"))
    assert (over.deadline_at, over.status) == (None, "unknown")
    still = from_boamp(_legacy(None, diffusion_end=(date.today() + timedelta(days=5)).isoformat()))
    assert still.status == "open"
    with_deadline = from_boamp(_legacy("2021-04-16T16:00:00+01:00", diffusion_end="2021-04-16"))
    assert with_deadline.status == "open"          # its own deadline decides, as before


# --------------------------------------------------------- worker: guards


def test_a_job_that_is_already_running_is_not_started_again(monkeypatch):
    """The catch-up runs beside the scheduler now: a slot that fires meanwhile must not
    start the same job a second time in this process."""
    monkeypatch.setattr(worker, "ping", lambda *a, **k: True)
    monkeypatch.setattr(worker, "notify", lambda *a, **k: None)
    inner = []

    def outer() -> None:
        inner.append(worker.run_job("ted_daily", lambda: inner.append("ran twice")))

    first = worker.run_job("ted_daily", outer)
    assert first.status == "success"
    assert len(inner) == 1 and inner[0].detail == "already running"
    # and the guard is released afterwards
    again = worker.run_job("ted_daily", lambda: None)
    assert again.detail == ""


def test_the_new_jobs_are_scheduled_and_listed():
    ids = {job.id for job in worker.build_scheduler().get_jobs()}
    assert {"link_twins_daily", "requalify_weekly"} <= ids
    lines = worker.describe_schedule()
    assert any(line.startswith("link_twins") for line in lines)
    assert any(line.startswith("requalify") for line in lines)


def test_the_scheduler_is_not_held_up_by_the_catch_up(monkeypatch):
    """Start-up work goes to a thread (internal audit M8): `main` reaches the scheduler
    while a catch-up is still running."""
    import threading

    release = threading.Event()
    started = threading.Event()

    def slow_catch_up():
        started.set()
        release.wait(5)
        return []

    monkeypatch.setattr(worker, "catch_up", slow_catch_up)
    monkeypatch.setattr(worker, "catch_up_backups", lambda: [])
    monkeypatch.setattr(worker, "start_backfill_thread", lambda: [])
    thread = worker.start_catch_up_thread(True)
    assert started.wait(5) and thread.is_alive()      # returned while the catch-up runs
    release.set()
    thread.join(5)
    assert not thread.is_alive()


# ------------------------------------------------- the borrowed read side


def test_a_deadline_far_ahead_is_flagged_and_a_twins_deadline_replaces_a_typo():
    from dgate import tenders

    now = datetime.now(timezone.utc)
    row = {"id": 1, "native_id": "N-1", "buyer_name_raw": "Buyer", "title_original": "Title",
           "status": "open", "deadline_at": now + timedelta(days=400),
           "published_at": date.today(), "value_amount": None, "procedure_type": None,
           "cpv_codes": [], "source_code": "es_placsp", "source_name": "PLACSP",
           "source_licence": "", "source_attribution": "", "source_url": None}
    plain = tenders.to_tender(row, {}, {}, [], None)
    assert "deadline-more-than-1y" in plain["anomalies"] and plain["deadlineFrom"] is None

    twin = {"procedure": "restricted", "deadline": now + timedelta(days=30)}
    borrowed = tenders.to_tender(row, {}, {}, [], None, twin_extra=twin)
    assert borrowed["deadline"] == twin["deadline"] and borrowed["deadlineFrom"] == "ted_twin"
    assert borrowed["procedure"] == "Restricted procedure"
    assert borrowed["procedureFrom"] == "ted_twin"
    assert "deadline-differs-from-ted-twin" in borrowed["anomalies"]
    assert "deadline-more-than-1y" not in borrowed["anomalies"]

    near = {"procedure": None, "deadline": row["deadline_at"] + timedelta(days=10)}
    same = tenders.to_tender(row, {}, {}, [], None, twin_extra=near)
    assert same["deadline"] == row["deadline_at"] and same["deadlineFrom"] is None


def test_a_notice_with_no_publication_date_says_so():
    from dgate import tenders

    row = {"id": 1, "native_id": "N-1", "buyer_name_raw": "Buyer", "title_original": "Title",
           "status": "awarded", "deadline_at": None, "published_at": None, "value_amount": None,
           "procedure_type": None, "cpv_codes": [], "source_code": "es_placsp",
           "source_name": "PLACSP", "source_licence": "", "source_attribution": "",
           "source_url": None}
    served = tenders.to_tender(row, {}, {}, [], None)
    assert served["publishedAt"] is None and served["publishedKnown"] is False


# ------------------------------------------------- repair_reversions (O1)


def test_a_remapped_version_is_never_marked_as_a_reread():
    """A re-mapping writes a version with the raw hash of the one it corrects: by hash it
    is "the same content read again", and would be hidden from clients."""
    from dgate.ops.repair_reversions import plan_repair

    payload = {"published_at": "2026-09-01"}
    rows = [{"id": 1, "version": 1, "raw_hash": "a", "payload": payload},
            {"id": 2, "version": 2, "raw_hash": "a", "payload": payload, "is_remap": True}]
    assert plan_repair(1, "N-1", rows).notes == []
    rows[1]["is_remap"] = False
    assert [kind for _, kind, _ in plan_repair(1, "N-1", rows).notes] == ["reread"]
