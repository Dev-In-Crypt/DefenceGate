"""WP-85: the supplier map and the demand answer read one definition of the award set (`dgate/award_set.py`)."""

from datetime import date

from dgate import award_set, demand, suppliers


def test_both_modules_build_on_the_one_definition_and_keep_no_copy_of_it():
    assert award_set.NOTICES in demand.MATCH and award_set.CPV_MATCH in demand.MATCH
    assert award_set.scope() in demand.query()
    assert demand.KEY is award_set.KEY and demand.prefix is award_set.prefix and demand.YEARS == award_set.YEARS
    assert suppliers.FROM is award_set.FROM and suppliers.scope is award_set.scope
    assert not {"SCOPE", "NOT_TWIN", "SINCE", "AWARD_OK"} & set(vars(suppliers)) | ({"AWARD_OK", "PLACSP_IDS"} & set(vars(demand)))


def test_the_window_is_three_years_back_from_today():
    # always 1,096 days (round(365.25 * 3)), the demand answer's rule since WP-66
    assert award_set.since(date(2026, 10, 22)) == date(2023, 10, 22)
    assert award_set.since(date(2027, 3, 1)) == date(2024, 2, 29)


def test_the_twin_test_reads_the_preferred_row_under_its_own_aliases():
    # the preferred twin must be in the set itself: the same condition, over its own aliases
    assert "ko.is_defence AND NOT ko.suppressed" in award_set.NOT_TWIN and "korg.individual_reason" in award_set.NOT_TWIN
    assert " o." not in award_set.NOT_TWIN.split("WHERE", 1)[1]
