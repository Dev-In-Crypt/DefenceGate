"""The resolution cascade of the networks layer (plan 7.2, data architecture part VIII).

    resolve(conn, name, country, identifiers, context) -> Resolution(org_id, method, confidence, ...)

Stages, cheapest and surest first. A decision at any stage is written down (an alias or an
identifier, each with its method and confidence) and stops the cascade.

  1  identifier   the PIC (unique across the Participant Register), then a national
                  registration number or a VAT number held by an organisation of the same
                  country whose name shares its words with this one (`names_compatible`).
                  The PIC is asked first because it is a unique lookup and beats any name.
  0  alias        this normalised name in this country has been decided before.
  2  exact name   the same normalised name in the same country. One live organisation: that
                  one. Two or more: the best known of them, at 0.80, and the pair goes to
                  `resolution_review`. An organisation that holds another PIC is a namesake,
                  not this one: a new organisation is made and the pair goes to review.
     legal form   a name that states a legal form (AG, GmbH, SA, Ltd ...) is not the organisation that has
                  stated another one under the same key: RENK AG and RENK GmbH are two bodies. The row is
                  skipped, a new organisation is made if no row with this form exists, and the pair goes
                  to `resolution_review` (method `legal_form_conflict`). WP-41, N11.
  3  candidates   trigram similarity of 0.85 or more within the country, same numbers in the
                  name, never across countries. They are written to `resolution_review` and
                  **never merged**: Thales SA and Thales Nederland B.V. are related, not one body.

Stages 4 to 6 of the plan (embeddings, a model's adjudication, the person) are not built;
stage 6 is the review queue as a table. No model is called here.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

from .. import db
from ..normalise import normalise_identifier
from .names import key_of, legal_form_of
from .trigram import THRESHOLD, is_candidate

log = logging.getLogger(__name__)

CONF_PIC = 1.00
CONF_AMBIGUOUS = 0.80
CONF_NATIONAL_ID = db.CONF_IDENTIFIER


@dataclass
class Resolution:
    org_id: int | None
    method: str                    # pic | national_id | vat | alias | exact_name | exact_name_ambiguous | none
    confidence: float
    created: bool = False
    candidates: list[dict[str, Any]] = field(default_factory=list)


def clean_pic(value: Any) -> str | None:
    s = re.sub(r"\D", "", str(value or ""))
    return s if re.fullmatch(r"\d{9}", s) else None


def clean_vat(value: Any, country: str | None = None) -> str | None:
    """A VAT number as digits and letters, without the country prefix (EL for Greece), so that
    the one a research registry states and the one a procurement notice states compare equal."""
    s = re.sub(r"[^0-9A-Za-z]", "", str(value or "")).upper()
    cc = (country or "").upper()
    for prefix in ((cc, "EL") if cc == "GR" else (cc,)):
        if prefix and s.startswith(prefix) and len(s) - len(prefix) >= 5:
            s = s[len(prefix):]
            break
    return s if 4 <= len(s) <= 20 else None


def clean_ids(ids: dict[str, Any], country: str) -> dict[str, str]:
    """{'reg': ..., 'vat': ...} as comparable strings; what is absent or junk is left out."""
    out: dict[str, str] = {}
    reg = normalise_identifier(ids.get("reg"), country) if ids.get("reg") else None
    vat = clean_vat(ids.get("vat"), country)
    if reg:
        out["reg"] = reg
    if vat:
        out["vat"] = vat
    return out


def add_review(conn: psycopg.Connection, a: int, b: int, *, relation: str, method: str,
               confidence: float, evidence: dict[str, Any]) -> bool:
    """Queue a pair for a person. Idempotent; never touches either organisation."""
    if a == b:
        return False
    lo, hi = sorted((a, b))
    row = conn.execute(
        """INSERT INTO resolution_review (org_a, org_b, proposed_relation, method, confidence, evidence)
           VALUES (%s, %s, %s, %s, %s, %s)
           ON CONFLICT (org_a, org_b, method) DO NOTHING RETURNING id""",
        (lo, hi, relation, method, round(confidence, 2), Jsonb(evidence))).fetchone()
    return row is not None


def propose_candidates(conn: psycopg.Connection, org_id: int, key: str, country: str,
                       *, limit: int = 5) -> list[dict[str, Any]]:
    """Stage 3: organisations of the same country whose key is 0.85 alike. Written to the review
    queue and returned; nothing is merged."""
    conn.execute("SELECT set_config('pg_trgm.similarity_threshold', %s, false)", (str(THRESHOLD),))
    rows = conn.execute(
        """SELECT id, canonical_name, eu_pic, similarity(canonical_name, %s) AS sim
             FROM organisation
            WHERE country = %s AND id <> %s AND merged_into IS NULL AND canonical_name %% %s
            ORDER BY sim DESC, id LIMIT %s""",
        (key, country, org_id, key, limit * 3)).fetchall()
    found: list[dict[str, Any]] = []
    for r in rows:
        sim = is_candidate(key, country, r["canonical_name"], country)
        if sim is None:
            continue
        found.append({"org_id": r["id"], "name": r["canonical_name"], "similarity": round(sim, 3)})
        add_review(conn, org_id, r["id"], relation="same", method="trigram", confidence=sim,
                   evidence={"keys": [key, r["canonical_name"]], "country": country,
                             "similarity": round(sim, 3), "pic": r["eu_pic"]})
        if len(found) >= limit:
            break
    return found


def _by_pic(conn: psycopg.Connection, pic: str) -> int | None:
    row = conn.execute("SELECT id FROM organisation WHERE eu_pic = %s", (pic,)).fetchone()
    return db._live(conn, row["id"]) if row else None


def _by_national_id(conn: psycopg.Connection, key: str, country: str, ids: dict[str, Any]
                    ) -> tuple[int, str] | None:
    """A registration or VAT number, trusted only against a name that shares its words."""
    for kind, value in clean_ids(ids, country).items():
        # a registry number and a VAT number are often the same digits: ask both columns
        row = conn.execute(
            """SELECT id, canonical_name FROM organisation
                WHERE country = %s AND (national_reg_no = %s OR vat_number = %s)
                  AND merged_into IS NULL ORDER BY id LIMIT 1""", (country, value, value)).fetchone()
        if row and db.names_compatible(key, row["canonical_name"]):
            return row["id"], "national_id" if kind == "reg" else "vat"
    return None


def _form_clash(conn: psycopg.Connection, org_id: int, name: str) -> bool:
    """Whether `name` states a legal form and the organisation has been called, by that form's class,
    only something else: its display name and the names of its aliases are the evidence. A name with no
    form, or an organisation never seen with one, clashes with nothing."""
    new = legal_form_of(name)
    if new is None:
        return False
    names = [r["n"] for r in conn.execute(
        """SELECT display_name AS n FROM organisation WHERE id = %s
           UNION ALL (SELECT raw_name FROM organisation_alias WHERE organisation_id = %s LIMIT 50)""",
        (org_id, org_id)).fetchall()]
    have = {c for c in (legal_form_of(n or "") for n in names) if c}
    return bool(have) and new not in have


def resolve(conn: psycopg.Connection, name: str, country: str | None,
            identifiers: dict[str, Any] | None = None,
            context: dict[str, Any] | None = None) -> Resolution:
    """Which organisation is this participant? See the module docstring for the stages.

    context: source_id (alias provenance), create (default True: make an organisation when no
    stage matches), candidates (default True: run stage 3 for an organisation made now).
    """
    ctx = context or {}
    ids = identifiers or {}
    src_id = ctx.get("source_id")
    key, legacy = key_of(name)
    if not key or not country:
        return Resolution(None, "none", 0.0)
    pic = clean_pic(ids.get("pic"))
    vat = clean_vat(ids.get("vat"), country)

    def note(org_id: int, method: str, confidence: float) -> None:
        """Write the alias: under the new key, and under the legacy key when it differs (a
        Cyrillic spelling is then found by both the old lookups and the new ones)."""
        db._record_alias(conn, org_id, name, key, src_id, country, method, confidence)
        if legacy and legacy != key:
            db._record_alias(conn, org_id, name, legacy, src_id, country, method, confidence)

    # Stage 1, the PIC.
    if pic:
        org_id = _by_pic(conn, pic)
        if org_id is not None:
            note(org_id, "pic", CONF_PIC)
            return Resolution(org_id, "pic", CONF_PIC)

    # Stage 0, an alias decided before. A PIC held by the organisation must not contradict ours.
    alias = conn.execute(
        """SELECT a.organisation_id, a.confidence, o.eu_pic
             FROM organisation_alias a JOIN organisation o ON o.id = a.organisation_id
            WHERE a.normalised_name = ANY(%s) AND (a.country_hint = %s OR a.country_hint IS NULL)
              AND o.country = %s
            ORDER BY a.confidence DESC, a.id LIMIT 1""",
        (list({key, legacy}), country, country)).fetchone()
    if alias and not (pic and alias["eu_pic"] and alias["eu_pic"] != pic) and not _form_clash(
            conn, alias["organisation_id"], name):
        org_id = db._live(conn, alias["organisation_id"])
        if pic and alias["eu_pic"] is None:
            _attach_pic(conn, org_id, pic, "alias", float(alias["confidence"]), name, vat)
        return Resolution(org_id, "alias", float(alias["confidence"]))

    # Stage 1 again, the weaker identifiers.
    hit = _by_national_id(conn, key, country, ids)
    if hit:
        org_id, method = hit
        note(org_id, method, CONF_NATIONAL_ID)
        if pic:
            _attach_pic(conn, org_id, pic, method, CONF_NATIONAL_ID, name, vat)
        return Resolution(org_id, method, CONF_NATIONAL_ID)

    # Stage 2, the exact normalised name within the country.
    rows = conn.execute(
        """SELECT id, eu_pic FROM organisation
            WHERE country = %s AND lower(canonical_name) = ANY(%s) AND merged_into IS NULL
            ORDER BY id""", (country, list({key, legacy}))).fetchall()
    same = [r for r in rows if not (pic and r["eu_pic"] and r["eu_pic"] != pic)]
    other_pic = [r for r in rows if pic and r["eu_pic"] and r["eu_pic"] != pic]
    other_form = [r for r in same if _form_clash(conn, r["id"], name)]
    same = [r for r in same if r not in other_form]
    if len(same) == 1:
        org_id = same[0]["id"]
        if pic and same[0]["eu_pic"] is None:
            _attach_pic(conn, org_id, pic, "exact_name", db.CONF_EXACT_NAME, name, vat)
        note(org_id, "exact_name", db.CONF_EXACT_NAME)
        return Resolution(org_id, "exact_name", db.CONF_EXACT_NAME)
    if len(same) > 1:
        best = sorted(same, key=lambda r: (r["eu_pic"] is None, r["id"]))[0]["id"]
        for r in same:
            add_review(conn, best, r["id"], relation="ambiguous_name", method="exact_name_ambiguous",
                       confidence=CONF_AMBIGUOUS,
                       evidence={"key": key, "country": country, "chosen": best,
                                 "candidates": [x["id"] for x in same]})
        note(best, "exact_name_ambiguous", CONF_AMBIGUOUS)
        return Resolution(best, "exact_name_ambiguous", CONF_AMBIGUOUS,
                          candidates=[{"org_id": r["id"]} for r in same if r["id"] != best])
    if not ctx.get("create", True):
        return Resolution(None, "none", 0.0)

    org_id = _new_organisation(conn, name, key, country, pic, vat)
    method, conf = ("pic", CONF_PIC) if pic else ("exact_name", db.CONF_EXACT_NAME)
    note(org_id, method, conf)
    for r in other_pic:
        add_review(conn, org_id, r["id"], relation="same_name_other_pic", method="pic_conflict",
                   confidence=0.50,
                   evidence={"key": key, "country": country, "pics": [pic, r["eu_pic"]]})
    for r in other_form:
        add_review(conn, org_id, r["id"], relation="same_name_other_legal_form", method="legal_form_conflict",
                   confidence=0.50,
                   evidence={"key": key, "country": country, "form": legal_form_of(name)})
    found: list[dict[str, Any]] = []
    if ctx.get("candidates", True):
        found = propose_candidates(conn, org_id, key, country)
    return Resolution(org_id, method, conf, created=True, candidates=found)


def _attach_pic(conn: psycopg.Connection, org_id: int, pic: str, method: str, confidence: float,
                name: str, vat: str | None) -> None:
    """Give an organisation we knew by name or number its PIC, if nobody holds that PIC."""
    conn.execute(
        """UPDATE organisation
              SET eu_pic = %s, pic_method = %s, pic_confidence = %s,
                  display_name = COALESCE(display_name, %s), vat_number = COALESCE(vat_number, %s)
            WHERE id = %s AND eu_pic IS NULL
              AND NOT EXISTS (SELECT 1 FROM organisation x WHERE x.eu_pic = %s)""",
        (pic, method, round(confidence, 2), name[:300], vat, org_id, pic))


def _new_organisation(conn: psycopg.Connection, name: str, key: str, country: str,
                      pic: str | None, vat: str | None) -> int:
    return conn.execute(
        """INSERT INTO organisation
             (canonical_name, display_name, country, confidence, review_status, eu_pic, pic_method,
              pic_confidence, vat_number)
           VALUES (%s, %s, %s, 0.95, 'auto', %s, %s, %s, %s) RETURNING id""",
        (key, name[:300], country, pic, "source" if pic else None, CONF_PIC if pic else None,
         vat)).fetchone()["id"]
