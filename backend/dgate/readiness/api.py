"""The readiness API: the public requirements catalogue and the stateless assessment.

    GET  /v1/requirements                      the catalogue
    GET  /v1/requirements/{code}               one requirement with its issuers, rules and sources
    GET  /v1/requirements/{code}/issuers?country=XX
    GET  /v1/readiness/programmes              the rules, public
    POST /v1/readiness/assess                  the verdict for a profile sent in the body

Nothing about a company is stored or logged. `assess` receives the profile and the statuses in the
request body, computes with the pure engine and returns; it opens no write, keeps no copy, and a
body that is refused is not echoed back (the default 422 of the framework repeats the input).
Content (the rules) is read from the database, kept in memory for the list-cache time.
"""

from __future__ import annotations

import re
import threading
import time
from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .. import db
from ..config import settings
from ..suppress import removed
from . import engine, roadmap
from .content import Content, Money, Requirement, Rule
from .seed import read_content

router = APIRouter()

CODE = re.compile(r"^REQ-[A-Z0-9-]{1,30}$")
MAX_STATUSES = 40
NOTICE = ("This is a structured reading of the rules of each programme, with the text of the regulation "
          "beside every line. It is not legal advice and it does not replace the call text or the "
          "contracting authority. It does not cover the exclusion criteria and the financial and operational "
          "capacity checks of the Financial Regulation, or the conditions each call sets. The answers were not stored.")
# ISO 3166-1 alpha-2, as the profile takes it, and XX for a country that is not listed. "EL" (Greece in
# EU usage) and "UK" are read as GR and GB: left alone they would be taken for countries outside the EU.
ISO_COUNTRIES = frozenset((
    "AD AE AF AG AI AL AM AO AQ AR AS AT AU AW AX AZ BA BB BD BE BF BG BH BI BJ BL BM BN BO BQ BR BS BT BV BW BY BZ "
    "CA CC CD CF CG CH CI CK CL CM CN CO CR CU CV CW CX CY CZ DE DJ DK DM DO DZ EC EE EG EH ER ES ET FI FJ FK FM FO FR "
    "GA GB GD GE GF GG GH GI GL GM GN GP GQ GR GS GT GU GW GY HK HM HN HR HT HU ID IE IL IM IN IO IQ IR IS IT JE JM JO "
    "JP KE KG KH KI KM KN KP KR KW KY KZ LA LB LC LI LK LR LS LT LU LV LY MA MC MD ME MF MG MH MK ML MM MN MO MP MQ MR "
    "MS MT MU MV MW MX MY MZ NA NC NE NF NG NI NL NO NP NR NU NZ OM PA PE PF PG PH PK PL PM PN PR PS PT PW PY QA RE RO "
    "RS RU RW SA SB SC SD SE SG SH SI SJ SK SL SM SN SO SR SS ST SV SX SY SZ TC TD TF TG TH TJ TK TL TM TN TO TR TT TV "
    "TW TZ UA UG UM US UY UZ VA VC VE VG VI VN VU WF WS YE YT ZA ZM ZW XX").split())
COUNTRY_ALIASES = {"EL": "GR", "UK": "GB"}
MAX_BIGINT = 9_223_372_036_854_775_807


def get_conn():
    cfg = settings()
    with db.connect(cfg.api_dsn or cfg.dsn) as conn:
        yield conn


# --------------------------------------------------------------------------- content cache

_lock = threading.Lock()
_cached: tuple[float, Content] | None = None


def reset_cache() -> None:
    global _cached
    with _lock:
        _cached = None


def content(conn) -> Content:
    """The active content. Kept for the list-cache time (60 s; 0 in the tests): a rule edit is live
    within a minute of the worker applying the seed."""
    global _cached
    ttl = settings().list_cache_seconds
    now = time.monotonic()
    with _lock:
        if ttl > 0 and _cached and _cached[0] > now:
            return _cached[1]
    fresh = read_content(conn)
    if not fresh.programmes:
        # The worker applies the seed when it starts. Until then the honest answer is "not yet", not an
        # assessment against no rules, which would read as "eligible".
        raise HTTPException(503, "the rules are not loaded yet", headers={"Retry-After": "30"})
    if ttl > 0:
        with _lock:
            _cached = (now + ttl, fresh)
    return fresh


