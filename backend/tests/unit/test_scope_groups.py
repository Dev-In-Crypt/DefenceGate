"""WP-8, owner decision of 14 October 2026: two groups of defence-qualified notice leave
`core` for `supply` (never deleted), and Forsvarsbygg is a defence buyer.

  A. the 2009/81/EC legal basis is the only signal and the buyer is a civil body
     -> `directive_civil_buyer`
  B. a military CPV is the only signal and the buyer is a police, prison, border,
     customs or tax body (class `security`) -> `security_buyer_cpv`
"""

from __future__ import annotations

import re

import pytest

from dgate import api
from dgate import buyer_vocab as bv
from dgate import classify as c
from dgate.migrate import MIGRATIONS_DIR
from dgate.tenders import CORE, _qualified_by

DIRECTIVE = "32009L0081"


def verdict(name, country, cpv, *, legal=None, listed=False, linked=False):
    cls = bv.effective_buyer_class(name, country, listed)
    return c.classify(legal_basis=legal, cpv_codes=cpv, buyer_is_defence=listed,
                      buyer_class=cls, linked_defence=linked)


# --------------------------------------------------------------- A: the directive alone

@pytest.mark.parametrize("name, country", [
    ("Landesbetrieb Bau und Liegenschaften", "DE"),          # a state building office
    ("Stadt Nürnberg", "DE"),
    ("Swedavia AB", "SE"),
    ("Szpital Wojewódzki w Zamościu", "PL"),
])
def test_the_directive_alone_from_a_civil_buyer_is_filed_outside_core(name, country):
    sig = verdict(name, country, ["45000000"], legal=DIRECTIVE)
    assert sig.buyer_class not in ("defence", "security", None)
    assert sig.is_defence and sig.legal_basis and not sig.military_cpv
    assert sig.scope_group == c.GROUP_CIVIL_DIRECTIVE
    assert not sig.in_core
    assert sig.confidence < 0.5


def test_the_directive_still_qualifies_a_notice_for_core_when_anything_else_agrees():
    unknown = "Landesbetrieb Bau und Liegenschaften"
    # a military CPV agrees
    sig = verdict(unknown, "DE", ["35400000"], legal=DIRECTIVE)
    assert sig.in_core and sig.scope_group is None
    # the buyer is on the defence list
    sig = verdict(unknown, "DE", ["45000000"], legal=DIRECTIVE, listed=True)
    assert sig.in_core and sig.scope_group is None
    # the notice is the twin of a national defence notice
    sig = verdict(unknown, "DE", ["45000000"], legal=DIRECTIVE, linked=True)
    assert sig.in_core and sig.scope_group is None
    # the buyer is a defence or a security body
    for name in ("Bundesamt für Ausrüstung, Informationstechnik und Nutzung der Bundeswehr",
                 "Polizeiverwaltungsamt Logistikzentrum"):
        sig = verdict(name, "DE", ["45000000"], legal=DIRECTIVE)
        assert sig.in_core and sig.scope_group is None, name


def test_a_buyer_nobody_has_classified_yet_is_never_demoted():
    sig = c.classify(legal_basis=DIRECTIVE, cpv_codes=["45000000"], buyer_is_defence=False)
    assert sig.buyer_class is None and sig.in_core and sig.scope_group is None


# ---------------------------------------------------------- B: a military CPV, a security body

@pytest.mark.parametrize("name, country, cpv", [
    ("Komenda Główna Policji", "PL", ["35321200"]),                          # 1037
    ("Izba Administracji Skarbowej w Gdańsku", "PL", ["35321100", "35330000"]),   # 618
    ("Zakład Karny w Opolu", "PL", ["35820000"]),
])
def test_a_military_cpv_alone_from_a_security_body_is_filed_outside_core(name, country, cpv):
    sig = verdict(name, country, cpv)
    assert bv.buyer_class_of(name, country) == "security"
    assert sig.is_defence and sig.military_cpv and not sig.dual_use
    assert sig.scope_group == c.GROUP_SECURITY_CPV
    assert not sig.in_core


def test_a_security_body_keeps_core_when_the_directive_or_the_list_agrees():
    name = "Komenda Główna Policji"
    assert verdict(name, "PL", ["35321200"], legal=DIRECTIVE).in_core
    sig = verdict(name, "PL", ["35321200"], listed=True)
    assert sig.in_core and sig.scope_group is None


def test_a_military_cpv_from_a_defence_body_or_a_civil_one_is_unchanged():
    assert verdict("Armasuisse", "CH", ["35400000"]).in_core
    # civil bodies were already demoted as dual-use; that is not the new group
    sig = verdict("Stadt Nürnberg", "DE", ["35810000"])
    assert sig.dual_use and sig.scope_group is None and not sig.in_core


