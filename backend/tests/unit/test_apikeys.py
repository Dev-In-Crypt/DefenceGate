"""WP-153: the shape of an API key, the routes a key may call, and the /api page's list of them."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.openapi.utils import get_openapi

from dgate import api, apikeys

ENDPOINTS = Path(__file__).resolve().parents[3] / "web" / "lib" / "data" / "api-endpoints.json"


def test_a_new_key_has_a_public_prefix_and_256_random_bits():
    key, prefix = apikeys.new_key()
    m = apikeys._KEY.match(key)
    assert m and m.group(1) == prefix and len(m.group(2)) == 43
    assert apikeys.new_key()[0] != key


@pytest.mark.parametrize(("path", "scope"), [
    ("/v1/opportunities", "tenders"), ("/v1/opportunities/42", "tenders"), ("/v1/opportunities/42/versions", "archive"),
    ("/v1/opportunities/", None), ("/v1/opportunities/x", None), ("/v1/tenders", None), ("/v1/account/me", None),
    ("/v1/opportunities/42/versions/1", None),
])
def test_only_the_listed_routes_have_a_scope(path, scope):
    assert apikeys.scope_of(path) == scope


@pytest.mark.skipif(not ENDPOINTS.exists(), reason="the web folder is not in this checkout")
def test_the_api_page_lists_exactly_the_key_routes_with_parameters_the_api_has():
    listed = json.loads(ENDPOINTS.read_text(encoding="utf-8"))["endpoints"]
    spec = get_openapi(title="dgate", version="0", routes=api.app.routes)   # the document /openapi.json serves with DGATE_DOCS=1
    concrete = {"/v1/opportunities": "/v1/opportunities", "/v1/opportunities/{opp_id}": "/v1/opportunities/1",
                "/v1/opportunities/{opp_id}/versions": "/v1/opportunities/1/versions"}
    assert sorted(e["path"] for e in listed) == sorted(concrete) and len(apikeys.ROUTES) == len(listed)
    for e in listed:
        assert apikeys.scope_of(concrete[e["path"]]) == e["scope"], e["path"]
        have = {p["name"] for p in spec["paths"][e["path"]]["get"].get("parameters", [])}
        assert {p["name"] for p in e["params"]} <= have, e["path"]
