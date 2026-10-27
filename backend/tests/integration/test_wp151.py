"""WP-151 against a real Postgres: BOAMP buyers across the 2024 eForms switch.

1. New notices resolve by the SIRET every BOAMP shape states (the mapper read none before).
2. `ops.boamp_buyer_ids` repairs the rows split before the fix: the report changes nothing, `--yes`
   merges the one-to-one pairs with method and confidence and leaves ambiguous groups, and the undo
   puts every row back.
"""

from __future__ import annotations

import json
from datetime import date

import pytest

from dgate import db
from dgate.normalise import Opportunity, from_boamp, normalise_org_name
from dgate.ops import boamp_buyer_ids as op
from dgate.pipeline import _finalise
from dgate.rawstore import FileRawStore, bundle_key, record_key

pytestmark = pytest.mark.integration


def _n(conn, sql, *params) -> int:
    return conn.execute(sql, params).fetchone()["n"]


def _record(idweb: str, name: str, day: str, siret: str | None, shape: str = "legacy") -> dict:
    if shape == "legacy":
        body = {"IDENTITE": {"DENOMINATION": name, **({"CODE_IDENT_NATIONAL": siret} if siret else {})}}
    else:
        body = {"FNSimple": {"organisme": {"nomOfficiel": name, "typeIdentificationNational": {"siret": ""},
                                           **({"codeIdentificationNational": siret} if siret else {})}}}
    return {"idweb": idweb, "objet": f"Travaux {idweb}", "nomacheteur": name, "dateparution": day,
            "perimetre": "DIRECTIVE-81", "nature": "APPEL_OFFRE", "donnees": json.dumps(body)}


def _ingest(conn, opp: Opportunity) -> int:
    src = db.source_id(conn, "fr_boamp")
    opp = _finalise(conn, opp, src)
    db.upsert_opportunity(conn, opp, f"hash-{opp.native_id}", src)
    conn.commit()
    return opp.buyer_org_id


# ------------------------------------------------------------------ new notices

def test_a_new_notice_finds_its_buyer_by_siret(conn):
    old = _ingest(conn, from_boamp(_record("19-1", "Mairie de Beziers", "2019-05-02", "21340032000014")))
    new = _ingest(conn, from_boamp(_record("26-1", "Ville de Béziers - Mairie", "2026-10-02", "21340032000014",
                                           shape="fnsimple")))
    assert new == old
    alias = conn.execute("SELECT match_method FROM organisation_alias WHERE normalised_name = %s",
                         (normalise_org_name("Ville de Béziers - Mairie"),)).fetchone()
    assert alias["match_method"] == "identifier"


def test_an_html_reference_in_the_name_is_the_same_buyer(conn):
    old = _ingest(conn, from_boamp(_record("20-2", "Département de l'Oise", "2020-05-02", None)))
    new = _ingest(conn, from_boamp(_record("26-2", "Département de l&#039;Oise", "2026-10-02", None, "fnsimple")))
    assert new == old


# ------------------------------------------------------------------ the repair

# (native id, stated name, published, SIRET in the payload): the state production was in before the fix
SPLIT = [
    ("19-10", "MINARM/SGA/DCSID/ESID Lyon", "2019-03-01", "13000190200274"),   # A, old
    ("25-10", "SID Sud-Est", "2025-03-01", "13000190200274"),                  # B, new: pairs with A by SIRET
    ("20-11", "Département de l'Oise", "2020-03-01", None),                    # C, old
    ("25-11", "Département de l&#039;Oise", "2025-04-01", None),               # D, new: pairs with C by name
    ("18-12", "MINARM/AIR/SIAé", "2018-03-01", "11000000000013"),              # E, old
    ("19-12", "MINARM/SCA/PFC-RBT", "2019-03-01", "11000000000013"),           # F, old
    ("25-12", "Ministère des Armées", "2025-03-01", "11000000000013"),         # G, new: one new, two old: left
    ("17-13", "SYDER", "2017-03-01", "25390186300017"),                        # H, old, alone: number attached
]


def _land_split(conn, store, monkeypatch) -> dict[str, int]:
    """Archive the notices as the old mapper did (no buyer number, HTML references kept in the key)."""
    real = normalise_org_name
    bundle = bundle_key("fr_boamp", date(2026, 9, 23))
    store.put_records(bundle, [_record(i, name, day, siret) for i, name, day, siret in SPLIT])
    src = db.source_id(conn, "fr_boamp")
    orgs = {}
    with monkeypatch.context() as m:
        m.setattr(db, "normalise_org_name", lambda raw, **kw: real((raw or "").replace("&#", "& #"), **kw))
        for line, (i, name, day, _) in enumerate(SPLIT):
            orgs[i] = _ingest(conn, from_boamp(_record(i, name, day, None)))
            db.record_raw(conn, src, i, f"raw-{i}", record_key(bundle, line))
    conn.commit()
    assert len(set(orgs.values())) == len(SPLIT)          # every row its own organisation, as on production
    return orgs


