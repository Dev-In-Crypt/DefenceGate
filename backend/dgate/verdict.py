"""The verdict of one call for one company profile (WP-93, fix 5 of the eligibility check of 23 October 2026).

The list badge, the filter "Fits my profile" and the call page compute it in the browser (web/lib/fit.ts `callFit`, over
web/lib/eligibility-check.ts `check`); this module is the same rules, line for line, for the API (`POST /v1/readiness/assess` with
`call`: `call.verdict`). Both are run on the same 60 verified pairs and their fixture calls (web/lib/data/wp93-pairs.json:
web/lib/wp93.check.ts and tests/unit/test_wp93.py), and agree on every line's verdict and words.

Rules of the verdict, all conservative: a "no" only where a rule read from the call (or of its programme) excludes the profile; a "yes"
only where every applicable fact allows it and carries no condition; everything else "check"; nothing read: "unknown", never "yes".
The profile is the request body of the assessment (`ProfileIn`, the answers the browser sends), nothing stored.
"""

from __future__ import annotations

import math
import re
from typing import Any

INF = math.inf
EU27 = frozenset("AT BE BG HR CY CZ DK EE FI FR DE GR HU IE IT LV LT LU MT NL PL PT RO SK SI ES SE".split())
EEA_EXTRA = frozenset({"IS", "LI", "NO"})
PUBLIC_KINDS = ("contracting_authority", "international_organisation", "seap", "eda")

# ---------------------------------------------------------------- helpers (eligibility-check.ts)

_SCOPE_PREFIX = re.compile(r"^(?:General rule of the work programme annexes; the topic or the type of action may add or change it\.|"
                           r"Stated in this topic[’']s own conditions\.)\s*")


def own_note(f: dict[str, Any] | None) -> str:
    return _SCOPE_PREFIX.sub("", (f or {}).get("note") or "", count=1).strip()


def _num(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _str(v: Any) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, list):
        return ",".join(_str(x) for x in v)
    if _num(v) and float(v).is_integer():
        return str(int(v))
    return str(v)


def _line(key: str, label: str, verdict: str, reason: str, quote: str | None = None) -> dict[str, Any]:
    return {"key": key, "label": label, "verdict": verdict, "reason": reason, "quote": quote}


def with_note(line: dict[str, Any], fact: dict[str, Any] | None, note: str | None = None) -> dict[str, Any]:
    note = own_note(fact) if note is None else note
    if line["verdict"] == "yes" and note:
        return {**line, "verdict": "check", "reason": f"{line['reason']} A condition applies: {note}"}
    return line


def _worst(a: str, b: str) -> str:
    return "no" if "no" in (a, b) else "check" if "check" in (a, b) else "yes"


# WP-102: "guarantees" (the route), not the verb of "In order to guarantee the protection of the strategic interests", with which every
# Horizon Europe Article 22(5) clause begins: it turned "shall not participate" into "a way round exists" (CS-ECCC 34-37).
_EXCEPTION = re.compile(r"guarantees|exempt|exception|unless|screening|derogat|approved by|china|high[- ]risk|only (?:applies|if|for)|limited to", re.I)
_COVERS = {
    "sme": re.compile(r"legal entit|private|compan|enterprise|business|firm|industr|\bsmes?\b|start-?up|mid-?cap", re.I),
    "large": re.compile(r"legal entit|private|compan|enterprise|business|firm|industr", re.I),
    "public": re.compile(r"legal entit|public|authorit|ministr|agenc|bod(?:y|ies)", re.I),
    "university": re.compile(r"legal entit|universit|research|academi|\brtos?\b", re.I),
    "individual": re.compile(r"natural person|individual|sole trader", re.I),
}
_SMALL_ONLY = re.compile(r"(?<!non-)\bsmes?\b|\bsmall\b|\bmicro\b|\bmedium\b|mid-?\s?caps?", re.I)
_LARGE = re.compile(r"\blarge\b", re.I)
_MIDCAP = re.compile(r"mid-?\s?caps?", re.I)
_SIZE_WORDS = re.compile(r"\bsmes?\b|small and medium|mid-?\s?caps?|micro|employees|staff", re.I)   # WP-109: eligibility-check.ts SIZE_WORDS


def covers(org: str, kind: str) -> bool:
    if org == "large" and _SMALL_ONLY.search(kind) and not _LARGE.search(kind):
        return False
    return bool(_COVERS[org].search(kind))


def small_kinds_only(facts: dict[str, Any]) -> list[str] | None:
    v = (facts.get("entity_types") or {}).get("value")
    if not isinstance(v, list) or not v:
        return None
    kinds = [_str(k) for k in v]
    return kinds if all(_SMALL_ONLY.search(k) and not _LARGE.search(k) for k in kinds) else None


def single_applicant_condition(facts: dict[str, Any]) -> str | None:
    single = facts.get("single_applicant_allowed")
    note = own_note(single)
    return f"A single applicant may apply under a condition: {note}" if single and single["value"] is True and note else None


def consortium_condition(facts: dict[str, Any]) -> str | None:
    cons = facts.get("consortium_required")
    cons_note = own_note(cons)
    single = single_applicant_condition(facts)
    if single:
        return single
    if cons_note:
        return f"The call attaches a condition to the consortium: {cons_note}"
    if cons and cons["value"] is True and re.search(r"specific conditions|conditions for the consortium|composition", cons.get("quote") or "", re.I):
        return "The call sets specific conditions on who may form the consortium that are not read here; check its section on consortium composition."
    return None


def consortium_unclear(facts: dict[str, Any]) -> bool:
    if (facts.get("consortium_required") or {}).get("value") is not False:
        return False
    n, k = (facts.get("min_entities") or {}).get("value"), (facts.get("min_countries") or {}).get("value")
    return (_num(n) and n >= 2) or (_num(k) and k >= 2)


def unclear_consortium_text(facts: dict[str, Any]) -> str:
    n, k = (facts.get("min_entities") or {}).get("value"), (facts.get("min_countries") or {}).get("value")
    asks = " and ".join(x for x in [f"at least {_str(n)} legal entities" if _num(n) and n >= 2 else None,
                                    f"at least {_str(k)} countries" if _num(k) and k >= 2 else None] if x)
    return f"it says no consortium is required and also asks for {asks}."


