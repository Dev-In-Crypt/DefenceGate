"""Undo one batch of organisation merges: the WP-72 run of 21 October 2026 (WP-74).

`ops.accept_merge_candidates --yes --limit 500` merged 6,641 rows into 500 heads between 18:20 and
18:39 UTC. Many groups were public administrations sharing one tax id across departments (the Basque
Government's 116 names under 'gobierno vasco - seguridad', every Madrid area under one of them):
legally one entity, as buyers different units. This reverses exactly that batch, from what the
merge itself left behind, and deletes nothing:

  * the batch      rows with `merge_method` 'identifier' and `merged_at` in the window, each with its
                   candidate row (`merged`, decided in the window); the count must equal `--expect`
  * the rows       `merged_into`, `merge_method`, `merge_confidence`, `merged_at` back to NULL
  * aliases        an alias on a head whose `prev_organisation_id` leads (through the merges that are
                   NOT undone) to a member goes back to that member; `prev_organisation_id` is cleared
                   when it is that member (the merge had set it from NULL)
  * notices        a notice on a head goes back to the member its version payload names: the latest
                   version observed before the batch, its `buyer_org_id`, followed through the merges
                   that stay (the docstring of `db.merge_organisations`: that is how a merge is undone)
  * the number     `merge_organisations` moves a member's `national_reg_no` onto a head that had none
                   and stamps the head `identifier_method` 'identifier' with the merge confidence
                   (>= 0.97; resolution stamps 0.90). The member keeps its own `identifier_method`, so
                   the donor is the member with a method and no number: the number goes back to it
  * the flag       `merge_organisations` sets `is_defence_buyer` on a head when a member had it, and
                   writes no source. A head flagged with no `defence_buyer_source`, a flagged member and
                   no place in the seed file had it from the merge: cleared
  * candidates     the batch's pairs go back to `pending` (the next merge run decides them under the
                   public-body rule); the audit rows the merge wrote (`detected_by` the WP-72 script,
                   created in the window) become `undone`

then the directory table is rebuilt. One transaction; a second run finds no batch and changes nothing.
`ops.accept_merge_candidates --undo-batch FROM TO` runs the same logic for any window and for the
two-signal methods of WP-76 (`identifier+name` ...), without an expected count.

    python -m dgate.ops.undo_merges                 # dry run: counts and 20 sampled notices
    python -m dgate.ops.undo_merges --yes
"""

from __future__ import annotations

import argparse
import hashlib
import logging
import sys
from datetime import datetime
from typing import Any

from .. import db, networks
from ..config import settings
from ..normalise import normalise_org_name

log = logging.getLogger("undo_merges")

METHOD = "identifier"
DETECTED_BY = "ops.accept_merge_candidates"
START = "2026-10-21 18:00:00+00"
END = "2026-10-21 19:00:00+00"
EXPECTED = 6641
MERGE_STAMP = 0.97           # the lowest identifier confidence a merge writes on a head


class BatchMismatch(RuntimeError):
    pass


def batch(conn, start: str, end: str, methods: tuple[str, ...], only: list[int] | None = None) -> list[dict[str, Any]]:
    """The rows merged by `methods` in [start, end); WP-119: only the rows `only` names, when given (one wrong group of
    a run is undone, the rest of the run stays)."""
    return [dict(r) for r in conn.execute(
        """SELECT o.id, o.merged_into AS head, o.merged_at, o.identifier_method,
                  o.national_reg_no, o.is_defence_buyer
             FROM organisation o
            WHERE o.merge_method = ANY(%s) AND o.merged_at >= %s AND o.merged_at < %s
              AND (%s::bigint[] IS NULL OR o.id = ANY(%s::bigint[]))
            ORDER BY o.id""", (list(methods), start, end, only, only)).fetchall()]


def _with_candidate(conn, rows: list[dict[str, Any]], start: str, end: str,
                    methods: tuple[str, ...]) -> int:
    """How many (member, head) pairs carry the `merged` candidate row the merge wrote or updated."""
    pairs = [(min(r["id"], r["head"]), max(r["id"], r["head"])) for r in rows]
    n = 0
    for i in range(0, len(pairs), 5000):
        part = pairs[i:i + 5000]
        n += conn.execute(
            """SELECT count(DISTINCT (c.organisation_id, c.candidate_org_id)) AS n
                 FROM organisation_merge_candidate c
                 JOIN unnest(%s::bigint[], %s::bigint[]) AS p(a, b)
                   ON c.organisation_id = p.a AND c.candidate_org_id = p.b
                WHERE c.match_method = ANY(%s) AND c.status = 'merged'
                  AND c.decided_at >= %s AND c.decided_at < %s""",
            ([a for a, _ in part], [b for _, b in part], list(methods), start, end)).fetchone()["n"]
    return n


