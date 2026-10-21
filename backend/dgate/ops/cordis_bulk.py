"""Fill the missing or doubled CORDIS amounts from the official bulk exports (WP-70).

    python -m dgate.ops.cordis_bulk --dir /bulk              # the three CSV packages, downloaded by a person (robots.txt)
    python -m dgate.ops.cordis_bulk --dir /bulk              # dry run on the packages already in /bulk
    python -m dgate.ops.cordis_bulk --dir /bulk --yes        # write, then rebuild the directory table

The SPARQL copy that loaded CORDIS (`dgate.sources.cordis`) holds no payment for some roles and summed a few
twice; the monthly CSV packages (`cordis-{fp7,h2020,HORIZON}projects-csv.zip`, `organization.csv`) state
`ecContribution` per participant. This module reads those files, streamed, and touches only:

  * an amount that is NULL because the service stated no payment (`no_payment_stated`) -> the bulk
    `ecContribution` (a third party at 0 there stays `linked_third_party`, as the loader stores it)
  * an amount that is an exact multiple (x2, x3 ...) of the bulk figure -> the bulk figure (the WP-43 defect)

Countries are compared, not written: no stored organisation can be without one (see COUNTRY_SQL).

Any other stated amount that differs from the bulk is counted (`differs_kept`) and left alone: the column is the
gross payment of the open data (migration 0086), the bulk is a later copy, and which figure is right is not
decided here. Every project touched is settled again with the loader's own rules
(`networks.settle_amounts`), so a fill can end or start an `exceeds_project_total` withholding exactly as a reload
would, with one exception: a fill that would push a project over its EU contribution, and so withhold amounts shown
today, is dropped for that project (`fill_over_total`). Matching: our project by CORDIS record number
(`project.csv` maps the grant number to it; a unique grant number is the fallback), the participant by the PIC of its organisation (or of the organisation it was merged
into) and the role (an organisation met twice in one project is one row, coordinator first, amounts added, as the
loader does). Nothing is inserted or deleted; a participation the bulk has and we do not is only counted.

Only the columns in `READ` are taken from the files: no name, address, contact form or any contact person.
"""

from __future__ import annotations

import argparse
import csv
import io
import logging
import re
import shutil
import sys
import time
import zipfile
from collections import Counter, defaultdict
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx

from .. import db, networks
from ..config import settings
from ..sources import USER_AGENT, cordis

log = logging.getLogger("cordis_bulk")

HUB = "https://data.europa.eu/api/hub/search/datasets/"
DATASETS = ("cordisfp7projects", "cordish2020projects", "cordis-eu-research-projects-under-horizon-europe-2021-2027")
FILE_URL = re.compile(r"^https://cordis\.europa\.eu/data/cordis-(fp7|h2020|HORIZON)projects-csv\.zip$")
MIN_FREE = 3 * 1024 ** 3          # bytes left on the disk after a download, or it is not started
READ = ("projectID", "organisationID", "role", "ecContribution", "country")
CENT = 0.011
BATCH = 5000

csv.field_size_limit(1 << 26)     # project.csv carries long objectives in quoted fields


# ------------------------------------------------------------------ finding and fetching the files

def bulk_urls(client: httpx.Client) -> list[str]:
    """The current CSV package of each framework, as data.europa.eu lists the distributions."""
    urls: list[str] = []
    for i, ds in enumerate(DATASETS):
        if i:
            time.sleep(1.0)
        r = client.get(HUB + ds)
        r.raise_for_status()
        for d in r.json()["result"].get("distributions", []):
            for u in (d.get("download_url") or []) + (d.get("access_url") or []):
                if FILE_URL.match(u) and u not in urls:
                    urls.append(u)
    return urls


def download(url: str, dest_dir: Path, client: httpx.Client, *, free=shutil.disk_usage) -> Path:
    """Stream one package to `dest_dir`; a file already there is used as it is. Refused when the disk would be left
    with less than MIN_FREE."""
    dest = dest_dir / url.rsplit("/", 1)[1]
    if dest.exists() and dest.stat().st_size > 0:
        log.info("%s already present, not downloading again", dest.name)
        return dest
    dest_dir.mkdir(parents=True, exist_ok=True)
    partial = dest.with_suffix(".partial")
    with client.stream("GET", url) as r:
        r.raise_for_status()
        size = int(r.headers.get("content-length") or 0)
        left = free(dest_dir).free - size
        if left < MIN_FREE:
            raise RuntimeError(f"{dest.name}: {size} bytes would leave {left} free, under {MIN_FREE}")
        with partial.open("wb") as fh:
            for block in r.iter_bytes(1 << 20):
                fh.write(block)
    partial.replace(dest)
    log.info("downloaded %s (%.0f MB)", dest.name, dest.stat().st_size / 1e6)
    return dest


