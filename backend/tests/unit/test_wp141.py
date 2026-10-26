"""WP-141: with a saved profile, a call whose action admits only some kinds of applicant (EDIP common procurement, SEAP support 114, EDPCI
preparation 193) gave "Blocked by: an established SEAP" over a row "Who may apply: Check". The row now carries the rule's verdict in a
sentence, in the API's verdict (dgate/verdict.call_fit) as in the browser's (web/lib/fit.ts callFit, web/lib/wp141.check.ts). The calls and
profiles are the verified sets (web/lib/data/wp93-pairs.json, wp102-pairs.json); test_wp93/test_wp102 compare every line with the browser's."""

from __future__ import annotations

import json
from pathlib import Path

from dgate import verdict

DATA = Path(__file__).resolve().parents[3] / "web" / "lib" / "data"
ONLY = {
    "110": "Only contracting authorities, international organisations, SEAPs and the EDA may apply to this call.",
    "111": "Only contracting authorities, international organisations, SEAPs and the EDA may apply to this call.",
    "112": "Only contracting authorities, international organisations, SEAPs and the EDA may apply to this call.",
    # WP-143: the document admits a SEAP being established too
    "114": ("Only a SEAP may apply to this call: an established one, or one being established whose application has already been "
            "submitted to the Commission."),
    "193": "Only a SEAP or a group of Member States may apply to this call.",
}


def _fit(data: dict, key: str, cid: str, **profile: object) -> dict:
    c = data["after"][cid]
    answers = {**data["requests"][key]["profile"], **profile}
    return verdict.call_fit({"state": c["state"], "facts": c["facts"], "programme": c["programme"], "topic": c["topic"]}, answers,
                            data["assessments"][key])


def test_the_row_who_may_apply_says_the_rule_that_blocks_in_a_sentence():
    blocked = 0
    for name in ("wp93-pairs.json", "wp102-pairs.json"):
        data = json.loads((DATA / name).read_text(encoding="utf-8"))
        for cid in sorted(set(data["after"]) & set(ONLY)):
            for key in data["requests"]:
                r = _fit(data, key, cid)
                if not any(b.startswith(f"{verdict.WHO_MAY_APPLY}: ") for b in r["blockedBy"]):
                    continue
                lines = r["result"]["lines"]
                who = [x for x in lines if x["label"] == verdict.WHO_MAY_APPLY]
                assert len(who) == 1 and who[0]["verdict"] == "no", (key, cid, lines)
                assert who[0]["reason"].startswith(ONLY[cid] + " "), who[0]["reason"]
                assert not any(x["key"] == "entity" for x in lines), "the document's 'Check' row gave way"
                assert r["result"]["verdict"] == "no" and r["fit"] == "no"
                assert verdict.fit_word(r).startswith("Blocked by: "), "the badge as before"
                blocked += 1
    assert blocked == 50   # wp93: 10 profiles x 110 112 114 193; wp102: 10 profiles x 111


def test_the_first_row_where_the_document_names_nobody_and_nothing_replaced_for_a_seap():
    data = json.loads((DATA / "wp93-pairs.json").read_text(encoding="utf-8"))
    r = _fit(data, "P1", "193")
    assert r["result"]["lines"][0]["key"] == "who", "193 has no 'who may apply' fact: the rule's row comes first"
    seap = _fit(data, "P1", "114", applicant_kind="seap")
    assert seap["fit"] != "no"
    assert not any(x["key"] == "who" for x in seap["result"]["lines"])


def test_a_call_whose_rules_were_not_read_gets_the_row_too():
    r = verdict.call_fit({"state": "not_read", "facts": {}, "programme": "EDF", "topic": "EDF-EDIP-P-2026-FNLC-CSA-PREP"},
                         {"country": "ES", "applicant_kind": "company_or_research"}, None)
    assert r["fit"] == "no"
    assert [x["key"] for x in r["result"]["lines"]] == ["who"]
    assert r["result"]["lines"][0]["reason"].startswith(ONLY["193"])
