"""The Spanish subsidy register: which calls matter, and what they map to.

Fixtures are the shapes the register returned on 6 October 2026: a CDTI call open to
companies, an INTA scholarship for natural persons, a direct grant, and a search row.
The register holds 52,744 calls registered this year, and what this connector has to
get right is mostly what it must *not* keep.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from dgate.normalise import from_bdns, strip_personal_data
from dgate.sources import bdns

TODAY = date(2026, 10, 6)

CDTI = {
    "id": 1114148, "codigoBDNS": "912587",
    "organo": {"nivel1": "ESTADO", "nivel2": "MINISTERIO DE CIENCIA, INNOVACIÓN Y UNIVERSIDADES",
               "nivel3": "CENTRO PARA EL DESARROLLO TECNOLÓGICO Y LA INNOVACIÓN E.P.E."},
    "sedeElectronica": "https://sede.cdti.gob.es/AreaPublica/home.aspx",
    "fechaRecepcion": "2026-06-12",
    "instrumentos": [{"descripcion": "SUBVENCIÓN Y ENTREGA DINERARIA SIN CONTRAPRESTACIÓN "}],
    "tipoConvocatoria": "Concurrencia competitiva - canónica",
    "presupuestoTotal": 5000000,
    "descripcion": "Resolución de 11 de junio de 2026 de la Dirección General del CDTI por la que "
                   "se aprueba la convocatoria de ayudas a proyectos de I+D de   defensa y dual",
    "tiposBeneficiarios": [{"descripcion": "GRAN EMPRESA"},
                           {"descripcion": "PYME Y PERSONAS FÍSICAS QUE DESARROLLAN ACTIVIDAD ECONÓMICA"}],
    "sectores": [{"descripcion": "Investigación y desarrollo", "codigo": "72"}],
    "regiones": [{"descripcion": "ES - ESPAÑA "}],
    "descripcionFinalidad": "Investigación, desarrollo e innovación",
    "descripcionBasesReguladoras": "Ley 14/2011, de 1 de junio, de la Ciencia.",
    "urlBasesReguladoras": "https://www.boe.es/buscar/act.php?id=BOE-A-2011-9617",
    "abierto": True,
    "fechaInicioSolicitud": "2026-06-18", "fechaFinSolicitud": "2026-10-23",
    "textInicio": None, "textFin": None,
    "ayudaEstado": "SA.123966", "urlAyudaEstado": "https://competition-cases.ec.europa.eu/cases/SA.123966",
    "fondos": [], "reglamento": {"descripcion": "REG (UE) 651/2014"},
    "documentos": [{"id": 1, "nombreFic": "Convocatoria.pdf"}],
    "sePublicaDiarioOficial": True,
}

INTA_SCHOLARSHIP = {
    **CDTI, "codigoBDNS": "894036",
    "organo": {"nivel1": "ESTADO", "nivel2": "MINISTERIO DE DEFENSA",
               "nivel3": "INSTITUTO NACIONAL DE TÉCNICA AEROESPACIAL ESTEBAN TERRADAS (INTA)"},
    "descripcion": "Resolución por la que se convocan becas de formación del INTA",
    "tiposBeneficiarios": [{"descripcion": "PERSONAS FÍSICAS QUE NO DESARROLLAN ACTIVIDAD ECONÓMICA"}],
    "abierto": False, "fechaInicioSolicitud": None, "fechaFinSolicitud": None,
    "textInicio": "Desde el día siguiente a la publicación del Extracto en BOE",
    "textFin": "15 días hábiles a contar desde el siguiente a la publicación",
}

DEFENCE_BODY_CALL = {
    **CDTI, "codigoBDNS": "900001",
    "organo": {"nivel1": "ESTADO", "nivel2": "MINISTERIO DE DEFENSA",
               "nivel3": "DIRECCIÓN GENERAL DE ARMAMENTO Y MATERIAL"},
    "descripcion": "Orden por la que se convocan ayudas a la industria",
}

SEARCH_ROW = {"id": 1, "numeroConvocatoria": "912587", "descripcion": "Resolución del CDTI",
              "fechaRecepcion": "2026-06-12", "nivel1": "ESTADO",
              "nivel2": "MINISTERIO DE CIENCIA, INNOVACIÓN Y UNIVERSIDADES",
              "nivel3": "CENTRO PARA EL DESARROLLO TECNOLÓGICO Y LA INNOVACIÓN E.P.E."}


# ----------------------------------------------------------- the query

def test_the_register_wants_its_own_date_format():
    """ISO dates are silently ignored and the whole register comes back. Measured on
    6 October 2026: `fechaDesde=2026-01-01` returned no total at all."""
    params = bdns.search_params(date(2026, 1, 5), 3)
    assert params["fechaDesde"] == "05/01/2026"
    assert params["tipoAdministracion"] == "C" and params["page"] == 3


class _Response:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


class _Client:
    def __init__(self, pages):
        self.pages, self.asked = pages, []

    def get(self, url, params=None, timeout=None):
        self.asked.append(dict(params))
        return _Response(self.pages[params["page"]])


@pytest.fixture(autouse=True)
def no_pause(monkeypatch):
    monkeypatch.setattr(bdns, "REQUEST_PAUSE", 0.0)


def test_search_walks_every_page_to_the_last():
    client = _Client([{"content": [{"numeroConvocatoria": "1"}, {"numeroConvocatoria": "2"}], "last": False},
                      {"content": [{"numeroConvocatoria": "3"}], "last": True}])
    got = list(bdns.search_central(date(2026, 1, 1), client=client))
    assert [r["numeroConvocatoria"] for r in got] == ["1", "2", "3"]
    assert [c["page"] for c in client.asked] == [0, 1]


def test_a_window_that_never_reaches_its_last_page_is_an_error_not_a_smaller_window():
    pages = [{"content": [{"numeroConvocatoria": str(i)}], "last": False} for i in range(5)]
    with pytest.raises(RuntimeError, match="cut short"):
        list(bdns.search_central(date(2026, 1, 1), client=_Client(pages), max_pages=3))


def test_a_reply_that_is_not_a_page_of_calls_is_refused():
    with pytest.raises(ValueError, match="shape changed"):
        list(bdns.search_central(date(2026, 1, 1), client=_Client([{"error": "x"}])))


# ----------------------------------------------------------- relevance

def test_a_body_that_funds_company_rd_is_a_candidate():
    assert bdns.is_candidate(SEARCH_ROW)


def test_a_call_about_defence_from_any_body_is_a_candidate_on_its_words():
    row = {"nivel2": "MINISTERIO DE INDUSTRIA Y TURISMO", "nivel3": "DG DE INDUSTRIA",
           "descripcion": "Ayudas a la industria aeroespacial y de defensa"}
    assert bdns.is_candidate(row)


def test_a_call_from_an_unrelated_body_is_not():
    row = {"nivel2": "MINISTERIO DE CULTURA", "nivel3": "DG DEL LIBRO",
           "descripcion": "Ayudas a la edición de libros"}
    assert not bdns.is_candidate(row)


def test_the_candidate_test_reads_the_body_from_a_search_row_or_a_detail_record():
    assert bdns.organ_text(SEARCH_ROW) == bdns.organ_text(CDTI)


# --------------------------------------------------------------- scope

def test_a_competitive_call_open_to_companies_is_in_scope():
    assert bdns.in_scope(CDTI, today=TODAY)


def test_a_scholarship_for_natural_persons_is_not_a_call_a_supplier_can_answer():
    """The Ministry of Defence issues it and INTA's name is in the body text, and it
    is still not for a company. The register says who may apply; the body does not."""
    assert not bdns.in_scope(INTA_SCHOLARSHIP, today=TODAY)


def test_a_direct_grant_is_not_in_scope():
    """`Concesión directa` is a grant to named entities, decided by the administration.
    There is nothing to apply for, so it is not an opportunity."""
    direct = {**CDTI, "tipoConvocatoria": "Concesión directa - canónica"}
    assert not bdns.in_scope(direct, today=TODAY)


def test_a_call_that_closed_in_an_earlier_year_is_not_in_scope():
    old = {**CDTI, "abierto": False, "fechaFinSolicitud": "2025-03-01"}
    assert not bdns.in_scope(old, today=TODAY)


def test_a_call_that_closed_this_year_is_kept_so_the_next_cycle_can_be_predicted():
    closed = {**CDTI, "abierto": False, "fechaFinSolicitud": "2026-03-01"}
    assert bdns.in_scope(closed, today=TODAY)


def test_a_call_from_an_unrelated_body_with_no_defence_words_is_not_in_scope():
    other = {**CDTI, "organo": {"nivel2": "MINISTERIO DE CULTURA", "nivel3": "DG DEL LIBRO"},
             "descripcion": "Ayudas a la edición de libros"}
    assert not bdns.in_scope(other, today=TODAY)


def test_the_regime_follows_the_ministry_not_the_word():
    """CDTI belongs to the Ministry of Science, so its lines are dual-use at best.
    Only the Ministry of Defence's own bodies are `defence`."""
    assert bdns.regime(CDTI) == "dual_use"
    assert bdns.regime(DEFENCE_BODY_CALL) == "defence"
    assert bdns.regime(INTA_SCHOLARSHIP) == "defence"          # INTA is under Defensa


