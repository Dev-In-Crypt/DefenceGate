"""Recover the EDF consortium members the quote check dropped or the model left out (WP-41, N6).

    python -m dgate.ops.edf_recover               # report what would be added, write nothing
    python -m dgate.ops.edf_recover --yes         # add them

The first reading of the 283 factsheets dropped a member whose name wraps over two lines or whose
spaces the PDF layout collapsed ("ATHINA - EREVNITIKO KENTRO ... PLIROFORIAS" in ARCHER, "ISD LYSEIS
..." in EMISSARY and MARTE), and counted it in `project_factsheet.dropped` without keeping the name.
The text of each factsheet is still in the raw store. For every stored factsheet this tool reads that
text again, takes the rows of the consortium table that the stored participants lack
(`edf_factsheets.recover_missing`: the table is read by rule, a row is taken only if its letters are in
the document), adds them to `project_factsheet.facts`, resolves them like any participant and adds the
participations. It asks no model and no website; it reads only the private raw store.

Idempotent: a recovered participant is in the stored facts afterwards, so a second run finds nothing.
It also gives the organisations made from a glued name ("UNIVERSITEDULUXEMBOURG") the spelling the plain text
prints. What it cannot recover (a sheet whose table the rule cannot read, where the stored counts say rows are
missing) is listed, with the cost of a model re-read.
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections import Counter
from typing import Any
from urllib.parse import parse_qs, urlsplit

from psycopg.types.json import Jsonb

from .. import db, networks
from ..config import settings
from ..rawstore import build_store
from ..sources import edf_factsheets as edf

log = logging.getLogger("edf_recover")

COST_PER_SHEET_USD = 0.0015      # 0.42 USD for 284 sheets at the configured prices (docs/sources/edf_factsheets.md)


def landed_texts(conn, store) -> dict[tuple[str, str], dict[str, Any]]:
    """{(url, sha256): landed payload} for every EDF factsheet in the raw store."""
    out = {}
    src = conn.execute("SELECT id FROM source WHERE code = %s", (edf.SOURCE_CODE,)).fetchone()
    if not src:
        return out
    for r in conn.execute("SELECT storage_key FROM raw_ingest WHERE source_id = %s", (src["id"],)).fetchall():
        try:
            payload = store.get(r["storage_key"])
        except Exception as exc:                      # a missing object is reported, not fatal
            log.warning("raw store: %s: %s", r["storage_key"], exc)
            continue
        if isinstance(payload, dict) and payload.get("url") and payload.get("sha256"):
            out[(payload["url"], payload["sha256"])] = payload
    return out


def recategorise(conn, *, apply: bool = False) -> int:
    """Give each EDF project the category its topic code names by the rule of `edf.category_of` (the last
    category token): EDF-2023-DA-DS-AIRDEF-EATMI was filed under DS, not AIRDEF. Returns how many differ."""
    changed = 0
    for r in conn.execute(
            """SELECT p.id, p.topic_code, p.category FROM project p JOIN source s ON s.id = p.source_id
                WHERE s.code = %s AND p.topic_code IS NOT NULL""", (edf.SOURCE_CODE,)).fetchall():
        new = edf.category_of(r["topic_code"].split("-"))
        if new and new != r["category"]:
            changed += 1
            if apply:
                conn.execute("UPDATE project SET category = %s WHERE id = %s", (new, r["id"]))
    if apply:
        conn.commit()
    return changed


def _respace_names(conn, participants: list[dict[str, Any]], text: edf.FactsheetText, *, apply: bool) -> int:
    """A name the model copied glued from the layout ("UNIVERSITEDULUXEMBOURG") became the display name of an
    organisation the resolver made for it. Where the plain text prints it with its spaces on one line, that
    organisation's display name is replaced, if it is still the glued one and the organisation holds no PIC (a
    PIC organisation's name is CORDIS's). The key stays: the aliases keep finding the row, and `ops/org_dedupe`
    merges it with its spaced twin where there is one."""
    n = 0
    for p in participants:
        name = p.get("name") or ""
        better = edf.printed_spelling(name, text.plain)
        if better == name or not p.get("country_iso"):
            continue
        if apply:
            cur = conn.execute(
                """UPDATE organisation SET display_name = %s
                    WHERE display_name = %s AND country = %s AND eu_pic IS NULL AND merged_into IS NULL""",
                (better[:300], name[:300], p["country_iso"]))
            n += cur.rowcount
        else:
            n += conn.execute(
                """SELECT count(*) AS n FROM organisation WHERE display_name = %s AND country = %s
                    AND eu_pic IS NULL AND merged_into IS NULL""", (name[:300], p["country_iso"])).fetchone()["n"]
    return n


def run(conn, store, *, apply: bool = False, out=print) -> Counter:
    c: Counter = Counter()
    c["projects_recategorised"] = recategorise(conn, apply=apply)
    texts = landed_texts(conn, store)
    src_id = conn.execute("SELECT id FROM source WHERE code = %s", (edf.SOURCE_CODE,)).fetchone()["id"]
    unreadable: list[tuple[str, int]] = []
    for pf in conn.execute(
            """SELECT f.url, f.sha256, f.facts, f.dropped, f.pages, p.call_year, p.acronym, p.native_id
                 FROM project_factsheet f JOIN project p ON p.id = f.project_id ORDER BY f.url""").fetchall():
        c["factsheets"] += 1
        payload = texts.get((pf["url"], pf["sha256"]))
        if payload is None:
            c["factsheets_without_text"] += 1
            continue
        text = edf.FactsheetText(pf["sha256"], pf["pages"], payload["layout"], payload["plain"])
        facts = pf["facts"]
        c["names_respaced"] += _respace_names(conn, facts.get("participants") or [], text, apply=apply)
        found = edf.recover_missing(facts.get("participants") or [], text)
        lost = int((pf["dropped"] or {}).get("not_in_text", 0))
        recovered_before = int((pf["dropped"] or {}).get("recovered", 0))
        if found:
            c["factsheets_with_recovery"] += 1
            c["participants_recovered"] += len(found)
            out(f"{pf['acronym'] or pf['url'][-40:]:<22} +{len(found)}: " + "; ".join(f"{p['name'][:60]} ({p['country_iso']})" for p in found))
        short = lost - recovered_before - len(found)
        if short > 0:
            unreadable.append((pf["acronym"] or pf["url"][-40:], short))
        if not (found and apply):
            continue
        facts = {**facts, "participants": [*facts["participants"], *found]}
        filename = parse_qs(urlsplit(pf["url"]).query).get("filename", [payload.get("filename", "")])[0]
        info = edf.parse_filename(filename, pf["call_year"])
        if info is None or info.key != pf["native_id"]:
            c["factsheets_name_unparsed"] += 1          # never write a project under a key the loader did not give it
            continue
        counter: Counter = Counter()
        project_id = networks.load_edf_factsheet(conn, src_id, info, pf["url"], text, facts, counter)
        dropped = {**(pf["dropped"] or {}), "recovered": recovered_before + len(found)}
        conn.execute("UPDATE project_factsheet SET facts = %s, dropped = %s WHERE url = %s",
                     (Jsonb(facts), Jsonb(dropped), pf["url"]))
        c["participations_new"] += counter["participations_new"]
        c["organisations_new"] += counter["organisations_new"]
        conn.commit()
        del project_id
    c["names_not_recoverable_by_rule"] = sum(n for _, n in unreadable)
    c["sheets_to_reread_with_the_model"] = len(unreadable)
    if unreadable:
        out("not recoverable by rule (the stored counts say more was lost than the table gives back): "
            + ", ".join(f"{a} ({n})" for a, n in unreadable))
        out(f"a model re-read of those {len(unreadable)} sheets would cost about USD {len(unreadable) * COST_PER_SHEET_USD:.3f}")
    if apply:
        c["directory_rows"] = networks.refresh_organisation_network(conn)["organisations"]
    out(f"{dict(c)} ({'written' if apply else 'dry run, nothing is written'})")
    return c


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--yes", action="store_true", help="write; without it nothing changes")
    a = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    with db.connect(settings().dsn) as conn:
        run(conn, build_store(), apply=a.yes)
    return 0


if __name__ == "__main__":
    sys.exit(main())
