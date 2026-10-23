"""Which organisation rows are one body (display layer only, WP-22).

A pure function over (country, normalised name). It decides nothing about the data: the
rows stay as they are and `ops/buyer_families.py` stores the result in `buyer_family_member`,
which the buyer list reads. Explicit rules, no fuzzy matching, no similarity score and no
grouping across countries; a wrong group is worse than none, so a rule that cannot be
defended from the names alone is not here.

Rules, strongest first:

  named agency   a short list written as regular expressions, each with the reason it is
                 one body (confidence 0.90)
  fr_ministry    French names carry the ministry's own prefix (`minarm`, `mindef`) and
                 sometimes its title as a suffix; with those removed the same service has
                 one name (0.90)
  identical_name the same normalised name in the same country (0.95)
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .buyer_vocab import buyer_class_of


@dataclass(frozen=True)
class Family:
    key: str            # rows with the same key are one family
    method: str         # the rule, stored with the member
    confidence: float


IDENTICAL = 0.95
RULE = 0.90

# (name, country, pattern on the normalised name, why it is one body)
NAMED: tuple[tuple[str, str, re.Pattern[str], str], ...] = (
    # The Federal Office for Bundeswehr Equipment, IT and In-Service Support. Its desks
    # (K2 4, G2 1, E3 6 ...), its Koblenz seat, its tender collection point and the
    # misspelt long names (the notices are typed by hand) are all the one federal office.
    ("baainbw", "DE", re.compile(r"^(?:baainbw\b|bundesamt fu(?:r|er) ausr(?:u|ue)stung\b)"),
     "one federal office; the names begin with its name or its abbreviation"),
    # The Navy arsenal: two sites (Wilhelmshaven, Rostock/Warnowwerft), one authority.
    ("marinearsenal", "DE", re.compile(r"^marinearsenal\b"),
     "one authority with two sites, both named after it"),
    # Heeresinstandsetzungslogistik GmbH, written with or without its abbreviation.
    ("hil", "DE", re.compile(r"^(?:hil )?heeresinstandsetzungslog\w*$"),
     "one company, with and without its abbreviation (and one typo)"),
    # BW Bekleidungsmanagement GmbH (BwBM), the Bundeswehr's clothing company.
    ("bwbm", "DE", re.compile(r"^(?:bw bekleidungsmanagement|bwbm)\b"),
     "one company, written in full or by its abbreviation"),
    # The Polish Armament Agency; 'Skarb Panstwa' is the State Treasury, the owner the
    # budget unit signs for, and one record carries a removed e-mail address after the name.
    ("agencja_uzbrojenia", "PL", re.compile(r"^(?:skarb panstwa\s*-?\s*)?agencja uzbrojenia\b"),
     "one budget unit, with and without the State Treasury in front"),
)

# Renamed bodies (WP-87, owner decision of 22 October 2026): a curated list of a predecessor's names and the family of
# its successor, each with the evidence and a confidence that are stored with the member (`buyer_family_member.method`
# is `curated_rename`). Read by `family_of` before the rules above; the ops command `dgate.ops.curated_renames` reports
# what it covers. Display layer only, like every family: no organisation row is merged.
CURATED_RENAME = "curated_rename"
RENAMES: tuple[tuple[str, re.Pattern[str], str, float, str], ...] = (
    # The Armament Inspectorate (Inspektorat Uzbrojenia) became the Armament Agency (Agencja Uzbrojenia) on
    # 1 January 2022: the same budget unit of the Ministry of National Defence, the same procurement desk in Warsaw.
    ("PL", re.compile(r"^(?:skarb panstwa\s*-?\s*)?inspektorat uzbrojenia\b"), "agencja_uzbrojenia", 0.95,
     "Inspektorat Uzbrojenia was renamed Agencja Uzbrojenia on 1 January 2022 (Ministry of National Defence)"),
)

_FR_PREFIX = re.compile(r"^(?:minarm|mindef) ")
_FR_SUFFIX = re.compile(r" ministere (?:des armees|de la defense)\b(.*)$")
# A suffix that goes on to name a division, a site or a production pole describes a
# sub-unit, not the service in front of it: those names are left whole.
_FR_SUBUNIT = re.compile(r"\b(?:division|site|prod|pole|da-\w+)\b")


def _fr_stripped(name: str) -> str:
    out = _FR_PREFIX.sub("", name, count=1)
    m = _FR_SUFFIX.search(out)
    if m and m.start() > 0 and not _FR_SUBUNIT.search(m.group(1)):
        out = out[:m.start()]
    return out


def family_of(country: str | None, name: str | None) -> Family | None:
    """The family a (country, normalised name) belongs to, or None for an empty name.
    A family of one row is not a family: the caller keeps only keys with two rows."""
    c = (country or "").strip().upper()
    n = (name or "").strip()
    if not c or not n:
        return None
    for country_, pattern, label, confidence, _evidence in RENAMES:
        if c == country_ and pattern.search(n):
            return Family(f"{c}:rule:{label}", CURATED_RENAME, confidence)
    for label, country_, pattern, _why in NAMED:
        if c == country_ and pattern.search(n):
            # "rule:" cannot occur in a normalised name, so a row that is merely called "hil"
            # never lands in the key of the HIL rule
            return Family(f"{c}:rule:{label}", f"rule:{label}", RULE)
    if c == "FR":
        stripped = _fr_stripped(n)
        if stripped and stripped != n:
            return Family(f"{c}:{stripped}", "fr_ministry", RULE)
    return Family(f"{c}:{n}", "identical_name", IDENTICAL)


def family_key(country: str | None, name: str | None) -> str | None:
    f = family_of(country, name)
    return f.key if f else None


# ------------------------------------------------------------- public bodies and their units
#
# A tax id proves one legal entity, not one buyer: a regional government, a ministry or a city
# council files every department under its one number (WP-74: on 21 October 2026 the merge of rows
# sharing a number put the Basque Government's 116 departments under 'gobierno vasco - seguridad').
# Such rows are never merged by a shared number (`ops/accept_merge_candidates`, refusal
# `public_body`); `ops/buyer_families` shows them as one buyer under the parent body's name
# (rule `shared_tax_id`). Names are the stored form: lower case, accents folded.

SHARED_TAX_ID = "shared_tax_id"

# a name that names a unit of a body: a department, a directorate, a service, a branch
SUB_UNIT = re.compile("|".join((
    r"\bdepartamento?\b|\bdepartament\b|\bconsejeria\b|\bconselleria\b|\bviceconsejeria\b",
    r"\barea de gobierno\b|\bdireccion\b|\bsubdireccion\b|\bdelegacion\b|\bgerencia\b",
    r"\bsecretaria general\b|\bservicio de\b|\bservei de\b|\bconcejalia\b|\bregidoria\b",
    r"\btenencia de alcaldia\b|\bdistrito\b|\bdistricte\b|\bunidad de contratacion\b",
    r"\bdirezione\b|\bdipartimento\b|\bsettore\b|\bservizio\b|\bufficio\b|\bdivisione\b",
    r"\bprovveditorato\b|\bassessorato\b|\bstazione unica appaltante\b|\bu d\b",
    r"\bdirection\b|\bsous-direction\b|\bsecretariat general\b|\bservice (?:de|d|des|du)\b|\bpole\b",
    r"\bdelegation (?:regionale|territoriale|departementale)\b|\bdirection territoriale\b",
    r"\babteilung\b|\babt\b|\bfachbereich\b|\bfachdienst\b|\breferat\b|\bdezernat\b|\bamt fur\b",
    r"\bsachgebiet\b|\bdienststelle\b|\bniederlassung\b|\blandesstelle\b|\bdienstort\b|betriebsstelle",
    r"\balue\b|\bvestiging\b",
    r"\bafdeling\b|\bdirectie\b|\blocatie\b|\bdirectia\b|\bdirectiei\b|\bsucursala\b|\bserviciul\b",
    r"\bdirecao\b|\bdivisao\b|\bwydzial\b|\bdepartament\b|\boddzial\b|\bdelegatura\b|\bdzielnica\b",
    r"\bodbor\b|\boddeleni\b|\bpobocka\b|\bmestsky obvod\b|\bmestska cast\b",
    r"\bavdeling\b|\bavdelning\b|\bforvaltning\b|\bosasto\b|\bdivisjon\b|\benhed\b",
    r"\bdepartment\b|\bdirectorate\b|\bdivision\b|\boffice of\b",
    r"териториално поделение|\bтп\b|дирекция|филиал|\bотдел\b|διευθυνση|τμημα|περιφερειακη ενοτητα",
)))

# a name that says public authority (the classes of `buyer_vocab.buyer_class_of` cover towns,
# regions, hospitals, schools, police, ministries of the interior and justice, armed forces)
PUBLIC_NAME = re.compile("|".join((
    r"minist|министерств|υπουργ|\bgobierno\b|\bgovern|regierung|\bsenat|\bjunta\b",
    r"\bagenzia\b|\bagencia\b|\bagence\b|\bagentia\b|\bagency\b|\bagentur\b|\bagencja\b|агенци",
    r"\bcommunaute\b|\bagglo|intercommunal|\bsyndicat mixte\b|\bcias\b|\bparc naturel\b",
    r"landratsamt|\w+kreis\b|\bstad\b|\bstads|^region\b|etaten\b|verket\b|direktorat|styrelsen\b",
    r"myndighet|virasto\b|\blaitos\b|\buniversit|\bhogeschool\b|\bdiensten\b|\bassociatie\b",
    r"\bdepartement\b|landesbetrieb|landesbehorde|\blra\b|\breditelstvi\b",
    r"bundesamt|landesamt|landesverwaltung|\bamt der\b|\bland \w+$|\bfreistaat\b|\bfreie hansestadt\b",
    r"\badministracion\b|\badministration\b|\bamministrazione\b|\badministracao\b",
    r"\brijks|\bstatens\b|staatsbetrieb|\bstaat\b|\bstato\b|\bestado\b|\betat\b|\brepublik|\brepublic",
    r"\bskarb panstwa\b|\burzad\b|\burad\b|\bstatni\b|\bdrzavn|\bдържавн|\bdirectoratul\b",
    r"\bprefecture\b|\bprefettura\b|\bservicio (?:andaluz|vasco|canario|navarro|madrileno)\b",
    # WP-76: the words of the administrations that `buyer_class_of` does not class, per language
    # (two Dutch government units were merged in the sample of WP-74: 'ubr his', 'ssc iuc dji')
    r"\bgemeente|\bministerie\b|rijkswaterstaat|\bprovincie\b|waterschap|hoogheemraadschap|\bdienst\b",
    r"\bzbo\b|uitvoeringsorganisatie|\binspectie\b|belastingdienst|\bvng\b|veiligheidsregio",
    r"\bbehorde\b|\bamt\b|\bamter\b|\bstadt\b|landkreis|\bgemeinde\b|kreisverwaltung|zweckverband",
    r"landeshauptstadt|bezirkshauptmannschaft|bezirksregierung|\bmagistrat|\bbund\b|bundes\w+",
    r"\bministere\b|\bdirection\b|\bcommune\b|\bmairie\b|\bdepartement\b|\bconseil (?:departemental|regional"
    r"|general|municipal|de (?:gouvernement|l europe))|\bregion (?:de|d|des|du)\b|\bcentre de gestion\b",
    r"\brectorat\b|\bacademie (?:de|d)\b|office public|\bsdis\b|\bccas\b|\bsivu\b|\bsivom\b|\bsictom\b",
    r"\bcomune\b|\bprovincia\b|\bregione\b|\bente\b|\bcentrale unica\b|\bcuc\b|camera di commercio",
    r"\bquestura\b|\bautorita\b|\bconsorzio di bonifica\b|\baler\b|\bater\b|\biacp\b|case popolari",
    r"\bayuntamiento\b|\bdiputacion\b|\bcabildo\b|\bconsell\b|\bconsejo (?:de gobierno|insular|comarcal)",
    r"\bgeneralitat\b|\bxunta\b|\bconcello\b|\bmancomunidad\b|\balcaldia\b|\bpleno\b|\bmesa del\b",
    r"\brectorado\b|\bcomarca\b|\bconcejo\b|\bcomunidad (?:autonoma|de madrid)",
    r"\burzad\b|\bgmina\b|\bgminn|\bstarostwo\b|\bwojewodzk|\bwojewodztw|\bpowiat|\bkomenda\b",
    r"jednostka wojskowa|\bmiasto\b|\bmiejsk|\bzarzad (?:drog|dzielnicy|zlewni|transportu|budynkow)",
    r"\bsad (?:rejonowy|okregowy|apelacyjny)|\bprokuratur|\bnadlesnictwo\b|lasy panstwowe",
    r"\b(?:generalna|regionalna) dyrekcja\b|\bosrodek pomocy\b|\binspektorat\b|\bsamorzad",
    r"\bmesto\b|\bobec\b|\bkraj\b|\bkrajsk|\bministerstvo\b|\bsprava\b|\bobvodni\b|\bmestsk",
    r"\bkommun\b|\bkommune\b|\bregion \w+|\blandsting|lansstyrelsen|\bkaupunki\b|\bkunta\b|kuntayhtyma",
    r"hyvinvointialue|\bmaakunta|\bkeskus\b|\bministerio\b|ministeriet\b|fylkeskommune|\bdirektoratet\b",
    r"\bville de\b|\bcpas\b|\bocmw\b|\bservice public\b|federale overheidsdienst|\bspf\b|\bfod\b",
    r"vlaamse overheid|region wallonne|\bintercommunal|stadtgemeinde|marktgemeinde|\bmunicipio\b",
    r"camara municipal|\bfreguesia\b|servicos municipalizados|direcao-geral|instituto publico",
    r"\bprimaria\b|\bconsiliul\b|\bjudetul\b|\bmunicipiul\b|\borasul\b|\bcomuna\b|unitatea militara",
    r"\binspectoratul\b|\bagentia\b|\badministratia\b|\bvald\b|\blinn\b|vallavalitsus|linnavalitsus",
    r"\bamet\b|\bministeerium\b|\briigi\b|pasvaldib|\bnovada\b|\bdome\b|\bvalsts\b|\bministrija\b",
    r"\bparvalde\b|savivaldyb|\badministracija\b|\bministerija\b|\btarnyba\b|\binspekcija\b|valstybes",
    r"onkormanyzat|polgarmesteri|\bhivatal\b|\bmegyei\b|\bkozseg|kormanyhivatal|\ballami\b|igazgatosag",
    r"\bopcina\b|\bopcine\b|\bgrad\b|zupanij|\bobcina\b|\buprava\b|\bagencija\b|\bministarstvo\b",
    r"община|областна администрация|районн|столична|δημος|δημου|περιφερεια|αποκεντρωμενη|οργανισμος",
    r"\bcouncil\b|\bborough\b|\bcounty\b|department of|office of public works|health service executive",
    r"\bauthority\b|\bcommission\b|\binstitute\b|\binstitut\b|\binstituto\b|\bistituto\b|\binstytut\b",
    # social security and health insurance: public-law bodies with regional funds or offices
    # ('msa midi pyrenees' / '.. sud', 'arbeitsmarktservice' / '.. wien', the Bulgarian district funds)
    r"\bcaf\b|\bcpam\b|\burssaf\b|\bcarsat\b|\bmsa\b|\bcnaf\b|caisse (?:primaire|d allocations|nationale"
    r"|regionale|de mutualite|d assurance)|sozialversicherung|krankenkasse|\baok\b|unfallkasse",
    r"berufsgenossenschaft|rentenversicherung|arbeitsmarktservice|bundesagentur|jobcenter|\binps\b",
    r"\binail\b|\binami\b|\briziv\b|\bonem\b|seguridad social|\bmutua\b|здравноосигурителна",
    r"здравна инспекция|раионн|областн",
)))

# Abbreviations that mean a public body in one country only (elsewhere they are words or companies)
PUBLIC_NAME_BY_COUNTRY: dict[str, re.Pattern[str]] = {
    # Dutch central government's own units: 'ubr' (Uitvoeringsorganisatie Bedrijfsvoering Rijk),
    # 'dji' (Dienst Justitiele Inrichtingen), 'ssc' (shared service centre) ...
    "NL": re.compile(
        r"\b(?:ubr|dji|ssc|dtv|rvo|cjib|ind|rws|dico|logius|p-direkt|odc|rvb|rijk|rivm|nvwa|duo|uwv"
        r"|svb|kadaster|knmi|coa|dictu|dosco|cbs|ilt|nza|afm|acm)\b"),
    # 'a s p palermo - u o c approvvigionamenti': the provincial health authority and a unit of it;
    # a central purchasing body ('centrale di committenza') buys for others under their number
    "IT": re.compile(r"\ba ?s ?p\b|\bu ?o ?c\b|\bu ?o ?s ?d?\b|centrale di committenza|stazioni? (?:unica )?appaltant"),
}

# Identifiers that by their own shape belong to a public body (the stored form: upper case, no
# separators; a VAT number may carry its country prefix). Each was read against the identifiers of
# the pending pairs on production (22 October 2026, docs/verification/product/wp76-selfcheck.md).
PUBLIC_ID: dict[str, re.Pattern[str]] = {
    # SIREN / SIRET: 1 the State and its establishments, 2 local authorities; a VAT number is
    # FR + 2 check characters + the SIREN
    "FR": re.compile(r"^(?:FR)?(?:[0-9A-Z]{2}(?=\d{9}$))?[12]\d{8}(?:\d{5})?$"),
    # NIF / CIF: P local corporations, Q public bodies, S organs of the State and the regions
    "ES": re.compile(r"^(?:ES)?[PQS]\d{7}[0-9A-J]$"),
    # codice fiscale of an administration (non-commercial body): 11 digits beginning 8 or 9
    "IT": re.compile(r"^(?:IT)?[89]\d{10}$"),
    # enterprise number 0200 .. 0399: public-law bodies (companies hold the former VAT range 04..09)
    "BE": re.compile(r"^(?:BE)?0[23]\d{8}"),
    # organisationsnummer 2xxxxx-xxxx: the State, regions, municipalities, parishes
    "SE": re.compile(r"^(?:SE)?2\d{9}"),
    # NIPC 6xxxxxxxx: public administration
    "PT": re.compile(r"^(?:PT)?6\d{8}$"),
    # registry code 70.. state agencies, 75.. local governments
    "EE": re.compile(r"^(?:EE)?7[05]\d{6}$"),
    # registration number 9000...: state and municipal institutions
    "LV": re.compile(r"^(?:LV)?9000\d{7}$"),
    # tax number 15......: budgetary bodies
    "HU": re.compile(r"^(?:HU)?15\d{6}(?:\d{3})?$"),
    # OIN of a government body: 00000001 + RSIN, 00000004 + a number Logius assigns
    "NL": re.compile(r"^0000000[14]\d{12}$"),
    # Leitweg-ID (the e-invoicing address of a public buyer; 99x.. the Federation), as the notices
    # write it, with or without its label
    "DE": re.compile(r"^(?:LEITWEG|BERICHTSEINHEIT|FACHAMTSNUMMER)|^99[1-9]\d{6,}$|^\d{2,12}[A-Z][0-9A-Z]*\d{2}$"),
}


def public_identifier(country: str | None, *identifiers: str | None) -> bool:
    rx = PUBLIC_ID.get((country or "").upper())
    return bool(rx and any(i and rx.search(i.upper()) for i in identifiers))

# legal forms of public bodies (the `legal_form` column, or written into the name)
PUBLIC_FORM = re.compile("|".join((
    r"anstalt des offentlichen rechts|korperschaft des offentlichen rechts|\baor\b|\bkdor\b",
    r"etablissement public|\bepic\b|\bepa\b|ente pubblico|organismo autonomo|entidad publica",
    r"\be p e\b|\bepe\b|statni organizace|prispevkova organizace|public body|public authority",
)))

_PUBLIC_CLASSES = frozenset({
    # `infrastructure` too: road, rail, port and utility operators are contracting entities that buy
    # by region and department under the one number of the operator (ASFINAG: 78 rows in the batch)
    "defence", "security", "municipal", "international", "fire_rescue", "education", "health",
    "infrastructure",
})


def is_sub_unit(name: str | None) -> bool:
    return bool(name and SUB_UNIT.search(name))


def public_signal(name: str | None, country: str | None = None, *, legal_form: str | None = None,
                  org_role: str | None = None, defence_buyer: bool = False, buys: bool = False,
                  company_form: bool = False, identifiers: tuple[str | None, ...] = ()) -> str | None:
    """Why a row is a public authority or a unit of one, or None: its flags, its buyer role (it
    publishes notices, and no name of it states a company's legal form: a utility or an exhibition
    centre that is an S.A. buys too), its legal form, an identifier of a public body, or its name.
    ponytail: a vocabulary and identifier shapes, not a register; a company whose name says 'pharma'
    or 'institute' is held as public too, which only means it waits for a person."""
    if defence_buyer:
        return "defence_buyer"
    if (org_role or "").lower() == "buyer" or (buys and not company_form):
        return "buyer_role"
    if legal_form and PUBLIC_FORM.search(legal_form.lower()):
        return "legal_form"
    if public_identifier(country, *identifiers):
        return "identifier"
    n = (name or "").strip()
    if not n:
        return None
    if (SUB_UNIT.search(n) or PUBLIC_NAME.search(n) or PUBLIC_FORM.search(n)
            or ((rx := PUBLIC_NAME_BY_COUNTRY.get((country or "").upper())) and rx.search(n))
            or buyer_class_of(n, country) in _PUBLIC_CLASSES):
        return "name"
    return None


def is_public_body(name: str | None, country: str | None = None, **kw) -> bool:
    return public_signal(name, country, **kw) is not None
