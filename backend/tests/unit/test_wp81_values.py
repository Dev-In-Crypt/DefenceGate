"""WP-81: the sum of values per supplier (`suppliers.value_totals`, `suppliers.valued`), the owner's rule of 22 October 2026."""

from dgate.suppliers import value_totals, valued


def row(ok: bool, shared: bool, vc: str | None, amount: float | None, n: int, lots: int = 0) -> dict:
    return {"ok": ok, "shared": shared, "vc": vc, "amount": amount, "n": n, "lots": lots}


def test_per_currency_never_converted_most_contracts_first():
    got = value_totals([row(True, False, "PLN", 300, 1), row(True, False, "EUR ", 1234.567, 3, lots=1),
                        row(False, True, None, None, 2), row(False, False, None, None, 4)], of=10)
    assert got == {"byCurrency": [{"currency": "EUR", "amount": 1234.57, "count": 3, "lotEstimates": 1},
                                  {"currency": "PLN", "amount": 300.0, "count": 1, "lotEstimates": 0}],
                   "of": 10, "withoutValue": 6, "shared": 2}


def test_no_value_at_all():
    assert value_totals([], of=5) == {"byCurrency": [], "of": 5, "withoutValue": 5, "shared": 0}


def test_the_condition_is_one_winner_a_total_or_lot_sum_above_the_placeholder_with_a_currency():
    sql = valued("a.wn", "o.va", "o.vc", "o.vk")
    assert "a.wn = 1" in sql and "o.vk IN ('total', 'lot_sum')" in sql and "o.va > 1.0" in sql and "o.vc IS NOT NULL" in sql
