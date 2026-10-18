"""WP-43, N1: a role's payment is summed once, however many organisation nodes or projects the role points to."""

from __future__ import annotations

from dgate.sources import cordis


def _row(**kw):
    row = {"project": "242772", "org": "089d", "role": "participant", "amount": "92035", "orgs": "1", "projects": "1"}
    row.update(kw)
    return row


def test_a_role_with_one_organisation_node_keeps_its_amount():
    assert cordis.role_record(_row()).contribution == 92035.0


def test_a_payment_read_twice_because_the_role_has_two_organisation_nodes_is_halved():
    # ENEN2plus, CEA: the open data holds 46,017.50; the sum over two nodes was stored as 92,035
    assert cordis.role_record(_row(orgs="2")).contribution == 46017.5


def test_the_division_covers_organisations_and_projects_together():
    assert cordis.role_record(_row(amount="300", orgs="3", projects="2")).contribution == 50.0


def test_a_row_without_the_counts_is_read_as_before():
    row = _row()
    del row["orgs"], row["projects"]
    assert cordis.role_record(row).contribution == 92035.0
    assert cordis.role_record(_row(orgs="x", projects="")).contribution == 92035.0


def test_the_node_with_a_description_wins_over_a_bare_reference():
    rec = cordis.role_record(_row(org="fa66", real_org="089d", orgs="2"))
    assert rec.org_key == "089d"
    assert cordis.role_record(_row(org="fa66", real_org="")).org_key == "fa66"


def test_a_stated_zero_is_still_zero_and_a_third_party_zero_still_unknown():
    assert cordis.role_record(_row(amount="0", orgs="2")).contribution == 0
    r = cordis.role_record(_row(amount="0", role="thirdParty", orgs="2"))
    assert r.contribution is None and r.note == "linked_third_party"


def test_the_roles_query_counts_what_it_multiplies_and_the_repair_query_finds_them():
    text = cordis._query("roles", "", 10)
    assert "COUNT(DISTINCT ?o) AS ?orgs" in text and "COUNT(DISTINCT ?p) AS ?projects" in text
    assert "AS ?real_org" in text
    multi = cordis.multiple_roles_query()
    assert "HAVING" in multi and "COUNT(DISTINCT ?o) > 1" in multi
    for forbidden in ("abstract", "keyword", "objective"):
        assert forbidden not in multi
