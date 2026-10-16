"""Buyer families (WP-22): which organisation rows are one body. A wrong group is worse
than none, so every rule has a case that groups and a near neighbour that must not."""

from __future__ import annotations

import pytest

from dgate import worker
from dgate.buyer_family import family_key, family_of
from dgate.ops.buyer_families import groups_of


def same(country, *names):
    keys = {family_key(country, n) for n in names}
    assert len(keys) == 1 and None not in keys, keys


def apart(country, a, b):
    assert family_key(country, a) != family_key(country, b)


def test_the_same_normalised_name_in_the_same_country_is_one_family():
    same("DE", "bundesamt fur infrastruktur umweltschutz und dienstleistungen der bundeswehr",
         "bundesamt fur infrastruktur umweltschutz und dienstleistungen der bundeswehr")
    f = family_of("PL", "jednostka wojskowa nr 6021")
    assert (f.method, f.confidence) == ("identical_name", 0.95)


def test_nothing_is_grouped_across_countries():
    assert family_key("BE", "ministere de la defense") != family_key("FR", "ministere de la defense")
    assert family_key("PL", "baainbw") != family_key("DE", "baainbw")     # a rule is per country


def test_empty_names_and_countries_have_no_family():
    assert family_key("DE", "") is None and family_key("DE", None) is None
    assert family_key("", "baainbw") is None and family_key(None, "baainbw") is None


def test_baainbw_long_short_and_department_names_are_one_family():
    same("DE", "baainbw", "baainbw koblenz", "baainbw g2 1", "baainbw-e3 6",
         "bundesamt fur ausrustung informationstechnik und nutzung der bundeswehr",
         "bundesamt fur ausrustung informationstechnik und nutzung der bundeswehr baainbw",
         "bundesamt fur ausrustung informationstechnik und nutzung der bundeswehr -e1 3- angebotssammelstelle",
         "bundesamt fur ausrustung informationstechnik und nutzung der bundeswehr - s2 2",
         "bundesamt fur ausruestung informationstechnik und nutzung der bundeswehr baainbw",
         "bundesamt fur ausrustung informatonstechnik und nutzung der bundeswehr")   # a typo
    assert family_of("DE", "baainbw").method == "rule:baainbw"
    assert family_of("DE", "baainbw").confidence == 0.90


def test_baainbw_is_not_a_prefix_match_on_other_bundeswehr_bodies():
    for other in ("bundesamt fur infrastruktur umweltschutz und dienstleistungen der bundeswehr",
                  "bundeswehr-dienstleistungszentrum koblenz", "bundesamt fur auswartige angelegenheiten",
                  "baainbwx", "wehrtechnische dienststelle 41"):
        assert family_key("DE", other) != family_key("DE", "baainbw"), other


def test_marinearsenal_sites_are_one_family_and_other_navy_bodies_are_not():
    same("DE", "marinearsenal", "marinearsenal wilhelmshaven", "marinearsenal dienstort rostock",
         "marinearsenal warnowwerft", "marinearsenal wilhelmshaven sachgebiet firmen")
    apart("DE", "marinearsenal", "marinekommando")
    apart("DE", "marinearsenal", "baainbw s2 4 im hause marinearsenal af 911")  # BAAINBw's own desk


def test_hil_and_bwbm_variants():
    same("DE", "hil heeresinstandsetzungslogistik", "heeresinstandsetzungslogistik",
         "hil heeresinstandsetzungslogistk")
    same("DE", "bw bekleidungsmanagement", "bwbm")
    apart("DE", "bw bekleidungsmanagement", "lh bundeswehr bekleidungsgesellschaft")


