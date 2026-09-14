"""Migration 0007 against a real Postgres.

The session fixture has already applied 0007 to an empty schema, where it does
nothing. These tests write names in the form the old normaliser produced, run
the migration file again, and check the result against the Python normaliser:
the SQL copy is only correct if the two agree.
"""

from __future__ import annotations

import pytest

from dgate import db, normalise
from dgate.normalise import normalise_org_name
from tests.conftest import MIGRATIONS
from tests.integration.test_archive_integration import NOTICE, ingest

pytestmark = pytest.mark.integration

SQL = (MIGRATIONS / "0007_transliterate_org_names.sql").read_text(encoding="utf-8")

BIALYSTOK = "16 Wojskowy Oddział Gospodarczy w Białymstoku"
BIALYSTOK_ASCII = "16 WOJSKOWY ODDZIAL GOSPODARCZY W BIALYMSTOKU"


@pytest.fixture()
def old_form(monkeypatch):
    """normalise_org_name as it was before transliteration existed."""
    def old(raw: str) -> str:
        with monkeypatch.context() as m:
            m.setattr(normalise, "_TRANSLITERATE", {})
            return normalise_org_name(raw)
    return old


def run_migration(conn) -> None:
    conn.execute(SQL)
    conn.commit()


def add_org(conn, name: str, country: str = "PL", **extra) -> int:
    cols = ["canonical_name", "country", *extra]
    return conn.execute(
        f"INSERT INTO organisation ({', '.join(cols)}) VALUES "
        f"({', '.join(['%s'] * len(cols))}) RETURNING id",
        (name, country, *extra.values()),
    ).fetchone()["id"]


def add_alias(conn, org_id: int, raw: str, norm: str, source_id: int | None,
              country: str | None = "PL") -> int:
    return conn.execute(
        """INSERT INTO organisation_alias
             (organisation_id, raw_name, normalised_name, source_id, country_hint,
              match_method, confidence)
           VALUES (%s, %s, %s, %s, %s, 'exact_name', 0.95) RETURNING id""",
        (org_id, raw, norm, source_id, country),
    ).fetchone()["id"]


def candidates(conn) -> list[dict]:
    return conn.execute(
        """SELECT organisation_id, candidate_org_id, match_method, confidence, status
             FROM organisation_merge_candidate ORDER BY id"""
    ).fetchall()


def test_old_form_really_differs(old_form):
    """Guard for the fixture: without this the rest would test nothing."""
    assert old_form(BIALYSTOK) != normalise_org_name(BIALYSTOK)


def test_sql_agrees_with_python_normaliser(conn, old_form):
    names = [
        BIALYSTOK,
        "Wojskowe Zakłady Łączności Nr 1 S.A.",
        "Bumar-Łabędy S.A.",
        "MESKO Spółka Akcyjna",
        "Politechnika Łódzka",
        "Forsvarsministeriets Materiel- og Indkøbsstyrelse",
        "Landesamt für Straßenbau GmbH",
        "Đuro Đaković Holding d.d.",
        "Æbeltoft Kommune",
        "Agencja Uzbrojenia",
    ]
    src = db.source_id(conn, "pl_atlas")
    orgs, aliases = {}, {}
    for name in names:
        org_id = add_org(conn, old_form(name))
        orgs[org_id] = name
        aliases[add_alias(conn, org_id, name, old_form(name), src)] = name
    conn.commit()

    run_migration(conn)

    for row in conn.execute("SELECT id, canonical_name FROM organisation").fetchall():
        assert row["canonical_name"] == normalise_org_name(orgs[row["id"]])
    for row in conn.execute("SELECT id, normalised_name FROM organisation_alias").fetchall():
        assert row["normalised_name"] == normalise_org_name(aliases[row["id"]])
    assert candidates(conn) == []


def test_organisations_that_now_collide_are_queued_not_merged(conn, old_form):
    polish = add_org(conn, old_form(BIALYSTOK))
    ascii_ = add_org(conn, old_form(BIALYSTOK_ASCII), review_status="human_verified")
    conn.commit()

    run_migration(conn)

    rows = conn.execute(
        "SELECT id, canonical_name, review_status FROM organisation ORDER BY id"
    ).fetchall()
    assert [r["id"] for r in rows] == [polish, ascii_], "nothing is merged or deleted"
    assert {r["canonical_name"] for r in rows} == {normalise_org_name(BIALYSTOK)}
    assert rows[1]["review_status"] == "human_verified"
    got = candidates(conn)
    assert len(got) == 1
    assert (got[0]["organisation_id"], got[0]["candidate_org_id"]) == (polish, ascii_)
    assert got[0]["match_method"] == "transliteration_fold"
    assert float(got[0]["confidence"]) == 0.90
    assert got[0]["status"] == "pending"


def test_new_ingest_after_migration_finds_the_existing_organisation(conn, old_form):
    """The point of the change: the ASCII spelling stops creating a second row."""
    src = db.source_id(conn, "pl_atlas")
    org = add_org(conn, old_form(BIALYSTOK))
    add_alias(conn, org, BIALYSTOK, old_form(BIALYSTOK), src)
    conn.commit()

    run_migration(conn)

    ted = db.source_id(conn, "ted")
    assert db.resolve_organisation(conn, BIALYSTOK_ASCII, "PL", src_id=ted) == org
    assert db.resolve_organisation(conn, BIALYSTOK, "PL", src_id=src) == org
    conn.commit()
    assert conn.execute("SELECT count(*) n FROM organisation").fetchone()["n"] == 1


