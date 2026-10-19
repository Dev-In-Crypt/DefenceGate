"""WP-57: a country written as a code, a three-letter code or an English name is the stored alpha-2 code
(UX audit M6: `/suppliers?country=Germany` and `?country=DEU` were a 404 page)."""
import pytest

from dgate.countries import to_iso2
from dgate.normalise import _ISO3_TO_2


@pytest.mark.parametrize("given,expected", [
    ("DE", "DE"), ("de", "DE"), (" De ", "DE"),
    ("DEU", "DE"), ("deu", "DE"), ("GBR", "GB"), ("ROU", "RO"), ("TUR", "TR"), ("XKX", "XK"),
    ("Germany", "DE"), ("germany", "DE"), ("GERMANY", "DE"), ("  Germany ", "DE"),
    ("Czechia", "CZ"), ("Czech Republic", "CZ"), ("United Kingdom", "GB"), ("UK", "GB"), ("uk", "GB"),
    ("Türkiye", "TR"), ("Turkey", "TR"), ("The Netherlands", "NL"), ("Bosnia & Herzegovina", "BA"),
    ("Côte d'Ivoire", "CI"), ("united states of america", "US"), ("Deutschland", "DE"), ("North-Macedonia", "MK"),
    ("ZZ", "ZZ"),                      # two letters are a code as written: an empty group, as before
])
def test_a_country_is_read_as_its_alpha2_code(given, expected):
    assert to_iso2(given) == expected


@pytest.mark.parametrize("given", ["", "   ", "Atlantis", "Germ", "DEUT", "XYZ", "G", "Ger many!", "1", "DE; DROP TABLE"])
def test_a_value_that_is_no_country_is_none(given):
    assert to_iso2(given) is None


def test_every_three_letter_code_of_the_connector_table_is_read():
    for iso3, iso2 in _ISO3_TO_2.items():
        assert to_iso2(iso3) == iso2
        assert to_iso2(iso3.lower()) == iso2


def test_the_countries_that_win_defence_notices_are_known_by_name():
    names = {"Poland": "PL", "France": "FR", "Spain": "ES", "Italy": "IT", "Romania": "RO", "Sweden": "SE", "Norway": "NO",
             "Finland": "FI", "Estonia": "EE", "Latvia": "LV", "Lithuania": "LT", "Ukraine": "UA", "Israel": "IL",
             "Switzerland": "CH", "Greece": "GR", "Hungary": "HU", "Bulgaria": "BG", "Portugal": "PT", "Belgium": "BE"}
    for name, code in names.items():
        assert to_iso2(name) == code
