"""WP-175 (QA of 24 November 2026), no database: a Greek or Bulgarian name gives a readable address (D-18), and PLACSP's "UK" is
the United Kingdom's ISO code (D-7)."""

from __future__ import annotations

from dgate import placsp_awards
from dgate.funding import make_slug, slugify


def test_greek_and_cyrillic_names_give_a_readable_address():
    assert make_slug(5, "ΥΠΟΥΡΓΕΙΟ ΕΘΝΙΚΗΣ ΑΜΥΝΑΣ - Γενική Διεύθυνση") == "5-ypourgeio-ethnikis-amynas-geniki-dieythynsi"
    assert make_slug(6, "Министерство на отбраната") == "6-ministerstvo-na-otbranata"
    assert slugify("Сухопътни войски, й") == "suhopatni-voyski-y"


def test_latin_addresses_are_as_before():
    assert make_slug(7, "Bundesamt für Ausrüstung, Informationstechnik") == "7-bundesamt-fur-ausrustung-informationstechnik"
    assert make_slug(8, "Café Ñandú") == "8-cafe-nandu"
    assert make_slug(9, "???") == "9"


def test_placsp_uk_is_gb():
    assert placsp_awards._country({"country": "UK"}) == "GB"
    assert placsp_awards._country({"country": " gb "}) == "GB"
    assert placsp_awards._country({"country": "FR"}) == "FR"