# ------------------------------------------------- one definition, in Python and in SQL

def _strip(sql: str) -> str:
    return re.sub(r"\s+", " ", sql.replace("o.", "")).strip()


def test_the_api_and_the_tender_list_read_one_definition_of_core():
    assert api.CORE_SQL == c.CORE_SQL == CORE
    assert api.SCOPE_SQL["core"] == c.CORE_SQL
    assert api.SCOPE_SQL["supply"] == c.SUPPLY_SQL
    assert c.CIVIL_DIRECTIVE_SQL in c.SUPPLY_SQL and c.SECURITY_CPV_SQL in c.SUPPLY_SQL


def test_the_partial_index_of_migration_0045_has_the_predicate_the_queries_use():
    sql = (MIGRATIONS_DIR / "0045_core_scope_groups.sql").read_text(encoding="utf-8")
    sql = "\n".join(line for line in sql.splitlines() if not line.startswith("--"))
    predicate = _strip(sql[sql.index("WHERE is_defence AND") + len("WHERE is_defence AND"):])
    predicate = predicate.rstrip(";").strip()
    assert re.sub(r"[\s()]", "", predicate) == re.sub(r"[\s()]", "", _strip(c.CORE_SQL))


@pytest.mark.parametrize("legal", [False, True])
@pytest.mark.parametrize("military", [False, True])
@pytest.mark.parametrize("dual", [False, True])
@pytest.mark.parametrize("buyer", [False, True])
@pytest.mark.parametrize("linked", [False, True])
@pytest.mark.parametrize("cls", [None, "defence", "security", "other", "municipal"])
def test_row_scope_agrees_with_the_signals(legal, military, dual, buyer, linked, cls):
    row = {"sig_legal_basis": legal, "sig_cpv_military": military, "dual_use": dual,
           "sig_buyer": buyer, "sig_linked_defence": linked, "buyer_class": cls}
    expect = c.in_core(legal_basis=legal, military_cpv=military, dual_use=dual, buyer=buyer,
                       linked_defence=linked, buyer_class=cls)
    assert api.row_scope(row) == ("core" if expect else "supply")


# ------------------------------------------------------------------------ qualifiedBy

def test_qualified_by_names_the_group_and_not_the_signal_it_was_found_through():
    civil = {"sig_legal_basis": True, "sig_cpv_military": False, "legal_basis": DIRECTIVE,
             "buyer_class": "other"}
    assert _qualified_by(civil, ["45000000"]) == (["directive_civil_buyer"], [])
    police = {"sig_legal_basis": False, "sig_cpv_military": True, "buyer_class": "security"}
    assert _qualified_by(police, ["35321200", "33100000"]) == (["security_buyer_cpv"],
                                                               ["35321200"])


def test_qualified_by_is_unchanged_for_notices_that_stay_in_core():
    both = {"sig_legal_basis": True, "sig_cpv_military": True, "buyer_class": "other",
            "legal_basis": DIRECTIVE}
    assert _qualified_by(both, ["35400000"]) == (["legal_basis", "military_cpv"], ["35400000"])
    listed = {"sig_legal_basis": True, "sig_cpv_military": False, "sig_buyer": True,
              "buyer_class": "other", "legal_basis": DIRECTIVE}
    assert _qualified_by(listed, ["45000000"]) == (["legal_basis", "buyer"], [])


# ----------------------------------------------------------------------------- Forsvarsbygg

@pytest.mark.parametrize("name", [
    "Forsvarsbygg", "FORSVARSBYGG", "Forsvarsbygg - the Norwegian Defence Estates Agency",
    "Forsvarsbygg Utvikling Øst", "Forsvarsbygg Anskaffelser",
])
def test_forsvarsbygg_is_a_defence_buyer(name):
    body = bv.defence_body(name, "NO")
    assert body.label == "defence_estates_agency" and body.confidence >= 0.80, name
    assert bv.buyer_class_of(name, "NO") == "defence"


def test_forsvarsbygg_qualifies_into_supply_and_never_into_core_on_its_own():
    sig = verdict("Forsvarsbygg", "NO", ["45000000"], listed=True)
    assert sig.is_defence and sig.buyer and not sig.in_core
    assert api.row_scope({"sig_buyer": True, "buyer_class": "defence"}) == "supply"


def test_the_other_estate_agencies_stay_off_the_list():
    for name, country in (("Agencja Mienia Wojskowego", "PL"),
                          ("Defence Infrastructure Organisation", "GB"),
                          ("Fortifikationsverket", "SE"),
                          ("Bundesanstalt für Immobilienaufgaben - Bundeswehr", "DE")):
        assert bv.defence_body(name, country).label is None, name
