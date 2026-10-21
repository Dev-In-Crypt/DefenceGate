"""Process the pending organisation merge candidates that a shared identifier proves (WP-72).

On 21 October 2026 164,827 candidate pairs were pending (QA audit, finding 1). Only one kind is
accepted here without a person: a pair found by a strong identifier, i.e. one organisation holds the
registration or tax number the notice states and the name the notice gives is filed under the other
(`resolve_organisation`, method `identifier`, confidence 0.97), and the stored confidence is at
least 0.97. Everything else stays `pending` for review: the 0.50 kinds say the identifier and the
name DISAGREE (`identifier_name_mismatch`, `same_name_different_identifier`), and a trigram or a
folded name is a resemblance, not a fact.

A pair, and the group it joins by shared members, is refused when anything contradicts it:

  * the two are already one organisation (an earlier merge)
  * different countries
  * two different registration numbers, VAT numbers or PICs anywhere in the group (bodies with
    different registration numbers are never merged: the owner's standing decision)
  * a row removed on request (suppressed) or marked as a natural person
  * a name that says one body acts for another ("per conto", "pour le compte", "im Auftrag" ...):
    the number is the agent's (`ACTING_FOR`)
  * either side is a public authority or a unit of one (`buyer_family.is_public_body`: the
    defence-buyer flag, `org_role` buyer, a public legal form, or a name of an administration or of
    a department, directorate, service ...): a regional government, a ministry or a city council
    files every department under one tax id, so the number proves one legal entity, not one buyer
    (WP-74: the run of 21 October 2026 merged 6,641 such rows and was undone by `ops.undo_merges`).
    With `--yes` such pairs are marked `rejected_public_units` and `ops.buyer_families` shows each
    connected set as one buyer under the parent body's name (rule `shared_tax_id`). Companies that
    share a VAT number, a registration number or a PIC are still merged.

The head of a group is the row with the most notices, then the one holding a PIC, then the
oldest. Each other row is merged with `db.merge_organisations`, which stores the method
(`identifier`) and the candidate's confidence on the absorbed row, re-points aliases and notices,
and deletes nothing (the alias keeps `prev_organisation_id`). The group's candidate rows are marked
`merged`. Public bodies split by office id (BAAINBw: 67 rows, each with its own Leitweg-ID) are NOT
merged: different identifiers. The buyer list shows them as one buyer through the buyer families
(`ops.buyer_families`, rule `baainbw`); the dry run reports how many such rows a family covers.

    python -m dgate.ops.accept_merge_candidates                  # dry run: counts and 30 sampled pairs
    python -m dgate.ops.accept_merge_candidates --yes --limit 500
"""

from __future__ import annotations

import argparse
import hashlib
import logging
import re
import sys
from collections import Counter, defaultdict
from typing import Any

from .. import db, networks
from ..buyer_family import is_public_body
from ..config import settings
from . import buyer_families

log = logging.getLogger("accept_merge_candidates")

DETECTED_BY = "ops.accept_merge_candidates"
STRONG_METHODS = ("identifier",)
MIN_CONFIDENCE = 0.97
IDENTIFIERS = ("reg", "vat", "pic")

# A body that procures for another states its own number beside the other's name ("commune de
# Villefontaine represented by SARA", "SUA Provincia di Cosenza per conto del Comune ..."): the number
# then proves the agent, not that the two names are one body. 2 of the 30 pairs read by hand on
# 21 October 2026; such pairs wait for a person. Names are stored lower-case and unaccented.
ACTING_FOR = re.compile(
    r"\b(?:per conto|pour (?:le )?compte|repres(?:ente|entee)? par|au nom d|on behalf|im auftrag"
    r"|w imieniu|por cuenta|en (?:nombre|representacion) de|c/o|mandatair"
    # Dutch "p.a." (per adres: care of; "p a ku leuven", "p a csg"), not the "s p a" of an Italian name
    r"|(?<!\bs )p a\b)", re.IGNORECASE)


def pending_by_method(conn) -> list[dict[str, Any]]:
    return [dict(r) for r in conn.execute(
        """SELECT match_method, round(confidence, 2) AS confidence, count(*) AS n
             FROM organisation_merge_candidate WHERE status = 'pending'
            GROUP BY 1, 2 ORDER BY n DESC""").fetchall()]


def strong_pairs(conn) -> list[dict[str, Any]]:
    """The pending candidates of a strong method, with both ends taken to their live row."""
    return [dict(r) for r in conn.execute(
        """SELECT c.id, c.match_method, c.confidence, c.evidence,
                  COALESCE(la.live_id, c.organisation_id) AS a,
                  COALESCE(lb.live_id, c.candidate_org_id) AS b
             FROM organisation_merge_candidate c
             LEFT JOIN organisation_merged_live la ON la.id = c.organisation_id
             LEFT JOIN organisation_merged_live lb ON lb.id = c.candidate_org_id
            WHERE c.status = 'pending' AND c.match_method = ANY(%s) AND c.confidence >= %s
            ORDER BY c.id""", (list(STRONG_METHODS), MIN_CONFIDENCE)).fetchall()]


