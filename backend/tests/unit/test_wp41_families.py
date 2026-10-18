"""WP-41, N5 and N11: which organisation rows are merged, which are shown as one card, and which are kept apart."""

from __future__ import annotations

import pytest

from dgate import org_family
from dgate.ops import org_dedupe
from dgate.resolution.names import fold_key, key_of, legal_form_of

# ----------------------------------------------------------------- legal form (RENK AG / RENK GmbH)

@pytest.mark.parametrize("name,form", [
    ("RENK GmbH", "gmbh"), ("Renk G.m.b.H.", "gmbh"), ("Renk Gesellschaft mit beschraenkter Haftung", "gmbh"),
    ("Renk Aktiengesellschaft", "ag"), ("RENK AG", "ag"), ("RENK GROUP AG", "ag"),
    ("Thales Nederland B.V.", "bv"), ("Thales SA", "sa"), ("THALES S.A.", "sa"), ("Acme Ltd", "ltd"), ("Acme Limited", "ltd"),
    ("SYBILLA TECHNOLOGIES SPOLKA Z OGRANICZONA ODPOWIEDZIALNOSCIA", "zoo"), ("Foo sp. z o.o.", "zoo"),
    ("Airbus Defence and Space GmbH & Co. KG", "gmbh_co_kg"),
])
def test_a_legal_form_is_a_class_and_its_spellings_are_one(name, form):
    assert legal_form_of(name) == form


@pytest.mark.parametrize("name", ["Universite de Lorraine", "CNRS", "Fraunhofer", "Alpha", "SE", "AG"])
def test_a_name_without_a_form_has_none(name):
    assert legal_form_of(name) is None


def test_renk_ag_and_renk_gmbh_share_a_key_but_not_a_form():
    assert key_of("Renk Aktiengesellschaft")[0] == key_of("RENK GmbH")[0] == "renk"
    assert legal_form_of("Renk Aktiengesellschaft") != legal_form_of("RENK GmbH")


def test_fold_removes_every_space():
    assert fold_key("universite du luxembourg") == fold_key("universiteduluxembourg") == "universiteduluxembourg"


# ----------------------------------------------------------------- the merge plan

def row(i, name, *, country="DE", pic=None, reg=None, vat=None, display="same", suppressed=False):
    return {"id": i, "country": country, "canonical": name.lower(), "display": name if display == "same" else display,
            "pic": pic, "reg": reg, "vat": vat, "suppressed": suppressed}


def merge(rows, **kw):
    groups, left = org_dedupe.plan(rows, **kw)
    return [(g.head, [m[0] for m in g.members], [m[1] for m in g.members]) for g in groups], left


def test_case_hyphens_and_legal_form_are_one_key_and_the_row_with_the_pic_is_the_head():
    out, _ = merge([row(1, "fraunhofer-gesellschaft zur forderung der angewandten forschung e v", display=None),
                    row(2, "FRAUNHOFER GESELLSCHAFT ZUR FORDERUNG DER ANGEWANDTEN FORSCHUNG EV", pic="999000001"),
                    row(3, "Fraunhofer Gesellschaft zur Förderung der angewandten Forschung e.V.")])
    assert [(h, sorted(m), k) for h, m, k in out] == [(2, [1, 3], ["name_key", "name_key"])]


def test_a_spacing_difference_merges_a_long_key_with_the_lower_confidence_and_leaves_a_short_one():
    out, _ = merge([row(1, "UNIVERSITE DU LUXEMBOURG", pic="999000002", country="LU"),
                    row(2, "UNIVERSITEDULUXEMBOURG", country="LU")])
    assert out == [(1, [2], ["name_key_spaces"])]
    out, left = merge([row(1, "NORTH WOOD", country="LU"), row(2, "NORTHWOOD", country="LU")])
    assert out == [] and left == {"spacing_on_a_short_key": 1}


