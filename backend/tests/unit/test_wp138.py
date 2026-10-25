"""WP-138: data findings of verification round 8 (unit part)."""

from __future__ import annotations

import pytest

from dgate.awards import person_reason
from dgate.normalise import VALUE_UNIT_PRICE, contractor_is_person, from_ted, unit_price_total

# The five public bodies of the pl_ezam raw check (25 October 2026) that the Polish person rules read as sole traders.
PUBLIC_BODIES = [
    "Gmina Trawniki",
    "Centralny Ośrodek Informatyki",
    "Samodzielny Publiczny Zakład Opieki Zdrowotnej w Wieluniu",
    "SAMODZIELNY PUBLICZNY ZAKŁAD OPIEKI ZDROWOTNEJ W WIELUNIU",
    "Poznańskie Inwestycje Miejskie w imieniu Miasto Poznań pl. Kolegiacki 17 61-841 Poznań",
]


@pytest.mark.parametrize("name", PUBLIC_BODIES)
def test_a_polish_public_body_is_not_read_as_a_person(name):
    assert person_reason(name, None, "PL") is None
    assert not contractor_is_person({"contractorName": name, "contractorCountry": "PL"})


@pytest.mark.parametrize("name", [
    "Ośrodek Szkolenia Kierowców Jan Przykładowy",          # a sole trader trading as an "ośrodek": his given name
    "P.P.H.U. Krismark Krystyna Łopuszańska",
])
def test_a_sole_trader_with_a_public_word_or_a_trading_name_stays_a_person(name):
    assert person_reason(name, None, "PL") is not None


def test_a_pesel_is_a_person_whatever_the_name_says():
    assert contractor_is_person({"contractorName": "Gmina Przykładowa", "contractorNationalId": "44051401458",
                                 "contractorCountry": "PL"})


# ------------------------------------------------------------------ two gminas of one name

def _org(i, name, **kw):
    return {"id": i, "country": "PL", "name": name, "display_name": None, "suppressed": False, "person": False,
            "reg": None, "vat": None, "pic": None, "notices": 0, "raw_names": [], "legal_form": None,
            "org_role": "buyer", "is_defence_buyer": False, "buys": True, **kw}


def test_a_twin_gmina_name_is_ambiguous_and_its_rows_join_only_by_a_number():
    from dgate.ops import accept_merge_candidates as amc
    from dgate.ops.org_repair import ambiguous_name

    assert ambiguous_name("PL", "gmina lagow") and ambiguous_name("PL", "gmina krasne")
    assert ambiguous_name("PL", "powiat tomaszowski") and not ambiguous_name("PL", "gmina trawniki")
    orgs = {1: _org(1, "gmina lagow", reg="6572524434"), 2: _org(2, "gmina lagow"),
            3: _org(3, "gmina krasne", reg="7611542308"), 4: _org(4, "gmina krasne"),
            5: _org(5, "gmina iwaniska", reg="6572524434"), 6: _org(6, "gmina iwaniska")}
    pair = lambda cid, a, b, method: {"id": cid, "a": a, "b": b, "confidence": 0.9, "match_method": method,  # noqa: E731
                                      "evidence": "", "status": "pending"}
    pairs = [pair(1, 1, 2, "cleared_register_number"), pair(2, 3, 4, "same_name_different_identifier"),
             pair(3, 5, 6, "same_name_different_identifier")]
    review = {i: {"decision": "ACCEPT", "head": None, "confidence": None, "reason": "r"} for i in (1, 2, 3)}
    groups, refused, _ = amc.plan_reviewed(pairs, orgs, review)
    assert refused == {"twin_name": 1}                        # Krasne by name alone: refused
    assert sorted(g["head"] for g in groups) == [1, 5]        # Łagów by its cleared number; a unique name as before


# ------------------------------------------------------------------ unit prices stated as a total

@pytest.mark.parametrize("amount,cpv,expected", [
    (74.13, ["79620000"], True),          # BWI ANÜ call-off: an hourly rate
    (300.0, ["79624000"], True),          # nursing staff, a rate
    (6.35, ["09310000", "65300000"], True),   # electricity: a price per MWh
    (500.0, ["79620000"], True),
    (500.01, ["79620000"], False),        # over the limit: a contract
    (398.0, ["60140000"], False),         # a bus charter of EUR 398 is a contract
    (308.5, ["39143112"], False),         # a mattress
    (1.0, ["79620000"], False),           # a placeholder, already no value
    (74.13, ["35000000", "79620000"], False),   # the main code decides
    (74.13, [], False),
])
def test_a_total_is_a_unit_price_only_for_a_rate_code_and_at_most_500(amount, cpv, expected):
    assert unit_price_total(amount, "total", cpv) is expected


def test_only_a_total_is_read_as_a_unit_price():
    assert not unit_price_total(74.13, "estimated", ["79620000"])
    assert not unit_price_total(74.13, None, ["79620000"])


def _award(value: str, cpv: str) -> dict:
    return {"publication-number": "689828-2026", "notice-type": "can-standard", "buyer-name": ["BWI GmbH"],
            "notice-title": {"deu": "Deutschland – Überlassung von Personal – 2000284335 ANÜ"},
            "official-language": ["DEU"], "buyer-country": ["DEU"], "publication-date": "2026-10-07+02:00",
            "classification-cpv": [cpv], "total-value": value, "total-value-cur": "EUR"}


def test_the_ted_mapper_marks_an_hourly_rate_and_keeps_a_contract_total():
    rate = from_ted(_award("74.13", "79620000"))
    assert (rate.value_amount, rate.value_kind) == (74.13, VALUE_UNIT_PRICE)
    contract = from_ted(_award("2500000", "79620000"))
    assert contract.value_kind == "total"
    small = from_ted(_award("398", "60140000"))
    assert small.value_kind == "total"