# ------------------------------------------------------------ the dates

def test_the_deadline_is_the_end_of_that_day_in_madrid():
    """The register states a date, and a deadline given as a date is the whole of it.
    Midnight at its start would show the call closed on the last day it is open."""
    closes = bdns.deadline(CDTI)
    assert closes == datetime(2026, 10, 23, 21, 59, 59, tzinfo=UTC)      # 23:59:59 CEST


def test_a_call_with_no_closing_date_has_none_not_a_guess():
    assert bdns.deadline(INTA_SCHOLARSHIP) is None


def test_status_follows_the_registers_own_flag_and_the_opening_date():
    assert bdns.status(CDTI, today=TODAY) == "open"
    assert bdns.status({**CDTI, "abierto": False, "fechaInicioSolicitud": "2026-11-01"},
                       today=TODAY) == "forthcoming"
    assert bdns.status({**CDTI, "abierto": False, "fechaInicioSolicitud": "2026-06-18"},
                       today=TODAY) == "closed"


# ----------------------------------------------------------- the mapping

def test_a_call_maps_completely():
    call = from_bdns(CDTI, today=TODAY)
    assert call.programme_code == "ES-BDNS"
    assert call.native_id == call.topic_code == "912587"
    assert call.country == "ES"
    assert call.issuer == ("MINISTERIO DE CIENCIA, INNOVACIÓN Y UNIVERSIDADES / "
                           "CENTRO PARA EL DESARROLLO TECNOLÓGICO Y LA INNOVACIÓN E.P.E.")
    assert (call.budget, call.budget_scope) == (5_000_000.0, "call")
    assert call.status == "open" and call.regime == "dual_use"
    assert call.opens_at == date(2026, 6, 18)
    assert call.source_url.endswith("/convocatorias/912587")
    assert call.type_of_action.startswith("Concurrencia competitiva")


