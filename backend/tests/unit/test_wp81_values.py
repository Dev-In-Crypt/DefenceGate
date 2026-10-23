"""WP-81: the sum of values per supplier (`suppliers.value_totals`, `suppliers.valued`), the owner's rule of 22 October 2026."""

from dgate.suppliers import value_totals, valued


def row(ok: bool, shared: bool, vc: str | None, amount: float | None, n: int, lots: int = 0) -> dict:
    return {"ok": ok, "shared": shared, "vc": vc, "amount": amount, "n": n, "lots": lots}


def test_per_currency_never_converted_most_contracts_first():
    got = value_totals([row(True, False, "PLN", 300, 1), row(True, False, "EUR ", 1234.567, 3, lots=1),
                        row(False, True, None, None, 2), row(False, False, None, None, 4)], of=10)
    assert got == {"byCurrency": [{"currency": "EUR", "amount": 1234.57, "count": 3, "lotEstimates": 1},
                                  {"currency": "PLN", "amount": 300.0, "count": 1, "lotEstimates": 0}],
                   "of": 10, "withoutValue": 6, "shared": 2, "suspect": 0}


def test_one_currency_in_two_rows_is_one_sum():
    # a PLACSP lot amount in a notice of several winners comes grouped apart from the single-winner notices
    got = value_totals([row(True, False, "EUR", 100, 2), row(True, True, "EUR", 50, 1)], of=3)
    assert got["byCurrency"] == [{"currency": "EUR", "amount": 150.0, "count": 3, "lotEstimates": 0}]
    assert (got["withoutValue"], got["shared"]) == (0, 0)


def test_no_value_at_all():
    assert value_totals([], of=5) == {"byCurrency": [], "of": 5, "withoutValue": 5, "shared": 0, "suspect": 0}


def test_a_value_under_a_thousand_is_a_unit_price_in_no_sum_and_counted():
    """WP-87: "EUR 48 over 1 contract" was a price per item, not a contract value."""
    got = value_totals([row(True, False, "EUR", 1500, 2), {**row(False, False, None, None, 1), "suspect": True},
                        row(False, False, None, None, 1)], of=4)
    assert got["byCurrency"] == [{"currency": "EUR", "amount": 1500.0, "count": 2, "lotEstimates": 0}]
    assert (got["suspect"], got["withoutValue"]) == (1, 1)


def test_the_sum_statement_reads_a_value_under_the_threshold_as_suspect():
    from dgate.suppliers import SUSPECT_VALUE_MAX, sums_select
    outer, group = sums_select()
    assert SUSPECT_VALUE_MAX == 1000
    bad = f"(x.ok AND x.va < {SUSPECT_VALUE_MAX} AND x.vk IS DISTINCT FROM 'awarded')"
    assert f"{bad} AS suspect" in outer and f"(x.ok AND NOT {bad}) AS ok" in outer
    assert f"sum(x.va) FILTER (WHERE (x.ok AND NOT {bad}))" in outer
    assert group == "GROUP BY 1, 2, 3, 4" and sums_select("x.org")[1] == "GROUP BY 1, 2, 3, 4, 5"


def test_a_placsp_awarded_amount_under_a_thousand_is_a_contract_total_not_a_unit_price():
    """Owner, 23 October 2026: PLACSP awarded amounts are contract totals; only a TED-stated value is flagged."""
    from dgate.suppliers import is_suspect
    assert is_suspect(48, "total") and is_suspect(48, "lot_sum") and is_suspect(999.99, None)
    assert not is_suspect(48, "awarded") and not is_suspect(1000, "total") and not is_suspect(None, "total")


def test_the_condition_is_one_winner_a_total_or_lot_sum_above_the_placeholder_with_a_currency():
    sql = valued("a.wn", "o.va", "o.vc", "o.vk")
    assert "a.wn = 1" in sql and "o.vk IN ('total', 'lot_sum')" in sql and "o.va > 1.0" in sql and "o.vc IS NOT NULL" in sql
