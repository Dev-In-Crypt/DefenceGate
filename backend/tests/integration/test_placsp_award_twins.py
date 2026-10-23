"""WP-61 against a real Postgres: an award that both TED and PLACSP publish is counted once on the supplier map,
the nightly PLACSP walk collects the award results with the archive loader's code path, and the public switch
(DGATE_PLACSP_AWARDS_PUBLIC) changes nothing while it is off.

The PLACSP notice is the made-up awarded defence entry of `test_placsp_awards`; the TED notice is a result
notice of the same procedure (the same eForms procedure identifier), its winners served by a stand-in for the
TED search API. Every name and number is made up.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timezone

import pytest
from fastapi.testclient import TestClient

from dgate import api, award_set, awards, config, db, pipeline, suppliers, worker
from dgate.normalise import Opportunity
from dgate.rawstore import build_store
from dgate.sources import placsp

from .test_placsp_awards import (
    ALFA,
    BETA,
    HEAD,
    PERSON,
    Portal,
    archive,
    awarded,
    ingest,
    result,
    winner,
)
from .test_supplier_map import FakeTed, rec

pytestmark = pytest.mark.integration

PID = "8f0c3a52-1b7e-4c1d-9a55-3e2f6d7c8b90"


@pytest.fixture()
def env(conn, tmp_path, monkeypatch):
    monkeypatch.setenv("DGATE_RAW_BACKEND", "fs")
    monkeypatch.setenv("DGATE_RAW_DIR", str(tmp_path / "raw"))
    monkeypatch.delenv("DGATE_PLACSP_AWARDS_PUBLIC", raising=False)
    config.reset_cache()
    yield tmp_path
    config.reset_cache()


def public(monkeypatch, on: bool) -> None:
    if on:
        monkeypatch.setenv("DGATE_PLACSP_AWARDS_PUBLIC", "true")
    else:
        monkeypatch.delenv("DGATE_PLACSP_AWARDS_PUBLIC", raising=False)
    config.reset_cache()


def ted_result(conn, native_id: str, *, pid: str | None = PID, published: date = date(2026, 9, 25)) -> int:
    """A TED result notice of the core scope (Directive 2009/81/EC), of procedure `pid`."""
    opp = Opportunity(
        source_code="ted", native_id=native_id, buyer_name_raw="Ministerio de Defensa", title_original="Repuestos",
        title_en="Spare parts", country="ES", published_at=published, cpv_codes=["35400000"], status="awarded",
        is_defence=True, sig_legal_basis=True, sig_cpv=True, notice_subtype="29", procedure_identifier=pid,
        source_url=f"https://ted.example/{native_id}")
    src = db.source_id(conn, "ted")
    opp.buyer_org_id = db.resolve_organisation(conn, opp.buyer_name_raw, "ES", src_id=src)
    opp_id, _ = db.upsert_opportunity(conn, opp, f"hash-{native_id}", src)
    conn.commit()
    return opp_id


def load_ted(conn, records: list[dict]) -> None:
    awards.run_awards(client=FakeTed(records).client(), pause=0, sleep=lambda s: None)


def with_procedure(entry: str, pid: str = PID) -> str:
    """The PLACSP entry as one sent to TED: <cbc:UUID schemeName="TED"> under the folder status."""
    return entry.replace("<cac-place-ext:LocatedContractingParty>",
                         f'<cbc:UUID schemeName="TED">{pid}</cbc:UUID><cac-place-ext:LocatedContractingParty>', 1)


def load_placsp(conn, entry: str) -> None:
    ingest(archive(entry))
    # The core scope wants a defence buyer for a 2009/81 notice; the buyer list is not seeded in these tests.
    conn.execute("UPDATE opportunity SET buyer_class = 'defence' WHERE source_id = %s",
                 (db.source_id(conn, "es_placsp"),))
    conn.commit()


def everything(client) -> dict:
    """What the map serves: the list, the summary and every profile."""
    items = client.get("/v1/suppliers").json()["items"]
    return {"list": items, "summary": client.get("/v1/suppliers/summary").json(),
            "profiles": [client.get(f"/v1/suppliers/{i['slug']}").json() for i in items]}


TED_ALFA_NO_ID = ("Alfa Defensa Inventada, S.L.", "ESP", None)


def test_one_award_in_ted_and_placsp_counts_once_and_the_numbered_record_stands_for_it(conn, env, monkeypatch):
    ted_result(conn, "500001-2026")
    load_ted(conn, [rec("500001-2026", [TED_ALFA_NO_ID])])
    with TestClient(api.app) as client:
        before = everything(client)
        load_placsp(conn, with_procedure(awarded(result("1", ALFA))))
        # off: nothing changes, whatever PLACSP holds
        assert everything(client) == before
        assert before["list"][0]["awardCount"] == 1 and before["profiles"][0]["notices"][0]["source"] == "ted"

        public(monkeypatch, True)
        after = everything(client)
    twin = conn.execute("SELECT * FROM award_twin").fetchall()
    assert [(r["procedure_method"], r["winner_method"]) for r in twin] == [("procedure_id", "organisation")]
    [item] = after["list"]
    assert item["awardCount"] == 1 and (item["firstYear"], item["lastYear"]) == (2026, 2026)
    profile = after["profiles"][0]
    assert profile["noticeCount"] == 1 and [y["awards"] for y in profile["byYear"]] == [1]
    assert sum(c["awards"] for c in profile["byCpv"]) == 1 and [b["awards"] for b in profile["buyers"]] == [1]
    # the PLACSP row states the NIF and the TED one states none: PLACSP's stands for the award, TED's is its provenance
    [notice] = profile["notices"]
    assert notice["source"] == "es_placsp"
    assert notice["alsoPublished"] == [{"source": "ted", "noticeId": "500001-2026",
                                        "sourceUrl": "https://ted.example/500001-2026"}]
    assert profile["identifiers"] == ["B99999990"]
    s = after["summary"]
    assert (s["suppliers"], s["awards"], s["noticesWithSupplier"]) == (1, 1, 1)
    # WP-81: the PLACSP result's awarded amount without VAT (250,000) is the award's value, once
    stored = conn.execute("SELECT value_amount, value_currency FROM award WHERE value_amount IS NOT NULL").fetchall()
    assert [(float(r["value_amount"]), r["value_currency"]) for r in stored] == [(250000.0, "EUR")]
    assert notice["valueAmount"] == 250000.0 and notice["valueCurrency"] == "EUR"
    assert profile["values"] == {"byCurrency": [{"currency": "EUR", "amount": 250000.0, "count": 1, "lotEstimates": 0}],
                                 "of": 1, "withoutValue": 0, "shared": 0, "suspect": 0}
    assert before["profiles"][0]["values"]["byCurrency"] == []     # off: the TED notice states none, PLACSP is not read


def test_the_ted_record_stands_for_the_award_when_it_states_a_number_too(conn, env, monkeypatch):
    ted_result(conn, "500002-2026")
    load_ted(conn, [rec("500002-2026", [("Alfa Defensa Inventada, S.L.", "ESP", "ESB99999990")])])
    load_placsp(conn, with_procedure(awarded(result("1", ALFA))))
    # WP-81: the TED notice states a value too; the PLACSP twin's awarded amount is preferred, and the pair counts once
    conn.execute("UPDATE opportunity SET value_amount = 1500, value_currency = 'EUR', value_kind = 'total' "
                 "WHERE native_id = '500002-2026'")
    conn.commit()
    public(monkeypatch, True)
    with TestClient(api.app) as client:
        got = everything(client)
    [item] = got["list"]
    assert item["awardCount"] == 1
    [notice] = got["profiles"][0]["notices"]
    assert notice["source"] == "ted" and [r["source"] for r in notice["alsoPublished"]] == ["es_placsp"]
    assert got["profiles"][0]["values"] == {
        "byCurrency": [{"currency": "EUR", "amount": 250000.0, "count": 1, "lotEstimates": 0}],
        "of": 1, "withoutValue": 0, "shared": 0, "suspect": 0}
    assert notice["valueAmount"] == 250000.0
    # without a PLACSP amount, the TED value stands, still once
    conn.execute("UPDATE award SET value_amount = NULL, value_currency = NULL")
    conn.commit()
    with TestClient(api.app) as client:
        again = everything(client)
    assert again["profiles"][0]["values"]["byCurrency"] == [{"currency": "EUR", "amount": 1500.0, "count": 1,
                                                             "lotEstimates": 0}]


def test_a_placsp_row_standing_for_the_pair_takes_the_ted_value_when_it_states_none(conn, env, monkeypatch):
    # WP-81: the PLACSP row (with the NIF) stands for the award; it states no amount, the TED twin does
    ted_result(conn, "500009-2026")
    load_ted(conn, [rec("500009-2026", [TED_ALFA_NO_ID])])
    load_placsp(conn, with_procedure(awarded(result("1", ALFA))))
    conn.execute("UPDATE award SET value_amount = NULL, value_currency = NULL")
    conn.execute("UPDATE opportunity SET value_amount = 7000, value_currency = 'EUR', value_kind = 'total' "
                 "WHERE native_id = '500009-2026'")
    conn.commit()
    public(monkeypatch, True)
    with TestClient(api.app) as client:
        got = everything(client)
    [profile] = got["profiles"]
    assert profile["notices"][0]["source"] == "es_placsp" and profile["notices"][0]["valueAmount"] == 7000.0
    assert profile["values"] == {"byCurrency": [{"currency": "EUR", "amount": 7000.0, "count": 1, "lotEstimates": 0}],
                                 "of": 1, "withoutValue": 0, "shared": 0, "suspect": 0}


def test_one_number_on_two_organisations_is_one_winner(conn, env, monkeypatch):
    """The cascade kept two bodies (another name in TED, the number written as a VAT number), but both rows state
    one number: one award. The TED row stands for it (both state a number; TED first)."""
    ted_result(conn, "500003-2026")
    load_ted(conn, [rec("500003-2026", [("Grupo Alfa Inventado Sociedad Limitada", "ESP", "ES-B99999990")])])
    load_placsp(conn, with_procedure(awarded(result("1", ALFA))))
    assert conn.execute("SELECT count(DISTINCT organisation_id) AS n FROM award").fetchone()["n"] == 2
    public(monkeypatch, True)
    assert [r["winner_method"] for r in conn.execute("SELECT winner_method FROM award_twin").fetchall()] == \
        ["identifier"]
    with TestClient(api.app) as client:
        got = everything(client)
    assert [(i["name"], i["awardCount"]) for i in got["list"]] == [("Grupo Alfa Inventado Sociedad Limitada", 1)]
    assert got["summary"]["awards"] == 1


def test_another_winner_of_the_same_procedure_is_another_award(conn, env, monkeypatch):
    ted_result(conn, "500004-2026")
    load_ted(conn, [rec("500004-2026", [TED_ALFA_NO_ID])])
    load_placsp(conn, with_procedure(awarded(result("1", ALFA) + result("2", BETA))))
    public(monkeypatch, True)
    with TestClient(api.app) as client:
        got = everything(client)
    assert sorted((i["name"].upper(), i["awardCount"]) for i in got["list"]) == [
        ("ALFA DEFENSA INVENTADA, S.L.", 1), ("BETA SISTEMAS INVENTADOS SA", 1)]
    assert got["summary"]["awards"] == 2


def test_two_ted_result_notices_and_the_numbered_placsp_folder_are_one_award(conn, env, monkeypatch):
    """Lots awarded apart: TED published two result notices of the procedure, PLACSP one folder with the NIF."""
    ted_result(conn, "500005-2026")
    ted_result(conn, "500006-2026", published=date(2026, 9, 28))
    load_ted(conn, [rec("500005-2026", [TED_ALFA_NO_ID]), rec("500006-2026", [TED_ALFA_NO_ID])])
    with TestClient(api.app) as client:
        # TED alone: two result notices of one procedure are one procurement (WP-85, `award_set.KEY`, as the demand answer)
        assert client.get("/v1/suppliers").json()["items"][0]["awardCount"] == 1
        load_placsp(conn, with_procedure(awarded(result("1", ALFA))))
        public(monkeypatch, True)
        got = everything(client)
    assert got["list"][0]["awardCount"] == 1 and got["summary"]["awards"] == 1
    assert sorted(r["noticeId"] for r in got["profiles"][0]["notices"][0]["alsoPublished"]) == \
        ["500005-2026", "500006-2026"]


def test_a_twin_link_without_a_procedure_identifier_is_the_same_procedure(conn, env, monkeypatch):
    """`ops/link_twins` tied the PLACSP folder to the TED notice (ted_ref); neither states a procedure identifier."""
    ted_result(conn, "500007-2026", pid=None)
    load_ted(conn, [rec("500007-2026", [TED_ALFA_NO_ID])])
    load_placsp(conn, awarded(result("1", ALFA)))
    conn.execute("UPDATE opportunity SET ted_ref = '500007-2026', twin_method = 'heuristic' WHERE source_id = %s",
                 (db.source_id(conn, "es_placsp"),))
    conn.commit()
    # The map reads the stored pairs (WP-75): a link made after the load reaches them with the daily twin job.
    assert stored_pairs(conn) == []
    assert worker.job_link_twins().ok
    assert stored_pairs(conn) == view_pairs(conn)
    public(monkeypatch, True)
    assert [r["procedure_method"] for r in conn.execute("SELECT * FROM award_twin").fetchall()] == ["ted_ref"]
    with TestClient(api.app) as client:
        assert client.get("/v1/suppliers").json()["items"][0]["awardCount"] == 1


def test_a_twin_the_map_does_not_serve_does_not_hide_the_other(conn, env, monkeypatch):
    """The preferred row is the PLACSP one; the PLACSP notice is removed on request: the TED win is counted."""
    ted_result(conn, "500008-2026")
    load_ted(conn, [rec("500008-2026", [TED_ALFA_NO_ID])])
    load_placsp(conn, with_procedure(awarded(result("1", ALFA))))
    conn.execute("UPDATE opportunity SET suppressed = TRUE WHERE source_id = %s", (db.source_id(conn, "es_placsp"),))
    conn.commit()
    public(monkeypatch, True)
    with TestClient(api.app) as client:
        got = everything(client)
    assert got["list"][0]["awardCount"] == 1
    assert got["profiles"][0]["notices"][0]["source"] == "ted"
    assert got["profiles"][0]["notices"][0]["alsoPublished"] == []


def test_natural_persons_are_counted_once_and_never_shown_and_placsp_is_attributed(conn, env, monkeypatch):
    ted_result(conn, "500009-2026")
    load_ted(conn, [rec("500009-2026", [TED_ALFA_NO_ID, ("Antonio Pérez Gómez", "ESP", None)])])
    load_placsp(conn, with_procedure(awarded(result("1", ALFA) + result("2", PERSON))))
    with TestClient(api.app) as client:
        off = everything(client)
        public(monkeypatch, True)
        on = everything(client)
    for got in (off, on):
        blob = json.dumps(got, ensure_ascii=False).upper()
        assert "PEREZ" not in blob and "PÉREZ" not in blob and "***9999**" not in blob
        assert got["summary"]["skippedNaturalPersons"] == 1          # the same person in both publications
    assert [s["code"] for s in off["summary"]["sources"]] == ["ted"] and "PLACSP" not in off["summary"]["coverage"]
    assert "PLACSP" in on["summary"]["coverage"] and "counted once" in on["summary"]["coverage"]
    placsp_note = on["summary"]["sources"][1]
    assert placsp_note["code"] == "es_placsp" and placsp_note["attribution"].startswith(
        "Origen de los datos: Ministerio de Hacienda")
    assert placsp_note["lastUpdated"].startswith("2026-09-20")
    attribution = on["profiles"][0]["attribution"]
    assert "© European Union" in attribution and "Ministerio de Hacienda" in attribution
    assert "2026-09-20" in attribution and "natural persons are never named" in attribution
    assert off["profiles"][0]["attribution"].startswith("Source: TED") and "Hacienda" not in \
        off["profiles"][0]["attribution"]


def test_a_supplier_only_in_placsp_is_not_served_while_the_switch_is_off(conn, env, monkeypatch):
    load_placsp(conn, awarded(result("1", BETA)))
    with TestClient(api.app) as client:
        assert client.get("/v1/suppliers").json()["total"] == 0
        org = conn.execute("SELECT organisation_id FROM award").fetchone()["organisation_id"]
        assert client.get(f"/v1/suppliers/{org}-beta").status_code == 404
        public(monkeypatch, True)
        assert client.get(f"/v1/suppliers/{org}-beta").json()["notices"][0]["source"] == "es_placsp"


def test_the_placsp_spelling_of_a_ted_supplier_is_not_shown_while_the_switch_is_off(conn, env, monkeypatch):
    """The supplier is public through TED; PLACSP spells it its own way twice. Off, the TED spelling is shown."""
    ted_result(conn, "500010-2026")
    load_ted(conn, [rec("500010-2026", [TED_ALFA_NO_ID])])
    load_placsp(conn, awarded(result("1", ALFA)))
    load_placsp(conn, awarded(result("1", ALFA), folder="2026/ETSAE0921/00002222E"))
    with TestClient(api.app) as client:
        assert client.get("/v1/suppliers").json()["items"][0]["name"] == "Alfa Defensa Inventada, S.L."


def test_the_read_only_report_counts_the_twins_and_the_pairs_it_may_have_missed(conn, env):
    from dgate.ops import supplier_twins

    ted_result(conn, "500011-2026")
    load_ted(conn, [rec("500011-2026", [TED_ALFA_NO_ID])])
    load_placsp(conn, with_procedure(awarded(result("1", ALFA))))
    ted_result(conn, "500012-2026", pid="1b2c3d4e-0000-4000-8000-000000000012")
    load_ted(conn, [rec("500012-2026", [("Delta Inventada SA", "ESP", None)])])
    load_placsp(conn, with_procedure(awarded(result("1", BETA), folder="2026/ETSAE0921/00003333E"),
                                     pid="1b2c3d4e-0000-4000-8000-000000000012"))
    got = supplier_twins.report(conn)
    assert got["twins"] == [{"procedure_method": "procedure_id", "winner_method": "organisation", "n": 1}]
    assert got["dropped_by_source"] == [{"code": "ted", "n": 1}]
    assert got["single_winner_pairs_not_matched"] == 1          # Delta in TED, Beta in PLACSP: for a person to read
    assert supplier_twins.main([]) == 0


# ------------------------------------------------- the stored pairs and the one-pass summary (WP-75)

PAIRS = "SELECT award_id, preferred_id, procedure_method, winner_method FROM {} ORDER BY 1, 2"


def stored_pairs(conn) -> list[dict]:
    return conn.execute(PAIRS.format("award_twin_set")).fetchall()


def view_pairs(conn) -> list[dict]:
    return conn.execute(PAIRS.format("award_twin")).fetchall()


def many_twins(conn) -> None:
    """Every kind of pair at once, beside suppliers that are in TED alone (three German ones: a published cell)."""
    ted_result(conn, "500021-2026")                                               # same organisation
    load_ted(conn, [rec("500021-2026", [TED_ALFA_NO_ID])])
    load_placsp(conn, with_procedure(awarded(result("1", ALFA) + result("2", BETA))))      # Beta: no twin
    pid = "1b2c3d4e-0000-4000-8000-000000000022"                                  # same number, two bodies
    ted_result(conn, "500022-2026", pid=pid)
    load_ted(conn, [rec("500022-2026", [("Grupo Gamma Inventado Sociedad Limitada", "ESP", "ES-B99999992")])])
    load_placsp(conn, with_procedure(awarded(result("1", winner("GAMMA INVENTADA SL", "B99999992")),
                                             folder="2026/ETSAE0921/00004444E"), pid=pid))
    ted_result(conn, "500023-2026", pid=None)                                     # the twin link, no identifier
    load_ted(conn, [rec("500023-2026", [("Delta Inventada SA", "ESP", "ESA99999993")])])
    load_placsp(conn, awarded(result("1", winner("DELTA INVENTADA SA", "A99999993")), folder="2026/ETSAE0921/00005555E"))
    conn.execute("UPDATE opportunity SET ted_ref = '500023-2026', twin_method = 'heuristic' WHERE native_id = %s",
                 ("2026/ETSAE0921/00005555E",))
    conn.commit()
    for i, name in enumerate(("Alfa Tech GmbH", "Beta Werke GmbH", "Gamma Systems GmbH")):
        ted_result(conn, f"50003{i}-2026", pid=None)
        load_ted(conn, [rec(f"50003{i}-2026", [(name, "DEU", f"DE12345678{i}")])])
    awards.refresh_award_twins(conn)
    conn.commit()


def old_summary_parts(conn) -> dict:
    """The summary's head, groups and cells as separate plain statements compute them (the five statements before
    WP-75), under the WP-85 rule: the award set (`award_set`), a win is a supplier and a procurement, a row in every
    CPV division its notice has a code in."""
    f, s = award_set.FROM, award_set.scope()
    p = {"since": award_set.since(), "k": suppliers.K_MIN}
    rows = f"""(SELECT org.id AS org, {award_set.KEY_HASH} AS key, a.supplier_country AS country, d.division
                  {f} LEFT JOIN LATERAL (SELECT DISTINCT left(c, 2) AS division FROM unnest(o.cpv_codes) c) d ON TRUE
                 WHERE {s}) r"""
    head = conn.execute(
        f"""SELECT count(DISTINCT key) AS notices, count(DISTINCT org) AS suppliers, count(DISTINCT (org, key)) AS awards
              FROM {rows}""", p).fetchone()

    def groups(expr: str) -> tuple[list, int]:
        got = conn.execute(f"""SELECT {expr} AS key, count(DISTINCT org) AS suppliers, count(DISTINCT (org, key)) AS awards
                                 FROM {rows} WHERE division IS NOT NULL GROUP BY 1 ORDER BY 3 DESC, 1""", p).fetchall()
        kept = [r for r in got if r["suppliers"] >= suppliers.K_MIN and r["key"]]
        return kept, len(got) - len(kept)

    by_cpv, hidden_cpv = groups("division")
    by_country, hidden_country = groups("country")
    cells = conn.execute(
        f"""SELECT division, country, count(DISTINCT org) AS suppliers, count(DISTINCT (org, key)) AS awards
              FROM {rows} WHERE division IS NOT NULL
             GROUP BY 1, 2 HAVING count(DISTINCT org) >= %(k)s ORDER BY 3 DESC, 4 DESC, 1, 2 LIMIT 300""", p).fetchall()
    total_cells = conn.execute(
        f"""SELECT count(*) AS n FROM (SELECT 1 FROM {rows} WHERE division IS NOT NULL
             GROUP BY division, country) t""", p).fetchone()["n"]
    return {"noticesWithSupplier": head["notices"], "suppliers": head["suppliers"], "awards": head["awards"],
            "byCpv": [dict(r) for r in by_cpv], "byCountry": [dict(r) for r in by_country],
            "cells": [dict(r) for r in cells],
            "suppressedGroups": hidden_cpv + hidden_country + (total_cells - len(cells))}


def test_the_stored_pairs_are_the_view_and_the_map_reads_the_same_from_either(conn, env, monkeypatch):
    many_twins(conn)
    assert stored_pairs(conn) == view_pairs(conn)
    assert {(r["procedure_method"], r["winner_method"]) for r in stored_pairs(conn)} == {
        ("procedure_id", "organisation"), ("procedure_id", "identifier"), ("ted_ref", "organisation")}
    public(monkeypatch, True)
    with TestClient(api.app) as client:
        stored = everything(client)
        monkeypatch.setattr(award_set, "NOT_TWIN", award_set.NOT_TWIN.replace("award_twin_set", "award_twin"))
        assert everything(client) == stored
    # Alfa, Beta, Gamma, Delta and the three German suppliers: one award each, every twin counted once
    assert stored["summary"]["awards"] == 7 and stored["summary"]["suppliers"] == 7
    assert stored["summary"]["cells"] and all(i["awardCount"] == 1 for i in stored["list"])


def test_the_summary_in_one_pass_says_what_the_five_statements_said(conn, env, monkeypatch):
    many_twins(conn)
    # a row without a CPV (WP-85: the groups read the notice's codes)
    conn.execute("""UPDATE opportunity SET cpv_codes = '{}' WHERE id IN (
                        SELECT opportunity_id FROM award WHERE name_as_stated = 'Beta Werke GmbH')""")
    conn.commit()
    with TestClient(api.app) as client:
        for on in (False, True):
            public(monkeypatch, on)
            got = client.get("/v1/suppliers/summary").json()
            assert {k: got[k] for k in old_summary_parts(conn)} == old_summary_parts(conn), on


def test_a_merged_supplier_is_one_profile_read_by_index(conn, env, monkeypatch):
    """The profile reads the award rows of the organisation and those merged into it (WP-75): both are counted."""
    for i in (1, 2):
        ted_result(conn, f"50004{i}-2026", pid=None)
    load_ted(conn, [rec("500041-2026", [("Epsilon Inventada SA", "ESP", "ESA99999994")]),
                    rec("500042-2026", [("Zeta Inventada SA", "ESP", "ESA99999995")])])
    first, second = [r["organisation_id"] for r in conn.execute(
        "SELECT organisation_id FROM award ORDER BY id").fetchall()]
    assert first != second
    conn.execute("UPDATE organisation SET merged_into = %s WHERE id = %s", (first, second))
    conn.commit()
    with TestClient(api.app) as client:
        [item] = client.get("/v1/suppliers").json()["items"]
        profile = client.get(f"/v1/suppliers/{item['slug']}").json()
        via_merged = client.get(f"/v1/suppliers/{second}-epsilon").json()
    assert item["awardCount"] == 2 and profile["noticeCount"] == 2 and len(profile["notices"]) == 2
    assert sorted(profile["namesAsStated"]) == ["Epsilon Inventada SA", "Zeta Inventada SA"]
    assert via_merged == profile


def test_the_four_hourly_job_brings_the_pairs_up_to_date(conn, env, monkeypatch):
    """A merge made after the load can make two rows one award: the list snapshots' job rewrites the pairs."""
    many_twins(conn)
    conn.execute("DELETE FROM award_twin_set")
    conn.commit()
    from dgate.ops import warm_lists

    monkeypatch.setattr(warm_lists, "run", lambda conn, write: {"views": 0, "written": 0, "failed": 0, "removed": 0})
    assert worker.job_warm_lists().ok
    assert stored_pairs(conn) == view_pairs(conn) != []