def _sentences(note: str) -> list[str]:
    return [s.strip() for s in re.findall(r"[^.;!?]+[.;!?]*", note) if s.strip()]


def entity_note(fact: dict[str, Any] | None, more: dict[str, Any] | None) -> str:
    note = own_note(fact)
    if not more:
        return note

    def keep(s: str) -> bool:
        if len(s) > 260 or re.search(r"companies|company (?:must|shall|with|that|of|has)\b|enterprise|\bSMEs?\b|employee|turnover|private|your", s, re.I):
            return True
        kinds = [k for k in (
            more["legalPerson"] if re.search(r"natural persons?|sole traders?|self-employed|without (?:a )?(?:separate )?legal personality", s, re.I) else None,
            more["company"] if re.search(r"international organisations?", s, re.I) else None,
            more["company"] if re.search(r"\bSEAPs?\b", s) else None,
        ) if k is not None]
        return not kinds or False in kinds

    return " ".join(s for s in _sentences(note) if keep(s))


def country_note(fact: dict[str, Any] | None, country: str, more: dict[str, Any] | None) -> str:
    note = own_note(fact)
    if not more or not fact:
        return note
    text = _str(fact["value"])
    m = more["managementCountry"]
    named = m != "" and ((bool(re.search(r"member states|\bunion\b|\bEU\b", text, re.I)) and m in EU27)
                         or (m in EEA_EXTRA and bool(re.search(r"EEA", text, re.I))) or (m == "UA" and bool(re.search(r"ukrain", text, re.I))))

    def keep(s: str) -> bool:
        if re.search(r"non-government[- ]controlled areas? of Ukraine", s, re.I):
            return not (country != "" and (country != "UA" or more["uaOccupied"] == "no"))
        if re.search(r"executive management structures? (?:\w+ ){0,4}established in an eligible country", s, re.I):
            return not named
        return True

    return " ".join(s for s in _sentences(note) if keep(s))


def partner_kind(sentence: str) -> str:
    if re.search(r"^this is the minimum for the topic[.;]?$", sentence, re.I):
        return "harmless"
    if (re.search(r"\bukrain", sentence, re.I) and re.search(r"single applicant|consorti|must include", sentence, re.I)
            and re.search(r"established|executive management", sentence, re.I)):
        return "ukraine"
    if re.search(r"\bSEAPs?\b", sentence) and re.search(r"(?:no|without a) SEAP (?:participates|takes part)|unless a SEAP (?:participates|takes part)", sentence, re.I):
        return "seap"
    return "other"


def partner_needs(facts: dict[str, Any]) -> dict[str, bool]:
    out = {"ukraine": False, "seap": False, "other": False}
    for key in ("single_applicant_allowed", "consortium_required", "min_entities", "min_countries"):
        for s in _sentences(own_note(facts.get(key))):
            k = partner_kind(s)
            if k in ("ukraine", "seap"):
                out[k] = True
            elif k == "other" and key in ("single_applicant_allowed", "consortium_required"):
                out["other"] = True
    return out


def partner_line(facts: dict[str, Any], p: dict[str, Any]) -> dict[str, Any] | None:
    base = consortium_condition(facts)
    if not base:
        return None
    quote = (facts.get("consortium_required") or facts.get("single_applicant_allowed") or {}).get("quote")
    needs = partner_needs(facts)
    more = p.get("more")
    if not more or needs["other"] or (not needs["ukraine"] and not needs["seap"]):
        return _line("consortium", "Partners", "check", base, quote)
    met: list[str] = []
    unmet: list[str] = []
    if needs["ukraine"]:
        if p["country"] == "UA" and more["managementCountry"] == "UA":
            met.append("your company is established in Ukraine, with its executive management there")
        elif more["uaPartner"] == "yes" and p["country"] != "UA":
            met.append("you said a legal entity established in Ukraine takes part in your consortium")
        elif p["country"] == "UA":
            unmet.append("Your answers do not place your executive management in Ukraine.")
        else:
            unmet.append("You said no legal entity established in Ukraine takes part in your consortium." if more["uaPartner"] == "no"
                         else "Your answers do not say whether a legal entity established in Ukraine takes part in your consortium.")
    if needs["seap"]:
        if more["seapPartner"] == "yes":
            met.append("you said a SEAP takes part in your consortium")
        else:
            unmet.append("You said no SEAP takes part in your consortium." if more["seapPartner"] == "no"
                         else "Your answers do not say whether a SEAP takes part in your consortium.")
    if unmet:
        return _line("consortium", "Partners", "check", f"{base} {' '.join(unmet)}", quote)
    return _line("consortium", "Partners", "yes", f"The call attaches conditions to who applies with whom, and your answers meet them: {'; '.join(met)}.", quote)


# ---------------------------------------------------------------- WP-93: countries, association, size, control

