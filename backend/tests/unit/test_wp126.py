"""WP-126: a PLACSP awarded amount under EUR 100 is a unit price, set aside and in no sum. No database."""

from dgate import placsp_awards
from dgate.award_value import SET_ASIDE_UNIT_PRICE, placsp_unit_price


def _landed(*amounts: float) -> dict:
    return {"results": [{"result_code": "8", "value": v, "currency": "EUR",
                         "winners": [{"name": f"Ejemplo {i} S.L.", "country": "ES", "identifier": None}]}
                        for i, v in enumerate(amounts)], "natural_persons": 0}


def test_an_amount_under_a_hundred_is_a_unit_price_and_a_placeholder_or_a_minor_contract_is_not():
    assert placsp_unit_price(84.95) and placsp_unit_price(1.02) and placsp_unit_price(99.99)
    assert not placsp_unit_price(1.0) and not placsp_unit_price(100.0) and not placsp_unit_price(300.0)
    assert not placsp_unit_price(None)


def test_the_reader_sets_a_unit_price_aside_and_keeps_its_kind_and_currency():
    got = placsp_awards.read(_landed(84.95, 300.0, 0.0), "contract").winners
    shoes, minor, placeholder = got
    assert (shoes.value_amount, shoes.value_currency, shoes.value_kind) == (None, "EUR", "contract")
    assert (shoes.value_set_aside, shoes.value_set_aside_reason) == (84.95, SET_ASIDE_UNIT_PRICE)
    assert (minor.value_amount, minor.value_set_aside, minor.value_set_aside_reason) == (300.0, None, None)
    assert (placeholder.value_amount, placeholder.value_set_aside, placeholder.value_kind) == (None, None, None)
