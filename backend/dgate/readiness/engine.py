"""The rules engine: `assess(profile, statuses, programme) -> Assessment`.

A pure function. No database, no clock, no network, no model: the same inputs always give the
same output, and every line of the output can be traced to a rule and the verbatim text of its
source. The rules themselves are data (`seeds/requirements.json`, tables `programme_requirement`).

The language of a rule's expression is small (everything is three-valued: true, false, or
unknown when an answer is missing, so a question left unanswered never reads as "no"):

    {"all": [expr, ...]}                       every one true
    {"any": [expr, ...]}                       at least one true
    {"not": expr}
    {"field": "country", "is": "ES"}           a profile field equals a value (also true/false)
    {"field": "country", "in": ["EU", "UA"]}   a field is one of the values; for the two country
                                               fields the names EU, EEA_EFTA and UA stand for the
                                               members of those groups
    {"status": "REQ-PIC", "is": "held"}        the company's status of a requirement; "in": [...]
    {"threshold": {"field": "non_eu_component_cost_pct", "lte": 35}}     lte, lt, gte, gt

A rule has up to three expressions: `applies_when` (false: the rule is not applicable), `condition`
(true: met) and `conditional_when` (consulted only when the condition is false: true means a
derogation may apply, so the outcome is "conditional" and not "not met").

A mandatory rule of kind "registration" (the PIC, the NCAGE code) that is not met has the outcome
`to_obtain`: it is something to obtain first, not a block. The verdict of a programme is `blocked` if a
mandatory rule is not met, else `conditional` if a derogation or an answer is open, else `obtain` if only
registrations are missing, else `eligible`.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from .content import Content, Expr, Programme, Rule

EU27 = frozenset("AT BE BG HR CY CZ DK EE FI FR DE GR HU IE IT LV LT LU MT NL PL PT RO SK SI ES SE".split())
EEA_EFTA = frozenset({"IS", "LI", "NO"})
GROUPS: dict[str, frozenset[str]] = {"EU": EU27, "EEA_EFTA": EEA_EFTA, "UA": frozenset({"UA"})}
OTHER_COUNTRY = "XX"      # a country that is not listed: the engine treats it as outside every group

# The profile fields a rule may read. kind: country | enum | bool | pct. The label is the question
# that is shown when the answer is missing.
FIELDS: dict[str, dict[str, Any]] = {
    "country": {"kind": "country", "label": "In which country is your company established?"},
    "legal_form": {"kind": "enum", "values": ("legal_person", "natural_person", "no_legal_personality"),
                   "label": "What is the legal form of your organisation: a legal person, a natural person (for example a sole trader), or an entity without legal personality?"},
    "executive_management_country": {"kind": "country", "label": "Where are your company's executive management structures established?"},
    "third_country_control": {"kind": "enum", "values": ("no", "ua_eea_only", "other"),
                              "label": "Is your company controlled by a country or an entity outside the EU?"},
    "ua_non_government_controlled_area": {"kind": "bool", "label": "Is your company established in an area of Ukraine that the Ukrainian government does not control?"},
    "non_eu_component_cost_pct": {"kind": "pct", "label": "What share of the estimated cost of the components of your end product originates outside the EU, the EEA EFTA states and Ukraine?"},
    "restricted_third_country_component": {"kind": "bool", "label": "Does any component of your end product come from a third country that contravenes the Union's security and defence interests?"},
    "components_from_ua_or_eea_efta": {"kind": "bool", "label": "Do any components of your end product originate in Ukraine or in an EEA EFTA state (Iceland, Liechtenstein, Norway)?"},
    "safe_role": {"kind": "enum", "values": ("contractor", "subcontractor_involved", "other_supplier"),
                  "label": "In a SAFE-supported procurement, would you be the contractor, a subcontractor that is allocated at least 15 % of the contract value, provides critical inputs and needs access to classified information, or another supplier?"},
    "handles_classified": {"kind": "bool", "label": "Will you handle classified information?"},
    "product_regime": {"kind": "enum", "values": ("none", "dual_use", "military", "unknown"),
                       "label": "Is your product in the dual-use regime, the military regime, or neither?"},
    "export_intent": {"kind": "enum", "values": ("none", "within_eu", "outside_eu", "unsure"),
                      "label": "Do you export or plan to export?"},
}
COUNTRY_FIELDS = frozenset(k for k, v in FIELDS.items() if v["kind"] == "country")
STATUS_VALUES = ("held", "in_progress", "not_held", "not_applicable")
THRESHOLD_OPS = {
    "lte": lambda a, b: a <= b, "lt": lambda a, b: a < b,
    "gte": lambda a, b: a >= b, "gt": lambda a, b: a > b,
}
OUTCOMES = ("met", "not_met", "to_obtain", "conditional", "unknown", "not_applicable", "info")
GENERIC = {
    "unknown": "Answer the questions that are missing to see whether this applies to you.",
    "not_applicable": "This rule does not apply to your company.",
}


class ExprError(ValueError):
    """An expression that is not in the language above."""


# --------------------------------------------------------------------------- the profile

@dataclass(frozen=True)
class Profile:
    """What the engine reads of a company. A field that is None is unknown, not "no"."""
    country: str
    legal_form: str | None = None
    executive_management_country: str | None = None
    third_country_control: str | None = None
    ua_non_government_controlled_area: bool | None = None
    non_eu_component_cost_pct: float | None = None
    restricted_third_country_component: bool | None = None
    components_from_ua_or_eea_efta: bool | None = None
    safe_role: str | None = None
    handles_classified: bool | None = None
    product_regime: str = "unknown"
    export_intent: str | None = None

    def fields(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in FIELDS}


# --------------------------------------------------------------------------- validation

def validate_expr(expr: Any, requirement_codes: set[str] | frozenset[str]) -> None:
    """Raise ExprError unless `expr` is a well-formed expression over known fields and codes.
    Used when the seed is loaded, so a typo in a rule is a failed load and not a silent "unknown"."""
    if not isinstance(expr, dict) or not expr:
        raise ExprError(f"an expression is a non-empty object: {expr!r}")
    if "all" in expr or "any" in expr:
        key = "all" if "all" in expr else "any"
        if len(expr) != 1 or not isinstance(expr[key], list) or not expr[key]:
            raise ExprError(f"'{key}' takes a non-empty list and nothing else: {expr!r}")
        for sub in expr[key]:
            validate_expr(sub, requirement_codes)
    elif "not" in expr:
        if len(expr) != 1:
            raise ExprError(f"'not' takes nothing else: {expr!r}")
        validate_expr(expr["not"], requirement_codes)
    elif "threshold" in expr:
        spec = expr["threshold"]
        ops = [k for k in spec if k in THRESHOLD_OPS] if isinstance(spec, dict) else []
        if (len(expr) != 1 or len(ops) != 1 or len(spec) != 2 or spec.get("field") not in FIELDS
                or FIELDS[spec["field"]]["kind"] != "pct" or isinstance(spec[ops[0]], bool)
                or not isinstance(spec[ops[0]], (int, float))):
            raise ExprError(f"a threshold names a percentage field and one number: {expr!r}")
    elif "field" in expr:
        _validate_comparison(expr, set(FIELDS), "field", FIELDS.get(expr["field"], {}).get("kind"))
    elif "status" in expr:
        _validate_comparison(expr, set(requirement_codes), "status", "status")
    else:
        raise ExprError(f"unknown expression: {expr!r}")


def _validate_comparison(expr: Expr, known: set[str], key: str, kind: str | None) -> None:
    if expr[key] not in known:
        raise ExprError(f"unknown {key} {expr[key]!r}")
    rest = {k: v for k, v in expr.items() if k != key}
    if len(rest) != 1 or next(iter(rest)) not in ("is", "in"):
        raise ExprError(f"a comparison takes 'is' or 'in': {expr!r}")
    op, value = next(iter(rest.items()))
    if op == "in" and (not isinstance(value, list) or not value):
        raise ExprError(f"'in' takes a non-empty list: {expr!r}")
    values = value if op == "in" else [value]
    if kind == "status":
        bad = [v for v in values if v not in STATUS_VALUES]
    elif kind == "country":
        bad = [v for v in values if not isinstance(v, str) or not (v in GROUPS or len(v) == 2)]
    elif kind == "enum":
        bad = [v for v in values if v not in FIELDS[expr[key]]["values"]]
    else:
        bad = [v for v in values if not isinstance(v, bool)] if kind == "bool" else values
    if bad:
        raise ExprError(f"value {bad!r} is not allowed for {expr[key]!r}")


def fields_in(expr: Expr | None) -> list[str]:
    """The profile fields an expression reads, in order, once each."""
    found: list[str] = []

    def walk(node: Expr) -> None:
        for key in ("all", "any"):
            if key in node:
                for sub in node[key]:
                    walk(sub)
        if "not" in node:
            walk(node["not"])
        name = node.get("field") or (node.get("threshold") or {}).get("field")
        if name and name not in found:
            found.append(name)

    if expr:
        walk(expr)
    return found


# --------------------------------------------------------------------------- evaluation

def _and(values: list[bool | None]) -> bool | None:
    if False in values:
        return False
    return None if None in values else True


def _or(values: list[bool | None]) -> bool | None:
    if True in values:
        return True
    return None if None in values else False


def evaluate(expr: Expr, fields: Mapping[str, Any], statuses: Mapping[str, str]) -> bool | None:
    """True, False, or None (unknown). The expression must have passed `validate_expr`."""
    if "all" in expr:
        return _and([evaluate(e, fields, statuses) for e in expr["all"]])
    if "any" in expr:
        return _or([evaluate(e, fields, statuses) for e in expr["any"]])
    if "not" in expr:
        inner = evaluate(expr["not"], fields, statuses)
        return None if inner is None else not inner
    if "threshold" in expr:
        spec = expr["threshold"]
        value = fields.get(spec["field"])
        if value is None:
            return None
        op = next(k for k in spec if k in THRESHOLD_OPS)
        return THRESHOLD_OPS[op](value, spec[op])
    if "status" in expr:
        # A requirement the company did not mention is not held.
        value = statuses.get(expr["status"], "not_held")
        return _compare(value, expr, set())
    name = expr["field"]
    value = fields.get(name)
    if value is None:
        return None
    return _compare(value, expr, COUNTRY_FIELDS if name in COUNTRY_FIELDS else set(), name)


def _compare(value: Any, expr: Expr, country_fields: set[str] | frozenset[str], name: str = "") -> bool:
    if "is" in expr:
        wanted = expr["is"]
        if isinstance(wanted, bool):
            return value is wanted
        return bool(value == wanted)
    allowed: set[Any] = set()
    for item in expr["in"]:
        allowed |= GROUPS[item] if name in country_fields and item in GROUPS else {item}
    return value in allowed


# --------------------------------------------------------------------------- assessment

@dataclass(frozen=True)
class RuleResult:
    rule: str
    title: str
    outcome: str
    reason: str
    obligation: str
    kind: str
    requirement: str | None
    note: str | None
    asks: tuple[str, ...]                 # the fields still to answer, for an "unknown"
    source_url: str
    source_ref: str
    source_text: str
    text_origin: str
    verification_status: str
    last_reviewed: str
    denominator: str | None = None


@dataclass(frozen=True)
class Assessment:
    programme: str
    name: str
    kind: str
    verdict: str                           # eligible | obtain | conditional | blocked
    incomplete: bool                       # an answer is missing, so "eligible" or "blocked" may change
    rules: tuple[RuleResult, ...]
    blocking: tuple[str, ...] = ()         # rule codes
    conditions: tuple[str, ...] = ()
    to_obtain: tuple[str, ...] = ()        # rule codes: a registration to obtain first (not a block)
    missing: tuple[str, ...] = ()          # profile fields to answer
    summary: dict[str, int] = field(default_factory=dict)

    @property
    def explanation(self) -> list[dict[str, str]]:
        """The plan's shape: the rule, its outcome, the reason and the source."""
        return [{"rule": r.rule, "outcome": r.outcome, "reason": r.reason, "source_url": r.source_url}
                for r in self.rules]