_EU_WORDS = re.compile(r"member states?|\bunion\b|\bEU\b", re.I)
_OPEN_LIST = re.compile(r"associated|third[- ]countr|any (?:legal )?(?:entity|entities|country|countries)|regardless|other countries|middle[- ]income|international organi", re.I)
_NAMED = [
    (r"\bnorway\b", "NO"), (r"\biceland\b", "IS"), (r"\bliechtenstein\b", "LI"), (r"\bukrain", "UA"), (r"\bswitzerland\b", "CH"),
    (r"united kingdom", "GB"), (r"\bcanada\b", "CA"), (r"\bisrael\b", "IL"), (r"\bkorea\b", "KR"), (r"new[- ]zealand", "NZ"), (r"\bjapan\b", "JP"),
    (r"t[üu]rkiye|\bturkey\b", "TR"), (r"\bmoldova\b", "MD"), (r"\balbania\b", "AL"), (r"\bserbia\b", "RS"), (r"\bmontenegro\b", "ME"),
    (r"north macedonia", "MK"), (r"\bgeorgia\b", "GE"), (r"\barmenia\b", "AM"), (r"\btunisia\b", "TN"), (r"faroe", "FO"), (r"bosnia", "BA"), (r"kosovo", "XK"),
]
# The same list, with its sources, as web/lib/eligibility-check.ts ASSOCIATED.
# WP-102: Horizon Europe from the Commission's list of participating countries (V4.2, 7 October 2026): the countries associated to the
# entire programme (Japan, New Zealand, Korea and the United Kingdom are associated to parts of it and stay a question), and Liechtenstein,
# which the list says does not intend to associate. The clauses are kept with the list (`ASSOCIATION_SOURCES`).
ASSOCIATED = {
    "HORIZON": {"name": "Horizon Europe", "yes": ["AL", "AM", "BA", "EG", "FO", "GE", "IS", "IL", "XK", "MD", "ME", "MK", "NO", "RS", "CH", "TN", "TR", "UA"],
                "no": ["LI"]},
    "EDIP": {"name": "the EDIP Programme", "yes": ["NO"], "no": ["UA"]},
    "EDF": {"name": "the European Defence Fund", "yes": ["NO"], "no": []},
}
# WP-102: the primary-source clause each Horizon Europe entry rests on (the same in web/lib/eligibility-check.ts ASSOCIATION_SOURCES).
HE_LIST_URL = "https://ec.europa.eu/info/funding-tenders/opportunities/docs/2021-2027/common/guidance/list-3rd-country-participation_horizon-euratom_en.pdf"
ASSOCIATION_SOURCES = {
    "HORIZON": {
        "document": "EU Grants: List of participating countries (HE): V4.2 - 07.10.2026", "url": HE_LIST_URL,
        "yes": "The association agreements with the following countries have now started to produce legal effects (either through provisional "
               "application or their entry into force)",
        # the entries of that list associated to the entire programme, as the list writes them
        "listed": "Albania; Armenia; Bosnia and Herzegovina; Egypt (associated to the entire Programme for award procedures implementing Union "
                  "budget for the year 2025 and onwards); Faroe Islands; Georgia; Iceland; Israel; Kosovo; Moldova; Montenegro; North Macedonia; "
                  "Norway; Serbia; Switzerland (associated to the entire Programme for award procedures implementing Union budget for the year "
                  "2025 and onwards); Tunisia; Türkiye; Ukraine",
        "no": "Liechtenstein does not intend to associate to Horizon Europe.",
    },
}


def named_countries(text: str) -> set[str]:
    return {code for pattern, code in _NAMED if re.search(pattern, text, re.I)}


def association_of(text: str, ctx: dict[str, str] | None) -> str | None:
    if re.search(r"associated to (?:the )?horizon", text, re.I):
        return "HORIZON"
    if re.search(r"associated to the EDIP|EDIP associated", text, re.I):
        return "EDIP"
    if not ctx:
        return None
    t = (ctx.get("topic") or "").upper().split("-")
    if "EDIP" in t:
        after = t[t.index("EDIP") + 1] if t.index("EDIP") + 1 < len(t) else None
        return None if after == "USI" else "EDIP"
    return ctx.get("programme") if ctx.get("programme") in ASSOCIATED else None


def country_status(fact: dict[str, Any], country: str, ctx: dict[str, str] | None = None) -> tuple[str, str]:
    text = _str(fact["value"])
    eu = bool(_EU_WORDS.search(text))
    named = named_countries(text)
    eea_assoc_only = bool(re.search(r"EEA (?:member|countr\w*|state\w*) associated", text, re.I))
    eea_all = bool(re.search(r"\bEEA\b", text)) and not eea_assoc_only
    assoc = association_of(text, ctx)
    lst = ASSOCIATED.get(assoc) if assoc else None
    opens = bool(re.search(r"(?<!non-)associated", text, re.I))
    if eu and country in EU27:
        return "yes", "An EU Member State is eligible under this call."
    if country in EEA_EXTRA and eea_all:
        return "yes", "EEA countries are eligible under this call."
    if country in named:
        return "yes", "Your country is named among the eligible countries."
    if opens and lst and country in lst["yes"]:
        return "yes", f"Your country is associated to {lst['name']}, and the call is open to the associated countries."
    if opens and lst and country in lst["no"]:
        return "no", f"Your country is not associated to {lst['name']}, and the call is open only to the Member States and the associated countries it names."
    if fact.get("scope") != "general" and eu and not _OPEN_LIST.search(text) and (named or re.search(r"\bEEA\b", text)):
        return "no", f"The call lists the countries where applicants must be established ({text}), and your country is not among them."
    if country in EU27:
        return "check", "The document lists the eligible countries in its own words, and they are not simply the Member States. Check that your country is among them."
    if opens and lst:
        return "check", f"Your country is not an EU Member State. The call is open to countries associated to {lst['name']}: check whether yours is one."
    return "check", "Your country is not an EU Member State. Check the list of eligible and associated countries in the document."


BAND_RANGE = {"lt50": (0, 49), "50_249": (50, 249), "250_499": (250, 499), "500_1999": (500, 1999), "2000plus": (2000, INF)}


def size_rule(facts: dict[str, Any]) -> dict[str, Any] | None:
    sme = facts.get("sme_only")
    if sme and sme["value"] is True:
        note = own_note(sme)
        return {"limit": 249, "midcap": note if _MIDCAP.search(note) else None, "fact": sme, "words": "SMEs"}
    kinds = small_kinds_only(facts)
    if kinds and facts.get("entity_types"):
        mid = any(_MIDCAP.search(k) for k in kinds)
        return {"limit": 499 if mid else 249, "midcap": None, "fact": facts["entity_types"],
                "words": "SMEs and small mid-caps (up to 499 staff)" if mid else "SMEs"}
    return None


def _staff(h: tuple[float, float]) -> str:
    return f"{int(h[0])} or more" if h[1] == INF else f"{int(h[0])} to {int(h[1])}"


def size_line(rule: dict[str, Any], h: tuple[float, float]) -> dict[str, Any]:
    q, words, limit, midcap = rule["fact"].get("quote"), rule["words"], rule["limit"], rule["midcap"]
    lo, hi = h
    if hi <= 249:
        return with_note(_line("sme", "Organisation size", "yes", f"The call is for {words}, and your staff count, counted with your group, is under 250.", q), rule["fact"])
    if limit == 499 and hi <= 499:
        return _line("sme", "Organisation size", "yes", f"The call is for {words}, and your staff count, counted with your group, is at most 499.", q)
    if limit == 249 and midcap and lo >= 250 and hi <= 499:
        return _line("sme", "Organisation size", "check", f"The call is reserved for SMEs; a company of 250 to 499 staff is a small mid-cap, which may apply only on a condition: {midcap}", q)
    if lo > (499 if midcap else limit):
        return _line("sme", "Organisation size", "no", f"The call is for {words}{' (small mid-caps up to 499 staff on a condition)' if midcap else ''}, counted with the staff of linked enterprises, and your answers give {_staff(h)} staff.", q)
    return _line("sme", "Organisation size", "check", f"The call is for {words}, counted with the staff of linked enterprises. Your answers do not settle it ({_staff(h)} staff): say whether you are part of a group, and its staff count.", q)


