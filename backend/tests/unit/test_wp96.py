"""WP-96 (persona round of 23 October 2026, A2): entities, counts and links, the pure parts."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from dgate.awards import read_award
from dgate.buyer_family import family_of
from dgate.normalise import _country2, _paris_wall_time, from_ezamowienia, normalise_org_name
from dgate.ops.buyer_families import Group, Member, twin_groups
from dgate.ops.company_groups import group_of
from dgate.ops.supplier_dedupe import Row, core_key, plan, stated_key
from dgate.sources import de_bkms
from dgate.stats import month_gaps
from dgate.supplier_identity import company_number, piva_valid, stated_country_check, vat_country

# ------------------------------------------------------------------ 1. supplier duplicates

def test_a_swedish_vat_number_is_the_organisation_number():
    assert company_number("556036-0793", "SE") == company_number("SE556036079301", "SE") == "5560360793"
    assert company_number("SE556036079301", "DE") != "5560360793"       # only Swedish numbers


def test_italian_numbers_are_checked_by_their_check_digit():
    assert piva_valid("00881841001") and piva_valid("00401990585")      # Leonardo's partita IVA and codice fiscale
    assert not piva_valid("00881841002") and not piva_valid("12345") and not piva_valid("00000000000")


def row(i, name, country="DE", numbers=(), awards=1, public=False, stated=None, forms=None):
    from dgate.resolution.names import legal_form_of
    return Row(i, country, name, set(numbers), forms if forms is not None else ({legal_form_of(name)} - {None}),
               awards, public, stated or {})


def test_the_persona_duplicates_are_grouped_and_the_conflicts_left_alone():
    rows = [
        row(1, "Saab AB", "SE", {"5560360793"}, 30), row(2, "SAAB Aktiebolag", "SE", {"5560360793"}, 5),
        row(3, "Rheinmetall Landsysteme GmbH", numbers={"HRB1234"}, awards=18),
        row(4, "Rheinmetall Land Systeme GmbH", awards=2),
        row(5, "RheinmetallMAN Military Vehicles GmbH", awards=3), row(6, "Rheinmetall MAN Military Vehicles GmbH"),
        row(7, "Thales Deutschland GmbH", numbers={"811168413"}, awards=10), row(8, "Thales Deutschland GmbH", awards=7),
        # three Rheinmetall Electronics with two VAT numbers: left alone (and the third with them)
        row(9, "Rheinmetall Electronics GmbH", numbers={"119356818"}, awards=29),
        row(10, "Rheinmetall Electronics GmbH", numbers={"251121155"}, awards=4), row(11, "Rheinmetall Electronics GmbH"),
        row(12, "RENK AG", awards=4), row(13, "RENK GmbH", awards=2),                      # two legal forms
        row(14, "KNDS Cbrn GmbH", numbers={"HRB55"}), row(15, "KNDS Crbn GmbH", numbers={"HRB55"}),   # one number
        row(16, "Bundesamt fuer Ausruestung", public=True), row(17, "Bundesamt fuer Ausruestung", public=True),
    ]
    groups, left, _ = plan(rows)
    got = {g["head"]: sorted((m, method) for m, method, _ in g["members"]) for g in groups}
    assert got[1] == [(2, "company_number")]
    assert got[3] == [(4, "name_key_spaces")]
    assert got[5] == [(6, "name_key_spaces")]
    assert got[7] == [(8, "name_key")]
    assert got[14] == [(15, "company_number")]
    assert not {9, 10, 11, 12, 13, 16, 17} & {i for g in groups for i in [g["head"], *(m for m, _, _ in g["members"])]}
    assert left["different_company_numbers"] == 1 and left["different_legal_forms"] == 1
    assert core_key("SAAB Aktiebolag") == "saab" and core_key("KNDS Deutschland GmbH & Co. KG") == "knds deutschland"


def test_two_italian_numbers_merge_only_when_one_stated_name_carries_both():
    a = row(1, "Leonardo S.p.A.", "IT", {"00881841001"}, 4, stated={stated_key("LEONARDO SPA"): {"00881841001"}})
    b = row(2, "Leonardo", "IT", {"00401990585"}, 6, stated={stated_key("Leonardo"): {"00401990585"}})
    groups, left, waiting = plan([a, b])
    assert not groups and left == {"different_company_numbers": 1} and len(waiting) == 1
    a.stated[stated_key("Leonardo S.p.A.")] = {"00881841001"}
    b.stated[stated_key("LEONARDO SPA")] = {"00401990585"}       # the same stated name with each number
    groups, left, waiting = plan([a, b])
    assert [(g["head"], g["members"]) for g in groups] == [(2, [(1, "it_tax_pair", 0.90)])]


def test_the_curated_groups_take_named_subsidiaries_and_the_parent_only_at_home():
    assert group_of("Rheinmetall Electronics GmbH", "DE")[0].key == "rheinmetall"
    assert group_of("RheinmetallMAN Military Vehicles", "AT")[0].key == "rheinmetall"
    assert group_of("Leonardo S.p.A.", "IT")[0].key == "leonardo"
    assert group_of("LEONARDO Germany GmbH", "DE")[0].key == "leonardo"
    assert group_of("Leonardo S.L.", "ES") is None                          # a namesake abroad
    assert group_of("SAAB Aktiebolag", "SE")[0].key == "saab"
    assert group_of("Mesko S.A.", "PL")[0].key == "pgz" and group_of("PIT-RADWAR S.A.", "PL")[0].key == "pgz"
    assert group_of("WB Electronics S.A.", "PL") is None                     # private, not PGZ


# ------------------------------------------------------------------ 2. buyer families

def fam(country, name):
    return family_of(country, normalise_org_name(name))


def test_the_dutch_ministry_and_its_units_are_one_buyer():
    keys = {fam("NL", n).key for n in ("Ministerie van Defensie", "Ministry of Defence (MoD)",
                                       "Ministry of Defense of the Netherlands", "Defensie Materieel Organisatie",
                                       "Defence Materiel Organisation (DMO)", "DMO", "Commando DienstenCentra (CDC)",
                                       "DOSCO", "Koninklijke Marine")}
    assert keys == {"NL:rule:nl_defensie"}
    assert fam("GB", "Ministry of Defence").key != "NL:rule:nl_defensie"          # one country only


def test_dash_prefix_seat_abbreviation_and_typo_variants_are_one_buyer():
    pl = {fam("PL", n).key for n in ("1 Regionalna Baza Logistyczna", "1 Regionalna Baza Logistyczna w Wałczu",
                                     "Skarb Państwa - 1 Regionalna Baza Logistyczna",
                                     "Skarb Państwa – 1 Regionalna Baza Logistyczna w Wałczu")}
    assert pl == {"PL:1 regionalna baza logistyczna"}
    assert fam("PL", "2 Regionalna Baza Logistyczna").key != "PL:1 regionalna baza logistyczna"
    assert fam("DE", "Staatl. Hochbauamt Schwäbisch Hall").key == fam("DE", "Staatliches Hochbauamt Schwäbisch Hall").key
    assert fam("DE", "Beschafffungsamt des BMI").key == fam("DE", "Beschaffungsamt des BMI").key
    assert fam("DE", "Schifffahrtsamt").key == "DE:schifffahrtsamt"              # a real triple f stays
    assert {fam("ES", n).key for n in ("Jaemale", "Jae Male", "JAE MALE")} == {"ES:rule:jae_male"}
    assert fam("PL", "Skarb Państwa - 1 Regionalna Baza Logistyczna").method == "spelling_variant"


def test_a_national_copy_follows_its_ted_twins_buyer_family():
    buyers = {i: Member(i, f"b{i}", n, "x", 0.9) for i, n in ((10, 50), (11, 5), (20, 9), (21, 3), (30, 1))}
    named = [Group("NL:rule:x", buyers[10], [Member(11, "b11", 5, "rule:x", 0.9)])]
    # 20's copies are TED notices of 11 (a member of 10's family); 21's twin is 30, which no rule placed; 10 itself
    # (a head) never moves
    added = twin_groups(named, [(20, 11), (20, 11), (21, 30), (10, 30)], buyers)
    assert [m.org_id for m in named[0].members] == [11, 20] and named[0].members[1].method == "twin_notice"
    assert [(g.head.org_id, [m.org_id for m in g.members]) for g in added] == [(30, [21])]


# ------------------------------------------------------------------ 4. supplier countries

def test_a_winner_country_its_own_name_or_number_contradicts_is_corrected():
    assert stated_country_check("LEONARDO Germany GmbH", "HRB17453", "SE") == ("DE", "name")
    assert stated_country_check("Saab Finland Oy", None, "SE") == ("FI", "name")
    assert stated_country_check("Rheinmetall Canada Inc.", None, "SE") == ("CA", "name")
    assert stated_country_check("KNDS Ammo France", None, "LU") == ("FR", "name")
    assert stated_country_check("Indra Avitech GmbH", None, "ES") == ("DE", "legal_form")
    assert stated_country_check("Indra Avitech GmbH", None, "ES", ("ES", "AT")) == ("AT", "legal_form_notice")
    assert stated_country_check("Rheinmetall Expal Munition S.A.", None, "LV", ("LV", "ES")) == ("ES", "legal_form_notice")
    assert stated_country_check("Rheinmetall Expal Munition S.A.", None, "LV") == ("LV", None)   # nothing decides
    assert stated_country_check("Hensoldt Sensors GmbH", "DE811168413", "LT") == ("DE", "identifier")
    # a parent's VAT number on a subsidiary its name and legal form place elsewhere does not move it (27 Oct 2026)
    assert stated_country_check("Saab Finland Oy", "SE556036079301", "FI") == ("FI", None)
    assert stated_country_check("Elbit Systems Sweden AB", None, "IL") == ("SE", "name")
    assert stated_country_check("Thales Nederland B.V.", None, "NL") == ("NL", None)
    assert stated_country_check("Canada Dry Spain S.L.", None, "ES") == ("ES", None)
    assert vat_country("EL094444763") == "GR" and vat_country("HRB 1234") is None
    assert _country2("UK") == "GB" and _country2("GBR") == "GB"


def test_the_award_loader_files_a_winner_under_its_own_country():
    rec = {"winner-name": {"eng": ["Saab AB", "Saab Finland Oy"]},
           "organisation-name-tenderer": {"eng": ["Saab AB", "Saab Finland Oy"]},
           "organisation-country-tenderer": ["SWE"]}
    got = read_award(rec)
    assert [(w.name, w.country) for w in got.winners] == [("Saab AB", "SE"), ("Saab Finland Oy", "FI")]
    assert got.counts["country_corrected_name"] == 1


# ------------------------------------------------------------------ 5. links

def test_the_polish_bulletin_links_the_notice_page_that_answers():
    opp = from_ezamowienia({"bzpNumber": "2026/BZP 00499054", "noticeNumber": "2026/BZP 00499054/01",
                            "objectId": "08df2f67-7a50-647b-701a-d0000164b0a2", "noticeType": "ContractNotice",
                            "organizationName": "34 Wojskowy Oddzial Gospodarczy", "orderObject": "Remont"})
    assert opp.source_url == ("https://ezamowienia.gov.pl/mo-client-board/bzp/notice-details/id/"
                              "08df2f67-7a50-647b-701a-d0000164b0a2")


def test_a_german_notice_page_is_built_from_an_eforms_notice_id_only():
    assert de_bkms.notice_page("129F4D26-440E-4017-91B5-DF3A10CF3F30").endswith(
        "noticeId=129f4d26-440e-4017-91b5-df3a10cf3f30")
    assert de_bkms.notice_page("1234567") is None and de_bkms.notice_page(None) is None


# ------------------------------------------------------------------ 6. BOAMP deadlines

def test_a_paris_offset_is_read_as_paris_wall_time_on_the_day():
    summer_offset = timezone(timedelta(hours=2))
    got = _paris_wall_time(datetime(2026, 11, 19, 12, 0, tzinfo=summer_offset))
    assert got.astimezone(timezone.utc) == datetime(2026, 11, 19, 11, 0, tzinfo=timezone.utc)   # BOAMP: 12h00
    july = _paris_wall_time(datetime(2026, 7, 9, 12, 0, tzinfo=timezone(timedelta(hours=1))))
    assert july.astimezone(timezone.utc) == datetime(2026, 7, 9, 10, 0, tzinfo=timezone.utc)
    utc = datetime(2026, 11, 19, 12, 0, tzinfo=timezone.utc)
    assert _paris_wall_time(utc) is utc                                       # Z is the notice's own
    reunion = datetime(2026, 11, 19, 12, 0, tzinfo=timezone(timedelta(hours=4)))
    assert _paris_wall_time(reunion) is reunion
    assert _paris_wall_time(datetime(2026, 11, 19, 12, 0, tzinfo=summer_offset)).tzinfo == ZoneInfo("Europe/Paris")


# ------------------------------------------------------------------ 7. numbers

def test_the_seed_folder_is_found_and_can_be_set(monkeypatch, tmp_path):
    from dgate import config, pipeline

    assert (pipeline.seeds_dir() / "defence_buyers.csv").exists()
    monkeypatch.setenv("DGATE_SEEDS_DIR", str(tmp_path))
    config.reset_cache()
    try:
        assert pipeline.seeds_dir() == tmp_path
    finally:
        monkeypatch.delenv("DGATE_SEEDS_DIR")
        config.reset_cache()


def test_the_person_rejected_latvian_agency_is_read_from_the_seeds():
    from dgate.ops.buyer_cleanup import rejected_names

    assert ("LV", "nodrosinajuma valsts agentura") in rejected_names()


def test_the_usual_month_is_that_of_the_last_twelve_whole_months():
    per_month = {f"{y}-{m:02d}": 5 for y in range(2015, 2025) for m in range(1, 13)}
    per_month.update({f"2025-{m:02d}": 1000 for m in range(1, 13)})
    per_month.update({f"2026-{m:02d}": 1100 for m in range(1, 11)})
    median, gaps = month_gaps(per_month)
    assert median == 1100                     # it was 5: ten thin years outweighed the current one
    assert gaps[0] == "2015-02" and "2025-01" not in gaps
