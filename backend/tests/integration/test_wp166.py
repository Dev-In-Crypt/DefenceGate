"""WP-166: each suggested partner's and each consortium-gap organisation's past roles (coordinator, participant, third party),
counted over all its projects in CORDIS and the EDF factsheets, through `merged_into`. Organisations only, never a person."""

from __future__ import annotations

import pytest

from tests.integration import test_network_api as net
from tests.integration import test_wp32 as wp32

pytestmark = pytest.mark.integration

_fresh_cache = wp32._fresh_cache
client = wp32.client
space = wp32.space
world = net.world


def test_a_partner_suggestion_carries_its_past_roles_over_all_its_projects(client, conn, space):
    # outside the call's area: still a past role (the count is of every project, not only the area's)
    wp32.join(conn, wp32.project(conn, "tp", category="AIR", year=2022, topic="EDF-2022-DA-AIR-X"), space["a"], "third_party")
    wp32.join(conn, wp32.project(conn, "ap", category="AIR", year=2021, topic="EDF-2021-DA-AIR-X"), space["a"], "associated_partner")
    conn.commit()
    _, slug = wp32.call(conn, "edf1", "EDF-2026-DA-SPACE-PRS-STEP")
    body = wp32.partners(client, slug)
    by = {p["name"]: p["roles"] for p in body["partners"]}
    assert by["Alpha SA"] == {"coordinator": 1, "participant": 2, "thirdParty": 1, "other": 1}
    assert by["Delta SA"] == {"coordinator": 1, "participant": 0, "thirdParty": 0, "other": 0}
    # Echo's project in another category counts as a past role too; Foxtrot's inactive participation never does
    assert by["Echo AB"]["participant"] == 2
    ua = wp32.partners(client, slug, country="UA")
    assert ua["partners"] == [] and ua["total"] == 0


def test_consortium_gap_organisations_carry_their_past_roles_merged_rows_included(client, world):
    body = client.get("/v1/analytics/consortium-gaps?programme=EDF&topic=CYBER&lacking=UA").json()
    roles = {i["organisation"]["name"]: i["roles"] for i in body["items"]}
    assert roles["ALPHA SYSTEMS GMBH"] == {"coordinator": 3, "participant": 1, "thirdParty": 0, "other": 0}
    # Bravo's merged-away row took part in ECHOP: it counts for Bravo
    assert roles["BRAVO INGÉNIERIE SAS"] == {"coordinator": 1, "participant": 4, "thirdParty": 0, "other": 0}
    assert roles["ECHO IBERICA SL"] == {"coordinator": 1, "participant": 3, "thirdParty": 0, "other": 0}