# ------------------------------------------------------------------ reading them

def _csv(z: zipfile.ZipFile, name: str) -> Iterator[dict[str, str | None]]:
    with z.open(name) as fh:
        yield from csv.DictReader(io.TextIOWrapper(fh, encoding="utf-8-sig", newline=""), delimiter=";")


def read_package(path: Path, c: Counter) -> Iterator[dict[str, Any]]:
    """One dict per participant row of `organization.csv`, with the project's record number from `project.csv`:
    keys rcn, ga, pic, role, ec, country and nothing else. A row that does not parse (a stray quote shifts the
    columns) is counted and skipped."""
    with zipfile.ZipFile(path) as z:
        rcn_of = {r["id"]: (r.get("rcn") or "").strip() for r in _csv(z, "project.csv") if r.get("id")}
        for r in _csv(z, "organization.csv"):
            row = {k: (r.get(k) or "").strip() for k in READ}
            role = cordis._ROLE.get(row["role"])
            pic = row["organisationID"]
            ec = row["ecContribution"]
            if not role or not re.fullmatch(r"\d{9}", pic) or not row["projectID"] or (
                    ec and not re.fullmatch(r"-?\d+(\.\d+)?", ec)):
                c["bulk_rows_skipped"] += 1
                continue
            c["bulk_rows"] += 1
            yield {"rcn": rcn_of.get(row["projectID"]) or None, "ga": row["projectID"], "pic": pic, "role": role,
                   "ec": round(float(ec), 2) if ec else None, "country": cordis.country_of(row["country"])}


# ------------------------------------------------------------------ the rules

def corrected(role: str, amount: float | None, note: str | None, bulk_role: str | None,
              bulk_ec: float | None) -> tuple[float | None, str | None, str | None]:
    """(amount, note, reason) for one participation, from what the open data said (`networks.source_view`) and the
    bulk row it matched. reason None = unchanged; 'filled', 'multiple' = changed (a 'filled' third party at 0 changes
    only its note); 'differs_kept', 'role_differs' = the bulk disagrees and nothing is changed."""
    if bulk_role is None or bulk_ec is None:
        return amount, note, None
    if bulk_role != role:
        return amount, note, "role_differs"
    if amount is None:
        if note == "no_payment_stated":
            if role == "third_party" and bulk_ec == 0:
                return None, "linked_third_party", "filled"
            return bulk_ec, None, "filled"
        return amount, note, None
    if abs(amount - bulk_ec) < CENT:
        return amount, note, None
    k = round(amount / bulk_ec) if bulk_ec > 0 else 0
    if k >= 2 and abs(amount - k * bulk_ec) < CENT * k:
        return bulk_ec, None, "multiple"
    return amount, note, "differs_kept"


# ------------------------------------------------------------------ against the database

_RANK = " ".join(f"WHEN '{r}' THEN {n}" for r, n in networks.ROLE_RANK.items())

MATCH_SQL = f"""
WITH b AS (
  SELECT project_id, pic, (array_agg(role ORDER BY CASE role {_RANK} ELSE 9 END))[1] AS role, sum(ec) AS ec
    FROM cordis_bulk GROUP BY project_id, pic)
SELECT pa.id, pa.project_id, pa.role, pa.contribution, pa.contribution_note, pa.contribution_stated,
       p.eu_contribution AS fund, COALESCE(pr.code, 'none') AS prog, b.pic AS b_pic, b.role AS b_role, b.ec AS b_ec
  FROM participation pa
  JOIN project p ON p.id = pa.project_id
  JOIN source s ON s.id = p.source_id AND s.code = 'cordis'
  LEFT JOIN programme pr ON pr.id = p.programme_id
  JOIN organisation o ON o.id = pa.organisation_id
  LEFT JOIN organisation_merged_live ml ON ml.id = o.id
  LEFT JOIN organisation lo ON lo.id = ml.live_id
  LEFT JOIN b ON b.project_id = pa.project_id AND b.pic = COALESCE(o.eu_pic, lo.eu_pic)
 WHERE pa.active
 ORDER BY pa.project_id, pa.id"""