def _seeded(conn) -> set[tuple[str, str]]:
    """(country, normalised name) of every spelling in the seed file: such a body is flagged by
    `seed-buyers`, which writes no source either."""
    from ..pipeline import load_seed_rows
    out = set()
    for (country, canonical), spellings in load_seed_rows().items():
        out.add((country, normalise_org_name(canonical)))
        out.update((country, normalise_org_name(raw)) for raw, _ in spellings)
    return out


def plan(conn, rows: list[dict[str, Any]], methods: tuple[str, ...] = (METHOD,)) -> dict[str, Any]:
    members = {r["id"]: r for r in rows}
    head_of = {r["id"]: r["head"] for r in rows}
    heads = sorted(set(head_of.values()))
    batch_start: datetime = min(r["merged_at"] for r in rows)

    # every other merge, which stays: the chain a payload id or an alias's origin follows afterwards
    stays = {r["id"]: r["merged_into"] for r in conn.execute(
        "SELECT id, merged_into FROM organisation WHERE merged_into IS NOT NULL").fetchall()
        if r["id"] not in members}
    # WP-115: a row that pointed at a member and was moved on to the member's head when the member was merged
    # (`db.repoint_merged`) points at the member again after the undo
    repointed = [(r["organisation_id"], int(r["old_value"]), int(r["new_value"])) for r in conn.execute(
        """SELECT DISTINCT ON (r.organisation_id) r.organisation_id, r.old_value, r.new_value
             FROM organisation_repair r JOIN organisation o ON o.id = r.organisation_id
            WHERE r.action = 'repoint_merged_into' AND r.old_value = ANY(%s)
              AND o.merged_into::text = r.new_value
            ORDER BY r.organisation_id, r.id DESC""", ([str(m) for m in members],)).fetchall()]
    for org, old, _new in repointed:
        stays[org] = old

    def live(x: int) -> int:
        for _ in range(16):
            if x not in stays:
                return x
            x = stays[x]
        return x

    def back_to(org: int | None, head: int) -> int | None:
        """The batch member `org` stands for after the undo, if it is one of `head`'s."""
        if org is None:
            return None
        t = live(org)
        return t if head_of.get(t) == head else None

    hrows = {r["id"]: dict(r) for r in conn.execute(
        """SELECT id, country, canonical_name, merged_into, national_reg_no, identifier_method,
                  identifier_confidence, is_defence_buyer, defence_buyer_source
             FROM organisation WHERE id = ANY(%s)""", (heads,)).fetchall()}
    if any(h["merged_into"] is not None for h in hrows.values()):
        raise BatchMismatch("a head of the batch was merged since: undo that first")

    aliases = []
    for a in conn.execute(
            """SELECT id, organisation_id, prev_organisation_id FROM organisation_alias
                WHERE organisation_id = ANY(%s) AND prev_organisation_id IS NOT NULL""",
            (heads,)).fetchall():
        t = back_to(a["prev_organisation_id"], a["organisation_id"])
        if t is not None:
            aliases.append((a["id"], t, None if a["prev_organisation_id"] == t
                            else a["prev_organisation_id"]))

    notices, kept = [], 0
    for o in conn.execute(
            """SELECT o.id, o.buyer_org_id,
                      (SELECT (v.payload->>'buyer_org_id')::bigint FROM opportunity_version v
                        WHERE v.opportunity_id = o.id AND v.observed_at < %s
                        ORDER BY v.version DESC LIMIT 1) AS archived
                 FROM opportunity o WHERE o.buyer_org_id = ANY(%s)""",
            (batch_start, heads)).fetchall():
        t = back_to(o["archived"], o["buyer_org_id"])
        if t is None:
            kept += 1
        else:
            notices.append((o["id"], o["buyer_org_id"], t))

    numbers = []                      # (head, donor, number)
    for h in hrows.values():
        # the stamp tells a merge's 'identifier' from resolution's (0.90); WP-129: any other method is a merge's own
        # ('person_review' stamps the reviewer's confidence, 0.80 .. 0.95)
        if not (h["national_reg_no"] and h["identifier_method"] in methods
                and h["identifier_confidence"] is not None
                and (h["identifier_method"] != METHOD or float(h["identifier_confidence"]) >= MERGE_STAMP)):
            continue
        donors = [m for m in members.values() if m["head"] == h["id"]
                  and m["identifier_method"] is not None and m["national_reg_no"] is None]
        if len(donors) == 1:
            numbers.append((h["id"], donors[0]["id"], h["national_reg_no"]))

    seeded = _seeded(conn) if any(h["is_defence_buyer"] for h in hrows.values()) else set()
    flagged_members = {m["head"] for m in members.values() if m["is_defence_buyer"]}
    flags = [h["id"] for h in hrows.values()
             if h["is_defence_buyer"] and h["defence_buyer_source"] is None
             and h["id"] in flagged_members
             and (h["country"], h["canonical_name"]) not in seeded]

    # WP-119: what the merge moved to the head (`db.MERGE_MOVES`: the PIC, the VAT number) and the
    # awards it counted once (`same_winner_twice`), each logged on the member with its head's id
    moves = [dict(r) for r in conn.execute(
        """SELECT DISTINCT ON (r.organisation_id, r.action) r.organisation_id AS member, r.action, r.old_value,
                  r.new_value::bigint AS head
             FROM organisation_repair r
            WHERE r.organisation_id = ANY(%s) AND r.action = ANY(%s) AND r.created_at >= %s
            ORDER BY r.organisation_id, r.action, r.id DESC""",
        (sorted(members), list(db.MERGE_MOVES), batch_start)).fetchall()
        if head_of.get(r["member"]) == int(r["head"])]

    return {"members": sorted(members), "heads": heads, "aliases": aliases, "notices": notices,
            "notices_kept": kept, "numbers": numbers, "flags": flags, "head_rows": hrows,
            "repointed": repointed, "moves": moves}


