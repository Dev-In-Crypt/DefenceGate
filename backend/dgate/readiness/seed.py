"""Load the readiness content: parse and validate `seeds/requirements.json`, write it to the
database, read it back.

    python -m dgate.readiness.seed --check     parse and validate the seed file only (no database)
    python -m dgate.readiness.seed             apply it to the database in DGATE_DSN

Applying is idempotent: a second run inserts nothing. A row the seed no longer lists is switched
off (`active = false`), never deleted. The worker applies the seed when it starts, so a deploy
that changes the file changes the rules without a separate step.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict
from datetime import date
from pathlib import Path
from typing import Any

import psycopg

from .content import Content, Issuer, Money, Programme, Requirement, Rule, Span, Variant
from .engine import ExprError, fields_in, validate_expr

SEED_PATH = Path(__file__).resolve().parents[2] / "seeds" / "requirements.json"
OBLIGATIONS = {"mandatory", "conditional", "recommended"}
RULE_KINDS = {"threshold", "categorical", "establishment", "control", "declaration", "registration",
              "contract", "export", "security", "information"}
CATEGORIES = {"identification", "registration", "quality", "export_control", "security", "integrity",
              "admission", "origin"}
STATUSES = {"V", "S", "U"}
ORIGINS = {"primary", "notes"}
RELATIONS = {"before", "before_or_with"}
COUNTRY = re.compile(r"^(\*|[A-Z]{2})$")


class SeedError(ValueError):
    """The seed file is not valid. The message names the row."""


def _need(cond: bool, message: str) -> None:
    if not cond:
        raise SeedError(message)


def _money(raw: dict[str, Any] | None, where: str) -> Money | None:
    if raw is None:
        return None
    _need(raw.get("basis") in ("free", "vendor_range", "not_stated"), f"{where}: unknown cost basis {raw.get('basis')!r}")
    _need(raw.get("min") is not None and raw.get("max") is not None and raw["min"] <= raw["max"], f"{where}: cost min/max")
    _need((raw["basis"] == "free") == (raw.get("currency") is None), f"{where}: a free cost has no currency, any other has one")
    return Money(raw["min"], raw["max"], raw.get("currency"), raw["basis"], raw.get("text"), raw.get("alt"))


def _span(raw: dict[str, Any] | None, where: str) -> Span | None:
    if raw is None:
        return None
    _need(raw.get("min") is not None and raw.get("max") is not None and 0 <= raw["min"] <= raw["max"], f"{where}: days min/max")
    return Span(raw["min"], raw["max"], raw.get("text"), raw.get("note"))


def _source_text(passages: list[dict[str, Any]], where: str) -> str:
    _need(bool(passages), f"{where}: no verbatim passage")
    for p in passages:
        _need(bool(p.get("ref")) and bool(p.get("text")), f"{where}: a passage needs a ref and a text")
    return "\n\n".join(f"[{p['ref']}] {p['text']}" for p in passages)


def _common(raw: dict[str, Any], where: str) -> None:
    _need(raw.get("verification_status") in STATUSES, f"{where}: verification_status")
    _need(raw.get("text_origin") in ORIGINS, f"{where}: text_origin")
    _need(bool(raw.get("source_url")), f"{where}: source_url is required")
    try:
        date.fromisoformat(raw["last_reviewed"])
    except (KeyError, ValueError):
        raise SeedError(f"{where}: last_reviewed must be a date") from None


def parse(raw: dict[str, Any]) -> Content:
    codes = {r["code"] for r in raw["requirements"]}
    _need(len(codes) == len(raw["requirements"]), "duplicate requirement code")

    issuers: dict[str, list[Issuer]] = {c: [] for c in codes}
    rows = list(raw["issuers"])
    d = raw.get("issuer_defaults")
    if d:
        rows += [{"requirement": d["requirement"], "country": c, "name": d["name"], "url": None,
                  "status": d["status"], "notes": d["notes"]} for c in d["countries"]]
    for i in rows:
        where = f"issuer {i['requirement']} {i['country']}"
        _need(i["requirement"] in codes, f"{where}: unknown requirement")
        _need(bool(COUNTRY.match(i["country"])), f"{where}: country")
        _need(i["status"] in STATUSES, f"{where}: status")
        issuers[i["requirement"]].append(Issuer(i["requirement"], i["country"], i["name"], i.get("url"), i.get("notes"), i["status"]))

    prereq: dict[str, list[tuple[str, str]]] = {c: [] for c in codes}
    for p in raw["prerequisites"]:
        _need(p["requirement"] in codes and p["prerequisite"] in codes, f"prerequisite {p}: unknown code")
        _need(p["relation"] in RELATIONS and p["requirement"] != p["prerequisite"], f"prerequisite {p}")
        prereq[p["requirement"]].append((p["prerequisite"], p["relation"]))

    requirements: dict[str, Requirement] = {}
    for r in raw["requirements"]:
        where = f"requirement {r['code']}"
        _common(r, where)
        _need(r["category"] in CATEGORIES and r["kind"] in ("document", "rule"), f"{where}: category or kind")
        variants = []
        for v in r.get("variants", []):
            _need(v["when_held"] in codes, f"{where}: variant for an unknown requirement")
            variants.append(Variant(v["when_held"], _money(v.get("cost"), where + " variant"),
                                    _span(v.get("days"), where + " variant"), _source_text(v["passages"], where + " variant")))
        requirements[r["code"]] = Requirement(
            code=r["code"], name=r["name"], category=r["category"], kind=r["kind"], summary=r["summary"],
            description=r.get("description"), cost=_money(r.get("cost"), where), days=_span(r.get("days"), where),
            variants=tuple(variants), extras=r.get("extras", {}), legal_basis=r.get("legal_basis"),
            mandatory_for=r.get("mandatory_for"), source_url=r["source_url"], source_ref=r.get("source_ref"),
            source_text=_source_text(r["passages"], where), text_origin=r["text_origin"],
            status=r["verification_status"], last_reviewed=r["last_reviewed"], position=r.get("position", 0),
            prerequisites=tuple(prereq[r["code"]]), issuers=tuple(issuers[r["code"]]))

    rules: dict[str, list[Rule]] = {p["code"]: [] for p in raw["programmes"]}
    seen: set[tuple[str, str]] = set()
    for r in raw["rules"]:
        where = f"rule {r['code']}"
        # A rule quoted from the regulation was read on the day of the seed; one quoted from the
        # research notes was last reviewed when those were written, unless it says otherwise.
        r.setdefault("last_reviewed", raw["reviewed"] if r.get("text_origin") == "primary" else raw["notes_reviewed"])
        _common(r, where)
        _need(r["obligation"] in OBLIGATIONS and r["kind"] in RULE_KINDS, f"{where}: obligation or kind")
        _need(r.get("requirement") is None or r["requirement"] in codes, f"{where}: unknown requirement")
        for key in ("applies_when", "condition", "conditional_when"):
            if r.get(key) is not None:
                try:
                    validate_expr(r[key], codes)
                except ExprError as exc:
                    raise SeedError(f"{where}: {key}: {exc}") from None
        texts = r["texts"]
        if r.get("condition") is None:
            _need("info" in texts, f"{where}: an information rule needs texts.info")
            _need(r.get("conditional_when") is None, f"{where}: conditional_when needs a condition")
        else:
            _need({"met", "not_met"} <= set(texts), f"{where}: texts needs met and not_met")
            # a condition that reads a profile field can be unknown; one that reads statuses cannot
            _need("unknown" in texts or not fields_in(r["condition"]), f"{where}: texts.unknown is missing")
        if r.get("conditional_when") is not None:
            _need("conditional" in texts, f"{where}: texts.conditional is missing")
        if r.get("applies_when") is not None:
            _need("not_applicable" in texts, f"{where}: texts.not_applicable is missing")
        source_text = _source_text(r["passages"], where)
        for programme in r["programmes"]:
            _need(programme in rules, f"{where}: unknown programme {programme}")
            _need((programme, r["code"]) not in seen, f"{where}: duplicate in {programme}")
            seen.add((programme, r["code"]))
            rules[programme].append(Rule(
                programme=programme, code=r["code"], title=r["title"], obligation=r["obligation"], kind=r["kind"],
                requirement=r.get("requirement"), applies_when=r.get("applies_when"), condition=r.get("condition"),
                conditional_when=r.get("conditional_when"), texts=texts, note=r.get("note"),
                denominator=r.get("denominator"), source_url=r["source_url"], source_ref=r["source_ref"],
                source_text=source_text, text_origin=r["text_origin"], status=r["verification_status"],
                last_reviewed=r["last_reviewed"], position=r.get("position", 0)))

    known = {r.code for rs in rules.values() for r in rs}
    for r in requirements.values():
        missing = set(r.extras.get("rules", [])) - known
        _need(not missing, f"requirement {r.code}: extras.rules names unknown rules {sorted(missing)}")

    programmes: dict[str, Programme] = {}
    for p in raw["programmes"]:
        _need(p["kind"] in ("programme", "route", "general") and bool(p["source_url"]), f"programme {p['code']}")
        programmes[p["code"]] = Programme(
            code=p["code"], name=p["name"], summary=p["summary"], kind=p["kind"], legal_basis=p.get("legal_basis"),
            source_url=p["source_url"], call_programme=p.get("call_programme"), last_reviewed=raw["reviewed"],
            position=p.get("position", 0), rules=tuple(sorted(rules[p["code"]], key=lambda x: (x.position, x.code))))
    return Content(programmes=programmes, requirements=requirements, reviewed=raw["reviewed"])


def load_file(path: Path = SEED_PATH) -> Content:
    return parse(json.loads(path.read_text(encoding="utf-8")))


# --------------------------------------------------------------------------- database

def _j(value: Any) -> str | None:
    return None if value is None else json.dumps(value)


def apply(conn: psycopg.Connection, content: Content) -> dict[str, int]:
    """Write the content. Returns how many rows were inserted and how many switched off."""
    counts = {"inserted": 0, "deactivated": 0}

    def upsert(sql: str, args: tuple[Any, ...]) -> Any:
        row = conn.execute(sql, args).fetchone()
        counts["inserted"] += 1 if row["inserted"] else 0
        return row

    for p in content.programmes.values():
        upsert("""INSERT INTO readiness_programme
                    (code, name, summary, kind, legal_basis, source_url, call_programme_code, last_reviewed, position, active)
                  VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,TRUE)
                  ON CONFLICT (code) DO UPDATE SET name=EXCLUDED.name, summary=EXCLUDED.summary, kind=EXCLUDED.kind,
                    legal_basis=EXCLUDED.legal_basis, source_url=EXCLUDED.source_url,
                    call_programme_code=EXCLUDED.call_programme_code, last_reviewed=EXCLUDED.last_reviewed,
                    position=EXCLUDED.position, active=TRUE
                  RETURNING (xmax = 0) AS inserted""",
               (p.code, p.name, p.summary, p.kind, p.legal_basis, p.source_url, p.call_programme, p.last_reviewed, p.position))
    ids: dict[str, int] = {}
    for r in content.requirements.values():
        c, d = r.cost, r.days
        row = upsert("""INSERT INTO requirement
                    (code, name, category, kind, summary, description, typical_cost_min, typical_cost_max, cost_currency,
                     cost_basis, cost_text, cost_alt, typical_days_min, typical_days_max, duration_text, duration_note,
                     variants, extras, legal_basis, mandatory_for, source_url, source_ref, source_text, text_origin,
                     verification_status, last_reviewed, position, active)
                  VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s,%s,%s,%s,%s,%s,%s,%s,%s,TRUE)
                  ON CONFLICT (code) DO UPDATE SET name=EXCLUDED.name, category=EXCLUDED.category, kind=EXCLUDED.kind,
                    summary=EXCLUDED.summary, description=EXCLUDED.description, typical_cost_min=EXCLUDED.typical_cost_min,
                    typical_cost_max=EXCLUDED.typical_cost_max, cost_currency=EXCLUDED.cost_currency,
                    cost_basis=EXCLUDED.cost_basis, cost_text=EXCLUDED.cost_text, cost_alt=EXCLUDED.cost_alt,
                    typical_days_min=EXCLUDED.typical_days_min, typical_days_max=EXCLUDED.typical_days_max,
                    duration_text=EXCLUDED.duration_text, duration_note=EXCLUDED.duration_note,
                    variants=EXCLUDED.variants, extras=EXCLUDED.extras, legal_basis=EXCLUDED.legal_basis,
                    mandatory_for=EXCLUDED.mandatory_for, source_url=EXCLUDED.source_url, source_ref=EXCLUDED.source_ref,
                    source_text=EXCLUDED.source_text, text_origin=EXCLUDED.text_origin,
                    verification_status=EXCLUDED.verification_status, last_reviewed=EXCLUDED.last_reviewed,
                    position=EXCLUDED.position, active=TRUE
                  RETURNING id, (xmax = 0) AS inserted""",
                   (r.code, r.name, r.category, r.kind, r.summary, r.description,
                    c.min if c else None, c.max if c else None, c.currency if c else None, c.basis if c else None,
                    c.text if c else None, _j(c.alt if c else None), d.min if d else None, d.max if d else None,
                    d.text if d else None, d.note if d else None,
                    json.dumps([{"when_held": v.when_held, "cost": asdict(v.cost) if v.cost else None,
                                 "days": asdict(v.days) if v.days else None, "source_text": v.source_text}
                                for v in r.variants]),
                    json.dumps(r.extras), r.legal_basis, r.mandatory_for, r.source_url, r.source_ref, r.source_text,
                    r.text_origin, r.status, r.last_reviewed, r.position))
        ids[r.code] = row["id"]
    for r in content.requirements.values():
        for pre, relation in r.prerequisites:
            upsert("""INSERT INTO requirement_prerequisite (requirement_id, prerequisite_id, relation)
                      VALUES (%s,%s,%s) ON CONFLICT (requirement_id, prerequisite_id)
                      DO UPDATE SET relation = EXCLUDED.relation RETURNING (xmax = 0) AS inserted""",
                   (ids[r.code], ids[pre], relation))
        for i in r.issuers:
            upsert("""INSERT INTO requirement_issuer (requirement_id, country, issuer_name, issuer_url, notes, verification_status, active)
                      VALUES (%s,%s,%s,%s,%s,%s,TRUE)
                      ON CONFLICT (requirement_id, country, issuer_name) DO UPDATE SET issuer_url=EXCLUDED.issuer_url,
                        notes=EXCLUDED.notes, verification_status=EXCLUDED.verification_status, active=TRUE
                      RETURNING (xmax = 0) AS inserted""",
                   (ids[r.code], i.country, i.name, i.url, i.notes, i.status))
    for p in content.programmes.values():
        for x in p.rules:
            upsert("""INSERT INTO programme_requirement
                        (programme_code, rule_code, requirement_id, title, obligation, rule_kind, applies_when, condition_expr,
                         conditional_when, texts, note, denominator, source_url, source_ref, source_text, text_origin,
                         verification_status, last_reviewed, position, active)
                      VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s::jsonb,%s::jsonb,%s,%s,%s,%s,%s,%s,%s,%s,%s,TRUE)
                      ON CONFLICT (programme_code, rule_code) DO UPDATE SET requirement_id=EXCLUDED.requirement_id,
                        title=EXCLUDED.title, obligation=EXCLUDED.obligation, rule_kind=EXCLUDED.rule_kind,
                        applies_when=EXCLUDED.applies_when, condition_expr=EXCLUDED.condition_expr,
                        conditional_when=EXCLUDED.conditional_when, texts=EXCLUDED.texts, note=EXCLUDED.note,
                        denominator=EXCLUDED.denominator, source_url=EXCLUDED.source_url, source_ref=EXCLUDED.source_ref,
                        source_text=EXCLUDED.source_text, text_origin=EXCLUDED.text_origin,
                        verification_status=EXCLUDED.verification_status, last_reviewed=EXCLUDED.last_reviewed,
                        position=EXCLUDED.position, active=TRUE
                      RETURNING (xmax = 0) AS inserted""",
                   (p.code, x.code, ids[x.requirement] if x.requirement else None, x.title, x.obligation, x.kind,
                    _j(x.applies_when), _j(x.condition), _j(x.conditional_when), json.dumps(x.texts), x.note,
                    x.denominator, x.source_url, x.source_ref, x.source_text, x.text_origin, x.status,
                    x.last_reviewed, x.position))

    # Switch off what the seed no longer lists (never delete).
    codes = [r for r in content.requirements]
    prog = [p for p in content.programmes]
    rule_keys = [f"{p.code}/{x.code}" for p in content.programmes.values() for x in p.rules]
    issuer_keys = [f"{i.requirement}/{i.country}/{i.name}" for r in content.requirements.values() for i in r.issuers]
    for sql, arg in (
        ("UPDATE requirement SET active = FALSE WHERE active AND NOT (code = ANY(%s))", codes),
        ("UPDATE readiness_programme SET active = FALSE WHERE active AND NOT (code = ANY(%s))", prog),
        ("""UPDATE programme_requirement SET active = FALSE WHERE active
             AND NOT ((programme_code || '/' || rule_code) = ANY(%s))""", rule_keys),
        ("""UPDATE requirement_issuer i SET active = FALSE FROM requirement r WHERE r.id = i.requirement_id AND i.active
             AND NOT ((r.code || '/' || i.country || '/' || i.issuer_name) = ANY(%s))""", issuer_keys),
    ):
        counts["deactivated"] += conn.execute(sql, (arg,)).rowcount
    return counts


def _m(row: dict[str, Any]) -> Money | None:
    if row["cost_basis"] is None:
        return None
    alt = row["cost_alt"]
    return Money(float(row["typical_cost_min"]), float(row["typical_cost_max"]), (row["cost_currency"] or None),
                 row["cost_basis"], row["cost_text"], alt)


def _variant_money(raw: dict[str, Any] | None) -> Money | None:
    return None if raw is None else Money(raw["min"], raw["max"], raw["currency"], raw["basis"], raw["text"], raw["alt"])


def _variant_span(raw: dict[str, Any] | None) -> Span | None:
    return None if raw is None else Span(raw["min"], raw["max"], raw["text"], raw["note"])


def read_content(conn: psycopg.Connection) -> Content:
    """The active content, as the API serves it."""
    reqs = conn.execute("SELECT * FROM requirement WHERE active ORDER BY position, code").fetchall()
    by_id = {r["id"]: r["code"] for r in reqs}
    pre: dict[str, list[tuple[str, str]]] = {r["code"]: [] for r in reqs}
    for p in conn.execute("SELECT requirement_id, prerequisite_id, relation FROM requirement_prerequisite ORDER BY prerequisite_id").fetchall():
        if p["requirement_id"] in by_id and p["prerequisite_id"] in by_id:
            pre[by_id[p["requirement_id"]]].append((by_id[p["prerequisite_id"]], p["relation"]))
    iss: dict[str, list[Issuer]] = {r["code"]: [] for r in reqs}
    for i in conn.execute("SELECT * FROM requirement_issuer WHERE active ORDER BY country, id").fetchall():
        if i["requirement_id"] in by_id:
            code = by_id[i["requirement_id"]]
            iss[code].append(Issuer(code, i["country"], i["issuer_name"], i["issuer_url"], i["notes"], i["verification_status"]))
    requirements = {}
    for r in reqs:
        days = None
        if r["typical_days_min"] is not None:
            days = Span(r["typical_days_min"], r["typical_days_max"], r["duration_text"], r["duration_note"])
        requirements[r["code"]] = Requirement(
            code=r["code"], name=r["name"], category=r["category"], kind=r["kind"], summary=r["summary"],
            description=r["description"], cost=_m(r), days=days,
            variants=tuple(Variant(v["when_held"], _variant_money(v["cost"]), _variant_span(v["days"]), v["source_text"])
                           for v in r["variants"]),
            extras=r["extras"], legal_basis=r["legal_basis"], mandatory_for=r["mandatory_for"],
            source_url=r["source_url"], source_ref=r["source_ref"], source_text=r["source_text"],
            text_origin=r["text_origin"], status=r["verification_status"], last_reviewed=r["last_reviewed"].isoformat(),
            position=r["position"], prerequisites=tuple(pre[r["code"]]), issuers=tuple(iss[r["code"]]))
    rules: dict[str, list[Rule]] = {}
    for x in conn.execute("SELECT * FROM programme_requirement WHERE active ORDER BY position, rule_code").fetchall():
        rules.setdefault(x["programme_code"], []).append(Rule(
            programme=x["programme_code"], code=x["rule_code"], title=x["title"], obligation=x["obligation"],
            kind=x["rule_kind"], requirement=by_id.get(x["requirement_id"]), applies_when=x["applies_when"],
            condition=x["condition_expr"], conditional_when=x["conditional_when"], texts=x["texts"], note=x["note"],
            denominator=x["denominator"], source_url=x["source_url"], source_ref=x["source_ref"],
            source_text=x["source_text"], text_origin=x["text_origin"], status=x["verification_status"],
            last_reviewed=x["last_reviewed"].isoformat(), position=x["position"]))
    programmes = {}
    reviewed = ""
    for p in conn.execute("SELECT * FROM readiness_programme WHERE active ORDER BY position, code").fetchall():
        reviewed = max(reviewed, p["last_reviewed"].isoformat())
        programmes[p["code"]] = Programme(
            code=p["code"], name=p["name"], summary=p["summary"], kind=p["kind"], legal_basis=p["legal_basis"],
            source_url=p["source_url"], call_programme=p["call_programme_code"],
            last_reviewed=p["last_reviewed"].isoformat(), position=p["position"],
            rules=tuple(rules.get(p["code"], [])))
    return Content(programmes=programmes, requirements=requirements, reviewed=reviewed)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Load the readiness content (requirements, issuers, rules)")
    ap.add_argument("--check", action="store_true", help="validate the seed file only; touch no database")
    ap.add_argument("--file", type=Path, default=SEED_PATH)
    a = ap.parse_args(argv)
    content = load_file(a.file)
    n_rules = sum(len(p.rules) for p in content.programmes.values())
    summary = f"{len(content.programmes)} programmes, {len(content.requirements)} requirements, {n_rules} rules"
    if a.check:
        print(f"seed ok: {summary}")
        return 0
    from .. import db
    from ..config import settings

    with db.connect(settings().dsn) as conn:
        counts = apply(conn, content)
    print(f"seed applied: {summary}; {counts['inserted']} rows inserted, {counts['deactivated']} switched off")
    return 0


if __name__ == "__main__":
    sys.exit(main())