def test_the_scripted_refresh_says_what_differs_and_writes_only_with_yes(conn, env):
    from dgate.ops import supplier_twins

    many_twins(conn)
    n = len(view_pairs(conn))
    conn.execute("DELETE FROM award_twin_set WHERE award_id = (SELECT min(award_id) FROM award_twin_set)")
    conn.commit()
    assert supplier_twins.refresh(conn) == {"stored": n - 1, "view": n, "differ": 1}
    assert len(stored_pairs(conn)) == n - 1                                     # the dry run wrote nothing
    assert supplier_twins.main(["--refresh", "--yes"]) == 0
    conn.rollback()
    assert supplier_twins.refresh(conn) == {"stored": n, "view": n, "differ": 0}


# ------------------------------------------------- the nightly walk (item 2)

REAL_LIVE = placsp.fetch_live


def live_page(*entries: str) -> bytes:
    head = "\n".join(line for line in HEAD.splitlines() if 'rel="next"' not in line)
    return (head + "".join(entries) + "</feed>").encode("utf-8")


def walk(monkeypatch, body: bytes, now: datetime) -> Portal:
    portal = Portal({"licitacionesPerfilesContratanteCompleto3.atom": body})
    monkeypatch.setattr(placsp, "fetch_live", lambda ds, **kw: REAL_LIVE(ds, client=portal.client(), **kw))
    monkeypatch.setattr("dgate.ops.notify.notify", lambda text: None)
    pipeline.run_placsp_live(datasets=[placsp.MAIN], now=now)
    return portal


