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

Which rules count (WP-73): every rule that is not only `recommended`. A rule whose obligation is `conditional` is binding wherever its
`applies_when` holds (the HSEM where classified information is handled: Ley 24/2011, art. 21.2), so it counts like a mandatory one; where
`applies_when` is false it is "not applicable" and counts for nothing. One exception: a `conditional` rule of kind `contract` (PECAL, EN 9100
for PECAL 2310) is what a contract may name, not a condition of the route, so when it is not met it is a condition and not a block.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from .content import Content, Expr, Programme, Rule

EU27 = frozenset("AT BE BG HR CY CZ DK EE FI FR DE GR HU IE IT LV LT LU MT NL PL PT RO SK SI ES SE".split())
EEA_EFTA = frozenset({"IS", "LI", "NO"})
GROUPS: dict[str, frozenset[str]] = {"EU": EU27, "EEA_EFTA": EEA_EFTA, "UA": frozenset({"UA"})}
OTHER_COUNTRY = "XX"      # a country that is not listed: the engine treats it as outside every group

# The profile fields a rule may read. kind: country | enum | bool | pct. The label is the question
# that is shown when the answer is missing.
APPLICANT_KINDS = ("company_or_research", "contracting_authority", "international_organisation", "seap", "eda")
ACTIONS = ("common_procurement", "seap_support", "edpci_preparation", "industrial_reinforcement")
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
    # A partner in the planned consortium (WP-53). Unanswered is unknown, never "no": the Ukraine Support Instrument asks for a Ukrainian
    # entity that the company itself may not be, and only the company can say whether it has one.
    "ua_partner": {"kind": "bool", "label": "Does your planned consortium include a legal entity established in Ukraine, with its executive management structure there?"},
    # Who the applicant is: only a few EDIP calls (common procurement) are open to anybody but a company or a
    # research body. Asked once, in the first step of the wizard.
    "applicant_kind": {"kind": "enum", "values": APPLICANT_KINDS,
                       "label": "What kind of organisation are you: a company or research body, a contracting authority, an international organisation, a SEAP (structure for European armament programmes) or the European Defence Agency?"},
    # Not a question: the kind of action of the call being judged (see `regime.action_of`). It is unknown outside a call,
    # and a rule that applies to one kind of action then does not apply.
    "action": {"kind": "enum", "context": True, "values": ACTIONS, "label": "The kind of action of the call"},
}
# The questions of the Spain, Germany and NATO/EU rules (WP-64, docs/research/ANGLE1_RULES_ES_DE_2026-10-20.md). The wizard
# does not ask them yet (the supplier profile is WP-65): a rule that reads one is "unknown", and the result names the question.
_YES_NO_UNSURE = ("yes", "no", "unsure")
SUPPLIER_FIELDS: dict[str, dict[str, Any]] = {
    "nato_icb_bid": {"kind": "bool", "label": "Do you want to bid in a NATO international competitive bidding tender (NATO Security Investment Programme)?"},
    "rid_capabilities_declared": {"kind": "bool", "label": "Have you declared your industrial capabilities in the Registro de la Industria de Defensa (RID)?"},
    "pecal_certificate_wanted": {"kind": "bool", "label": "Do you want the PECAL certificate of your quality management system itself, and not only to meet PECAL requirements inside a contract?"},
    "pecal_system_9_months": {"kind": "bool", "label": "Has your PECAL quality system been in place, and audited by your management, for at least nine months?"},
    "pecal_prior_contract": {"kind": "bool", "label": "In the last two years, have you had at least one Ministry of Defence contract with PECAL requirements, or a certificate of conformity signed by a DGAM quality representative (RAC)?"},
    "pecal_2310_target": {"kind": "bool", "label": "Do you target PECAL 2310 (aviation, space and defence)?"},
    "stores_classified": {"kind": "bool", "label": "Will classified information be stored on your own premises?"},
    "nato_classified_contract": {"kind": "bool", "label": "Does a NATO contract you target involve information classified NATO CONFIDENTIAL or higher?"},
    "nsfcc_held": {"kind": "bool", "label": "Do you hold a NATO Facility Security Clearance Certificate (NSFCC)?"},
    "nato_staff_cleared": {"kind": "bool", "label": "Do the staff who need access hold NATO personnel security clearances?"},
    "ncage_need_justified": {"kind": "bool", "label": "Is a product of yours bought by the Ministry of Defence (so that it must be catalogued), or do you need an NCAGE code to register in the US System for Award Management (SAM)?"},
    "specific_defence_use": {"kind": "bool", "label": "Is your product for specific defence use (Article 346 of the Treaty on the Functioning of the EU), rather than a civilian product?"},
    "homologation_mandatory": {"kind": "bool", "label": "Is your product on the Ministry of Defence's list of products for which homologation is mandatory?"},
    "homologated": {"kind": "bool", "label": "Is your product homologated by the Ministry of Defence?"},
    "es_defence_material_list": {"kind": "enum", "values": _YES_NO_UNSURE, "label": "Is the item in Annex I of Real Decreto 679/2014 (the Spanish list of defence material, Relación de Material de Defensa)?"},
    "foreign_capital": {"kind": "bool", "label": "Does a foreign investor hold shares in your company, directly or indirectly?"},
    "foreign_investor_authorised": {"kind": "bool", "label": "Does the foreign investor hold an administrative authorisation of the Spanish Council of Ministers?"},
    "receives_eea_defence_products": {"kind": "bool", "label": "Do you receive defence-related products from other EEA states?"},
    "certified_recipient": {"kind": "bool", "label": "Are you certified by your national authority as a recipient of defence-related products under the general transfer licences of other member states?"},
    "de_vs_vertraulich": {"kind": "bool", "label": "Will material classified VS-VERTRAULICH or higher be handed to you for processing and storage?"},
    "ghb_admitted": {"kind": "bool", "label": "Is your company already under the BMWE Geheimschutzbetreuung (with a security notice)?"},
    "de_vs_nfd": {"kind": "bool", "label": "Does the contract involve material classified VS-NUR FÜR DEN DIENSTGEBRAUCH (VS-NfD)?"},
    "vsnfd_declaration_signed": {"kind": "bool", "label": "Have you signed the commitment declaration (Verpflichtungserklärung) for VS-NfD?"},
    "vsnfd_merkblatt": {"kind": "bool", "label": "Does your contract incorporate the VS-NfD-Merkblatt (GHB Anlage 4)?"},
    "sibe_appointed": {"kind": "bool", "label": "Have you appointed a security officer (Sicherheitsbevollmächtigter, SiBe)?"},
    "de_ausfuhrliste": {"kind": "enum", "values": ("part_i_a", "part_i_b", "neither", "unsure"),
                        "label": "Is the item in the German export list (Ausfuhrliste) Part I Section A (arms) or Section B (national dual-use list)?"},
    "dualuse_annex_i": {"kind": "enum", "values": _YES_NO_UNSURE, "label": "Is your item listed in Annex I of Regulation (EU) 2021/821 (dual-use items)?"},
    "us_components": {"kind": "bool", "label": "Does your product contain components, technology or software of US origin?"},
}
FIELDS.update(SUPPLIER_FIELDS)
COUNTRY_FIELDS = frozenset(k for k, v in FIELDS.items() if v["kind"] == "country")
STATUS_VALUES = ("held", "in_progress", "not_held", "not_applicable")
# Not an answer: the status of a requirement the questionnaire does not ask (`unasked`). A rule that reads it is "unknown".
STATUS_UNKNOWN = "unknown"
THRESHOLD_OPS = {
    "lte": lambda a, b: a <= b, "lt": lambda a, b: a < b,
    "gte": lambda a, b: a >= b, "gt": lambda a, b: a > b,
}
OUTCOMES = ("met", "not_met", "to_obtain", "conditional", "unknown", "not_applicable", "info")
GENERIC = {
    "unknown": "Answer the questions that are missing to see whether this applies to you.",
    "not_applicable": "This rule does not apply to your company.",
}
# The company answered "Not applicable to us" for the requirement a rule reads (WP-53, T4). That is neither held nor missing:
# the rule is left out of the verdict, and the words say so instead of "You have a PIC".
DECLARED_NOT_APPLICABLE = ("You answered “Not applicable to us” for this requirement, so this rule is left out of your result. "
                           "It is not counted as met. If it does apply to you, change the answer.")


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
    applicant_kind: str | None = None
    ua_partner: bool | None = None
    action: str | None = None          # context of a call, never an answer of the company (the API does not take it)
    # WP-64: the questions of the Spain, Germany and NATO/EU rules (`SUPPLIER_FIELDS`)
    nato_icb_bid: bool | None = None
    rid_capabilities_declared: bool | None = None
    pecal_certificate_wanted: bool | None = None
    pecal_system_9_months: bool | None = None
    pecal_prior_contract: bool | None = None
    pecal_2310_target: bool | None = None
    stores_classified: bool | None = None
    nato_classified_contract: bool | None = None
    nsfcc_held: bool | None = None
    nato_staff_cleared: bool | None = None
    ncage_need_justified: bool | None = None
    specific_defence_use: bool | None = None
    homologation_mandatory: bool | None = None
    homologated: bool | None = None
    es_defence_material_list: str | None = None
    foreign_capital: bool | None = None
    foreign_investor_authorised: bool | None = None
    receives_eea_defence_products: bool | None = None
    certified_recipient: bool | None = None
    de_vs_vertraulich: bool | None = None
    ghb_admitted: bool | None = None
    de_vs_nfd: bool | None = None
    vsnfd_declaration_signed: bool | None = None
    vsnfd_merkblatt: bool | None = None
    sibe_appointed: bool | None = None
    de_ausfuhrliste: str | None = None
    dualuse_annex_i: str | None = None
    us_components: bool | None = None

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


