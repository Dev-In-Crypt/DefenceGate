"""What a contract winner's own name and number say about it (WP-96): its company number in one comparable form, and
the country its number, its name or its legal form state.

Pure functions, no database. Used by `ops/supplier_dedupe` (one company under two rows) and by `awards` /
`ops/supplier_countries` (a winner filed under the buyer's or another tenderer's country).
"""

from __future__ import annotations

import re
import unicodedata

from .normalise import normalise_identifier

# EU VAT prefixes that are not the ISO code of their country
_VAT_PREFIX = {"EL": "GR"}
_EU_VAT = frozenset("AT BE BG CY CZ DE DK EE EL ES FI FR HR HU IE IT LT LU LV MT NL PL PT RO SE SI SK XI".split())
# digits after the prefix, per country (the VAT number formats of the EU's VIES)
_VAT_DIGITS = {"AT": r"U\d{8}", "BE": r"[01]\d{9}", "BG": r"\d{9,10}", "CY": r"\d{8}[A-Z]", "CZ": r"\d{8,10}",
               "DE": r"\d{9}", "DK": r"\d{8}", "EE": r"\d{9}", "EL": r"\d{9}", "ES": r"[0-9A-Z]\d{7}[0-9A-Z]",
               "FI": r"\d{8}", "FR": r"[0-9A-Z]{2}\d{9}", "HR": r"\d{11}", "HU": r"\d{8}", "IE": r"\d[0-9A-Z+*]\d{5}[A-Z]{1,2}",
               "IT": r"\d{11}", "LT": r"\d{9}|\d{12}", "LU": r"\d{8}", "LV": r"\d{11}", "MT": r"\d{8}",
               "NL": r"\d{9}B\d{2}", "PL": r"\d{10}", "PT": r"\d{9}", "RO": r"\d{2,10}", "SE": r"\d{12}",
               "SI": r"\d{8}", "SK": r"\d{10}"}


def company_number(raw: str | None, country: str | None) -> str | None:
    """The comparable form of a company's registration or VAT number (`normalise_identifier`), with the one rule it
    lacks: a Swedish VAT number is the organisation number with SE in front and 01 behind (SAAB AB 556036-0793 and
    SE556036079301 are one number)."""
    n = normalise_identifier(raw, country) if raw else None
    if n and (country or "").upper() == "SE" and len(n) == 12 and n.isdigit() and n.endswith("01"):
        return n[:10]
    return n


def piva_valid(number: str) -> bool:
    """An Italian partita IVA (and the codice fiscale of a company, which has the same shape): 11 digits whose last is
    the check digit of the first ten (Luhn, as the Agenzia delle Entrate computes it)."""
    if not re.fullmatch(r"\d{11}", number or "") or number == "0" * 11:
        return False
    total = 0
    for i, ch in enumerate(number[:10]):
        d = int(ch)
        if i % 2:
            d = d * 2 - 9 if d * 2 > 9 else d * 2
        total += d
    return (10 - total % 10) % 10 == int(number[10])


def vat_country(raw: str | None) -> str | None:
    """The country an EU VAT number states by its prefix (DE119356818 -> DE, EL... -> GR), or None when the value is
    not written as one."""
    s = re.sub(r"[^0-9A-Za-z]", "", raw or "").upper()
    prefix = s[:2]
    if prefix in _EU_VAT and re.fullmatch(_VAT_DIGITS.get(prefix, r"\d{8,12}"), s[2:]):
        return _VAT_PREFIX.get(prefix, prefix)
    return None