def organisations(conn, ids: set[int]) -> dict[int, dict[str, Any]]:
    out: dict[int, dict[str, Any]] = {}
    chunk = sorted(ids)
    for n in range(0, len(chunk), 5000):
        part = chunk[n:n + 5000]
        for r in conn.execute(
                """SELECT g.id, g.country, g.canonical_name AS name, g.suppressed,
                          g.individual_reason IS NOT NULL AS person,
                          g.is_defence_buyer, g.org_role, g.legal_form,
                          NULLIF(btrim(g.national_reg_no), '') AS reg,
                          NULLIF(upper(regexp_replace(coalesce(g.vat_number, ''), '[^A-Za-z0-9]', '', 'g')), '') AS vat,
                          NULLIF(btrim(g.eu_pic), '') AS pic,
                          (SELECT count(*) FROM opportunity o WHERE o.buyer_org_id = g.id AND o.is_defence) AS notices
                     FROM organisation g WHERE g.id = ANY(%s)""", (part,)).fetchall():
            out[r["id"]] = dict(r)
    return out


def _pair_refusal(a: dict[str, Any] | None, b: dict[str, Any] | None) -> str | None:
    if a is None or b is None:
        return "unknown_organisation"
    if a["id"] == b["id"]:
        return "already_one"
    if a["country"] != b["country"]:
        return "different_countries"
    if a["suppressed"] or b["suppressed"]:
        return "suppressed"
    if a["person"] or b["person"]:
        return "natural_person"
    if ACTING_FOR.search(a["name"] or "") or ACTING_FOR.search(b["name"] or ""):
        return "acting_for_another_body"
    for k in IDENTIFIERS:
        if a[k] and b[k] and a[k] != b[k]:
            return f"different_{k}"
    if _public(a) or _public(b):
        return "public_body"
    return None


def _public(o: dict[str, Any]) -> bool:
    return is_public_body(o["name"], o["country"], legal_form=o.get("legal_form"),
                          org_role=o.get("org_role"), defence_buyer=bool(o.get("is_defence_buyer")))


def plan(pairs: list[dict[str, Any]], orgs: dict[int, dict[str, Any]]
         ) -> tuple[list[dict[str, Any]], Counter[str]]:
    """The groups to merge ({head, members, candidates, confidence}) and the refusals by reason."""
    refused: Counter[str] = Counter()
    parent: dict[int, int] = {}

    def find(x: int) -> int:
        while parent.setdefault(x, x) != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    kept: list[dict[str, Any]] = []
    for p in pairs:
        why = _pair_refusal(orgs.get(p["a"]), orgs.get(p["b"]))
        if why:
            refused[why] += 1
            continue
        kept.append(p)
        parent[find(p["a"])] = find(p["b"])
    by_root: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for p in kept:
        by_root[find(p["a"])].append(p)
    groups: list[dict[str, Any]] = []
    for cands in by_root.values():
        ids = sorted({i for p in cands for i in (p["a"], p["b"])})
        rows = [orgs[i] for i in ids]
        clash = next((k for k in IDENTIFIERS if len({r[k] for r in rows if r[k]}) > 1), None)
        if clash:
            refused[f"group_different_{clash}"] += len(cands)
            continue
        head = min(rows, key=lambda r: (-r["notices"], r["pic"] is None, r["id"]))
        groups.append({"head": head["id"], "members": [i for i in ids if i != head["id"]],
                       "candidates": cands,
                       "confidence": float(min(p["confidence"] for p in cands))})
    groups.sort(key=lambda g: (-len(g["members"]), g["head"]))
    return groups, refused


def office_splits(conn) -> dict[str, int]:
    """Live rows of one country and one folded name that carry different registration numbers
    (BAAINBw: 67, one per office), and how many of those holding defence notices a buyer family
    shows as one buyer. Never merged: a display question, answered by `ops.buyer_families`."""
    r = conn.execute(
        """WITH g AS (
               SELECT country, dg_fold(canonical_name) AS k
                 FROM organisation WHERE merged_into IS NULL AND national_reg_no IS NOT NULL
                GROUP BY 1, 2 HAVING count(DISTINCT national_reg_no) > 1),
           m AS (
               SELECT o.id,
                      EXISTS (SELECT 1 FROM opportunity x WHERE x.buyer_org_id = o.id AND x.is_defence) AS buys,
                      EXISTS (SELECT 1 FROM buyer_family_member f
                               WHERE f.org_id = o.id OR f.head_org_id = o.id) AS in_family
                 FROM organisation o JOIN g ON g.country = o.country AND g.k = dg_fold(o.canonical_name)
                WHERE o.merged_into IS NULL)
           SELECT (SELECT count(*) FROM g) AS groups, count(*) AS rows,
                  count(*) FILTER (WHERE buys) AS buying_rows,
                  count(*) FILTER (WHERE buys AND in_family) AS buying_rows_in_a_family
             FROM m""").fetchone()
    return dict(r)


