"""WP-57: the supplier list takes a country as a code, a three-letter code or an English name (UX audit M6)."""

from __future__ import annotations

import pytest

from . import test_network_api as net
from . import test_supplier_map as sup
from .test_wp39 import seed_suppliers

_fresh_cache, client, env = net._fresh_cache, net.client, sup.env

pytestmark = pytest.mark.integration


def test_a_country_name_or_three_letter_code_lists_the_same_suppliers_as_the_code(conn, env, client):
    seed_suppliers(conn, env)
    by_code = client.get("/v1/suppliers?country=DE&sort=name").json()
    assert by_code["total"] == 3
    for given in ("Germany", "germany", "DEU", "deu", "de", "Deutschland", "Germany,DEU"):
        got = client.get("/v1/suppliers", params={"country": given, "sort": "name"})
        assert got.status_code == 200, given
        assert got.json()["items"] == by_code["items"], given
    # the k rule still holds under a name: Estonia has one supplier
    assert client.get("/v1/suppliers?country=Estonia").json()["withheld"] is True
    assert client.get("/v1/suppliers?country=EST").json()["withheld"] is True


def test_a_value_that_is_no_country_is_a_clear_422_not_a_list(conn, env, client):
    seed_suppliers(conn, env)
    for given in ("Atlantis", "Germ", "XYZ", "DE,Atlantis"):
        got = client.get("/v1/suppliers", params={"country": given})
        assert got.status_code == 422, given
        assert "is not a country" in got.json()["detail"]
    assert client.get("/v1/suppliers?country=ZZ").status_code == 200       # a code nobody holds is an empty group