def move_back(conn, moves: list[dict[str, Any]]) -> None:
    """WP-119: undo what `db.carry_to_head` moved: the PIC and the VAT number back to the member (the head's cleared
    first, the PIC being unique), and its awards counted again."""
    for m in moves:
        member, head, old, action = m["member"], m["head"], m["old_value"], m["action"]
        if action == "merge_moved_pic":
            had = conn.execute("SELECT pic_method, pic_confidence FROM organisation WHERE id = %s AND eu_pic = %s",
                               (head, old)).fetchone()
            if had:
                conn.execute("UPDATE organisation SET eu_pic = NULL, pic_method = NULL, pic_confidence = NULL "
                             "WHERE id = %s", (head,))
                conn.execute("UPDATE organisation SET eu_pic = %s, pic_method = %s, pic_confidence = %s WHERE id = %s",
                             (old, had["pic_method"], had["pic_confidence"], member))
        elif action == "merge_moved_vat":
            if conn.execute("UPDATE organisation SET vat_number = NULL WHERE id = %s AND vat_number = %s",
                            (head, old)).rowcount:
                conn.execute("UPDATE organisation SET vat_number = %s WHERE id = %s", (old, member))
        elif action == "merge_award_twice":
            conn.execute("UPDATE award SET excluded_reason = NULL WHERE id = ANY(%s) AND excluded_reason = %s",
                         ([int(x) for x in old.split(",")], db.SAME_WINNER_TWICE))


def sample_notices(conn, notices: list[tuple[int, int, int]], n: int = 20) -> list[dict[str, Any]]:
    pick = sorted(notices, key=lambda x: hashlib.sha1(str(x[0]).encode()).hexdigest())[:n]
    ids = sorted({i for _, h, m in pick for i in (h, m)})
    names = {r["id"]: r["canonical_name"] for r in conn.execute(
        "SELECT id, canonical_name FROM organisation WHERE id = ANY(%s)", (ids,)).fetchall()}
    return [{"notice": o, "old": (h, names.get(h)), "new": (m, names.get(m))} for o, h, m in pick]


