"""Builds the second eligibility regression set (WP-102): the 60 new (profile, call) pairs that two verifiers read against the official
documents on 24 October 2026 (D:/DEFENCEGATE TESTS/elig-fresh/A and B, pairs.csv), as web/lib/data/wp102-pairs.json. Not a test;
tests/unit/test_wp102.py and web/lib/wp102.check.ts check what it wrote against the code.

    python -m tests.wp102_golden build     # profiles, calls (the facts /v1/fit/facts served on 24 October), pairs, readings
    python -m tests.wp102_golden derive    # `after` facts, programme verdicts and the expected verdict of every profile x call
    python -m tests.wp102_golden before <dir of the integration branch's backend>   # the verdicts of the code before WP-102

`requests` is written by web/lib/wp102.check.ts with WP102_WRITE=1 (lib/profile.ts toRequest). The sources (WP102_SRC, read only) are the
stored texts of production read on 24 October (call.eligibility_text, call_document_text) and the verifiers' saved profiles.
"""

from __future__ import annotations

import csv
import importlib.util
import json
import os
import sys
from pathlib import Path
from typing import Any

from dgate import eligibility, rule_readings, verdict
from dgate.readiness import api, seed

FIXTURE = Path(__file__).resolve().parents[2] / "web" / "lib" / "data" / "wp102-pairs.json"
SRC = Path(os.environ.get("WP102_SRC", "D:/DEFENCEGATE TESTS/wp102/src"))
PAIRS = Path(os.environ.get("WP102_PAIRS", "D:/DEFENCEGATE TESTS/elig-fresh"))

# n, profile, call, what the document says (can / can_if / cannot; uncheckable: no document read; not_held: we hold no rules), a word the
# answer must name. A 1-30, B 31-60 (B's own rows 1-30). The verifiers' text is in pairs.csv; the class column is their verdict of the site.
PAIRS_TABLE = [
    (1, "A1", "113", "cannot", None), (2, "A1", "116", "can_if", None), (3, "A1", "35", "can_if", None), (4, "A1", "60", "can_if", None),
    (5, "A1", "69", "can_if", "Border"), (6, "A1", "144", "can_if", None), (7, "A2", "111", "cannot", None), (8, "A2", "37", "can_if", None),
    (9, "A2", "60", "can_if", None), (10, "A2", "128", "can", None), (11, "A2", "77", "can_if", "Doctoral Networks"), (12, "A2", "147", "can", None),
    (13, "A3", "117", "cannot", None), (14, "A3", "36", "cannot", None), (15, "A3", "62", "can_if", "Border or Coast Guard"),
    (16, "A3", "65", "can_if", None), (17, "A3", "140", "can_if", "guarantees"), (18, "A3", "150", "cannot", None), (19, "A4", "116", "can", None),
    (20, "A4", "34", "can_if", None), (21, "A4", "60", "can_if", None), (22, "A4", "133", "uncheckable", None), (23, "A4", "145", "can_if", "designated"),
    (24, "A4", "61", "can_if", None), (25, "A5", "118", "can", None), (26, "A5", "111", "cannot", None), (27, "A5", "174", "not_held", None),
    (28, "A5", "35", "can_if", None), (29, "A5", "64", "can_if", "Training Centres"), (30, "A5", "60", "can_if", "15 %"),
    (31, "F6", "128", "can", None), (32, "F6", "24", "can", None), (33, "F6", "150", "cannot", None), (34, "F6", "44", "can_if", "Police Authorities"),
    (35, "F6", "111", "cannot", None), (36, "F6", "58", "can_if", "conflict of interest"), (37, "F7", "46", "cannot", None), (38, "F7", "53", "cannot", None),
    (39, "F7", "44", "can_if", "Police Authorities"), (40, "F7", "145", "cannot", None), (41, "F7", "24", "cannot", None),
    (42, "F7", "130", "can_if", "mid-caps and larger"), (43, "F8", "24", "cannot", None), (44, "F8", "130", "can", None), (45, "F8", "147", "can", None),
    (46, "F8", "58", "can_if", None), (47, "F8", "111", "cannot", None), (48, "F8", "144", "can_if", None), (49, "F9", "24", "can_if", "mid-cap"),
    (50, "F9", "131", "can", None), (51, "F9", "111", "cannot", None), (52, "F9", "150", "can", None), (53, "F9", "59", "can_if", None),
    (54, "F9", "187", "uncheckable", None), (55, "F10", "24", "can", None), (56, "F10", "128", "can", None), (57, "F10", "147", "cannot", None),
    (58, "F10", "42", "can_if", "Police"), (59, "F10", "111", "cannot", None), (60, "F10", "48", "can_if", None),
]