# A country named in a company's own name: "LEONARDO Germany GmbH", "Saab Finland Oy", "KNDS Ammo France". English and
# the country's own name; words that are also common names elsewhere are left out.
_NAME_COUNTRY = {
    "germany": "DE", "deutschland": "DE", "finland": "FI", "suomi": "FI", "canada": "CA", "france": "FR",
    "italia": "IT", "italy": "IT", "espana": "ES", "spain": "ES", "polska": "PL", "poland": "PL", "sweden": "SE",
    "sverige": "SE", "norway": "NO", "norge": "NO", "denmark": "DK", "danmark": "DK", "nederland": "NL",
    "netherlands": "NL", "belgium": "BE", "belgique": "BE", "austria": "AT", "osterreich": "AT", "portugal": "PT",
    "romania": "RO", "hellas": "GR", "greece": "GR", "uk": "GB", "britain": "GB", "australia": "AU",
    "schweiz": "CH", "switzerland": "CH", "czech": "CZ", "slovakia": "SK", "hungary": "HU", "estonia": "EE",
    "latvia": "LV", "lithuania": "LT", "ireland": "IE", "turkiye": "TR", "turkey": "TR", "usa": "US",
}
# Legal forms that exist in a few countries only, as the classes `resolution.names.legal_form_of` names them, with the
# countries where each is a company form. ponytail: the usual countries of each form, not a register; a form missing
# here never decides anything.
_FORM_COUNTRIES = {
    "gmbh": ("DE", "AT", "CH", "LI"), "gmbh_co_kg": ("DE", "AT"), "kg": ("DE", "AT", "CH"), "ag": ("DE", "AT", "CH", "LI"),
    "oy": ("FI",), "oyj": ("FI",), "ab": ("SE", "FI", "LT"), "sl": ("ES",), "spa": ("IT",), "srl": ("IT", "RO", "MD", "BE"),
    "zoo": ("PL",), "bv": ("NL", "BE"), "nv": ("NL", "BE", "CW"), "aps": ("DK",), "sro": ("CZ", "SK"),
    "inc": ("US", "CA", "PH"), "llc": ("US",), "ltd": ("GB", "IE", "CY", "MT", "IL", "ZA", "AU", "NZ", "IN", "CA", "HK", "SG"),
    "plc": ("GB", "IE"), "sas": ("FR", "LU", "BE", "CO"), "sarl": ("FR", "LU", "BE", "CH", "MA", "TN"),
    "sa": ("ES", "FR", "BE", "LU", "PL", "PT", "GR", "CH", "RO", "AR", "BR", "MX", "CL", "PE", "UY", "MA", "TN"),
}
# A form held by one country far more than by the others (DE for a GmbH): the country chosen when the stated one cannot
# hold that form and nothing else decides. ponytail: the likeliest country, not a fact; stored as basis `legal_form`.
_FORM_USUAL = {"gmbh": "DE", "gmbh_co_kg": "DE", "kg": "DE", "ag": "DE", "oy": "FI", "oyj": "FI", "sl": "ES",
               "spa": "IT", "zoo": "PL", "aps": "DK"}


def _words(name: str) -> list[str]:
    s = unicodedata.normalize("NFKD", name or "")
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    return re.findall(r"[a-z]+", s)


def name_country(name: str | None) -> str | None:
    """The one country the company's own name names, or None (none, or two)."""
    found = {_NAME_COUNTRY[w] for w in _words(name or "") if w in _NAME_COUNTRY}
    return found.pop() if len(found) == 1 else None


def stated_country_check(name: str, identifier: str | None, stated: str | None,
                         others: tuple[str, ...] = ()) -> tuple[str | None, str | None]:
    """(country, basis) for a winner whose stated country its own name or number contradicts, else (stated, None).

    In order: the prefix of a VAT number (`identifier`), a country the name names, then the legal form: a form the
    stated country does not have is corrected to the one country of the notice's other tenderers (`others`) that has
    it, else to the form's usual country (`_FORM_USUAL`). A number or a name decides against the stated country; a
    legal form only vetoes it. The basis is `identifier`, `name`, `legal_form_notice` or `legal_form`."""
    from .resolution.names import legal_form_of

    stated = (stated or "").upper() or None
    by_vat = vat_country(identifier)
    if by_vat and by_vat != stated:
        return by_vat, "identifier"
    by_name = name_country(name)
    form = legal_form_of(name)
    holders = _FORM_COUNTRIES.get(form or "")
    if by_name and by_name != stated and (not holders or by_name in holders):
        return by_name, "name"
    if holders and stated and stated not in holders and not by_vat and not (by_name and by_name == stated):
        among = sorted({c for c in others if c in holders})
        if len(among) == 1:
            return among[0], "legal_form_notice"
        if form in _FORM_USUAL:
            return _FORM_USUAL[form], "legal_form"
    return stated, None


