"""WP-8 (owner decision of 14 October 2026) against a real Postgres: the two groups that
leave `core` for `supply` are served under that scope, filterable, searchable and named by
`qualifiedBy`; and the buyer cleanup keeps the flag of a real defence body.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from dgate import api, db, stats
from dgate.normalise import Opportunity
from dgate.ops import buyer_cleanup

pytestmark = pytest.mark.integration

FUTURE = datetime.now(timezone.utc) + timedelta(days=30)
DIRECTIVE = "32009L0081"


@pytest.fixture(autouse=True)
def _fresh_cache():
    stats.reset_cache()
    yield
    stats.reset_cache()


@pytest.fixture()
def client(conn):
    with TestClient(api.app) as c:
        yield c


def _store(conn, native_id, buyer, country, *, cls, legal=False, military=False,
           buyer_flag=False, cpv=("45000000",), title="Works"):
    opp = Opportunity(source_code="ted", native_id=native_id, buyer_name_raw=buyer,
                      title_original=title, country=country, published_at=date(2026, 10, 1),
                      deadline_at=FUTURE, cpv_codes=list(cpv), status="open", is_defence=True,
                      sig_cpv=military, sig_cpv_military=military, sig_legal_basis=legal,
                      sig_buyer=buyer_flag, buyer_class=cls,
                      legal_basis=DIRECTIVE if legal else "32014L0024")
    src = db.source_id(conn, "ted")
    opp.buyer_org_id = db.resolve_organisation(conn, buyer, country, src_id=src)
    oid, _ = db.upsert_opportunity(conn, opp, f"h-{native_id}", src)
    conn.commit()
    return oid


def _ids(client, **params):
    body = client.get("/v1/tenders", params={"status": "all", **params}).json()
    return {t["noticeId"]: t for t in body["items"]}


def test_the_two_groups_are_supply_findable_and_named(client, conn):
    _store(conn, "CORE-DEF", "Armasuisse", "CH", cls="defence", legal=True)
    _store(conn, "CORE-BOTH", "Stadt Nürnberg", "DE", cls="municipal", legal=True,
           military=True, cpv=("35400000",))
    _store(conn, "CIVIL", "Landesbetrieb Bau und Liegenschaften", "DE", cls="other",
           legal=True, title="Scaffolding works")
    _store(conn, "POLICE", "Komenda Główna Policji", "PL", cls="security", military=True,
           cpv=("35321200",), title="Traffic enforcement devices")
    _store(conn, "SUPPLY-BUYER", "Forsvarsbygg", "NO", cls="defence", buyer_flag=True)
    # a row the classifier has not read yet (class NULL): never moved, and NULL logic in the
    # SQL must not drop it from `core`
    _store(conn, "CORE-NULL", "Unclassified Buyer", "PL", cls=None, military=True,
           cpv=("35400000",))

    core = _ids(client, scope="core")
    assert set(core) == {"CORE-DEF", "CORE-BOTH", "CORE-NULL"}
    supply = _ids(client, scope="supply")
    assert set(supply) == {"CIVIL", "POLICE", "SUPPLY-BUYER"}
    assert set(_ids(client, scope="all")) == set(core) | set(supply)

    assert supply["CIVIL"]["scope"] == "supply"
    assert supply["CIVIL"]["qualifiedBy"] == ["directive_civil_buyer"]
    assert supply["POLICE"]["scope"] == "supply"
    assert supply["POLICE"]["qualifiedBy"] == ["security_buyer_cpv"]
    assert supply["POLICE"]["militaryCpv"] == ["35321200"]
    assert supply["SUPPLY-BUYER"]["qualifiedBy"] == ["buyer"]
    # still findable by search, in the group's scope and in `all`
    assert "CIVIL" in _ids(client, scope="supply", q="scaffolding")
    assert "POLICE" in _ids(client, scope="all", q="enforcement")
    # the detail page agrees
    oid = next(t["id"] for t in supply.values() if t["noticeId"] == "CIVIL")
    assert client.get(f"/v1/tenders/{oid}").json()["scope"] == "supply"


# ------------------------------------------------------------------ buyer cleanup, step 2

def _org(conn, name, country, *, source, flagged=True):
    oid = conn.execute(
        """INSERT INTO organisation (canonical_name, country, is_defence_buyer,
                                     defence_buyer_source)
           VALUES (%s, %s, %s, %s) RETURNING id""", (name, country, flagged, source)
    ).fetchone()["id"]
    conn.commit()
    return oid


def _merged_namesake(conn, name, country, into):
    oid = _org(conn, name, country, source="derived_rule", flagged=False)
    conn.execute("UPDATE organisation SET merged_into = %s WHERE id = %s", (into, oid))
    conn.commit()
    return oid


@pytest.mark.parametrize("name, country, holder", [
    ("junta de contratacion del ejercito de tierra", "ES",
     "direccion de asuntos economicos del ejercito"),                       # org 311783
    ("minarm sga dcsid esid toulon service achats infrastructure", "FR",
     "minarm air siae"),                                                    # org 331798
])
def test_cleanup_keeps_the_flag_of_a_real_defence_body_it_inherited(conn, name, country, holder):
    """Both carry a flag inherited from a namesake that was merged into another, flagged
    organisation; the tool read that as 'no flagged namesake is left' and a municipal or
    property word in the name as the reason."""
    top = _org(conn, holder, country, source="seed")
    _merged_namesake(conn, name, country, top)
    held = _org(conn, name, country, source="namesake")
    assert held not in [r["id"] for r in buyer_cleanup.rejected_flags(conn, keep=set())]


def test_cleanup_keeps_a_derived_flag_the_classifier_reads_as_defence(conn):
    org = _org(conn, "minarm sga dcsid esid toulon service achats infrastructure", "FR",
               source="derived_rule")
    assert org not in [r["id"] for r in buyer_cleanup.rejected_flags(conn, keep=set())]


def test_cleanup_never_withdraws_the_flag_of_a_body_with_notices_under_the_directive(conn):
    flagged = _org(conn, "dga council of europe directorate general of administration", "FR",
                   source="derived_rule")
    other = _org(conn, "dga france travail", "FR", source="derived_rule")
    assert {flagged, other} <= {r["id"] for r in buyer_cleanup.rejected_flags(conn, keep=set())}
    oid = _store(conn, "LB-1", "DGA Council of Europe Directorate General of Administration",
                 "FR", cls="international", legal=True)
    conn.execute("UPDATE opportunity SET buyer_org_id = %s WHERE id = %s", (flagged, oid))
    conn.commit()
    gone = {r["id"] for r in buyer_cleanup.rejected_flags(conn, keep=set())}
    assert flagged not in gone and other in gone
