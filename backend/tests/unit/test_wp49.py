"""WP-49: why a call has no budget, which tender sources read no value, and the bound on database connections."""

from __future__ import annotations

import threading
from contextlib import ExitStack, contextmanager

import pytest

from dgate import db, normalise
from dgate.funding import budget_note
from dgate.normalise import VALUE_NOT_READ_SOURCES

# ------------------------------------------------------------ the reason for an empty budget

def test_the_portal_stating_zero_is_said_to_be_zero_and_not_a_budget():
    """HORIZON-EIC-2026-ACCELERATOR-01: budgetYearMap {"2026": "0"}."""
    note = budget_note("HORIZON", {"budget_line": {"action": "HORIZON-EIC-2026-ACCELERATOR-01",
                                                   "budgetYearMap": {"2026": "0"}, "expectedGrants": 0}})
    assert note["reason"] == "portal_zero"
    assert "states 0" in note["short"] and "work programme" in note["text"]
    assert "perProject" not in note


def test_an_empty_budget_map_is_not_the_same_as_a_zero():
    """EDF-EDIP-P-2026-FNLC-CSA-PREP: the portal's map is empty."""
    note = budget_note("EDF", {"budget_line": {"action": "EDF-EDIP-P-2026-FNLC-CSA-PREP", "budgetYearMap": {}}})
    assert note["reason"] == "portal_empty"
    assert "0" not in note["short"]


def test_a_topic_the_budget_table_does_not_list_says_so():
    assert budget_note("HORIZON", {})["reason"] == "portal_no_line"
    assert budget_note("HORIZON", {"budget_line": None})["reason"] == "portal_no_line"


def test_the_work_programme_is_pointed_at_as_linked_only_when_it_is_linked():
    docs = [{"label": "Work Programme 2026", "url": "https://example.org/wp.pdf"}]
    zero = {"budgetYearMap": {"2026": "0"}}
    assert "linked under Documents" in budget_note("HORIZON", {"budget_line": zero, "documents": docs})["text"]
    assert "linked under Documents" not in budget_note("HORIZON", {"budget_line": zero})["text"]


def test_vinnova_has_no_budget_field_and_no_figure_is_invented():
    note = budget_note("SE-VINNOVA", {"web_text_sv": ["Steg 1: 500 000 kronor"]})
    assert note["reason"] == "source_no_field" and "perProject" not in note
    assert not any(ch.isdigit() for ch in note["short"] + note["text"])      # no number of ours


def test_the_french_per_project_ceiling_is_given_as_that_and_only_where_stored():
    with_ceiling = budget_note("FR-AID", {"max_aid_eur_per_project": 300000})
    assert with_ceiling["perProject"] == {"amount": 300000.0, "currency": "EUR"}
    assert "total" in with_ceiling["short"]                 # it says there is no total
    assert "perProject" not in budget_note("FR-AID", {})


def test_any_other_national_source_says_it_states_none():
    assert budget_note("PL-NCBR", {})["reason"] == "source_none"


# ------------------------------------------------------------ the sources that read no value

def test_the_two_connectors_that_never_read_a_value_are_named_and_do_leave_it_empty():
    assert VALUE_NOT_READ_SOURCES == {"pl_ezam", "nl_tenderned"}
    ez = normalise.from_ezamowienia({"bzpNumber": "2026/BZP 1", "organizationName": "Buyer", "orderObject": "Thing",
                                     "noticeType": "ContractNotice", "publicationDate": "2026-10-01T00:00:00Z"})
    nl = normalise.from_tenderned({"publicatieId": 1, "opdrachtgeverNaam": "Buyer", "aanbestedingNaam": "Thing",
                                   "typePublicatie": {"code": "AAO"}, "publicatieDatum": "2026-10-01"})
    assert ez.value_amount is None and nl.value_amount is None
    # a source that reads values is not in the set
    assert "ted" not in VALUE_NOT_READ_SOURCES and "fr_boamp" not in VALUE_NOT_READ_SOURCES


# ------------------------------------------------------------ the bound on connections

class _Fake:
    closed = False


@pytest.fixture()
def fake_connect(monkeypatch):
    opened: list[_Fake] = []

    @contextmanager
    def connect(dsn):
        c = _Fake()
        opened.append(c)
        try:
            yield c
        finally:
            c.closed = True

    monkeypatch.setattr(db, "connect", connect)
    return opened


def test_a_request_over_the_bound_waits_and_then_is_refused_not_served(fake_connect):
    dsn = "bound-refuses"
    with ExitStack() as stack:
        stack.enter_context(db.bounded_connect(dsn, 2, 0.05))
        stack.enter_context(db.bounded_connect(dsn, 2, 0.05))
        with pytest.raises(db.PoolBusy):
            with db.bounded_connect(dsn, 2, 0.05):
                pytest.fail("a third connection was opened over the bound of two")
        assert len(fake_connect) == 2                           # the refused one never connected
    with db.bounded_connect(dsn, 2, 0.05) as conn:               # both released: there is room again
        assert conn.closed is False
    assert all(c.closed for c in fake_connect)


def test_a_slot_is_given_back_when_the_work_fails(fake_connect):
    dsn = "bound-releases"
    for _ in range(5):                                           # more failures than the bound of one
        with pytest.raises(RuntimeError):
            with db.bounded_connect(dsn, 1, 0.05):
                raise RuntimeError("the query failed")
    with db.bounded_connect(dsn, 1, 0.05):
        pass


def test_a_waiting_request_gets_the_slot_the_moment_it_is_freed(fake_connect):
    dsn = "bound-queue"
    holder = db.bounded_connect(dsn, 1, 1)
    holder.__enter__()
    got: list[bool] = []

    def waiter():
        with db.bounded_connect(dsn, 1, 2):
            got.append(True)

    t = threading.Thread(target=waiter)
    t.start()
    t.join(0.1)
    assert t.is_alive() and not got                              # queued, not refused
    holder.__exit__(None, None, None)
    t.join(2)
    assert got == [True]


def test_the_bound_is_per_dsn_so_the_accounts_role_is_counted_apart(fake_connect):
    with db.bounded_connect("role-a", 1, 0.05):
        with db.bounded_connect("role-b", 1, 0.05):
            pass