def statuses_in(expr: Expr | None) -> list[str]:
    """The requirement codes an expression reads the status of, in order, once each."""
    found: list[str] = []

    def walk(node: Expr) -> None:
        for key in ("all", "any"):
            for sub in node.get(key, []):
                walk(sub)
        if "not" in node:
            walk(node["not"])
        if "status" in node and node["status"] not in found:
            found.append(node["status"])

    if expr:
        walk(expr)
    return found


def with_unasked(statuses: Mapping[str, str], unasked: Iterable[str]) -> dict[str, str]:
    """The statuses the engine reads: a requirement the questionnaire does not ask (`unasked`, its codes) and the company
    did not mention is `STATUS_UNKNOWN`, so a rule on it says "unknown" and asks, instead of reading "not held"."""
    out = {code: STATUS_UNKNOWN for code in unasked if code not in statuses}
    out.update(statuses)
    return out


def reads_status(expr: Expr | None, code: str) -> bool:
    """Whether an expression reads the company's status of a requirement."""
    if not expr:
        return False
    if expr.get("status") == code:
        return True
    return any(reads_status(sub, code) for key in ("all", "any") for sub in expr.get(key, [])) or reads_status(expr.get("not"), code)


def declared_not_applicable(rule: Rule, statuses: Mapping[str, str]) -> bool:
    """The company said "Not applicable to us" for the requirement this rule's condition is about."""
    return bool(rule.requirement) and statuses.get(rule.requirement or "") == "not_applicable" and reads_status(rule.condition, rule.requirement or "")


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
        if value == STATUS_UNKNOWN:
            return None
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
    # "consultant needed" (WP-64): the rule's `texts.consultant`, set when the rule is open or not met for this company
    consultant: str | None = None


