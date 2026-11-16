"""WP-172: a value computed in the background with a connection of its own (`stats.warm`; the list pages through
`cache_list(warm_next=True)` are tested in tests/integration/test_wp172.py), and the twin gmina names checked against TERYT
(`org_repair._PL_TWIN_GMINAS`, docs/sources/pl_teryt_gminas.csv)."""

from __future__ import annotations

import csv
import threading
from contextlib import contextmanager
from pathlib import Path

import pytest

from dgate import config, stats


@pytest.fixture
def cache_on(monkeypatch):
    monkeypatch.setenv("DGATE_LIST_CACHE_SECONDS", "60")
    config.reset_cache()
    stats.reset_cache()

    @contextmanager
    def own_connection():
        yield "own"
    monkeypatch.setattr(stats, "_connection", own_connection)
    yield
    monkeypatch.setenv("DGATE_LIST_CACHE_SECONDS", "0")
    config.reset_cache()
    stats.reset_cache()


def _settle():
    for t in threading.enumerate():
        if t.name == "warm":
            t.join(5)


def test_warm_computes_once_in_the_background_and_a_request_meanwhile_waits_for_it(cache_on):
    go, calls = threading.Event(), []

    def compute(c):
        calls.append(c)
        go.wait(5)
        return {"v": 1}

    assert stats.warm(("k",), compute, 60) is True
    assert stats.warm(("k",), compute, 60) is False                   # already being computed
    waiter = threading.Thread(target=lambda: calls.append(stats.cached(("k",), lambda: {"v": 2}, 60)))
    waiter.start()
    go.set()
    waiter.join(5)
    _settle()
    assert calls == ["own", {"v": 1}]                                # its own connection; the request took its value
    assert stats.warm(("k",), compute, 60) is False                   # kept: nothing to do
    assert stats._get(("k",)) == {"v": 1}


def test_a_failed_warm_up_keeps_nothing_and_frees_its_place(cache_on):
    def boom(c):
        raise RuntimeError("down")
    assert stats.warm(("x",), boom, 60) is True
    _settle()
    assert stats._get(("x",)) is stats._ABSENT and ("x",) not in stats._refreshing
    assert stats.warm(("x",), lambda c: 1, 60) is True               # the gate was given back
    _settle()


# ------------------------------------------------------------------------------------------- 3. twin gmina names

def test_the_twin_gmina_names_are_the_teryt_twins_of_the_derived_list():
    from dgate.ops.org_repair import _PL_TWIN_GMINAS, ambiguous_name, twin_name

    rows = list(csv.DictReader((Path(__file__).parents[3] / "docs" / "sources" / "pl_teryt_gminas.csv").open(encoding="utf-8")))
    assert len(rows) == 52
    twins = {r["name"] for r in rows if r["verdict"] == "twin"}
    assert len(twins) == 40 and all(int(r["gminas_in_terc"]) >= 2 for r in rows if r["name"] in twins)
    assert _PL_TWIN_GMINAS == twins
    assert {"gmina lagow", "gmina krasne", "gmina stezyca"} <= _PL_TWIN_GMINAS          # the pairs met before
    assert twin_name("PL", "gmina osiek") and ambiguous_name("PL", "Gmina Dabrowa")
    for one in (r["name"] for r in rows if r["verdict"] == "one"):                     # one gmina: a number decides
        assert not twin_name("PL", one)
    assert not twin_name("CZ", "gmina osiek")