def test_polish_armament_agency_with_and_without_the_treasury():
    same("PL", "skarb panstwa - agencja uzbrojenia", "agencja uzbrojenia email removed",
         "agencja uzbrojenia")
    same("PL", "skarb panstwa - inspektorat uzbrojenia", "inspektorat uzbrojenia",
         "skarb panstwa-inspektorat uzbrojenia")
    apart("PL", "agencja uzbrojenia", "inspektorat uzbrojenia")      # a rename is not a merge
    apart("PL", "agencja uzbrojenia", "wojskowy instytut techniczny uzbrojenia")
    apart("PL", "agencja uzbrojenia", "agencja mienia wojskowego")


def test_french_ministry_prefix_and_title_suffix_are_stripped():
    same("FR", "minarm dga do s2a", "mindef dga do s2a", "dga do s2a",
         "minarm dga do s2a ministere des armees - direction generale de l armement - "
         "direction des operations - service des achats d armement minarm dga do s2a")
    same("FR", "minarm air siae", "mindef air siae", "minarm air siae ministere des armees")
    same("FR", "minarm terre simmt", "mindef terre simmt")
    assert family_of("FR", "mindef air siae").method == "fr_ministry"


def test_french_sub_units_stay_apart():
    apart("FR", "mindef dga dt scat toulon", "mindef dga dt scat toulouse")
    apart("FR", "mindef dga dt scat toulon", "mindef dga do s2a")      # sub-unit of the DGA, not the S2A
    apart("FR", "mindef air siae aia cf", "mindef air siae")
    apart("FR", "minarm dga do s2a",
          "minarm dga do s2a ministere des armees direction generale de l armement direction "
          "des operations service des achats d armement division achats-sud-est site d istres")
    # a name that only begins with the ministry's title has no service to strip to
    assert family_of("FR", "ministere des armees").method == "identical_name"


def test_offices_that_share_a_pattern_but_not_a_place_stay_apart():
    apart("DE", "bundeswehr-dienstleistungszentrum munster", "bundeswehr-dienstleistungszentrum koln")
    apart("DE", "staatliches bauamt weilheim", "staatliches bauamt schweinfurt")
    apart("DE", "staatliches hochbauamt karlsruhe", "staatliches hochbauamt freiburg")
    apart("GB", "mod commercial team a", "mod commercial team b")


def _rows():
    # (id, country, name, defence notices, registration number)
    return [(1, "DE", "baainbw", 5, None), (2, "DE", "bundesamt fur ausrustung informationstechnik "
            "und nutzung der bundeswehr", 50, "X1"), (3, "DE", "baainbw koblenz", 50, "X2"),
            (4, "DE", "bundeswehr-dienstleistungszentrum koln", 9, None),
            (5, "DE", "bundeswehr-dienstleistungszentrum munster", 9, None),
            (6, "FR", "mindef dga do s2a", 3, None)]


def test_a_group_needs_two_rows_and_the_head_has_the_most_notices_then_the_lowest_id():
    groups = groups_of(_rows())
    assert len(groups) == 1                         # the lone offices and the lone S2A row are no family
    g = groups[0]
    assert g.head.org_id == 2                       # 50 notices, ties broken by the lowest id (2 < 3)
    assert sorted(m.org_id for m in g.members) == [1, 3]
    assert g.notices == 105


def test_the_worker_schedules_the_families_daily_and_can_run_them_by_hand():
    assert "buyer-families" in worker.JOBS
    assert "buyer_families_daily" in {j.id for j in worker.build_scheduler().get_jobs()}
    assert any("buyer_families" in line for line in worker.describe_schedule())


@pytest.mark.parametrize("name", ["baainbw", "marinearsenal", "hil heeresinstandsetzungslogistik"])
def test_rules_do_not_leak_to_another_country(name):
    assert family_of("FR", name).method == "identical_name"


def test_a_row_that_is_only_called_like_a_rule_is_not_in_its_family():
    # "hil" alone is not Heeresinstandsetzungslogistik: it must not share the rule's key
    assert family_key("DE", "hil") != family_key("DE", "hil heeresinstandsetzungslogistik")
    assert family_key("DE", "hil") == "DE:hil"
