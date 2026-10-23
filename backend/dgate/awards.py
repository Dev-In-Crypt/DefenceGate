"""Layer 2b, the supplier map: who won the defence-relevant result notices of TED (WP-37).

The pipeline rule, as everywhere: land the raw payload, normalise, archive.

    land       the winner fields of each result notice, as TED returns them, in the raw store
               (source `ted_awards`), with the entries of natural persons blanked first
    normalise  `read_award()`: one `Winner` per winning organisation, natural persons and
               unidentifiable entries left out and counted
    archive    one `award` row per (notice, organisation), the organisation found by the
               resolution cascade of WP-26 (`dgate.resolution.resolve`; nothing else decides who
               a supplier is), and one `award_notice` row per notice read, so a second run asks
               TED about nothing it has already read

What the notices state and this module keeps: the winner's name, country and registration number
as the buyer published them. It keeps no contact, no person, no technical content. A winner that is
a natural person (a sole trader under their own name) is not a supplier profile: it is skipped and
counted, and its name never reaches the database or the raw store (see `is_natural_person`).

Values (WP-95): the notice's value fields are asked with its winners (`award_value.TED_VALUE_FIELDS`), and the
value with its kind (contract, framework ceiling, estimate) is kept on `award_notice` and, where the notice names
one winner, on that winner's `award` row (a value shared by several winners belongs to none of them).
"""

from __future__ import annotations

import copy
import logging
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from typing import Any

import httpx
import psycopg

from . import db
from .award_value import TED_VALUE_FIELDS, ted_value
from .classify import CORE_SQL, military_cpv_codes
from .config import settings
from .normalise import _country2, looks_like_contact, normalise_identifier, redact_emails
from .rawstore import BundleWriter, build_store, storage_key
from .resolution import Resolution, resolve
from .resolution.cascade import add_review
from .resolution.names import key_of
from .sources import USER_AGENT, new_client, ted
from .supplier_identity import stated_country_check

log = logging.getLogger(__name__)

SOURCE_CODE = "ted_awards"
# The notice types that carry winners (TED `notice-type` can-standard, can-social, can-desg and the
# voluntary ex ante notices), as the `notice_subtype` column stores them; measured 18 October 2026.
AWARD_SUBTYPES = ("29", "30", "31", "33", "34", "35", "36", "37", "E1", "E2", "E3", "E4", "E5", "E6")
# eForms is mandatory from 25 October 2023 and optional from 25 October 2022; before that the API
# states no winner at all (measured: 735 of 10,894 result notices of 2023 name one, 9,859 of 11,795 of
# 2024). Older notices are not asked for.
DEFAULT_SINCE = date(2023, 1, 1)
# WP-95: a result notice in the older (pre-eForms) format has no subtype (the column is NULL), only TED's notice
# type, and was never a candidate: TED 40783-2024 (Italian Navy, warship repair, Fincantieri), published in January
# 2024 under the defence directive, which kept the older forms into 2024. Such notices are read too, within the
# same core scope and window; the search API states no winner for them, so their winners are read from the notice
# document (`legacy_award_record`).
LEGACY_AWARD_TYPES = ("can-standard", "can-social", "can-desg", "can-tran", "veat")
# The winner fields and (WP-95) the value fields, asked in one request.
AWARD_FETCH_FIELDS = ted.AWARD_FIELDS + TED_VALUE_FIELDS
PERSON_PLACEHOLDER = "[natural person]"

# ----------------------------------------------------------------------------- natural persons
#
# A notice does not say whether a winner is a person. The rule is deliberately on the side of
# leaving a company out: a supplier we miss is a gap in coverage, a person we publish is a harm.
#
#   marker      a legal form or a business word anywhere in the name: a legal entity, kept
#   no marker   two to four capitalised words ("Radek Nečas"), or a SURNAME in capitals with a
#               first name ("DUPONT Jean"), or a Polish trading name that ends in a person's two
#               names ("P.P.H.U. Krismark Krystyna Łopuszańska"): a natural person, skipped
#   a Cyrillic sole-trader form (ET, FOP, IP): skipped
# Words are compared lower-case, without accents and dots; a run of single letters is one word
# ("S. A." is "sa"). Measured on the 5,997 distinct (name, country) pairs of the core scope on
# 18 October 2026: docs/design/SUPPLIER_MAP_FEASIBILITY.md.

_LEGAL_FORMS = frozenset("""
    gmbh mbh ag kg ohg gbr ug se sa sas sasu sarl snc eurl sl slu srl spa bv nv cv vof bvba sprl cvba
    ltd limited llc llp lp inc plc corp co company companies compagnie compania companhia kompanie
    oy oyj ab aps as asa uab sia ou ood eood doo dd ad kft zrt nyrt rt zoo oo sp spolka spółka spoldzielnia
    spółdzielnia sro akciova spolocnost aktiebolag osakeyhtio osauhing aktsiaselts tulundusuhistu
    aktiengesellschaft gesellschaft genossenschaft verein gie eig ev scpa scarl lda unipessoal
    societe sociedad sociedade societa entreprise entreprises etablissements etablissement ets
    groupement consortium konsorcjum
    sau slne sll slp sal sc scoop coop sccl scl sad sat aie sgps
    ооо оод еоод ад еад дздд дззд тов прат пат ао зао
""".split())
_BUSINESS = frozenset("""
    group groupe grupo gruppe holding holdings industries industrie industria industrial systems system
    systeme sistemas technologies technology technologie technik technical tech services service
    solutions solution defence defense defensa engineering engineers logistics logistik international
    internacional trading trade consulting consultants associates partners partnerschaft institute institut
    instytut university universität universidad universite università uniwersytet hospital ministry
    agency agentur association asociacion fundacion foundation stiftung cooperative cooperativa
    aerospace aeronautics electronics elektronik electric optics optical motors vehicles fahrzeugbau
    shipyard shipyards werft werke werk works factory fabrik pinselfabrik laboratories laboratoire
    laboratorium labor pharma medical medica med bank insurance telecom telecommunications energy power bau
    construction construcciones transport transportes security safety armaments arms ammunition munition
    munitions dynamics helicopters aircraft aviation marine naval maritime space satellite robotics
    instruments precision machinery metal metall steel plastics chemicals textile apparel uniforms
    clothing sports outdoor food catering cleaning printing publishing publications software digital data
    cyber studio design media advisory research development centre center centrum zentrum bureau buro office
    toimisto belgium belgique belgie france deutschland germany eesti estonia polska poland polen
    nederland netherlands espana spain italia italy europe europa european sverige sweden norge norway
    danmark denmark suomi finland latvija lietuva romania bulgaria czech ceska slovakia slovenija
    hrvatska hungary magyarorszag uk usa
    corporation corporations incorporated akcyjna ograniczona odpowiedzialnoscia komandytowa jawna
    partnerska korlatolt felelossegu tarsasag reszvenytarsasag nyilvanosan mukodo zartkoruen sabiedriba
    ierobezotu atbildibu elektronische electronic electronique computers computer facilities ordnance
    propellers autonomy advanced instrumentation ingenieure ingenieur ingenieurs architektur architects
    architekten schlauchboot izba politechnika uniwersytet universitaet ustav univerza fakulteta
    obedinenie sdruzeni sdruzenie ay ministerstwo ministerium ministere ministerio ministero ministerie
    ministerija
""".split())
_CORPORATE = _LEGAL_FORMS | _BUSINESS
_SOLE_TRADER = frozenset("ет фоп ип".split())
# forms that are a person trading, by country: PL spółka cywilna, DE eingetragener Kaufmann, RO PFA, FR EIRL
_SOLE_TRADER_BY_COUNTRY = {"PL": frozenset({"sc"}), "DE": frozenset({"ek"}), "RO": frozenset({"pfa"}),
                           "FR": frozenset({"eirl"})}
