"""WP-72, the parts that need no database: the twin rule, the list filters' SQL shape, the German
notice link, and the plan of the merge-candidate acceptance."""

from __future__ import annotations

from pathlib import Path

from dgate import tenders
from dgate.classify import OWN_RELEVANCE_SQL, own_relevance_sql, relevant_on_its_own
from dgate.normalise import from_de_bkms, strip_personal_data
from dgate.ops.accept_merge_candidates import plan

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "de_bkms"


# ------------------------------------------------------------- the twin rule

def test_a_dual_use_twin_is_not_relevant_on_its_own():
    # GDDKiA motorway works: 35710000 among the construction codes, a civil buyer class
    assert not relevant_on_its_own(legal_basis=False, military_cpv=True, dual_use=True,
                                   buyer=False, buyer_class="other")


def test_core_supply_and_the_two_groups_are_relevant_on_their_own():
    assert relevant_on_its_own(legal_basis=True, military_cpv=False, dual_use=False,
                               buyer=False, buyer_class="defence")
    assert relevant_on_its_own(legal_basis=False, military_cpv=True, dual_use=False,
                               buyer=False, buyer_class=None)
    assert relevant_on_its_own(legal_basis=False, military_cpv=False, dual_use=False,
                               buyer=True, buyer_class="other")            # listed buyer: supply
    assert relevant_on_its_own(legal_basis=True, military_cpv=False, dual_use=False,
                               buyer=False, buyer_class="municipal")       # directive_civil_buyer
    assert not relevant_on_its_own(legal_basis=False, military_cpv=False, dual_use=False,
                                   buyer=False, buyer_class=None)          # only a link


def test_the_sql_reads_no_link_and_can_be_written_over_another_alias():
    assert "sig_linked_defence" not in OWN_RELEVANCE_SQL
    t = own_relevance_sql("t")
    assert "t.is_defence" in t and "o." not in t


# ------------------------------------------------------------- list filters

def _filters(**kw):
    a = dict(q=None, country=None, cpv=None, status="all", scope="relevant", goods=None, buyer=None,
             from_=None, to=None, min_=None, max_=None, currency=None)
    a.update(kw)
    return tenders._tender_filters(**a)


def test_one_country_is_a_plain_equality_so_the_country_index_gives_the_order():
    where, params, _ = _filters(country="mt")
    assert "o.country = %s" in where and params == ["MT"]
    where, params, _ = _filters(country="MT,LU")
    assert "o.country = ANY(%s)" in where and params == [["MT", "LU"]]


class _Conn:
    def __init__(self, ids):
        self.ids = ids

    def execute(self, sql, args):
        assert "dgate_family_ids" in sql
        ids = self.ids

        class R:
            def fetchone(self):
                return {"ids": ids}
        return R()


def test_a_buyer_of_one_row_is_an_equality_and_a_family_its_ids():
    where, params, _ = _filters(buyer=196, conn=_Conn([196]))
    assert "o.buyer_org_id = %s" in where and params == [196]
    where, params, _ = _filters(buyer=196, conn=_Conn([900, 196]))
    assert "o.buyer_org_id = ANY(%s)" in where and params == [[196, 900]]
    where, params, _ = _filters(buyer=196)                  # no connection: the old sub-select
    assert any("dgate_family_ids" in w for w in where) and params == [196]


# ------------------------------------------------------------- German notice link

def _record(xml: str) -> dict:
    return {"file": "cn_standard_defence.xml", "notice_id": None, "version": "01", "xml": xml}


DOCS = ("<cac:TenderingTerms><cac:CallForTendersDocumentReference><cbc:ID>1</cbc:ID>"
        "<cac:Attachment><cac:ExternalReference><cbc:URI>{}</cbc:URI></cac:ExternalReference>"
        "</cac:Attachment></cac:CallForTendersDocumentReference>")


def _with_documents(url: str) -> str:
    xml = (FIX / "cn_standard_defence.xml").read_text(encoding="utf-8")
    assert xml.count("<cac:TenderingTerms>") == 1
    return xml.replace("<cac:TenderingTerms>", DOCS.format(url), 1)


def test_the_german_notice_links_to_its_documents_on_the_buyers_platform():
    url = ("https://vergabeplattform.bwi.de/NetServer/TenderingProcedureDetails?"
           "function=_Details&amp;TenderOID=54321-Tender-18c6cdda559-62b24c881b2c9a16")
    opp = from_de_bkms(strip_personal_data(_record(_with_documents(url))))
    assert opp.source_url == url.replace("&amp;", "&")


def test_a_link_that_is_not_http_is_refused():
    opp = from_de_bkms(strip_personal_data(_record(_with_documents("javascript:alert(1)"))))
    assert opp.source_url is None


# ------------------------------------------------------------- merge candidates

def _org(i, reg=None, vat=None, pic=None, notices=0, country="FR", suppressed=False, person=False):
    return {"id": i, "country": country, "name": f"org {i}", "suppressed": suppressed,
            "person": person, "reg": reg, "vat": vat, "pic": pic, "notices": notices}


def _pair(cid, a, b, conf=0.97):
    return {"id": cid, "a": a, "b": b, "confidence": conf, "match_method": "identifier",
            "evidence": f"{a}~{b}"}


def test_an_identifier_pair_is_one_group_headed_by_the_row_with_most_notices():
    orgs = {1: _org(1, reg="21440103600121", notices=2), 2: _org(2, notices=9), 3: _org(3)}
    groups, refused = plan([_pair(10, 1, 2), _pair(11, 1, 3)], orgs)
    assert refused == {}
    assert [(g["head"], g["members"]) for g in groups] == [(2, [1, 3])]
    assert groups[0]["confidence"] == 0.97


def test_anything_that_contradicts_the_identifier_is_refused():
    orgs = {1: _org(1, reg="A"), 2: _org(2, reg="B"), 3: _org(3, country="DE"),
            4: _org(4, suppressed=True), 5: _org(5, person=True), 6: _org(6, vat="FR1"),
            7: _org(7, vat="FR2")}
    groups, refused = plan([_pair(1, 1, 2), _pair(2, 1, 3), _pair(3, 1, 4), _pair(4, 1, 5),
                            _pair(5, 6, 7), _pair(6, 1, 1)], orgs)
    assert groups == []
    assert refused == {"different_reg": 1, "different_countries": 1, "suppressed": 1,
                       "natural_person": 1, "different_vat": 1, "already_one": 1}


def test_a_group_that_joins_two_numbers_through_a_third_row_is_refused_whole():
    # 1 and 3 each agree with 2 (which holds none), but 1 and 3 carry different numbers
    orgs = {1: _org(1, reg="A"), 2: _org(2), 3: _org(3, reg="B")}
    groups, refused = plan([_pair(1, 1, 2), _pair(2, 2, 3)], orgs)
    assert groups == [] and refused == {"group_different_reg": 2}


def test_a_body_acting_for_another_is_not_proved_one_by_the_agents_number():
    orgs = {1: _org(1, reg="53339597600012"), 2: _org(2)}
    orgs[2]["name"] = "cmne de villefontaine repres par sara"
    groups, refused = plan([_pair(1, 1, 2)], orgs)
    assert groups == [] and refused == {"acting_for_another_body": 1}
    orgs[2]["name"] = "sua provincia di cosenza per conto del comune di rende"
    assert plan([_pair(1, 1, 2)], orgs)[1] == {"acting_for_another_body": 1}
    # no such words: accepted (a company: a commune is a public body, refused since WP-74)
    orgs[2]["name"] = "chantiers navals de montoir"
    assert plan([_pair(1, 1, 2)], orgs)[1] == {}
