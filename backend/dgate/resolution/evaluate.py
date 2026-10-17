"""`dgate resolution-eval`: precision and recall of each resolution stage on the gold pairs.

The gold set (seeds/resolution_gold.json, table `resolution_gold`) is a list of pairs of names
with a hand-given verdict: the same legal entity or not. The stages are run on each pair as pure
functions, without a database and with the arithmetic of the database stages (trigram.py), so
the same command runs in CI and on the server and gives the same numbers.

  identifier   both sides state a PIC: equal says "same", different says "other"; or a registry or
               VAT number in common in one country (the names must also share words in the database)
  exact_name   same country, same normalised key (and no contradicting identifier)
  candidate    stage 3: same country, 0.85 alike, same numbers; goes to review, never decides

Precision is what matters (a false merge corrupts a funding history, a missed one makes a
duplicate). The command exits 1 when the precision of a stage that decides alone is under 0.97.
Stage 0 (alias lookup) replays the decisions of the others and has no pairwise form.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .. import db
from .cascade import clean_ids, clean_pic
from .names import key_of
from .trigram import is_candidate

SEED = Path(__file__).resolve().parents[2] / "seeds" / "resolution_gold.json"
MIN_PRECISION = 0.97
DECIDING = ("identifier", "exact_name")


def _stage_identifier(p: dict[str, Any]) -> str | None:
    a, b = p.get("ids_a") or {}, p.get("ids_b") or {}
    pa, pb = clean_pic(a.get("pic")), clean_pic(b.get("pic"))
    if pa and pb:
        return "same" if pa == pb else "other"
    if p["country_a"] == p["country_b"]:
        # a registry number or a VAT number in common; two different numbers prove nothing
        # (one body has several), so only agreement decides
        ia, ib = set(clean_ids(a, p["country_a"]).values()), set(clean_ids(b, p["country_b"]).values())
        # the database trusts a number only against a name that shares its words
        if ia & ib and db.names_compatible(key_of(p["name_a"])[0], key_of(p["name_b"])[0]):
            return "same"
    return None


def _stage_exact(p: dict[str, Any]) -> bool:
    if p["country_a"] != p["country_b"]:
        return False
    ka, kb = key_of(p["name_a"])[0], key_of(p["name_b"])[0]
    return bool(ka) and ka == kb


def decide(p: dict[str, Any]) -> tuple[str, float | None]:
    """The stage that settles a pair, and for a candidate its similarity:
    identifier | exact_name | candidate | none.

    Two different PICs stop the two deciding stages (two registrations are two organisations until a
    person says otherwise) but not stage 3: the cascade queues such a pair for review, with both PICs
    in the evidence."""
    ident = _stage_identifier(p)
    if ident == "same":
        return "identifier", None
    if ident != "other" and _stage_exact(p):
        return "exact_name", None
    ka, kb = key_of(p["name_a"])[0], key_of(p["name_b"])[0]
    sim = is_candidate(ka, p["country_a"], kb, p["country_b"])
    return ("candidate", sim) if sim is not None else ("none", None)


def evaluate(pairs: list[dict[str, Any]]) -> dict[str, Any]:
    positives = sum(1 for p in pairs if p["is_match"])
    stages: dict[str, dict[str, Any]] = {}
    verdicts = [(p, *decide(p)) for p in pairs]
    for stage in ("identifier", "exact_name", "candidate"):
        said = [p for p, s, _ in verdicts if s == stage]
        tp = sum(1 for p in said if p["is_match"])
        fp = len(said) - tp
        stages[stage] = {
            "predicted_same": len(said), "true_positive": tp, "false_positive": fp,
            "precision": (tp / len(said)) if said else None,
            "recall": (tp / positives) if positives else None,
            "wrong": [(p["name_a"], p["country_a"], p["name_b"], p["country_b"], p.get("note"))
                      for p in said if not p["is_match"]],
        }
    decided = [p for p, s, _ in verdicts if s in DECIDING]
    tp = sum(1 for p in decided if p["is_match"])
    stages["deciding_stages"] = {
        "predicted_same": len(decided), "true_positive": tp, "false_positive": len(decided) - tp,
        "precision": (tp / len(decided)) if decided else None,
        "recall": (tp / positives) if positives else None, "wrong": []}
    missed = [(p["name_a"], p["country_a"], p["name_b"], p["country_b"], p.get("note"))
              for p, s, _ in verdicts if p["is_match"] and s not in DECIDING + ("candidate",)]
    by_kind: dict[str, dict[str, int]] = {}
    for p, s, _ in verdicts:
        row = by_kind.setdefault(p["kind"], {"pairs": 0, "match": 0, "identifier": 0, "exact_name": 0,
                                             "candidate": 0, "none": 0})
        row["pairs"] += 1
        row["match"] += bool(p["is_match"])
        row[s] += 1
    return {"pairs": len(pairs), "positives": positives, "negatives": len(pairs) - positives,
            "stages": stages, "by_kind": by_kind, "missed_by_every_stage": missed,
            "ok": all(stages[s]["precision"] is None or stages[s]["precision"] >= MIN_PRECISION
                      for s in DECIDING)}


def format_report(rep: dict[str, Any]) -> str:
    def f(x: float | None) -> str:
        return "  n/a" if x is None else f"{x:.3f}"

    lines = [f"gold pairs: {rep['pairs']}  ({rep['positives']} positive, {rep['negatives']} negative)",
             "",
             f"{'stage':<18}{'said same':>10}{'right':>7}{'wrong':>7}{'precision':>11}{'recall':>9}"]
    for name, s in rep["stages"].items():
        lines.append(f"{name:<18}{s['predicted_same']:>10}{s['true_positive']:>7}"
                     f"{s['false_positive']:>7}{f(s['precision']):>11}{f(s['recall']):>9}")
    for name, s in rep["stages"].items():
        for w in s["wrong"]:
            lines.append(f"  WRONG at {name}: {w[0]} ({w[1]}) / {w[2]} ({w[3]})  {w[4] or ''}")
    lines.append("")
    lines.append(f"{'kind':<16}{'pairs':>6}{'same':>6}{'by id':>7}{'by name':>9}{'candidate':>11}{'none':>6}")
    for kind, k in sorted(rep["by_kind"].items()):
        lines.append(f"{kind:<16}{k['pairs']:>6}{k['match']:>6}{k['identifier']:>7}{k['exact_name']:>9}"
                     f"{k['candidate']:>11}{k['none']:>6}")
    lines.append(f"positives no stage found (duplicates the cascade leaves): "
                 f"{len(rep['missed_by_every_stage'])}")
    lines.append("")
    lines.append(("OK" if rep["ok"] else f"FAIL: a deciding stage is under {MIN_PRECISION} precision")
                 + f" (threshold {MIN_PRECISION} for {', '.join(DECIDING)})")
    return "\n".join(lines)


def load_seed(path: Path = SEED) -> list[dict[str, Any]]:
    return json.loads(path.read_text(encoding="utf-8"))


def store_seed(conn, pairs: list[dict[str, Any]]) -> int:
    """Upsert the seed into `resolution_gold`. Returns the number of pairs written."""
    from psycopg.types.json import Jsonb

    for p in pairs:
        conn.execute(
            """INSERT INTO resolution_gold
                 (name_a, country_a, name_b, country_b, ids_a, ids_b, is_match, kind, note)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT (name_a, country_a, name_b, country_b) DO UPDATE SET
                 ids_a = EXCLUDED.ids_a, ids_b = EXCLUDED.ids_b, is_match = EXCLUDED.is_match,
                 kind = EXCLUDED.kind, note = EXCLUDED.note""",
            (p["name_a"], p["country_a"], p["name_b"], p["country_b"], Jsonb(p.get("ids_a") or {}),
             Jsonb(p.get("ids_b") or {}), p["is_match"], p["kind"], p.get("note")))
    conn.commit()
    return len(pairs)


def load_table(conn) -> list[dict[str, Any]]:
    return [dict(r) for r in conn.execute(
        """SELECT name_a, country_a, name_b, country_b, ids_a, ids_b, is_match, kind, note
             FROM resolution_gold ORDER BY id""").fetchall()]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="dgate resolution-eval")
    ap.add_argument("--gold", type=Path, default=SEED, help="gold pairs (JSON); default: the seed")
    ap.add_argument("--load", action="store_true",
                    help="write the pairs into resolution_gold first (needs DGATE_DSN)")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    pairs = load_seed(a.gold)
    if a.load:
        from .. import db
        from ..config import settings

        with db.connect(settings().dsn) as conn:
            print(f"resolution_gold: {store_seed(conn, pairs)} pairs written")
    rep = evaluate(pairs)
    print(json.dumps(rep, indent=1, default=str) if a.json else format_report(rep))
    return 0 if rep["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