# letters NFKD does not decompose: the fold that makes "Spółka" and "spolka" one word
_FOLD = {ord("ł"): "l", ord("ø"): "o", ord("đ"): "d", ord("ß"): "ss", ord("ı"): "i", ord("ð"): "d",
         ord("æ"): "ae", ord("œ"): "oe"}
_PL_TRADING = re.compile(r"\b(?:PPHU|PHU|PUH|FHU|PPUH|PHPU|ZPUH)\b")
_PL_TRAILING_PERSON = re.compile(r",\s+[A-ZŁŚŻŹĆ][a-ząćęłńóśźż]+\s+[A-ZŁŚŻŹĆ][a-ząćęłńóśźż\-]+$")
# Poland: a trading name without a legal form is a sole proprietorship, i.e. a natural person
_PL_TRADE_WORDS = frozenset("""przedsiebiorstwo firma zaklad uslugi uslugowe handlowo produkcyjno agencja biuro
    pphu phu puh fhu ppuh phpu zphu zp mk pw ph""".split())
_ADDRESS = re.compile(r"\bul\.|\b\d{2}-\d{3}\b")
_PL_GIVEN = frozenset("""piotr andrzej jan krzysztof tomasz pawel michal marcin jacek grzegorz rafal marek adam lukasz
    waldemar kazimierz robert zbigniew stanislaw mariusz dariusz artur arkadiusz bartlomiej dawid krystyna anna
    iwona jadwiga malgorzata katarzyna agnieszka barbara ewa maria joanna magdalena monika teresa elzbieta zofia
    danuta halina renata beata aleksandra dorota wojciech jerzy henryk jozef ryszard slawomir tadeusz janusz
    roman miroslaw leszek edward bogdan damian kamil maciej przemyslaw sebastian jaroslaw radoslaw daniel
    mateusz karol szymon filip kacper patryk dominik norbert zdzislaw wladyslaw bernard cezary czeslaw
    ireneusz kornel lech marian mieczyslaw natalia stefan walenty zygmunt hanna ilona jolanta wanda lucyna
    alicja marzena urszula grazyna bozena sylwia paulina justyna karolina weronika wioletta ewelina kinga""".split())


def _words(name: str) -> list[str]:
    folded = unicodedata.normalize("NFKD", name.replace(".", "").replace("/", ""))
    folded = "".join(c for c in folded if not unicodedata.combining(c)).lower().translate(_FOLD)
    merged: list[str] = []
    run = ""                      # a run of single letters is one word: "s a" is "sa", "d o o" is "doo"
    for w in re.findall(r"[^\W_]+", folded) + [""]:
        if len(w) == 1:
            run += w
            continue
        if run:
            merged.append(run)
            run = ""
        if w:
            merged.append(w)
    return merged


def _title(tok: str) -> bool:
    parts = tok.split("-")
    return all(len(p) >= 2 and p[0].isupper() and p[1:].islower() for p in parts)


# Spain (WP-60): the tax number says what a winner is, and PLACSP states it for nearly every winner. A DNI
# (8 digits and a letter) or an NIE (X, Y or Z, 7 digits and a letter) is a natural person's number, and the
# publisher masks a person's number itself ("***1234**": 7 of 80 winners of the live feed of 20 October
# 2026, all of them a capitals-only name of three or four words). A CIF whose first letter is a legal form's
# (A sociedad anónima, B limitada, ..., U a UTE, W a foreign entity) is a legal entity's.
_ES_PERSON_ID = re.compile(r"\d{8}[A-Z]|[XYZ]\d{7}[A-Z]")
_ES_ENTITY_ID = re.compile(r"[ABCDEFGHJNPQRSUVW]\d{7}[0-9A-J]")
_MASKED_ID = re.compile(r"\*+\s*\d{3,5}\s*\*+")
# Spanish names are mostly written in capitals with the surnames first ("GARCIA LOPEZ JUAN", "MARTINEZ
# SANCHEZ, ANTONIO"); particles join the words of one name ("MARIA DEL CARMEN DE LA FUENTE").
_ES_PARTICLES = frozenset("de del la las los y i e da".split())
# capitals only: "Ute" is also a given name (DE)
_JOINT_VENTURE = re.compile(r"\bU\.?\s?T\.?\s?E\.?(?=\s|$|[,\-(])|\b(?i:uni[oó]n\s+temporal)\b")


def es_tax_kind(identifier: str | None, country: str | None = None) -> str | None:
    """'person', 'entity' or None (not a Spanish tax number) for a winner's stated number."""
    raw = (identifier or "").strip().upper()
    if not raw:
        return None
    if _MASKED_ID.fullmatch(raw):
        return "person"                 # masked by the publisher, whatever the country
    if country not in (None, "", "ES"):
        return None
    s = re.sub(r"[\s.\-/]", "", raw)
    if s.startswith("ES") and len(s) == 11:
        s = s[2:]
    if _ES_PERSON_ID.fullmatch(s):
        return "person"
    if _ES_ENTITY_ID.fullmatch(s):
        return "entity"
    return None