def test_alias_key_collision_across_organisations_keeps_both_and_queues(conn, old_form):
    src = db.source_id(conn, "pl_atlas")
    polish = add_org(conn, old_form(BIALYSTOK))
    ascii_ = add_org(conn, "16 wojskowy oddzial gospodarczy w bialymstoku zegrze")
    held = add_alias(conn, ascii_, BIALYSTOK_ASCII, old_form(BIALYSTOK_ASCII), src)
    blocked = add_alias(conn, polish, BIALYSTOK, old_form(BIALYSTOK), src)
    conn.commit()

    run_migration(conn)

    rows = {r["id"]: r for r in conn.execute(
        "SELECT id, organisation_id, normalised_name FROM organisation_alias").fetchall()}
    assert set(rows) == {held, blocked}, "no alias is deleted"
    assert rows[held]["normalised_name"] == normalise_org_name(BIALYSTOK)
    assert rows[blocked]["normalised_name"] == old_form(BIALYSTOK), (
        "the colliding alias keeps its old key rather than breaking the unique index")
    assert rows[blocked]["organisation_id"] == polish, "and is not repointed"
    got = [c for c in candidates(conn) if c["match_method"] == "alias_transliteration_fold"]
    assert len(got) == 1
    assert (got[0]["organisation_id"], got[0]["candidate_org_id"]) == (polish, ascii_)


def test_alias_collision_between_two_renamed_rows(conn, old_form):
    """"Ærø" and "Aerø" are different old keys that fold to one new key."""
    src = db.source_id(conn, "ted")
    a = add_org(conn, old_form("Ærø Kommune"), country="DK")
    b = add_org(conn, old_form("Aerø Kommune"), country="DK")
    first = add_alias(conn, a, "Ærø Kommune", old_form("Ærø Kommune"), src, "DK")
    second = add_alias(conn, b, "Aerø Kommune", old_form("Aerø Kommune"), src, "DK")
    conn.commit()

    run_migration(conn)

    names = {r["id"]: r["normalised_name"] for r in conn.execute(
        "SELECT id, normalised_name FROM organisation_alias").fetchall()}
    assert names[first] == "aero kommune"
    assert names[second] == old_form("Aerø Kommune")
    methods = {c["match_method"] for c in candidates(conn)}
    assert methods == {"transliteration_fold", "alias_transliteration_fold"}


def test_alias_collision_within_one_organisation_needs_no_review(conn, old_form):
    src = db.source_id(conn, "pl_atlas")
    org = add_org(conn, normalise_org_name(BIALYSTOK))
    add_alias(conn, org, BIALYSTOK_ASCII, old_form(BIALYSTOK_ASCII), src)
    add_alias(conn, org, BIALYSTOK, old_form(BIALYSTOK), src)
    conn.commit()

    run_migration(conn)

    assert conn.execute("SELECT count(*) n FROM organisation_alias").fetchone()["n"] == 2
    assert candidates(conn) == []


def test_seeded_aliases_with_no_source_collide_since_0005(conn, old_form):
    """0005 made the alias key NULLS NOT DISTINCT; seeded rows have source_id NULL.

    Treating NULL as distinct here would try to write a second row with the same
    key and abort the whole migration on the unique index.
    """
    seeded = add_org(conn, old_form(BIALYSTOK))
    ingested = add_org(conn, "16 wog bialystok")
    held = add_alias(conn, ingested, BIALYSTOK_ASCII, old_form(BIALYSTOK_ASCII), None)
    blocked = add_alias(conn, seeded, BIALYSTOK, old_form(BIALYSTOK), None)
    renamed = add_alias(conn, seeded, "Oddział Białystok", old_form("Oddział Białystok"), None)
    conn.commit()

    run_migration(conn)

    names = {r["id"]: r["normalised_name"] for r in conn.execute(
        "SELECT id, normalised_name FROM organisation_alias").fetchall()}
    assert names[held] == normalise_org_name(BIALYSTOK)
    assert names[blocked] == old_form(BIALYSTOK)
    assert names[renamed] == "oddzial bialystok", "a free NULL-source key is still renamed"
    got = [c for c in candidates(conn) if c["match_method"] == "alias_transliteration_fold"]
    assert [(c["organisation_id"], c["candidate_org_id"]) for c in got] == [(seeded, ingested)]


def test_running_again_changes_nothing(conn, old_form):
    add_org(conn, old_form(BIALYSTOK))
    add_org(conn, old_form(BIALYSTOK_ASCII))
    conn.commit()
    run_migration(conn)
    before_orgs = conn.execute("SELECT * FROM organisation ORDER BY id").fetchall()
    before_candidates = conn.execute(
        "SELECT * FROM organisation_merge_candidate ORDER BY id").fetchall()

    run_migration(conn)

    assert conn.execute("SELECT * FROM organisation ORDER BY id").fetchall() == before_orgs
    assert conn.execute(
        "SELECT * FROM organisation_merge_candidate ORDER BY id").fetchall() == before_candidates


def test_archive_is_untouched(conn, old_form):
    oid, _ = ingest(conn, NOTICE)
    add_org(conn, old_form(BIALYSTOK))
    add_org(conn, old_form(BIALYSTOK_ASCII))
    conn.commit()
    before = conn.execute("SELECT * FROM opportunity_version ORDER BY id").fetchall()
    opp_before = conn.execute("SELECT * FROM opportunity WHERE id = %s", (oid,)).fetchone()

    run_migration(conn)

    assert conn.execute("SELECT * FROM opportunity_version ORDER BY id").fetchall() == before
    assert conn.execute(
        "SELECT * FROM opportunity WHERE id = %s", (oid,)).fetchone() == opp_before
