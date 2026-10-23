"""WP-91 (UX audit 6, the funding path): the pure parts, without a database."""

from __future__ import annotations

import re

from dgate import funding, partners, rules_apply, textsearch
from dgate.network_api import relevance, topic_alternatives
from dgate.readiness.seed import load_file


def test_the_programme_chip_of_an_edip_topic_filed_under_the_edf():
    assert funding.programme_of("EDF", "EDF-EDIP-USI-2026-LS-IRA-MAB") == "EDIP-USI"
    assert funding.programme_of("EDF", "EDF-EDIP-P-2027-FNLC-CPA-AMDS") == "EDIP"
    assert funding.programme_of("EDF", "EDF-2026-DA-SPACE-SSA") == "EDF"
    assert funding.programme_of("EDF") == "EDF", "without the topic, as before (the follows of an account)"
    assert funding.programme_of("PL-NCBR", "EDF-EDIP-USI-X") == "NATIONAL"
    assert "EDIP-USI" in funding.PROGRAMME_CHIPS


def test_the_sql_of_the_chips_reads_the_prefixes_of_the_regime():
    assert "EDF-EDIP-USI-" in funding._USI_SQL and "EDF-EDIP-P-" in funding._EDIP_SQL
    # who may apply: the three EDIP actions that are not open to a company, by the tokens `regime.action_of` reads
    for token in ("-CPA-", "-SA-", "-SEAP-", "-CSA-", "-PREP-"):
        assert token in funding.WHO_MAY_APPLY
    assert "'public'" in funding.WHO_MAY_APPLY and "'companies'" in funding.WHO_MAY_APPLY


def test_the_new_synonyms_find_what_the_audit_typed():
    def hit(q: str, text: str, codes: str = "") -> bool:
        query = textsearch.parse(q)
        return query is not None and query.matches(text, codes)

    assert hit("software", "Ground segment software") and hit("software", "Algorithms for target tracking")
    assert hit("autonomy", "Autonomous systems") and hit("AI", "Machine learning for logistics")
    assert hit("cyber", "Cybersecurity uptake") and hit("cybersecurity", "Cyber defence of networks")
    assert hit("SME", "Innowacje dla MŚP") and hit("SME", "Appel à projets pour PME") and hit("SME", "Call for SMEs")
    assert not hit("AI", "Available against all")
    assert not hit("EUDIS", "EDF open call"), "no synonym invents a programme"
    # one idea per row: no word in two rows, so a search never widens through a chain
    seen: dict[str, int] = {}
    for i, row in enumerate(textsearch.SYNONYMS):
        for w in row:
            assert seen.setdefault(w, i) == i, w


def test_the_topic_words_of_a_call_title():
    assert partners.topic_words("Unmanned systems and counter-unmanned systems") == ["unmanned", "counter"]
    assert partners.topic_words("Missiles, ammunition and bombs") == ["missiles", "ammunition", "bombs"]
    assert partners.topic_words("Support for the functioning of SEAPs, including for the purpose of establishing") == ["seaps"]
    q = partners.topic_query("Unmanned systems and counter-unmanned systems")
    assert partners.is_topical(q, "UAS swarm detection") and partners.is_topical(q, "Counter-drone sensor")
    assert not partners.is_topical(q, "Naval platform") and not partners.is_topical(None, "anything")


def test_the_topic_search_of_organisations_takes_synonyms_and_at_most_four_words():
    assert topic_alternatives("drone") == [["drone", "uas", "uav", "unmanned", "rpas"]]
    assert topic_alternatives("the drone")[0][0] == "drone", "a stop word is dropped"
    assert len(topic_alternatives("one two three four five six")) == 4
    assert topic_alternatives("") == [] and topic_alternatives("--") == []


def test_defence_relevance_of_a_project():
    assert relevance("EDF", None) == 2 and relevance("PADR", "x") == 2
    assert relevance("HORIZON", "HORIZON-CL3-2022-BM-01") == 1 and relevance("H2020", "H2020-SU-SEC-2018") == 1
    assert relevance("HORIZON", "HORIZON-CL6-2023-FARM2FORK") == 0 and relevance(None, None) == 0


def test_the_country_groups_of_the_rules_block_from_the_seed():
    content = load_file()
    usi = rules_apply.build(content, "EDF", "EDF-EDIP-USI-2027-LS-IRA-CUXS")
    assert set(usi["byCountry"]) == set(rules_apply.SUMMARY_GROUPS)
    eu = {r["rule"]: r for r in usi["byCountry"]["EU"]}
    assert eu["USI-INVOLVES-UA"]["asks"] == ["ua_partner"] and eu["USI-ESTABLISH"]["outcome"] == "met"
    # never "met" for a rule that reads an answer the summary does not have
    for group in usi["byCountry"].values():
        for r in group:
            assert r["outcome"] != "met" or not r["asks"]
    edf = rules_apply.build(content, "EDF", "EDF-2026-DA-SPACE-SSA")
    assert {r["rule"]: r["outcome"] for r in edf["byCountry"]["UA"]}["EDF-ESTABLISH"] == "conditional"
    cpa = rules_apply.build(content, "EDF", "EDF-EDIP-P-2027-FNLC-CPA-AMDS")
    assert [r["outcome"] for r in cpa["forCompany"]] == ["not_met"]
    assert rules_apply.build(content, "HORIZON", "HORIZON-CL3-2026-01-DRS-01").get("byCountry") is None, "no rules encoded: no summary"


def test_the_search_text_reads_the_tags_and_the_sme_flag():
    sql = re.sub(r"\s+", " ", funding.SEARCH_TEXT)
    assert "conditions_raw->>'tags'" in sql and "'for_smes' = 'true' THEN 'SME'" in sql
