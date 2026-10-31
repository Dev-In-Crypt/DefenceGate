"""WP-162, the "Who to sell to" report, without a database: the mosaic rule and its size rule, the requirement items v1
(primary-source quotes only, a consultant for export, US rules and clearances), the 90-day templates, and the form."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from dgate import sell_report as sr
from dgate.readiness import api as readiness
from dgate.readiness.seed import load_file


# ---------------------------------------------------------------- the mosaic rule
def test_a_small_company_is_named_only_when_every_cell_it_is_in_holds_five():
    rows = [{"org": i, "country": "ES", "cn": f"taller {i}", "prefixes": ["343"]} for i in range(5)]
    rows += [{"org": 10, "country": "PL", "cn": "warsztat", "prefixes": ["343"]},                 # alone in PL x 343
             {"org": 11, "country": "ES", "cn": "taller mixto", "prefixes": ["343", "4447"]},      # ES x 4447 alone
             {"org": 12, "country": "DE", "cn": "rheinmetall landsysteme", "prefixes": ["343"]}]   # large, alone
    may = sr.mosaic(rows)
    assert all(may[i] for i in range(5))           # ES x 343 holds 6 companies (0-4 and 11)
    assert may[10] is False                        # its cell has one company: counted, not named
    assert may[11] is False                        # one of its cells has fewer than five
    assert may[12] is True                         # a large prime is always named
    assert sr.mosaic(rows, minimum=7)[0] is False


def test_the_size_rule_is_the_sipri_list_only():
    assert sr.is_large("bae systems plc") and sr.is_large("rheinmetall landsysteme") and sr.is_large("indra sistemas")
    # on the curated prime list but not under SIPRI's source: may be small or medium, so the mosaic rule applies
    assert not sr.is_large("uro vehiculos especiales")
    assert not sr.is_large("talleres norte") and not sr.is_large(None)


# ---------------------------------------------------------------- the form
def test_the_form_is_validated_and_takes_nothing_else():
    ok = sr.ReportIn(country="ES", cpv=["34300000-0", "34300000"], name="  Acme \n Parts ", held=["ISO9001"])
    assert ok.cpv == ["34300000"] and ok.name == "Acme Parts"
    for bad in ({"country": "ES", "cpv": ["3430"]}, {"country": "ES", "email": "a@b.c"}, {"country": "ES", "held": ["X"]},
                {"country": "ES", "nace": "<script>"}, {"org": "../etc"}, {"country": "ES", "cpv": ["34300000"] * 16}):
        with pytest.raises(ValidationError):
            sr.ReportIn(**bad)


# ---------------------------------------------------------------- section 6
@pytest.fixture()
def content(monkeypatch):
    c = load_file()
    monkeypatch.setattr(readiness, "content", lambda conn: c)
    return c


def test_the_spanish_items_quote_primary_sources_and_decide_nothing_a_consultant_must(content):
    q = sr.qualify(None, {"country": "ES", "held": ["ISO9001", "RID"], "classified": "unsure", "exports": "outside_eu",
                          "usComponents": "yes"})
    items = {i["key"]: i for i in q["items"]}
    assert {"RID", "PECAL", "HSES", "HSEM", "AQAP2110", "AQAP2310", "NCAGE", "ISO9001", "EN9100", "EXPORT", "ITAR-EAR"} <= set(items)
    assert items["RID"]["status"] == "have" and items["ISO9001"]["status"] == "have"
    assert items["PECAL"]["status"] == "missing" and items["NCAGE"]["status"] == "missing"
    for k in ("HSES", "HSEM", "EXPORT", "ITAR-EAR"):
        assert items[k]["status"] == "consultant", k
    for i in q["items"]:
        assert i["quotes"] and all(x["text"] and x["url"].startswith("https://") for x in i["quotes"]), i["key"]
    assert "subcontratistas" in items["HSEM"]["quotes"][0]["text"] and items["HSEM"]["applies"] == "both"
    # cost and time only where the requirement's own source is verified: NCAGE (free, NSPA); never AQAP's vendor range
    assert items["NCAGE"]["cost"] and items["NCAGE"]["time"]
    assert items["AQAP2110"]["cost"] is None and items["AQAP2110"]["time"] is None
    assert {v["programme"] for v in q["verdicts"]} >= {"ES-MOD", "NATO-SUPPLY"}
    assert "CLEARANCE" not in {n["key"] for n in q["notSourced"]} and "NSPA" in {n["key"] for n in q["notSourced"]}


def test_outside_spain_the_spanish_route_is_left_out(content):
    q = sr.qualify(None, {"country": "DE", "held": []})
    keys = {i["key"] for i in q["items"]}
    assert not keys & {"RID", "PECAL", "HSES", "HSEM"} and {"AQAP2110", "EXPORT", "ITAR-EAR"} <= keys
    assert "CLEARANCE" in {n["key"] for n in q["notSourced"]}
    assert "ES-MOD" not in {v["programme"] for v in q["verdicts"]}


# ---------------------------------------------------------------- section 7
def _rep(**over):
    rep = {"profile": {"country": "ES", "exports": "none", "usComponents": "no", "classified": "no"},
           "market": {"available": True, "total": {"procurements": 3},
                      "buyers": [{"rows": [{"name": "JAE MALE"}, {"name": "Intendencia"}]}],
                      "winners": {"rows": [{"name": "Talleres Norte SL"}]}},
           "open": {"tenders": {"rows": []}, "calls": {"rows": []}},
           "qualify": {"items": [{"key": "RID", "status": "missing"}, {"key": "ISO9001", "status": "have"},
                                 {"key": "AQAP2110", "status": "missing"}]},
           "ending": None}
    rep.update(over)
    return rep


def test_the_plan_is_the_fixed_templates_its_findings_trigger():
    got = sr.steps(_rep())
    keys = [s["key"] for s in got]
    assert keys == ["buyers", "rid", "winners", "aqap", "review"]
    assert "JAE MALE and Intendencia" in got[0]["text"] and "Talleres Norte SL" in got[2]["text"]
    templates = {k: t for k, _, t in sr.STEPS}
    for s in got:                                   # every line is a template of STEPS, slots filled from the report only
        head = templates[s["key"]].split("{")[0]
        assert s["text"].startswith(head)


def test_an_empty_market_asks_for_other_codes_and_never_names_anyone():
    got = sr.steps(_rep(market={"available": False, "reason": "no_codes"}, qualify={"items": []},
                        profile={"country": "PL", "usComponents": "unsure", "exports": "unsure"}))
    assert [s["key"] for s in got] == ["codes", "export", "us", "review"]
    broad = sr.steps(_rep(market={"available": False, "reason": "too_broad"}))
    assert broad[0]["key"] == "broad"


def test_the_section_5_seam_is_empty_until_wp160_is_wired():
    assert sr.ending_soon(None, ["34300000"], ["ES"], None) is None
