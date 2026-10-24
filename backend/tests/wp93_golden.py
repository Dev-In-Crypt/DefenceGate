"""Builds the derived parts of the WP-93 regression set (web/lib/data/wp93-pairs.json). Not a test; tests/unit/test_wp93.py checks
that what it wrote is still what the code gives.

    python -m tests.wp93_golden readings   # the rule readings, from the verifiers' saved documents (WP93_DOCS, read only)
    python -m tests.wp93_golden derive     # `after` facts, the programme verdicts of each profile and the expected verdict of each pair

`requests` (the assessment request of each profile) is written by web/lib/wp93.check.ts with WP93_WRITE=1 (lib/profile.ts toRequest).
"""

from __future__ import annotations

import html
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

from dgate import eligibility, verdict
from dgate.readiness import api, seed
from dgate.rule_readings import read_aid_page, read_document

FIXTURE = Path(__file__).resolve().parents[2] / "web" / "lib" / "data" / "wp93-pairs.json"
DOCS = Path(os.environ.get("WP93_DOCS", "D:/DEFENCEGATE TESTS/elig-check"))
# Where each call's readings come from: the document the verifiers saved, or (RAPID) the sentence they quote from the agency's page.
READ_FROM = {
    "24": "A/docs/eic-wp-2026.txt", "25": "A/docs/eic-wp-2026.txt", "131": "A/docs/eic-wp-2026.txt", "129": "A/docs/eic-wp-2026.txt",
    "146": "B/docs/dep11.txt", "148": "B/docs/dep11.txt", "149": "B/docs/dep11.txt", "191": "B/docs/dep12.txt", "192": "B/docs/dep12.txt",
}
AID_PAGES = {"179": "B/docs/cdf.html"}
RAPID_QUOTE = "effectif consolidé de moins de 2000 salariés"   # the verifier's quote of the AID RAPID page (A/pairs.csv row 22)
EIC_OWN = ("24", "25", "129")            # calls whose facts were read from the EIC work programme for their topic (scope general)


def load() -> dict[str, Any]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def save(data: dict[str, Any]) -> None:
    FIXTURE.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def readings(data: dict[str, Any]) -> None:
    out: dict[str, Any] = {}
    for cid, rel in READ_FROM.items():
        text = (DOCS / rel).read_text(encoding="utf-8", errors="replace")
        got = read_document(text, data["calls"][cid]["topic"])
        if got:
            out[cid] = {"from": rel, "facts": got}
    for cid, rel in AID_PAGES.items():
        page = html.unescape(re.sub(r"<[^>]+>", " ", (DOCS / rel).read_text(encoding="utf-8", errors="replace")))
        out[cid] = {"from": rel, "facts": read_aid_page(page)}
    out["188"] = {"from": "the AID RAPID page, as quoted by the verifier", "facts": read_aid_page(RAPID_QUOTE)}
    data["readings"] = out


def after_facts(data: dict[str, Any]) -> dict[str, Any]:
    """The facts as the code now serves them: a reading replaces the model's fact (eligibility.extract_one, ops/rule_readings), the EIC
    work programme read for the topic is `programme` scope (eligibility.assemble), an entity list that names required partners is
    `required_partners` (eligibility.required_partners), and an AID page's facts come without the quote (eligibility.page_rules)."""
    out = {}
    for cid, call in data["calls"].items():
        facts = {k: dict(v) for k, v in call["facts"].items()}
        read = (data.get("readings") or {}).get(cid, {}).get("facts", {})
        state = call["state"]
        if cid in AID_PAGES or cid == "188":
            page = eligibility.page_rules({"rules_read": read})
            facts, state = (page["facts"], "read") if page else (facts, state)
        else:
            source_scope = "general" if cid in EIC_OWN or cid == "131" else None
            for k, f in read.items():
                facts[k] = {"value": f["value"], "note": f["note"], "quote": f["quote"], "scope": source_scope or "call_document"}
            if cid in EIC_OWN or cid == "131":
                for k, f in facts.items():
                    if f["scope"] == "general":
                        facts[k] = {**f, "scope": "programme", "note": eligibility._without_scope_note(f["note"])}
            facts = eligibility.required_partners(facts)
        out[cid] = {**call, "state": state, "facts": facts}
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
                                       for r in a["rules"]]}
                            for a in payload["assessments"]],
            "roadmap": {"steps": [{"code": s["code"], "name": s["name"], "blockingFor": s["blockingFor"]} for s in payload["roadmap"]["steps"]]},
        }
    data["assessments"] = assessments
    # every fixture call for every profile (the 60 pairs are among them): the browser's verdict must be this one
    data["expected"] = {f"{k}|{c}": expected(data, k, c) for k in sorted(assessments) for c in sorted(data["after"], key=int)} if assessments else {}


def expected(data: dict[str, Any], profile: str, cid: str) -> dict[str, Any]:
    call = data["after"][cid]
    req = data["requests"][profile]
    # The SEAP-partner answer stays in the browser (lib/profile.ts); the API takes it when a caller sends it, as here, so that the two
    # implementations are compared on the same answers. Without it the API's partner line asks instead (the cautious side).
    seap = {"yes": True, "no": False}.get(data["profiles"][profile]["stored"].get("seapPartner", ""))
    answers = {**req["profile"], **({"seap_partner": seap} if seap is not None else {})}
    r = verdict.call_fit({"state": call["state"], "facts": call["facts"], "programme": call["programme"], "topic": call["topic"]},
                         answers, data["assessments"][profile])
    return {"fit": r["fit"], "shown": verdict.shown_fit(r), "word": verdict.fit_word(r), "conditions": r["conditions"],
            "lines": [{k: x[k] for k in ("key", "verdict", "reason")} for x in ((r.get("result") or {}).get("lines") or [])]}


def main(argv: list[str]) -> int:
    data = load()
    if "readings" in argv:
        readings(data)
    if "derive" in argv:
        derive(data)
    save(data)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