# The outcomes for which a "consultant needed" flag is shown: never when the rule is met or does not apply.
CONSULTANT_OUTCOMES = ("not_met", "to_obtain", "conditional", "unknown", "info")


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


def counts(r: RuleResult) -> bool:
    """Whether a rule's outcome takes part in the verdict: every rule except a recommendation."""
    return r.obligation != "recommended"


def blocks(r: RuleResult) -> bool:
    """Whether a rule that is not met blocks (else it is a condition): see the module notes."""
    return r.obligation == "mandatory" or (r.obligation == "conditional" and r.kind != "contract")


def assess_rule(rule: Rule, fields: Mapping[str, Any], statuses: Mapping[str, str]) -> RuleResult:
    outcome, asks, declared = _outcome(rule, fields, statuses)
    # a registration that is missing is a to-do with the same words as "not met": the text says it is free
    reason = rule.texts.get(outcome) or (rule.texts["not_met"] if outcome == "to_obtain" else GENERIC.get(outcome, ""))
    if declared:
        reason = DECLARED_NOT_APPLICABLE
    return RuleResult(
        rule=rule.code, title=rule.title, outcome=outcome, reason=reason, obligation=rule.obligation,
        kind=rule.kind, requirement=rule.requirement, note=rule.note, asks=tuple(asks),
        source_url=rule.source_url, source_ref=rule.source_ref, source_text=rule.source_text,
        text_origin=rule.text_origin, verification_status=rule.status,
        last_reviewed=rule.last_reviewed, denominator=rule.denominator,
        consultant=rule.texts.get("consultant") if outcome in CONSULTANT_OUTCOMES and not declared else None)


