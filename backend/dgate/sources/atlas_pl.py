"""Atlas Przetargow open dataset: the Polish historical backfill.

Record:    https://zenodo.org/records/19634050
DOI:       10.5281/zenodo.19634050
Licence:   CC BY 4.0. Attribution is mandatory and is recorded on the `source`
           row, not just in this file, so it travels with the data.
Format:    Parquet, one file per year.

Why this exists at all: the live connector (`ezamowienia.py`) can only see what
the bulletin is serving now. Everything published before we started collecting
is reachable only through a bulk dataset, and it is the part a competitor
starting after us cannot obtain. That makes this a one-off worth doing
carefully rather than a job worth scheduling.

What the dataset actually is, checked against the file rather than its README,
which understates it considerably:

  - 43 columns, not the 16 the README documents. The undocumented ones matter:
    `source` separates BZP from TED rows, `nip_normalized` is a cleaned tax
    identifier, `notice_url` is the citable link, `bzp_number`/`ted_number`
    cross-reference the original notices.
  - 669,983 rows for 2024. Of those, 571,869 are BZP and 98,114 are TED.
  - 4,218 rows carry a CPV code in division 35 -- 0.63%. The defence slice of a
    national bulletin is small, which is the whole premise of the product.
  - `order_type` is entirely null despite being documented, and `is_duplicate`
    is False on every row, so neither can be relied on.
  - `currency` is mostly PLN with 181,062 nulls and a tail of junk ('Kry',
    'net', 'bru'). Values are only trusted where the currency parses.

Two of the four defence signals are simply absent here. The dataset carries no
legal basis and no security-clearance text, so only CPV and the buyer list can
fire. Classification on this source is therefore weaker than on the live ones
by construction, not by accident, and `docs/sources/atlas_pl.md` says so.

Personal data: contractor identity can name a natural person. The publisher
pseudonymises those already -- '[Osoba fizyczna]' for the name, a stable
SHA-256 for the identifier -- but a stable hash still singles out one person
across every contract they ever won, which is exactly the reasoning that put
e-Zamowienia's `userId` on the same list. Both fields are dropped in
`strip_personal_data`, before anything is stored.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Iterator

import httpx

from . import USER_AGENT, request_with_retry

log = logging.getLogger(__name__)

SOURCE_CODE = "pl_atlas"

ZENODO_RECORD = "19634050"
ZENODO_API = f"https://zenodo.org/api/records/{ZENODO_RECORD}"
DOI = "10.5281/zenodo.19634050"

# CC BY 4.0 requires attribution in a form the licensor specifies. This is the
# human-readable citation the dataset's own README asks for, with the DOI
# appended so the exact version is recoverable. It is written to
# `source.attribution` by migration 0004.
ATTRIBUTION = (
    "Atlas Przetargow (2026). Polish Public Tenders Dataset (BZP + TED), "
    "version 2026.Q2. DOI 10.5281/zenodo.19634050. Licensed CC BY 4.0."
)
LICENCE = "CC BY 4.0 (Creative Commons Attribution 4.0 International)"

# The dataset ships CSV and Parquet of the same content. Parquet is a sixth of
# the size and typed, so the CSV copies are never downloaded.
YEAR_FILES = {2024: "tenders_2024.parquet", 2025: "tenders_2025.parquet"}

# Only the columns that are mapped or classified on. Parquet is columnar, so
# not asking for the other 27 is a real saving on a 76 MB file, and it makes a
# schema change visible as a missing column rather than as silently absent data.
COLUMNS = [
    "id",
    "source",
    "notice_type",
    "title",
    "buyer",
    "buyer_nip",
    "nip_normalized",
    "city",
    "province",
    "cpv_code",
    "date",
    "submitting_offers_date",
    "estimated_value",
    "currency",
    "notice_url",
    "notice_number",
    "bzp_number",
    "ted_number",
    "organization_country",
    "contractor_name",
    "contractor_national_id",
]


def dataset_files() -> dict[str, dict[str, Any]]:
    """The record's files, from Zenodo, keyed by filename.

    Asked rather than assumed so that a new version of the dataset shows up as
    a changed file list instead of a download that quietly fetches last
    quarter's data.
    """
    def send() -> httpx.Response:
        r = httpx.get(ZENODO_API, headers={"User-Agent": USER_AGENT},
                      follow_redirects=True, timeout=60.0)
        r.raise_for_status()
        return r

    record = request_with_retry(send, what="Zenodo record").json()
    return {f["key"]: f for f in record.get("files", [])}


def download(filename: str, dest: Path, *, chunk: int = 1 << 20) -> Path:
    """Fetch one dataset file, streaming it to disk.

    Streamed because these run to hundreds of megabytes and a backfill host is
    not guaranteed to have that much memory to spare. Written to a partial name
    and renamed at the end, so an interrupted download cannot be mistaken for a
    complete one on the next run.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 0:
        log.info("%s already present (%.0f MB), not downloading again",
                 dest.name, dest.stat().st_size / 1e6)
        return dest

    url = f"{ZENODO_API}/files/{filename}/content"
    partial = dest.with_suffix(dest.suffix + ".partial")

    def fetch() -> None:
        written = 0
        with httpx.stream("GET", url, headers={"User-Agent": USER_AGENT},
                          follow_redirects=True, timeout=120.0) as r:
            r.raise_for_status()
            with partial.open("wb") as fh:
                for block in r.iter_bytes(chunk):
                    fh.write(block)
                    written += len(block)
        log.info("downloaded %s (%.0f MB)", filename, written / 1e6)

    request_with_retry(lambda: fetch(), what=f"download {filename}")
    partial.replace(dest)
    return dest


def read_rows(path: Path, *, batch_size: int = 2000,
              columns: list[str] | None = None) -> Iterator[dict[str, Any]]:
    """Yield one dict per notice, a batch at a time.

    Batched rather than read whole: 669,983 rows of 43 columns does not want to
    be a single in-memory table on a machine that is also running Postgres.
    """
    import pyarrow.parquet as pq

    wanted = columns or COLUMNS
    handle = pq.ParquetFile(path)
    available = set(handle.schema_arrow.names)
    missing = [c for c in wanted if c not in available]
    if missing:
        # Loud, because the alternative is a backfill that silently maps
        # nothing into half its fields.
        raise ValueError(
            f"{path.name} is missing expected columns {missing}; "
            f"the dataset schema has changed and the mapping must be rechecked")

    for batch in handle.iter_batches(batch_size=batch_size, columns=wanted):
        for row in batch.to_pylist():
            yield row


def row_count(path: Path) -> int:
    """Rows in a dataset file, from the footer rather than by reading it."""
    import pyarrow.parquet as pq

    return pq.ParquetFile(path).metadata.num_rows


def content_hash(record: dict[str, Any]) -> str:
    """Stable hash for change detection, shared with every other source."""
    from .ted import content_hash as _hash

    return _hash(record)
