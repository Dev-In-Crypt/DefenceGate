"""WP-39, data protection fixes (verify2-abuse N1-N10): the rules that need no database."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from dgate.awards import clean_supplier_name, read_award, stated_number
from dgate.hardening import HeadAsGet, SecurityHeaders, request_cost
from dgate.individuals import individual_reason
from dgate.normalise import looks_like_contact, normalise_identifier
from dgate.sources import edf_factsheets as edf
from tests.pdfmaker import factsheet_pdf, make_pdf

# ------------------------------------------------------------------ N1: contact data is no identifier

@pytest.mark.parametrize("value", ["+49 5827-805314", "+48 566446404", "+49 89-81404707", "andrei@eqqus.ee",
                                   "Tel. 0383 193 494", "tel: +33 1 23 45 67 89", "(Fax) 030 1234567"])
def test_a_telephone_number_or_an_address_is_not_an_identifier(value):
    assert looks_like_contact(value)
    assert normalise_identifier(value, "DE") is None
    assert stated_number(value, "DE") is None


@pytest.mark.parametrize("value,country", [("DE 129 415 943", "DE"), ("NIP: 852-000-06-54", "PL"), ("EE10717064", "EE"),
                                           ("HRB 123456", "DE"), ("FR 12 345678901", "FR"), ("RO 14399840", "RO")])
def test_a_register_or_tax_number_is_still_one(value, country):
    assert not looks_like_contact(value)
    assert normalise_identifier(value, country)
    assert stated_number(value, country) == value


@pytest.mark.parametrize("value", ["Unknown", "BAE Systems (Operations) Ltd", "keine Angabe", "nimat-3", "0000", "xx"])
def test_a_word_in_the_identifier_field_is_not_stored_as_a_number(value):
    assert stated_number(value, "DE") is None


def tender_record(names, countries, idents, winners=None):
    return {"publication-number": "9-2026",
            "winner-name": {"eng": winners or names},
            "organisation-name-tenderer": {"eng": names},
            "organisation-country-tenderer": countries,
            "organisation-identifier-tenderer": idents}


def test_the_reader_drops_a_telephone_number_and_blanks_it_in_the_landed_record():
    rec = tender_record(["Krauss-Maffei Wegmann GmbH", "Eqqus Ltd OU"], ["DEU", "EST"],
                        ["+49 89-81404707", "andrei@eqqus.ee"])
    got = read_award(rec)
    assert [w.identifier for w in got.winners] == [None, None]
    landed = str(got.redacted)
    assert "81404707" not in landed and "eqqus.ee" not in landed and "andrei" not in landed
    assert "Krauss-Maffei Wegmann GmbH" in landed          # the names stay; only the contact data goes
    assert "81404707" in str(rec)                          # and the caller's record was not changed


def test_a_real_number_beside_a_telephone_number_is_kept_in_its_place():
    rec = tender_record(["Alfa Optics S.A.", "Zeta GmbH"], ["FRA", "DEU"], ["FR12345678901", "+49 30 123456"])
    got = read_award(rec)
    assert [w.identifier for w in got.winners] == ["FR12345678901", None]
    assert got.redacted["organisation-identifier-tenderer"] == ["FR12345678901", ""]


# ------------------------------------------------------------------ N8: names that are no supplier

@pytest.mark.parametrize("name,reason", [
    ("keine Angabe", "placeholder"), ("n/a", "placeholder"), ("Unknown", "placeholder"), ("xxx", "placeholder"),
    ("-", "placeholder"), ("K.A.", "placeholder"),
    ("Wojskowe Zak¿ady Uzbrojenia S.A.", "garbled"), ("CafÃ© Defense", "garbled"),
    ("Siuda Sp. z o.o. �", "garbled"),
    ("Lider konsorcjum: BOGMAR sp.k., Partner konsorcjum: JOAN Sp. z o.o.", "consortium_string"),
    ("Konsorcjum w składzie: A Sp. z o.o., B Sp. z o.o.", "consortium_string"),
    ("Groupement BGC", "consortium_string"), ("Consortium 'Cordeel'", "consortium_string"),
    ("Lider: Seris Konsalnet Security Sp. z o.o., Partner: Seris Konsalnet Ochrona Sp. z o.o.", "consortium_string"),
    ("Contact andrei@eqqus.ee Eqqus Ltd", "contact_in_name"), ("Eqqus +372 5551234 Ltd", "contact_in_name"),
])
def test_what_is_no_supplier_is_refused_with_its_reason(name, reason):
    assert clean_supplier_name(name)[0] == reason


@pytest.mark.parametrize("name,kept", [
    ("Stekop Spółka Akcyjna - Lider", "Stekop Spółka Akcyjna"),
    ("Hako Sp. z o.o. -Lider", "Hako Sp. z o.o."),
    ("Lider Konsorcjum - DGP Security Partner Sp. z o.o.", "DGP Security Partner Sp. z o.o."),
    ("Konsorcjum firm: Lider konsorcjum: BAUDZIEDZIC Sp. z o.o. Sp. K.", "BAUDZIEDZIC Sp. z o.o. Sp. K."),
    ("CS GROUP mandataire", "CS GROUP"), ("Lider - WOJSKOWE ZAKŁADY ELEKTRONICZNE S.A.", "WOJSKOWE ZAKŁADY ELEKTRONICZNE S.A."),
    ("KFR Sp. z o.o. – Partner Konsorcjum", "KFR Sp. z o.o."),
])
def test_a_role_note_after_a_single_company_is_removed_and_the_company_kept(name, kept):
    assert clean_supplier_name(name) == (None, kept)


@pytest.mark.parametrize("name", [
    "Rheinmetall Landsysteme GmbH", "Lider Sp. z o.o.", "Partner Fire Protection Ltd", "ÅF Digital Solutions AB",
    "HONOS - SOCIEDADE COMERCIAL DE IMPORTAÇÃO E EXPORTAÇÃO, LDA", "NÅR A/S", "Nammo Raufoss AS",
    "Smith & Sons (Defence) Ltd", "Indra Sistemas, S.A.", "Airbus Defence and Space GmbH",
])
def test_ordinary_suppliers_pass_unchanged(name):
    assert clean_supplier_name(name) == (None, name)


def test_the_reader_counts_what_it_skips_and_keeps_the_cleaned_name():
    rec = tender_record(["keine Angabe", "Hako Sp. z o.o. -Lider", "Lider konsorcjum: A Sp. z o.o., Partner konsorcjum: B Sp. z o.o.",
                         "Nammo Raufoss AS"], ["DEU", "POL", "POL", "NOR"], ["DE0000000", "PL1234567890", "PL2345678901", "NO923456789"])
    got = read_award(rec)
    assert [(w.name, w.country) for w in got.winners] == [("Hako Sp. z o.o.", "PL"), ("Nammo Raufoss AS", "NO")]
    assert got.counts["skipped_placeholder"] == 1 and got.counts["skipped_consortium_string"] == 1
    assert got.winners_seen == 4


# ------------------------------------------------------------------ N2: organisations that are persons

@pytest.mark.parametrize("name,country", [
    ("MIRABILE ANTONIO", "FR"), ("VAN DEN BERGH JOHANNA", "NL"), ("TENNANT DAVID ROBIN", "GB"),
    ("Melina Bucher", "DE"), ("Gitte Wichmann-Hansen", "DK"), ("JANSSEN BOB", "NL"), ("HEIKO SENNEWALD", "DE"),
    ("Philipp Rene Schubert", "DE"), ("WANDA MARIA SZPERLINSKA", "PL"), ("DR WILLIGE Barbara Katharina", "DE"),
    ("WAMECO S.C. RYSZARD SZPADT, WOJCIECH GORNIKOWSKI", "PL"),
    ("DIE RÄUCHEREI e.K. HANS-JOACHIM KUNKEL", "DE"),
    ("@BC - ARENDT BUSINESS CONSULTING (HANS-HENNING ARENDT)", "DE"),
])
def test_a_name_that_is_a_person_or_a_business_named_for_one_is_found(name, country):
    assert individual_reason(name, country)


@pytest.mark.parametrize("name,country", [
    ("CENTRE NATIONAL DE LA RECHERCHE SCIENTIFIQUE CNRS", "FR"), ("FRAUNHOFER GESELLSCHAFT ZUR FORDERUNG DER ANGEWANDTEN FORSCHUNG EV", "DE"),
    ("THE CHANCELLOR MASTERS AND SCHOLARS OF THE UNIVERSITY OF CAMBRIDGE", "GB"), ("THALES", "FR"),
    ("ECOLE POLYTECHNIQUE FEDERALE DE LAUSANNE", "CH"), ("Belfast City Council", "GB"), ("Kenya Ports Authority", "KE"),
    ("EURO-ARGO ERIC", "FR"), ("CLARIN ERIC", "NL"), ("IDRYMA TECHNOLOGIAS KAI EREVNAS", "GR"),
    ("FILMUNIVERSITAT BABELSBERG KONRAD WOLF", "DE"), ("CONSERVATORIO DI MUSICA GIUSEPPE TARTINI", "IT"),
    ("ENERGIE PER LA CITTA", "IT"), ("Clusterul Roman de Bioinformatica", "RO"), ("IRT ANTOINE DE SAINT EXUPERY", "FR"),
    ("COLLECTIVITE DE SAINT MARTIN", "FR"), ("AZIENDA OSPEDALIERA SAN PAOLO", "IT"), ("UNIVERZITNA NEMOCNICA MARTIN", "SK"),
    ("JOHN COCKERILL RENEWABLES", "BE"), ("Stichting Hanzehogeschool Groningen", "NL"), ("Waterschap Hollandse Delta", "NL"),
    ("EUROPEAN INFRASTRUCTURE OF OPEN SCREENING PLATFORMS FOR CHEMICAL BIOLOGY EUROPEAN RESEARCH INFRASTUCTURE CONSORTIUM (EU-OPENSCREEN ERIC)", "DE"),
    ("BIOBANKS AND BIOMOLECULAR RESOURCES RESEARCH INFRASTRUCTURE CONSORTIUM (BBMRI-ERIC)", "AT"),
    ("AIRBUS DEFENCE AND SPACE GMBH", "DE"), ("Leonardo S.p.a.", "IT"), ("SAAB AB", "SE"), ("Lawrence Berkeley National Laboratory", "US"),
    ("Max Planck Institute for Plasma Physics", "DE"), ("", "DE"), ("A", "DE"),
])
def test_an_institution_or_a_company_is_not_taken_for_a_person(name, country):
    assert individual_reason(name, country) is None


# ------------------------------------------------------------------ N4: prices

def test_the_routes_that_cost_a_second_cold_cost_more_than_a_plain_page():
    plain = request_cost("/v1/funding", {})
    assert request_cost("/v1/organisations/220347-cnrs/partners", {}) == 5
    assert request_cost("/v1/organisations/220347-cnrs/partners", {"country": "DE"}) == 7
    assert request_cost("/v1/analytics/ukraine-partners", {}) == 8
    assert request_cost("/v1/analytics/consortium-gaps", {"programme": "EDF"}) == 8
    assert request_cost("/v1/suppliers", {}) == 3
    assert request_cost("/v1/suppliers", {"q": "co", "page": "3"}) == 5
    assert request_cost("/v1/suppliers", {"q": "co", "country": "DE"}) == 7
    assert request_cost("/v1/changes", {}) == 5
    assert request_cost("/v1/organisations/slugs", {}) == 20 and request_cost("/v1/projects/slugs", {}) == 20
    assert request_cost("/v1/organisations/resolve", {}) == 5          # unchanged
    for path in ("/v1/organisations", "/v1/organisations/1-x", "/v1/projects/9-y", "/v1/suppliers/summary",
                 "/v1/suppliers/4-z"):
        assert request_cost(path, {}) == 2 > plain


# ------------------------------------------------------------------ N10: HEAD

def _app() -> TestClient:
    app = FastAPI()
    app.add_middleware(SecurityHeaders)          # a streaming (BaseHTTPMiddleware) layer under it, as in dgate.api
    app.add_middleware(HeadAsGet)

    @app.get("/v1/thing")
    def thing():
        return {"hello": "world"}

    @app.post("/v1/post-only")
    def post_only():
        return {}

    @app.get("/elsewhere")
    def elsewhere():
        return {"x": 1}

    return TestClient(app)


def test_head_on_a_read_route_answers_like_get_without_a_body():
    c = _app()
    got, head = c.get("/v1/thing"), c.head("/v1/thing")
    assert head.status_code == 200 and head.content == b""
    assert head.headers["content-type"] == got.headers["content-type"]
    assert head.headers["content-length"] == got.headers["content-length"]


def test_head_does_not_open_a_route_that_has_no_get():
    c = _app()
    assert c.head("/v1/post-only").status_code == 405
    assert c.head("/elsewhere").status_code == 405          # only /v1/ is rewritten
    assert c.get("/v1/post-only").status_code == 405


# ------------------------------------------------------------------ the EDF factsheet text carries no address

def test_an_address_in_a_factsheet_is_gone_before_the_text_is_landed_or_sent():
    pdf = make_pdf([[(60, 780, "EDF-2023-DA-CYBER factsheet"), (60, 760, "Contact point: someone.name@example-agency.eu"),
                     (60, 740, "Tel: +32 2 123 45 67"), (60, 720, "(Coordinator) TALGEN CYBERSECURITY OU   Estonia")]])
    text = edf.read_pdf(pdf)
    for body in (text.layout, text.plain):
        assert "example-agency" not in body and "someone.name" not in body
        assert "[email removed]" in body
        assert "TALGEN CYBERSECURITY OU" in body
    assert edf.read_pdf(factsheet_pdf()).sha256         # an ordinary factsheet still reads


def test_a_name_with_an_at_sign_that_is_no_address_survives():
    pdf = make_pdf([[(60, 780, "(Coordinator) SYSTEM@TIC PARIS REGION   France")]])
    assert "SYSTEM@TIC PARIS REGION" in edf.read_pdf(pdf).plain

