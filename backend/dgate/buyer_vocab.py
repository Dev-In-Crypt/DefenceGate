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
    r"brannvesen|brann og redning|\bcgdis\b|incendie et de secours|katasztrofavedelm|zachranny utvar",
    r"morska sluzba poszukiwania|ratownictwa|ratownicz|pogotowie ratunkowe|\b110-?sentral",
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
    r"klinicni|klinick|kliniczn|bolnisnic|bolnice\b|dom upokojencev|zdravstveni dom|nursing home",
)

EDUCATION = _rx(
    r"universit|uniwersytet|politechnik|hochschule|fachhochschule",
    r"\bschool\b|\bcollege\b|szkola|szkoly|szkole|schule\b|schulen|ecole\b|lycee",
    r"escuela|colegio|scuola|istituto (?:comprensivo|scolastico|d istruzione)",
    r"\bskola\b|\bskolen\b|\bskole\b|koulu|gymnas|gymnazium|fakult",
    r"language school|sprachen|jezykow|studentenwerk|studentski",
    r"университет|училищ|школа|гимнази|πανεπιστημι|σχολη|σχολεια",
    r"research (?:council|centre|institute)|forschung|badawcz|wetenschapp",
    r"egyetem|universidade|universidad\b|univerzit|veleuciliste|zespol szkol|\bzsti?o?\b",
    r"technikum|centrum ksztalcenia|utbildning|yliopisto|universiteit|universitet|rectorado",
)

