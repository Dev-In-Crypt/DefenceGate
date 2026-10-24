"""WP-112: the trade rules of "who to approach" (`demand.prime_of` with the answer's prefixes, `demand.trades`) and the market's
all-defence basis text."""

from __future__ import annotations

from dgate import demand, stats


def test_indra_is_marked_for_vehicle_codes_only():
    assert demand.prime_of("indra sistemas")["group"] == "Indra"              # no prefixes: the name alone, as before
    assert demand.prime_of("indra sistemas", ["343"])["group"] == "Indra"
    assert demand.prime_of("indra sistemas", ["3542"])["group"] == "Indra"
    assert demand.prime_of("indra sistemas", ["60", "631", "72"]) is None     # a logistics firm's codes
    assert demand.prime_of("navantia sa sme", ["60"])["group"] == "Navantia"  # SIPRI: any trade
    # a joint venture of Indra and Thales is Thales's when Indra is not marked
    assert demand.prime_of("ute indra sistemas thales programas de electronica", ["72"])["group"] == "Thales"


def test_the_trade_of_the_codes():
    assert demand.trades(["343", "4447"]) == ["34", "354", "44"]
    assert demand.trades(["35812", "358113", "1811"]) == ["18", "358"]
    assert demand.trades(["35"]) == ["35"]
    assert demand.trades(["3542"]) == ["34", "354"]


def test_the_all_defence_basis_says_what_it_counts():
    assert "Only notices that state the defence directive" in stats.BASIS["months"]
    assert "services and supplies that defence buyers buy" in stats.RELEVANT_BASIS["months"]
    assert stats.RELEVANT_BASIS["countries"] == stats.BASIS["countries"]