def is_joint_venture(name: str) -> bool:
    """A Spanish unión temporal de empresas ("UTE INDRA - ISDEFE"): one contracting party of its own."""
    return bool(_JOINT_VENTURE.search(name or ""))


# WP-94: a Spanish name is a person's only when it holds a common given name and no trade word. Without the
# given name the rule flagged 518 company names on production (DISA GAS S.A.U, CONTINENTAL TIRES, HIERROS BUENO
# SAL); a person whose given name is not here, and who states no DNI or NIE, is published (the owner's choice).
# Folded: lower case, no accents. Names that are also common trade or place words (Victoria, Santiago, Luz, Paz,
# Salvador, Belén, Fátima, Ángeles) are left out.
_ES_GIVEN = frozenset("""
    juan jose antonio manuel francisco javier jesus david daniel carlos miguel alejandro rafael pedro angel
    pablo sergio fernando jorge luis alberto alvaro diego adrian raul enrique ramon vicente ivan ruben oscar
    andres joaquin eduardo victor roberto jaime ignacio alfonso mario marcos ricardo emilio julio julian
    tomas agustin gonzalo felix hugo guillermo cristian mariano lorenzo martin nicolas sebastian gabriel
    samuel ismael marc jordi josep joan xavier xavi pau oriol sergi albert aitor inaki iker unai mikel jon
    gorka asier xabier xose xoan borja cesar arturo benito bernardo cristobal esteban federico gregorio
    gustavo hector isidro jacinto leandro leonardo lucas marcelino mateo mauricio nestor rodrigo rogelio
    teodoro valentin abel adolfo alfredo anselmo aurelio bartolome basilio camilo celestino clemente damian
    dionisio eloy elias eugenio fabian faustino fermin florencio gerardo german gines isaac jeronimo juanjo
    joaquim marcelo moises narciso pascual matias joao goncalo rui nuno tiago paulo duarte vasco afonso
    maria carmen ana isabel dolores pilar teresa rosa josefa francisca antonia laura cristina marta lucia
    mercedes elena manuela concepcion raquel sara paula rosario beatriz encarnacion julia silvia patricia
    irene montserrat montse monica alicia sonia rocio sandra yolanda esther andrea marina nuria inmaculada
    margarita susana eva veronica natalia claudia noelia gabriela daniela sofia carla amparo lorena lidia
    ines consuelo begona ainhoa itziar maite nerea leire amaia idoia arantxa olga catalina luisa emilia
    soledad estefania eugenia adela alejandra almudena amalia asuncion blanca celia clara elisa eloisa
    gemma ignacia jimena juana lourdes macarena magdalena mariana matilde miriam noemi olivia ruth vanesa
    virginia ximena joana anabel rebeca tamara judith marisol mireia neus fernanda conceicao graca
""".split())
# trade and corporate words of Spanish names, on top of _CORPORATE (folded)
_ES_TRADE = frozenset("""
    centro centros talleres taller suministros suministro comercial comerciales servicios proyectos hermandad
    autoescuela almacen almacenes hierros neumaticos neumaticas concesiones integracion formacion auditores
    auditoria iberia iberica espagne gas clientes turbo lingua obras construccion reformas instalaciones
    montajes distribuciones distribuidora ingenieria ingenieros consultores consultoria asesores asesoria
    gestion gestoria transportes recambios mantenimiento limpiezas limpieza seguridad electricidad electrica
    electricas fontaneria carpinteria cerrajeria pinturas imprenta grafica graficas farmacia farmaceutica
    farmaceuticos laboratorio laboratorios clinica colegio academia escuela instituto federacion empresa
    empresas industrias fabrica productos maquinaria vehiculos especiales automoviles motor motores
    ferreteria materiales tecnologia tecnologias soluciones informatica electronica telecomunicaciones
    energia ambiental medioambiente aguas hermanos hijos sucesores herederos armeria deportes optica
    uniformes textil textiles confecciones calzados alimentacion restaurante hotel viajes agencia estudio
    estudios diseno publicidad comunicacion editorial libreria papeleria oficina muebles mobiliario equipos
    equipamientos san santa santo nuestra senora ayuntamiento diputacion consejo junta club global nacional
    mediterraneo abogados cia tires tyres
""".split())


def _jv_has_company(name: str) -> bool:
    """Whether a UTE name keeps a member besides PERSON_PLACEHOLDER (a lone legal form is no member)."""
    rest = _JOINT_VENTURE.sub(" ", name.replace(PERSON_PLACEHOLDER, " "))
    return bool(set(_words(rest)) - _ES_PARTICLES - _LEGAL_FORMS - {"empresas", "denominada"})


def _es_person_name(tokens: list[str], words: set[str]) -> bool:
    shape = [t for t in tokens if t.lower() not in _ES_PARTICLES]
    return (2 <= len(shape) <= 5 and all(t.replace("-", "").isalpha() for t in shape)
            and all(t.isupper() or _title(t) for t in shape)
            and bool(words & _ES_GIVEN) and not words & (_CORPORATE | _ES_TRADE))


