"""TenderNed: lifecycle of prior-information notices, and the legal basis.

Closes findings F13 and, for the Netherlands, part of F14's legal-basis gap (301
Dutch defence rows had none). Measured on the 22,092 publications landed up to
12 October 2026: seven publication types and six `formType`s are all there are,
and `juridischKaderCode` takes four values (NAW 19,175, ARW2012 2,325,
AND2012 429, DEF 162).

Before, VAK (prior information) and MAC (market consultation) were `open`, so 62
of the 107 effective-open Dutch rows were not tenders, and a rectification of an
award notice was `open` too.
"""

from __future__ import annotations

import pytest

from dgate.normalise import from_tenderned


def _record(kind: str, form: str = "EF16", form_text: str | None = None, *,
            form_type: str | None = None, framework: str | None = "NAW",
            european: bool | None = True) -> dict:
    texts = {
        "EF16": "Aankondiging van een opdracht - algemene richtlijn, standaardregeling",
        "EF17": "Aankondiging van een opdracht - sectorale richtlijn, standaardregeling",
        "EF19": "Concessieaankondiging - concessierichtlijn, standaardregeling",
        "EF18": "Aankondiging van een opdracht - defensierichtlijn, standaardregeling",
        "EFE3": "Vrijwillige aankondiging van een opdracht",
    }
    detail: dict = {}
    if form_type:
        detail["formType"] = form_type
    if framework:
        detail["juridischKaderCode"] = {"code": framework}
    if european is not None:
        detail["nationaalOfEuropeesCode"] = {"code": "EU" if european else "NL"}
    return {"publicatieId": "1", "typePublicatie": {"code": kind},
            "publicatiecode": {"code": form, "omschrijving": form_text or texts.get(form, "")},
            "detail": detail}


# ----------------------------------------------------------- lifecycle

@pytest.mark.parametrize("kind,status", [
    ("AAO", "open"),
    ("VAK", "forthcoming"),         # prior information: not a tender
    ("MAC", "forthcoming"),         # a market consultation: no procedure yet
    ("AGO", "awarded"),
    ("AAW", "awarded"),
    ("VBE", "cancelled"),
    ("XYZ", "unknown"),
])
def test_the_publication_type_decides_the_lifecycle(kind, status):
    assert from_tenderned(_record(kind)).status == status


@pytest.mark.parametrize("form_type,status", [
    ("competition", "open"),        # a corrected contract notice
    ("planning", "forthcoming"),    # a corrected prior-information notice
    ("consultation", "forthcoming"),
    ("result", "awarded"),          # a corrected award: not an open tender
    ("dir-awa-pre", "awarded"),
    ("cont-modif", "awarded"),
])
def test_a_rectification_takes_the_lifecycle_of_what_it_corrects(form_type, status):
    assert from_tenderned(_record("REC", form_type=form_type)).status == status


def test_a_rectification_whose_form_type_is_unknown_is_never_open():
    """No detail page, or a formType added later: `unknown`, which is never served
    as open, rather than the `open` it had before."""
    assert from_tenderned(_record("REC")).status == "unknown"
    assert from_tenderned(_record("REC", form_type="brand-new")).status == "unknown"


def test_a_prior_information_notice_used_as_a_call_for_competition_is_forthcoming():
    """EF10-EF14 are prior-information notices that open a procedure, formType
    `competition`. They are announced, not yet answerable: 100 of them in 2026."""
    assert from_tenderned(_record("VAK", "EF10", form_type="competition")).status == "forthcoming"


# --------------------------------------------------------- legal basis

@pytest.mark.parametrize("record,celex", [
    (_record("AAO", "EF16"), "32014L0024"),                 # general directive
    (_record("AAO", "EF17"), "32014L0025"),                 # utilities
    (_record("AAO", "EF19"), "32014L0023"),                 # concessions
    (_record("AAO", "EF18", framework="DEF"), "32009L0081"),    # defence, framework DEF
    (_record("AAO", "EF18", framework="NAW"), "32009L0081"),    # defence, from the form
    (_record("AAO", "EFE3", framework="DEF", european=False), "32009L0081"),
])
def test_a_directive_is_named_when_form_and_framework_agree(record, celex):
    assert from_tenderned(record).legal_basis == celex


@pytest.mark.parametrize("record", [
    _record("AAO", "EF16", european=False),                 # national-only publication
    _record("AAO", "EF16", framework="ARW2012"),            # the works regulation
    _record("AAO", "EF16", framework="AND2012"),            # "Anders"
    _record("AAO", "EFE3"),                                 # a voluntary form names no directive
    _record("AAO", "EF16", framework=None),                 # no detail page
    _record("AAO", "EF16", framework=None, european=None),
])
def test_the_legal_basis_stays_empty_where_the_source_does_not_say(record):
    """NAW alone is the Aanbestedingswet 2012: three directives and the national
    regime. ARW2012 and AND2012 name none. A guess is a wrong filter."""
    assert from_tenderned(record).legal_basis is None


def test_the_european_flag_of_the_list_row_counts_when_the_detail_lacks_its_own():
    record = _record("AAO", "EF16", framework="NAW", european=None)
    assert from_tenderned(record).legal_basis is None        # nothing says it is European
    record["europees"] = True
    assert from_tenderned(record).legal_basis == "32014L0024"
    record["europees"] = False
    assert from_tenderned(record).legal_basis is None
