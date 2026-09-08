"""Coverage floors (measured against the live sources on 7 September 2026).

A floor exists to make silent under-collection loud. It therefore has to match
the rhythm of the source: TED publishes nothing at weekends, so a single number
would mark every Monday run `partial` and train whoever reads the alerts to
ignore them.
"""

from datetime import date

import pytest

from dgate import config

# A week whose weekdays are known: 7 September 2026 is a Monday.
MONDAY = date(2026, 9, 7)
DAYS = {name: MONDAY.replace(day=MONDAY.day + i) for i, name in enumerate(
    ["mon", "tue", "wed", "thu", "fri", "sat", "sun"])}


@pytest.fixture(autouse=True)
def clean_settings():
    config.reset_cache()
    yield
    config.reset_cache()


def test_ted_expects_nothing_on_monday():
    """The Monday run covers Saturday and Sunday, when TED publishes nothing.

    Measured: 0 notices on each of two consecutive weekends.
    """
    assert config.settings().floor("ted", DAYS["mon"]) == 0


def test_ted_expects_the_most_midweek():
    """Wednesday to Saturday cover two full weekdays, about 150 notices."""
    for day in ("wed", "thu", "fri", "sat"):
        assert config.settings().floor("ted", DAYS[day]) == 60


def test_ted_expects_half_after_a_weekend_day_in_the_window():
    assert config.settings().floor("ted", DAYS["tue"]) == 30
    assert config.settings().floor("ted", DAYS["sun"]) == 30


def test_every_ted_floor_is_below_what_was_measured():
    """Floors must not fire on a healthy day. Measured weekday minimum was 60
    notices per publication day, so a two-weekday window yields at least 120."""
    settings = config.settings()
    assert settings.floor("ted", DAYS["wed"]) < 120
    assert settings.floor("ted", DAYS["tue"]) < 60


def test_placsp_floor_is_one_page():
    """Pages carry 405 to 500 entries. Fewer than one page means the chain
    broke, not that Spain went quiet."""
    settings = config.settings()
    assert settings.floor("es_placsp", DAYS["mon"]) == 400
    assert settings.floor("es_placsp_agg", DAYS["mon"]) == 50


def test_placsp_floors_do_not_vary_by_day():
    settings = config.settings()
    assert len({settings.floor("es_placsp", d) for d in DAYS.values()}) == 1


def test_unknown_source_has_no_floor_rather_than_a_guessed_one():
    """None means "not measured yet", which is honest. Zero would be a claim."""
    assert config.settings().floor("ro_seap") is None


def test_poland_has_a_measured_floor():
    """Set below the weekend figure: Poland, unlike TED, publishes at weekends,
    and 139 records came back across a measured Saturday and Sunday."""
    settings = config.settings()
    assert settings.floor("pl_ezam", DAYS["mon"]) == 50
    assert len({settings.floor("pl_ezam", d) for d in DAYS.values()}) == 1


def test_zero_is_a_real_floor_not_a_missing_one():
    assert config.settings().floor("ted", DAYS["mon"]) == 0
    assert config.settings().floor("ted", DAYS["mon"]) is not None


def test_a_single_number_sets_every_day(monkeypatch):
    monkeypatch.setenv("DGATE_FLOOR_TED", "17")
    config.reset_cache()
    settings = config.settings()
    assert {settings.floor("ted", d) for d in DAYS.values()} == {17}


def test_seven_numbers_set_monday_through_sunday(monkeypatch):
    monkeypatch.setenv("DGATE_FLOOR_TED", "1,2,3,4,5,6,7")
    config.reset_cache()
    settings = config.settings()
    assert settings.floor("ted", DAYS["mon"]) == 1
    assert settings.floor("ted", DAYS["sun"]) == 7


def test_a_malformed_override_falls_back_to_the_measured_defaults(monkeypatch):
    """A typo in an env var must not silently disable the floor."""
    monkeypatch.setenv("DGATE_FLOOR_TED", "sixty, or so")
    config.reset_cache()
    assert config.settings().floor("ted", DAYS["wed"]) == 60


def test_a_wrong_length_override_falls_back_too(monkeypatch):
    monkeypatch.setenv("DGATE_FLOOR_TED", "10,20,30")
    config.reset_cache()
    assert config.settings().floor("ted", DAYS["wed"]) == 60