def test_two_pics_two_registration_numbers_or_two_vat_numbers_are_never_merged():
    assert merge([row(1, "Aalborg Universitet", pic="999000001"), row(2, "AALBORG UNIVERSITET", pic="999000002")]) == (
        [], {"different_pics": 1})
    assert merge([row(1, "Mairie de Lyon", reg="111"), row(2, "MAIRIE DE LYON", reg="222")]) == (
        [], {"different_registration_numbers": 1})
    assert merge([row(1, "Acme Systems", vat="DE111111111"), row(2, "ACME SYSTEMS", vat="DE222222222")]) == (
        [], {"different_vat_numbers": 1})


def test_one_pic_and_one_matching_number_are_not_a_conflict():
    out, _ = merge([row(1, "Acme Systems", pic="999000001", reg="111"), row(2, "ACME SYSTEMS", reg="111", vat="DE111111111")])
    assert out == [(1, [2], ["name_key"])]


def test_different_legal_forms_are_different_bodies_even_with_one_key():
    # RENK Aktiengesellschaft and RENK GmbH: one supplier on 18 October 2026, probably two legal entities
    assert merge([row(1, "Renk Aktiengesellschaft"), row(2, "RENK GmbH")]) == ([], {"different_legal_forms": 1})


def test_a_form_the_alias_list_shows_counts_even_when_the_display_name_has_none():
    forms = {1: {"ag"}}
    assert merge([row(1, "Renk", display="Renk"), row(2, "RENK GmbH")], forms=forms) == ([], {"different_legal_forms": 1})


def test_the_same_name_in_two_countries_is_never_a_group():
    assert merge([row(1, "Politecnico di Torino", country="IT"), row(2, "POLITECNICO DI TORINO", country="CH")]) == ([], {})


def test_a_row_removed_on_request_stops_its_group():
    out, left = merge([row(1, "Acme Systems"), row(2, "ACME SYSTEMS", suppressed=True)])
    assert out == [] and left == {"suppressed": 1}


def test_only_groups_that_touch_a_project_are_merged():
    rows = [row(1, "Mairie de Lyon"), row(2, "MAIRIE DE LYON"), row(3, "Acme Systems"), row(4, "ACME SYSTEMS")]
    out, _ = merge(rows, focus={4})
    assert [g[0] for g in out] == [3]


def test_a_name_too_short_or_numeric_is_not_a_key():
    assert merge([row(1, "AB"), row(2, "ab")]) == ([], {})
    assert merge([row(1, "12345"), row(2, "12345 ")]) == ([], {})


# ----------------------------------------------------------------- the family layer

def node(i, name, *, country="DE", projects=0, pic=None, reg=None, vat=None, display=None):
    return {"id": i, "country": country, "key": key_of(name)[0], "display": display or name, "name": name, "pic": pic,
            "reg": reg, "vat": vat, "projects": projects}


def fam(nodes, pairs):
    return org_family.build({n["id"]: n for n in nodes}, [org_family.Pair(*p) for p in pairs])


def test_name_variants_become_a_star_around_the_biggest_row():
    nodes = [node(1, "Fraunhofer Gesellschaft", projects=2727, pic="999000001"), node(2, "Fraunhofer-Gesellschaft e V Muenchen", projects=8),
             node(3, "Fraunhofer Gesellschaft Institut", projects=1), node(4, "Fraunhofer Gesellschaft Zentrale", projects=1)]
    out, seen = fam(nodes, [(1, 2, "trigram", 0.91), (1, 3, "trigram", 0.88), (1, 4, "trigram", 0.86)])
    assert out == {2: (1, "name_variant", 0.91), 3: (1, "name_variant", 0.88), 4: (1, "name_variant", 0.86)}
    assert seen == {"accepted": 3}


