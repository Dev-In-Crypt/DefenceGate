"""The pure parts of the networks read side (WP-28): the sentence on how a participant was recognised, the
validation of list parameters, how an organisation removed on request is named, and what an alias may show."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from dgate.network_api import (
    PHONE_LIKE,
    PROGRAMME_CODE,
    ROLES,
    _codes,
    _role_rank,
    org_ref,
    resolution_note,
)
from dgate.suppress import WITHHELD_NAME


def test_resolution_note_says_how_many_participations_were_matched_each_way():
    note = resolution_note({"pic": 3, "exact_name": 1}, 0.9, "999000001")
    assert note == ("Participations: 3 of 4 matched by its PIC, the participant identification code the source states; "
                    "1 of 4 matched by the same name (ignoring accents, capitals and the legal form) in the same country. "
                    "How sure the least certain match is: 0.90 on a scale to 1 (1 is certain).")


def test_resolution_note_for_one_method_and_for_nothing_held():
    assert resolution_note({"pic": 5}, 1.0, "1").startswith("Participations: all 5 matched by its PIC")
    assert resolution_note({}, None, None) == "No participation is held for this organisation."
    assert resolution_note({"exact_name_ambiguous": 2}, 0.8, None).endswith("The sources give it no PIC, so it was recognised by its name.")
    assert "queued for a person to check" in resolution_note({"exact_name_ambiguous": 2}, 0.8, None)


def test_a_method_without_a_word_is_still_said():
    assert "matched by something new" in resolution_note({"something_new": 1}, None, "9")


def test_list_parameters_are_checked_and_folded():
    assert _codes("de, fr", "country", pattern=__import__("re").compile(r"^[A-Z]{2}$")) == ["DE", "FR"]
    assert _codes("Coordinator,participant", "role", allowed=ROLES, upper=False) == ["coordinator", "participant"]
    assert _codes(None, "role", allowed=ROLES, upper=False) == []
    assert _codes("edf, horizon", "programme", pattern=PROGRAMME_CODE) == ["EDF", "HORIZON"]
    for bad in ("boss", "coordinator,boss"):
        with pytest.raises(HTTPException) as e:
            _codes(bad, "role", allowed=ROLES, upper=False)
        assert e.value.status_code == 422
    with pytest.raises(HTTPException):
        _codes("a b", "programme", pattern=PROGRAMME_CODE)
    with pytest.raises(HTTPException):
        _codes(",".join(["DE"] * 11), "country", max_items=10)


def test_an_organisation_removed_on_request_is_named_so_and_carries_no_link():
    live = {"id": 7, "display_name": "THALES SA", "canonical_name": "thales", "country": "FR", "suppressed": False}
    assert org_ref(live) == {"id": "7", "slug": "7-thales-sa", "name": "THALES SA", "country": "FR"}
    gone = org_ref({**live, "suppressed": True})
    assert gone == {"id": None, "slug": None, "name": WITHHELD_NAME, "country": None}
    assert "THALES" not in str(gone)


def test_an_organisation_name_has_no_address_and_falls_back_to_the_key():
    r = org_ref({"id": 3, "display_name": None, "canonical_name": "acme (mail x@y.example)", "country": "DE"})
    assert "@" not in r["name"] and r["slug"].startswith("3-")


def test_the_slug_of_a_name_without_latin_letters_is_the_id_alone():
    assert org_ref({"id": 9, "display_name": "Київський інститут", "canonical_name": "x", "country": "UA"})["slug"] == "9"


def test_a_name_with_a_telephone_number_is_not_an_alias_to_show():
    for text in ("Alpha tel +49 30 1234 5678", "Ministry (0044) 20 7946 0958", "Contact 12345678"):
        assert PHONE_LIKE.search(text), text
    for text in ("Alpha Systems GmbH", "Project 2020", "Section 7 of 12 Ltd"):
        assert not PHONE_LIKE.search(text), text


def test_role_rank_puts_the_coordinator_first_and_unknown_roles_last():
    assert sorted(["participant", "coordinator", "mystery", "third_party"], key=_role_rank) == [
        "coordinator", "participant", "third_party", "mystery"]