_STATUSES = {"REQ-NCAGE": "not_held", "REQ-PIC": "held", "REQ-ISO9001": "held", "REQ-EN9100": "not_held", "REQ-AQAP2110": "not_held",
             "REQ-AQAP2310": "not_held", "REQ-EXPORT": "not_applicable"}
_SUPPLIER = {"region": "", "foreignOwner": "", "foreignCountry": "", "nace": "", "cpv": [], "processes": [], "held": [], "expiry": {},
             "usComponents": "", "answers": {}, "euFunding": ""}


def _b(country: str, size: str, offering: str, org: str, head: str, group: str, ghead: str, control: str, ctl: str, investor: str,
       regime: str, role: str, classified: str, export: str) -> dict[str, Any]:
    """Half B's profiles were entered in the wizard by its answers (B/profiles.json), not saved: the stored form of the same answers."""
    return {"version": 5, "step": 6, "updatedAt": "2026-10-24T12:00:00.000Z", "name": "", "sizeClass": size, "country": country,
            "legalForm": "legal_person", "applicantKind": "company_or_research", "offering": offering, "topics": "", "orgKind": org,
            "headcount": head, "inGroup": group, "groupHeadcount": ghead, "management": "same", "managementCountry": "", "control": control,
            "controlCountry": ctl, "investor": investor, "uaOccupied": "no" if country == "UA" else "", "uaPartner": "no", "seapPartner": "no",
            "regime": regime, "componentPct": "", "componentBand": "le35", "restricted": "no", "uaComponents": "no", "eeaComponents": "no",
            "safeRole": role, "statuses": dict(_STATUSES), "classified": classified, "exportIntent": export, "supplier": dict(_SUPPLIER)}


B_PROFILES = {
    "F6": ("UA software SME 80 staff, Ukrainian-owned", _b("UA", "medium", "software_services", "company", "50_249", "no", "", "ua_eea_only", "ua", "no", "dual_use", "unsure", "no", "outside_eu")),
    "F7": ("NL electronics 600 staff, subsidiary of a Chinese group (2,000+)", _b("NL", "large", "products", "company", "500_1999", "yes", "2000plus", "other", "cn", "no", "dual_use", "unsure", "no", "outside_eu")),
    "F8": ("PL public research institute, 300 staff", _b("PL", "large", "software_services", "research", "250_499", "no", "", "no", "", "no", "dual_use", "unsure", "yes", "within_eu")),
    "F9": ("BE small mid-cap, 300 staff, independent, military products, investor pre-commitment", _b("BE", "large", "products", "company", "250_499", "no", "", "no", "", "yes", "military", "contractor", "yes", "within_eu")),
    "F10": ("CH software SME, 40 staff, Swiss-owned", _b("CH", "small", "software_services", "company", "lt50", "no", "", "no", "", "no", "dual_use", "unsure", "no", "within_eu")),
}
A_DESCRIBE = {"A1": "NO SME 50-249, dual-use products, Norway-controlled", "A2": "ES public university, 2,000+",
              "A3": "DE company 500-1999 in a 2,000+ group, US-controlled, military, over 35 % non-EU components",
              "A4": "IT micro start-up, software, independent", "A5": "FR large group 2,000+, military, Ukrainian partner"}

# Where each call's readings come from: the portal's conditions text (`call.eligibility_text`, read when served) or a stored document
# (the EIC work programme read per topic, the ECCC call document, the Horizon Europe general annexes), as production would serve them.
DOC_READS = {"128": "programme", "130": "programme", "145": "call_document", "58": "general"}