def test_the_title_is_the_legal_citation_with_its_whitespace_collapsed():
    title = from_bdns(CDTI).title
    assert "  " not in title and title.startswith("Resolución de 11 de junio")


def test_who_may_apply_is_stated_as_a_sentence():
    text = from_bdns(CDTI).eligibility_text
    assert "Beneficiarios: GRAN EMPRESA; PYME" in text
    assert "Finalidad: Investigación, desarrollo e innovación." in text
    assert "Bases reguladoras: Ley 14/2011" in text


def test_the_structured_conditions_keep_the_state_aid_and_the_legal_basis_url():
    cond = from_bdns(CDTI).conditions_raw
    assert cond["state_aid"] == "SA.123966"
    assert cond["legal_basis_url"].startswith("https://www.boe.es/")
    assert cond["beneficiary_types"][0] == "GRAN EMPRESA"
    assert cond["documents"] == ["Convocatoria.pdf"]


def test_a_call_without_a_budget_has_none_and_no_scope():
    call = from_bdns({**CDTI, "presupuestoTotal": None})
    assert (call.budget, call.budget_scope) == (None, None)


def test_a_call_without_a_code_is_refused():
    with pytest.raises(ValueError):
        from_bdns({**CDTI, "codigoBDNS": None, "numeroConvocatoria": None})


def test_an_address_written_into_a_description_is_removed_before_landing():
    """Calls name no persons, but free text sometimes carries an address."""
    detail = {**CDTI, "descripcion": "Información: subvenciones@cdti.es o 91 581 55 00"}
    assert "subvenciones@cdti.es" not in str(strip_personal_data(detail))