def person_reason(name: str, identifier: str | None = None, country: str | None = None) -> str | None:
    """Why this winner is not published as a supplier, or None when it is a legal entity."""
    raw = (name or "").strip()
    if is_joint_venture(raw) and PERSON_PLACEHOLDER in raw:
        # WP-94: a UTE whose person members joint_venture_name blanked is a party of its own while a company is left
        return None if _jv_has_company(raw) else "person_marked"
    if not raw or raw == PERSON_PLACEHOLDER or "natural person" in raw.lower() or "osoba fizyczna" in raw.lower():
        return "person_marked"
    tax = es_tax_kind(identifier, country)
    if tax == "person":
        if not set(_words(raw)) & _CORPORATE:
            return "person_identifier"
        # WP-94: a legal form or a business word in the name beats a person's number ("NAMMO PALENCIA SLU")
        log.info("a person's tax number stated for a name with a legal form or business word: read as an entity")
    if tax == "entity":
        return None                     # a CIF is a legal entity's, whatever its name looks like
    words = set(_words(raw))
    if words & _SOLE_TRADER or words & _SOLE_TRADER_BY_COUNTRY.get(country or "", frozenset()):
        return "person_in_trading_name"
    has_marker = bool(words & _CORPORATE)
    legal_form = bool(words & _LEGAL_FORMS)
    if not legal_form and _ADDRESS.search(raw):
        return "person_in_trading_name"            # a street or a postal code in a name: a sole trader's
    tokens = [t.strip(",;()\"'“”«»") for t in raw.replace(".", " ").split()]
    tokens = [t for t in tokens if t]
    if _PL_TRAILING_PERSON.search(raw) and not has_marker:
        return "person_in_trading_name"
    if _PL_TRADING.search(raw.replace(".", "")) and len(tokens) >= 3 and all(_title(t) for t in tokens[-2:]):
        return "person_in_trading_name"
    if country == "PL" and not legal_form:
        first = _words(tokens[0])[:1] if tokens else []
        pair = [_words(t)[:1] for t in tokens[-2:]]
        if (words & _PL_TRADE_WORDS
                or (len(tokens) >= 3 and pair[0] and pair[0][0] in _PL_GIVEN and len(tokens[-1]) >= 3)
                or (len(tokens) >= 3 and first and first[0] in _PL_GIVEN
                     and (_title(tokens[1]) or tokens[1].isupper()))):
            return "person_in_trading_name"
    if is_joint_venture(raw) and country in (None, "", "ES"):
        return None                     # a UTE: its members are blanked one by one (joint_venture_name)
    if country == "ES":                 # GARCIA LOPEZ JUAN, MARTINEZ SANCHEZ, ANTONIO; nothing else for Spain
        return "person_name" if _es_person_name(tokens, words) else None
    if has_marker or not 2 <= len(tokens) <= 4:
        return None
    titled = [t for t in tokens if _title(t)]
    caps = [t for t in tokens if len(t) >= 2 and t.isalpha() and t.isupper()]
    initials = [t for t in tokens if len(t) == 1 and t.isupper()]
    if len(titled) + len(initials) == len(tokens) and len(titled) >= 2:
        return "person_name"                       # Radek Nečas, Jean-Pierre Martin, Markus F. Strieder
    if titled and caps and len(titled) + len(caps) + len(initials) == len(tokens):
        return "person_name"                       # DUPONT Jean, Jan NOVAK
    return None


_JV_SPLIT = re.compile(r"\s+-\s+|\s*[,/;]\s*|\s+[YE]\s+(?=[A-ZÁÉÍÓÚÑ])")


def joint_venture_name(name: str, country: str | None = "ES") -> str:
    """A UTE's name with every member that reads as a natural person replaced by PERSON_PLACEHOLDER.

    "UTE INDRA - GARCIA LOPEZ JUAN" becomes "UTE INDRA - [natural person]": the joint venture is kept as
    a contracting party of its own, with the names of its member companies only."""
    m = _JOINT_VENTURE.search(name)
    if not m:
        return name
    head, rest = name[:m.end()], name[m.end():]
    lead = re.match(r"[\s:,\-]*(?:de\s+empresas\b)?[\s:,\-]*(?:denominada\b)?[\s:,\-]*", rest, re.IGNORECASE).group(0)
    parts = [p for p in _JV_SPLIT.split(rest[len(lead):]) if p.strip()]
    kept = [PERSON_PLACEHOLDER if person_reason(p.strip(), None, country) else p.strip() for p in parts]
    if kept == [p.strip() for p in parts]:
        return name
    return (head + lead).rstrip() + " " + " - ".join(kept)


def is_natural_person(name: str, identifier: str | None = None, country: str | None = None) -> bool:
    return person_reason(name, identifier, country) is not None


# ----------------------------------------------------------------------------- names that are not a supplier
#
# WP-39 (verify2-abuse N8, 18 October 2026): the winner block of a notice also carries text that is no
# organisation. Measured on production: a placeholder ("keine Angabe", DE0000000), a consortium written as
# one string ("Lider konsorcjum: A, Partner konsorcjum: B": 109 organisations, 143 awards), one name with a
# replacement character ("Zak¿ady") and, in principle, a telephone number or an address in the name field.
# A role note after a single company ("Stekop S.A. - Lider") is removed and the company kept; a string that
# still names a consortium or several parties afterwards is not a supplier. Skipped winners are counted.

_PLACEHOLDERS = frozenset("""
    keine angabe|keine angaben|ka|na|n a|none|nil|null|unknown|unbekannt|nicht angegeben|nicht bekannt|
    not available|not applicable|not specified|not stated|not known|no data|no name|brak|brak danych|bez nazwy|
    test|anonymous|anonym|anonyme|onbekend|niet bekend|inconnu|neant|non renseigne|non communique|sconosciuto|
    desconocido|tbd|tba|various|diverse|other|others|sonstige|nn|n n
""".replace("\n", "").split("|"))
_PLACEHOLDERS = frozenset(p.strip() for p in _PLACEHOLDERS if p.strip())
_ROLE_HEAD = re.compile(
    r"^\s*(?:konsorcjum(?:\s+firm|\s+w\s+sk[lł]adzie)?\s*:\s*)?"
    r"(?:(?:lider|partner|cz[lł]onek)\s+konsorcjum|lider|leader)\s*[:\-–—]\s*", re.IGNORECASE)
_ROLE_TAIL = re.compile(
    r"(?:\s*[-–—(,]\s*(?:lider|leader|partner|cz[lł]onek|mandataire|membre)"
    r"(?:\s+(?:konsorcjum|du\s+groupement|groupement|consortium))?|\s+(?:mandataire|lider)(?:\s+groupement)?)"
    r"\s*\)?\s*$", re.IGNORECASE)
_CONSORTIUM = re.compile(
    r"konsorcjum|konsortium|consortium|groupement|mandataire|cotraitant|bietergemeinschaft|"
    r"arbeitsgemeinschaft|\barge\b|joint[- ]venture|cz[lł]onek\s+konsorcjum|\b(?:lider|partner)\s*[:\-–—]",
    re.IGNORECASE)
# U+FFFD, a "¿" inside a word (a code page lost a letter: "Zak¿ady"), UTF-8 read as Latin-1 ("Ã©", "Â ").
_GARBLED = re.compile("\ufffd|(?<=\\w)\u00bf(?=\\w)|[\u00c3\u00c2][\u0080-\u00bf]")
_PHONE_IN_NAME = re.compile(r"\+\d[\d\s().-]{6,}\d|\b(?:tel|fax|phone|tlf)\b\.?\s*:?\s*[\d(+]", re.IGNORECASE)


