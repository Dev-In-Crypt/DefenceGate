"""WP-125 (verification round 6, 25 October 2026): "castings" found a Swiss water-pipe tender through TED's code title "Foundry moulds".
Against a real Postgres: the tender search reads the castings group without its place words, and a typed place word still finds both."""

from __future__ import annotations

import pytest

from tests.integration.test_wp98 import _fresh_cache, client, get, ids, put  # noqa: F401 (fixtures)

pytestmark = pytest.mark.integration


def test_castings_finds_castings_and_not_a_tender_titled_by_the_code_foundry_moulds(client, conn):  # noqa: F811
    put(conn, "F-PIPES", "IWB, Wasserleitungsrohre (Guss) und Formstücke", country="CH", cpv=["43415000"],
        title_en="Switzerland – Foundry moulds – IWB, Wasserleitungsrohre (Guss) und Formstücke")
    put(conn, "F-ALU", "Aluminium castings for gearboxes", cpv=["34320000"])
    put(conn, "F-GUSS", "Lieferung von Gussteilen für Fahrzeuge", cpv=["34320000"])
    put(conn, "F-FONDERIE", "Pièces de fonderie pour véhicules", country="FR", cpv=["34320000"])
    page = get(client, "/v1/tenders", q="castings")
    assert ids(page) == ["F-ALU", "F-FONDERIE", "F-GUSS"]
    assert "foundry" not in page["alsoSearched"] and "fonderie" not in page["alsoSearched"]
    # typed, "foundry" is the visitor's own word: it finds what its title says, and the group's terms still search the castings
    assert ids(get(client, "/v1/tenders", q="foundry")) == ["F-ALU", "F-FONDERIE", "F-GUSS", "F-PIPES"]
    assert ids(get(client, "/v1/tenders", q="Gussteile")) == ["F-ALU", "F-FONDERIE", "F-GUSS"]