# --------------------------------------------------------------------------- shapes

def _money(m: Money | None) -> dict[str, Any] | None:
    return roadmap._money(m)


def _requirement_summary(r: Requirement, c: Content) -> dict[str, Any]:
    programmes = sorted({x.programme for x in c.rules_of(r.code)})
    return {
        "code": r.code, "name": r.name, "category": r.category, "kind": r.kind, "summary": r.summary,
        "cost": _money(r.cost), "days": roadmap._span(r.days), "mandatoryFor": r.mandatory_for,
        "programmes": programmes, "verificationStatus": r.status, "lastReviewed": r.last_reviewed,
        "sourceUrl": r.source_url,
    }


def _issuer(i) -> dict[str, Any]:
    return {"country": i.country, "name": i.name, "url": i.url, "notes": i.notes, "verificationStatus": i.status}


def _rule_public(x: Rule) -> dict[str, Any]:
    return {
        "programme": x.programme, "rule": x.code, "title": x.title, "obligation": x.obligation, "kind": x.kind,
        "requirement": x.requirement, "appliesWhen": x.applies_when, "condition": x.condition,
        "conditionalWhen": x.conditional_when, "texts": x.texts, "note": x.note, "denominator": x.denominator,
        "reads": engine.fields_in(x.condition),
        "source": _source(x.source_url, x.source_ref, x.source_text, x.text_origin, x.status, x.last_reviewed),
    }


def _source(url: str, ref: str | None, text: str | None, origin: str, status: str, reviewed: str) -> dict[str, Any]:
    return {"url": url, "ref": ref, "text": text, "origin": origin, "verificationStatus": status, "lastReviewed": reviewed}


def _result(r: engine.RuleResult) -> dict[str, Any]:
    return {
        "rule": r.rule, "title": r.title, "outcome": r.outcome, "reason": r.reason, "obligation": r.obligation,
        "kind": r.kind, "requirement": r.requirement, "note": r.note, "denominator": r.denominator,
        "asks": [{"field": f, "question": engine.FIELDS[f]["label"]} for f in r.asks],
        "source": _source(r.source_url, r.source_ref, r.source_text, r.text_origin, r.verification_status, r.last_reviewed),
    }


def _assessment(a: engine.Assessment, c: Content) -> dict[str, Any]:
    p = c.programmes[a.programme]
    return {
        "programme": a.programme, "name": a.name, "kind": a.kind, "summary": p.summary, "legalBasis": p.legal_basis,
        "sourceUrl": p.source_url, "verdict": a.verdict, "incomplete": a.incomplete, "blocking": list(a.blocking),
        "conditions": list(a.conditions), "toObtain": list(a.to_obtain), "counts": a.summary,
        "missing": [{"field": f, "question": engine.FIELDS[f]["label"]} for f in a.missing],
        "rules": [_result(r) for r in a.rules],
    }


# --------------------------------------------------------------------------- catalogue

def catalogue_payload(c: Content) -> dict[str, Any]:
    items = [_requirement_summary(r, c) for r in sorted(c.requirements.values(), key=lambda r: (r.position, r.code))]
    return {"items": items, "total": len(items), "meta": {"rulesReviewed": c.reviewed}}


def requirement_payload(c: Content, code: str) -> dict[str, Any]:
    r = c.requirements[code]
    out = _requirement_summary(r, c)
    out.update({
        "description": r.description, "legalBasis": r.legal_basis,
        "durationNote": r.days.note if r.days else None,
        "variants": [{"whenHeld": v.when_held, "cost": _money(v.cost), "days": roadmap._span(v.days),
                      "sourceText": v.source_text} for v in r.variants],
        "extras": r.extras,
        "prerequisites": [{"code": p, "name": c.requirements[p].name, "relation": rel} for p, rel in r.prerequisites],
        "requiredBy": sorted({q.code for q in c.requirements.values() if any(p == r.code for p, _ in q.prerequisites)}),
        "issuers": [_issuer(i) for i in r.issuers],
        "rules": [{**{k: v for k, v in _rule_public(x).items() if k in
                      ("programme", "rule", "title", "obligation", "kind", "texts", "note", "source")},
                   "programmeName": c.programmes[x.programme].name}
                  for x in c.rules_of(r.code)],
        "source": _source(r.source_url, r.source_ref, r.source_text, r.text_origin, r.status, r.last_reviewed),
        "vendorRangeLabel": roadmap.VENDOR_LABEL if r.cost and r.cost.basis == "vendor_range" else None,
    })
    return out