def test_the_nightly_walk_lands_and_loads_the_award_results_like_the_archive_loader(conn, env, monkeypatch):
    now = datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc)          # the feed is fresh: no archive is read
    portal = walk(monkeypatch, live_page(awarded(result("1", ALFA) + result("2", PERSON))), now)
    assert all(url.endswith("Completo3.atom") for _, url in portal.asked)
    rows = conn.execute("SELECT name_as_stated, superseded_at FROM award").fetchall()
    assert [(r["name_as_stated"], r["superseded_at"]) for r in rows] == [("ALFA DEFENSA INVENTADA, S.L.", None)]
    notice = conn.execute("SELECT * FROM award_notice").fetchone()
    assert notice["payload_hash"] and notice["skipped_person"] == 1 and notice["raw_key"].startswith("placsp_awards/")
    landed = json.dumps(build_store().get(notice["raw_key"]), ensure_ascii=False)
    assert "PEREZ" not in landed and "***9999**" not in landed and "Ciudad Inventada" not in landed

    def counts() -> dict[str, int]:
        return {t: conn.execute(f"SELECT count(*) AS n FROM {t}").fetchone()["n"]
                for t in ("opportunity", "opportunity_version", "award", "award_notice", "organisation",
                          "raw_ingest")}

    before = counts()
    walk(monkeypatch, live_page(awarded(result("1", ALFA) + result("2", PERSON))), now)   # the next night: same
    assert counts() == before

    # the winner renounced, the next one awarded: read again, the first marked superseded (not deleted)
    walk(monkeypatch, live_page(awarded(result("1", winner("GAMMA INVENTADA SL", "B99999992")), status="RES",
                                        updated="2026-10-01T10:00:00.000+02:00")),
         datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc))
    rows = conn.execute("SELECT name_as_stated, superseded_at IS NOT NULL AS gone FROM award ORDER BY id").fetchall()
    assert [(r["name_as_stated"], r["gone"]) for r in rows] == [
        ("ALFA DEFENSA INVENTADA, S.L.", True), ("GAMMA INVENTADA SL", False)]