def assess_rule(rule: Rule, fields: Mapping[str, Any], statuses: Mapping[str, str]) -> RuleResult:
    outcome, asks = _outcome(rule, fields, statuses)
    # a registration that is missing is a to-do with the same words as "not met": the text says it is free
    reason = rule.texts.get(outcome) or (rule.texts["not_met"] if outcome == "to_obtain" else GENERIC.get(outcome, ""))
    return RuleResult(
        rule=rule.code, title=rule.title, outcome=outcome, reason=reason, obligation=rule.obligation,
        kind=rule.kind, requirement=rule.requirement, note=rule.note, asks=tuple(asks),
        source_url=rule.source_url, source_ref=rule.source_ref, source_text=rule.source_text,
        text_origin=rule.text_origin, verification_status=rule.status,
        last_reviewed=rule.last_reviewed, denominator=rule.denominator)


def _outcome(rule: Rule, fields: Mapping[str, Any], statuses: Mapping[str, str]) -> tuple[str, list[str]]:
    def missing(*exprs: Expr | None) -> list[str]:
        return [f for e in exprs for f in fields_in(e) if fields.get(f) is None]

    if rule.applies_when is not None:
        applies = evaluate(rule.applies_when, fields, statuses)
        if applies is False:
            return "not_applicable", []
        if applies is None:
            return "unknown", missing(rule.applies_when, rule.condition)
    if rule.condition is None:
        return "info", []
    met = evaluate(rule.condition, fields, statuses)
    if met is True:
        return "met", []
    if met is None:
        return "unknown", missing(rule.condition)
    if rule.conditional_when is not None:
        derogation = evaluate(rule.conditional_when, fields, statuses)
        if derogation is True:
            return "conditional", []
        if derogation is None:
            return "unknown", missing(rule.conditional_when)
    # D3: a registration that anybody can obtain (the PIC, the NCAGE code) is something to obtain first,
    # not a reason to call the company blocked.
    return ("to_obtain" if rule.kind == "registration" else "not_met"), []


