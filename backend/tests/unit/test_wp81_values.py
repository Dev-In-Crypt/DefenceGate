"""WP-81: the sum of values per supplier (`suppliers.value_totals`, `suppliers.valued`), the owner's rule of 22 October 2026.

WP-95 (persona round of 23 October 2026, A1.1): `value_totals` reads one row per procurement (`suppliers.best`) with
the kind of its value (contract, framework, estimate); only contract values are summed in `byCurrency`, framework
ceilings and estimates apart (`frameworks`, `estimates`); a sum of lot estimates is an estimate (it was summed with the
contract values, counted as `lotEstimates`)."""

from dgate.suppliers import best, value_totals, valued


def row(kind: str | None, vc: str | None, va: float | None, *, shared: bool = False, placsp: bool = False,
        k: int = 0, **notice) -> dict:
    return {"vk": kind, "vc": vc, "va": va, "shared": shared, "vp": placsp, "k": k, **notice}


def test_per_currency_never_converted_most_contracts_first():
    rows = [row("contract", "PLN", 300 * 10), row("contract", "EUR ", 1000.0), row("contract", "EUR", 234.567 * 10),
            row("contract", "EUR", 1000.0), row(None, None, None, shared=True), row(None, None, None), row(None, None, None)]
    got = value_totals(rows, of=10)
    assert got == {"byCurrency": [{"currency": "EUR", "amount": 4345.67, "count": 3, "lotEstimates": 0},
                                  {"currency": "PLN", "amount": 3000.0, "count": 1, "lotEstimates": 0}],
                   "of": 10, "withoutValue": 6, "shared": 1, "suspect": 0, "frameworks": [], "estimates": []}


def test_frameworks_and_estimates_are_listed_apart_and_never_added_to_the_contract_values():
    """Rheinmetall 390572-2026: EUR 11,930,000 is the framework maximum (the tenders were 318,900); 712069-2026: EUR
    1,160,000 is the procedure's estimate (the award states no value). Neither is money the supplier won."""
    got = value_totals([row("contract", "EUR", 625371.0), row("framework", "EUR", 11930000.0),
                        row("estimate", "EUR", 1160000.0), row("estimate", "EUR", 40000.0)], of=4)
    assert got["byCurrency"] == [{"currency": "EUR", "amount": 625371.0, "count": 1, "lotEstimates": 0}]
    assert got["frameworks"] == [{"currency": "EUR", "amount": 11930000.0, "count": 1, "lotEstimates": 0}]
    assert got["estimates"] == [{"currency": "EUR", "amount": 1200000.0, "count": 2, "lotEstimates": 0}]
    assert (got["withoutValue"], got["suspect"]) == (0, 0)


def test_no_value_at_all():
    assert value_totals([], of=5) == {"byCurrency": [], "of": 5, "withoutValue": 5, "shared": 0, "suspect": 0,
                                      "frameworks": [], "estimates": []}


def test_a_value_under_a_thousand_is_a_unit_price_in_no_sum_and_counted():
    """WP-87: "EUR 48 over 1 contract" was a price per item, not a contract value."""
    got = value_totals([row("contract", "EUR", 1500.0), row("contract", "EUR", 48.0), row(None, None, None)], of=3)
    assert got["byCurrency"] == [{"currency": "EUR", "amount": 1500.0, "count": 1, "lotEstimates": 0}]
    assert (got["suspect"], got["withoutValue"]) == (1, 1)


def test_a_placsp_awarded_amount_under_a_thousand_is_a_contract_total_not_a_unit_price():
    """Owner, 23 October 2026: PLACSP awarded amounts are contract totals; only a TED-stated value is flagged."""
    from dgate.suppliers import is_suspect
    assert is_suspect(48, "contract") and is_suspect(999.99, "contract")
    assert not is_suspect(48, "contract", placsp=True) and not is_suspect(1000, "contract") and not is_suspect(None, "contract")
    # WP-95: a ceiling or an estimate is never summed, so it is never read as a unit price
    assert not is_suspect(48, "framework") and not is_suspect(48, "estimate")
    got = value_totals([row("contract", "EUR", 300.0, placsp=True)], of=1)
    assert got["byCurrency"] == [{"currency": "EUR", "amount": 300.0, "count": 1, "lotEstimates": 0}]


def test_each_procurement_is_valued_once_contract_before_ceiling_before_estimate():
    """WP-95: of the rows of one procurement (a twin pair, two notices), the one with a contract value stands for it."""
    rows = [row("estimate", "EUR", 9.0e6, k=1), row("contract", "EUR", 5000.0, k=1), row(None, None, None, k=1),
            row("framework", "EUR", 1.0e6, k=2), row(None, None, None, k=2), row(None, None, None, k=3),
            row("contract", "EUR", 4200.0, placsp=True, k=4), row("contract", "EUR", 5000.0, k=4)]
    got = best(rows)
    assert got[1]["vk"] == "contract" and got[1]["va"] == 5000.0
    assert got[2]["vk"] == "framework" and got[3]["va"] is None
    assert got[4]["vp"] and got[4]["va"] == 4200.0          # PLACSP's awarded amount before TED's value


def test_the_largest_contracts_are_the_contract_values_in_the_currencies_order_largest_first():
    def n(i, kind, cur, va, **kw):
        return row(kind, cur, va, k=i, id=i, native_id=f"{i}-2026", title_en=f"Notice {i}", title_original=None,
                   buyer_name_raw="Buyer", buyer_withheld=False, published_at=None, source_url=None, source_code="ted", **kw)

    rows = [n(i, "contract", "EUR", 10000.0 * i) for i in range(1, 13)]
    rows += [n(20, "framework", "EUR", 9.9e9), n(21, "estimate", "EUR", 9.0e9), n(22, "contract", "SEK", 9.0e8),
             n(23, "contract", "EUR", 50.0)]
    got = value_totals(rows, of=len(rows), largest=True)
    top = got["largest"]
    assert len(top) == 10
    assert [t["noticeId"] for t in top[:3]] == ["12-2026", "11-2026", "10-2026"]   # EUR (most contracts) first
    assert all(t["currency"] == "EUR" for t in top)       # the SEK contract comes after the EUR ones: not in the ten
    assert "20-2026" not in {t["noticeId"] for t in top} and "23-2026" not in {t["noticeId"] for t in top}
    assert top[0] == {"id": "12", "slug": "12-notice-12", "noticeId": "12-2026", "title": "Notice 12", "buyerName": "Buyer",
                      "publishedAt": None, "amount": 120000.0, "currency": "EUR", "sourceUrl": None, "source": "ted"}


def test_the_condition_is_one_winner_a_total_or_lot_sum_above_the_placeholder_with_a_currency():
    sql = valued("a.wn", "o.va", "o.vc", "o.vk")
    assert "a.wn = 1" in sql and "o.vk IN ('total', 'lot_sum')" in sql and "o.va > 1.0" in sql and "o.vc IS NOT NULL" in sql