# Military property and estate agencies buy buildings, land and maintenance: real
# money, not the defence supply chain. Kept out of the list on purpose. One exception,
# by the owner's decision of 14 October 2026: Forsvarsbygg (the Norwegian Defence Estates
# Agency) is a defence buyer (DEFENCE_INCLUDE, label `defence_estates_agency`), so its
# notices qualify into `supply`; it never reaches `core` on the buyer signal alone.
PROPERTY = _rx(
    r"agencja mienia wojskowego|wojskowa agencja mieszkaniow|agencja nieruchomosci",
    r"bundesanstalt fur immobilienaufgaben|\bbima\b|bundesamt fur bauwesen|amt fur bundesbau",
    r"bau- ?und liegenschaft|baumanagement|liegenschaftsbetrieb|landesbetrieb|bauamt|hochbauamt",
    r"defen[cs]e (?:infrastructure organi[sz]ation|estates)|\bdio\b|infrastructure organi[sz]ation",
    r"fortifikationsverket|forsvarets ejendom|ejendomsstyrelse|puolustushallinnon rakennuslaitos",
    r"defence estates|estates agency|agentura hospodareni s nemovitym majetkem|agentura pre majetok",
    r"direction de l immobilier|agence immobiliere|immobilienaufgaben",
    # The French Defence Infrastructure Service (SID, ESID, DCSID...) was listed here until
    # 15 October 2026: the owner decided that it is a defence buyer (DEFENCE_INCLUDE,
    # `defence_infrastructure_service`), like Forsvarsbygg, and it qualifies into `supply`.
    r"cercle (?:national|de la base|interarmees|mixte)|coordination de defense des services sociaux",
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
    # Gaps found reading the buyers that the CPV-group demotion of 13 October 2026 would
    # have caught: a police authority, a prison service or a customs office whose class was
    # `other` is a security body, kept in core as before (classification:D3 is the owner's).
    r"\bpolis\b|polismyndighet|rendor|policejn|penitentiar|penitenzi|kriminalforsorg",
    r"kriminalvard|fangsel|\bjva\b|justizvollzugsanstalt|tullverket|tolletaten|\btulli\b",
    r"\bdgddi\b|reditelstvi cel|robezsardz|home affairs|citizen protection|protection du citoyen",
    r"ochrony rzadu|ochrony panstwa|\bpp elt\b|ministerium des innern|innern und",
    r"beschaffungsamt des bundesministeriums des innern|landesamt fur innere verwaltung",
    r"национална служба за охрана|борба с организираната|гдбоп|προστασιας του πολιτη",
    r"αντεγκληματικ|\bjustis\b|department of justice|ministerul justitiei|ministrstvo za pravosodje",
    r"ministarstvo pravosu|ministerstvo spravedlnosti",
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
         r"^(?:royal (?:netherlands |danish |norwegian )?|british |irish |hellenic |polish |swedish "
         r"|norwegian )?(?:navy|army|air force|marines)\b",
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
         # Belgian Defence's "Material Resources" directorate. Not the bare phrase: any
         # hospital or university department of "human and material resources" has it.
         r"direction generale material resources|^dg material resources|^mrmp",
         r"defen[cs]e.{0,30}material resources",
         r"^romtehnica|^compania nationala romtehnica|^baza de aprovizionare gospodarire"),
    _row("procurement_agency", 0.95, "FR",
         r"^dga\b", r"^ema (?:dc|sca|dcssa)", r"^sca (?:pf|plate)", r"^sga (?:sd|drh|sid|did|shd|dm)",
         r"^ssf\b", r"^esid\b", r"^dirisi\b",
         r"^saelsi\b", r"^depafi\b", r"^delpia\b", r"^drsid\b", r"^simmt\b", r"^simmad\b",
         r"^marine (?:dcssf|dssf)", r"^plate-?forme affretement", r"^dcssf\b", r"^arm sca",
         r"^plate-?forme (?:du )?commissariat", r"^dicom\b"),
    # France (15 October 2026, coverage:X1). Real buyer strings read from the BOAMP
    # organisations of the production database; every row has a test with them. The
    # families are those of the Ministry of the Armed Forces (the SGA's purchasing
    # services, the SCA platforms, the SSA's central supply, the DGA, the DIRISI, the
    # infrastructure service) and the bodies it supervises that buy for themselves.
    # Not included, and why: the gendarmerie (Interior; a security class), military
    # hospitals and schools, social clubs ("cercle"), the CEA, the SGDSN, the Paris
    # business district.
    _row("ministry", 0.95, "FR",
         r"^(?:etat\W+|l acheteur public est l etat\W+)?min\w*(?:ere|re)s? (?:des armee|de la defense)",
         r"^(?:etat\W+)?min(?:arm|d[a-z]{2,7}|ar)\b",
         r"^min(?:istere)? defense\b",
         r"^armees?$|^defense (?:etat|nationale|mobilite)|^defense$",
         r"^(?:defense )?etat[- ]major (?:des armees|de l armee|de la marine)"),
    _row("defence_infrastructure_service", 0.90, "FR",
         r"(?:^|\W)(?:service|direction|etablissement)(?: (?:central|regional)e?)?(?: du)?"
         r"(?: service)?(?: d| de l| de la)? ?i+nfra\w* (?:de )?la ?defense",
         r"^etablissement du service de la defense",
         r"^(?:direction|service) (?:centrale|regionale) (?:du )?service d ?i+nfra",
         r"^(?:dcsid|esid|drsid|usid)\b",
         r"^did\b(?:\W+(?:sds|fdf|cayenne|papeete|de|fort|saint|nouvelle)\b)",
         r"^sga[ -]+(?:minarm[ -]+)?(?:dcsid|sid)\b",
         r"^sid(?:[ -]+(?:epn|expertise|idf|ne|se|so|no|n-o|s-e|med|atl\w*|nord|sud|mediterranee"
         r"|ile|sve)\b|$)",
         r"agissant (?:en qualite de mandataire de l etat|au nom et pour le compte).{0,260}"
         r"(?:service d infrastr\w+ de la defense|\bsid\b|ministere des armees)"),
    # The central supply of the Armed Forces Health Service. Its names say "sante": the
    # health exclusion does not apply (EXEMPT); a hospital or a transfusion centre never
    # matches these patterns. Before the procurement row: the first match names the label.
    _row("health_supply_agency", 0.95, "FR",
         r"\bdapsa\b|direction des approvisionnements? en produits? de sante des armees",
         r"^(?:(?:ema|minarm|mindef|sga)[ -]+)*(?:dcssa|ssa)[ -]+(?:dapsa|daps)",
         r"^direction centrale du service de sante des armees|^pfaf[- ]?(?:s|sante)\b"),
    _row("procurement_agency", 0.95, "FR",
         r"^plate[- ]?forme (?:du )?commissariat|^plate[- ]?forme (?:achats|affretement)",
         r"^pfc\b|^pfaf\b|^dcsca\b|^sca (?:pfaf|pfc|gsbdd|plate|dcsca|so)\b",
         r"^service du commissariat des armees|^direction centrale du service du commissariat",
         r"^direction du commissariat (?:d outre|des forces armees)",
         r"^ema[ -]+(?:dc|sca|dcssa|ssa|dcdirisi|dapsa|dseo)\b|^dcsea\b|^dseo\b",
         r"^direction interarmees des reseaux d infrastructure|^commissariat au numerique de defense",
         r"^service interarmees? des munitions|^simu\b|^service des essences des armees",
         r"^service de l energie operationnelle|^service industriel de l aeronautique",
         r"^structure integree du maintien en condition operationnelle|^service de maintenance"
         r" industrielle terrestre|^service de soutien de la flotte",
         r"^service parisien de soutien de l administration centrale|^spac\b",
         r"^etablissement de communication et de production audiovisuelles? de la defense",
         r"^ecpad\b|^epa ecpad|^section technique de l armee de terre"),
    _row("base_support_group", 0.90, "FR",
         r"gsbdd|^gsdbb\b|^groupement (?:de )?soutien (?:de la )?base de defense",
         r"^service soutien vie gsbdd"),
    # Bodies the Ministry supervises: a social management agency, a veterans' office.
    # They are the Ministry's, and supply-scope only (a buyer signal never reaches core).
    _row("ministry_affiliated", 0.85, "FR",
         r"^igesa\b|^institution de gestion sociale des armees",
         r"^onac(?:vg|etamp)?\b|^onac ?(?:&|et) ?vg|^epa onacvg",
         r"^office national des (?:anciens )?combattants et (?:des )?victimes de guerre"),
    # Units: a number leads, then the unit type. The regiments of the "service militaire
    # adapte" (overseas youth service run in military form) were on the derived list before
    # and stay; whether they are armed forces is the owner's call, not this change's.
    _row("military_unit", 0.90, "FR",
         r"^\d+(?:e|er|ere|eme|\W{0,2}me)?\W{0,2}(?:regiment|rgt|rima|rpima|rcp|rch|rei|bataillon"
         r"|escadre|escadron|brigade|base aerienne|base navale|groupement de soutien)\b",
         r"^(?:regiment|escadre|escadron|bataillon|base aerienne|base navale|base de defense)\b"),
    # The Netherlands: the Ministry files under its bare name too ("Defensie", one
    # organisation, unflagged on 15 October 2026). The academy is education, as everywhere.
    _row("ministry", 0.95, "NL",
         r"^defensie$", r"^defensie (?:ondersteuningscommando|vastgoed|nederland)\b",
         r"^dienst vastgoed defensie"),
    _row("defence_estates_agency", 0.90, "NO", r"^forsvarsbygg\b"),
    _row("procurement_agency", 0.95, "SE", r"^fmv\b", r"^foi\b"),
    _row("procurement_agency", 0.95, "NL", r"^dmo\b"),
    _row("procurement_agency", 0.95, "DK", r"^dalo\b"),
    _row("procurement_agency", 0.95, "DE", r"^bwi\b", r"^hil\b", r"heeresinstandsetzung",
         r"^bw bekleidungsmanagement"),
    # The Ministry's supply contractor: files its notices "Leidos Supply Ltd on behalf of
    # the UK Ministry of Defence" (classification:D2 sample, 62835).
    _row("procurement_agency", 0.90, "GB", r"^leidos supply"),
    _row("procurement_agency", 0.95, "HU", r"vedelemgazdasagi hivatal",
         r"^hm (?:vedelemgazdasagi|elektronikai|ei)\b"),
    _row("procurement_agency", 0.95, "LV",
         r"^nodrosinajuma valsts agentura", r"^nodrosinajuma pavelnieciba"),
    _row("military_unit", 0.85, "RO",
         r"^(?:ministerul apararii (?:nationale )?)?(?:unitatea militara|u m|um)\s*\d",
         r"^statul major|^baza (?:aeriana|navala|logistica)|^comandamentul"),
    _row("military_unit", 0.85, None,
         r"^(?:vojensk|vojenska|vojenske|vojensky|vojenskeho)\w* ",
         r"^(?:kommando|kommandeur)\b.{0,40}(?:heer|luftwaffe|marine|streitkrafte|bundeswehr)",
         r"^(?:wojskow|jednostka wojskowa|dowodztwo)",
         r"^(?:military|garrison)\b", r"^ввму|^висше военноморско",
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
    # Added 13 October 2026 (classification:D12, coverage:C2). Services and offices of the
    # armed forces that carry the Bundeswehr's name sat at 0.70 (a defence word somewhere
    # in the name) and so under the 0.80 loading floor: 185 service centres, none flagged.
    # Not promoted, and so still reviewed by a person: the recruiting offices, the personnel
    # office and the training and fire-protection centres, which buy for themselves.
    _row("armed_forces_service", 0.90, "DE",
         r"^bundeswehr[ -]?dienstleistungszentrum|^bwdlz\b",
         r"^v(?:er)?pflegungsamt der bundeswehr|^verlegungsamt der bundeswehr",
         r"^bundes?amt f(?:ur)? (?:aus+rustung|informationstechnik|infomationstechnik|infrastruktur)"
         r".{0,60}der bundeswehr$",
         r"^planungsamt der bundeswehr|^zentrum fur geoinformationswesen der bundeswehr",
         r"^(?:lh )?bundeswehr bekleidungsgesellschaft"),
    # Polish air bases and regional infrastructure boards (RZI) of the Ministry: unit
    # numbers lead the name, which no rule above reads. Poland's list itself is
    # derived by its own rules (ops/derive_buyers.py); these rows give the class.
    _row("military_unit", 0.90, "PL",
         r"^\d+ ?(?:regionalna baza logistyczna|baza lotnictwa|wojskowy oddzial gospodarczy)",
         r"^rejonowy zarzad infrastruktury|^baza lotnictwa"),
    # Spain's contracting boards and intendances of the three services.
    _row("armed_forces_service", 0.90, "ES",
         r"^junta de contratacion del (?:ejercito|aire|ministerio de defensa)",
         r"^junta de contratacion de la armada|^junta (?:tecnico economica|de compras) .{0,30}"
         r"(?:ejercito|armada|aire)",
         r"^intendente de |^organo de contratacion intendente|^jefatura de intendencia",
         r"^jefatura del apoyo logistico|^mando de apoyo logistico|^direccion de adquisiciones del mando",
         r"^direccion general del inta\b|^instituto nacional de tecnica aeroespacial"),
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
# "DGA" is the French armament agency, and also the "direction generale de l administration"
# of the Council of Europe and a "direction generale adjointe" of France Travail: 197 and 7
# notices of those two were flagged as defence on 13 October 2026.
NOT_DEFENCE = _rx(
    r"armada spasy|salvation army|heilsarmee|armee du salut|esercito della salvezza|leger des heils",
    r"frelsesarme|fralsningsarme|pelastusarmeija|armata salvarii|armija spasenja",
    r"council of europe|conseil de l europe|france travail|pole emploi",
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


# Exclusions that do not apply to a label: the estates agency's name says "estates"; the
# infrastructure service's says "infrastructure"; the SSA's central supply bodies name the
# health service they supply (never a hospital: the patterns are anchored on the bodies).
EXEMPT: dict[str, frozenset[str]] = {
    "defence_estates_agency": frozenset({"property_agency"}),
    "defence_infrastructure_service": frozenset({"property_agency"}),
    "health_supply_agency": frozenset({"military_healthcare"}),
}


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


# French registration numbers (SIREN, nine digits) that belong to the Ministry's own services,
# read from the organisations the database holds under them (15 October 2026): every
# organisation under one of them is a service of the Ministry of the Armed Forces by name.
# Not the Ministry's own number (110002011): the Conseil d'Etat and the interior ministry's
# regional services state it too. Used only when the name says nothing: "DID CAYENNE".
DEFENCE_SIREN_FR = {
    "130001902": "defence_infrastructure_service",   # SID, DCSID, DID, DRSID, ESID
    "130008899": "procurement_agency",               # Service du commissariat des armees
    "130015340": "procurement_agency",               # SCA platforms (PFAF, affretement)
    "130015370": "procurement_agency",
    "130015373": "procurement_agency",
    "130015399": "procurement_agency",
    "151000023": "health_supply_agency",             # DAPSA
}


def defence_body_by_identifier(identifier: str | None, country: str | None) -> DefenceBody:
    """A body whose registration number is one of the Ministry's own services'."""
    digits = "".join(c for c in (identifier or "") if c.isdigit())
    label = DEFENCE_SIREN_FR.get(digits[:9]) if (country or "").upper() == "FR" else None
    return DefenceBody(label, 0.90, None) if label else DefenceBody(None, 0.0, None)


def defence_body(name: str, country: str | None = None,
                 identifier: str | None = None) -> DefenceBody:
    key = folded(name)
    if not key:
        return DefenceBody(None, 0.0, None)
    matched = _first_include(key, country)
    if matched is None:
        return defence_body_by_identifier(identifier, country)
    for why, rx in DEFENCE_EXCLUDE:
        if why == "security_service" and matched[0] == "military_police":
            continue
        if why in EXEMPT.get(matched[0], ()):
            continue          # "Forsvarsbygg - the Norwegian Defence Estates Agency"
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
    # "Ville d'Orleans" folds to "ville d orleans": the elided article is part of the pattern
    # (classification:D5, 96 notices from French towns carried class `other`).
    r"commune (?:de|d)\b|ville (?:de|d)\b|mairie|communaute (?:de|d)|metropole|conseil (?:departemental|regional)",
    r"departement (?:de|d)\b|region (?:de|d)|centre communal|syndicat intercommunal|\bccas\b",
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


# Infrastructure operators: airports and air-navigation providers, road and rail
# authorities and operators, ports and maritime administrations, meteorological
# services, water, energy, waste and postal utilities. They buy radar, command-and-control
# and "military" aircraft or vehicle codes for civil purposes (classification:D6 of
# 13 October 2026: 863 core rows by name, the Polish road authority's works alone 166,
# all carrying 35710000). Whole words or distinctive stems; a name that begins with a
# defence body never gets here (the first-include check in buyer_class_of).
INFRASTRUCTURE = _rx(
    r"airport|aeroport|flughafen|lotnisk|port lotniczy|aeropuerto|letiste|letisko|luchthaven",
    r"lufthavn|lentoasema|lentokentta|flygplats|swedavia|avinor|finavia|\baena\b|\bpansa\b",
    r"navigation aerienne|flugsicherung|air traffic|skyguide|eurocontrol|austro control",
    r"generalny dyrektor drog|dyrekcja drog|zarzad drog|\bgddkia\b|drog krajowych",
    r"road (?:authority|administration|agency|directorate|operator)|\bhighways?\b|autobahn",
    r"autoroute|strassenbau|strassenverkehr|strassen nrw|rijkswaterstaat|trafikverket|vegvesen",
    r"vejdirektorat|vaylavirasto|ceske drahy|sprava zeleznic|sprava silnic|ridicstvi silnic",
    r"zeleznic|railway|\brail\b|kolej|\bbahn\b|\bsncf\b|ferrovi|chemin de fer|\bvasut\b|\bcfr\b",
    r"infrabel|prorail|network rail|\bpkp\b|\brenfe\b|\badif\b",
    r"public transport|transports? publics?|verkehrsbetriebe|verkehrsverbund|tramwaj|autobus",
    r"\bmetro\b|\bztm\b|\bmpk\b|zarzad transportu|urzad morski|maritime administration",
    r"sjofartsverket|port authority|\bhafen\b|\bhavn\b|\bport of\b|harbour",
    r"meteorolog|\bmeteo\b|wetterdienst|\bmet office\b|\bsmhi\b|\bimgw\b|\bknmi\b",
    r"wodociag|wasserwerk|stadtwerke|water (?:company|board|utility|supply|authority)",
    r"waterbedrijf|\benerg[ai]\b|\btauron\b|\bpge\b|energet|elektrown|electricity|power grid",
    r"\benea\b|\borlen\b|vattenfall|veolia|\bsuez\b|\bedf\b|enedis|\bengie\b|eneco|\brwe\b",
    r"iberdrola|abwasser|kanalisation|odpad|waste (?:management|authority)|poczta polska",
    r"\bpostnl\b|\bsewage\b|parkeringsselskab|\bparking\b|parkerings",
    r"kontrola zracn|legiforgalm|hungarocontrol|naviair|\benaire\b|autoridad portuaria",
    r"puertos del estado|kystverk|dopravny podnik|dopravni podnik|tisseo|sytral|\bsiaap\b",
    r"gasunie|\bervia\b|slovenske elektrarne|\bmvm\b|kopaln|teplarn|acquedotto|met eireann",
    r"miljodirektorat|kartverk|seaports|autoceste|avtocest|vodovod|romsilva|public works",
    r"regionalna dyrekcja ochrony srodowiska|park narodowy|national park|nationalpark",
    r"железопътна инфраструктура|пътна инфраструктура|\bтец\b|\bтец",
)

# Embassies, consulates, EU institutions and international organisations: a notice by
# an embassy is a building or services contract abroad (classification:D13: 166 core
# rows, 156 with a military CPV). NATO bodies and the European Defence Agency are
# defence procurement bodies and are named in DEFENCE_INCLUDE, which is checked first.
INTERNATIONAL = _rx(
    r"embassy|ambassade|ambasada|botschaft|ambasciata|embajada|embaixada|velvyslanectvi",
    r"suurlahetyst|sendiraad|konsulat|consulate|\bconsulat\b|konzulat|consolato",
    r"permanent representation|representation permanente|delegation of the european union",
    r"european (?:commission|parliament|council|investment bank|court)",
    r"commission europeenne|parlement europeen|council of europe|conseil de l europe",
    r"united nations|\boecd\b|\bocde\b|\bunesco\b|\bunicef\b",
    r"space agency|satellite cent|agency for the space programme|gnss agency|maritime safety agency",
    r"external action service|\beeas\b|europol|european union agency|european external",
    r"deutsche gesellschaft fur internationale zusammenarbeit|\bsida\b|central finance and contracts",
)

# Institutions of the armed forces that carry their name. The buyer *list* keeps the
# military universities out (education), but the label must not call the armed
# forces' own university civil: 20 of the 29 Universitat der Bundeswehr rows were
# demoted as `education` although the customer is the Bundeswehr (classification:D11).
ARMED_FORCES_INSTITUTION = _rx(
    r"universitat der bundeswehr|bundeswehr universitat|helmut schmidt universitat",
)


def effective_buyer_class(name: str, country: str | None, listed: bool) -> str:
    """The class stored on a notice: the name's class, except that a body the defence
    buyer list holds is a defence body. 71,504 notices from listed buyers carried
    `other` because only the name was asked (classification:D8 of 13 October 2026).
    Only `other` is overridden: a listed body whose name says hospital or school keeps
    that label, which is the better warning."""
    cls = buyer_class_of(name, country)
    if listed and cls == "other":
        return "defence"
    return cls


@lru_cache(maxsize=100_000)
def buyer_class_of(name: str, country: str | None = None) -> str:
    """One of: defence, security, fire_rescue, health, education, municipal,
    infrastructure, international, other.

    Order matters: a military hospital is a hospital, a civil-protection agency is
    not a defence body, and a town that runs its fire brigade is a fire brigade.
    """
    key = folded(name)
    if not key:
        return "other"
    if CIVIL_PROTECTION.search(key) or FIRE_RESCUE.search(key):
        return "fire_rescue"
    if ARMED_FORCES_INSTITUTION.search(key):
        return "defence"
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
    if INTERNATIONAL.search(key):
        return "international"
    if INFRASTRUCTURE.search(key):
        return "infrastructure"
    if defence_body(name, country).label:
        return "defence"
    if SECURITY.search(key):
        return "security"
    if MUNICIPAL.search(key):
        return "municipal"
    return "other"


DEMOTING_CLASSES = frozenset({
    "municipal", "health", "education", "fire_rescue", "infrastructure", "international",
})