def _fold_placeholder(name: str) -> str:
    return " ".join(_words(name.replace("/", " ")))


def clean_supplier_name(name: str) -> tuple[str | None, str]:
    """(why this winner is not a supplier or None, the name to keep). Role notes are stripped; a name
    that is a placeholder, a consortium, garbled or carries contact details is refused."""
    raw = (name or "").strip()
    folded = _fold_placeholder(raw)
    if _GARBLED.search(raw):
        return "garbled", raw
    if redact_emails(raw) != raw or _PHONE_IN_NAME.search(raw):
        return "contact_in_name", raw
    if folded in _PLACEHOLDERS or len(re.findall(r"[^\W\d_]", raw)) < 2 or re.fullmatch(r"(.)\1{1,}", folded.replace(" ", "")):
        return "placeholder", raw
    cleaned = raw
    for _ in range(3):                        # "Konsorcjum firm: Lider konsorcjum: X S.A. - lider": a few layers at most
        stripped = _ROLE_TAIL.sub("", _ROLE_HEAD.sub("", cleaned))
        if stripped == cleaned:
            break
        cleaned = stripped.strip(" ,;-–—")
    if _CONSORTIUM.search(cleaned):
        return "consortium_string", raw
    return None, cleaned or raw


# ----------------------------------------------------------------------------- reading a record

@dataclass
class Winner:
    name: str
    country: str | None
    identifier: str | None
    # WP-81, PLACSP: the awarded amount without VAT of the results naming this one winner (`award.value_amount`);
    # WP-95, TED too: the notice's value where it names this one winner. `value_kind`: contract, framework or
    # estimate (`award_value`); None: nothing derived (the row is left as it is)
    value_amount: float | None = None
    value_currency: str | None = None
    value_kind: str | None = None


@dataclass
class Read:
    winners: list[Winner] = field(default_factory=list)
    counts: Counter = field(default_factory=Counter)
    redacted: dict[str, Any] = field(default_factory=dict)
    winners_seen: int = 0               # distinct winning organisations the notice names, kept or not
    # WP-95: the notice's own value (amount, currency, kind), TED; the framework notice a call-off is based on
    notice_value: tuple[float | None, str | None, str | None] | None = None
    framework_id: int | None = None


def _lists(value: Any) -> list[list[str]]:
    """A multilingual block {lang: [..]} as its lists; a plain list as one list."""
    if isinstance(value, dict):
        return [[str(x).strip() for x in (v or [])] for v in value.values()]
    if isinstance(value, (list, tuple)):
        return [[str(x).strip() for x in value]]
    if value in (None, ""):
        return []
    return [[str(value).strip()]]


def _longest(value: Any) -> list[str]:
    ls = _lists(value)
    return max(ls, key=len) if ls else []


def _flat(value: Any) -> list[str]:
    return [x for lst in _lists(value) for x in lst]


def read_award(rec: dict[str, Any]) -> Read:
    """The winners of one result notice, as TED's winner fields state them.

    `organisation-*-tenderer` are parallel lists, one entry per organisation of the tendering parties
    (they agree on a legal form and a country for 99.0 % of 1,226 pairs measured on 18 October 2026),
    and `winner-name` says which of them won. `winner-country` and `winner-identifier` are not read:
    in notices with several winners they are not in the order of `winner-name` (81 % agreement).
    A country or a number is taken from its list only when the list has one entry per organisation,
    or the notice has one organisation, or all entries are equal (countries only).
    """
    out = Read()
    won = set(_flat(rec.get("winner-name")))
    names = _longest(rec.get("organisation-name-tenderer"))
    if not won:
        out.counts["no_winner_name"] += 1
        return out
    if not names:
        out.counts["no_tenderer_block"] += 1
        return out
    countries = [_country2(c) for c in _flat(rec.get("organisation-country-tenderer"))]
    idents = _flat(rec.get("organisation-identifier-tenderer"))
    n = len(names)
    one_country = countries[0] if countries and len(set(countries)) == 1 else None
    blank: set[int] = set()
    seen: set[tuple[str, str | None]] = set()
    for i, name in enumerate(names):
        country = countries[i] if len(countries) == n else one_country
        ident = idents[i] if len(idents) == n else (idents[0] if n == 1 and idents else None)
        reason = person_reason(name, ident, country)
        problem, cleaned = (None, name) if reason else clean_supplier_name(name)
        if reason or problem == "contact_in_name":
            blank.add(i)
        if name not in won or (name, country) in seen:
            continue
        seen.add((name, country))
        out.winners_seen += 1
        if reason:
            out.counts["skipped_" + reason] += 1
            out.counts["skipped_person"] += 1
        elif problem:
            out.counts["skipped_" + problem] += 1
        elif not country:
            out.counts["skipped_no_country"] += 1
        else:
            # A telephone number or an address typed into the identifier field is contact data (4 of 4,186
            # profiles, verify2-abuse N1): never read on. A word in the field is dropped when the row is stored.
            ident = None if looks_like_contact(ident) else (ident or None)
            # WP-96: a country the winner's own VAT prefix, name or legal form contradicts was the list's slip
            # (LEONARDO Germany GmbH, Saab Finland Oy and Rheinmetall Canada Inc. filed as Sweden)
            fixed, basis = stated_country_check(cleaned, ident, country, tuple(c for c in countries if c))
            if basis:
                out.counts["country_corrected_" + basis] += 1
            out.winners.append(Winner(cleaned, fixed, ident))
    if not out.winners_seen:
        out.counts["winner_not_among_tenderers"] += 1
    out.redacted = _redact(rec, names, blank, idents, len(idents) == n, one_country)
    return out