def test_a_chain_never_makes_two_rows_that_are_not_alike_one_family():
    nodes = [node(1, "Alpha Research Institute", projects=10), node(2, "Alpha Research Institut Berlin", projects=5),
             node(3, "Alpha Research Institut Berlin Mitte", projects=1)]
    out, _ = fam(nodes, [(1, 2, "trigram", 0.9), (2, 3, "trigram", 0.9)])
    assert out == {2: (1, "name_variant", 0.9)}            # 3 is alike 2 only, and 2 is a member: 3 stays alone


def test_a_row_is_a_head_or_a_member_never_both():
    nodes = [node(i, f"Beta Institute Number {n}", projects=p) for i, n, p in ((1, "one", 9), (2, "two", 8), (3, "three", 7), (4, "four", 6))]
    out, _ = fam(nodes, [(1, 2, "trigram", 0.9), (2, 3, "trigram", 0.9), (3, 4, "trigram", 0.9), (1, 4, "trigram", 0.9)])
    assert set(out.values()) and not (set(out) & {h for h, _, _ in out.values()})


def test_different_pics_veto_a_trigram_pair_but_not_the_same_name():
    nodes = [node(1, "Nantes Universite", projects=71, pic="999000001"), node(2, "Universite de Nantes", projects=22, pic="999000002")]
    out, seen = fam(nodes, [(1, 2, "trigram", 0.9)])
    assert out == {} and seen == {"vetoed_pic": 1}
    # AP-HP: one name under several PICs is a family of its own kind, at the confidence the cascade stored
    aphp = [node(1, "Assistance Publique Hopitaux de Paris", projects=40, pic="999000001"),
            node(2, "ASSISTANCE PUBLIQUE - HOPITAUX DE PARIS", projects=3, pic="999000002")]
    out, _ = fam(aphp, [(1, 2, "exact_name_ambiguous", 0.8)])
    assert out == {2: (1, "same_name", 0.8)}


def test_a_name_that_is_only_alike_is_not_a_same_name_family():
    nodes = [node(1, "Hopital Alpha", projects=4, pic="999000001"), node(2, "Hopital Alphabet", projects=3, pic="999000002")]
    assert fam(nodes, [(1, 2, "exact_name_ambiguous", 0.8)])[1] == {"vetoed_not_the_same_name": 1}


@pytest.mark.parametrize("a,b,why", [
    (dict(country="DE"), dict(country="AT"), "country"),
    (dict(reg="111"), dict(reg="222"), "registration_number"),
    (dict(vat="DE111111111"), dict(vat="DE222222222"), "vat_number"),
])
def test_other_vetoes(a, b, why):
    x = node(1, "Gamma Analytics Group", projects=3, **a)
    y = node(2, "Gamma Analytics Gruppe", projects=2, **b)
    out, seen = fam([x, y], [(1, 2, "trigram", 0.9)])
    assert out == {} and seen == {f"vetoed_{why}": 1}


def test_renk_ag_and_renk_gmbh_are_not_one_family_and_a_short_name_is_not_either():
    x, y = node(1, "Rheinmetall Aktiengesellschaft", projects=3), node(2, "RHEINMETALL GmbH", projects=2)
    assert fam([x, y], [(1, 2, "trigram", 0.95)])[1] == {"vetoed_legal_form": 1}
    s, t = node(3, "Abc", projects=3), node(4, "Abcd", projects=2)
    assert fam([s, t], [(3, 4, "trigram", 0.9)])[1] == {"vetoed_short_name": 1}


def test_a_pair_with_a_row_outside_the_directory_is_not_counted():
    out, seen = fam([node(1, "Delta Systems Oy", projects=3)], [(1, 99, "trigram", 0.9)])
    assert out == {} and seen == {"outside_the_directory": 1}


def test_confidence_is_the_stored_similarity_within_the_range_of_the_rule():
    out, _ = fam([node(1, "Epsilon Logistics", projects=3), node(2, "Epsilon Logistic", projects=2)], [(1, 2, "trigram", 1.0)])
    assert out[2][2] == 0.99