def control_kind(way: str) -> str:
    if not re.search(r"\bChin(?:a|ese)\b", way, re.I):
        return "other"
    if re.search(r"(?:cannot|can not|may not|not (?:be )?(?:allowed|able|eligible) to) (?:submit|provide) guarantees", way, re.I):
        return "china_no_guarantee"
    if re.search(r"guarantee|non-?eligible|non-associated|outside the (?:eligible|EU)|third countr", way, re.I):
        return "other"
    return "china_only"


def controller_eligible(c: dict[str, Any] | None, ctl: str, ctx: dict[str, str] | None) -> bool:
    return controller_status(c, ctl, ctx) == "yes"


def controller_status(c: dict[str, Any] | None, ctl: str, ctx: dict[str, str] | None) -> str:
    """WP-102: 'yes' when every country the answer may mean is eligible under the call (Ukraine; the three EEA EFTA states), 'some' when
    only some are (Horizon Europe: Iceland and Norway are associated, Liechtenstein is not), else 'no'."""
    if not c or ctl not in ("ua", "eea"):
        return "no"
    codes = ["UA"] if ctl == "ua" else ["IS", "LI", "NO"]
    ok = [country_status(c, code, ctx)[0] == "yes" for code in codes]
    return "yes" if all(ok) else "some" if any(ok) else "no"


LINE_FACT = {"country": "eligible_countries", "sme": "sme_only", "person": "natural_persons_allowed", "consortium": "consortium_required",
             "control": "ownership_control_restriction", "entity": "entity_types", "designated": "designated_applicants",
             "required": "required_partners", "investor": "investor_precommitment", "group": "max_group_headcount", "nationality": "staff_nationality",
             "cap": "non_sme_budget_cap", "single": "single_beneficiary_excludes", "procurement": "procurement_conflict"}
# WP-102: the label of a designated-bodies line that leaves others a route as partners; the badge names it (fit_word)
PARTNER_ONLY = "Only as a partner"