def _redact(rec: dict[str, Any], names: list[str], blank: set[int], idents: list[str],
            ids_aligned: bool, country: str | None = None) -> dict[str, Any]:
    """The record with the names (and numbers) of natural persons blanked, positions kept, and any contact
    detail typed into an identifier field removed.

    Every name the record states is tested, not only the longest tenderer list: a `winner-name` that is not
    among the tenderers, or another language's spelling of a tenderer, is landed too (WP-71, QA M6)."""
    red = copy.deepcopy(rec)
    contact = [i for i, x in enumerate(idents) if looks_like_contact(x)]
    winner_ids = _flat(rec.get("winner-identifier"))
    bad = {names[i] for i in blank}
    others = set(_flat(rec.get("winner-name"))) | set(_flat(rec.get("organisation-name-tenderer")))
    bad |= {x for x in others - set(names) if person_reason(x, None, country)}
    if not bad and not contact and not any(looks_like_contact(x) for x in winner_ids):
        return red
    for key in ("winner-name", "organisation-name-tenderer"):
        v = red.get(key)
        if isinstance(v, dict):
            red[key] = {lang: [PERSON_PLACEHOLDER if str(x).strip() in bad else x for x in (lst or [])]
                        for lang, lst in v.items()}
        elif isinstance(v, list):
            red[key] = [PERSON_PLACEHOLDER if str(x).strip() in bad else x for x in v]
    ids = red.get("organisation-identifier-tenderer")
    if isinstance(ids, list):
        drop = blank | set(contact)
        red["organisation-identifier-tenderer"] = (
            ["" if i in drop else x for i, x in enumerate(ids)] if ids_aligned else [])
    elif isinstance(ids, dict) and (contact or bad):
        # positions in a per-language block cannot be matched to a person: the block goes
        red["organisation-identifier-tenderer"] = {}
    if bad or any(looks_like_contact(x) for x in winner_ids):
        red.pop("winner-identifier", None)
    return red


# ----------------------------------------------------------------------------- the loader

def _main_cpv(codes: list[str] | None) -> str | None:
    """The code a profile files the notice under: the first military code, else the first code."""
    mil = military_cpv_codes(codes)
    first = next((c for c in (codes or []) if c), None)
    return (mil[0] if mil else first) or None


def stated_number(ident: str | None, country: str | None) -> str | None:
    """The identifier as the notice states it, kept only when it is a registration or tax number (at most 60
    characters). "Unknown", a company name or a telephone number typed into the field is not one: the profile
    page showed such values as identifiers (verify2-abuse N1; 547 of 8,368 stored values were not numbers)."""
    return ident[:60] if ident and normalise_identifier(ident, country) else None


def _attach_reg(conn: psycopg.Connection, org_id: int, ident: str | None, country: str) -> None:
    """Give an organisation the registration number the notice states, if it has none and nobody
    else of the country holds that number. The cascade's stage 1 finds it from then on."""
    reg = normalise_identifier(ident, country) if ident else None
    if not reg:
        return
    conn.execute(
        """UPDATE organisation
              SET national_reg_no = %s, identifier_method = 'identifier', identifier_confidence = %s
            WHERE id = %s AND national_reg_no IS NULL
              AND NOT EXISTS (SELECT 1 FROM organisation x WHERE x.country = %s AND x.national_reg_no = %s)""",
        (reg, db.CONF_IDENTIFIER_ATTACHED, org_id, country, reg))


def _kind(number: str) -> tuple[str, int | str]:
    """What sort of number this looks like: its length when it is all digits (a German VAT number is nine
    digits), its letter prefix otherwise (HRB, FN, ATU)."""
    if number.isdigit():
        return ("D", len(number.lstrip("0")))
    m = re.match(r"[A-Z]+", number)
    return ("A", m.group(0) if m else "")


def _distance(a: str, b: str) -> int:
    row = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        prev, row[0] = row[0], i
        for j, cb in enumerate(b, 1):
            prev, row[j] = row[j], min(row[j] + 1, row[j - 1] + 1, prev + (ca != cb))
    return row[-1]


def numbers_conflict(a: str, b: str) -> bool:
    """Two registration numbers that cannot be one body's. Notices write one company's number as a VAT
    number or as a register number, with or without a leading zero or a prefix, and with typos: in the
    replay of the real notices (18 October 2026) a plain inequality split 225 organisations, and most of
    the 40 read were such spellings. So they conflict only when they are of one kind (the same count of
    digits, or the same letter prefix), neither is the start of the other, and they differ by at least two
    characters."""
    za, zb = a.lstrip("0"), b.lstrip("0")
    if za == zb or za.startswith(zb) or zb.startswith(za):
        return False
    return _kind(a) == _kind(b) and _distance(a, b) >= 2


def _namesake_guard(conn: psycopg.Connection, res: Resolution, w: Winner) -> Resolution:
    """A match by name on a body that holds another registration number is a namesake, not this
    supplier ("Mueller Bau GmbH" exists in every German town): the number the notice states makes a
    body of its own, and the pair goes to the review queue. The cascade (stage 2) decides on the name
    alone, which is right for a buyer a notice names without a number and wrong for a supplier that
    states one."""
    reg = normalise_identifier(w.identifier, w.country) if w.identifier else None
    if not reg or res.org_id is None or res.method in ("pic", "national_id", "vat"):
        return res
    key, _ = key_of(w.name)
    # The cascade tries an alias before a registration number, so a name that was decided before wins over
    # the number: the body that holds this number, if its name fits, is the supplier.
    holder = conn.execute("""SELECT id, canonical_name FROM organisation
                              WHERE country = %s AND national_reg_no = %s AND merged_into IS NULL""",
                          (w.country, reg)).fetchone()
    if holder:
        if holder["id"] != res.org_id and db.names_compatible(key, holder["canonical_name"]):
            return Resolution(holder["id"], "national_id", db.CONF_IDENTIFIER)
        return res          # the number sits on a body whose name shares nothing with this one: a person decides
    held = conn.execute("SELECT national_reg_no FROM organisation WHERE id = %s",
                        (res.org_id,)).fetchone()["national_reg_no"]
    if not held or not numbers_conflict(held, reg):
        return res
    other = db._new_organisation(conn, key, w.country or "", reg)
    conn.execute("UPDATE organisation SET display_name = %s WHERE id = %s", (w.name[:300], other))
    add_review(conn, res.org_id, other, relation="same_name_other_id", method="id_conflict", confidence=0.50,
               evidence={"key": key, "country": w.country, "numbers": [held, reg]})
    return Resolution(other, "national_id_new", db.CONF_IDENTIFIER_ATTACHED, created=True)


