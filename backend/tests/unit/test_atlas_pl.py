"""The Polish historical backfill: Atlas Przetargow.

Every expectation here was measured against the real 2024 file (669,983 rows),
not against the dataset's README, which documents 16 of its 43 columns and gets
some of those wrong -- `order_type` is documented but entirely null, and
`is_duplicate` is False on every row.
"""

from __future__ import annotations

from datetime import date

import pytest

from dgate.classify import classify
from dgate.normalise import from_atlas_pl, strip_personal_data
from dgate.sources import atlas_pl


def row(**over):
    base = {
        "id": "2024/BZP 00000043",
        "source": "bzp",
        "notice_type": "ContractNotice",
        "title": "Dostawa umundurowania Marynarki Wojennej",
        "buyer": "Komenda Portu Wojennego Gdynia",
        "buyer_nip": "5860103108",
        "nip_normalized": "5860103108",
        "city": "Gdynia",
        "province": "PL63",
        "cpv_code": "35811300, 18332000",
        "date": date(2024, 1, 2),
        "submitting_offers_date": None,
        "estimated_value": 242241.4,
        "currency": "PLN",
        "notice_url": "https://ezamowienia.gov.pl/mo-client-board/bzp/notice-details/id/x",
        "notice_number": "2024/BZP 00000043/01",
        "bzp_number": "2024/BZP 00000043",
        "ted_number": None,
        "organization_country": "PL",
        "contractor_name": "[Osoba fizyczna]",
        "contractor_national_id": "a" * 64,
    }
    base.update(over)
    return base


# ------------------------------------------------------------- personal data

def test_contractor_identity_never_reaches_the_payload():
    """A stable hash still singles out one person across every contract.

    The publisher pseudonymises natural persons already, but pseudonymous is
    not anonymous, which is the same reasoning that put e-Zamowienia's userId
    on this list.
    """
    clean = strip_personal_data(row())
    assert "contractor_name" not in clean
    assert "contractor_national_id" not in clean


def test_stripping_keeps_the_buyer():
    """Buyers are public bodies by law; removing them would empty the product."""
    clean = strip_personal_data(row())
    assert clean["buyer"] == "Komenda Portu Wojennego Gdynia"


# ------------------------------------------------------------------ mapping

def test_a_real_defence_row_maps_end_to_end():
    opp = from_atlas_pl(strip_personal_data(row()))
    assert opp.source_code == "pl_atlas"
    assert opp.native_id == "2024/BZP 00000043"
    assert opp.buyer_name_raw == "Komenda Portu Wojennego Gdynia"
    assert opp.cpv_codes == ["35811300", "18332000"]
    assert opp.published_at == date(2024, 1, 2)
    assert opp.country == "PL"


def test_a_row_without_an_id_is_refused():
    with pytest.raises(ValueError, match="no id"):
        from_atlas_pl(row(id=None))


def test_legal_basis_is_never_invented():
    """The dataset carries no legal basis, and guessing sets the strongest
    signal we have on the flimsiest evidence we have."""
    opp = from_atlas_pl(strip_personal_data(row()))
    assert opp.legal_basis is None


def test_award_notices_are_not_left_looking_open():
    assert from_atlas_pl(row(notice_type="TenderResultNotice")).status == "awarded"
    assert from_atlas_pl(row(notice_type="ContractPerformingNotice")).status == "awarded"
    assert from_atlas_pl(row(notice_type="can-standard")).status == "awarded"


def test_an_unknown_notice_type_stays_open():
    """Wrongly open is visible and gets corrected; wrongly closed never does."""
    assert from_atlas_pl(row(notice_type="SomethingNew")).status == "open"


# -------------------------------------------------------------------- value

@pytest.mark.parametrize("currency", ["net", "bru", "Kry", "", None, "PLNX"])
def test_a_value_with_an_unusable_currency_is_dropped(currency):
    """181,062 rows have no currency and a tail carry junk. A number whose
    currency is 'net' is a parsing accident, and showing it to someone deciding
    whether to bid would be worse than showing nothing."""
    opp = from_atlas_pl(row(currency=currency))
    assert opp.value_amount is None
    assert opp.value_currency is None


def test_a_well_formed_value_survives():
    opp = from_atlas_pl(row(estimated_value=242241.4, currency="PLN"))
    assert opp.value_amount == pytest.approx(242241.4)
    assert opp.value_currency == "PLN"


def test_a_nonpositive_value_is_dropped():
    assert from_atlas_pl(row(estimated_value=0)).value_amount is None
    assert from_atlas_pl(row(estimated_value=-5)).value_amount is None


# --------------------------------------------------------------- classifying

def test_military_cpv_alone_qualifies():
    opp = from_atlas_pl(strip_personal_data(row()))
    sig = classify(legal_basis=opp.legal_basis, cpv_codes=opp.cpv_codes,
                   buyer_is_defence=False)
    assert sig.is_defence


def test_safety_clothing_bought_by_a_waste_company_does_not_qualify():
    """Measured: 4,218 rows carry a CPV in division 35, but only 756 are
    military. The rest are civil-security codes like this one, and letting them
    through would bury the defence slice in workwear."""
    opp = from_atlas_pl(row(
        buyer="Zaklad Zagospodarowania Odpadow", cpv_code="35113470, 18141000"))
    sig = classify(legal_basis=opp.legal_basis, cpv_codes=opp.cpv_codes,
                   buyer_is_defence=False)
    assert not sig.is_defence


# -------------------------------------------------------------------- source

def test_the_attribution_names_the_dataset_and_the_licence():
    """CC BY 4.0 makes attribution a licence condition, not a courtesy."""
    assert "Atlas Przetargow" in atlas_pl.ATTRIBUTION
    assert "CC BY 4.0" in atlas_pl.ATTRIBUTION
    assert atlas_pl.DOI in atlas_pl.ATTRIBUTION


def test_only_the_years_the_release_actually_contains_are_offered():
    assert sorted(atlas_pl.YEAR_FILES) == [2024, 2025]
    assert all(f.endswith(".parquet") for f in atlas_pl.YEAR_FILES.values())


def test_every_mapped_column_is_requested_from_the_file():
    """Parquet is columnar, so a column not asked for is silently absent rather
    than missing. Anything the mapper reads has to be in COLUMNS."""
    for name in ("id", "title", "buyer", "cpv_code", "date", "notice_type",
                 "estimated_value", "currency", "submitting_offers_date",
                 "notice_url", "organization_country"):
        assert name in atlas_pl.COLUMNS


def test_a_changed_schema_is_refused_rather_than_half_mapped(tmp_path):
    import pyarrow as pa
    import pyarrow.parquet as pq

    path = tmp_path / "truncated.parquet"
    pq.write_table(pa.table({"id": ["x"], "title": ["y"]}), path)
    with pytest.raises(ValueError, match="missing expected columns"):
        list(atlas_pl.read_rows(path))