def sample_pairs(groups: list[dict[str, Any]], orgs: dict[int, dict[str, Any]],
                 n: int = 30) -> list[dict[str, Any]]:
    """`n` accepted pairs, spread by a hash of the candidate id (the same sample on every run)."""
    cands = [(g, p) for g in groups for p in g["candidates"]]
    cands.sort(key=lambda gp: hashlib.sha1(str(gp[1]["id"]).encode()).hexdigest())
    out = []
    for g, p in cands[:n]:
        a, b = orgs[p["a"]], orgs[p["b"]]
        out.append({"candidate": p["id"], "country": a["country"], "head": g["head"],
                    "a": (a["id"], a["name"], a["reg"] or a["vat"] or a["pic"]),
                    "b": (b["id"], b["name"], b["reg"] or b["vat"] or b["pic"]),
                    "evidence": p["evidence"]})
    return out


def run(conn, *, apply: bool = False, limit: int | None = None, sample: int = 30,
        with_office_splits: bool = True, out=print) -> dict[str, Any]:
    pending = pending_by_method(conn)
    out("pending candidates by method: " + ", ".join(
        f"{r['match_method']}@{r['confidence']} {r['n']}" for r in pending))
    pairs = strong_pairs(conn)
    orgs = organisations(conn, {i for p in pairs for i in (p["a"], p["b"])})
    groups, refused = plan(pairs, orgs)
    result: dict[str, Any] = {
        "pending": sum(r["n"] for r in pending), "strong_candidates": len(pairs),
        "accepted_candidates": sum(len(g["candidates"]) for g in groups),
        "groups": len(groups), "rows_to_merge": sum(len(g["members"]) for g in groups),
        "refused": dict(refused), "merged": 0}
    out(f"strong candidates ({'/'.join(STRONG_METHODS)} >= {MIN_CONFIDENCE}): {len(pairs)}; accepted "
        f"{result['accepted_candidates']} in {len(groups)} groups ({result['rows_to_merge']} rows to "
        f"merge); refused {dict(refused)}")
    public = [p for p in pairs
              if _pair_refusal(orgs.get(p["a"]), orgs.get(p["b"])) == "public_body"]
    result["families"] = buyer_families.run(
        conn, write=False, extra_pairs=[(p["a"], p["b"]) for p in public])
    out(f"public-body pairs (never merged, shown as buyer families): {len(public)}; buyer families "
        f"once they are: {result['families']}")
    result["public_sample"] = [
        {"candidate": p["id"], "a": (p["a"], orgs[p["a"]]["name"]), "b": (p["b"], orgs[p["b"]]["name"])}
        for p in sorted(public, key=lambda p: hashlib.sha1(str(p["id"]).encode()).hexdigest())[:sample]]
    for s in result["public_sample"]:
        out(f"  public #{s['candidate']}: {s['a'][0]} {s['a'][1][:50]!r} ~ {s['b'][0]} {s['b'][1][:50]!r}")
    result["sample"] = sample_pairs(groups, orgs, sample)
    for s in result["sample"]:
        out(f"  #{s['candidate']} {s['country']} head {s['head']}: {s['a'][0]} {s['a'][1][:45]!r} "
            f"[{s['a'][2]}] ~ {s['b'][0]} {s['b'][1][:45]!r} [{s['b'][2]}]")
    if with_office_splits:
        result["office_splits"] = office_splits(conn)
        out(f"same name, different registration numbers (never merged): {result['office_splits']}")
    if not apply:
        conn.rollback()
        out("dry run: nothing written (add --yes)")
        return result
    conn.execute(
        """UPDATE organisation_merge_candidate SET status = 'rejected_public_units', decided_at = now()
            WHERE id = ANY(%s) AND status = 'pending'""", ([p["id"] for p in public],))
    conn.commit()
    result["rejected_public_units"] = len(public)
    for g in groups[:limit]:
        for member in g["members"]:
            db.merge_organisations(
                conn, g["head"], member, method="identifier", confidence=g["confidence"],
                evidence=next(p["evidence"] for p in g["candidates"] if member in (p["a"], p["b"])),
                detected_by=DETECTED_BY)
            result["merged"] += 1
        conn.execute(
            """UPDATE organisation_merge_candidate SET status = 'merged', decided_at = now()
                WHERE id = ANY(%s) AND status = 'pending'""", ([p["id"] for p in g["candidates"]],))
        conn.commit()
    result["families_written"] = buyer_families.run(conn, write=True)
    result["directory_rows"] = networks.refresh_organisation_network(conn)["organisations"]
    out(f"merged {result['merged']} rows in {min(len(groups), limit or len(groups))} groups")
    return result


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--yes", action="store_true", help="merge; without it nothing changes")
    p.add_argument("--limit", type=int, default=None, help="merge at most this many groups")
    p.add_argument("--no-office-splits", action="store_true",
                   help="skip the report on same-name rows with different numbers (a full scan)")
    a = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    with db.connect(settings().dsn) as conn:
        run(conn, apply=a.yes, limit=a.limit, with_office_splits=not a.no_office_splits)
    return 0


if __name__ == "__main__":
    sys.exit(main())