def store_notice(conn: psycopg.Connection, src_id: int, opp: dict[str, Any], read: Read,
                 raw_key: str | None, c: Counter, *, payload_hash: str | None = None,
                 payload_updated_at: Any = None) -> None:
    """Archive one notice's winners. Idempotent: an award row exists once per (notice, organisation).

    With `payload_hash` (PLACSP, WP-60) the notice may be read again when its result changes (a folder
    moves from ADJ to RES, a winner renounces and the next is awarded): the notice row is rewritten, a
    winner no longer named is marked `superseded_at` (rows are never deleted), and one named again is
    current again. TED notices are read once and never pass a hash."""
    kept = 0
    current: list[int] = []
    for w in read.winners:
        res = resolve(conn, w.name, w.country, {"reg": w.identifier},
                      {"source_id": src_id, "candidates": False})
        if res.org_id is None:
            c["skipped_unresolved"] += 1
            continue
        res = _namesake_guard(conn, res, w)
        _attach_reg(conn, res.org_id, w.identifier, w.country)
        row = conn.execute(
            """INSERT INTO award (opportunity_id, organisation_id, supplier_country, name_as_stated,
                                  identifier_as_stated, winners_in_notice, cpv_main,
                                  resolution_method, resolution_confidence)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT (opportunity_id, organisation_id) DO UPDATE SET superseded_at = NULL
                  WHERE award.superseded_at IS NOT NULL
               RETURNING id, (xmax = 0) AS inserted""",
            (opp["id"], res.org_id, w.country, w.name[:300], stated_number(w.identifier, w.country),
             read.winners_seen, _main_cpv(opp["cpv_codes"]), res.method, round(res.confidence, 2))).fetchone()
        if payload_hash is not None or w.value_kind is not None:
            # WP-81: a PLACSP re-read carries the awarded amount of this read, whatever the row held before;
            # WP-95: and its kind, and a TED notice the value of its one winner
            conn.execute(
                """UPDATE award SET value_amount = %s, value_currency = %s, value_kind = %s
                    WHERE opportunity_id = %s AND organisation_id = %s
                      AND (value_amount IS DISTINCT FROM %s::numeric OR value_currency IS DISTINCT FROM %s
                           OR value_kind IS DISTINCT FROM %s)""",
                (w.value_amount, w.value_currency, w.value_kind, opp["id"], res.org_id, w.value_amount,
                 w.value_currency, w.value_kind))
        c["awards_new"] += bool(row and row["inserted"])
        c["awards_current_again"] += bool(row and not row["inserted"])
        c["organisations_new"] += res.created
        c["by_" + res.method] += 1
        current.append(res.org_id)
        kept += 1
    status = "loaded" if kept else ("no_supplier" if read.winners_seen else "no_winner_data")
    if payload_hash is not None:
        gone = conn.execute(
            """UPDATE award SET superseded_at = now()
                WHERE opportunity_id = %s AND superseded_at IS NULL AND NOT (organisation_id = ANY(%s))""",
            (opp["id"], current)).rowcount
        c["awards_superseded"] += gone
    va, vc, vk = read.notice_value or (None, None, None)
    conn.execute(
        """INSERT INTO award_notice (opportunity_id, raw_key, winners_seen, winners_kept, skipped_person,
                                     skipped_no_country, status, payload_hash, payload_updated_at,
                                     value_amount, value_currency, value_kind, framework_id)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
           ON CONFLICT (opportunity_id) DO UPDATE
              SET raw_key = EXCLUDED.raw_key, winners_seen = EXCLUDED.winners_seen,
                  winners_kept = EXCLUDED.winners_kept, skipped_person = EXCLUDED.skipped_person,
                  skipped_no_country = EXCLUDED.skipped_no_country, status = EXCLUDED.status,
                  payload_hash = EXCLUDED.payload_hash, payload_updated_at = EXCLUDED.payload_updated_at,
                  framework_id = EXCLUDED.framework_id, read_at = now()
            WHERE EXCLUDED.payload_hash IS NOT NULL""",
        (opp["id"], raw_key, read.winners_seen, kept, read.counts["skipped_person"],
         read.counts["skipped_no_country"], status, payload_hash, payload_updated_at, va, vc, vk, read.framework_id))
    c["notices_" + status] += 1
    for k, v in read.counts.items():
        c[k] += v


# The serving columns the value of a TED notice is read with (`award_value.ted_value`).
VALUE_COLUMNS = "o.value_amount, o.value_currency, o.value_kind, o.notice_subtype, o.title_original, o.title_en"
RESULT_NOTICE_SQL = ("(o.notice_subtype = ANY(%(subtypes)s) "
                     "OR (o.notice_subtype IS NULL AND o.status_native = ANY(%(legacy)s)))")
RESULT_NOTICE_PARAMS = {"subtypes": list(AWARD_SUBTYPES), "legacy": list(LEGACY_AWARD_TYPES)}


def candidates(conn: psycopg.Connection, src_id: int, since: date, limit: int | None) -> list[dict[str, Any]]:
    """TED result notices of the core scope that no run has read yet, newest first: eForms ones by subtype, older
    ones by notice type (WP-95)."""
    return conn.execute(
        f"""SELECT o.id, o.native_id, o.cpv_codes, {VALUE_COLUMNS} FROM opportunity o
             WHERE o.source_id = %(src)s AND o.is_defence AND NOT o.suppressed AND {CORE_SQL}
               AND {RESULT_NOTICE_SQL} AND o.published_at >= %(since)s
               AND NOT EXISTS (SELECT 1 FROM award_notice n WHERE n.opportunity_id = o.id)
             ORDER BY o.published_at DESC, o.id LIMIT %(limit)s""",
        {"src": src_id, **RESULT_NOTICE_PARAMS, "since": since, "limit": limit or 1_000_000}).fetchall()


def _xml_local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _xml_find(el: Any, name: str) -> Any:
    return next((x for x in el.iter() if _xml_local(x.tag) == name), None)


