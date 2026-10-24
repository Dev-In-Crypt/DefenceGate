"""WP-103 (persona round of 24 October 2026): award and value correctness. The evidence quoted is the personas'
(D:/DEFENCEGATE TESTS/ux-oct24: p01, p04, p05, p07, p10)."""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from dgate import award_value as av
from dgate import awards, db
from dgate.api import effective_status
from dgate.classify import classify
from dgate.confidence import confidence, label


def opp(value=None, kind="total", subtype="29", title="Repair", currency="EUR") -> dict:
    return {"value_amount": value, "value_currency": currency if value else None, "value_kind": kind if value else None,
            "notice_subtype": subtype, "title_original": title, "title_en": None}


# ------------------------------------------------------------------------------------------------ value kinds

@pytest.mark.parametrize("title", [
    # the 29 Indra call-offs held as framework ceilings (p07 indra-calloffs-as-ceiling.txt), one of each spelling
    "Expediente 2026/AR46U/00001471E CB Cuarto AM 2024/AR40U/00003743E Servicio de desarrollo de actividades",
    "Expediente 2026/AR46U/00001640E CB 24 JEMANDIZ AM 2022/AR40U/00001640E Servicio de desarrollo",
    "20264007 Sostenimiento de aulas virtuales de tiro (5º Basado AM 202340A1)",
    "20266358 Asistencia técnica para el apoyo logístico al sistema de defensa aérea nacional (15º Basado AM 202363A1)",
    "20º CB en el AM 1640/22 para el Sostenimiento Integral de Equipos Electrónicos de Plataformas Navales",
    "PLURIANUAL 2027.16º CB EN EL AM 1639/22 para el Sostenimiento Integral del MK-92",
    "2027 CB plurianual AM 3743/24 para el desarrollo de actividades de sostenimiento",
    "JEMAN.- Ramo de Armas.- CB Nº2 Acuerdo Marco para mantenimiento y servicio técnico sistemas ópticos",
    'CB 17º ACUERDO MARCO para el "sostenimiento integral de equipos electrónicos de plataformas navales',
    "Basado acuerdo marco exp. 2023/ETSAE0906/00002140E,Servicio de mantenimiento para los centros de simulación",
    "CB EN 24_AM 1388 Mantenimiento de los sistemas electrónicos, ópticos y optrónicos",
    "4º CB Operador Logístico y Servicio Apoyo Administrativo Lote 7 UALSAN en AM 2018_0001",
    "CB5 (AM 1943_24) Servicio de gestión de residuos del punto limpio de la Base Naval de Rota.",
    "Expediente 2022/AR46U/00001889 Quinto CD AM para el sostenimiento integral de chalecos inflables",
])
def test_a_call_off_that_writes_cb_or_basado_apart_from_the_am_is_a_contract(title):
    assert av.kind_of_title(title) == "contract"
    assert av.placsp_kind(None, title) == "contract"


@pytest.mark.parametrize("title, kind", [
    ("Acuerdo Marco para el suministro de medicamentos", "framework"),
    ("202440A1 Acuerdo Marco para la renovación de plataformas y bateas de municionamiento", "framework"),
    ("Rahmenvereinbarong über Facility Services Leistungen an den (Technik-)-Standorten der BDBOS", "framework"),  # 638010-2024
    ("Suministro de cable CB para radios", None),           # "CB" without a framework named is no call-off
    ("Amortiguadores para vehículos", None),
])
def test_the_widened_rule_keeps_frameworks_and_plain_titles(title, kind):
    assert av.kind_of_title(title) == kind


def test_teds_own_field_names_for_the_framework_maximum_and_the_tenders_are_read():
    """p10 ted-verify.json: STRABAG 638010-2024 states only framework-maximum-value-lot 280,000,000; Arquus 38915-2026 states
    framework-maximum-value-lot = result value = tender-value = 2,449,392,735 (a ceiling: shown as such, never summed)."""
    assert av.ted_value({"framework-maximum-value-lot": ["280000000.00"]}, opp(280000000.0)) == (280000000.0, "EUR", "framework")
    rec = {"framework-maximum-value-lot": ["2449392735"], "tender-value": ["2449392735"]}
    assert av.ted_value(rec, opp(2449392735.0)) == (2449392735.0, "EUR", "framework")
    assert av.ted_value({"tender-value": ["5000", "7000"]}, opp(None)) == (12000.0, None, "contract")
    assert "framework-maximum-value-lot" in awards.AWARD_FETCH_FIELDS and "tender-value" in awards.AWARD_FETCH_FIELDS


