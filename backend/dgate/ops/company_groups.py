"""Company groups of the supplier map, from a curated parent list with a source (WP-96, A2.1).

    python -m dgate.ops.company_groups          # report: the companies each group's list covers, nothing written
    python -m dgate.ops.company_groups --yes    # write `company_group_member`

A group (Rheinmetall, Leonardo, Saab, PGZ) is a parent company and its subsidiaries: separate legal entities, never
merged. Nothing infers a group: each entry below names the parent, the source a person can check, and the names of
the companies it covers (patterns on the name key, `resolution.names.key_of`; a bare parent name only in its home
country, so an unrelated "Leonardo S.L." in Spain is not taken). Every row written carries the method `curated_group`,
the entry's confidence and the pattern that matched. Display layer only: emptying the table undoes everything; the
supplier map reads it for "Part of the ... group" and `/suppliers?group=`.

Only contract winners are looked at (an award row). Idempotent: rows no entry produces any more are deleted (this
table only).
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
from dataclasses import dataclass

from .. import db
from ..config import settings
from ..resolution.names import key_of

log = logging.getLogger("company_groups")

METHOD = "curated_group"


@dataclass(frozen=True)
class CompanyGroup:
    key: str
    name: str
    source: str              # where a person checks the list
    home: str                # the parent's country: a bare parent name is matched there only
    bare: re.Pattern[str]    # the parent's own name key
    members: re.Pattern[str]  # the subsidiaries' name keys, any country
    confidence: float = 0.90


GROUPS: tuple[CompanyGroup, ...] = (
    CompanyGroup(
        "rheinmetall", "Rheinmetall", "Rheinmetall AG, annual report: list of shareholdings "
        "(https://www.rheinmetall.com/en/investor-relations)", "DE",
        re.compile(r"^rheinmetall$"),
        # every company that carries the parent's name, with or without a space (RheinmetallMAN)
        re.compile(r"^rheinmetall\s?\w")),
    CompanyGroup(
        "leonardo", "Leonardo", "Leonardo S.p.A., integrated annual report: consolidated companies "
        "(https://www.leonardo.com/en/investors)", "IT",
        re.compile(r"^leonardo(?: s ?p ?a| societa per azion[ei]| spa[ _]?\d+)?$"),
        # WP-104: and PZL-Swidnik (Leonardo's Polish helicopter maker, with or without the parent's name) and Leonardo
        # Belgium, both in the consolidated companies
        re.compile(r"^(?:leonardo )?pzl swidnik\b|^leonardo (?:germany|uk|drs|hispania|polska|poland|us|usa|australia"
                   r"|helicopters|electronics|global solutions|logistics|international|mw|belgium)\b")),
    CompanyGroup(
        "saab", "Saab", "Saab AB, annual report: group companies (https://www.saab.com/investors)", "SE",
        re.compile(r"^saab(?: aktiebolag)?$"),
        re.compile(r"^saab (?:dynamics|kockums|finland|danmark|denmark|norge|norway|deutschland|germany|uk|australia"
                   r"|bofors|barracuda|technologies|grintek|defen[cs]e|south africa|inc|nederland|polska|seaeye)\b")),
    CompanyGroup(
        "pgz", "Polska Grupa Zbrojeniowa (PGZ)", "Polska Grupa Zbrojeniowa S.A.: companies of the PGZ group "
        "(https://www.pgzsa.pl)", "PL",
        re.compile(r"^(?:polska grupa zbrojeniowa|pgz)$"),
        re.compile(r"^(?:polska grupa zbrojeniowa\b|pgz \w|mesko\b|huta stalowa wola\b|jelcz\b|rosomak\b|belma\b"
                   r"|zaklady mechaniczne (?:tarnow|bumar)|fabryka broni lucznik|niewiadow\b|maskpol\b|pit radwar\b"
                   r"|nitro chem\b|dezamet\b|wojskowe zaklady (?:lotnicze|uzbrojenia|elektroniczne|lacznosci"
                   r"|inzynieryjne|motoryzacyjne)\b|stocznia wojenna\b)")),
)


def group_of(name: str, country: str) -> tuple[CompanyGroup, str] | None:
    """The group a company of `country` called `name` is listed under, and the pattern that matched, or None."""
    k = key_of(name or "")[0]
    if not k:
        return None
    for g in GROUPS:
        if country == g.home and g.bare.search(k):
            return g, g.bare.pattern
        if g.members.search(k):
            return g, g.members.pattern
    return None


def wanted(conn) -> dict[int, tuple[str, float, str]]:
    """org id -> (group key, confidence, evidence) for every live contract winner an entry covers."""
    out: dict[int, tuple[str, float, str]] = {}
    for r in conn.execute(
            """SELECT DISTINCT g.id, COALESCE(g.display_name, g.canonical_name) AS name, g.country
                 FROM award a JOIN organisation raw ON raw.id = a.organisation_id
                 JOIN organisation g ON g.id = COALESCE(raw.merged_into, raw.id)
                WHERE a.superseded_at IS NULL AND a.excluded_reason IS NULL AND NOT g.suppressed
                  AND g.individual_reason IS NULL""").fetchall():
        hit = group_of(r["name"], (r["country"] or "").strip())
        if hit:
            g, pattern = hit
            out[r["id"]] = (g.key, g.confidence, f"{g.source}; name matched {pattern}")
    return out


def run(conn, *, write: bool = False, out=print) -> dict[str, int]:
    want = wanted(conn)
    stored = {r["org_id"]: (r["group_key"], float(r["confidence"]), r["evidence"]) for r in conn.execute(
        "SELECT org_id, group_key, confidence, evidence FROM company_group_member").fetchall()}
    changed = [o for o, v in want.items() if stored.get(o) != v]
    gone = [o for o in stored if o not in want]
    names = {r["id"]: r["n"] for r in conn.execute(
        "SELECT id, COALESCE(display_name, canonical_name) AS n FROM organisation WHERE id = ANY(%s)",
        (list(want),)).fetchall()} if want else {}
    for g in GROUPS:
        ids = sorted(o for o, v in want.items() if v[0] == g.key)
        out(f"{g.key}: {len(ids)} companies  ({g.source})")
        for o in ids[:40]:
            out(f"    {o:>8}  {names.get(o, '')}")
    if write:
        for o in changed:
            key, conf, evidence = want[o]
            conn.execute(
                """INSERT INTO company_group_member (org_id, group_key, method, confidence, evidence)
                   VALUES (%s, %s, %s, %s, %s)
                   ON CONFLICT (org_id) DO UPDATE SET group_key = EXCLUDED.group_key, method = EXCLUDED.method,
                       confidence = EXCLUDED.confidence, evidence = EXCLUDED.evidence""",
                (o, key, METHOD, conf, evidence[:500]))
        if gone:
            conn.execute("DELETE FROM company_group_member WHERE org_id = ANY(%s)", (gone,))
        conn.commit()
    else:
        conn.rollback()
    counts = {"members": len(want), "written": len(changed) if write else 0, "removed": len(gone) if write else 0,
              "to_write": len(changed), "to_remove": len(gone)}
    out(f"{counts}" + ("" if write else "  (dry run: nothing written, add --yes)"))
    return counts


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--yes", action="store_true", help="write; without it nothing changes")
    a = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    with db.connect(settings().dsn) as conn:
        run(conn, write=a.yes)
    return 0


if __name__ == "__main__":
    sys.exit(main())
