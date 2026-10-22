"""WP-66: the CPV level of a code, the request the demand map accepts, and its price in the rate limit."""

from __future__ import annotations

import json
import pathlib

import pytest
from pydantic import ValidationError

from dgate import demand, hardening


@pytest.mark.parametrize("code, head", [
    ("34300000", "343"), ("44470000", "4447"), ("35000000", "35"), ("34352100", "343521"), ("10000000", "10"),
    ("03000000", "03"), ("31712310", "3171231"), ("30200000", "302"),
])
def test_a_code_stands_for_its_level_in_the_tree(code, head):
    assert demand.prefix(code) == head


def test_the_request_is_bounded_and_normalised():
    ok = demand.DemandIn(cpv=["34300000-0", "34300000", " 44470000 "], countries=["PL", "ES", "PL"])
    assert ok.cpv == ["34300000", "44470000"]
    assert ok.countries == ["ES", "PL"]                           # the map's order, once each
    assert demand.DemandIn(cpv=["34300000"]).countries == list(demand.COUNTRIES)
    for bad in ({"cpv": []}, {"cpv": ["343"]}, {"cpv": ["3430000a"]}, {"cpv": [f"{31000000 + i}" for i in range(16)]},
                {"cpv": ["34300000"], "countries": ["IT"]}, {"cpv": ["34300000"], "countries": []},
                {"cpv": ["34300000"], "countries": ["ES", "DE", "FR", "PL", "NL", "ES"]},
                {"cpv": ["34300000"], "profile": {}}):
        with pytest.raises(ValidationError):
            demand.DemandIn(**bad)


def test_the_demand_map_is_priced_and_its_body_is_bounded():
    assert hardening.request_cost("/v1/readiness/demand", {}) == 5
    assert "/v1/readiness/demand".startswith(hardening.BODY_LIMITED_PREFIXES)


def test_the_coverage_line_says_what_the_map_is_not():
    assert "not the sub-tier needs of prime contractors" in demand.COVERAGE
    assert "about a tenth of EU defence spending" in demand.COVERAGE


def test_the_site_demo_answer_has_the_api_shape():
    """web/lib/mock/demand.json (the demo build's answer, from production) is what the response model serves, field for field."""
    path = pathlib.Path(__file__).resolve().parents[3] / "web" / "lib" / "mock" / "demand.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert demand.Demand.model_validate(data).model_dump(mode="json") == data