def test_a_figure_its_own_estimate_contradicts_is_set_aside_and_the_estimate_stands():
    """World Aviation 220199-2026: EUR 7,274,615,930 for one lot estimated at EUR 7,317,073.17 topped the EUR ranking."""
    held = opp(7317073.17, kind="estimated")
    rec = {"BT-161-NoticeResult": "7274615930"}
    assert av.ted_value(rec, held) == (7317073.17, "EUR", "estimate")
    assert av.ted_value_set_aside(rec, held) == 7274615930.0
    # a ceiling contradicted the same way (593313-2026: EUR 6.65 bn over lots of EUR 2.7 m)
    assert av.ted_value({"BT-118-NoticeResult": "6652800000"}, opp(2700000.0, kind="lot_sum"))[2] == "estimate"
    # a large figure the estimate does not contradict stands (419618-2026, PLN 9.3 bn, no estimate held)
    assert av.ted_value({"BT-161-NoticeResult": "9311212000"}, opp(9311212000.0, currency="PLN")) == (
        9311212000.0, "PLN", "contract")
    assert av.ted_value_set_aside({"BT-161-NoticeResult": "9311212000"}, opp(9311212000.0)) is None
    assert not av.contradicted(5e8, held) and not av.contradicted(None, held)


def test_veat_notices_are_result_notices():
    """375694-2026 (VEAT, subtype 25, F.B. Design, EUR 50.8 m) was never read for its winner."""
    assert {"25", "26", "27", "28"} <= set(awards.AWARD_SUBTYPES)


# ------------------------------------------------------------------------------------------------ re-read versions

def test_a_version_after_one_of_the_older_mapping_is_the_mappings():
    old = {"value_amount": 71000.0, "published_at": "2026-09-17"}
    new = {"value_amount": 58677.69, "published_at": "2026-06-23", "source_updated_at": "2026-10-14T11:21:19+02:00",
           "legal_basis": "Ley 24/2011 (defensa y seguridad)"}
    assert db.older_mapping(old, new)
    assert not db.older_mapping({**old, "source_updated_at": "2026-10-01T10:00:00+02:00"}, new)   # both stamped
    assert not db.older_mapping(old, {"value_amount": 1.0})                                       # neither


# ------------------------------------------------------------------------------------------------ classification

def test_ley_24_2011_is_the_defence_directive():
    """/tenders/146480 (p01): "Legal basis: Ley 24/2011 (defensa y seguridad)" was not the directive signal."""
    sig = classify(legal_basis="Ley 24/2011 (defensa y seguridad)", cpv_codes=["34330000"], buyer_is_defence=True,
                   buyer_class="defence")
    assert sig.legal_basis and any("Ley 24/2011" in r for r in sig.reasons)
    assert not classify(legal_basis="Ley 9/2017 (LCSP)", cpv_codes=["34330000"], buyer_is_defence=True).legal_basis


@pytest.mark.parametrize("cls, military, want", [
    ("security", True, "Defence and security directive, security buyer"),    # police rounds (p04), Cyprus police UAVs (p05)
    ("municipal", True, "Defence directive, civil buyer"),
    ("defence", False, "Defence directive, unlisted buyer"),
])
def test_a_directive_notice_is_never_called_a_weak_signal(cls, military, want):
    lv, _ = confidence(legal_basis=True, military_cpv=military, buyer=False, buyer_class=cls)
    got = label(lv, buyer=False, military_cpv=military, legal_basis=True, buyer_class=cls)
    assert got == want and "Weak" not in got
    assert label("low", buyer=False, military_cpv=True) == "Weak defence signal"      # no directive: as before


# ------------------------------------------------------------------------------------------------ stale statuses

NOW = datetime(2026, 10, 24, 12, 0, tzinfo=timezone.utc)


def test_a_planned_notice_without_a_deadline_expires_after_a_year():
    """Planned PINs of 2017-2024 on buyer pages (p03 BAAINBw, p07 91425/200153, p01 buyer 306)."""
    assert effective_status("forthcoming", None, date(2024, 10, 1), NOW) == "expired"
    assert effective_status("forthcoming", None, date(2026, 6, 1), NOW) == "forthcoming"
    assert effective_status("forthcoming", datetime(2027, 1, 1, tzinfo=timezone.utc), date(2024, 1, 1), NOW) == "forthcoming"


def test_an_open_notice_of_a_procedure_without_a_call_and_no_deadline_is_not_open():
    """de_bkms 283577 (p10): "de-comp-wo-call", no deadline, no publication date, served Open."""
    assert effective_status("open", None, None, NOW, procedure="de-comp-wo-call") == "expired"
    assert effective_status("open", None, None, NOW, procedure="de-restricted-w-call") == "open"
    assert effective_status("open", datetime(2026, 11, 1, tzinfo=timezone.utc), None, NOW, procedure="neg-wo-call") == "open"