def _state(conn):
    return (conn.execute("SELECT id, merged_into, national_reg_no FROM organisation ORDER BY id").fetchall(),
            conn.execute("SELECT native_id, buyer_org_id FROM opportunity ORDER BY native_id").fetchall(),
            conn.execute("SELECT id, organisation_id FROM organisation_alias ORDER BY id").fetchall(),
            _n(conn, "SELECT count(*) n FROM organisation_merge_candidate"),
            _n(conn, "SELECT count(*) n FROM opportunity_version"))


def test_the_report_changes_nothing_and_yes_merges_and_undo_restores(conn, tmp_path, monkeypatch):
    store = FileRawStore(tmp_path / "raw")
    orgs = _land_split(conn, store, monkeypatch)
    before = _state(conn)

    lines: list[str] = []
    report = op.run(conn, store, apply=False, out=lines.append)
    assert _state(conn) == before
    assert report["pairs"] == {op.METHOD_ID: 1, op.METHOD_NAME: 1}
    assert report["notices_moved"] == 2 and report["attach"] == 1
    assert report["left_out"] == {(op.METHOD_ID, "one eForms-era buyer, 2 older ones"): 1}
    text = "\n".join(lines)
    assert "report only: nothing written" in text
    assert "'sid sud-est'" in text and "examples left out" in text

    done = op.run(conn, store, apply=True, out=lambda *_: None)
    assert (done["merged"], done["attached"], done["skipped"]) == (2, 1, 0)
    a, b, c, d = orgs["19-10"], orgs["25-10"], orgs["20-11"], orgs["25-11"]
    rows = {r["id"]: r for r in conn.execute(
        "SELECT id, merged_into, merge_method, merge_confidence, national_reg_no, identifier_method FROM organisation"
    ).fetchall()}
    assert (rows[b]["merged_into"], rows[b]["merge_method"], float(rows[b]["merge_confidence"])) == (a, op.METHOD_ID, 0.9)
    assert (rows[d]["merged_into"], rows[d]["merge_method"]) == (c, op.METHOD_NAME)
    assert rows[a]["national_reg_no"] == "13000190200274"
    assert rows[orgs["17-13"]]["national_reg_no"] == "25390186300017"
    assert all(rows[orgs[i]]["merged_into"] is None for i in ("18-12", "19-12", "25-12"))
    assert _n(conn, "SELECT count(*) n FROM opportunity WHERE buyer_org_id = %s", a) == 2
    assert _n(conn, """SELECT count(*) n FROM organisation_merge_candidate
                        WHERE status = 'merged' AND match_method = ANY(%s)""", list(op.METHODS)) == 2
    assert _n(conn, "SELECT count(*) n FROM opportunity_version") == before[4]       # the archive is not touched

    # the next eForms-era notice of the paired buyer resolves to the kept row, by number then alias
    nxt = _ingest(conn, from_boamp(_record("26-10", "SID Sud-Est", "2026-10-20", "13000190200274", "fnsimple")))
    assert nxt == a

    start, end = done["window"]
    # the new notice was archived after the run's window; the undo leaves it on the kept row
    dry = op.undo(conn, start, end, apply=False, out=lambda *_: None)
    assert dry["rows"] == 2 and dry["numbers_detached"] == 2
    undone = op.undo(conn, start, end, apply=True, out=lambda *_: None)
    assert undone["applied"]
    after = {r["id"]: r for r in conn.execute("SELECT id, merged_into, national_reg_no FROM organisation").fetchall()}
    assert after[b]["merged_into"] is None and after[d]["merged_into"] is None
    assert after[a]["national_reg_no"] is None and after[orgs["17-13"]]["national_reg_no"] is None
    back = {r["native_id"]: r["buyer_org_id"] for r in conn.execute("SELECT native_id, buyer_org_id FROM opportunity")}
    assert {k: v for k, v in back.items() if k != "26-10"} == orgs
    assert _n(conn, """SELECT count(*) n FROM organisation_merge_candidate
                        WHERE status = 'merged' AND match_method = ANY(%s)""", list(op.METHODS)) == 0