def check(facts: dict[str, Any], p: dict[str, Any], ctx: dict[str, str] | None = None) -> dict[str, Any]:
    """web/lib/eligibility-check.ts `check`, for the profile of `check_profile`."""
    lines: list[dict[str, Any]] = []
    org, size, kind = p["orgType"], p.get("size"), p.get("kind")

    def midcap_covered(k: str) -> bool:
        return org == "large" and size is not None and size[1] <= 499 and bool(_MIDCAP.search(k))

    # WP-102 (p05, 191): where only designated bodies may apply, that line says who may apply (no "covered by it" beside a block)
    types = None if facts.get("designated_applicants") and p["country"] else facts.get("entity_types")
    if types and isinstance(types["value"], list) and types["value"]:
        kinds = [_str(k) for k in types["value"]]
        if not org:
            lines.append(_line("entity", "Who may apply", "check", f"The call names who may apply: {'; '.join(kinds)}. Check that your organisation is one of them.", types.get("quote")))
        elif not any(covers(org, k) or midcap_covered(k) for k in kinds):
            lines.append(_line("entity", "Who may apply", "check", f"The call names who may apply: {'; '.join(kinds)}. Nothing in that list says a company like yours may. Check the document before you go on.", types.get("quote")))
        else:
            lines.append(with_note(_line("entity", "Who may apply", "yes", f"The call names who may apply ({'; '.join(kinds)}) and your organisation is covered by it.", types.get("quote")),
                                   types, entity_note(types, p.get("more"))))

    designated = facts.get("designated_applicants")
    if designated and p["country"]:
        who, note = _str(designated["value"]), own_note(designated)
        if re.search(r"partners?|in (?:a )?consortium with|may (?:also )?join", note, re.I):
            lines.append(_line("designated", PARTNER_ONLY, "check", f"Only {who} may apply; anybody else can take part only as a partner in a consortium with one. {note}", designated.get("quote")))
        else:
            lines.append(_line("designated", "Only these may apply", "check" if kind == "public" or org == "public" else "no",
                               f"Only {who} may apply. You are not eligible unless your organisation is one.", designated.get("quote")))
    required = facts.get("required_partners")
    if required and p["country"]:
        lines.append(_line("required", "Required in the consortium", "check", f"The consortium must include {_str(required['value'])}. You can take part together with them.", required.get("quote")))

    c = facts.get("eligible_countries")
    if c and p["country"]:
        verdict, reason = country_status(c, p["country"], ctx)
        line = _line("country", "Country", verdict, reason, c.get("quote"))
        lines.append(line if verdict == "no" else with_note(line, c, country_note(c, p["country"], p.get("more"))))
    # WP-145: eligibility-check.ts, the call document says Ukrainian entities cannot receive funding: a Ukrainian applicant is blocked by it
    said = (ctx or {}).get("ukraineNoFunding")
    if said and p["country"] == "UA":
        lines.append(_line("ukraine_funding", UA_NO_FUNDING, "no", UA_NO_FUNDING_REASON, said))
    # WP-99: eligibility-check.ts, the non-government controlled areas of Ukraine and Horizon Europe: not checked, and said so
    if p["country"] == "UA" and (p.get("more") or {}).get("uaOccupied") == "yes" and (ctx or {}).get("programme") == "HORIZON":
        lines.append(_line("territory", "Non-government controlled areas", "check",
                           "You said your company is established in a non-government controlled area of Ukraine. Whether the association of "
                           "Ukraine to Horizon Europe covers those areas is not checked here: no text we hold says so. Ask the National "
                           "Contact Point or the call’s helpdesk before you apply.", None))

    rule = size_rule(facts)
    sme = facts.get("sme_only")
    # WP-102: the form of the call page has no `kind`: its "university or research body" is not a company either
    if rule and (kind in ("university", "public") or (not kind and org in ("public", "university"))):
        who = "A university" if kind == "university" else "A public body" if org == "public" else "A university or a research body"
        lines.append(_line("sme", "Organisation size", "no", f"The call is for companies: {rule['words']}. {who} is not one.", rule["fact"].get("quote")))
    elif rule and kind == "research" and size is not None and size[0] > 249:
        # WP-102 (B13): a research organisation of 250 staff or more is no SME, and the small mid-cap route is for companies
        lines.append(_line("sme", "Organisation size", "no", f"The call is for companies: {rule['words']}. A research organisation of {_staff(size)} staff is not an SME, and the small mid-cap route is for companies.", rule["fact"].get("quote")))
    elif rule and kind == "research":
        lines.append(_line("sme", "Organisation size", "check", f"The call is for companies: {rule['words']}. A research organisation may apply only if it is such an enterprise.", rule["fact"].get("quote")))
    elif rule and size is not None:
        lines.append(size_line(rule, size))
    elif rule and org:
        # no staff count (the form of the call page): the size class decides what it can. WP-102: never "not reserved for SMEs" where the call
        # names only SMEs and small mid-caps (131).
        q = rule["fact"].get("quote")
        if org == "sme":
            words = "The call is reserved for SMEs and you are one." if rule["limit"] == 249 else f"The call is for {rule['words']}, and you are an SME."
            lines.append(with_note(_line("sme", "Organisation size", "yes", words, q), rule["fact"]))
        elif org == "large" and rule["midcap"]:
            lines.append(_line("sme", "Organisation size", "check", f"The call is reserved for SMEs; a small mid-cap (up to 499 staff) may apply only on a condition: {rule['midcap']}", q))
        elif org == "large" and rule["limit"] == 499:
            lines.append(_line("sme", "Organisation size", "check", f"The call names only these kinds of applicant: {'; '.join(small_kinds_only(facts) or [])}. It does not name a large company, so check your size class against the document before you go on.", q))
        elif org == "large" or rule["limit"] == 249:
            lines.append(_line("sme", "Organisation size", "no", "The call is reserved for SMEs.", q))
        else:
            lines.append(_line("sme", "Organisation size", "check", f"The call names only these kinds of applicant: {'; '.join(small_kinds_only(facts) or [])}. Check that you are one of them.", q))
    elif sme and org:
        # WP-109 (p09, 39): the sentence only where it speaks of size
        q = sme.get("quote") if _SIZE_WORDS.search(sme.get("quote") or "") else None
        lines.append(with_note(_line("sme", "Organisation size", "yes", "The call is not reserved for SMEs.", q), sme))

    np_ = facts.get("natural_persons_allowed")
    if np_ and org == "individual":
        if np_["value"] is False:
            lines.append(_line("person", "Natural person", "check" if np_.get("note") else "no",
                               f"Natural persons are not eligible, with an exception: {np_['note']}" if np_.get("note") else "Natural persons are not eligible.", np_.get("quote")))
        else:
            lines.append(with_note(_line("person", "Natural person", "yes", "Natural persons may apply.", np_.get("quote")), np_))

    own = facts.get("ownership_control_restriction")
    abroad = p["controlledAbroad"]
    if own and abroad:
        q = own.get("quote")
        if own["value"] is not True:
            lines.append(with_note(_line("control", "Ownership control", "yes", "No ownership control restriction is stated.", q), own))
        elif abroad == "yes":
            way = f"{own.get('note') or ''} {q or ''}"
            ctl = p.get("controller") or ""
            ck = control_kind(way)
            from_eligible = controller_status(c, ctl, ctx)
            if from_eligible == "yes":
                where = "Ukraine" if ctl == "ua" else "an EEA EFTA state"
                lines.append(_line("control", "Ownership control", "yes", f"The call restricts control from outside the eligible countries, and your company is controlled from {where}, which is eligible under it.", q))
            elif ck == "china_only" and ctl == "cn":
                lines.append(_line("control", "Ownership control", "no", "Entities controlled by China, or by a legal entity established in China, are not eligible under this call, and you said your company is controlled from China.", q))
            elif ck == "china_only" and ctl != "":
                lines.append(_line("control", "Ownership control", "yes", "The restriction concerns control by China only, and you said your company is controlled from another country.", q))
            elif ck == "china_no_guarantee" and ctl == "cn":
                lines.append(_line("control", "Ownership control", "no", "Entities controlled from outside the eligible countries may take part only with guarantees, and the call says entities controlled by China cannot submit guarantees.", q))
            elif from_eligible == "some":
                # WP-102: an answer "an EEA EFTA state" where Iceland and Norway are eligible and Liechtenstein is not (Horizon Europe)
                lines.append(_line("control", "Ownership control", "check", "The call restricts control from outside the eligible countries, and only some of the EEA EFTA states are eligible under it: check which one controls your company.", q))
            elif _EXCEPTION.search(way):
                tail = f": {own_note(own)}" if own_note(own) else ""
                lines.append(_line("control", "Ownership control", "check", f"{CONTROL_WAY_ROUND} allows a way round or narrows the restriction{tail}. Read it before you decide.", q))
            else:
                lines.append(_line("control", "Ownership control", "no", "Entities controlled from outside the eligible countries are excluded, and the document names no exception.", q))
        elif abroad == "unsure":
            lines.append(_line("control", "Ownership control", "check", "Entities controlled from outside the eligible countries are excluded. Find out who controls your company.", q))
        else:
            line = _line("control", "Ownership control", "yes", "The restriction applies, and your company is not controlled from outside the eligible countries.", q)
            lines.append(line if _EXCEPTION.search(own_note(own)) else with_note(line, own))

    # The consortium line of the form on the call page (`hasPartners`) is not here: the profile never answers it (lib/fit.ts).

    investor = facts.get("investor_precommitment")
    if investor and investor["value"] is True and p["country"]:
        q, inv = investor.get("quote"), p.get("investor")
        if inv == "yes":
            lines.append(_line("investor", "Investor pre-commitment", "yes", "The call requires a pre-commitment of a qualified investor for at least 20 % of the funding round, and you said you have one.", q))
        elif inv == "no":
            lines.append(_line("investor", "Investor pre-commitment", "no", "The call requires a pre-commitment of a qualified investor for at least 20 % of the funding round, and you said you do not have one.", q))
        else:
            lines.append(_line("investor", "Investor pre-commitment", "check", "The call requires a pre-commitment of a single qualified investor for at least 20 % of the funding round you aim to raise. Check that you have one.", q))
    most = facts.get("max_group_headcount")
    if most and _num(most["value"]) and p["country"]:
        fewer, q = _str(most["value"] + 1), most.get("quote")
        # WP-132 (RAPID, a Polish university: "Nothing known blocks you"): a cap on a company's group staff makes the call one for
        # companies; a university or a public body is not one, and a research organisation only if it is a company
        if kind in ("university", "public") or (not kind and org in ("public", "university")):
            who = "A university" if kind == "university" else "A public body" if org == "public" else "A university or a research body"
            lines.append(_line("group", "Staff count with the group", "no", f"The call is for companies with fewer than {fewer} staff, counted with the group. {who} is not a company.", q))
        elif kind == "research":
            lines.append(_line("group", "Staff count with the group", "check", f"The call is for companies with fewer than {fewer} staff, counted with the group. A research organisation may apply only if it is such a company.", q))
        elif size is not None and size[1] <= most["value"]:
            lines.append(_line("group", "Staff count with the group", "yes", f"The call is for companies with fewer than {fewer} staff, counted with the group, and yours is within that.", q))
        elif size is not None and size[0] > most["value"]:
            lines.append(_line("group", "Staff count with the group", "no", f"The call is for companies with fewer than {fewer} staff, counted with the group, and your answers give {_staff(size)}.", q))
        else:
            lines.append(_line("group", "Staff count with the group", "check", f"The call is for companies with fewer than {fewer} staff, counted with the whole group. Check your group's consolidated staff count.", q))
    nationality = facts.get("staff_nationality")
    if nationality and p["country"]:
        lines.append(_line("nationality", "Nationality of the staff", "check", f"Only staff of {_str(nationality['value'])} nationality may submit the application and work on the project. Check that yours are.", nationality.get("quote")))
    # WP-102: the composition rules a topic adds (read by rule_readings.py from the stated text, each with its sentence)
    cap = facts.get("non_sme_budget_cap")
    if cap and _num(cap["value"]) and p["country"] and (org == "large" or kind == "research"):
        lines.append(_line("cap", "Share of the budget", "check", f"Non-SME industries and research and technology organisations may take part, but together within {_str(cap['value'])} % of the proposed budget.", cap.get("quote")))
    single_no = facts.get("single_beneficiary_excludes")
    if single_no and p["country"] and org == "large":
        lines.append(_line("single", "Applying alone", "check", f"In a single-beneficiary project {_str(single_no['value'])} are not permitted: you can take part only in a consortium.", single_no.get("quote")))
    procurement = facts.get("procurement_conflict")
    if procurement and procurement["value"] is True and p["country"] and org != "public" and kind != "public":
        lines.append(_line("procurement", "Procurement of innovation", "check", "The procurement is prepared and carried out by public procurers. Other entities may take part only in additional activities, and only without a conflict of interest with the procurement: a company that could bid in it cannot be a beneficiary.", procurement.get("quote")))

    settled = []
    for line in lines:
        if (facts.get(LINE_FACT.get(line["key"], "")) or {}).get("scope") != "general":
            settled.append(line)
        elif line["verdict"] == "no":
            settled.append({**line, "verdict": "check", "reason": f"{line['reason']} This is the work programme's general rule; the topic may differ, so check its own conditions."})
        elif line["verdict"] == "yes":
            settled.append({**line, "verdict": "check", "reason": f"{line['reason']} This is the work programme's general rule, and the topic may add conditions: check its own."})
        else:
            settled.append(line)
    verdict = "yes"
    for line in settled:
        verdict = _worst(verdict, line["verdict"])
    return {"verdict": verdict, "lines": settled}