@router.get("/v1/requirements")
def list_requirements(conn=Depends(get_conn)):
    return catalogue_payload(content(conn))


@router.get("/v1/requirements/{code}")
def get_requirement(code: str = Path(pattern=CODE.pattern, max_length=40), conn=Depends(get_conn)):
    c = content(conn)
    if code not in c.requirements:
        raise HTTPException(404, "no such requirement")
    return requirement_payload(c, code)


@router.get("/v1/requirements/{code}/issuers")
def get_issuers(code: str = Path(pattern=CODE.pattern, max_length=40),
                country: str | None = Query(default=None, pattern=r"^[A-Za-z]{2}$"), conn=Depends(get_conn)):
    c = content(conn)
    if code not in c.requirements:
        raise HTTPException(404, "no such requirement")
    r = c.requirements[code]
    wanted = country.upper() if country else None
    if wanted:
        issuers = c.issuers_for(code, wanted)
    else:
        issuers = list(r.issuers)
    return {
        "requirement": code, "country": wanted, "issuers": [_issuer(i) for i in issuers],
        "note": None if issuers else "The body that issues this has not been collected for this country.",
    }


# --------------------------------------------------------------------------- the rules

def programmes_payload(c: Content) -> dict[str, Any]:
    return {
        "programmes": [{
            "code": p.code, "name": p.name, "summary": p.summary, "kind": p.kind, "legalBasis": p.legal_basis,
            "sourceUrl": p.source_url, "callProgramme": p.call_programme, "lastReviewed": p.last_reviewed,
            "rules": [_rule_public(x) for x in p.rules]} for p in sorted(c.programmes.values(), key=lambda p: (p.position, p.code))],
        "fields": {k: {"kind": v["kind"], "question": v["label"], **({"values": list(v["values"])} if "values" in v else {})}
                   for k, v in engine.FIELDS.items()},
        "groups": {k: sorted(v) for k, v in engine.GROUPS.items()},
        "statuses": list(engine.STATUS_VALUES),
        "meta": {"rulesReviewed": c.reviewed},
    }


@router.get("/v1/readiness/programmes")
def list_programmes(conn=Depends(get_conn)):
    return programmes_payload(content(conn))


# --------------------------------------------------------------------------- the assessment

class ProfileIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    country: str = Field(pattern=r"^[A-Z]{2}$")
    legal_form: Literal["legal_person", "natural_person", "no_legal_personality"] | None = None
    executive_management_country: str | None = Field(default=None, pattern=r"^[A-Z]{2}$")
    third_country_control: Literal["no", "ua_eea_only", "other"] | None = None
    ua_non_government_controlled_area: bool | None = None
    non_eu_component_cost_pct: float | None = Field(default=None, ge=0, le=100)
    restricted_third_country_component: bool | None = None
    components_from_ua_or_eea_efta: bool | None = None
    safe_role: Literal["contractor", "subcontractor_involved", "other_supplier"] | None = None
    handles_classified: bool | None = None
    product_regime: Literal["none", "dual_use", "military", "unknown"] = "unknown"
    export_intent: Literal["none", "within_eu", "outside_eu", "unsure"] | None = None

    @field_validator("country", "executive_management_country")
    @classmethod
    def _known_country(cls, v: str | None) -> str | None:
        v = COUNTRY_ALIASES.get(v, v) if v else v
        if v is not None and v not in ISO_COUNTRIES:
            raise ValueError("country: an ISO 3166-1 alpha-2 code, or XX for a country that is not listed")
        return v

    def to_engine(self) -> engine.Profile:
        return engine.Profile(**self.model_dump())


class AssessIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    profile: ProfileIn
    statuses: dict[str, Literal["held", "in_progress", "not_held", "not_applicable"]] = Field(default_factory=dict)
    programmes: list[str] | None = Field(default=None, max_length=12)
    call: int | None = Field(default=None, ge=1, le=MAX_BIGINT)

    @field_validator("statuses")
    @classmethod
    def _bounded(cls, v: dict[str, str]) -> dict[str, str]:
        if len(v) > MAX_STATUSES or any(not CODE.match(k) for k in v):
            raise ValueError("statuses: too many, or a code that is not a requirement code")
        return v

    @field_validator("programmes")
    @classmethod
    def _codes(cls, v: list[str] | None) -> list[str] | None:
        if v is not None and any(not re.match(r"^[A-Z][A-Z-]{1,19}$", p) for p in v):
            raise ValueError("programmes: codes in capitals")
        return v


def assess_payload(c: Content, profile: engine.Profile, statuses: dict[str, str],
                   programmes: list[str] | None = None) -> dict[str, Any]:
    """The whole answer for one profile, a pure function of the content: the verdict of each programme,
    the rules that apply to every route, and the roadmap. Raises KeyError for an unknown programme."""
    chosen = [p for p in sorted(c.programmes.values(), key=lambda p: (p.position, p.code)) if p.kind != "general"]
    if programmes is not None:
        missing = set(programmes) - set(c.programmes)
        if missing:
            raise KeyError(sorted(missing)[0])
        chosen = [p for p in chosen if p.code in set(programmes)]
    assessments = [engine.assess(profile, statuses, p) for p in chosen]
    general = [engine.assess(profile, statuses, p) for p in c.programmes.values() if p.kind == "general"]
    plan = roadmap.build_roadmap([*assessments, *general], statuses, c, profile.country)
    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "rulesReviewed": c.reviewed,
        "assessments": [_assessment(a, c) for a in assessments],
        "general": [_assessment(a, c) for a in general],
        "roadmap": plan,
        "call": None,
        "notice": NOTICE,
    }


@router.post("/v1/readiness/assess")
def assess(body: AssessIn, conn=Depends(get_conn)):
    c = content(conn)
    if any(k not in c.requirements for k in body.statuses):
        raise HTTPException(422, "unknown requirement code")
    profile = body.profile.to_engine()
    try:
        out = assess_payload(c, profile, body.statuses, body.programmes)
    except KeyError:
        raise HTTPException(422, "unknown programme") from None
    if body.call:
        out["call"] = _call(conn, c, body.call, body.statuses, profile)
    return out


def _call(conn, c: Content, call_id: int, statuses, profile) -> dict[str, Any]:
    """The cross-layer question: can I take part in this call before it closes, and if not, what is the
    fastest path? Reads one call; the rest is the pure engine and roadmap."""
    from ..funding import SELECT

    row = conn.execute(SELECT + " WHERE c.id = %s", (call_id,)).fetchone()
    if not row:
        raise HTTPException(404, "no such call")
    if row["suppressed"]:
        raise removed()
    out: dict[str, Any] = {"id": str(call_id), "title": row["title"], "programme": row["programme_code"],
                           "status": row["effective_status"], "deadline": row["deadline_at"].isoformat() if row["deadline_at"] else None,
                           "timings": []}
    now = datetime.now(timezone.utc)
    mapped = [p for p in c.programmes.values() if p.call_programme == row["programme_code"]]
    out["covered"] = bool(mapped)
    if not mapped:
        out["text"] = ("No readiness rules are encoded for the programme of this call, so no verdict is given.")
        return out
    for p in mapped:
        a = engine.assess(profile, statuses, p)
        plan = roadmap.build_roadmap([a], statuses, c, profile.country)
        timing = roadmap.call_timing(a, plan, row["deadline_at"], now)
        timing["name"] = p.name
        out["timings"].append(timing)
    if row["effective_status"] == "closed":
        out["text"] = "The call is closed."
    return out
