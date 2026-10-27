"""WP-151: a French buyer keeps one organisation across BOAMP's 2024 eForms switch.

Shapes are those of landed payloads (raw store, October 2026): the older schema's `IDENTITE`, the national
form `FNSimple/organisme`, and eForms with the buyer among the review body and the mediator. Names are of
public bodies only; no contact field.
"""

from __future__ import annotations

import collections
import json

from dgate.normalise import from_boamp, normalise_org_name
from dgate.ops import boamp_buyer_ids as op


def _record(idweb: str, name: str, day: str, body: dict) -> dict:
    return {"idweb": idweb, "id": idweb.replace("-", "_"), "objet": "Travaux", "nomacheteur": name,
            "dateparution": day, "perimetre": "DIRECTIVE-81", "nature": "APPEL_OFFRE", "donnees": json.dumps(body)}


LEGACY = _record("19-182081", "MINARM/DGA/DO/S2A", "2020-01-22", {
    "IDENTITE": {"DENOMINATION": "MINARM/DGA/DO/S2A", "CODE_IDENT_NATIONAL": "15000035400012",
                 "CORRESPONDANT": "Acheteur-négociateur"},
    "OBJET": {"TITRE_MARCHE": "Travaux"}})

FNSIMPLE = _record("26-98956", "SID Sud-Est", "2026-10-13", {"FNSimple": {
    "organisme": {"nomOfficiel": "SID Sud-Est", "typeIdentificationNational": {"siret": ""},
                  "codeIdentificationNational": "13000190200274", "ville": "Lyon", "cp": "69007"}}})


def _eforms(buyer_refs: list[str]) -> dict:
    orgs = [
        {"efac:Company": {"cac:PartyIdentification": {"cbc:ID": {"@schemeName": "organization", "#text": "ORG-0002"}},
                          "cac:PartyName": {"cbc:Name": {"@languageID": "FRA", "#text": "Tribunal administratif"}},
                          "cac:PartyLegalEntity": {"cbc:CompanyID": "17510005600019"}}},
        {"efac:Company": {"cac:PartyIdentification": {"cbc:ID": {"@schemeName": "organization", "#text": "ORG-0003"}},
                          "cac:PartyName": {"cbc:Name": {"@languageID": "FRA", "#text": "Ville de Reims"}},
                          "cac:PartyLegalEntity": {"cbc:CompanyID": "215 104 217 00017"}}},
        {"efac:Company": {"cac:PartyIdentification": {"cbc:ID": "ORG-0004"},
                          "cac:PartyName": {"cbc:Name": {"@languageID": "FRA", "#text": "Grand Reims"}},
                          "cac:PartyLegalEntity": {"cbc:CompanyID": "20005525100016"}}},
    ]
    parties = [{"cac:Party": {"cac:PartyIdentification": {"cbc:ID": ref}}} for ref in buyer_refs]
    return {"EFORMS": {"ContractNotice": {
        "ext:UBLExtensions": {"ext:UBLExtension": {"ext:ExtensionContent": {"efext:EformsExtension": {
            "efac:Organizations": {"efac:Organization": orgs}}}}},
        "cac:ContractingParty": parties[0] if len(parties) == 1 else parties,
        "cac:TenderingTerms": {"cac:AppealTerms": {"cac:AppealReceiverParty": {
            "cac:PartyIdentification": {"cbc:ID": "ORG-0002"}}}}}}}


def test_every_boamp_shape_gives_the_buyers_siret():
    assert from_boamp(LEGACY).buyer_identifier == "15000035400012"
    assert from_boamp(FNSIMPLE).buyer_identifier == "13000190200274"
    eforms = from_boamp(_record("24-21716", "Ville de Reims", "2024-02-22", _eforms(["ORG-0003"])))
    assert eforms.buyer_identifier == "21510421700017"          # the buyer's, not the review body's


def test_a_joint_procurement_or_no_number_gives_none():
    assert from_boamp(_record("24-1", "Ville de Reims", "2024-02-22",
                              _eforms(["ORG-0003", "ORG-0004"]))).buyer_identifier is None
    assert from_boamp(_record("26-2", "X", "2026-10-13", {"FNSimple": {"organisme": {
        "nomOfficiel": "X", "codeIdentificationNational": "N/A"}}})).buyer_identifier is None
    assert from_boamp(_record("15-3", "X", "2015-03-02", {"OBJET": {}})).buyer_identifier is None


def test_html_references_do_not_split_a_name():
    assert normalise_org_name("Département de l&#039;Oise") == normalise_org_name("Département de l'Oise")
    assert normalise_org_name("Ville &amp; Port") == normalise_org_name("Ville & Port")


def _org(i, side, reg=None, name=None):
    return op.Org(i, name or f"org {i}", reg, old=3 if side == "old" else 0, new=2 if side == "new" else 0, notices=5)


def test_plan_pairs_one_to_one_and_leaves_ambiguous_groups_out():
    orgs = {1: _org(1, "old"), 2: _org(2, "new"),                    # SIRET A: one pair
            3: _org(3, "old"), 4: _org(4, "old"), 5: _org(5, "new"),  # SIRET B: one new, two old
            6: _org(6, "new"),                                       # SIRET C: holder 9 holds no BOAMP notice
            7: _org(7, "old"),                                       # SIRET D: alone, attached
            10: _org(10, "old"), 11: _org(11, "new")}                # names only
    ids = {1: "A", 2: "A", 3: "B", 4: "B", 5: "B", 6: "C", 7: "D"}
    idents = {o: collections.Counter({k: 1}) for o, k in ids.items()}
    holders = {"C": op.Org(9, "ted body", "C", 0, 0, 4)}
    names = {10: {"departement de l oise"}, 11: {"departement de l oise", "x"}}
    p = op.plan(orgs, idents, holders, names)
    got = {(x.keep.id, x.absorbed.id, x.method) for x in p["pairs"]}
    assert got == {(1, 2, op.METHOD_ID), (10, 11, op.METHOD_NAME)}
    assert next(x for x in p["pairs"] if x.method == op.METHOD_ID).number == "A"
    reasons = {(m, r) for m, r, _ in p["left"]}
    assert (op.METHOD_ID, "one eForms-era buyer, 2 older ones") in reasons
    assert (op.METHOD_ID, "the number's holder holds no BOAMP notice") in reasons
    assert [(o.id, k) for o, k in p["attach"]] == [(7, "D")]


def test_plan_refuses_two_registered_numbers_and_prefers_the_registered_one():
    orgs = {1: _org(1, "old", reg="X"), 2: _org(2, "new")}
    idents = {1: collections.Counter({"Y": 1}), 2: collections.Counter({"Y": 1})}
    p = op.plan(orgs, idents, {}, {})
    assert p["pairs"] == [] and p["conflicting"] == 1               # org 1 is keyed by X, its registered number
    assert [(o.id, k) for o, k in p["attach"]] == [(2, "Y")]


def test_record_identifier_reads_a_landed_record():
    assert op.record_identifier(json.loads(json.dumps(FNSIMPLE))) == "13000190200274"