# ---------------------------------------------------------------- the profile (lib/fit.ts checkProfileOf, from the request body)

def _tri(v: bool | None) -> str:
    return "yes" if v is True else "no" if v is False else ""


def headcount_of(p: dict[str, Any]) -> tuple[float, float]:
    # the browser also reads a version 3 profile's size class while the staff count is unanswered; it is never sent, so here it is unknown
    own = BAND_RANGE.get(p.get("headcount") or "") or (0, INF)
    if p.get("in_group") is False:
        return own
    group = BAND_RANGE.get(p.get("group_headcount") or "") if p.get("in_group") is True else None
    if group:
        return (max(own[0], group[0]), max(own[1], group[1]))
    return (own[0], INF)


def check_profile(p: dict[str, Any]) -> dict[str, Any] | None:
    """What `check` reads, from the answers of the assessment request (`ProfileIn` fields), as lib/fit.ts reads the saved profile."""
    if not p.get("country"):
        return None
    if p.get("legal_form") == "natural_person":
        org = "individual"
    elif p.get("applicant_kind") in PUBLIC_KINDS:
        org = "public"
    elif p.get("org_kind") in ("university", "research"):
        org = "university"
    elif p.get("headcount") in BAND_RANGE:
        org = "sme" if BAND_RANGE[p["headcount"]][1] <= 249 else "large"
    else:
        org = ""
    control, ctl = p.get("third_country_control"), p.get("control_country")
    ctl = ctl if (control == "ua_eea_only" and ctl in ("ua", "eea")) or (control == "other" and ctl in ("cn", "ru_by", "other_non_eu")) else ""
    abroad = "no" if control == "no" else "yes" if control == "other" or (control == "ua_eea_only" and ctl) else "unsure"
    return {
        "country": p["country"], "orgType": org, "hasPartners": "", "controlledAbroad": abroad,
        "kind": "public" if p.get("applicant_kind") in PUBLIC_KINDS else (p.get("org_kind") or ""),
        "size": headcount_of(p), "controller": ctl, "investor": _tri(p.get("investor_precommitment")),
        "more": {
            "legalPerson": p.get("legal_form") == "legal_person", "company": p.get("applicant_kind") == "company_or_research",
            "managementCountry": p.get("executive_management_country") or "",
            "uaOccupied": _tri(p.get("ua_non_government_controlled_area")), "uaPartner": _tri(p.get("ua_partner")),
            "seapPartner": _tri(p.get("seap_partner")),
        },
    }


def _plural(n: Any, one: str, many: str) -> str:
    return one if n == 1 else many