def run(conn, *, apply: bool = False, start: str = START, end: str = END,
        methods: tuple[str, ...] = (METHOD,),
        expected: int | None = EXPECTED, detected_by: str = DETECTED_BY, sample: int = 20,
        refresh: bool = True, out=print, only: list[int] | None = None) -> dict[str, Any]:
    rows = batch(conn, start, end, methods, only)
    result: dict[str, Any] = {"rows": len(rows), "applied": False}
    if not rows:
        conn.rollback()
        out(f"no rows merged by {list(methods)} between {start} and {end}: nothing to undo")
        return result
    if expected is not None and len(rows) != expected:
        raise BatchMismatch(f"{len(rows)} rows in the window, expected {expected}")
    proved = _with_candidate(conn, rows, start, end, methods)
    if proved != len(rows):
        raise BatchMismatch(f"{len(rows) - proved} rows of the window have no merged candidate pair")
    p = plan(conn, rows, methods)
    # WP-119: with `only`, the candidate rows of those pairs alone
    pairs = (None, None) if only is None else ([min(r["id"], r["head"]) for r in rows],
                                               [max(r["id"], r["head"]) for r in rows])
    in_pairs = """ AND (%s::bigint[] IS NULL OR (organisation_id, candidate_org_id) IN
                        (SELECT a, b FROM unnest(%s::bigint[], %s::bigint[]) AS p(a, b)))"""
    cands = conn.execute(
        """SELECT count(*) FILTER (WHERE detected_by <> %s OR created_at < %s) AS to_pending,
                  count(*) FILTER (WHERE detected_by = %s AND created_at >= %s) AS to_undone
             FROM organisation_merge_candidate
            WHERE match_method = ANY(%s) AND status = 'merged' AND decided_at >= %s AND decided_at < %s""" + in_pairs,
        (detected_by, start, detected_by, start, list(methods), start, end, pairs[0], *pairs)).fetchone()
    result.update({
        "heads": len(p["heads"]), "aliases": len(p["aliases"]), "notices": len(p["notices"]),
        "notices_kept_on_head": p["notices_kept"], "numbers_restored": len(p["numbers"]),
        "flags_cleared": len(p["flags"]), "moved_back": len(p["moves"]), "candidates_pending": cands["to_pending"],
        "candidates_undone": cands["to_undone"]})
    out(f"batch {start} .. {end}: {len(rows)} rows under {len(p['heads'])} heads (every one with its "
        f"candidate pair); aliases back {len(p['aliases'])}; notices back {len(p['notices'])} "
        f"(kept on the head: {p['notices_kept']}); numbers back to their row {len(p['numbers'])}; "
        f"defence-buyer flags cleared {len(p['flags'])} {p['flags']}; PICs, VAT numbers and "
        f"awards moved back {len(p['moves'])}; candidates to pending "
        f"{cands['to_pending']}, audit rows to undone {cands['to_undone']}")
    result["sample"] = sample_notices(conn, p["notices"], sample)
    for s in result["sample"]:
        out(f"  notice {s['notice']}: buyer {s['old'][0]} {str(s['old'][1])[:50]!r} -> "
            f"{s['new'][0]} {str(s['new'][1])[:50]!r}")
    if not apply:
        conn.rollback()
        out("dry run: nothing written (add --yes)")
        return result

    conn.execute(
        """UPDATE organisation SET merged_into = NULL, merge_method = NULL, merge_confidence = NULL,
                  merged_at = NULL WHERE id = ANY(%s)""", (p["members"],))
    for org, old, new in p["repointed"]:
        conn.execute("UPDATE organisation SET merged_into = %s WHERE id = %s AND merged_into = %s", (old, org, new))
    for alias_id, org, prev in p["aliases"]:
        conn.execute("UPDATE organisation_alias SET organisation_id = %s, prev_organisation_id = %s "
                     "WHERE id = %s", (org, prev, alias_id))
    for opp, head, member in p["notices"]:
        conn.execute("UPDATE opportunity SET buyer_org_id = %s WHERE id = %s AND buyer_org_id = %s",
                     (member, opp, head))
    for head, donor, number in p["numbers"]:
        conn.execute("""UPDATE organisation SET national_reg_no = NULL, identifier_method = NULL,
                               identifier_confidence = NULL WHERE id = %s""", (head,))
        conn.execute("UPDATE organisation SET national_reg_no = %s WHERE id = %s", (number, donor))
    if p["flags"]:
        conn.execute("UPDATE organisation SET is_defence_buyer = FALSE WHERE id = ANY(%s)",
                     (p["flags"],))
    move_back(conn, p["moves"])
    conn.execute(
        """UPDATE organisation_merge_candidate
              SET status = CASE WHEN detected_by = %s AND created_at >= %s THEN 'undone'
                                ELSE 'pending' END,
                  decided_at = CASE WHEN detected_by = %s AND created_at >= %s THEN now() END
            WHERE match_method = ANY(%s) AND status = 'merged' AND decided_at >= %s AND decided_at < %s""" + in_pairs,
        (detected_by, start, detected_by, start, list(methods), start, end, pairs[0], *pairs))
    conn.commit()
    result["applied"] = True
    out(f"undone: {len(rows)} rows unmerged")
    if refresh:
        result["directory_rows"] = networks.refresh_organisation_network(conn)["organisations"]
    return result


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--yes", action="store_true", help="undo; without it nothing changes")
    p.add_argument("--start", default=START)
    p.add_argument("--end", default=END)
    p.add_argument("--expect", type=int, default=EXPECTED,
                   help="the number of rows the window must hold, or the run stops")
    a = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    with db.connect(settings().dsn) as conn:
        run(conn, apply=a.yes, start=a.start, end=a.end, expected=a.expect)
    return 0


if __name__ == "__main__":
    sys.exit(main())