# Counted, never written: `organisation.country` is NOT NULL (migration 0001) and the loader skips a CORDIS
# organisation without one, so no stored participant has an empty country. What the bulk can show is a country
# that differs from ours; `cordis.seat_country` and WP-43 decided those from the record, and they stay.
COUNTRY_SQL = """
WITH c AS (SELECT pic, min(country) AS cc FROM cordis_bulk WHERE country IS NOT NULL
            GROUP BY pic HAVING count(DISTINCT country) = 1)
SELECT count(*) FILTER (WHERE x.country IS DISTINCT FROM c.cc) AS country_differs_kept,
       count(*) FILTER (WHERE btrim(x.country) = '') AS country_empty
  FROM organisation o JOIN c ON c.pic = o.eu_pic
  LEFT JOIN organisation_merged_live ml ON ml.id = o.id
  JOIN organisation x ON x.id = COALESCE(ml.live_id, o.id)"""


def stage(conn, paths: list[Path], c: Counter) -> None:
    """The bulk rows of our projects into a session temp table (nothing permanent is created)."""
    by_rcn: dict[str, int] = {}
    by_ga: dict[str, list[int]] = defaultdict(list)
    for r in conn.execute("""SELECT p.id, p.cordis_id, p.ga_number FROM project p
                               JOIN source s ON s.id = p.source_id AND s.code = 'cordis'""").fetchall():
        if r["cordis_id"]:
            by_rcn[r["cordis_id"]] = r["id"]
        if r["ga_number"]:
            by_ga[r["ga_number"]].append(r["id"])
    conn.execute("DROP TABLE IF EXISTS cordis_bulk")
    conn.execute("CREATE TEMP TABLE cordis_bulk (project_id BIGINT NOT NULL, pic TEXT NOT NULL, "
                 "role TEXT NOT NULL, ec NUMERIC(14,2), country CHAR(2))")
    with conn.cursor().copy("COPY cordis_bulk (project_id, pic, role, ec, country) FROM STDIN") as cp:
        for path in paths:
            for row in read_package(path, c):
                pid = by_rcn.get(row["rcn"] or "")
                if pid is None and len(by_ga.get(row["ga"], ())) == 1:
                    pid = by_ga[row["ga"]][0]
                    c["project_by_grant_number"] += 1
                if pid is None:
                    c["bulk_rows_no_project"] += 1
                    continue
                cp.write_row((pid, row["pic"], row["role"], row["ec"], row["country"]))
    conn.execute("ANALYZE cordis_bulk")


def _groups(conn) -> Iterator[list[dict[str, Any]]]:
    """The active CORDIS participations with their bulk match, one list per project, from a named cursor (386,000
    rows are not held at once)."""
    with conn.cursor(name="cordis_bulk") as cur:
        cur.itersize = 20000
        cur.execute(MATCH_SQL)
        group: list[dict[str, Any]] = []
        for row in cur:
            if group and row["project_id"] != group[0]["project_id"]:
                yield group
                group = []
            group.append(row)
        if group:
            yield group


