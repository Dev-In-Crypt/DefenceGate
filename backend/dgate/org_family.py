"""Which organisation rows are one body for the directory (display layer only, WP-41, N5).

The twin of `buyer_family.py` for the networks layer. A pure function over organisations and the
pairs the resolution cascade queued for a person (`resolution_review`): it decides nothing about the
data. The rows stay as they are; `ops/org_families.py` stores the result in `organisation_family_member`,
the directory reads it and shows one card with "includes N name variants", and the head's profile
counts the variants' projects. Emptying the table undoes all of it.

What is NOT done here, on the owner's standing decision: organisations with different registration
numbers are never merged. A family is not a merge, but it is shown as one card, so the same vetoes
apply to it:

  * two rows of different countries are never one family
  * two PICs, two registration numbers or two VAT numbers that differ veto a pair whose names are
    merely alike (a trigram candidate). Where the normalised names are *equal* the pair is the same
    name under two registrations (an AP-HP hospital group with six PICs): that is a family of its own
    kind, `same_name`, with a lower confidence and the PICs shown beside it
  * two different legal forms (RENK AG, RENK GmbH) are two bodies: no family
  * a name too short to tell bodies apart (fewer than MIN_KEY characters) makes no family

Rules, each stored with the member (method, confidence):

  name_variant   a trigram candidate of the cascade (stage 3, similarity 0.85 or more) that no veto
                 stops. Confidence is the stored similarity.
  same_name      an ambiguous exact name (the cascade found several rows with this name and chose one).
                 Confidence 0.80, as the cascade stored it.

A family is a star: the head is the row with the most projects (then the one holding a PIC, then the
lowest id), every member has its own stored pair with the head, so a chain A~B~C never makes A and C
one family. A row is a head or a member, never both.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .resolution.cascade import clean_vat
from .resolution.names import legal_form_of

MIN_KEY = 6
SAME_NAME_CONFIDENCE = 0.80
METHODS = {"trigram": "name_variant", "exact_name_ambiguous": "same_name"}


@dataclass(frozen=True)
class Pair:
    a: int
    b: int
    review_method: str          # trigram | exact_name_ambiguous
    confidence: float


def _vat(row: dict[str, Any]) -> str | None:
    return clean_vat(row.get("vat"), row.get("country"))


def veto(a: dict[str, Any], b: dict[str, Any], review_method: str) -> str | None:
    """Why this pair is not a family, or None. `a` and `b` carry id, country, key, pic, reg, vat, display."""
    if a["country"] != b["country"]:
        return "country"
    if min(len(a["key"]), len(b["key"])) < MIN_KEY:
        return "short_name"
    fa, fb = legal_form_of(a.get("display") or ""), legal_form_of(b.get("display") or "")
    if fa and fb and fa != fb:
        return "legal_form"
    if a.get("reg") and b.get("reg") and a["reg"] != b["reg"]:
        return "registration_number"
    va, vb = _vat(a), _vat(b)
    if va and vb and va != vb:
        return "vat_number"
    if review_method == "trigram" and a.get("pic") and b.get("pic") and a["pic"] != b["pic"]:
        return "pic"
    if review_method == "exact_name_ambiguous" and a["key"] != b["key"]:
        return "not_the_same_name"
    return None


def build(nodes: dict[int, dict[str, Any]], pairs: list[Pair]
          ) -> tuple[dict[int, tuple[int, str, float]], dict[str, int]]:
    """({member: (head, method, confidence)}, counts of pairs by outcome) for the pairs between `nodes`
    (the organisations that took part in a project: a pair with a row outside them is not counted)."""
    seen: dict[str, int] = {}
    edges: dict[int, list[tuple[int, str, float]]] = {}
    for p in pairs:
        a, b = nodes.get(p.a), nodes.get(p.b)
        if a is None or b is None:
            seen["outside_the_directory"] = seen.get("outside_the_directory", 0) + 1
            continue
        why = veto(a, b, p.review_method)
        if why:
            seen[f"vetoed_{why}"] = seen.get(f"vetoed_{why}", 0) + 1
            continue
        method = METHODS[p.review_method]
        conf = SAME_NAME_CONFIDENCE if method == "same_name" else round(min(max(p.confidence, 0.85), 0.99), 2)
        edges.setdefault(p.a, []).append((p.b, method, conf))
        edges.setdefault(p.b, []).append((p.a, method, conf))
        seen["accepted"] = seen.get("accepted", 0) + 1

    def rank(i: int) -> tuple[int, int, int]:
        n = nodes[i]
        return (-int(n.get("projects") or 0), 0 if n.get("pic") else 1, i)

    member_of: dict[int, tuple[int, str, float]] = {}
    heads: set[int] = set()
    for i in sorted(edges, key=rank):
        if i in member_of or i in heads:
            continue
        mine = [(j, m, c) for j, m, c in sorted(edges[i], key=lambda e: rank(e[0]))
                if j not in member_of and j not in heads]
        if not mine:
            continue
        heads.add(i)
        for j, m, c in mine:
            member_of[j] = (i, m, c)
    return member_of, seen