# WP-111 (p07, p10): identifiers a notice gives in the winner's number field that are not the company's own number. The
# Spanish defence buyers (PLACSP) give a foreign winner without a Spanish tax number a code of their own: the country, zeros,
# "CGC" and a sequence ("DE0000CGC00430" for Heckler & Koch, "IL0000CGC62412" for an Elbit company, 94 award rows on
# 24 October 2026): it names the buyer's file of the supplier, not a register entry.
_BUYER_CODE = re.compile(r"^(?:[A-Z]{2})?0*CGC\d+$")
# Countries whose company numbers have one fixed shape (after `company_number`): Italy, the codice fiscale / partita IVA, 11
# digits with a check digit (written without its leading zeros as often as with them); the United Kingdom, a Companies House
# number (8 digits, or 2 letters and 6) or a VAT number (9 or 12 digits). A value of no such shape ("0006001333" for Leonardo
# from an Irish notice, "0898937602" for Leonardo UK from a Portuguese one) is a portal's or buyer's own reference.
_GB_NUMBER = re.compile(r"^(?:\d{8}|[A-Z]{2}\d{6}|\d{9}|\d{12})$")


def own_number(raw: str | None, country: str | None) -> str | None:
    """The company's own registration or VAT number in the comparable form (`company_number`), or None when the value is a
    buyer's or a portal's code (`_BUYER_CODE`) or has no shape a company number of its country has. An Italian number
    written without its leading zeros is given with them ("401990585" is 00401990585)."""
    n = company_number(raw, country)
    if not n or _BUYER_CODE.match(n):
        return None
    c = (country or "").upper()
    if c == "IT" and n.isdigit():
        n = n.zfill(11)
        # digits 8 to 10 are the issuing tax office: 001 to 100, or 120, 121, 888, 999 ("0006001333" padded passes the
        # check digit by chance, office 133)
        office = int(n[7:10]) if len(n) == 11 else 0
        return n if piva_valid(n) and (1 <= office <= 100 or office in (120, 121, 888, 999)) else None
    if c in ("GB", "UK"):
        if n.isdigit() and len(n) in (6, 7):
            n = n.zfill(8)                 # a Companies House number without its leading zeros
        return n if _GB_NUMBER.match(n) else None
    return n


def namesakes(conn, org_id: int, country: str | None, canonical_name: str | None) -> list[dict]:
    """WP-111 (owner, 24 October 2026: companies with different registration numbers are different companies): the other
    contract winners of the same country under the same name, each with the numbers it holds, so a supplier page says why
    it stands apart (Rheinmetall Electronics GmbH three times: DE811127845, DE119356818, DE251121155) and links the others."""
    if not canonical_name:
        return []
    rows = conn.execute(
        """SELECT o.id, COALESCE(o.display_name, o.canonical_name) AS name, o.country, o.national_reg_no, o.vat_number,
                  (SELECT count(*) FROM award a WHERE a.organisation_id = o.id AND a.superseded_at IS NULL
                      AND a.excluded_reason IS NULL) AS awards
             FROM organisation o
            WHERE o.country = %s AND lower(o.canonical_name) = lower(%s) AND o.id <> %s
              AND o.merged_into IS NULL AND NOT o.suppressed AND o.individual_reason IS NULL
            ORDER BY o.id LIMIT 10""", (country, canonical_name, org_id)).fetchall()
    out = []
    for r in rows:
        if not r["awards"]:
            continue
        numbers = sorted({n for n in (own_number(x, r["country"]) for x in (r["national_reg_no"], r["vat_number"])) if n})
        out.append({"id": r["id"], "name": r["name"], "country": (r["country"] or "").strip() or None,
                    "identifiers": numbers, "awards": r["awards"]})
    return out