def fit_of(facts: dict[str, Any] | None, profile: dict[str, Any] | None, ctx: dict[str, str] | None = None) -> dict[str, Any]:
    """lib/fit.ts `fitOf`."""
    unknown = {"fit": "unknown", "result": None, "conditions": [], "blockedBy": []}
    cp = check_profile(profile) if profile else None
    if not facts or not cp:
        return unknown
    lines = list(check(facts, cp, ctx)["lines"])
    sme = facts.get("sme_only")
    if sme and sme["value"] is True and not cp["orgType"] and not any(x["key"] == "sme" for x in lines):
        lines.append(_line("sme", "Organisation size", "check", "The call is reserved for SMEs and your profile does not give a size class.", sme.get("quote")))
    partner = partner_line(facts, cp)
    if partner and not any(x["key"] == "consortium" for x in lines):
        lines.append(partner)
    if not lines:
        return unknown
    if not facts.get("eligible_countries"):
        # WP-102 (RAPID 188): a call whose rule on where applicants must be established was not read is never "eligible"
        lines.append(_line("country", "Country", "check", "Where applicants must be established was not read from this call. Check the call's own conditions before you rely on this.", None))
    verdict = "yes"
    for x in lines:
        verdict = _worst(verdict, x["verdict"])
    conditions = []
    n, k = (facts.get("min_entities") or {}).get("value"), (facts.get("min_countries") or {}).get("value")
    if (facts.get("consortium_required") or {}).get("value") is True:
        need = f"at least {_str(n)} {_plural(n, 'legal entity', 'legal entities')}" if _num(n) else "several legal entities"
        where = f" from at least {_str(k)} {_plural(k, 'country', 'countries')}" if _num(k) else ""
        conditions.append(f"A consortium is required: {need}{where}. Your profile does not say whether you have partners.")
    elif consortium_unclear(facts):
        conditions.append(f"The document is unclear about a consortium: {unclear_consortium_text(facts)} Read it.")
    return {"fit": verdict, "result": {"verdict": verdict, "lines": lines}, "conditions": conditions,
            "blockedBy": [x["label"] for x in lines if x["verdict"] == "no"]}


# ---------------------------------------------------------------- the programme's rules (lib/fit.ts)

def programmes_of_call(chip: str, topic: str) -> list[str]:
    t = (topic or "").upper().split("-")
    if chip in ("EDF", "EDIP") and "EDIP" in t:
        i = t.index("EDIP") + 1
        after = t[i] if i < len(t) else None
        return ["EDIP-USI"] if after == "USI" else ["EDIP"] if after == "P" else ["EDIP", "EDIP-USI"]
    return ["EDF"] if chip == "EDF" else []


def action_of_call(chip: str, topic: str) -> str | None:
    t = (topic or "").upper().split("-")
    if chip not in ("EDF", "EDIP") or "EDIP" not in t:
        return None
    if "CPA" in t:
        return "common_procurement"
    if "SA" in t and "SEAP" in t:
        return "seap_support"
    if "CSA" in t and "PREP" in t:
        return "edpci_preparation"
    if "IRA" in t:
        return "industrial_reinforcement"
    return None


_APPLICANTS = {
    "common_procurement": {"title": "Who may apply: contracting authorities, international organisations, SEAPs and the EDA",
                           "only": "Only contracting authorities, international organisations, SEAPs and the EDA may apply to this call.",
                           "plain": ["international_organisation", "seap", "eda"], "maybe": ["contracting_authority"]},
    # WP-143 (r9-site, call 114): the document also admits a SEAP being established that has applied (rule EDIP-SEAP-APPLICANT)
    "seap_support": {"title": "Who may apply: an established SEAP",
                     "only": ("Only a SEAP may apply to this call: an established one, or one being established whose application "
                              "has already been submitted to the Commission."),
                     "plain": ["seap"], "maybe": []},
    "edpci_preparation": {"title": "Who may apply: a SEAP or a group of Member States",
                          "only": "Only a SEAP or a group of Member States may apply to this call.", "plain": ["seap"], "maybe": ["contracting_authority"]},
}
# WP-141: lib/fit.ts WHO_MAY_APPLY
WHO_MAY_APPLY = "Who may apply"


def applicant_fit(chip: str, topic: str, profile: dict[str, Any] | None) -> dict[str, Any] | None:
    action = action_of_call(chip, topic)
    rule = _APPLICANTS.get(action or "")
    if not rule or not profile or not profile.get("country"):
        return None
    # WP-102 (p01, 112): a profile that says what the organisation is (a company, a university, a research body) without the applicant-kind
    # answer is a company or research body for these rules, not an unanswered question
    kind = profile.get("applicant_kind") or ("company_or_research" if profile.get("org_kind") in ("company", "university", "research") else "")
    if kind == "":
        return {"fit": "check", "because": [f"{rule['title']}: say what kind of organisation you are"]}
    if kind in rule["plain"]:
        return {"fit": "yes", "because": []}
    if kind in rule["maybe"]:
        if action == "common_procurement" and profile["country"] in EU27:
            return {"fit": "yes", "because": []}
        return {"fit": "check", "because": [f"{rule['title']}: check that your organisation meets it"]}
    return {"fit": "no", "because": [rule["title"]]}


# WP-99: lib/fit.ts BLOCKED_AS, a blocking rule named as the fact that fails
BLOCKED_AS = {
    "USI-TERRITORY": "Your company is established in a non-government controlled area of Ukraine",
}
# WP-145: lib/eligibility-check.ts UA_NO_FUNDING, UA_NO_FUNDING_REASON
UA_NO_FUNDING = "No funding for Ukrainian entities"
UA_NO_FUNDING_REASON = ("The call document says Ukrainian entities cannot receive funding under this call, and your company is established "
                        "in Ukraine.")
# WP-99: lib/fit.ts NO_UA_PARTNER
NO_UA_PARTNER = "Not without a Ukrainian partner (you said none takes part)"
# WP-102 (p05, 149): a call only designated bodies may apply to, others joining them as partners: said on the badge, not "nothing blocks you"
PARTNER_ONLY_WORD = "Only as a partner of the bodies the call names"
# WP-109: lib/fit.ts NATIONALITY_PREFIX, nationalityWord
NATIONALITY_PREFIX = "Only if your staff are "
_NATIONALITY = re.compile(r"Only staff of (.+?) nationality")