def assess(profile: Profile, statuses: Mapping[str, str], programme: Programme | str,
           content: Content | None = None) -> Assessment:
    """The assessment of one programme. `programme` is a `Programme`, or its code with `content`."""
    if isinstance(programme, str):
        if content is None:
            raise ValueError("a programme code needs the content to look it up")
        programme = content.programmes[programme]
    fields = profile.fields()
    results = tuple(assess_rule(r, fields, statuses) for r in sorted(programme.rules, key=lambda r: (r.position, r.code)))
    mandatory = [r for r in results if r.obligation == "mandatory"]
    blocking = tuple(r.rule for r in mandatory if r.outcome == "not_met")
    conditions = tuple(r.rule for r in mandatory if r.outcome == "conditional")
    to_obtain = tuple(r.rule for r in mandatory if r.outcome == "to_obtain")
    unknown = [r for r in mandatory if r.outcome == "unknown"]
    missing: list[str] = []
    for r in results:
        for f in r.asks:
            if f not in missing:
                missing.append(f)
    if blocking:
        verdict = "blocked"
    elif conditions or unknown:
        verdict = "conditional"
    elif to_obtain:
        verdict = "obtain"
    else:
        verdict = "eligible"
    summary = {o: sum(1 for r in results if r.outcome == o) for o in OUTCOMES}
    return Assessment(
        programme=programme.code, name=programme.name, kind=programme.kind, verdict=verdict,
        incomplete=bool(unknown), rules=results, blocking=blocking, conditions=conditions,
        to_obtain=to_obtain, missing=tuple(missing), summary=summary)
