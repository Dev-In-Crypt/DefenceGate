"""WP-12 (15 October 2026): French defence-body vocabulary and the PLACSP notice date.

Every buyer string below is a real one, read from the `organisation` table of the
production database on 15 October 2026 (names only; no notice text, no contact data).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from dgate import buyer_vocab as v
from dgate.normalise import Opportunity
from dgate.ops import remap_source
from dgate.ops.derive_buyers import vocabulary_proposals
from dgate.sources import placsp

from .test_placsp_quality import _notices, _page


def body(name, country="FR", identifier=None):
    return v.defence_body(name, country, identifier)


# ------------------------------------------------------------ French vocabulary

@pytest.mark.parametrize("name", [
    # the infrastructure service (SID): a defence buyer by the owner's decision of 15 Oct
    "SID Sud-Est",
    "SID NORD OUEST",
    "Service d'infrastructure de la défense Sud-Est",
    "ETABLISSEMENT DU SERVICE D'INFRASTRUCTURE DE LA DEFENSE DE METZ",
    "ESID de Brest",
    "Direction d'infrastructure de la défense de Saint-Denis - DID SDS",
    "Direction centrale du service d'infrastructure de la défense",
    "MINARM SGA DCSID SID MED Service achats infrastructure",
    "mindef sga dcsid esid toulon",
    "Etat - Ministère des Armées - Service d'infrastructure de la défense Nord-Ouest",
    # the Ministry under its spellings
    "ministeres des armees",
    "Ministère des armées",
    "MINISTERE DE LA DEFENSE -DCSID-SNIA",
    "Min defense DCSID SNIA",
    "minstere des armees",
    "mindedf sga dcsid esid de toulon sai bam",
    "ETAT MINARM SGA DCSID ESID DE BREST",
    "Défense état-major des armées",
    # service du commissariat, platforms, health supply
    "Plate-forme commissariat Sud-Est",
    "Plate forme commissariat ouest Rennes",
    "PFC Brest",
    "PFAF-CO",
    "Direction des approvisionnements en produits de santé des armées",
    "DAPSA PFAF-S",
    "ema ssa dapsa-pfaf-s",
    "PFAF-SANTE",
    # DIRISI and the numeric directorate, DGA, communication, munitions, energy, fleet
    "Direction interarmées des réseaux d'infrastructure et des systèmes d'information de la défense DIRISI",
    "Commissariat au numérique de défense - CNSO",
    "ECPAD",
    "Etablissement de communication et de production audiovisuelle de la défense",
    "Service interarmées des munitions",
    "Service de l'énergie opérationnelle - centre de soutien technique et administratif",
    "Service de soutien de la flotte",
    "Section technique de l'armée de terre",
    # base support groups
    "GSBDD de Creil",
    "GSBDD_PAU",
    "Direction du commissariat d'outre-mer de Guyane",
    # supervised bodies, supply scope only
    "IGESA",
    "Institution de gestion sociale des armées",
    "ONACVG",
    "Office national des anciens combattants et des victimes de guerre",
])
def test_french_defence_bodies_of_the_ministry_are_recognised(name):
    got = body(name)
    assert got.label, (name, got)
    assert got.confidence >= 0.80, (name, got)


@pytest.mark.parametrize("name,why", [
    ("CEA Commissariat à l'énergie atomique et aux énergies alternatives", None),
    ("Commissariat général au développement durable", None),
    ("Commissariat de police de Marseille", None),
    ("Secrétariat général de la défense et de la sécurité nationale", None),
    ("Institut des hautes études de défense nationale", None),
    ("Paris la Défense", None),
    ("ENEDIS Paris La Défense", None),
    ("Etablissement public Paris Ouest La Défense", None),
    ("EDF direction des achats groupe 20 place de la défense", None),
    ("Cegelec Défense", None),
    ("Fondation de l'Armée du Salut", None),
    ("SIAEP de la région de Vernazobres", None),
    ("SIAE de Toulon", None),
    ("Syndicat mixte de défense et de valorisation forestière", None),
    ("Ville d'Amiens DGA attractivité du territoire", None),
    ("Pole d'interet commun SCA SCB SMS AP-HP", None),
    ("Société Valmy La Défense 82", None),
    # excluded on purpose
    ("Cercle de la base de défense de Toulon", "property_agency"),
    ("Cercle national des armées", "property_agency"),
    ("Centre de transfusion sanguine des armées", "military_healthcare"),
    ("Ministère de l'intérieur et des outre-mer le préfet de la zone de défense et de sécurité sud",
     "security_service"),
])
def test_names_that_are_not_the_armed_forces_buying_are_left_out(name, why):
    got = body(name)
    assert got.label is None or got.confidence < 0.80, (name, got)
    if why:
        assert got.excluded_as == why, (name, got)


def test_the_gendarmerie_is_security_not_defence():
    for name in ("Commandement des écoles de la gendarmerie nationale",
                 "COMMANDEMENT DE LA GENDARMERIE DE GUYANE",
                 "Budget annexe gendarmerie"):
        assert body(name).label is None, name
        assert v.buyer_class_of(name, "FR") == "security", name


def test_an_hospital_of_the_armed_forces_stays_a_hospital():
    name = "Hôpital d'instruction des armées Clermont-Tonnerre"
    assert body(name).label is None
    assert v.buyer_class_of(name, "FR") == "health"


def test_a_defence_service_that_names_health_or_infrastructure_is_not_demoted():
    """DAPSA says "sante" and the SID says "infrastructure": the old exclusions kept both
    out of the buyer list (coverage:X1)."""
    assert body("DAPSA - Direction des approvisionnements en produits de santé des armées").label
    assert body("Etablissement du service d'infrastructure de la défense de Lyon").label
    assert v.buyer_class_of("SID Sud-Est", "FR") == "defence"
    assert v.buyer_class_of("DAPSA", "FR") == "defence"


def test_the_french_rows_do_not_apply_to_other_countries():
    assert body("SID Sud-Est", "DE").label is None
    assert body("PFC Brest", "ES").label is None


def test_a_number_that_belongs_to_the_ministrys_services_names_a_body_the_name_does_not():
    assert body("DID CAYENNE").label            # name rule
    assert body("Direction locale", identifier="13000190200012").label == \
        "defence_infrastructure_service"
    assert body("Direction locale", identifier="13000548100012").label is None   # Pole emploi
    assert body("Direction locale", "DE", identifier="13000190200012").label is None


def test_the_derived_list_proposes_what_the_vocabulary_names():
    proposals = vocabulary_proposals([
        ("FR", "SID Sud-Est", "13000190200123", 5),
        ("FR", "Mairie de Ghisonaccia", "", 9),
        ("FR", "DAPSA", "", 2),
    ])
    assert {p.name for p in proposals} == {"SID Sud-Est", "DAPSA"}
    assert all(p.confidence >= 0.80 for p in proposals)


# --------------------------------------------------------- PLACSP notice date

def _entry(notices: str, status: str = "", updated: str = "2026-10-11T19:54:50+02:00"):
    code = (f"<cbc-place-ext:ContractFolderStatusCode>{status}</cbc-place-ext:ContractFolderStatusCode>"
            if status else "")
    body_ = (f"<entry><id>x</id><title>t</title><updated>{updated}</updated>"
             "<cac-place-ext:ContractFolderStatus><cbc:ContractFolderID>F-1</cbc:ContractFolderID>"
             f"<cac:ProcurementProject><cbc:Name>t</cbc:Name></cac:ProcurementProject>{code}"
             f"{notices}</cac-place-ext:ContractFolderStatus></entry>")
    opps, _ = placsp.parse_feed(_page(body_, None))
    return opps[0]


def test_an_award_only_entry_has_its_own_notice_date_and_no_publication_date():
    o = _entry(_notices(("DOC_FORM", "Perfil del contratante", ["2026-10-11"]),
                        ("DOC_CAN_ADJ", "Perfil del contratante", ["2026-09-18", "2026-09-23"])))
    assert o.published_at is None
    assert (o.notice_date, o.notice_kind) == (date(2026, 10, 11), "formalisation")


def test_an_award_entry_dated_by_its_award():
    o = _entry(_notices(("DOC_CAN_ADJ", "Perfil del contratante", ["2026-09-12"])), status="ADJ")
    assert o.published_at is None
    assert (o.notice_date, o.notice_kind) == (date(2026, 9, 12), "award")


def test_a_folder_with_its_call_keeps_both_dates_apart():
    o = _entry(_notices(("DOC_CN", "Perfil del contratante", ["2026-08-01"]),
                        ("DOC_CAN_ADJ", "Perfil del contratante", ["2026-09-12"])))
    assert o.published_at == date(2026, 8, 1)
    assert (o.notice_date, o.notice_kind) == (date(2026, 9, 12), "award")


def test_an_entry_without_notices_is_dated_by_its_update_stamp_and_status_code():
    o = _entry("", status="ANUL", updated="2026-07-29T07:52:01.243+02:00")
    assert (o.notice_date, o.notice_kind) == (date(2026, 7, 29), "cancellation")
    assert o.published_at is None


def test_a_call_entry_is_a_call():
    o = _entry(_notices(("DOC_CN", "Perfil del contratante", ["2026-08-01"])), status="PUB")
    assert (o.notice_date, o.notice_kind) == (date(2026, 8, 1), "call")


def test_the_notice_date_is_in_the_landed_record_and_round_trips():
    from dgate import db
    o = _entry(_notices(("DOC_CAN_ADJ", "Perfil del contratante", ["2026-09-12"])))
    payload = db.opportunity_payload(o)
    assert payload["notice_date"] == "2026-09-12" and payload["notice_kind"] == "award"
    back = db.opportunity_from_payload(payload)
    assert (back.notice_date, back.notice_kind) == (date(2026, 9, 12), "award")
    # absent while empty: no hash of a record that has none moves
    bare = Opportunity(source_code="es_placsp", native_id="n", buyer_name_raw="b",
                       title_original="t")
    assert "notice_date" not in db.opportunity_payload(bare)
    assert "notice_kind" not in db.opportunity_payload(bare)


# ------------------------------------------------- the stored records (remap)

def _stored(**kw) -> dict:
    from dataclasses import replace

    from dgate import db
    base = Opportunity(source_code="es_placsp", native_id="2026/EA27/1", buyer_name_raw="b",
                       title_original="t", country="ES", status="awarded", status_native="RES",
                       source_updated_at=datetime(2026, 6, 30, 8, 19, 8,
                                                  tzinfo=timezone(timedelta(hours=2))))
    return db.opportunity_payload(replace(base, **kw))


def test_the_stored_record_gets_its_notice_date_from_its_update_stamp_and_status():
    new = remap_source.from_placsp_stored(_stored())
    assert (new.notice_date, new.notice_kind) == (date(2026, 6, 30), "award")
    new = remap_source.from_placsp_stored(_stored(status_native="ANUL", status="cancelled"))
    assert new.notice_kind == "cancellation"
    new = remap_source.from_placsp_stored(_stored(status_native="PUB", status="open"))
    assert new.notice_kind == "call"


def test_a_record_that_already_states_its_notice_date_keeps_it():
    new = remap_source.from_placsp_stored(
        _stored(notice_date=date(2026, 6, 28), notice_kind="award"))
    assert (new.notice_date, new.notice_kind) == (date(2026, 6, 28), "award")


def test_a_later_notice_date_on_the_serving_row_is_not_taken_back_by_the_older_record():
    payload = _stored(notice_date=date(2022, 10, 14), notice_kind="award")
    new = remap_source.from_placsp_stored(payload)
    later = {"notice_date": date(2023, 10, 16), "notice_kind": "update"}
    change = remap_source.plan(payload, later, new)
    assert "notice_date" not in change.direct and "notice_kind" not in change.direct
    same_day = {"notice_date": date(2022, 10, 14), "notice_kind": "formalisation"}
    change = remap_source.plan(payload, same_day, new)
    assert "notice_kind" not in change.direct
    earlier = {"notice_date": date(2022, 1, 5), "notice_kind": "call"}
    change = remap_source.plan(payload, earlier, new)
    assert (change.direct["notice_date"], change.direct["notice_kind"]) == (date(2022, 10, 14), "award")


def test_the_notice_date_is_a_tolerated_field_of_the_tender_model():
    from dgate.tenders import Tender
    assert "noticeDate" in Tender.model_fields and "noticeKind" in Tender.model_fields