# WP-137 (EuroHPC JU 138-143: "Nothing known blocks you" to a company controlled from outside the eligible countries): lib/fit.ts
# CONTROL_WAY_ROUND, CONTROL_WORD. The call excludes such a company unless its way round (guarantees approved by the country of
# establishment) applies: the badge names that condition.
CONTROL_WAY_ROUND = "The call restricts entities controlled from outside the eligible countries, but the document"
CONTROL_WORD = "Controlled from outside: only on the exception the call allows"


def nationality_word(reason: str) -> str:
    m = _NATIONALITY.search(reason)
    return f"{NATIONALITY_PREFIX}{f'{m.group(1)} nationals' if m else 'of the nationality the call names'}"


def _one_programme(a: dict[str, Any], steps: list[dict[str, Any]]) -> dict[str, Any]:
    fixable = {s["code"] for s in steps if a["programme"] in s.get("blockingFor", [])}
    blocking = [r for r in a["rules"] if r["rule"] in a["blocking"]]
    structural = [r for r in blocking if not r.get("requirement") or r["requirement"] not in fixable]
    if structural:
        return {"fit": "no", "because": list(dict.fromkeys(f"{a['name']}: {BLOCKED_AS.get(r['rule'], r['title'])}" for r in structural))}
    if a["verdict"] == "blocked":
        return {"fit": "check", "because": [f"Needs first: {s['name']}" for s in steps if s["code"] in fixable]}
    if a["verdict"] == "conditional":
        partner = any(r["rule"] == "USI-INVOLVES-UA" and r.get("outcome") == "conditional" for r in a["rules"])
        return {"fit": "check", "because": [NO_UA_PARTNER if partner else f"{a['name']}: a condition or an answer is still open"]}
    return {"fit": "yes", "because": []}


def programme_fit(assessment: dict[str, Any] | None, codes: list[str]) -> dict[str, Any] | None:
    if not assessment or not codes:
        return None
    found = [a for a in assessment["assessments"] if a["programme"] in codes]
    if not found:
        return None
    rank = {"yes": 0, "check": 1, "no": 2}
    return sorted((_one_programme(a, assessment["roadmap"]["steps"]) for a in found), key=lambda x: rank[x["fit"]])[0]


def with_programme(doc: dict[str, Any], prog: dict[str, Any] | None) -> dict[str, Any]:
    if not prog:
        return doc
    if prog["fit"] == "no":
        return {**doc, "fit": "no", "conditions": [*prog["because"], *doc["conditions"]], "blockedBy": [*prog["because"], *doc["blockedBy"]]}
    if doc["fit"] == "unknown":
        return doc
    fit = "check" if prog["fit"] == "check" and doc["fit"] == "yes" else doc["fit"]
    return {**doc, "fit": fit, "conditions": [*prog["because"], *doc["conditions"]]}


def call_fit(call: dict[str, Any] | None, profile: dict[str, Any] | None, assessment: dict[str, Any] | None) -> dict[str, Any]:
    """lib/fit.ts `callFit`: `call` is {state, facts, programme, topic}; `assessment` the assess payload without a call."""
    ctx = {"programme": call["programme"], "topic": call["topic"], "ukraineNoFunding": call.get("ukraineNoFunding")} if call else None
    doc = fit_of(call["facts"], profile, ctx) if call and call["state"] == "read" else {"fit": "unknown", "result": None, "conditions": [], "blockedBy": []}
    with_rules = with_programme(doc, programme_fit(assessment, programmes_of_call(call["programme"], call["topic"]) if call else []))
    if not call:
        return with_rules
    applicant = applicant_fit(call["programme"], call["topic"], profile)
    out = with_programme(with_rules, applicant)
    if not applicant or applicant["fit"] != "no":
        return out
    # WP-141 (SEAP 114 with a saved profile: "Blocked by: an established SEAP" over a row "Who may apply: Check"): the action's rule on who
    # may apply answers the question the document's row asked, so that row says the same, in a sentence
    lines = list((out.get("result") or {}).get("lines") or [])
    at = next((i for i, x in enumerate(lines) if x["key"] == "entity"), None)
    only = _APPLICANTS[action_of_call(call["programme"], call["topic"]) or ""]["only"]
    who = _line("who", WHO_MAY_APPLY, "no", f"{only} Your profile names another kind of organisation.", lines[at]["quote"] if at is not None else None)
    if at is not None:
        lines[at] = who
    else:
        lines.insert(0, who)
    return {**out, "result": {"verdict": "no", "lines": lines}}


def shown_fit(r: dict[str, Any]) -> str:
    return "check" if r["fit"] == "yes" and r["conditions"] else r["fit"]


def condition_count(r: dict[str, Any]) -> int:
    return sum(1 for x in ((r.get("result") or {}).get("lines") or []) if x["verdict"] == "check") + len(r["conditions"])


def fit_word(r: dict[str, Any]) -> str:
    """lib/fit.ts `fitLabel(...).word`."""
    fit = shown_fit(r)
    if fit == "no":
        def rule(b: str) -> str:
            return b[b.rfind(": ") + 2:] if ": " in b else b
        first = rule(r["blockedBy"][0] if r["blockedBy"] else "a rule of the call")
        more = len(r["blockedBy"]) - 1
        by = "Blocked: " if first in BLOCKED_AS.values() else "Blocked by: "
        return f"{by}{first}{f' and {more} more' if more > 0 else ''}"
    if fit == "check":
        if NO_UA_PARTNER in r["conditions"]:
            return NO_UA_PARTNER
        if any(x["label"] == PARTNER_ONLY for x in ((r.get("result") or {}).get("lines") or [])):
            return PARTNER_ONLY_WORD
        # WP-109 (owner, 24 Oct: the Cyber Defense Factory stays in "Fits" with its condition): the word names the condition
        nationality = next((x for x in ((r.get("result") or {}).get("lines") or [])
                            if x["key"] == "nationality" and x["verdict"] == "check"), None)
        if nationality:
            return nationality_word(nationality["reason"])
        if any(x["key"] == "control" and x["verdict"] == "check" and x["reason"].startswith(CONTROL_WAY_ROUND)
               for x in ((r.get("result") or {}).get("lines") or [])):
            return CONTROL_WORD
        n = condition_count(r)
        return f"Nothing known blocks you, {n} {'condition' if n == 1 else 'conditions'} to check" if n > 0 else "Nothing known blocks you"
    return "Eligible" if fit == "yes" else "Rules not read"