def legacy_award_record(xml: bytes) -> dict[str, Any]:
    """The winners of an older-format TED result notice (the TED_EXPORT document: R2.0.8
    `ECONOMIC_OPERATOR_NAME_ADDRESS`, R2.0.9 `AWARDED_CONTRACT/CONTRACTORS/CONTRACTOR/ADDRESS_CONTRACTOR`) in the shape
    of the search API's award fields, so `read_award` reads them with the same rules (natural persons, names,
    countries). Only the name, the country and the national number of each contractor are read: no address, no
    contact. A document that is not XML, or names no contractor, gives a record without winners.
    ponytail: the element names are the TED_EXPORT schemas' as documented; the ops report counts the documents read
    and those that named a winner, so a schema this misses shows as a gap, not as a wrong winner."""
    import xml.etree.ElementTree as ET

    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return {"legacy-xml": True}
    names: list[str] = []
    countries: list[str] = []
    idents: list[str] = []
    for el in root.iter():
        if _xml_local(el.tag) not in ("ADDRESS_CONTRACTOR", "ECONOMIC_OPERATOR_NAME_ADDRESS"):
            continue
        name_el = _xml_find(el, "OFFICIALNAME")
        name = " ".join((name_el.text or "").split()) if name_el is not None else ""
        if not name:
            continue
        country_el = _xml_find(el, "COUNTRY")
        country = (country_el.get("VALUE") or "").strip().upper() if country_el is not None else ""
        ident_el = _xml_find(el, "NATIONALID")
        names.append(name)
        countries.append("GB" if country == "UK" else country)     # the older forms write UK
        idents.append(" ".join((ident_el.text or "").split()) if ident_el is not None else "")
    return {"legacy-xml": True, "winner-name": names, "organisation-name-tenderer": names,
            "organisation-country-tenderer": countries, "organisation-identifier-tenderer": idents}


def with_values(read: Read, value: tuple[float | None, str | None, str | None]) -> Read:
    """WP-95: the notice's value (`award_value.ted_value`) on the notice and, where the notice names one winner, on
    that winner (a value shared by several winners is attributed to none, as before)."""
    read.notice_value = value if value[2] else None
    if value[2] and read.winners_seen == 1:
        for w in read.winners:
            w.value_amount, w.value_currency, w.value_kind = value
    return read


def read_ted_notice(rec: dict[str, Any], opp: dict[str, Any], client: httpx.Client, counters: Counter,
                    nap=None) -> tuple[dict[str, Any], Read]:
    """The winners and value of one TED result notice from its search record; for an older-format notice whose
    record names no winner, from its document (WP-95). Returns the record read (to land) and the reading."""
    read = read_award(rec)
    if not read.winners_seen and not opp.get("notice_subtype"):
        if nap:
            nap()
        xml = ted.fetch_notice_xml(opp["native_id"], client=client)
        counters["legacy_documents"] += 1
        legacy = legacy_award_record(xml) if xml else {}
        if legacy.get("winner-name"):
            rec = {**rec, **legacy}
            read = read_award(rec)
            counters["legacy_with_winners"] += 1
    return rec, with_values(read, ted_value(rec, opp))


def refresh_award_twins(conn: psycopg.Connection) -> int:
    """Rewrite `award_twin_set` (migration 0098) from the `award_twin` view (seconds on production), in the
    caller's transaction: the caller commits, and a reader sees the old pairs or the new ones. The lock keeps two
    refreshes apart (the second would insert pairs the first committed) and lets readers through."""
    conn.execute("LOCK TABLE award_twin_set IN EXCLUSIVE MODE")
    conn.execute("DELETE FROM award_twin_set")
    return conn.execute(
        """INSERT INTO award_twin_set (award_id, preferred_id, procedure_method, winner_method)
           SELECT award_id, preferred_id, procedure_method, winner_method FROM award_twin""").rowcount


def run_awards(*, since: date = DEFAULT_SINCE, limit: int | None = None,
               client: httpx.Client | None = None, pause: float = 1.0,
               sleep=None) -> Counter:
    """Read the winners of the result notices we hold and have not read. One request a second."""
    import time

    nap = sleep or time.sleep
    cfg = settings()
    c: Counter = Counter()
    owns = client is None
    client = client or new_client(headers={"User-Agent": USER_AGENT})
    try:
        with db.connect(cfg.dsn) as conn, BundleWriter(build_store(), SOURCE_CODE) as writer:
            src_id = db.source_id(conn, SOURCE_CODE)
            ted_id = db.source_id(conn, "ted")
            run_id = db.start_run(conn, SOURCE_CODE, None)
            try:
                load_awards(conn, client, writer, src_id, ted_id, since=since, limit=limit,
                            counters=c, pause=pause, sleep=nap)
                writer.drain()
                refresh_award_twins(conn)
                db.finish_run(conn, run_id, fetched=c["fetched"], new=c["awards_new"], changed=0,
                              detail=dict(c))
            except Exception as exc:
                conn.rollback()
                db.finish_run(conn, run_id, fetched=c["fetched"], new=c["awards_new"], changed=0,
                              status="failed", error=str(exc)[:500])
                raise
    finally:
        if owns:
            client.close()
    log.info("%s done: %s", SOURCE_CODE, dict(c))
    return c


def load_awards(conn: psycopg.Connection, client: httpx.Client, writer: BundleWriter, src_id: int,
                ted_id: int, *, since: date, limit: int | None, counters: Counter,
                pause: float = 1.0, sleep=None) -> None:
    import time

    nap = sleep or time.sleep
    known = {r["content_hash"] for r in conn.execute(
        "SELECT content_hash FROM raw_ingest WHERE source_id = %s", (src_id,)).fetchall()}
    todo = candidates(conn, src_id=ted_id, since=since, limit=limit)
    counters["candidates"] = len(todo)
    for i in range(0, len(todo), ted.AWARD_BATCH):
        batch = [o for o in todo[i:i + ted.AWARD_BATCH] if ted.PUBLICATION_NUMBER.fullmatch(o["native_id"])]
        counters["skipped_bad_number"] += len(todo[i:i + ted.AWARD_BATCH]) - len(batch)
        if i:
            nap(pause)
        got = ted.fetch_by_numbers([o["native_id"] for o in batch], fields=AWARD_FETCH_FIELDS, client=client)
        for opp in batch:
            rec = got.get(opp["native_id"])
            if rec is None:
                counters["not_returned"] += 1       # not marked read: the next run asks again
                continue
            counters["fetched"] += 1
            rec, read = read_ted_notice(rec, opp, client, counters, nap=lambda: nap(pause))
            raw_key = None
            if read.redacted:
                h = ted.content_hash(read.redacted)
                raw_key = writer.put(storage_key(SOURCE_CODE, opp["native_id"], content_hash=h), read.redacted)
                if h not in known:
                    db.record_raw(conn, src_id, opp["native_id"], h, raw_key)
                    known.add(h)
            store_notice(conn, src_id, opp, read, raw_key, counters)
        writer.drain()        # the bundle is written before the rows that point into it are committed
        conn.commit()
