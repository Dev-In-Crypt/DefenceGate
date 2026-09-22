"""The daily runs write bundles, against a real Postgres.

An ordinary day was about 25,000 one-object writes; object storage bills per
write. The daily runs now land one bundle per checkpoint, and every index row
still resolves to its own payload.
"""

from __future__ import annotations

import pytest

from dgate import config, pipeline
from dgate.rawstore import build_store
from dgate.sources import ted

pytestmark = pytest.mark.integration


def _notice(number: str) -> dict:
    return {
        "notice-identifier": [number], "publication-number": [number],
        "notice-title": {"eng": "Supply"}, "buyer-name": {"eng": ["Ministry of Defence"]},
        "buyer-country": ["DEU"], "official-language": ["eng"],
        "dispatch-date": ["2026-09-20+02:00"], "classification-cpv": ["35700000"],
        "legal-basis": ["32009L0081"],
    }


@pytest.fixture
def fs_store(tmp_path, monkeypatch):
    monkeypatch.setenv("DGATE_RAW_BACKEND", "fs")
    monkeypatch.setenv("DGATE_RAW_DIR", str(tmp_path / "raw"))
    config.reset_cache()
    yield tmp_path / "raw"
    config.reset_cache()


def test_a_daily_run_writes_bundles_and_every_row_resolves(conn, fs_store, monkeypatch):
    notices = [_notice(f"{i:05d}-2026") for i in range(250)]
    monkeypatch.setattr(ted, "fetch_window", lambda days_back=2: iter(notices))
    pipeline.run_ted(days=2)

    rows = conn.execute("SELECT storage_key, content_hash FROM raw_ingest ORDER BY id").fetchall()
    assert len(rows) == 250
    assert all("#" in r["storage_key"] for r in rows)
    objects = list(fs_store.rglob("*"))
    files = [p for p in objects if p.is_file()]
    assert len(files) <= 4                      # one per checkpoint of 100, not 250
    store = build_store()
    assert all(ted.content_hash(store.get(r["storage_key"])) == r["content_hash"]
               for r in rows)
