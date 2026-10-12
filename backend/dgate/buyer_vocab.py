"""What a buyer's name says it is.

Two questions are answered from a name, and they are kept apart:

  defence_body(name)   is this an armed-forces body or a defence procurement body?
                       Feeds the derived buyer list (dgate/ops/derive_buyers.py).
  buyer_class_of(name) what kind of body is it? Feeds the demotion rule in
                       classify.py: a military CPV bought by a municipality, a
                       hospital, a school or a fire brigade is not a defence lead.

The vocabulary is per language and written against the folded form
(`normalise_org_name(name, fold_state=True)`: lowercase, accents stripped, legal
form dropped, state prefixes folded). Greek and Cyrillic names are matched in
their own script.

Precision is the point. A listed buyer qualifies a notice on its own, whatever it
buys, so every pattern here was read against real organisation names from the
database (docs/DATA_QUALITY_PLAN_2026-10-12.md, WP E) and the exclusions are as
explicit as the inclusions: military hospitals, military property agencies,
language schools, civil defence and civil protection, police and border bodies.

Poland and Spain have their own, older rules in dgate/ops/derive_buyers.py and
are not decided here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache

from .normalise import normalise_org_name


def folded(name: str) -> str:
    return normalise_org_name(name or "", fold_state=True)


def _rx(*parts: str) -> re.Pattern:
    return re.compile("|".join(parts))


# ------------------------------------------------------------ not defence
#
# Each of these is a body that carries a defence word and is not a defence buyer
# in the sense a supplier means. Checked before any inclusion.

CIVIL_PROTECTION = _rx(
    r"civil(?:t)? (?:defen[cs]e|forsvar|protection|contingenc)",
    r"civilni zasciti|civilnu zastitu|civilna zastita|civilnej ochrany|civilni obrany",
    r"protection civile|proteccion civil|protezione civile|protecao civil|zivilschutz",
    r"bevolkerungsschutz|katastrophenschutz|katastrophen",
    r"civilt forsvar|samhallsskydd|beredskab|samfundssikkerhed|samfunnssikkerhet",
    r"obrana cywilna|obrony cywilnej|ochrany obyvatelstva|ochrana obyvatelstva",
    r"civilna odbrana|civilines gynybos|civilas aizsardzibas|pelastus|paastea|paasteamet",
    r"situatii(?:lor)? de urgenta|inspectoratul general pentru situatii",
    r"гражданск\w+ защит|гражданска защита|πολιτικη προστασια|πολιτικης προστασιας",
)

FIRE_RESCUE = _rx(
    r"fire (?:and rescue|brigade|service|authority|department|rescue)|fire-?fighting",
    r"straz pozarna|pozarn|feuerwehr|pompier|sapeurs?|bomberos|brandweer|vigili del fuoco",
    r"bombeiros|raddningstjanst|brandvaesen|brandvesen|hasici|hasicsky",
    r"ugunsdz|gaisr|priesgaisr|vatrogas|gasilsk|ochotnicza straz",
    r"пожарн|противопожарн|πυροσβεστικ",
    r"service departemental d incendie|\bsdis\b|\bsamu\b|ambulance|rettungsdienst|rescue service",
)

HEALTH = _rx(
    r"szpital|zaklad opieki zdrowotnej|spzoz|przychodni|centrum medyczn|instytut medycyn",
    r"krankenhaus|klinik|sanitatsdienst|sanitatsamt|lazarett|wehrmedizin",
    r"hospital|hopital|hopitaux|centre hospitalier|\bchu\b|\bchr\b|clinique|medical|medicin",
    r"ospedal|azienda sanitaria|azienda ospedaliera|\basl\b|\basst\b|\busl\b|ulss",
    r"ziekenhuis|nemocnic|zdravotn|zdravstv|bolnic|spital|spitalul",
    r"sjukhus|sairaala|sygehus|sykehus|sundhed|sjukvard",
    r"egeszseg|korhaz|health|\bnhs\b|healthcare|centro de salud|unidade local de saude",
    r"\bsante\b|regionale de sante",
    r"servicio (?:de salud|andaluz de salud|madrileno de salud|gallego de salud)|servizio sanitario",
    r"болниц|болница|медицинск|νοσοκομει|ιατρικ|υγειας",
    r"service de sante des armees|centre de transfusion|institut de sante",
    r"veterinar|apotheke|pharma|krwiodawstw|uzdrowisk|sanatori|rehabilit|medico|medicale",
)

EDUCATION = _rx(
    r"universit|uniwersytet|politechnik|hochschule|fachhochschule",
    r"\bschool\b|\bcollege\b|szkola|szkoly|szkole|schule\b|schulen|ecole\b|lycee",
    r"escuela|colegio|scuola|istituto (?:comprensivo|scolastico|d istruzione)",
    r"\bskola\b|\bskolen\b|\bskole\b|koulu|gymnas|gymnazium|fakult",
    r"language school|sprachen|jezykow|studentenwerk|studentski",
    r"университет|училищ|школа|гимнази|πανεπιστημι|σχολη|σχολεια",
    r"research (?:council|centre|institute)|forschung|badawcz|wetenschapp",
)

# Military property and estate agencies buy buildings, land and maintenance: real
# money, not the defence supply chain. Kept out of the list on purpose.
PROPERTY = _rx(
    r"agencja mienia wojskowego|wojskowa agencja mieszkaniow|agencja nieruchomosci",
    r"bundesanstalt fur immobilienaufgaben|\bbima\b|bundesamt fur bauwesen|amt fur bundesbau",
    r"bau- ?und liegenschaft|baumanagement|liegenschaftsbetrieb|landesbetrieb|bauamt|hochbauamt",
    r"defen[cs]e (?:infrastructure organi[sz]ation|estates)|\bdio\b|infrastructure organi[sz]ation",
    r"forsvarsbygg|fortifikationsverket|forsvarets ejendom|ejendomsstyrelse|puolustushallinnon rakennuslaitos",
    r"defence estates|estates agency|agentura hospodareni s nemovitym majetkem|agentura pre majetok",
    r"direction de l immobilier|agence immobiliere|immobilienaufgaben",
    r"service d infrastructure de la defense|service d infrastrucutre|\bdcsid\b|\besid\b|\bdrsid\b",
    r"cercle (?:national|de la base)|coordination de defense des services sociaux",
    r"servicio de infraestructura|gerencia de infraestructura|instituto de vivienda|\binvied\b",
    r"agenzia del demanio|demanio|direzione dei lavori|puolustuskiinteistot",
    r"paris la defense|amenagement de la defense|epadesa|defacto|quartier d affaires|puteaux|courbevoie",
    r"muzeul|museum|muzeum|muzej|musee\b|\bmuseo\b|association|verband|yhdistys|sportszovetseg|\bclub",
)

SECURITY_SERVICE = _rx(
    r"polic|polizei|politie|\bpoliti\b|policie|policia|policja|poliisi|politsei|rendorseg|gendarm",
    r"carabinier|guardia civil|guardia di finanza|guarda nacional|jandarm|garda siochana",
    r"wiezien|zaklad karny|areszt sledczy|justizvollzug|strafvollzug|penitenc",
    r"\bprison|ieslodzij|gevangen|vezenska|grenz|\bborder|granic|\bzoll|douane|customs|dogana",
    r"inrikes|innenministerium|inneres\b|interieur|binnenlandse|\binterior|vnitra|vnutra|notranje",
    r"unutarnjih|ministerul afacerilor interne|spraw wewnetrznych|vidaus reikalu|iekslietu",
    r"siseministeerium|sisaministeerium|ministry of justice|home office|piirivalve|rajavartio",
    r"полиц|жандарм|вътрешните работи|αστυνομ|λιμενικ|kustwacht|coast ?guard|tieslietu",
)

# -------------------------------------------------------------- defence
#
# (label, confidence, pattern, countries or None). Confidence says how sure the
# NAME alone is:
#   0.95  the ministry, a service, a procurement agency, an armed-forces body
#   0.85  a unit or sub-unit of one ("Ministerul Apararii - U.M. 02192")
#   0.70  a defence word that is not the start of the name
# The first matching row wins, so the strongest rows come first. A row with a
# country set is for an abbreviation that means something else elsewhere
# ("Eda" is a Swedish municipality).

_Row = tuple[str, float, re.Pattern, "frozenset[str] | None"]


def _row(label: str, conf: float, countries: str | None, *parts: str) -> _Row:
    return (label, conf, _rx(*parts), frozenset(countries.split()) if countries else None)


DEFENCE_INCLUDE: list[_Row] = [
    _row("ministry", 0.95, None,
         r"^(?:the )?(?:ministry|department|secretary|office) (?:of|for) (?:national |the )?defen[cs]e",
         r"^(?:the )?(?:state )?ministry of (?:national )?defen[cs]e",
         r"^(?:danish|swedish|norwegian|finnish|irish|dutch) (?:ministry|department) of defen[cs]e",
         r"^bundesministerium (?:der verteidigung|fur landesverteidigung|fur verteidigung)",
         r"^bundesministerin fur landesverteidigung|^bundesminister fur landesverteidigung",
         r"^eidgenossisches departement fur verteidigung|^departement federal de la defense",
         r"^ministere (?:des armees|de la defense|de la defense nationale|de l armement)",
         r"^ministerie van (?:defensie|landsverdediging)|^ministerio (?:da|de la|de) defe[sn]",
         r"^ministero della difesa|^ministerul apararii|^ministerstvo obrany|^ministerstwo obrony",
         r"^ministarstvo obrane|^ministrstvo za obrambo|^ministarstvo odbrane|^honvedelmi miniszterium",
         r"^forsvarsministeriet|^forsvarsdepartementet|^forsvarsministerium|^forsvarsmin",
         r"^puolustusministerio|^kaitseministeerium|^aizsardzibas ministrija|^krasto apsaugos ministerija",
         r"^υπουργειο (?:εθνικης )?αμυνας|^министерство на отбраната|^ministry of defen[cs]e",
         r"^service public federal defense|^spf defense|^federale overheidsdienst defensie"),
    _row("ministry", 0.95, "DE", r"^bmvg\b", r"^bundesrepublik deutschland.{0,3}bundesministerium der verteidigung"),
    _row("ministry", 0.95, "FR", r"^mindef\b", r"^minarm\b"),
    _row("armed_forces", 0.95, None,
         r"^(?:the )?(?:irish |swedish |danish |finnish |norwegian |dutch |polish |british |maltese )?"
         r"(?:armed forces|defen[cs]e forces)",
         r"^(?:royal |british |irish |hellenic |polish |swedish |norwegian )?(?:navy|army|air force|marines)\b",
         r"^(?:royal |irish )?naval service|^air corps|^irish defence",
         r"^koninklijke (?:marine|landmacht|luchtmacht)",
         r"^armee de (?:terre|l air|l air et de l espace)|^marine nationale|^armee luxembourgeoise",
         r"^(?:ejercito|exercito|marinha|forca aerea|esercito|marina militare|aeronautica militare)\b",
         r"^(?:bundesheer|streitkrafte|luftwaffe|deutsche marine|marinearsenal)",
         r"^(?:forsvaret|forsvarsmakten|forsvarsmakt|puolustusvoimat|puolustusvoimien|puolustusvoimain)",
         r"^(?:kaitsevagi|kaitseliit|kaitseinvesteeringute|riigi kaitse|lietuvos kariuomen|krasto apsaugos)",
         r"^(?:nacionalie bruninotie speki|valsts aizsardzibas)",
         r"^(?:armada ceske republiky|armada cr|ozbrojene sily|ozbrojenych sil|vojenska policie)",
         r"^(?:oruzane snage|hrvatska vojska|slovenska vojska|slovenski vojski)",
         r"^(?:magyar honvedseg|honvedseg|honved)\b|^vedelmi ",
         r"^(?:armata romaniei|statul major|fortele (?:terestre|aeriene|navale))",
         r"^(?:estado maior|estado-maior)",
         r"^(?:γενικο επιτελειο|πολεμικο ναυτικο|πολεμικη αεροπορια|ελληνικος στρατος|ανωτατη στρατιωτικη)",
         r"^(?:българската армия|сухопътни войски|военноморски сили|военновъздушни сили|генерален щаб)",
         r"^(?:ethniki froura|εθνικη φρουρα)",
         r"^comando (?:aviazione|forze|logistico|trasporti|militare|brigata|operativo)",
         r"^arsenale militare|^\d+\W{0,3}(?:rgt|reggimento|stormo|brigata)\b"),
    _row("military_police", 0.90, None,
         r"military police|военна полиция|zandarmeria militara|feldjager|politia militara",
         r"policia militar|vojenska policie|zandarmeri\w* wojskow|wojskowa zandarmeria"),
    _row("procurement_agency", 0.95, None,
         r"^bundesamt fur ausrustung|baainbw|baiudbw|^bundesamt fur infrastruktur umweltschutz",
         r"^bundesamt fur rustung|^armasuisse|^wehrtechnische dienststelle|^wehrbereichsverwaltung",
         r"direction generale de l armement|^economat des armees|^commissariat des armees",
         r"^service du commissariat des armees|^service d infrastructure de la defense",
         r"^defensie materieel organisatie|^commando materieel|^commando dienstencentra",
         r"^defen[cs]e (?:equipment|procurement|logistics|materiel|acquisition|electronics and components)",
         r"danish defen[cs]e acquisition|forsvarsministeriets materiel|forsvarsministeriets",
         r"^forsvarets materielverk|^forsvarsmateriell|^forsvarets (?:logistik|forsknings|radioanstalt|materiel)",
         r"^agenzia industrie difesa|^segredifesa|^segretariato generale della difesa|^direzione armamenti",
         r"^direcao.geral de (?:armamento|recursos da defesa)|^direccion general de armamento",
         r"^agentura nakupu|^vojenska sprava|^vojensky utvar|^vojensky opravarensky|^lom praha|^vop cz",
         r"^agencja uzbrojenia|^inspektorat wsparcia|^gynybos resursu|^gynybos materialines",
         r"^nato support and procurement|^nato communications and information|^occar\b|^occar-",
         r"^european defen[cs]e agency|^european union military staff",
         r"^joint support|^national armaments|norwegian defen[cs]e (?:materiel|logistics|research)",
         r"^direction generale material resources|^dg material resources|^mrmp|material resources",
         r"^romtehnica|^compania nationala romtehnica|^baza de aprovizionare gospodarire"),
    _row("procurement_agency", 0.95, "FR",
         r"^dga\b", r"^ema (?:dc|sca|dcssa)", r"^sca (?:pf|plate)", r"^sga (?:sd|drh|sid|did|shd|dm)",
         r"^ssf\b", r"^esid\b", r"^dirisi\b",
         r"^saelsi\b", r"^depafi\b", r"^delpia\b", r"^drsid\b", r"^simmt\b", r"^simmad\b",
         r"^marine (?:dcssf|dssf)", r"^plate-?forme affretement", r"^dcssf\b", r"^arm sca"),
    _row("procurement_agency", 0.95, "SE", r"^fmv\b", r"^foi\b"),
    _row("procurement_agency", 0.95, "NL", r"^dmo\b"),
    _row("procurement_agency", 0.95, "DK", r"^dalo\b"),
    _row("procurement_agency", 0.95, "DE", r"^bwi\b", r"^hil\b", r"heeresinstandsetzung",
         r"^bw bekleidungsmanagement"),
    _row("procurement_agency", 0.95, "LV",
         r"^nodrosinajuma valsts agentura", r"^nodrosinajuma pavelnieciba"),
    _row("military_unit", 0.85, "RO",
         r"^(?:ministerul apararii (?:nationale )?)?(?:unitatea militara|u m|um)\s*\d",
         r"^statul major|^baza (?:aeriana|navala|logistica)|^comandamentul"),
    _row("military_unit", 0.85, None,
         r"^(?:vojensk|vojenska|vojenske|vojensky|vojenskeho)\w* ",
         r"^(?:kommando|kommandeur)\b.{0,40}(?:heer|luftwaffe|marine|streitkrafte|bundeswehr)",
         r"^(?:wojskow|jednostka wojskowa|dowodztwo)",
         r"^(?:military|garrison)\b",
         r"^(?:brigada|regimento|batallon|regiment|batalion|brigade)\b",
         r"^(?:военн|военна|военно)\w* ",
         r"^στρατιωτικ\w*"),
    _row("ministry", 0.95, None,
         r"^(?:het |the )?(?:netherlands |nl |nld |danish |uk |swedish |british |irish |polish |norwegian )?"
         r"minister(?:y|ie) (?:of|van) (?:national )?defen",
         r"^minister for defen[cs]e|^(?:swedish|norwegian|danish|finnish|dutch|german|polish) "
         r"defen[cs]e (?:materiel|material|acquisition|aquisition|logistic|research|forces|ministry)",
         r"^(?:danish|norwegian) defen[cs]e",
         r"^министерството на отбраната|^командване на|^служба военн|^военно формирование",
         r"^сухопътни во\w+|^военноморски|^висше военно",
         r"^stato maggiore|^comando delle forze|^direzione del genio militare|^direzione di commissariato"),
    _row("defence_word", 0.70, None,
         r"\bbundeswehr\b|bundeswehr-|der bundeswehr|\bkarrc bw\b",
         r"\bdefensie\b|\bdefen[cs]e forces\b|\barmed forces\b|\bforsvaret\b|\bforsvarsmakt",
         r"\bpuolustusvoim|\bkaitsevag|\bkariuomen|\bnato\b|\bhonvedseg|\bfuerzas armadas\b",
         r"\bforcas armadas\b|\bmilitary\b|\bvojensk|\bmilitare\b|\bmilitar\b",
         r"\bkaitse|\bvalsts aizsardzibas|\bvedelmi|\bgynybos|αμυντικ|\bυπουργειο αμυνας",
         r"ministry of defen[cs]e|defen[cs]e equipment (?:and|&) support|\bde&s\b",
         r"\barmee de terre\b|\binterarmees?\b|service d infrastructure de la defense|\bbase de defense\b",
         r"\bde la defense\b|\bde defense\b|\bdirection de la defense\b|\bdes armees\b",
         r"\besercito\b|\bmarina militare\b|genio militare|commissariato militare",
         r"воен(?:но|на|ни)\b|военно-"),
]

# "Armada spasy" is the Salvation Army, not an armed force.
NOT_DEFENCE = _rx(
    r"armada spasy|salvation army|heilsarmee|armee du salut|esercito della salvezza|leger des heils",
    r"frelsesarme|fralsningsarme|pelastusarmeija|armata salvarii|armija spasenja",
)

DEFENCE_EXCLUDE: list[tuple[str, re.Pattern]] = [
    ("not_defence", NOT_DEFENCE),
    ("civil_protection", CIVIL_PROTECTION),
    ("military_healthcare", HEALTH),
    ("property_agency", PROPERTY),
    ("education", EDUCATION),
    ("fire_rescue", FIRE_RESCUE),
    ("security_service", SECURITY_SERVICE),
]


@dataclass(frozen=True)
class DefenceBody:
    label: str | None          # the include rule that matched; None = not a defence body
    confidence: float          # 0.0 when label is None
    excluded_as: str | None    # set when an exclusion kept a name that otherwise matches


def _first_include(key: str, country: str | None) -> tuple[str, float] | None:
    cc = (country or "").upper()
    for label, conf, rx, countries in DEFENCE_INCLUDE:
        if countries and cc not in countries:
            continue
        if rx.search(key):
            return label, conf
    return None


def defence_body(name: str, country: str | None = None) -> DefenceBody:
    key = folded(name)
    if not key:
        return DefenceBody(None, 0.0, None)
    matched = _first_include(key, country)
    if matched is None:
        return DefenceBody(None, 0.0, None)
    for why, rx in DEFENCE_EXCLUDE:
        if why == "security_service" and matched[0] == "military_police":
            continue
        if rx.search(key):
            return DefenceBody(None, 0.0, why)
    return DefenceBody(matched[0], matched[1], None)


# -------------------------------------------------------- buyer classes
#
# Demoting classes are the ones that buy for themselves, not for the armed
# forces: a municipality, a hospital, a school, a fire brigade. `security` is a
# label and does not demote: police and border bodies do buy equipment that is
# military by CPV, and a supplier wants to see it -- marked.

MUNICIPAL = _rx(
    r"gmina|gminn|miasto|miejsk|powiat|starostwo|urzad miasta|urzad gminy|wojewodz|marszalkowski",
    r"\bstadt\b|stadtverwaltung|gemeinde|landkreis|\bkreis\b|verbandsgemeinde|samtgemeinde|bezirksamt",
    r"senatsverwaltung|regierungsprasidium|landesregierung|\bland \w+ vertreten durch",
    r"commune de|ville de|mairie|communaute (?:de|d)|metropole|conseil (?:departemental|regional)",
    r"departement de|region (?:de|d)|centre communal|syndicat intercommunal|\bccas\b",
    r"ayuntamiento|diputacion|cabildo|comunidad autonoma|generalitat|junta de|gobierno de|ajuntament",
    r"concello|\bconsell\b|mancomunidad|consorcio|area de gobierno|consejeria",
    r"comune di|provincia di|\bregione\b|citta metropolitana|unione dei comuni|unione montana",
    r"gemeente|provincie|waterschap|veiligheidsregio|omgevingsdienst",
    r"camara municipal|municipio|junta de freguesia|comunidade intermunicipal|freguesia",
    r"\bmesto\b|mestsk|\bobec\b|obecni|magistrat|statutarni|hlavni mesto|krajsky urad",
    r"primaria|consiliul judetean|municipiul|orasul|\bcomuna\b|judetean",
    r"община|onkormanyzat|\bvaros\b|megye|\bkommun\b|\bkommune\b|fylkeskommune",
    r"kaupunki|\bkunta\b|kuntayhtyma|maakunta|hyvinvointialue|pasvaldib|novada|pilsetas",
    r"savivaldyb|rajono|\bmiesto\b|\bvald\b|linnavalitsus|\blinn\b|\blinna\b",
    r"opcina|opcine|\bgrad\b|zupanij|obcina|mestna obcina|upravna enota",
    r"\bcouncil\b|\bborough\b|\bcounty\b|municipal|city of|town of|\bdistrict\b|local authority",
    r"δημος|δημου|περιφερεια|δημοτικ|νομαρχ",
    r"samorzad|miejski zarzad|wodociag|komunaln|spolka komunalna",
)

SECURITY = _rx(
    SECURITY_SERVICE.pattern,
    r"administracji skarbowej|zolldirektion|finanzverwaltung|agencia tributaria",
    r"ministry of (?:the )?interior|inrikes|justiz|justitie|justicia|ministerio de justicia",
    r"centralne biuro|agencja bezpieczenstwa|sluzba ochrony|inteligen|intelligence|security service",
    r"ministerio del interior|ministero dell interno|ministere de l interieur|ministerstvo spravedlnosti",
)


@lru_cache(maxsize=100_000)
def buyer_class_of(name: str, country: str | None = None) -> str:
    """One of: defence, security, fire_rescue, health, education, municipal, other.

    Order matters: a military hospital is a hospital, a civil-protection agency is
    not a defence body, and a town that runs its fire brigade is a fire brigade.
    """
    key = folded(name)
    if not key:
        return "other"
    if CIVIL_PROTECTION.search(key) or FIRE_RESCUE.search(key):
        return "fire_rescue"
    # A name that starts with the ministry, an armed force, an agency or a unit is
    # one of theirs even where it goes on to name a hospital or an institute: the
    # exclusions keep such a body off the buyer *list*, they do not make a
    # military uniform bought by the Ministry's medical institute a municipal one.
    first = _first_include(key, country)
    if first and first[1] >= 0.85 and not NOT_DEFENCE.search(key):
        return "defence"
    if HEALTH.search(key):
        return "health"
    if EDUCATION.search(key):
        return "education"
    if defence_body(name, country).label:
        return "defence"
    if SECURITY.search(key):
        return "security"
    if MUNICIPAL.search(key):
        return "municipal"
    return "other"


DEMOTING_CLASSES = frozenset({"municipal", "health", "education", "fire_rescue"})