def plan(conn) -> tuple[list[tuple[Any, ...]], Counter, Counter]:
    """(participation updates, counters, counts by programme and reason)."""
    c: Counter = Counter()
    by_prog: Counter = Counter()
    updates: list[tuple[Any, ...]] = []
    matched_keys: set[tuple[int, str]] = set()
    for group in _groups(conn):
        keys = Counter(r["b_pic"] for r in group if r["b_pic"])
        members, reasons = [], []
        for r in group:
            c["participations"] += 1
            amount, note = networks.source_view(r["role"], r["contribution"], r["contribution_note"],
                                                r["contribution_stated"])
            reason = None
            if r["b_pic"]:
                matched_keys.add((r["project_id"], r["b_pic"]))
                if keys[r["b_pic"]] > 1:          # two of our rows on one PIC: not guessed between
                    reason = "ambiguous"
                else:
                    c["matched"] += 1
                    amount, note, reason = corrected(
                        r["role"], amount, note, r["b_role"], None if r["b_ec"] is None else float(r["b_ec"]))
            members.append((r["role"], amount, note))
            reasons.append(reason)
        fund = None if group[0]["fund"] is None else float(group[0]["fund"])
        settled = networks.settle_amounts(members, fund)
        if (any(s[1] == "exceeds_project_total" for s in settled)
                and not any(r["contribution_note"] == "exceeds_project_total" for r in group)
                and "filled" in reasons):
            # A fill would push a project over its EU contribution and withhold amounts shown today (measured: an
            # ERC-like grant whose open data gives the whole total to one host, the bulk a share to another). The
            # stated amounts stay as they are and the fills of this project are dropped.
            for i, (r, reason) in enumerate(zip(group, reasons, strict=True)):
                if reason == "filled":
                    members[i] = (r["role"], *networks.source_view(
                        r["role"], r["contribution"], r["contribution_note"], r["contribution_stated"]))
                    reasons[i] = "fill_over_total"
            settled = networks.settle_amounts(members, fund)
        for r, reason, new in zip(group, reasons, settled, strict=True):
            old = (None if r["contribution"] is None else float(r["contribution"]), r["contribution_note"],
                   None if r["contribution_stated"] is None else float(r["contribution_stated"]))
            if reason in ("differs_kept", "role_differs", "ambiguous", "fill_over_total"):
                c[reason] += 1
                by_prog[(r["prog"], reason)] += 1
            if old != new:
                why = reason if reason in ("filled", "multiple") else "resettled"
                c["changed"] += 1
                c[why] += 1
                c[f"to_{new[1] or 'plain'}"] += 1
                by_prog[(r["prog"], why)] += 1
                updates.append((*new, r["id"]))
    c["bulk_participants"] = conn.execute(
        "SELECT count(*) AS n FROM (SELECT DISTINCT project_id, pic FROM cordis_bulk) x").fetchone()["n"]
    c["bulk_participants_not_stored"] = c["bulk_participants"] - len(matched_keys)
    c.update({k: v for k, v in conn.execute(COUNTRY_SQL).fetchone().items()})
    return updates, c, by_prog


def run(conn, paths: list[Path], *, apply: bool = False, out=print) -> Counter:
    c: Counter = Counter()
    stage(conn, paths, c)
    updates, c2, by_prog = plan(conn)
    c.update(c2)
    if apply:
        conn.commit()                              # the temp table lives on to the end of the session
        with conn.cursor() as cur:
            for i in range(0, len(updates), BATCH):
                cur.executemany("""UPDATE participation SET contribution = %s, contribution_note = %s,
                                          contribution_stated = %s WHERE id = %s""", updates[i:i + BATCH])
                conn.commit()
        c["directory_rows"] = networks.refresh_organisation_network(conn)["organisations"]
    else:
        conn.rollback()
    for (prog, why), n in sorted(by_prog.items()):
        out(f"  {prog:8} {why:14} {n:>8}")
    out(f"{'written' if apply else 'would change'}: {dict(sorted(c.items()))}"
        + ("" if apply else "  (dry run; add --yes)"))
    return c


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--dir", type=Path, default=Path("/tmp/cordis_bulk"), help="where the packages are (or go)")
    p.add_argument("--download", action="store_true", help="find the current packages and fetch the missing ones")
    p.add_argument("--yes", action="store_true", help="write; without it nothing changes")
    a = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if a.download:
        # cordis.europa.eu/robots.txt disallows /data/, where the packages are: the project honours robots.txt, so
        # this tool never fetches them. A person downloads the three CSV zips in a browser and puts them in --dir.
        log.error("--download is disabled: robots.txt disallows /data/ on cordis.europa.eu; download the "
                  "cordis-*projects-csv.zip packages in a browser and put them in %s", a.dir)
        return 2
    paths = sorted(a.dir.glob("cordis-*projects-csv.zip"))
    if not paths:
        log.error("no cordis-*projects-csv.zip in %s (use --download)", a.dir)
        return 2
    with db.connect(settings().dsn) as conn:
        run(conn, paths, apply=a.yes)
    return 0


if __name__ == "__main__":
    sys.exit(main())
