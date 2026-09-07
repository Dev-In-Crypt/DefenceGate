"""Tests for classification and normalisation.

Fixtures mirror the shape TED actually returns: multilingual dicts, values
wrapped in lists, ISO dates with timezone suffixes. The point is to catch the
parsing failures that only show up against real payloads.
"""

from datetime import date, datetime, timedelta, timezone

import pytest

from dgate.classify import classify, detects_subcontracting
from dgate.normalise import from_ted, normalise_org_name, strip_personal_data
from dgate.sources.ted import content_hash, defence_query

# ------------------------------------------------------------- fixtures

SPANISH_DEFENCE_NOTICE = {
    "notice-identifier": ["00512345-2026"],
    "notice-title": {"spa": "Suministro de equipos de comunicaciones tacticas",
                     "eng": "Supply of tactical communications equipment"},
    "notice-subtype": ["17"],
    "notice-version": ["03"],
    "buyer-name": {"spa": ["Ministerio de Defensa"]},
    "buyer-country": ["ESP"],
    "official-language": ["spa"],
    "dispatch-date": ["2026-08-14+02:00"],
    "deadline-receipt-tender-date-lot": ["2026-10-02+02:00"],
    "deadline-receipt-tender-time-lot": ["12:00:00+02:00"],
    "classification-cpv": ["35700000", "32500000"],
    "estimated-value-lot": ["4200000"],
    "estimated-value-cur-lot": ["EUR"],
    "legal-basis": ["32009L0081"],
    "description-lot": {"spa": "Acuerdo marco para el suministro y mantenimiento. "
                               "Se admite la subcontratacion parcial."},
    "csecurity-clearance-description-lot": ["Habilitacion de seguridad requerida"],
    "buyer-email": ["contacto@example.es"],
    "buyer-person": ["Juan Perez"],
    "links": ["https://ted.europa.eu/en/notice/-/detail/00512345-2026"],
}

MUNICIPAL_FIRE_NOTICE = {
    "notice-identifier": ["00998877-2026"],
    "notice-title": {"nld": "Levering van brandblussers"},
    "buyer-name": {"nld": ["Gemeente Utrecht"]},
    "buyer-country": ["NLD"],
    "official-language": ["nld"],
    "dispatch-date": ["2026-07-01+02:00"],
    "classification-cpv": ["35110000"],
    "estimated-value-proc": ["45000"],
    "estimated-value-cur-proc": ["EUR"],
    "legal-basis": ["32014L0024"],
}

MINIMAL_NOTICE = {
    "notice-identifier": "00111222-2026",
    "notice-title": "Test",
    "buyer-name": "Some Buyer",
}


# ------------------------------------------------------- classification

def test_strong_signals_stand_alone():
    sig = classify(legal_basis="32009L0081", cpv_codes=[],
                   buyer_is_defence=False)
    assert sig.is_defence and sig.legal_basis and sig.confidence >= 0.90


def test_military_cpv_alone_is_enough():
    sig = classify(legal_basis=None, cpv_codes=["35330000"],
                   buyer_is_defence=False)
    assert sig.is_defence and sig.cpv_military


def test_fire_extinguishers_are_not_defence():
    """The single most important negative case.

    CPV 35110000 sits in division 35 but a municipality buying fire
    extinguishers must not reach a defence feed.
    """
    sig = classify(legal_basis="32014L0024", cpv_codes=["35110000"],
                   buyer_is_defence=False)
    assert not sig.is_defence
    assert sig.cpv_civil_security
    assert sig.confidence < 0.5


def test_civil_cpv_plus_defence_buyer_is_defence():
    sig = classify(legal_basis=None, cpv_codes=["35110000"],
                   buyer_is_defence=True)
    assert sig.is_defence


def test_dual_use_cpv_alone_is_never_enough():
    """Otherwise the feed fills with generic IT contracts."""
    sig = classify(legal_basis=None, cpv_codes=["48000000", "72000000"],
                   buyer_is_defence=False)
    assert not sig.is_defence
    assert sig.cpv_dual_use


def test_clearance_requirement_is_a_strong_signal():
    sig = classify(legal_basis=None, cpv_codes=[], buyer_is_defence=False,
                   security_clearance_text="Clearance required")
    assert sig.is_defence and sig.clearance


def test_nda_alone_counts_as_clearance_signal():
    sig = classify(legal_basis=None, cpv_codes=[], buyer_is_defence=False,
                   nda_required=True)
    assert sig.clearance


def test_signals_are_retained_separately():
    """Storing only the verdict would make the logic untunable."""
    sig = classify(legal_basis="32009L0081", cpv_codes=["35700000"],
                   buyer_is_defence=True, security_clearance_text="yes")
    assert all([sig.legal_basis, sig.cpv_military, sig.buyer, sig.clearance])
    assert sig.confidence == 1.00
    assert len(sig.reasons) >= 3


def test_subcontracting_detected_across_languages():
    assert detects_subcontracting("Se admite la subcontratacion parcial")
    assert detects_subcontracting("Unterauftragsvergabe ist zulaessig")
    assert detects_subcontracting("Dopuszcza sie podwykonawstwo")
    assert detects_subcontracting("subcontractare partiala")
    assert not detects_subcontracting("Levering van brandblussers")
    assert not detects_subcontracting(None, "")


# -------------------------------------------------------- normalisation

