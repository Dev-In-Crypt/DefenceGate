"""WP-126 against a real Postgres: PLACSP unit prices set aside (the loader and the ops step, in no sum, the undo), and
the cleared Polish numbers another live row holds written as merge candidates, never merged."""

from __future__ import annotations

from collections import Counter
from decimal import Decimal

import pytest

from dgate import awards, db, placsp_awards
from dgate.ops import award_values, org_repair
from dgate.suppliers import value_of
from tests.integration.test_wp95 import award, env, notice, org  # noqa: F401  (fixtures)

pytestmark = pytest.mark.integration

QUIET = {"out": lambda *_: None}


def _num(x):
    return float(x) if isinstance(x, Decimal) else x


def _value(conn, award_id):
    return _num(conn.execute(f"SELECT v.va FROM award a {value_of('a.id', 'FALSE')} WHERE a.id = %s",
                             (award_id,)).fetchone()["va"])


def _award(conn, award_id):
    row = conn.execute("SELECT value_amount, value_currency, value_kind, value_set_aside, value_set_aside_reason "
                       "FROM award WHERE id = %s", (award_id,)).fetchone()
    return {k: _num(v) for k, v in row.items()}


def test_the_ops_step_sets_placsp_unit_prices_aside_out_of_every_sum_and_the_undo_puts_them_back(conn, env):  # noqa: F811
    buyer = org(conn, "jefatura de asuntos economicos del mando de apoyo logistico", "ES", is_defence_buyer=True)
    shoes_co, minor_co, ted_co = (org(conn, n, "ES") for n in ("calzados ejemplo", "talleres ejemplo", "ejemplo ted"))
    shoes = award(conn, notice(conn, "es_placsp", "2025/AM9008", buyer=buyer, title="Suministro de zapatillas de deporte",
                               value=(648000.0, "EUR", None)), shoes_co, "Calzados Ejemplo S.L.",
                  value=(84.95, "EUR", "contract"))
    minor = award(conn, notice(conn, "es_placsp", "2025/MIN1", buyer=buyer), minor_co, "Talleres Ejemplo S.L.",
                  value=(300.0, "EUR", "contract"))
    ted_row = award(conn, notice(conn, "ted", "100001-2026", buyer=buyer, value=(48.0, "EUR", "total")), ted_co,
                    "Ejemplo TED S.A.", value=(48.0, "EUR", "contract"))
    conn.commit()
    assert _value(conn, shoes) == 84.95

    report = award_values.run_unit_prices(conn, write=False)
    assert (report["unit_prices_set_aside"], report["unit_prices_set_aside_contract"]) == (1, 1)
    assert report["unit_prices_set_aside_amount"] == 84.95
    award_values.run_unit_prices(conn, write=True)
    assert tuple(_award(conn, shoes).values()) == (None, "EUR", "contract", 84.95, "unit_price")
    assert _value(conn, shoes) is None                         # in no sum: the row has no value
    assert _award(conn, minor)["value_amount"] == 300 and _award(conn, ted_row)["value_amount"] == 48   # not PLACSP < 100
    assert award_values.run_unit_prices(conn, write=False)["unit_prices_set_aside"] == 0   # a second run: nothing

    assert award_values.run_unit_prices(conn, write=True, undo=True)["unit_prices_restored"] == 1
    assert tuple(_award(conn, shoes).values()) == (84.95, "EUR", "contract", None, None)


def test_the_loader_sets_a_unit_price_aside_on_every_read(conn, env):  # noqa: F811
    opp = notice(conn, "es_placsp", "2026/AR43U/00009999E", title="Servicio de catering")
    conn.commit()
    landed = {"natural_persons": 0, "results": [
        {"result_code": "8", "value": 45.72, "currency": "EUR",
         "winners": [{"name": "Catering Ejemplo S.L.", "country": "ES", "identifier": "B99999990"}]}]}
    src = db.source_id(conn, "es_placsp")
    awards.store_notice(conn, src, {"id": opp, "cpv_codes": ["55520000"]}, placsp_awards.read(landed, "contract"),
                        "raw/key", Counter(), payload_hash="h1")
    conn.commit()
    row = conn.execute("SELECT id FROM award WHERE opportunity_id = %s", (opp,)).fetchone()
    assert tuple(_award(conn, row["id"]).values()) == (None, "EUR", "contract", 45.72, "unit_price")
    landed["results"][0]["value"] = 45720.0                   # a later read states a contract total: it stands
    awards.store_notice(conn, src, {"id": opp, "cpv_codes": ["55520000"]}, placsp_awards.read(landed, "contract"),
                        "raw/key", Counter(), payload_hash="h2")
    conn.commit()
    assert tuple(_award(conn, row["id"]).values()) == (45720, "EUR", "contract", None, None)


def test_a_cleared_number_another_live_row_holds_becomes_a_merge_candidate_and_nothing_is_merged(conn):
    nip, regon = "1234563218", "000177916"
    cleared = org(conn, "gmina kolbiel", "PL")
    holder = org(conn, "gmina kolbiel", "PL", national_reg_no=nip)
    short = org(conn, "zaklad karny", "PL")
    short_holder = org(conn, "zaklad karny we wronki", "PL", national_reg_no=regon)
    own = org(conn, "szpital", "PL")          # its number is on no other row: restore-ids' case, not this one
    for oid, old in ((cleared, nip + regon), (short, "177916"), (own, "5250007282000177916")):
        db.log_repair(conn, oid, "clear_false_identifier", old_value=old, new_value=None, method="wp115_register_check",
                      detected_by=org_repair.DETECTED_BY)
    conn.commit()

    report = org_repair.held_ids(conn, apply=False, **QUIET)
    assert (report["nip_regon_pair_held_by_another_row"], report["unpadded_regon_held_by_another_row"]) == (1, 1)
    assert report["nip_regon_pair_held_by_none"] == 1 and report["candidate_pairs_new"] == 2
    org_repair.held_ids(conn, apply=True, **QUIET)
    got = conn.execute("""SELECT organisation_id, candidate_org_id, match_method, confidence, status, evidence
                            FROM organisation_merge_candidate ORDER BY organisation_id""").fetchall()
    assert [(r["organisation_id"], r["candidate_org_id"]) for r in got] == [(cleared, holder), (short, short_holder)]
    assert all(r["match_method"] == org_repair.HELD_ID and float(r["confidence"]) == 0.90 and r["status"] == "pending"
               for r in got)
    assert all(nip not in r["evidence"] and regon not in r["evidence"] for r in got)   # names and rows, never the number
    assert conn.execute("SELECT count(*) AS n FROM organisation WHERE merged_into IS NOT NULL").fetchone()["n"] == 0
    assert org_repair.held_ids(conn, apply=False, **QUIET)["candidate_pairs_new"] == 0