def _outcome(rule: Rule, fields: Mapping[str, Any], statuses: Mapping[str, str]) -> tuple[str, list[str], bool]:
    """(outcome, the fields still to answer, whether the outcome is the company's own "Not applicable to us")."""
    def missing(*exprs: Expr | None) -> list[str]:
        # the context of a call is not something the company can answer
        asks = [f for e in exprs for f in fields_in(e) if fields.get(f) is None and not FIELDS[f].get("context")]
        # a requirement the questionnaire does not ask: its code stands for the question (`Requirement.extras["question"]`)
        asks += [c for e in exprs for c in statuses_in(e) if statuses.get(c) == STATUS_UNKNOWN and c not in asks]
        return asks

    if rule.applies_when is not None:
        applies = evaluate(rule.applies_when, fields, statuses)
        if applies is False:
            return "not_applicable", [], False
        if applies is None:
            # no call is being judged: a rule for one kind of action is not asked here, whatever else is unanswered
            if any(FIELDS[f].get("context") and fields.get(f) is None for f in fields_in(rule.applies_when)):
                return "not_applicable", [], False
            return "unknown", missing(rule.applies_when, rule.condition), False
    # "Not applicable to us" is a third state, not "held" (WP-53, T4): the rule is left out, and it never reads as met.
    if declared_not_applicable(rule, statuses):
        return "not_applicable", [], True
    if rule.condition is None:
        return "info", [], False
    met = evaluate(rule.condition, fields, statuses)
    if met is True:
        return "met", [], False
    if met is None:
        return "unknown", missing(rule.condition), False
    if rule.conditional_when is not None:
        derogation = evaluate(rule.conditional_when, fields, statuses)
        if derogation is True:
            return "conditional", [], False
        if derogation is None:
            return "unknown", missing(rule.conditional_when), False
    # D3: a registration that anybody can obtain (the PIC, the NCAGE code) is something to obtain first,
    # not a reason to call the company blocked.
    return ("to_obtain" if rule.kind == "registration" else "not_met"), [], False


def assess(profile: Profile, statuses: Mapping[str, str], programme: Programme | str,
           content: Content | None = None) -> Assessment:
    """The assessment of one programme. `programme` is a `Programme`, or its code with `content`."""
    if isinstance(programme, str):
        if content is None:
            raise ValueError("a programme code needs the content to look it up")
        programme = content.programmes[programme]
    fields = profile.fields()
    results = tuple(assess_rule(r, fields, statuses) for r in sorted(programme.rules, key=lambda r: (r.position, r.code)))
    counted = [r for r in results if counts(r)]
    blocking = tuple(r.rule for r in counted if r.outcome == "not_met" and blocks(r))
    conditions = tuple(r.rule for r in counted if r.outcome == "conditional" or (r.outcome == "not_met" and not blocks(r)))
    to_obtain = tuple(r.rule for r in counted if r.outcome == "to_obtain")
    unknown = [r for r in counted if r.outcome == "unknown"]
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


def concerns(a: Assessment) -> bool:
    """Whether a programme says anything about this company: a route whose every rule is for another country (the Spanish
    Ministry of Defence route for a Polish company) does not, and is left out rather than shown as "eligible"."""
    return any(r.outcome != "not_applicable" for r in a.rules)


# --------------------------------------------------------------------------- "consultant needed" (WP-64)

# US export control is not in the verified rules (docs/research/ANGLE1_RULES_ES_DE_2026-10-20.md has no row for it): the flag says
# only that a specialist is needed, and states no rule of its own.
US_COMPONENTS_FLAG = {
    "key": "US-COMPONENTS", "title": "US-origin components (ITAR)", "rule": None,
    "text": ("If your product contains components, technology or software of US origin, US export control (for defence articles, "
             "the International Traffic in Arms Regulations, ITAR) may decide to whom it can be sold or re-exported. This service holds "
             "no verified rule on US export control and gives no answer on it: ask a specialist in US export control."),
}


def consultant_flags(profile: Profile, assessments: Sequence[Assessment]) -> list[dict[str, Any]]:
    """Where the answer needs a specialist: export classification, US components, the HSES path, a prime's own qualification.
    One entry per rule whose `texts.consultant` is set and that is open for this company, then the US-components flag unless
    the company said it has none. Each says what to ask; none is a verdict."""
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for a in assessments:
        for r in a.rules:
            if r.consultant and r.rule not in seen:
                seen.add(r.rule)
                out.append({"key": r.rule, "title": r.title, "text": r.consultant, "rule": r.rule, "asks": list(r.asks)})
    if profile.us_components is not False:
        out.append({**US_COMPONENTS_FLAG, "asks": [] if profile.us_components else ["us_components"]})
    return out