def load() -> dict[str, Any]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def save(data: dict[str, Any]) -> None:
    FIXTURE.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def build() -> dict[str, Any]:
    profiles: dict[str, Any] = {}
    for i in range(1, 6):
        stored = json.loads(json.loads((SRC / f"p{i}_ls.json").read_text(encoding="utf-8"))["dg.profile.v1"])
        profiles[f"A{i}"] = {"describe": A_DESCRIBE[f"A{i}"], "stored": stored}
    for k, (describe, stored) in B_PROFILES.items():
        profiles[k] = {"describe": describe, "stored": stored}
    served = json.loads((SRC / "facts.json").read_text(encoding="utf-8"))["items"]
    wanted = sorted({c for _, _, c, _, _ in PAIRS_TABLE}, key=int)
    # a national call has no topic code (null in the API's answer; the browser reads it as "")
    calls = {c: {**{k: served[c][k] for k in ("programme", "state", "facts")}, "topic": served[c]["topic"] or ""} for c in wanted}
    verifier = {}
    for half, offset in (("A", 0), ("B", 30)):
        with open(PAIRS / half / "pairs.csv", encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                verifier[int(r["n"]) + offset] = r["class"]
    pairs = [{"n": n, "profile": p, "call": c, "document": d, "mention": m, "verifier": verifier[n]} for n, p, c, d, m in PAIRS_TABLE]
    return {"about": ("WP-102 regression set: the 60 new (profile, call) pairs of the eligibility check of 24 October 2026 (D:/DEFENCEGATE "
                      "TESTS/elig-fresh A and B, pairs.csv; A rows 1-30, B rows 31-60), none of them a pair the WP-93 fixes were tuned on. "
                      "`calls`: the facts /v1/fit/facts served that day. `document`: what the official text says for the profile (can, can_if "
                      "a condition, cannot; uncheckable: the verifier could not read the document; not_held: we hold no rules for the call). "
                      "`mention`: a word the answer must name. `readings`: the rules WP-102 reads by fixed patterns from the stored texts, "
                      "each with its sentence."), "profiles": profiles, "calls": calls, "pairs": pairs}


def readings(data: dict[str, Any]) -> None:
    raw = {str(r["id"]): r for r in json.loads((SRC / "calls_raw.json").read_text(encoding="utf-8"))}
    srcs = json.loads((SRC / "srcs.json").read_text(encoding="utf-8"))
    docs = json.loads((SRC / "docs.json").read_text(encoding="utf-8"))
    out: dict[str, Any] = {}
    for cid, call in data["calls"].items():
        got: dict[str, Any] = {}
        if cid in raw:
            for k, f in rule_readings.read_conditions(raw[cid]["etext"], call["topic"]).items():
                got[k] = {**f, "scope": "topic", "from": "the portal's conditions text of the topic"}
        scope = DOC_READS.get(cid)
        if scope:
            for s in srcs[cid]:
                if s["scope"] == "topic":
                    continue
                url = s["document"] or s["key"]
                text = docs.get(url) or ""
                read = rule_readings.general_annexes(text) if scope == "general" else rule_readings.read_document(text, call["topic"])
                for k, f in read.items():
                    if k in ("sme_only", "investor_precommitment", "designated_applicants", "single_beneficiary_excludes", "procurement_conflict"):
                        got[k] = {**f, "scope": scope, "from": url}
        if got:
            out[cid] = {k: {x: f[x] for x in ("value", "quote", "note", "scope", "from")} for k, f in got.items()}
    data["readings"] = out


def after_facts(data: dict[str, Any]) -> dict[str, Any]:
    """The facts as WP-102 serves them: a reading replaces the served fact of the same name (eligibility.assemble for the conditions text,
    ops/rule_readings for the stored documents), then the kinds that are required beneficiaries move to `required_partners`."""
    out = {}
    for cid, call in data["calls"].items():
        facts = {k: dict(v) for k, v in call["facts"].items()}
        for k, f in (data.get("readings") or {}).get(cid, {}).items():
            facts[k] = {"value": f["value"], "note": f["note"], "quote": f["quote"], "scope": f["scope"]}
        facts = eligibility.required_partners(facts)
        state = "read" if facts else call["state"]
        out[cid] = {**call, "state": state if call["state"] != "no_source" else "no_source", "facts": facts}
    return out


def derive(data: dict[str, Any]) -> None:
    data["after"] = after_facts(data)
    content = seed.load_file()
    assessments = {}
    for key, req in (data.get("requests") or {}).items():
        body = api.AssessIn(**req)
        payload = api.assess_payload(content, body.profile.to_engine(), body.statuses)
        assessments[key] = {
            "assessments": [{"programme": a["programme"], "name": a["name"], "verdict": a["verdict"], "blocking": a["blocking"],
                             "rules": [{"rule": r["rule"], "title": r["title"], "requirement": r["requirement"], "outcome": r["outcome"]}
                                       for r in a["rules"]]} for a in payload["assessments"]],
            "roadmap": {"steps": [{"code": s["code"], "name": s["name"], "blockingFor": s["blockingFor"]} for s in payload["roadmap"]["steps"]]},
        }
    data["assessments"] = assessments
    data["expected"] = {f"{k}|{c}": expected(data, k, c) for k in sorted(assessments) for c in sorted(data["after"], key=int)} if assessments else {}


def expected(data: dict[str, Any], profile: str, cid: str, engine: Any = verdict, facts_of: str = "after") -> dict[str, Any]:
    call = data[facts_of][cid]
    req = data["requests"][profile]
    seap = {"yes": True, "no": False}.get(data["profiles"][profile]["stored"].get("seapPartner", ""))
    answers = {**req["profile"], **({"seap_partner": seap} if seap is not None else {})}
    r = engine.call_fit({"state": call["state"], "facts": call["facts"], "programme": call["programme"], "topic": call["topic"]},
                        answers, data["assessments"][profile])
    return {"fit": r["fit"], "shown": engine.shown_fit(r), "word": engine.fit_word(r), "conditions": r["conditions"],
            "lines": [{k: x[k] for k in ("key", "verdict", "reason")} for x in ((r.get("result") or {}).get("lines") or [])]}


def correct(p: dict[str, Any], got: dict[str, Any]) -> bool | None:
    """Whether the verdict is what the document says; None for a pair that is not checkable (scored apart)."""
    shown = got["shown"]
    words = " ".join([*(x["reason"] for x in got["lines"]), *got["conditions"], got["word"]])
    named = not p["mention"] or p["mention"] in words
    doc = p["document"]
    if doc == "uncheckable":
        return None
    if doc == "not_held":
        return shown == "unknown"
    if doc == "cannot":
        return shown == "no" and named
    if doc == "can_if":
        return shown == "check" and named
    return shown in ("yes", "check")


def score(data: dict[str, Any], verdicts: dict[str, Any]) -> tuple[int, int, list[str]]:
    ok, checkable, wrong = 0, 0, []
    for p in data["pairs"]:
        got = verdicts[f"{p['profile']}|{p['call']}"]
        c = correct(p, got)
        if c is None:
            continue
        checkable += 1
        ok += c
        if not c:
            wrong.append(f"{p['n']} {p['profile']}/{p['call']} {p['document']}{' naming ' + repr(p['mention']) if p['mention'] else ''}: {got['word']}")
    return ok, checkable, wrong


def before(data: dict[str, Any], old_backend: str) -> None:
    """The verdicts the code of the integration branch (before WP-102) gives on the facts served on 24 October: the score before."""
    spec = importlib.util.spec_from_file_location("verdict_before", Path(old_backend) / "dgate" / "verdict.py")
    old = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(old)
    got = {f"{p['profile']}|{p['call']}": expected(data, p["profile"], p["call"], old, "calls") for p in data["pairs"]}
    ok, n, wrong = score(data, got)
    data["before"] = {"code": "integration 24e5295 (before WP-102), on the facts served on 24 October", "correct": ok, "checkable": n, "wrong": wrong,
                      "words": {k: v["word"] for k, v in got.items()}}


def main(argv: list[str]) -> int:
    data = build() if "build" in argv else load()
    if "build" in argv:
        old = load() if FIXTURE.exists() else {}
        for k in ("requests",):
            if k in old:
                data[k] = old[k]
        readings(data)
    if "derive" in argv:
        derive(data)
    if "before" in argv:
        before(data, argv[argv.index("before") + 1])
    save(data)
    if data.get("expected"):
        ok, n, wrong = score(data, data["expected"])
        print(f"after: {ok}/{n} checkable correct", *wrong, sep="\n  ")
    if data.get("before"):
        print(f"before: {data['before']['correct']}/{data['before']['checkable']}", *data["before"]["wrong"], sep="\n  ")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