def test_spanish_notice_maps_completely():
    o = from_ted(SPANISH_DEFENCE_NOTICE)
    assert o.native_id == "00512345-2026"
    assert o.country == "ES"
    assert o.original_language == "ES"
    assert o.buyer_name_raw == "Ministerio de Defensa"
    assert o.value_amount == 4200000.0
    assert o.value_currency == "EUR"
    assert o.published_at == date(2026, 8, 14)
    # Timezone-aware: the notice states +02:00, so 12:00 local is 10:00 UTC.
    assert o.deadline_at == datetime(2026, 10, 2, 12, 0, tzinfo=timezone(timedelta(hours=2)))
    assert o.deadline_at.astimezone(timezone.utc) == datetime(2026, 10, 2, 10, 0, tzinfo=timezone.utc)
    assert o.cpv_codes == ["35700000", "32500000"]
    assert o.legal_basis == "32009L0081"
    assert o.notice_version == 3
    assert o.security_clearance_required is True


def test_multilingual_title_prefers_original_not_english_only():
    o = from_ted(SPANISH_DEFENCE_NOTICE)
    assert o.title_original  # something was extracted, not empty


def test_value_falls_back_to_procedure_level():
    o = from_ted(MUNICIPAL_FIRE_NOTICE)
    assert o.value_amount == 45000.0
    assert o.value_currency == "EUR"


def test_minimal_notice_does_not_crash():
    o = from_ted(MINIMAL_NOTICE)
    assert o.native_id == "00111222-2026"
    assert o.cpv_codes == []
    assert o.value_amount is None
    assert o.deadline_at is None


def test_missing_identifier_raises():
    with pytest.raises(ValueError):
        from_ted({"notice-title": "no id"})


def test_url_is_constructed_when_absent():
    o = from_ted(MINIMAL_NOTICE)
    assert o.source_url and "00111222-2026" in o.source_url


# ------------------------------------------------------- personal data

def test_personal_data_is_stripped():
    clean = strip_personal_data(SPANISH_DEFENCE_NOTICE)
    assert "buyer-email" not in clean
    assert "buyer-person" not in clean
    assert "notice-title" in clean


def test_no_personal_field_survives_normalisation():
    """The Opportunity dataclass must have no field that could hold a person."""
    o = from_ted(SPANISH_DEFENCE_NOTICE)
    blob = " ".join(str(v) for v in vars(o).values())
    assert "contacto@example.es" not in blob
    assert "Juan Perez" not in blob


# ------------------------------------------------- entity resolution prep

def test_legal_form_stripped_consistently():
    """The core of the alias table: these must all collapse to one key."""
    variants = [
        "INDRA SISTEMAS, S.A.",
        "Indra Sistemas SA",
        "indra sistemas s.a.",
        "Indra Sistemas, S.A.",
    ]
    keys = {normalise_org_name(v) for v in variants}
    assert len(keys) == 1, keys
    assert keys.pop() == "indra sistemas"


def test_accents_folded():
    assert normalise_org_name("Télécom Défense SAS") == "telecom defense"


def test_various_legal_forms():
    assert normalise_org_name("Rheinmetall AG") == "rheinmetall"
    assert normalise_org_name("PGZ Sp. z o.o.") == "pgz"
    assert normalise_org_name("Thales Nederland B.V.") == "thales nederland"
    assert normalise_org_name("Leonardo S.p.A.") == "leonardo"


def test_noise_tokens_only_stripped_on_request():
    assert normalise_org_name("Thales Group") == "thales group"
    assert normalise_org_name("Thales Group", strip_noise=True) == "thales"


def test_parent_and_subsidiary_do_not_collapse():
    """Thales SA and Thales Nederland BV are related, not identical.

    Merging them would corrupt funding attribution.
    """
    assert normalise_org_name("Thales SA") != normalise_org_name("Thales Nederland B.V.")


def test_empty_name_is_safe():
    assert normalise_org_name("") == ""
    assert normalise_org_name(None) == ""


# ------------------------------------------------------------- archive

def test_hash_is_stable_across_key_order():
    """Key ordering must never create a spurious new archive version."""
    a = {"x": 1, "y": [2, 3], "z": {"k": "v"}}
    b = {"z": {"k": "v"}, "y": [2, 3], "x": 1}
    assert content_hash(a) == content_hash(b)


def test_hash_changes_on_real_change():
    a = dict(SPANISH_DEFENCE_NOTICE)
    b = dict(SPANISH_DEFENCE_NOTICE)
    b["deadline-receipt-tender-date-lot"] = ["2026-10-16+02:00"]
    assert content_hash(a) != content_hash(b)


def test_defence_query_covers_all_three_signals():
    q = defence_query(date(2026, 1, 1), date(2026, 1, 31))
    assert "32009L0081" in q
    assert "35*" in q
    assert "csecurity-clearance" in q
    assert "2026-01-01" in q and "2026-01-31" in q


# ------------------------------------------------------- end to end

def test_full_path_spanish_notice():
    raw = strip_personal_data(SPANISH_DEFENCE_NOTICE)
    o = from_ted(raw)
    sig = classify(
        legal_basis=o.legal_basis,
        cpv_codes=o.cpv_codes,
        buyer_is_defence=True,
        security_clearance_text="present" if o.security_clearance_required else None,
    )
    o.is_defence = sig.is_defence
    o.subcontracting_signal = detects_subcontracting(
        SPANISH_DEFENCE_NOTICE["description-lot"]["spa"]
    )
    assert o.is_defence
    assert o.subcontracting_signal
    assert sig.confidence == 1.00


def test_full_path_municipal_notice_is_excluded():
    o = from_ted(MUNICIPAL_FIRE_NOTICE)
    sig = classify(legal_basis=o.legal_basis, cpv_codes=o.cpv_codes,
                   buyer_is_defence=False)
    assert not sig.is_defence
