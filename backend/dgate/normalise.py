"""Normalisation: source-specific payloads into the unified opportunity schema.

Two hard rules enforced here.

1. Deterministic and idempotent. The same input must always produce the same
   output, so that reprocessing the raw archive rebuilds the serving layer
   exactly. No timestamps, no randomness, no "now()".

2. Personal data is dropped here and nowhere later. TED notices carry contact
   person names, emails, phone numbers, and award notices can name natural
   persons. None of it belongs in this product. It is stripped at the boundary
   so that no downstream code has to remember to.
"""

from __future__ import annotations

import json
import logging
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone, tzinfo
from typing import Any, Iterator
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

log = logging.getLogger(__name__)

# TED fields that carry personal data. Never mapped, never served.
# Reference: https://ted.europa.eu/en/legal-notice (Protection of personal data)
PERSONAL_DATA_FIELDS = {
    "buyer-contact-point", "buyer-email", "buyer-person", "buyer-tel",
    "buyer-fax", "buyer-touchpoint-contact-point", "buyer-touchpoint-email",
    "business-contact-point", "business-email", "business-tel", "business-fax",
    "first-name-ubo", "jury-member-name-lot",
    "organisation-contact-point", "organisation-email", "organisation-tel",
    "winner-contact-point", "winner-email", "winner-tel",
    # e-Zamowienia (Poland). userId identifies the person who published the
    # notice. Pseudonymous is still personal: it singles out an individual
    # across every notice they ever filed.
    "userId",
    # Vinnova (Sweden). Named contact persons with telephone and address on every
    # call and round.
    "KontaktLista",
    # Atlas Przetargow (Poland, historical). Contractor identity, which is a
    # natural person on roughly a quarter of 2024 rows. The publisher already
    # pseudonymises those -- '[Osoba fizyczna]' for the name, a stable SHA-256
    # for the identifier -- but a stable hash still singles out one person
    # across every contract they ever won, which is the same reasoning that put
    # userId here. Nothing downstream stores a contractor, so dropping both
    # costs no product value.
    "contractor_name", "contractor_national_id",
}


@dataclass
class Opportunity:
    """Unified record. Mirrors the opportunity table in schema.sql."""

    source_code: str
    native_id: str
    buyer_name_raw: str
    title_original: str
    buyer_identifier: str | None = None
    country: str | None = None
    original_language: str | None = None
    title_en: str | None = None
    summary_en: str | None = None
    procedure_type: str | None = None
    legal_basis: str | None = None
    value_amount: float | None = None
    value_currency: str | None = None
    published_at: date | None = None
    deadline_at: datetime | None = None
    cpv_codes: list[str] = field(default_factory=list)
    source_url: str | None = None
    notice_version: int | None = None
    buyer_org_id: int | None = None
    # lifecycle. status is the normalised value used by the API and by
    # VERSIONED_FIELDS; status_native keeps the source's own code so a mapping
    # mistake stays diagnosable from the serving row. A record that does not say what
    # it is has `unknown`, never `open`: every mapper sets it explicitly.
    status: str = "unknown"
    status_native: str | None = None
    # The TED publication number this national notice was forwarded under, when
    # the source states it ("696956-2026", leading zeros stripped). It is a
    # link, not a version-worthy fact: not part of VERSIONED_FIELDS, and left
    # out of the payload while empty so existing content hashes do not move.
    ted_ref: str | None = None
    # The native_id, within the same source, of the notice this one corrects.
    # Set for BOAMP rectificatifs (the record's `annonce_lie`): a rectificatif
    # is a separate notice that repeats the whole of its parent. A link like
    # ted_ref: not in VERSIONED_FIELDS and left out of the payload while empty.
    related_native_id: str | None = None
    # When the source last changed this record, where the source states it as an
    # instant (the Atom `updated` time of a PLACSP entry). It orders versions of
    # one notice -- db.upsert_opportunity reads it to tell history arriving late
    # from a change -- and is not a date the notice has: not versioned, not
    # served, and left out of the payload while empty so no hash moves.
    source_updated_at: datetime | None = None
    # TED facts that are attributes, not version-worthy changes (migration 0030):
    # the numeric/eForms subtype, the procedure a notice belongs to (its
    # re-publications and corrigenda share it), how many lots it lists, and which
    # of TED's value fields value_amount was taken from (total, estimated,
    # lot_sum, first_lot). Left out of the payload while empty, like ted_ref.
    notice_subtype: str | None = None
    procedure_identifier: str | None = None
    lot_count: int | None = None
    value_kind: str | None = None
    # The date and kind of the notice this record was read from (migration 0048), where
    # the source states them and no publication date: a PLACSP entry that is an award
    # carries its own date and no call notice. Never a publication date. Attributes: not
    # in VERSIONED_FIELDS, left out of the payload while empty so no hash moves.
    notice_date: date | None = None
    notice_kind: str | None = None
    # WP-95: the buyers of a joint procurement after the first (`buyer_name_raw`), as the notice names them
    # (TED's buyer-name list). An attribute: not versioned, left out of the payload while empty.
    other_buyers: list[str] | None = None
    # WP-113: the procurement documents on the buyer's platform (BT-15), where the notice states them and the link is
    # its own `source_url` no longer (the German service: the notice's page is). Payload only, left out while empty.
    documents_url: str | None = None
    # signals, populated by classify.py
    is_defence: bool = False
    sig_legal_basis: bool = False
    sig_cpv: bool = False
    sig_buyer: bool = False
    sig_clearance: bool = False
    # Migration 0029: the military CPV on its own (sig_cpv also counts the civil
    # security groups), the added military codes outside division 35, a link to a
    # defence notice of another source, and the demotion of a military CPV that
    # a municipality, hospital, school or fire brigade bought. All derived.
    sig_cpv_military: bool = False
    sig_cpv_adjacent: bool = False
    sig_linked_defence: bool = False
    dual_use: bool = False
    buyer_class: str | None = None
    security_clearance_required: bool = False
    nda_required: bool = False
    subcontracting_signal: bool = False
    # The notice's own text. It is persisted: opportunity_payload() serialises the
    # whole dataclass, so every archived version carries it. The API never serves it
    # (api.py whitelists the snapshot), and e-mail addresses in it are redacted.
    description: str | None = None

    def __post_init__(self) -> None:
        self.source_url = http_url(self.source_url)
        if self.cpv_codes and not (self.sig_cpv_military or self.sig_cpv_adjacent):
            # The military CPV is a pure function of the codes, so it is never left
            # unset: a record built by hand, or re-read from a payload written
            # before migration 0029, carries the same answer the classifier gives.
            from .classify import classify

            sig = classify(legal_basis=None, cpv_codes=self.cpv_codes, buyer_is_defence=False)
            self.sig_cpv_military = sig.military_cpv
            self.sig_cpv_adjacent = sig.cpv_adjacent


# ------------------------------------------------- the boundary's bounds
#
# Everything a source sends is untrusted, and a single record must not be able to
# stop a night's collection or the process. Measured on 12 October 2026: a JSON
# nesting of 1,200 raised RecursionError out of strip_personal_data, a NUL
# character is refused by Postgres in text and in jsonb, and the e-mail pattern
# was quadratic on a long run of address characters. Each source then failed
# every night for as long as the record stayed in its window.
MAX_DEPTH = 40
MAX_STRING = 100_000
MAX_ITEMS = 10_000


def _bound(node: Any, depth: int = 0) -> Any:
    """A copy of a payload that cannot hurt what is downstream: no NUL characters,
    strings and collections of a sane size, nothing nested beyond MAX_DEPTH."""
    if isinstance(node, str):
        return node.replace("\x00", "")[:MAX_STRING]
    if isinstance(node, dict):
        if depth >= MAX_DEPTH:
            return None
        return {(k.replace("\x00", "")[:MAX_STRING] if isinstance(k, str) else k):
                _bound(v, depth + 1) for k, v in list(node.items())[:MAX_ITEMS]}
    if isinstance(node, (list, tuple)):
        if depth >= MAX_DEPTH:
            return None
        return [_bound(v, depth + 1) for v in list(node)[:MAX_ITEMS]]
    return node


def http_url(value: Any) -> str | None:
    """The value if it is an absolute http(s) link, else None.

    A source supplies links that end up in `<a href>` under our attribution, and
    `javascript:`, `data:` and the like must never get that far. Control
    characters and whitespace inside are refused too.
    """
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text or any(ord(ch) < 32 or ch.isspace() for ch in text):
        return None
    from urllib.parse import urlsplit

    try:
        parts = urlsplit(text)
    except ValueError:
        return None
    return text if parts.scheme in ("http", "https") and parts.netloc else None


# --------------------------------------------------------------- helpers

_TED_NUMBER = re.compile(r"(?<![\d-])(\d{1,8})-(20[12]\d)(?![\d-])")
_TED_NOTICE_URL = re.compile(r"ted\.europa\.eu/[A-Za-z-]+/notice/(?:-/detail/)?(\d{1,8}-20[12]\d)")


def canonical_ted_ref(value: Any) -> str | None:
    """A TED publication number in the one spelling TED's own rows use.

    "00696956-2026" and "696956-2026" are the same notice; the source and the
    portal disagree on padding, so the number is compared without it. Anything
    that is not exactly a number and a year is not a reference.
    """
    if not isinstance(value, str):
        return None
    m = _TED_NUMBER.fullmatch(value.strip())
    return f"{int(m.group(1))}-{m.group(2)}" if m else None


def ted_ref_from_url(value: Any) -> str | None:
    """The publication number inside a link to a TED notice, if it is one."""
    m = _TED_NOTICE_URL.search(value) if isinstance(value, str) else None
    return canonical_ted_ref(m.group(1)) if m else None


def _first(value: Any) -> Any:
    """TED returns many fields as lists even when there is one value."""
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        for v in value:
            if v not in (None, "", []):
                return _first(v)
        return None
    if isinstance(value, dict):
        # multilingual blocks: {"eng": "...", "spa": "..."}
        for key in ("eng", "en", "value", "text"):
            if key in value:
                return _first(value[key])
        for v in value.values():
            got = _first(v)
            if got is not None:
                return got
        return None
    return value


def _all_strings(value: Any) -> list[str]:
    out: list[str] = []
    if value is None:
        return out
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple)):
        for v in value:
            out.extend(_all_strings(v))
        return out
    if isinstance(value, dict):
        for v in value.values():
            out.extend(_all_strings(v))
        return out
    return [str(value)]


def _parse_date(value: Any) -> date | None:
    raw = _first(value)
    if not raw:
        return None
    s = str(raw).strip()
    # TED emits ISO with optional timezone: 2026-10-02+02:00
    m = re.match(r"(\d{4}-\d{2}-\d{2})", s)
    if not m:
        return None
    try:
        return date.fromisoformat(m.group(1))
    except ValueError:
        return None


_TZ_SUFFIX = re.compile(r"(Z|[+-]\d{2}:?\d{2})\s*$")


def tz_from_offset(*values: Any) -> tzinfo | None:
    """Read the UTC offset out of the first value that carries one.

    TED writes the offset on both the date and the time field
    (``2026-10-02+02:00``, ``12:00:00+02:00``). Dropping it silently shifts
    every deadline by the server's own timezone, which is why this exists.
    """
    for raw in values:
        v = _first(raw)
        if not v:
            continue
        m = _TZ_SUFFIX.search(str(v).strip())
        if not m:
            continue
        token = m.group(1)
        if token == "Z":
            return timezone.utc
        sign = 1 if token[0] == "+" else -1
        digits = token[1:].replace(":", "")
        return timezone(sign * timedelta(hours=int(digits[:2]), minutes=int(digits[2:4])))
    return None


def _parse_datetime(d: Any, t: Any = None, *, default_tz: tzinfo = timezone.utc) -> datetime | None:
    """Timezone-aware deadline.

    The offset stated by the source wins. When the source states none, the
    caller's ``default_tz`` applies (UTC for TED, the national timezone for a
    national portal). The result is always aware, because the column is
    TIMESTAMPTZ and a naive value would be read in the server's timezone.
    """
    day = _parse_date(d)
    if day is None:
        return None
    raw_t = _first(t)
    hh, mm = 23, 59
    if raw_t:
        m = re.match(r"(\d{2}):(\d{2})", str(raw_t).strip())
        if m:
            hh, mm = int(m.group(1)), int(m.group(2))
    return datetime(day.year, day.month, day.day, hh, mm,
                    tzinfo=tz_from_offset(t, d) or default_tz)


def _as_bool(value: Any) -> bool:
    """Interpret a source flag. TED sends booleans, 'true'/'false' and 'Y'/'N'."""
    raw = _first(value)
    if raw is None:
        return False
    if isinstance(raw, bool):
        return raw
    return str(raw).strip().lower() in {"true", "yes", "y", "1"}


def _parse_amount(value: Any) -> float | None:
    raw = _first(value)
    if raw in (None, ""):
        return None
    try:
        return float(str(raw).replace(",", "").replace(" ", ""))
    except (TypeError, ValueError):
        return None


_CPV_CODE = re.compile(r"(?<!\d)(\d{8})(?:-\d)?(?!\d)")


def _clean_cpv(value: Any) -> list[str]:
    """Return 8-digit CPV codes, deduplicated, order preserved.

    Every code in every string, not just the first: Poland packs the whole set
    into one field as `45453000-7 (label),45110000-1 (label)`, so stopping at
    the first match silently discarded the rest.
    """
    out, seen = [], set()
    for raw in _all_strings(value):
        for code in _CPV_CODE.findall(raw):
            if code not in seen:
                seen.add(code)
                out.append(code)
    return out


def parse_iso_datetime(value: Any, *, default_tz: tzinfo = timezone.utc) -> datetime | None:
    """Parse a full ISO instant such as `2026-09-23T06:00:00Z`.

    ``_parse_datetime`` takes a date and a separate time, which is TED's and
    PLACSP's shape. A single combined stamp needs its own parser: feeding it to
    the two-field one silently produced 23:59 for every deadline, because the
    time regex is anchored at the start of the string.
    """
    raw = _first(value)
    if not raw:
        return None
    text = str(raw).strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=default_tz)


_LANG3_TO_2 = {
    "eng": "EN", "spa": "ES", "fra": "FR", "deu": "DE", "ger": "DE",
    "nld": "NL", "dut": "NL", "pol": "PL", "por": "PT", "ron": "RO",
    "rum": "RO", "ces": "CS", "cze": "CS", "lit": "LT", "lav": "LV",
    "est": "ET", "ita": "IT", "swe": "SV", "dan": "DA", "fin": "FI",
    "ell": "EL", "gre": "EL", "bul": "BG", "hrv": "HR", "hun": "HU",
    "gle": "GA", "mlt": "MT", "slk": "SK", "slv": "SL", "ukr": "UK",
}


def _lang2(value: Any) -> str | None:
    raw = _first(value)
    if not raw:
        return None
    s = str(raw).strip().lower()
    if len(s) == 2:
        return s.upper()
    return _LANG3_TO_2.get(s, s[:2].upper() if s else None)


# ISO 3166-1 alpha-3 to alpha-2, all 249 officially assigned codes, plus the two
# TED uses outside the standard: XKX (Kosovo, user-assigned XK) and EUR (the EU
# institutions, reserved EU). Truncating an unknown code to its first two letters
# was the previous fallback, and it silently turned BLR into BL, SRB into SR, TUR
# into TU and GRL into Greece (79 rows visibly wrong on 12 October 2026).
_ISO3_PAIRS = (
    """AFG AF ALA AX ALB AL DZA DZ ASM AS AND AD AGO AO AIA AI ATA AQ ATG AG ARG AR ARM AM
    ABW AW AUS AU AUT AT AZE AZ BHS BS BHR BH BGD BD BRB BB BLR BY BEL BE BLZ BZ BEN BJ
    BMU BM BTN BT BOL BO BES BQ BIH BA BWA BW BVT BV BRA BR IOT IO BRN BN BGR BG BFA BF
    BDI BI CPV CV KHM KH CMR CM CAN CA CYM KY CAF CF TCD TD CHL CL CHN CN CXR CX CCK CC
    COL CO COM KM COG CG COD CD COK CK CRI CR CIV CI HRV HR CUB CU CUW CW CYP CY CZE CZ
    DNK DK DJI DJ DMA DM DOM DO ECU EC EGY EG SLV SV GNQ GQ ERI ER EST EE SWZ SZ ETH ET
    FLK FK FRO FO FJI FJ FIN FI FRA FR GUF GF PYF PF ATF TF GAB GA GMB GM GEO GE DEU DE
    GHA GH GIB GI GRC GR GRL GL GRD GD GLP GP GUM GU GTM GT GGY GG GIN GN GNB GW GUY GY
    HTI HT HMD HM VAT VA HND HN HKG HK HUN HU ISL IS IND IN IDN ID IRN IR IRQ IQ IRL IE
    IMN IM ISR IL ITA IT JAM JM JPN JP JEY JE JOR JO KAZ KZ KEN KE KIR KI PRK KP KOR KR
    KWT KW KGZ KG LAO LA LVA LV LBN LB LSO LS LBR LR LBY LY LIE LI LTU LT LUX LU MAC MO
    MDG MG MWI MW MYS MY MDV MV MLI ML MLT MT MHL MH MTQ MQ MRT MR MUS MU MYT YT MEX MX
    FSM FM MDA MD MCO MC MNG MN MNE ME MSR MS MAR MA MOZ MZ MMR MM NAM NA NRU NR NPL NP
    NLD NL NCL NC NZL NZ NIC NI NER NE NGA NG NIU NU NFK NF MKD MK MNP MP NOR NO OMN OM
    PAK PK PLW PW PSE PS PAN PA PNG PG PRY PY PER PE PHL PH PCN PN POL PL PRT PT PRI PR
    QAT QA REU RE ROU RO RUS RU RWA RW BLM BL SHN SH KNA KN LCA LC MAF MF SPM PM VCT VC
    WSM WS SMR SM STP ST SAU SA SEN SN SRB RS SYC SC SLE SL SGP SG SXM SX SVK SK SVN SI
    SLB SB SOM SO ZAF ZA SGS GS SSD SS ESP ES LKA LK SDN SD SUR SR SJM SJ SWE SE CHE CH
    SYR SY TWN TW TJK TJ TZA TZ THA TH TLS TL TGO TG TKL TK TON TO TTO TT TUN TN TUR TR
    TKM TM TCA TC TUV TV UGA UG UKR UA ARE AE GBR GB USA US UMI UM URY UY UZB UZ VUT VU
    VEN VE VNM VN VGB VG VIR VI WLF WF ESH EH YEM YE ZMB ZM ZWE ZW XKX XK EUR EU""".split())
_ISO3_TO_2 = dict(zip(_ISO3_PAIRS[::2], _ISO3_PAIRS[1::2], strict=True))
_UNKNOWN_COUNTRY_LOGGED: set[str] = set()


def _country2(value: Any) -> str | None:
    raw = _first(value)
    if not raw:
        return None
    s = str(raw).strip().upper()
    if len(s) == 2:
        # WP-96: "UK" is no ISO code; the United Kingdom is GB (the supplier list showed it twice)
        return "GB" if s == "UK" else s
    got = _ISO3_TO_2.get(s)
    if (got is None and s not in _UNKNOWN_COUNTRY_LOGGED
            and len(_UNKNOWN_COUNTRY_LOGGED) < 100):
        _UNKNOWN_COUNTRY_LOGGED.add(s[:16])
        log.warning("country code %r is not in the ISO 3166-1 alpha-3 table; left empty", s)
    return got


# ---------------------------------------------------------- name handling

_LEGAL_FORMS = [
    "sociedad anonima", "sociedad limitada", "s.a.", "s.l.", "sa", "sl",
    "gmbh", "ag", "kg", "ohg", "mbh", "e.v.",
    "sp. z o.o.", "sp z oo", "spolka akcyjna", "s.a", "sp.j.",
    "b.v.", "bv", "n.v.", "nv",
    "s.r.l.", "srl", "s.p.a.", "spa",
    "uab", "ab", "as", "oy", "oyj", "a/s", "aps",
    "tov", "pat", "fop",
    "ltd", "limited", "plc", "llc", "inc", "corp",
    "sas", "sarl", "sasu", "eurl", "s.a.s.",
    "lda", "unipessoal",
    "s.r.o.", "sro", "a.s.",
]

_NOISE_TOKENS = {"group", "grupo", "groupe", "holding", "holdings",
                 "international", "internacional", "gruppe"}

# Letters that NFKD leaves alone because Unicode gives them no decomposition.
# Without this, "Białymstoku" from a Polish source and "Bialymstoku" from an
# ASCII one are two organisations. Migration 0007 repeats this table in SQL for
# the names already stored; the two must stay in step.
_TRANSLITERATE = str.maketrans({
    "ł": "l", "Ł": "l",
    "ø": "o", "Ø": "o",
    "ß": "ss", "ẞ": "ss",
    "đ": "d", "Đ": "d",
    "ħ": "h", "Ħ": "h",
    "æ": "ae", "Æ": "ae",
    "œ": "oe", "Œ": "oe",
    "ð": "d", "Ð": "d",
    "þ": "th", "Þ": "th",
    "ı": "i",
})


# WP-115: a telephone number, a fax number or an e-mail address written into an organisation's name, and all that
# follows it (805 stored names carried "tel <number>", aliases 95 e-mail addresses and 693 telephone numbers; coverage
# audit, 24 October 2026). A label counts only before a digit, "+" or "(": "Tel Aviv University" keeps its name.
_NAME_CONTACT = re.compile(
    r"\b(?:tel|t[eé]l[eé]phone|telefon|telefono|tel[eé]fono|phone|fax|tlf|tfno)\b\.?\s*[:.]?\s*(?=[\d(+])"
    r"|[\w.+-]+@[\w-]+(?:\.[\w-]+)+|\be-?mail\b\s*:?|\+\d[\d\s().-]{6,}\d",
    re.IGNORECASE)


def strip_name_contacts(name: str | None) -> str:
    """An organisation name without the contact details written into it: cut at the first telephone, fax or
    e-mail and everything after it (the stated contact block is "Tel ... Fax ... E-Mail ... www ...")."""
    m = _NAME_CONTACT.search(name or "")
    return (name or "")[:m.start()].rstrip(" ,;:-/(") if m else (name or "")


def normalise_org_name(raw: str, *, strip_noise: bool = False, fold_state: bool = False) -> str:
    """Canonical form for entity resolution.

    Fold accents (by decomposition, then by explicit transliteration for letters
    such as Polish ł that do not decompose), lowercase, strip legal form,
    collapse punctuation. Legal form
    is removed rather than kept because the same company appears with and
    without it across sources, and that difference alone should never create a
    duplicate organisation.
    """
    raw = strip_name_contacts(raw)
    if not raw:
        return ""
    s = unicodedata.normalize("NFKD", raw)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.translate(_TRANSLITERATE)
    s = s.lower()
    s = re.sub(r"[^\w\s.&-]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()

    for form in sorted(_LEGAL_FORMS, key=len, reverse=True):
        f = re.escape(form)
        s = re.sub(rf"(^|\s){f}(\s|$)", " ", s)
        s = re.sub(rf",\s*{f}\s*$", "", s)

    s = re.sub(r"[.,]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()

    if strip_noise:
        s = " ".join(t for t in s.split() if t not in _NOISE_TOKENS)

    if fold_state:
        s = _fold_state(s)

    return s


# ----------------------------------------------- state prefixes and word order
#
# The same body is written "Ministerstvo obrany", "Ceska republika - Ministerstvo
# obrany" and "Ministerstvo obrany - Ceska republika"; the German federal
# government names itself "Bundesrepublik Deutschland, vertreten durch das ...";
# a Romanian unit is "Ministerul Apararii - U.M. 02192" and "Unitatea militara
# 02192". Nothing in the stored form folds these, and the stored form must not
# move: names already stored were normalised without folding (migration 0007 had
# to rewrite them once, and a second rewrite would orphan every alias). So the
# fold is opt-in, and its only users are the places that compare names without
# deciding anything -- merge candidates. It is never the key an organisation is
# looked up by.
_STATE_PREFIXES = re.compile(
    r"^(?:"
    r"ceska republika|skarb panstwa|republika slovenija|republika hrvatska|republique francaise"
    r"|etat francais"
    r"|estado portugues|lietuvos respublikos|latvijas republikas"
    r"|(?:republik osterreich(?: bund)?|bund(?= (?:republik|vertreten)))"
    r"(?: vertreten durch(?: (?:das|den|die|der|dem))?)?"
    r"|republica portugueza|romania|statul roman|slovenska republika"
    r"|bundesrepublik deutschland(?: (?:end|diese )?vertreten durch(?: (?:das|den|die|der|dem))?"
    r"| vert(?:r)?(?: d)? durch(?: (?:das|den|die|der|dem))?| vertr d d)?"
    r"|federal republic of germany(?: represented by(?: the)?)?"
    r"|(?:the )?(?:government of (?:the )?)?(?:republic|kingdom|state) of [a-z ]{2,40}?"
    r"(?: represented by(?: the)?| (?=ministry|department|office))"
    r")\s*-*\s*"
)
_STATE_SUFFIXES = re.compile(
    r"\s*-*\s*(?:ceska republika|ceske republiky|cr|slovenskej republiky|sr|republic of poland"
    r"|of the republic of [a-z ]{2,40}|of republic of [a-z ]{2,40})$"
)
_RO_UNIT = re.compile(
    r"^(?:ministerul apararii(?: nationale)?\s*-*\s*)?(?:unitatea militara|u m|um)\s*(\d{3,5})\b.*$")


def _fold_state(s: str) -> str:
    for _ in range(3):                     # "skarb panstwa - ceska republika - ..."
        t = _STATE_PREFIXES.sub("", s, count=1)
        t = _STATE_SUFFIXES.sub("", t, count=1)
        if t == s or not t:
            break
        s = t
    s = re.sub(r"-+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


_TOKEN_STOP = {"of", "the", "de", "des", "du", "der", "die", "das", "und", "and", "et", "la", "le",
               "el", "del", "di", "da", "van", "von", "for", "fur", "pour", "para", "w", "we", "i"}


def token_sort_key(name: str) -> str:
    """A name as a sorted bag of its words, for word-order variants.

    "Defence Ministry" and "Ministry of Defence" have the same key. Only ever used
    to *find* pairs worth a person's look; two names with one key are not one body.
    """
    return " ".join(sorted(t for t in re.split(r"[\s-]+", name) if t and t not in _TOKEN_STOP))


def candidate_key(raw: str) -> str:
    """The key under which two spellings are worth a person's look.

    Folded of state prefixes, a Romanian military unit reduced to its number (the
    ministry in front of it and the city behind it are decoration), word order
    ignored. Two names with one key are a *candidate* pair, never one body.
    """
    s = normalise_org_name(raw, fold_state=True)
    m = _RO_UNIT.search(s)
    if m:
        return f"unitatea militara {m.group(1)}"
    return token_sort_key(s)


# Words that mean "this value is not an identifier", seen in the buyer-identifier
# field of TED notices: placeholders, UUIDs, the eForms internal label (ORG-0001)
# and an organisation name typed into the field.
_ID_JUNK = re.compile(r"^(?:ORG\d+|N/?A|NONE|TBD|COM|NULL|UNKNOWN|NOTAPPLICABLE|NIL|X+|0+)$")
_ID_SCHEME = re.compile(
    r"\b(?:REGON|NIP|KRS|VAT|UID|ICO|IČO|DIC|DIČ|SIRET|SIREN|CIF|NIF|NIPC|CUI|CVR|ORGNR|ORG\.?NR|BTW|KVK|"
    r"PIC|ID|NO|NR|NUMBER|REG|REGISTRATION|NATIONAL|TAX|CODE|NUMERO|NUMMER|IDENTIFICATION)\b\.?:?"
)
_ID_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.IGNORECASE)


# A telephone number or an e-mail address typed into an identifier field (TED, 18 October 2026: 3 telephone
# numbers and 1 address among 8,368 supplier identifiers). A number with a leading "+" or a "tel" label is a
# contact detail, never a register number, whatever digits follow.
_CONTACT_SHAPED = re.compile(r"@|^\s*\+|^\s*\(?\s*(?:tel|tlf|fax|phone|telefon|telefono|tél|mob|gsm)\b", re.IGNORECASE)


def looks_like_contact(text: Any) -> bool:
    """True for an e-mail address or a telephone number as opposed to a register or tax number."""
    return bool(text) and bool(_CONTACT_SHAPED.search(str(text)))


def normalise_identifier(raw: Any, country: str | None = None) -> str | None:
    """The comparable form of a buyer's registration or tax number, or None.

    "REGON 170939001", "DE 139 601 469" and "DE139601469" are one number written
    three ways, and "COM", "n/a", "ORG-0001" and a UUID are not numbers at all.
    Stored with the country, because the same digits are different bodies in
    different registers. Deliberately strict: an identifier that is wrongly
    accepted merges two bodies, one that is wrongly refused only leaves the
    name-based resolution where it was.
    """
    if raw is None:
        return None
    text = str(raw).strip()
    if (not text or len(text) > 60 or "://" in text or ";" in text or "," in text
            or _ID_UUID.search(text) or looks_like_contact(text)):
        return None
    s = unicodedata.normalize("NFKD", text)
    s = "".join(c for c in s if not unicodedata.combining(c)).upper()
    s = _ID_SCHEME.sub(" ", s)
    s = re.sub(r"[^A-Z0-9]", "", s)
    cc = (country or "").upper()
    if cc and s.startswith(cc) and len(s) > len(cc) + 4 and s[len(cc)].isdigit():
        s = s[len(cc):]                    # DE139601469 -> 139601469
    if _ID_JUNK.match(s) or len(s) < 6 or sum(ch.isdigit() for ch in s) < 5:
        return None
    if len(set(s)) <= 2:
        return None
    valid = _REGISTER_CHECKS.get(cc)
    if valid is None:
        return s
    # WP-115: in these countries only a number of the register's own shape and check digit is one. A case
    # reference typed into the field ("DEZ/26/019/2020", "ZP.271.2.2021") split one Polish hospital into
    # 340 organisation rows, each with its own "registration number" (coverage audit, 24 October 2026).
    for cand in (s, s[len(cc):] if s.startswith(cc) else None):     # ESA28015865 is the CIF A28015865
        if cand and valid(cand):
            return cand
    if cc == "PL" and (pair := pl_number_pair(s)):
        return pair[0]
    return None


def pl_number_pair(s: str) -> tuple[str, str] | None:
    """WP-119: (NIP, REGON) of a Polish NIP and REGON written together in one field, either way round, each by its own
    check digit (167 buyer rows held such 19-digit values on 25 October 2026; the register check cleared them whole)."""
    if len(s) != 19 or not s.isdigit():
        return None
    for nip, regon in ((s[:10], s[10:]), (s[9:], s[:9])):
        if not nip.startswith("000") and _pl_register_number(nip) and _pl_register_number(regon):
            return nip, regon
    return None


# A Polish TERYT code of a gmina (7 digits: voivodeship 02-32 even, powiat, gmina, type 1-5), which buyers' forms carry
# where a number is asked (3024022 for Gmina Duszniki): no register number, even when zero-padded it passes a check digit.
_PL_TERYT = re.compile(r"(0[2468]|[12][02468]|3[02])\d{4}[1-5]")
# a case number with its year (17/2020 stored as 172020, 431/2021 as 4312021), which passes a check digit by chance
_PL_CASE_YEAR = re.compile(r"(?:19[89]\d|20[0-3]\d)$")


def pl_unpadded_regon(s: str) -> str | None:
    """WP-119: a Polish REGON written without its leading zeros (6 to 8 digits; 000177916 of a ministry stored as
    177916), in its 9-digit form when that form passes the REGON check digit and the value is not a TERYT code. A KRS
    number has no check digit, so one written short cannot be told from a case number and is never restored."""
    if not (s.isdigit() and 6 <= len(s) <= 8) or _PL_TERYT.fullmatch(s) or _PL_CASE_YEAR.search(s):
        return None
    padded = s.zfill(9)
    return padded if _pl_register_number(padded) else None


def _pl_register_number(s: str) -> bool:
    """A Polish NIP (10 digits), REGON (9 or 14) or KRS (10, written with its leading zeros), by its check digit.
    An 11-digit PESEL is a natural person's number and never an organisation's."""
    if not s.isdigit():
        return False
    weights = {9: (8, 9, 2, 3, 4, 5, 6, 7), 14: (2, 4, 8, 5, 0, 9, 7, 3, 6, 1, 2, 4, 8)}
    if len(s) in weights:                                   # REGON: a remainder of 10 is check digit 0
        return sum(int(d) * w for d, w in zip(s[:-1], weights[len(s)], strict=True)) % 11 % 10 == int(s[-1])
    if len(s) == 10:
        if s.startswith("000"):                             # KRS 0000123456 (no check digit); no tax office is 000
            return True
        c = sum(int(d) * w for d, w in zip(s[:-1], (6, 5, 7, 2, 3, 4, 5, 6, 7), strict=True)) % 11
        return c != 10 and c == int(s[-1])
    return False


_NIF_LETTERS = "TRWAGMYFPDXBNJZSQVHLCKE"


def _es_register_number(s: str) -> bool:
    """A Spanish NIF: a DNI (8 digits and a letter), an NIE (X, Y or Z, 7 digits, a letter) or a CIF (a letter of
    the entity type, 7 digits, a check digit or letter), each by its check character."""
    m = re.fullmatch(r"([XYZ\d])(\d{7})([A-Z])", s)
    if m:
        lead = str("XYZ".index(m[1])) if m[1] in "XYZ" else m[1]
        return _NIF_LETTERS[int(lead + m[2]) % 23] == m[3]
    m = re.fullmatch(r"([ABCDEFGHJNPQRSUVW])(\d{7})([0-9A-J])", s)
    if not m:
        return False
    d = [int(x) for x in m[2]]
    total = d[1] + d[3] + d[5] + sum(sum(divmod(2 * d[i], 10)) for i in (0, 2, 4, 6))
    c = (10 - total % 10) % 10
    return m[3] in (str(c), "JABCDEFGHI"[c])


_REGISTER_CHECKS = {"PL": _pl_register_number, "ES": _es_register_number}


# ------------------------------------------------------------ TED mapping

_LANG2_TO_3 = {v: k for k, v in _LANG3_TO_2.items()}


def _in_language(value: Any, lang3: str | None) -> str | None:
    """Pull one language out of a multilingual block.

    TED returns titles in all twenty-four EU languages at once, keyed by
    three-letter code. Taking whichever key comes first yields a Hungarian
    title on a Polish notice, so the language has to be named.
    """
    if not isinstance(value, dict) or not lang3:
        return None
    for key, val in value.items():
        if key.lower() == lang3.lower():
            got = _first(val)
            return str(got).strip() if got else None
    return None


# What a TED notice type means for the lifecycle. The value is `status`; the type
# itself is kept in status_native. Anything not listed is `unknown`, never `open`:
# a notice type we have not read is not something a supplier can act on.
#   contract notices and calls for competition   open (the deadline decides, and
#                                                effective_status turns a passed
#                                                one into expired)
#   award, modification and ex-ante notices      awarded (or cancelled, below)
#   prior information, market consultation       forthcoming
#   prior information used as a call             open when it states a deadline,
#     (pin-cfc-*)                                forthcoming when it does not
#   corrigendum                                  open when it states a deadline
TED_RESULT_TYPES = frozenset(
    {"can-standard", "can-social", "can-desg", "can-tran", "can-modif", "veat", "compl"})
# A prior-information notice that is itself the call for competition. The one rule for
# every source that republishes TED's types (TED, Atlas, e-Zamowienia): a deadline makes
# it a call that can be acted on; without one it announces a purchase.
PIN_AS_CALL = frozenset({"pin-cfc-standard", "pin-cfc-social"})
TED_STATUS_BY_TYPE: dict[str, str] = {
    **dict.fromkeys(("cn-standard", "cn-social", "cn-desg", "subco", "qu-sy", "corr"), "open"),
    **dict.fromkeys(TED_RESULT_TYPES, "awarded"),
    **dict.fromkeys(("pin-only", "pin-buyer", "pin-rtl", "pin-tran", "pmc"), "forthcoming"),
    **dict.fromkeys(PIN_AS_CALL, "forthcoming"),     # "open" with a deadline: ted_status
}


# Notice types that are not a step of a procurement (information notices of the buyer): they
# carry no deadline and are never a call or an award, so their status is `unknown` on purpose.
# Listing them here is what keeps the daily coverage check from alerting about a type that is
# known and deliberately unmapped.
TED_INFORMATION_TYPES = frozenset({"brin-only", "brin-ecs"})


def ted_notice_type(notice: dict[str, Any]) -> str | None:
    raw = _first(notice.get("notice-type"))
    return str(raw).strip().lower() if raw else None


def ted_status(notice_type: str | None, has_deadline: bool,
               lot_results: list[str] | None = None) -> str:
    """The lifecycle status of a TED notice, from its type and what it states.

    A result notice whose every lot is `clos-nw` (closed, no winner) awarded
    nothing and is `cancelled`; any lot with a winner, or a notice that does not
    say per lot (anything before eForms), is `awarded`.
    """
    status = TED_STATUS_BY_TYPE.get(notice_type or "")
    if status is None:
        return "unknown"
    if notice_type == "corr":
        return "open" if has_deadline else "unknown"
    if notice_type in PIN_AS_CALL:
        return "open" if has_deadline else "forthcoming"
    if (notice_type in TED_RESULT_TYPES and lot_results
            and all(r == "clos-nw" for r in lot_results)):
        return "cancelled"
    return status


def _each(value: Any) -> list[Any]:
    """TED sends a scalar or a list for the same field; always a list here."""
    if isinstance(value, (list, tuple)):
        return [v for v in value if v not in (None, "")]
    return [] if value in (None, "") else [value]


def _ted_deadline(g) -> datetime | None:
    """The tender deadline, to the minute and in the notice's own time zone.

    `deadline-receipt-request` (TED's union of BT-131, BT-1311 and BT-630) is a
    full ISO datetime per lot. Lots of one notice carry the same one in all but
    a rare case; the latest is taken, because a notice is still one a supplier can
    act on while any lot is. Where it is absent -- a payload fetched before it was
    requested -- the lot-level date and time fields are read, the request-to-
    participate time included: dropping it applied 23:59 to a deadline stated as
    08:00. `deadline-date-lot` is BT-13 (additional information) and is never read.
    """
    stamps = [t for t in (parse_iso_datetime(v) for v in _each(g("deadline-receipt-request")))
              if t is not None]
    if stamps:
        return max(stamps)
    return (_parse_datetime(g("deadline-receipt-tender-date-lot"),
                            g("deadline-receipt-tender-time-lot"))
            or _parse_datetime(g("deadline-receipt-request-date-lot"),
                               g("deadline-receipt-request-time-lot")))


def _lot_count(g) -> int | None:
    """How many lots the notice lists, from the per-lot lists TED returns.

    `description-lot` is a block per language each holding one entry per lot, and
    the per-lot deadline, winner and value lists agree with it. The longest wins,
    so a lot with no description or no value is still counted.
    """
    sizes = []
    desc = g("description-lot")
    if isinstance(desc, dict):
        sizes += [len(v) if isinstance(v, list) else 1 for v in desc.values()]
    for key in ("deadline-receipt-request", "winner-selection-status", "estimated-value-lot"):
        v = g(key)
        if isinstance(v, list):
            sizes.append(len(v))
    return max(sizes) if sizes and max(sizes) > 0 else None


# The tender sources whose connector never reads an estimated value, so an empty value there says nothing
# about the buyer: the BZP board listing (`from_ezamowienia`) and the TenderNed listing and detail
# (`from_tenderned`) carry none; it is on the notice document, a separate fetch per notice (WP-49 checked
# 20 current eZamowienia records: `htmlBody` null in all, and no value field in the TenderNed detail). The
# site words these "not collected from this source", not "not stated by the buyer".
VALUE_NOT_READ_SOURCES = frozenset({"pl_ezam", "nl_tenderned"})

# TED states 0, 0.01, 1 and -1 where the buyer did not know an amount (5,771 of the 95,000 TED
# notices with a value on 13 October 2026: 0.01 on 4,407, 0.00 on 822, 1.00 on 512, -1.00 on
# 30), and a few notices a figure no contract has (50 above ten billion, with lot values of
# millions). Faithful to the source, and not money. Such an amount is never the notice's value:
# the next of TED's value fields is used when it is sound, and when none is, the value is
# empty and `value_kind` says why. The notice keeps stating it in the raw payload and in
# every archived version before this rule.
VALUE_NOT_STATED = "not_stated"
VALUE_IMPLAUSIBLE = "implausible"
UNSERVED_VALUE_KINDS = frozenset({VALUE_NOT_STATED, VALUE_IMPLAUSIBLE})
# An amount of this or less is a placeholder in every source (TED's 0, 0.01, 1, -1; BOAMP's
# 0.01, 0.10, 1.00 on six awards; PLACSP's 0.00 on 45 rows), never a contract value.
PLACEHOLDER_AMOUNT_MAX = 1.0
# Ten billion and a cent less: 9,999,999,999.99 (98602-2021) and exactly 10,000,000,000
# (127753-2025) are fill characters, and the rule used to be "above" ten billion.
_IMPLAUSIBLE_AMOUNT_FROM = 9_999_999_999.0
# A total of a billion or more that the notice's own lots or estimate put a hundred times
# lower is a figure entered in the wrong unit (421 TED rows over a billion on 14 October
# 2026; of the 15 largest, 4 were x1000 entries: 220199-2026 states 7.27 billion for one
# lot of 7.3 million). The suspect total is not served; the lots' own figures are used.
_CONTRADICTED_FROM = 1e9
_CONTRADICTED_RATIO = 100
# WP-138 (r8-data problem 3): a "total" a notice states that is the price of one unit of what it buys, not the contract's:
# BWI's staffing call-offs (main CPV 7962, supply of personnel) state the hourly rate, EUR 27 to 105 ("EUR 74, the total
# the award notice states"), and the Bulgarian Ministry of Defence's electricity supplies (CPV 0931) the price of a MWh,
# BGN 1.25 to 9.29. On production (25 October 2026) these two codes held 294 and 24 totals of EUR 500 or less and none
# between 500 and 1,000 (personnel; electricity: none between 10 and 1,000): the next totals are contracts (2,000 and
# more). The amount stays on the row as the notice states it; `value_kind` says it is a unit price, and it is served
# as no value, borrowed by no twin and matched by no value range. Every other small total stands: a bus charter of
# EUR 119, a mattress of EUR 308, a print job of EUR 259 are contracts (475 of Puolustusvoimat's call-offs are so).
# ponytail: two CPV families by their main code; another family whose totals are rates is added here with its evidence.
VALUE_UNIT_PRICE = "unit_price"
UNIT_PRICE_TOTAL_MAX = 500.0
UNIT_PRICE_CPV_PREFIXES = ("7962", "0931")


def unit_price_total(amount: float | None, kind: str | None, cpv_codes: list[str] | None) -> bool:
    """WP-138: whether a notice's stated total is a unit price (`UNIT_PRICE_CPV_PREFIXES`, at most UNIT_PRICE_TOTAL_MAX)."""
    return (kind == "total" and amount is not None and PLACEHOLDER_AMOUNT_MAX < amount <= UNIT_PRICE_TOTAL_MAX
            and bool(cpv_codes) and str(cpv_codes[0])[:4] in UNIT_PRICE_CPV_PREFIXES)


def _ted_value(g, notice_type: str | None, lots: int | None
               ) -> tuple[float | None, str | None, str | None]:
    """(amount, currency, kind): which of TED's several values is the notice's.

    `kind` records the choice, so a figure can be told from an approximation:
      total        TED's own notice total (`total-value`; for a result notice the
                   awarded value, `result-value-notice` failing that)
      estimated    the procedure's estimated value
      lot_sum      every lot has a value, all in one currency: their sum
      first_lot    none of the above, so the first lot's value, which may be one of
                   several and is flagged as such rather than shown as the total
      not_stated   every value the notice gives is a placeholder (0, 0.01, 1, -1):
                   no amount, no currency
      implausible  the only value given is ten billion or more, or a billion and more that
                   the notice's own lots or estimate contradict a hundredfold: no amount
    """
    unusable: list[str] = []

    def pair(amount: str, currency: str) -> tuple[float | None, str | None]:
        got = _parse_amount(g(amount))
        cur = _first(g(currency))
        return got, (str(cur) if cur else None)

    stated = [a for a in (_parse_amount(v) for v in _each(g("estimated-value-lot")))
              if a is not None]
    # What the notice's own smaller figures say the whole can be at most: its estimate, and
    # its largest lot times the number of lots.
    ceilings: list[float] = []
    estimate = pair("estimated-value-proc", "estimated-value-cur-proc")[0]
    if estimate is not None and estimate > PLACEHOLDER_AMOUNT_MAX:
        ceilings.append(estimate)
    real_lots = [a for a in stated if a > PLACEHOLDER_AMOUNT_MAX]
    if real_lots:
        ceilings.append(max(real_lots) * max(lots or 1, len(real_lots)))

    def usable(amount: float | None, *, whole: bool = True) -> bool:
        if amount is None:
            return False
        if amount <= PLACEHOLDER_AMOUNT_MAX:
            unusable.append(VALUE_NOT_STATED)
            return False
        if amount >= _IMPLAUSIBLE_AMOUNT_FROM or (
                whole and amount >= _CONTRADICTED_FROM
                and any(amount > _CONTRADICTED_RATIO * c for c in ceilings if c != amount)):
            unusable.append(VALUE_IMPLAUSIBLE)
            return False
        return True

    if notice_type in TED_RESULT_TYPES:
        for amount, cur in (("total-value", "total-value-cur"),
                            ("result-value-notice", "result-value-cur-notice")):
            got, c = pair(amount, cur)
            if usable(got):
                return got, c, "total"
    got, c = pair("estimated-value-proc", "estimated-value-cur-proc")
    if usable(got):
        return got, c, "estimated"
    # Before the lots: a legacy notice states only this, and it is the figure TED
    # itself calls the notice's total.
    got, c = pair("total-value", "total-value-cur")
    if usable(got):
        return got, c, "total"

    amounts = [a for a in stated if usable(a, whole=False)]
    if amounts:
        currencies = {str(c).strip().upper() for c in _each(g("estimated-value-cur-lot"))}
        # TED lists each distinct currency once, not one per lot.
        if len(currencies) == 1 and len(amounts) == (lots or len(amounts)):
            total = round(sum(amounts), 2)
            if usable(total, whole=False):
                return total, next(iter(currencies)), "lot_sum"
        else:
            first_cur = _first(g("estimated-value-cur-lot"))
            return amounts[0], (str(first_cur) if first_cur else None), "first_lot"
    if unusable:
        kind = VALUE_IMPLAUSIBLE if VALUE_IMPLAUSIBLE in unusable else VALUE_NOT_STATED
        return None, None, kind
    return None, None, None


def _ted_buyer_identifier(value: Any) -> str | None:
    """The buyer's registration number as TED states it, or nothing.

    An organisation identifier, never a person: it must carry a digit (a name does
    not), must not be a telephone number or an address -- one German buyer filed
    its switchboard as `+49...` -- and is dropped, not cut, when it is too long to
    be an identifier at all.
    """
    raw = _first(value)
    if raw is None:
        return None
    text = str(raw).strip()
    if (not text or len(text) > 64 or text.startswith("+") or "@" in text
            or not any(ch.isdigit() for ch in text)):
        return None
    return text


def _ted_other_buyers(value: Any) -> list[str] | None:
    """The buyers a TED notice names after the first, in the block the first is read from (`_first`: English, else
    the first language), each once (WP-95: TED 711894-2026 names Nodrosinajuma valsts agentura and Valsts policija).
    None when the notice names one buyer."""
    block = value
    if isinstance(value, dict):
        block = next((value[k] for k in ("eng", "en") if k in value), None) or next(iter(value.values()), None)
    names = [" ".join(str(x).split()) for x in (block if isinstance(block, list) else [block]) if x not in (None, "")]
    first = names[0] if names else None
    out = [n for n in dict.fromkeys(names[1:]) if n and n != first][:10]
    return out or None


def _ted_text(value: Any, limit: int = 64) -> str | None:
    raw = _first(value)
    text = str(raw).strip()[:limit] if raw is not None else ""
    return text or None


def from_ted(notice: dict[str, Any]) -> Opportunity:
    """Map one raw TED notice onto the unified schema.

    Field references are the official TED search field names, see
    https://docs.ted.europa.eu/ODS/latest/reuse/field-list.html
    """
    g = notice.get

    # The publication number ("550462-2026") is the identifier TED uses in its
    # own URLs and the one a buyer can quote. notice-identifier is a UUID that
    # identifies the same thing but resolves nowhere, so it is only a fallback.
    native_id = _first(g("publication-number")) or _first(g("notice-identifier"))
    if not native_id:
        raise ValueError("notice has no identifier")

    description = _first(g("description-lot")) or _first(g("description-proc"))

    notice_type = ted_notice_type(notice)
    lots = _lot_count(g)
    value, currency, value_kind = _ted_value(g, notice_type, lots)
    if unit_price_total(value, value_kind, _clean_cpv(g("classification-cpv"))):
        value_kind = VALUE_UNIT_PRICE                                   # WP-138: a rate, not the total
    deadline = _ted_deadline(g)
    lot_results = [str(r).strip().lower() for r in _each(g("winner-selection-status"))]
    status = ted_status(notice_type, deadline is not None, lot_results)

    # `links` is a nested dict of format and language variants
    # ({"xml": {"MUL": ...}, "pdf": {"BUL": ..., "SPA": ...}}), so picking the
    # first leaf hands the user a Bulgarian PDF. Build the notice page instead;
    # it is the page a person can actually read and quote.
    url = f"https://ted.europa.eu/en/notice/-/detail/{native_id}"

    version = _first(g("notice-version"))
    try:
        version = int(version) if version is not None else None
    except (TypeError, ValueError):
        version = None

    clearance = _first(g("csecurity-clearance-description-lot"))
    nda = _first(g("non-disclosure-agreement-lot"))

    # TED publishes the title in every EU language. Keep the authoritative one
    # in title_original and take the English rendering for free rather than
    # paying a model to reproduce a translation the source already made.
    lang3 = str(_first(g("official-language")) or "").lower() or None
    title_block = g("notice-title")
    title_original = (_in_language(title_block, lang3)
                      or _in_language(title_block, _LANG2_TO_3.get((_lang2(g("official-language")) or "")))
                      or str(_first(title_block) or "").strip())
    title_en = _in_language(title_block, "eng")
    if title_en and title_en == title_original:
        title_en = None      # the notice is already English; do not duplicate it

    return Opportunity(
        source_code="ted",
        native_id=str(native_id),
        buyer_name_raw=str(_first(g("buyer-name")) or "").strip() or "UNKNOWN",
        other_buyers=_ted_other_buyers(g("buyer-name")),
        title_original=title_original,
        title_en=title_en,
        buyer_identifier=_ted_buyer_identifier(g("buyer-identifier")),
        country=_country2(g("buyer-country")),
        original_language=_lang2(g("official-language")),
        # The procedure as TED names it (open, restricted, neg-w-call, ...). The
        # subtype -- "16", "29", "E4" -- used to sit here and the API hides digits,
        # so 101,603 notices showed no procedure. It has its own column now.
        procedure_type=_ted_text(g("procedure-type")),
        notice_subtype=_ted_text(g("notice-subtype")),
        procedure_identifier=_ted_text(g("procedure-identifier")),
        lot_count=lots,
        value_kind=value_kind,
        legal_basis=_first(g("legal-basis")),
        value_amount=value,
        value_currency=(str(currency)[:3].upper() if currency else None),
        # The publication date, which is what TED shows and what "new since"
        # means. dispatch-date is when the buyer sent it, one to six days earlier.
        published_at=_parse_date(g("publication-date")) or _parse_date(g("dispatch-date")),
        deadline_at=deadline,
        status=status,
        status_native=notice_type,
        cpv_codes=_clean_cpv(g("classification-cpv")),
        source_url=str(url),
        notice_version=version,
        description=description,
        security_clearance_required=bool(clearance and str(clearance).strip()),
        nda_required=_as_bool(nda),
    )


# BOAMP hides its personal data one level down, inside the `donnees` string:
# `adresseMailContact`, `telContact`, `nomContact` in the simplified French
# form, a whole `cac:Contact` node with name, telephone and e-mail in eForms,
# and `IDENTITE.TEL` in notices from before 2018. A flat key filter cannot see
# any of it, so the body is walked.
_FR_CONTACT_KEY = re.compile(
    r"contact|mail|courriel|telephone|telecopie|^tel$|^fax$|^mel$", re.IGNORECASE)


def _scrub_contacts(node: Any) -> Any:
    """Drop every contact-bearing key, at any depth, keeping the rest intact."""
    if isinstance(node, dict):
        return {k: _scrub_contacts(v) for k, v in node.items()
                if not _FR_CONTACT_KEY.search(str(k))}
    if isinstance(node, list):
        return [_scrub_contacts(v) for v in node]
    return node


# Contact details are not only in contact fields. Measured on 22 September 2026
# across three sources: 300 recent TED payloads carried 6 e-mail addresses
# inside free text, and a week of French notices carried hundreds -- in
# "additional information", in the appeal-procedure paragraph, in notes. A
# named field can be dropped by name; an address typed into a sentence has to
# be found. So every string is swept, whatever source it came from.
# Bounded on purpose: with open-ended quantifiers a long run of address
# characters followed by an "@" cost a quadratic scan, and `re` holds the GIL.
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]{1,255}\.[A-Za-z]{2,24}")
EMAIL_PLACEHOLDER = "[email removed]"


def _redact_emails(node: Any) -> Any:
    if isinstance(node, str):
        return _EMAIL.sub(EMAIL_PLACEHOLDER, node) if "@" in node else node
    if isinstance(node, dict):
        return {k: _redact_emails(v) for k, v in node.items()}
    if isinstance(node, list):
        return [_redact_emails(v) for v in node]
    return node


def redact_emails(node: Any) -> Any:
    """Public name of the redaction used at the boundary, for serving as well."""
    return _redact_emails(node)


def scrub_opportunity(opp: "Opportunity") -> "Opportunity":
    """Redact addresses and drop NUL characters in every text field of a record.

    For sources whose connector parses while fetching (PLACSP): their record is
    built before there is a raw payload to pass through strip_personal_data, so it
    has to be swept at this point or the "one boundary" has a hole in it.
    """
    from dataclasses import fields as _fields

    for f in _fields(opp):
        value = getattr(opp, f.name)
        if isinstance(value, str):
            setattr(opp, f.name, _redact_emails(value.replace("\x00", "")[:MAX_STRING]))
    opp.source_url = http_url(opp.source_url)
    return opp


# eForms UBL (German BKMS day files): elements that are, or hold, personal data. `Contact`
# is name, telephone, telefax and e-mail of buyers, winners, service providers and
# touch points; the beneficial owner and the jury member are natural persons by definition.
_EFORMS_DROP = frozenset({
    "Contact", "ElectronicMail", "Telephone", "Telefax", "UltimateBeneficialOwner",
    "TechnicalCommitteePerson", "FamilyName", "FirstName", "MiddleName", "JobTitle",
    "BirthDate", "BirthplaceName", "ResidenceAddress"})
MAX_EFORMS_XML = 8 * 1024 * 1024


def strip_eforms_xml(xml: Any) -> str | None:
    """An eForms notice file without its personal data, or None when it cannot be made safe.

    Contact blocks and person elements are removed at any depth; an organisation flagged
    `NaturalPersonIndicator` true keeps only its identifier, since its name and address are
    a person's; addresses written into prose are replaced. A file that is too large,
    declares a document type, or does not parse is dropped, not kept: it cannot be scrubbed.
    """
    import xml.etree.ElementTree as ET

    if not isinstance(xml, str) or len(xml) > MAX_EFORMS_XML:
        return None
    if re.search(r"<!\s*(DOCTYPE|ENTITY)", xml, re.IGNORECASE):
        return None
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return None

    def local(el: Any) -> str:
        return str(el.tag).rsplit("}", 1)[-1]

    def sweep(el: Any, depth: int = 0) -> None:
        if depth > MAX_DEPTH:
            raise ValueError("eForms document nested too deeply")
        natural = local(el) == "Organization" and any(
            local(c) == "NaturalPersonIndicator" and (c.text or "").strip().lower() == "true"
            for c in el)
        for child in list(el):
            if local(child) in _EFORMS_DROP:
                el.remove(child)
                continue
            if natural and local(child) in ("Company", "TouchPoint"):
                for part in list(child):
                    if local(part) != "PartyIdentification":
                        child.remove(part)
            sweep(child, depth + 1)
        for text_attr in ("text", "tail"):
            value = getattr(el, text_attr)
            if value and "@" in value:
                setattr(el, text_attr, _EMAIL.sub(EMAIL_PLACEHOLDER, value))
        for k, v in list(el.attrib.items()):
            if "@" in v:
                el.attrib[k] = _EMAIL.sub(EMAIL_PLACEHOLDER, v)

    try:
        sweep(root)
    except (ValueError, RecursionError):
        return None
    return ET.tostring(root, encoding="unicode").replace("\x00", "")


# The same person elements when a source sends eForms as JSON (BOAMP's `donnees`, keys like
# "cbc:FamilyName"), compared on the local name. Walked at every depth for every source
# (WP-71, QA H1/M5): the key filter used to see the top level only.
def _local(key: Any) -> str:
    return str(key).rsplit(":", 1)[-1].lstrip("@")


def _true(value: Any) -> bool:
    if isinstance(value, dict):
        value = value.get("#text")
    return str(value).strip().lower() == "true"


# A Polish PESEL (11 digits) is a natural person's number; a NIP (10) or REGON (9, 14) cannot
# tell a sole trader (CEIDG) from a company, so the name decides there.
_PESEL = re.compile(r"\d{11}")
# e-Zamowienia `contractors[]`: the fields that identify a winner who is a natural person.
_EZAM_PERSON_FIELDS = ("contractorNationalId", "contractorCity", "contractorProvince",
                       "contractorAddress", "contractorStreet", "contractorPostalCode")


def contractor_is_person(entry: dict[str, Any]) -> bool:
    """Whether an e-Zamowienia contractor entry is a natural person (a CEIDG sole trader)."""
    from .awards import person_reason

    name = str(entry.get("contractorName") or "")
    ident = re.sub(r"\D", "", str(entry.get("contractorNationalId") or ""))
    if _PESEL.fullmatch(ident):
        return True
    return person_reason(name, None, str(entry.get("contractorCountry") or "PL")[:2].upper()) is not None


def _strip_nested(node: Any) -> Any:
    """Drop person-bearing keys at any depth and blank the natural persons among organisations.

    Runs after `_bound`, so the depth is already capped."""
    if isinstance(node, list):
        return [_strip_nested(v) for v in node]
    if not isinstance(node, dict):
        return node
    if "contractorName" in node and contractor_is_person(node):
        from .awards import PERSON_PLACEHOLDER

        node = {k: v for k, v in node.items() if k not in _EZAM_PERSON_FIELDS}
        node["contractorName"] = PERSON_PLACEHOLDER
    # an eForms organisation flagged as a natural person keeps only its identifier
    natural = any(_local(k) == "NaturalPersonIndicator" and _true(v) for k, v in node.items())
    out: dict[Any, Any] = {}
    for k, v in node.items():
        if k in PERSONAL_DATA_FIELDS or _local(k) in _EFORMS_DROP:
            continue
        if natural and _local(k) in ("Company", "TouchPoint"):
            parts = v if isinstance(v, list) else [v]
            v = [{pk: pv for pk, pv in p.items() if _local(pk) == "PartyIdentification"}
                 if isinstance(p, dict) else None for p in parts]
            v = v if isinstance(node[k], list) else v[0]
        out[k] = _strip_nested(v)
    return out


def strip_personal_data(notice: dict[str, Any]) -> dict[str, Any]:
    """Remove personal-data fields before a payload is persisted or served.

    The raw archive keeps the original for reprocessing and audit, under
    restricted access. Everything downstream of this call is clean.

    Two passes, because personal data arrives two ways: named fields, which are
    dropped by name, and addresses written into prose, which are found and
    replaced. Telephone numbers in prose are deliberately *not* swept: French
    notices put SIRET numbers, contract references and amounts in the same
    sentences, and a pattern loose enough to catch the phone numbers corrupts
    those. They stay, and stay known: docs/RUNBOOK.md records it.

    The French body is handled apart from the rest. It arrives as a JSON string,
    and redaction must happen on what that string decodes to, never on the
    string itself: on 23 September 2026 an address preceded by an escaped
    newline was matched together with the escape's `n`, which left a dangling
    backslash and an archive entry that no longer parsed.
    """
    clean = {k: v for k, v in notice.items() if k not in PERSONAL_DATA_FIELDS}
    # German BKMS notice file (eForms UBL): the XML is taken apart on its own, because
    # `_bound` below cuts every string at MAX_STRING and a notice can be longer.
    if "xml" in clean and "file" in clean and "notice_id" in clean:
        xml = clean.pop("xml")
        clean = _redact_emails(_strip_nested(_bound(clean)))
        clean["xml"] = strip_eforms_xml(xml)
        return clean
    body = clean.pop("donnees", None) if "idweb" in clean else None
    clean = _redact_emails(_strip_nested(_bound(clean)))
    if body is None:
        return clean

    parsed: Any = body
    if isinstance(body, str):
        if not body.strip():
            clean["donnees"] = body
            return clean
        try:
            parsed = json.loads(body)
        except (ValueError, RecursionError):
            # Unparsable: it cannot be scrubbed, so it is not kept. The
            # record's own columns still describe the notice.
            clean["donnees"] = None
            return clean
    scrubbed = _redact_emails(_strip_nested(_scrub_contacts(_bound(parsed))))
    clean["donnees"] = (json.dumps(scrubbed, ensure_ascii=False)
                        if isinstance(body, str) else scrubbed)
    return clean


# --------------------------------------------------------- BOAMP mapping

_FR_TZ = "Europe/Paris"

# Which regimes are the defence and security directive. `perimetre` states it;
# DIRECTIVE-81 is Directive 2009/81/EC and CMP-2006-DEFENSE its French
# predecessor. Recorded as the CELEX reference every other source uses.
_FR_DEFENCE_PERIMETERS = {"DIRECTIVE-81", "CMP-2006-DEFENSE"}

# The lifecycle is the notice's `nature`: APPEL_OFFRE is a call for competition (open
# until its deadline says otherwise), ATTRIBUTION and RESULTAT are the award, and
# INTENTION_CONCLURE (the notice of intention to conclude, TED's veat) comes with the
# awards, as do MODIFICATION and EX_ANTE_VOLONTAIRE (TED's can-modif and veat, which
# the decision of 12 October 2026 maps to awarded); PRE-INFORMATION and PERIODIQUE are
# prior-information notices, ANNULATION a cancellation. Anything not listed (AUTRE, a
# nature nobody has read) is `unknown`, never `open`: a type we have not read is not
# something a supplier can act on.
#
# A rectificatif may keep the `nature` of the notice it corrects (an award's correction
# is then `awarded`, a call's `open`), and 449 of 453 stored ones have the nature
# RECTIFICATIF, which names no parent. For those the notice itself is read, as TED's
# corrigendum is: one that states a deadline for offers is a corrected call and `open`;
# without one its parent type is not determinable and it is `unknown`.
_FR_STATUS = {
    "APPEL_OFFRE": "open",
    "ATTRIBUTION": "awarded",
    "RESULTAT": "awarded",
    "INTENTION_CONCLURE": "awarded",
    "MODIFICATION": "awarded",
    "EX_ANTE_VOLONTAIRE": "awarded",
    "PRE-INFORMATION": "forthcoming",
    "PRE_INFORMATION": "forthcoming",
    "PERIODIQUE": "forthcoming",
    "ANNULATION": "cancelled",
}


# WP-113: the other directives, as `perimetre` names them (DIRECTIVE-24 is 2014/24/EU) or an eForms notice states
# them (`cbc:RegulatoryDomain`, 32014L0024 on 24-21716): 5,409 BOAMP notices showed no legal basis where TED,
# TenderNed and the German service show 2014/24.
_FR_PERIMETER_ACTS = {"DIRECTIVE-24": "32014L0024", "DIRECTIVE-25": "32014L0025", "DIRECTIVE-23": "32014L0023"}
_FR_CELEX = frozenset({"32009L0081", "32014L0024", "32014L0025", "32014L0023"})


def _fr_legal_basis(perimetre: str, body: dict[str, Any]) -> str | None:
    if perimetre in _FR_DEFENCE_PERIMETERS:
        return "32009L0081"
    for node in _fr_nodes(body, ("EFORMS", "*", "cbc:RegulatoryDomain")):
        text = (_fr_text(node) or "").upper()
        if text in _FR_CELEX:
            return text
    return _FR_PERIMETER_ACTS.get(perimetre)


def _fr_status(record: dict[str, Any], has_deadline: bool) -> str:
    nature = str(record.get("nature") or "").strip().upper()
    status = _FR_STATUS.get(nature)
    if status is not None:
        return status
    rectificatif = nature == "RECTIFICATIF" or str(record.get("etat") or "").upper() == "RECTIFICATIF"
    if rectificatif and has_deadline:
        return "open"
    return "unknown"


def _fr_walk(node: Any, key_part: str) -> Iterator[Any]:
    """Every value whose key contains `key_part`, at any depth."""
    if isinstance(node, dict):
        for k, v in node.items():
            if key_part.lower() in str(k).lower():
                yield v
            yield from _fr_walk(v, key_part)
    elif isinstance(node, list):
        for v in node:
            yield from _fr_walk(v, key_part)


def _fr_legacy_cpv(node: Any, out: list[str]) -> None:
    """CPV blocks of the BOAMP schemas (Boamp_v230.xsd, Boamp_v240.xsd).

    A `CPV` key holds `PRINCIPAL` and, when present, `SUPPLEMENTAIRE`: a single
    block (`OBJET.CPV`), a list of them, and one per lot (`OBJET.LOTS.LOT[].CPV`).
    `SUPPLEMENTAIRE` mixes the eight-digit CPV codes with the four-character
    supplementary vocabulary (`AB25`), which is not a CPV code and is left out.
    A rectificatif's block says `INIT` (what is corrected) and `LIRE` (what it
    now reads): only the second is the notice's CPV.
    """
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "CPV":
                for block in value if isinstance(value, list) else [value]:
                    if isinstance(block, dict) and "LIRE" in block:
                        block = block["LIRE"]
                    out.extend(_clean_cpv(block))
            else:
                _fr_legacy_cpv(value, out)
    elif isinstance(node, list):
        for item in node:
            _fr_legacy_cpv(item, out)


def _fr_cpv(body: dict[str, Any]) -> list[str]:
    """CPV codes from every notice shape the dataset holds, deduplicated, in order.

    eForms puts them in `cbc:ItemClassificationCode` as `{"#text": "35700000"}`;
    the simplified French form uses `codeCPV.objetPrincipal.classPrincipale`
    and one per lot; the schemas of 2015 to 2022 use `OBJET.CPV.PRINCIPAL`
    (`_fr_legacy_cpv`). Until 12 October 2026 only the first two were read, so
    4,175 of 4,185 stored rows, every one of 2015-2020, had no CPV although
    150 of 150 sampled legacy notices carry one. A notice that states none
    still gets an empty list, never a guess.
    """
    codes: list[str] = []
    for value in _fr_walk(body, "ItemClassificationCode"):
        text = value.get("#text") if isinstance(value, dict) else value
        if isinstance(text, str) and text.strip().isdigit():
            codes.append(text.strip()[:8])
    for value in _fr_walk(body, "codeCPV"):
        if isinstance(value, dict):
            for inner in _fr_walk(value, "class"):
                if isinstance(inner, str) and inner.strip().isdigit():
                    codes.append(inner.strip()[:8])
    _fr_legacy_cpv(body, codes)
    seen: set[str] = set()
    return [c for c in codes if not (c in seen or seen.add(c))]


def _fr_nodes(node: Any, path: tuple[str, ...]) -> list[Any]:
    """Every value at an exact key path, a list level being transparent.

    `*` matches any one key. Exact paths rather than the substring walk above,
    because a value's meaning is given by where it sits: the same element name
    is the notice's value at the top and one lot's value inside a lot.
    """
    nodes = [node]
    for key in path:
        found: list[Any] = []
        for current in nodes:
            for item in current if isinstance(current, list) else [current]:
                if not isinstance(item, dict):
                    continue
                for k, v in item.items():
                    if key == "*" or k == key:
                        found.extend(v if isinstance(v, list) else [v])
        nodes = found
    return nodes


def _fr_amount(raw: Any) -> float | None:
    """A plausible amount from `12500`, `"12 500,50"` or `"12500.00"`.

    Zero is "not stated", not a value: the simplified form writes `0.00` for a
    lot whose estimate the buyer left blank (102 of 102 sampled zeros), and an amount
    of one euro or less is a placeholder as in TED (six awards held 0.01, 0.10 and
    1.00). Anything the NUMERIC(16,2) column could not hold is dropped rather than
    failing the notice.
    """
    if isinstance(raw, bool) or raw is None:
        return None
    text = str(raw).replace("\xa0", "").replace(" ", "")
    if re.fullmatch(r"\d+,\d{1,2}", text):
        text = text.replace(",", ".")
    if not re.fullmatch(r"\d+(\.\d+)?", text):
        return None
    amount = float(text)
    return amount if PLACEHOLDER_AMOUNT_MAX < amount < 10 ** 14 else None


def _fr_money(node: Any, inner: tuple[str, ...] = ()) -> tuple[float, str] | None:
    """(amount, currency) from the two element shapes the notices use.

    `{"#text": "7000000", "@currencyID": "EUR"}` (BOAMP legacy, eForms: the
    currency is an attribute of the amount) and the simplified form's
    `{"@devise": "EUR", "valeur": "55150"}` (`inner` names the amount inside).

    The currency is the one the notice states and is never converted. Only when
    a French notice states none is it taken to be EUR; the legacy schema makes
    `DEVISE` mandatory, so this is a default for malformed input, not a habit.
    A stated currency that is not a three-letter code is not guessed at: the
    value is dropped.
    """
    if isinstance(node, (str, int, float)) and not inner:
        node = {"#text": node}          # an amount written without attributes
    if not isinstance(node, dict):
        return None
    raw: Any = node
    for key in inner or ("#text",):
        raw = raw.get(key) if isinstance(raw, dict) else None
    amount = _fr_amount(raw)
    if amount is None:
        return None
    stated = node.get("@DEVISE") or node.get("@devise") or node.get("@currencyID")
    if stated is None or str(stated).strip() == "":
        return amount, "EUR"
    code = str(stated).strip().upper()
    return (amount, code) if re.fullmatch(r"[A-Z]{3}", code) else None


# Where a BOAMP notice states a value, in the order they are tried. A rule is
# (parents, leaf, exactly_one_parent, inner): the leaf is looked for under every
# node at `parents`, and `exactly_one_parent` makes the rule apply only when the
# notice has a single such node -- a notice of several lots whose lots state their
# own amounts has no single value, and the first lot is not the notice.
#
# The meaning of each, from Boamp_v230.xsd and Boamp_v240.xsd (DILA, echanges.dila.gouv.fr/
# schemabook/boamp) and 4,185 stored legacy notices plus 4,000 of October 2026:
#
#   awarded      ATTRIBUTION.VALEUR_TOTALE      total final value of the award(s)
#                efac:NoticeResult TotalAmount  eForms BT-161, value of all contracts
#                DECISION.RENSEIGNEMENT.MONTANT final value of the one award
#   estimated    CARACTERISTIQUES.VALEUR_TOTALE "Valeur totale estimee" (XSD)
#                CARACTERISTIQUES.VALEUR        estimated value, one amount
#                ACCORD_CADRE.VALEUR            estimated value of a framework
#                EstimatedOverallContractAmount eForms BT-27, at procedure level, or in
#                                               the only lot
#                natureMarche.valeurEstimee     simplified form, one amount
#   initial      DECISION...ESTIMATION_INITIALE the estimate an award was made against
#   ceiling      VALEUR_MAX, FrameworkMaximum*, valeurHaute: the most the contract or
#                framework can reach. Used last, and only the top of a range, never
#                the bottom (VALEUR_MIN alone is not a value).
#
# An awarded amount comes before an estimate: an award notice repeats the whole
# notice, so both are present, and the award is the fact. Nothing is summed and
# nothing is converted.
#
# VAT. No BOAMP schema carries a tax marker (searched in both XSDs). The standard
# forms (JOUE, eForms) define their values as excluding VAT; for the national
# forms (FNS, FNSimple) the documentation found says nothing. The amount is kept
# as the notice states it and the basis is not asserted.
_FR_EXT = ("ext:UBLExtensions", "ext:UBLExtension", "ext:ExtensionContent",
           "efext:EformsExtension")
_FR_VALUE_RULES: tuple[tuple[tuple[str, ...], tuple[str, ...], bool, tuple[str, ...]], ...] = (
    # awarded
    (("ATTRIBUTION",), ("VALEUR_TOTALE",), False, ()),
    (("EFORMS", "*", *_FR_EXT, "efac:NoticeResult"), ("cbc:TotalAmount",), False, ()),
    (("ATTRIBUTION", "DECISION", "RENSEIGNEMENT"), ("MONTANT",), True, ()),
    # estimated
    (("OBJET", "CARACTERISTIQUES"), ("VALEUR_TOTALE",), False, ()),
    (("OBJET", "CARACTERISTIQUES"), ("VALEUR",), False, ()),
    (("OBJET", "ACCORD_CADRE"), ("VALEUR",), False, ()),
    (("EFORMS", "*", "cac:ProcurementProject", "cac:RequestedTenderTotal"),
     ("cbc:EstimatedOverallContractAmount",), False, ()),
    (("EFORMS", "*", "cac:ProcurementProjectLot"),
     ("cac:ProcurementProject", "cac:RequestedTenderTotal",
      "cbc:EstimatedOverallContractAmount"), True, ()),
    (("FNSimple", "*", "natureMarche"), ("valeurEstimee",), False, ("valeur",)),
    # the estimate an award was made against
    (("ATTRIBUTION", "DECISION"), ("RENSEIGNEMENT", "ESTIMATION_INITIALE"), True, ()),
    # ceilings
    (("OBJET", "ACCORD_CADRE"), ("VALEUR_MAX",), False, ()),
    (("OBJET", "CARACTERISTIQUES"), ("VALEUR_MAX",), False, ()),
    (("EFORMS", "*", *_FR_EXT, "efac:NoticeResult"),
     ("efbc:OverallMaximumFrameworkContractsAmount",), False, ()),
    (("EFORMS", "*", "cac:ProcurementProject", "cac:RequestedTenderTotal", *_FR_EXT),
     ("efbc:FrameworkMaximumAmount",), False, ()),
    (("FNSimple", "*", "natureMarche"), ("valeurEstimee",), False, ("fourchette", "valeurHaute")),
)


def _fr_value(body: dict[str, Any]) -> tuple[float | None, str | None]:
    """The contract value a BOAMP notice states, by the precedence above, or none."""
    for parents, leaf, one_parent, inner in _FR_VALUE_RULES:
        nodes = _fr_nodes(body, parents)
        if one_parent and len(nodes) != 1:
            continue
        for node in nodes:
            for value in _fr_nodes(node, leaf):
                got = _fr_money(value, inner)
                if got:
                    return got
    return None, None


def _fr_description(body: dict[str, Any]) -> str | None:
    for value in _fr_walk(body, "description"):
        if isinstance(value, str) and len(value.strip()) > 10:
            return value.strip()
        if isinstance(value, dict) and isinstance(value.get("#text"), str):
            return value["#text"].strip()
    return None


def _fr_corrected_notice(record: dict[str, Any], body: dict[str, Any],
                        native_id: str) -> str | None:
    """The `idweb` of the notice a rectificatif corrects, or None.

    A rectificatif (`etat` RECTIFICATIF) is a notice of its own that repeats the
    whole of its parent. The legacy notice names the one it corrects itself, in
    `RECTIF.ANNONCE_ANTERIEUR.REFERENCE.IDWEB`. The record's `annonce_lie` lists
    that notice and, once it has been corrected before, the earlier rectificatifs,
    and not with the corrected notice first: in 3 of 198 stored rectificatifs it is
    second. So `annonce_lie` is used on its own only when it has one entry. A
    2026 rectificatif with several entries and no reference of its own (31 of 335
    sampled) stays unlinked: the immediate parent is not stated, and a guess
    would hide an award correction behind the tender it belongs to.
    """
    if str(record.get("etat") or "").upper() != "RECTIFICATIF":
        return None
    named = {str(v).strip() for v in _fr_nodes(
        body, ("RECTIF", "ANNONCE_ANTERIEUR", "REFERENCE", "IDWEB")) if v}
    if not named:
        listed = record.get("annonce_lie")
        named = {str(v).strip() for v in (listed if isinstance(listed, list) else [])
                 if v and str(v).strip()}
    named.discard(native_id)
    return named.pop() if len(named) == 1 else None


def _fr_procedure_id(record: dict[str, Any]) -> str | None:
    """The eForms procedure identifier (BT-04) of a BOAMP notice, as TED spells it.

    The record's `contractfolderid` column repeats `cbc:ContractFolderID`, which an
    eForms notice sets to the procedure's UUID: the same value TED publishes as
    `procedure-identifier`, so it ties this notice to its TED twin. Legacy notices
    have no such column. Anything that is not a UUID is not an identifier.
    """
    value = record.get("contractfolderid")
    if isinstance(value, list):
        value = next((v for v in value if isinstance(v, str) and v.strip()), None)
    text = value.strip().strip("{}").strip().lower() if isinstance(value, str) else ""
    return text if _ID_UUID.fullmatch(text) else None


# The end of the period in which an eForms notice takes offers (BT-131 for an open
# procedure, BT-1311 for a restricted one) sits in the notice body, per lot. The record's
# `datelimitereponse` column is DILA's own reading of it and is empty for 32% of the call
# notices (2,049 of 6,386 on 13 October 2026, 119 of 129 effective-open ones already past
# their deadline). Where the column is present it is not the notice's instant either: for
# a time written `12:00:00.000+02:00` it carries the wall time as UTC, two hours late
# (12 of 30 BOAMP notices with a TED twin differ from TED by exactly the offset; the body
# read as stated agrees with TED).
_FR_DEADLINE_PERIODS = ("ParticipationRequestReceptionPeriod", "TenderSubmissionDeadlinePeriod")


def _fr_text(value: Any) -> str | None:
    if isinstance(value, dict):
        value = value.get("#text")
    return value.strip() if isinstance(value, str) and value.strip() else None


def _fr_eforms_deadline(body: dict[str, Any], zone: str = _FR_TZ) -> datetime | None:
    """The latest end of an offers period in an eForms notice, as the notice states it.

    The date and the time each carry an offset; the time's is read first, as TED's
    own deadline is, and Europe/Paris applies where neither states one. The latest of
    the lots is taken: the notice can be acted on while any lot can.
    """
    stamps: list[datetime] = []
    for key in _FR_DEADLINE_PERIODS:
        for node in _fr_walk(body, key):
            for period in node if isinstance(node, list) else [node]:
                if not isinstance(period, dict):
                    continue
                stamp = _parse_datetime(_fr_text(period.get("cbc:EndDate")),
                                        _fr_text(period.get("cbc:EndTime")),
                                        default_tz=ZoneInfo(zone))
                if stamp is not None:
                    stamps.append(_paris_wall_time(stamp, zone))
    return max(stamps) if stamps else None


def _paris_wall_time(stamp: datetime, zone: str = _FR_TZ) -> datetime:
    """A French deadline written with a Paris offset (+01:00 or +02:00) as the wall time it is on that day in the
    buyer's zone (Paris, or an overseas one: `_fr_zone`).

    BOAMP writes the offset in force when the notice is published, not on the deadline's date: a notice of October
    states "12:00:00+02:00" for 19 November, when Paris is at +01:00, and BOAMP's own page says "12h00", which is
    11:00 UTC, where reading the offset gave 10:00 (WP-96, p10 /tenders/269424). So the printed time is read in
    the zone for the date itself. WP-113: an overseas buyer's notice carries the same Paris offset on its own local
    wall time (26-98817, DID Saint-Denis de La Reunion, "12:00:00.000+02:00" for 12:00 Reunion). Any other offset
    (Z, an overseas one) is the notice's own and stays."""
    if stamp.utcoffset() in (timedelta(hours=1), timedelta(hours=2)):
        return stamp.replace(tzinfo=ZoneInfo(zone))
    return stamp


# WP-113: the zone of a French buyer outside metropolitan France, by the first three digits of its postcode or its
# department code (971-978, 986-988). Metropolitan France and Corsica are Europe/Paris.
_FR_OVERSEAS_TZ = {
    "971": "America/Guadeloupe", "972": "America/Martinique", "973": "America/Cayenne",
    "974": "Indian/Reunion", "975": "America/Miquelon", "976": "Indian/Mayotte",
    "977": "America/St_Barthelemy", "978": "America/Marigot",
    "986": "Pacific/Wallis", "987": "Pacific/Tahiti", "988": "Pacific/Noumea",
}


def _fr_buyer_postcode(body: dict[str, Any]) -> str | None:
    """The buyer's postcode: the national form's `organisme.cp`, or in eForms the address of the organisation the
    contracting party names (ORG-0001 as a rule; the review body and others are listed beside it)."""
    for org in _fr_nodes(body, ("*", "organisme")):
        if isinstance(org, dict) and _fr_text(org.get("cp")):
            return _fr_text(org.get("cp"))
    ids = {_fr_text(n) for n in _fr_nodes(body, ("EFORMS", "*", "cac:ContractingParty", "cac:Party",
                                                   "cac:PartyIdentification", "cbc:ID"))}
    for org in _fr_walk(body, "efac:Organization"):
        for item in org if isinstance(org, list) else [org]:
            company = item.get("efac:Company") if isinstance(item, dict) else None
            if not isinstance(company, dict):
                continue
            own = _fr_text((company.get("cac:PartyIdentification") or {}).get("cbc:ID"))
            if own in ids:
                return _fr_text((company.get("cac:PostalAddress") or {}).get("cbc:PostalZone"))
    return None


def _fr_zone(record: dict[str, Any], body: dict[str, Any]) -> str:
    """The time zone a BOAMP notice's wall times are in: the buyer's own (postcode first; else the first department
    the record lists, which is the buyer's: 26-103716 lists 973, 972, 971 for a buyer in Cayenne)."""
    code = (_fr_buyer_postcode(body) or "").replace(" ", "")[:3]
    if not code.isdigit():
        depts = record.get("code_departement")
        first = depts[0] if isinstance(depts, list) and depts else depts
        code = str(first or "").strip()[:3]
    return _FR_OVERSEAS_TZ.get(code, _FR_TZ)


def _fr_national_deadline(record: dict[str, Any], body: dict[str, Any], zone: str) -> datetime | None:
    """The offers deadline of the national forms (FNSimple, MAPA): `dateReceptionOffres`, a wall time without an
    offset, in the buyer's zone. WP-113: DILA's `datelimitereponse` repeats it with a false "+00:00" (26-98956,
    "2026-10-29T16:00:00+00:00" for 16:00 in Paris: 124 of 124 such notices since 2025 were an hour or two late), so
    where the body states none the column's printed time is read in the same zone."""
    stamps = [parse_iso_datetime(text[:19], default_tz=ZoneInfo(zone))
              for node in _fr_walk(body, "dateReceptionOffres")
              for item in (node if isinstance(node, list) else [node])
              if (text := _fr_text(item))]
    stamps = [s for s in stamps if s is not None]
    if stamps:
        return max(stamps)
    if not any(k in body for k in ("FNSimple", "MAPA")):
        return None
    column = _fr_text(record.get("datelimitereponse"))
    return parse_iso_datetime(column[:19], default_tz=ZoneInfo(zone)) if column else None


def _fr_legacy_deadline(body: dict[str, Any], zone: str = _FR_TZ) -> datetime | None:
    """The offers deadline of a notice in the schemas of 2015-2022, `CONDITION_DELAI.RECEPT_OFFRES`.

    1,792 stored `open` rows had no deadline and about 1,400 of them state one here
    (round 2, 14 October 2026). The value is a wall time with a fixed `+01:00` that the
    converter writes on every notice: 22 of 22 sampled, 2021 July dates included, where
    Paris is at +02:00. A constant is not information, so the printed date and time are
    Paris wall time; an offset other than `+01:00` (or `Z`) is the notice's own and wins.
    """
    stamps: list[datetime] = []
    for node in _fr_walk(body, "RECEPT_OFFRES"):
        for item in node if isinstance(node, list) else [node]:
            text = _fr_text(item)
            if not text:
                continue
            fixed = text[-6:] == "+01:00" and len(text) > 6
            stamp = parse_iso_datetime(text[:-6] if fixed else text,
                                       default_tz=ZoneInfo(zone))
            if stamp is not None:
                stamps.append(_paris_wall_time(stamp, zone))
    return max(stamps) if stamps else None


def _fr_diffusion_over(record: dict[str, Any], today: date | None = None) -> bool:
    """The bulletin has stopped publishing the notice: its `datefindiffusion` is past."""
    end = _parse_date(record.get("datefindiffusion"))
    return end is not None and end < (today or date.today())


def _fr_lot_count(body: dict[str, Any]) -> int | None:
    """How many lots the notice lists, in the three shapes that list them.

    eForms `cac:ProcurementProjectLot` (a `Part` is not a lot), the legacy schemas'
    `OBJET.LOTS.LOT` and the simplified form's `lots.lot`. A notice that lists none is a
    single contract and says nothing: None, not 1.
    """
    for path in (("EFORMS", "*", "cac:ProcurementProjectLot"), ("OBJET", "LOTS", "LOT"),
                 ("FNSimple", "*", "lots", "lot"), ("MAPA", "*", "lots", "lot")):
        nodes = [n for n in _fr_nodes(body, path)
                 if not (isinstance(n, dict) and isinstance(n.get("cbc:ID"), dict)
                         and n["cbc:ID"].get("@schemeName") == "Part")]
        if nodes:
            return len(nodes)
    return None


def from_boamp(record: dict[str, Any]) -> Opportunity:
    """Map one BOAMP record onto the unified schema.

    Two levels: the record's own columns carry the administrative shell, and
    `donnees` carries the notice. Everything that can be read from the columns
    is, because they are the same for all three notice shapes the dataset holds.
    """
    from .sources import boamp

    native_id = record.get("idweb") or record.get("id")
    if not native_id:
        raise ValueError("notice has no identifier")

    body = boamp.notice_body(record)
    perimetre = str(record.get("perimetre") or "")
    nature = str(record.get("nature") or "")
    amount, currency = _fr_value(body)
    zone = _fr_zone(record, body)
    deadline = (_fr_eforms_deadline(body, zone)
                or _fr_national_deadline(record, body, zone)
                or parse_iso_datetime(record.get("datelimitereponse"),
                                      default_tz=ZoneInfo(_FR_TZ))
                or _fr_legacy_deadline(body, zone))
    status = _fr_status(record, deadline is not None)
    if status == "open" and deadline is None and _fr_diffusion_over(record):
        # A call that states no deadline and is no longer published (25-122054, 26-33404
        # were served open): not something a supplier can act on.
        status = "unknown"

    return Opportunity(
        source_code=boamp.SOURCE_CODE,
        native_id=str(native_id),
        buyer_name_raw=str(record.get("nomacheteur") or "").strip() or "UNKNOWN",
        title_original=str(record.get("objet") or "").strip(),
        country="FR",
        original_language="FR",
        procedure_type=(record.get("procedure_libelle") or record.get("nature_libelle")),
        legal_basis=_fr_legal_basis(perimetre, body),
        value_amount=amount,
        value_currency=currency,
        published_at=_parse_date(record.get("dateparution")),
        deadline_at=deadline,
        cpv_codes=_fr_cpv(body),
        source_url=boamp.notice_url(record),
        status=status,
        status_native=f"{perimetre}/{nature}" if perimetre or nature else None,
        related_native_id=_fr_corrected_notice(record, body, str(native_id)),
        procedure_identifier=_fr_procedure_id(record),
        lot_count=_fr_lot_count(body),
        description=_fr_description(body),
    )


def _aid_rules(text: str, day: str | None) -> dict[str, Any]:
    """`rules_read` (and the page's date as `rules_read_at`) for conditions_raw, or nothing when the page states none of them."""
    from .rule_readings import read_aid_page

    read = read_aid_page(text)
    return {"rules_read": read, "rules_read_at": f"{day[:10]}T00:00:00+00:00" if day else None} if read else {}


def from_aid(record: dict[str, Any], *, today: date | None = None) -> Call:
    """Map one page of the Agence de l'innovation de defense to a Call.

    The identity is the page's slug and not its path, because a call moves from the
    "en cours" list to the "clotures" one and its path moves with it. Every call the
    agency publishes is a defence call, so the regime needs no signal.
    """
    from .sources import aid

    slug = record.get("slug")
    title = " ".join(str(record.get("title") or "").split())
    if not slug:
        raise ValueError("page has no slug")
    if not title:
        raise ValueError(f"page {slug} has no title")
    published = date.fromisoformat(record["published"]) if record.get("published") else None
    text = record.get("text") or ""
    ends = aid.deadlines(text, published)
    now = (datetime.combine(today, datetime.min.time(), tzinfo=timezone.utc)
           if today else None)

    return Call(
        programme_code="FR-AID",
        native_id=str(slug),
        title=title[:500],
        opens_at=aid.opening(text),
        published_at=published,
        deadline_at=ends[-1] if ends else None,
        deadline_precision="date" if ends and aid.is_end_of_day(ends[-1]) else None,
        conditions_raw={
            "list": record.get("list"),
            "summary": record.get("summary"),
            "published": record.get("published"),
            "modified": record.get("modified"),
            "deadlines": [d.isoformat() for d in ends],
            "max_aid_eur_per_project": aid.max_aid_eur(text),
            # WP-93: rules the page states in fixed words (RAPID's group staff count, the Cyber Defense Factory's staff nationality)
            **_aid_rules(text, record.get("modified") or record.get("published")),
        },
        status=aid.status(record, now=now),
        # WP-109 (p05): RAPID is the agency's scheme for dual innovation ("Régime d'APpui à l'Innovation Duale"), its own word
        regime=aid.regime_of(str(slug), title),
        source_url=record.get("url"),
        type_of_action=aid.kind_of(title),
        country="FR",
        issuer=aid.ISSUER,
    )


def from_matine(record: dict[str, Any], *, today: date | None = None) -> Call:
    """Map one MATINE yearly call page to a Call.

    The page named `maararahahaku-2027` is the call that closes in June 2026 and funds
    2027; its title says which. Facts only: the deadline, the stated total, the decision
    date, and a link. The Finnish text is not served.
    """
    from .sources import matine

    slug = record.get("slug")
    year = record.get("year")
    if not slug or not year:
        raise ValueError("page has no slug or year")
    text = record.get("text") or ""
    amount = matine.total_budget(text)
    projects = matine.project_range(text)
    decided = matine.decision_date(text)
    now = (datetime.combine(today, datetime.min.time(), tzinfo=timezone.utc)
           if today else None)

    return Call(
        programme_code="FI-MATINE",
        native_id=str(slug),
        title=f"MATINE määrärahahaku {year} (research funding call)",
        topic_code=f"MATINE-{year}",
        budget=amount,
        budget_scope="call" if amount is not None else None,
        currency="EUR" if amount is not None else None,
        deadline_at=matine.deadline(text),
        conditions_raw={
            "funding_year": int(year),
            "projects": list(projects) if projects else None,
            "decision_date": decided.isoformat() if decided else None,
            "page_title": record.get("title"),
        },
        status=matine.status(record, now=now),
        regime="defence",
        source_url=record.get("url"),
        type_of_action="research grant",
        country="FI",
        issuer="Puolustusministeriö (MATINE)",
    )


def from_vinnova(record: dict[str, Any], *, today: date | None = None) -> Call:
    """Map one Vinnova application round to a Call.

    The round is the unit because it carries the dates; its call and programme are
    named in the payload. The title is the agency's English one where it wrote one.
    """
    from .sources import vinnova

    native_id = record.get("Diarienummer")
    if not native_id:
        raise ValueError("round has no diarienummer")
    if not record.get("Titel"):
        raise ValueError(f"round {native_id} has no title")
    chosen = vinnova.regime(record)
    if chosen is None:
        raise ValueError(f"round {native_id} is not in a defence programme")
    text = vinnova.eligibility_text(record)
    # Read from the Swedish original: the English text is a translation, and the pattern
    # is the agency's Swedish wording ("totala budgeten for utlysningen ar ...").
    amount = vinnova.parse_total_budget(" ".join(t["sv"] for t in vinnova.web_texts(record)))
    now = (datetime.combine(today, datetime.min.time(), tzinfo=timezone.utc)
           if today else None)

    return Call(
        programme_code="SE-VINNOVA",
        native_id=str(native_id),
        title=vinnova.title(record)[:500],
        topic_code=str(native_id),
        call_identifier=(record.get("utlysning") or {}).get("Diarienummer"),
        budget=amount,
        budget_scope="call" if amount is not None else None,
        currency="SEK" if amount is not None else None,
        opens_at=vinnova.opens_at(record),
        deadline_at=vinnova.deadline(record),
        eligibility_text=text or None,
        conditions_raw=vinnova.conditions(record),
        status=vinnova.status(record, now=now),
        regime=chosen,
        source_url=vinnova.apply_url(record),
        country="SE",
        issuer="Vinnova",
    )


# -------------------------------------------------------- TenderNed mapping

_NL_TZ = "Europe/Amsterdam"

# The publication type decides the lifecycle. Checked on 12 October 2026 against
# the 22,092 publications landed so far (these seven types are all there are)
# and their `detail.formType`:
#
# - VAK is a prior-information notice (forms EF04-EF08, EFE2) or one used as a
#   call for competition (EF10-EF14). Neither is a tender that can be answered:
#   `forthcoming`. Mapped `open` they were 62 of the 107 effective-open Dutch
#   rows (finding F13).
# - MAC is a voluntary preliminary market consultation (EFE1). It carries no
#   `sluitingsDatum` (0 of 1,326), only a consultation date, and is not a
#   procedure yet: `forthcoming`.
# - REC rectifies a notice of any family and inherits that notice's formType, so
#   an award correction (EF29, EF30) is not an open tender. The formType decides
#   (_NL_RECTIFIED_STATUS); without it (no detail page) the lifecycle is
#   `unknown`, never `open`.
# - AGO is an award notice (a voluntary ex-ante transparency notice, formType
#   `dir-awa-pre`, is an award too), AAW a contract modification, VBE an early
#   termination.
_NL_STATUS = {
    "AAO": "open", "VAK": "forthcoming", "MAC": "forthcoming",
    "AGO": "awarded", "AAW": "awarded",
    "VBE": "cancelled",
}

# `detail.formType` of a rectification, to the lifecycle of the notice it corrects.
_NL_RECTIFIED_STATUS = {
    "competition": "open", "planning": "forthcoming", "consultation": "forthcoming",
    "result": "awarded", "dir-awa-pre": "awarded", "cont-modif": "awarded",
}

# The directive a Dutch form is written for, by the words of its description:
# "Aankondiging van een opdracht - algemene richtlijn, standaardregeling".
_NL_DIRECTIVES = (
    ("algemene richtlijn", "32014L0024"),
    ("sectorale richtlijn", "32014L0025"),
    ("concessierichtlijn", "32014L0023"),
)


def _nl_legal_basis(framework: Any, form_text: str, european: bool) -> str | None:
    """The CELEX act a publication stands on, when the source states it unambiguously.

    `juridischKaderCode` names a Dutch instrument, not a directive. DEF, the
    defence and security act, is Directive 2009/81/EC. NAW, the Aanbestedingswet
    2012, carries the general, utilities and concessions directives *and* the
    national below-threshold regime, so on its own it says nothing; with a form
    written for one directive and a European (not national-only) publication it
    does. ARW2012 (the works regulation) and AND2012 ("Anders") name no directive
    and stay empty, as does every national-only publication. Measured on 22,092
    publications: NAW 19,175, ARW2012 2,325, AND2012 429, DEF 162.
    """
    text = form_text.lower()
    if "defensierichtlijn" in text or framework == "DEF":
        return "32009L0081"
    if framework == "NAW" and european:
        for words, celex in _NL_DIRECTIVES:
            if words in text:
                return celex
    return None


def _nl_cpv(detail: dict[str, Any]) -> list[str]:
    """The detail's CPV codes, the one it flags as the main object (`isHoofdOpdracht`) first (WP-113: the first
    listed was taken as the main code, wrong on 150 of 481 publications, 422883: 34900000 for 42400000)."""
    codes: list[str] = []
    listed = detail.get("cpvCodes")
    listed = sorted(listed, key=lambda e: not (isinstance(e, dict) and e.get("isHoofdOpdracht") is True))         if isinstance(listed, list) else []
    for entry in listed:
        code = str(entry.get("code") if isinstance(entry, dict) else entry or "")[:8]
        if code.isdigit() and code not in codes:
            codes.append(code)
    return codes


def from_tenderned(record: dict[str, Any]) -> Opportunity:
    """Map one TenderNed publication, list row plus its `detail`, onto the schema.

    The directive is read from the form (`publicatiecode`: "defensierichtlijn")
    and from the detail's legal framework (`DEF`), whichever is present, and for
    the other directives from the framework and the form together
    (`_nl_legal_basis`). Value is left empty: neither level carries one, and the
    description's "circa EUR ..." is prose, not a field. The lifecycle follows
    the publication type, and a rectification's follows what it corrects.
    """
    from .sources import tenderned

    native_id = record.get("publicatieId")
    if not native_id:
        raise ValueError("publication has no identifier")
    def _dict(value: Any) -> dict[str, Any]:
        return value if isinstance(value, dict) else {}

    detail = _dict(record.get("detail"))
    form = _dict(record.get("publicatiecode"))
    kind = _dict(record.get("typePublicatie")).get("code") or ""
    framework = _dict(detail.get("juridischKaderCode")).get("code")
    european = (_dict(detail.get("nationaalOfEuropeesCode")).get("code") == "EU"
                or record.get("europees") is True)
    legal_basis = _nl_legal_basis(framework, str(form.get("omschrijving") or ""), european)
    status = _NL_STATUS.get(kind, "unknown")
    if kind == "REC":
        status = _NL_RECTIFIED_STATUS.get(detail.get("formType"), "unknown")
    description =record.get("opdrachtBeschrijving") or detail.get("opdrachtBeschrijving")

    return Opportunity(
        source_code=tenderned.SOURCE_CODE,
        native_id=str(native_id),
        buyer_name_raw=str(record.get("opdrachtgeverNaam") or "").strip() or "UNKNOWN",
        title_original=str(record.get("aanbestedingNaam") or "").strip(),
        country="NL",
        original_language="NL",
        procedure_type=_dict(record.get("procedure")).get("omschrijving"),
        legal_basis=legal_basis,
        published_at=_parse_date(record.get("publicatieDatum")),
        # WP-113: the detail carries the deadline as the latest rectification set it; the list row keeps the first
        # one (428231: rectified to 16 Nov, served closed on 19 Aug)
        deadline_at=parse_iso_datetime(detail.get("sluitingsDatum") or record.get("sluitingsDatum"),
                                       default_tz=ZoneInfo(_NL_TZ)),
        cpv_codes=_nl_cpv(detail),
        source_url=tenderned.notice_url(record),
        status=status,
        status_native=f"{kind}/{form.get('code')}" if kind or form.get("code") else None,
        ted_ref=canonical_ted_ref(detail.get("pbNummerTed")),
        description=str(description).strip() if description else None,
    )


# ----------------------------------------------- German BKMS mapping (eForms)

_DE_TZ = "Europe/Berlin"


def from_de_bkms(record: dict[str, Any]) -> Opportunity:
    """Map one BKMS notice file onto the unified schema, through the TED mapper.

    The XML is read into TED's own field names (`sources.de_bkms.ted_fields`) and
    `from_ted` does the rest, so status, value and deadline rules are the same as for
    the TED notice this one is the twin of. What is the BKMS's own: the identity (the
    notice id, without the version, so an amendment is a version), the TED number where
    the file states one, and the absence of a page URL (none is verified).
    """
    from .sources import de_bkms

    xml = record.get("xml")
    if not isinstance(xml, str) or not xml:
        raise ValueError(f"notice file {record.get('file')!r} unreadable: "
                         f"{record.get('unreadable') or 'no document'}")
    try:
        fields = de_bkms.ted_fields(xml)
    except Exception as exc:    # ParseError and the like: one file is not the run
        raise ValueError(f"notice file {record.get('file')!r} is not a notice: {exc}") from exc
    native_id = fields.pop("_notice_id") or record.get("notice_id")
    if not native_id:
        raise ValueError("notice has no identifier")
    fields["notice-identifier"] = native_id
    if not fields.get("notice-version") and record.get("version"):
        fields["notice-version"] = record["version"]
    tz = ZoneInfo(_DE_TZ)
    stamps = [_parse_datetime(d, t, default_tz=tz) for d, t in fields.pop("_deadlines", [])]
    fields["deadline-receipt-request"] = [s.isoformat() for s in stamps if s is not None]
    ted_ref = canonical_ted_ref(fields.pop("_ted_ref", None))
    fields.pop("_folder_id", None)
    fields.pop("_lots", None)
    documents_url = fields.pop("_documents_url", None)

    opp = from_ted(fields)
    opp.source_code = de_bkms.SOURCE_CODE
    opp.native_id = str(native_id)
    # WP-113: the notice's own page on oeffentlichevergabe.de (built from its eForms notice id) is the original; BT-15
    # is the buyer's platform, where the documents are, and was the link until now: 7,634 notices opened a platform
    # page and 115 a bare home page (https://www.meinauftrag.rib.de) that does not lead to the notice. BT-15 is kept
    # as the documents link unless it is such a home page; it is the only link of a notice without an eForms id.
    documents = http_url(documents_url)
    if documents and urlsplit(documents).path.strip("/") == "" and not urlsplit(documents).query:
        documents = None
    opp.documents_url = documents
    opp.source_url = de_bkms.notice_page(str(native_id)) or documents
    opp.country = opp.country or "DE"
    opp.original_language = opp.original_language or "DE"
    opp.ted_ref = ted_ref
    return opp


# --------------------------------------------------- e-Zamowienia mapping

_PL_TZ = "Europe/Warsaw"

# Which BZP notice types carry the defence and security directive. Poland
# transposes Directive 2009/81/EC in the PZP, and these notice types exist to
# publish under it, so the classifier's legal-basis signal is the right home
# for them: the CELEX reference is recorded, and the native type is kept in
# procedure_type so nothing is lost in the translation.
_PL_DEFENCE_NOTICE_TYPES = {
    "PriorInformationNoticeForContractsInTheFieldOfDefenceAndSecurityEU",
    "ContractNoticeForContractsInTheFieldOfDefenceAndSecurityEU",
    "ContractAwardNoticeForContractsInTheFieldOfDefenceAndSecurityEU",
}


def _pl_cpv(raw: Any) -> list[str]:
    """Pull codes out of `45453000-7 (Roboty...),45110000-1 (Roboty...)`.

    The field is one string mixing codes, check digits and Polish labels, and
    it repeats codes. `_clean_cpv` already deduplicates and takes eight digits.
    """
    return _clean_cpv(raw)



# Atlas Przetargow rows that are award or performance notices rather than live
# calls. Taken from the values actually present in the 2024 file, counted:
# ContractPerformingNotice 224,209, TenderResultNotice 135,885,
# ContractNotice 129,547, NoticeUpdateNotice 63,387, cn-standard 50,780,
# can-standard 36,764. The `*-standard` forms are the eForms names on rows that
# came from TED; the CamelCase ones are the BZP bulletin's own.
_ATLAS_CLOSED_TYPES = {
    "TenderResultNotice", "ContractPerformingNotice", "can-standard", "can-social", "can-desg",
    "can-modif", "can-tran", "veat", "compl", "AgreementUpdateNotice", "AgreementIntentionNotice",
    "NoticeOfIntentionToConcludeAContract",
}
_ATLAS_OPEN_TYPES = {
    "ContractNotice", "cn-standard", "cn-social", "cn-desg", "SmallContractNotice",
    "CompetitionNotice", "qu-sy", "subco",
}
# Prior information and plan notices announce a purchase; they are not calls.
_ATLAS_PLANNED_TYPES = {
    "pin-standard", "pin-only", "pin-buyer", "pin-rtl", "pin-tran", "pin-cfc-standard",
    "pin-cfc-social", "pmc", "PriorInformationNotice", "TenderPlanNotice",
}


def _atlas_status(notice_type: str | None, procedure_result: Any = None,
                  has_deadline: bool = False) -> str:
    """Live call, a record of one already decided, a planning notice, or unknown.

    Since 12 October 2026 an unrecognised type is `unknown`, never `open`: the
    notices of 2025 left open by the old rule (NoticeUpdateNotice, agreement
    updates, intentions, VEAT) were the ones a reader met as "open, no deadline".
    A `NoticeUpdateNotice` restates a notice that is listed itself, so it is not
    a second opportunity.

    The bulletin's own table decides first (`ezamowienia.map_status`, the one the
    board's records go through), so a type reads the same wherever it arrives: the
    defence-and-security forms, `ContractAwardNotice`, and a prior-information notice
    used as a call (`pin-cfc-*`: open with a deadline, forthcoming without). The sets
    below only add the types the dataset alone carries.

    A result notice whose parts were all annulled (`uniewaznienie`) is
    `cancelled`, not awarded.
    """
    from .sources.ezamowienia import map_status, result_status

    status = map_status(notice_type, has_deadline=has_deadline)
    if status == "unknown":
        if notice_type in _ATLAS_CLOSED_TYPES:
            status = "awarded"
        elif notice_type in _ATLAS_PLANNED_TYPES:
            status = "forthcoming"
        elif notice_type in _ATLAS_OPEN_TYPES:
            status = "open"
    if status == "awarded":
        return result_status(procedure_result) or "awarded"
    return status


# ISO 4217 codes accepted for an Atlas value. An allowlist rather than a shape
# test, because the shape test does not work here: counted over the 2024 file,
# the currency column holds 488,791 PLN, 72 SEK and 5 EUR against 181,062 nulls
# and a tail of three-letter strings that are not currencies at all -- 'pkt'
# (punkty), 'net', 'bru', 'ton', 'ppm', 'MPa', 'mil'. They are the first three
# characters of some free-text unit field, and every one of them is alphabetic
# and three letters long, so anything checking the shape lets them all through.
_ISO_4217 = {
    "PLN", "EUR", "USD", "GBP", "CHF", "SEK", "NOK", "DKK",
    "CZK", "HUF", "RON", "BGN", "UAH", "JPY", "CAD", "AUD",
}


def _atlas_value(amount: Any, currency: Any) -> tuple[float | None, str | None]:
    """A value only when the currency says what it is denominated in.

    A number whose currency is 'net' is not a value, it is a parsing accident,
    and carrying it would put a wrong figure in front of someone deciding
    whether to bid. Dropping the pair is the only honest option: the amount on
    its own is meaningless.
    """
    if amount is None:
        return None, None
    code = str(currency or "").strip().upper()
    if code not in _ISO_4217:
        return None, None
    try:
        value = float(amount)
    except (TypeError, ValueError):
        return None, None
    if value <= 0:
        return None, None
    return value, code


def from_atlas_pl(record: dict[str, Any]) -> Opportunity:
    """Map one Atlas Przetargow row onto the unified schema.

    Two of the four defence signals cannot fire here. The dataset carries no
    legal basis and no security-clearance text, so `legal_basis` stays None
    rather than being guessed from the notice type: a guess would set the
    strongest signal we have on the flimsiest evidence we have.
    """
    g = record.get

    native_id = _first(g("id"))
    if not native_id:
        raise ValueError("Atlas row has no id")

    # Prefer the bulletin's own numbering for the URL, and fall back to the
    # column the dataset built for exactly this.
    url = _first(g("notice_url")) or None

    # The dataset writes the deadline as `2025-07-18 07:30:00`, and the two halves of it
    # mean different things. A BZP row's is UTC: the bulletin shows 09:30 Warsaw for it, and
    # read as Warsaw it was one hour (winter) or two (summer) early on 4 of 4 rows compared.
    # A row republished from TED (`TED-628674-2024`) states Warsaw wall time, which the TED
    # twin confirms on 22 of 22 and again on 4 of 4 read as `09:00:00` for 07:00 UTC.
    from_ted_notice = (str(_first(g("source")) or "").strip().lower() == "ted"
                       or str(native_id).startswith("TED-"))
    deadline = parse_iso_datetime(
        g("submitting_offers_date"),
        default_tz=ZoneInfo(_PL_TZ) if from_ted_notice else timezone.utc)
    value, currency = _atlas_value(g("estimated_value"), g("currency"))
    notice_type = _first(g("notice_type"))

    return Opportunity(
        source_code="pl_atlas",
        native_id=str(native_id),
        buyer_name_raw=str(_first(g("buyer")) or "").strip() or "UNKNOWN",
        title_original=str(_first(g("title")) or "").strip(),
        country=_country2(g("organization_country")) or "PL",
        original_language="PL",
        # The procedure (`tender_type`, a BZP code), not the notice type. Null on
        # every TED row of the dataset (98,114 in 2024): those are shown with the
        # TED twin's procedure through `ted_ref`, never copied here.
        procedure_type=_procedure_label(g("tender_type")),
        legal_basis=None,
        value_amount=value,
        value_currency=currency,
        published_at=_parse_date(g("date")),
        deadline_at=deadline,
        cpv_codes=_clean_cpv(g("cpv_code")),
        source_url=url,
        status=_atlas_status(notice_type, _first(g("procedure_result")),
                             has_deadline=deadline is not None),
        status_native=notice_type,
        ted_ref=canonical_ted_ref(g("ted_number")) or ted_ref_from_url(url),
    )


def from_ezamowienia(record: dict[str, Any]) -> Opportunity:
    """Map one BZP board record onto the unified schema."""
    g = record.get

    # bzpNumber ("2026/BZP 00426594") identifies the procurement; noticeNumber
    # appends a version ("/01"). Keying on the former is what lets a re-issued
    # notice become a new version of the same opportunity rather than a
    # duplicate row.
    native_id = _first(g("bzpNumber")) or _first(g("noticeNumber")) or _first(g("objectId"))
    if not native_id:
        raise ValueError("notice has no identifier")

    version = None
    notice_number = str(_first(g("noticeNumber")) or "")
    if "/" in notice_number:
        parts = [p.strip() for p in notice_number.split("/")]
        # A plan notice is numbered `<plan>/<revision>/P`: the revision is the
        # one before the letter.
        tail = parts[-2] if parts[-1].upper() == "P" and len(parts) >= 3 else parts[-1]
        if tail.isdigit():
            version = int(tail)

    # A record republished from TED has `noticeType = null` and names its TED
    # form in `noticeTypeTed`; both are kept, the BZP one first.
    notice_type = _first(g("noticeType"))
    native_type = notice_type or _first(g("noticeTypeTed"))
    from .sources.ezamowienia import NOTICE_URL

    object_id = _first(g("objectId")) or _first(g("moIdentifier"))
    url = NOTICE_URL.format(object_id=object_id) if object_id else None

    deadline = parse_iso_datetime(g("submittingOffersDate"), default_tz=ZoneInfo(_PL_TZ))

    buyer = str(_first(g("organizationName")) or "").strip() or "UNKNOWN"
    title = str(_first(g("orderObject")) or "").strip()
    title_en = None
    if not title and notice_type == "TenderPlanNotice":
        # The listing of a plan notice names no subject and no CPV (35 of 35
        # checked on 12 October 2026); the plan itself is a separate document.
        # A clearly labelled line rather than an empty title: it says what the
        # notice is and who published it, and claims nothing else.
        title = title_en = f"Procurement plan notice (planned purchases, subject not stated): {buyer}"

    return Opportunity(
        source_code="pl_ezam",
        native_id=str(native_id),
        buyer_name_raw=buyer,
        title_original=title,
        title_en=title_en,
        country=_country2(g("organizationCountry")) or "PL",
        original_language="PL",
        # The procedure, not the notice type: `tenderType` is the procedure
        # (see sources/ezamowienia.procedure_label). The notice type is kept in
        # status_native.
        procedure_type=_procedure_label(g("tenderType")),
        legal_basis=("32009L0081" if notice_type in _PL_DEFENCE_NOTICE_TYPES else None),
        # The board listing carries no contract value. It is on the notice
        # document, which is a separate fetch, so the field stays honestly empty
        # rather than being guessed at.
        value_amount=None,
        value_currency=None,
        published_at=_parse_date(g("publicationDate")),
        deadline_at=deadline,
        cpv_codes=_pl_cpv(g("cpvCode")),
        source_url=url,
        notice_version=version,
        status=_pl_status({"noticeType": notice_type,
                           "noticeTypeTed": _first(g("noticeTypeTed")),
                           "procedureResult": _first(g("procedureResult")),
                           "hasDeadline": deadline is not None}),
        status_native=native_type,
        ted_ref=ted_ref_from_url(g("pdfUrl")) or _ted_ref_from_oj_number(notice_number),
    )


_OJ_NUMBER = re.compile(r"^(20[12]\d)/S \d{1,3}-(\d{1,8})$")


def _ted_ref_from_oj_number(value: str) -> str | None:
    """`2026/S 173-618851` (how the bulletin numbers a notice it republished from
    TED: year, OJ S issue, publication number) is TED notice `618851-2026`.
    The link is also in `pdfUrl`; this covers a record that lacks it."""
    m = _OJ_NUMBER.match(value.strip())
    return canonical_ted_ref(f"{m.group(2)}-{m.group(1)}") if m else None


def _pl_status(record: dict[str, Any]) -> str:
    from .sources.ezamowienia import record_status

    return record_status(record)


def _procedure_label(tender_type: Any) -> str | None:
    from .sources.ezamowienia import procedure_label

    return procedure_label(tender_type)


# ------------------------------------------------------- grants: EU portal

@dataclass
class Call:
    """A call for proposals, or one topic inside one. Mirrors the `call` table.

    Separate from `Opportunity` and not a variant of it, because what a supplier
    needs to know is different: not who is buying and for how much, but what the
    consortium has to look like, when the stage closes, and which regulation
    decides eligibility. Nothing here is a buyer, and a grant has no award.
    """

    programme_code: str
    native_id: str
    title: str
    topic_code: str | None = None
    call_identifier: str | None = None
    budget: float | None = None
    opens_at: date | None = None
    # The source's own date for the call, where it states one: the day BDNS received
    # it. Served so a reader can see how current the register's record is.
    published_at: date | None = None
    deadline_at: datetime | None = None
    min_consortium_size: int | None = None
    min_member_states: int | None = None
    eligibility_text: str | None = None
    eligibility_parsed: dict[str, Any] | None = None
    conditions_raw: dict[str, Any] | None = None
    status: str | None = None
    regime: str = "defence"
    source_url: str | None = None
    type_of_action: str | None = None
    cpv_codes: list[str] = field(default_factory=list)
    # National sources: whose money this is. An EU programme has neither -- the
    # call is open to every member state -- and leaves both None.
    country: str | None = None
    issuer: str | None = None
    # Whose budget `budget` is: `call` when it is the pot the call competes for.
    # None from a source that does not say; the EU topic page sets it later.
    budget_scope: str | None = None
    # ISO 4217 of `budget`. EU programme budgets and the Spanish register are in
    # euro; Polish competitions state theirs in zloty or euro, and a sum without its
    # currency is not a sum.
    currency: str | None = None
    # `date` when the source states the closing day and no time. The deadline is then
    # the end of that day in the source's own time zone, and the site prints the date
    # only; a time the source never stated is not claimed. None: a time was stated.
    deadline_precision: str | None = None

    def __post_init__(self) -> None:
        self.source_url = http_url(self.source_url)


# The portal's status vocabulary, mapped to the one the `call` table declares.
_CALL_STATUS = {
    "Open": "open",
    "Forthcoming": "forthcoming",
    "Closed": "closed",
    "Evaluated": "evaluated",
}


def from_eu_call(record: dict[str, Any]) -> Call:
    """Map one reference-data topic to a Call.

    The numeric `ccm2Id` is the identity, not the topic code: the code is a
    human label that a correction can change, and it is the key the archive
    would then split a call across. The code is kept as a column because it is
    what an applicant quotes and what the portal's own URL is built from.
    """
    from .sources import eu_portal as portal

    native_id = record.get("ccm2Id")
    if native_id in (None, ""):
        raise ValueError("call has no ccm2Id")
    programme = portal.programme_code(record)
    if not programme:
        raise ValueError(f"call {native_id} names no framework programme")
    title = (record.get("title") or "").strip()
    if not title:
        raise ValueError(f"call {native_id} has no title")

    actions = record.get("actions") or []
    type_of_action = None
    for action in actions:
        for kind in action.get("types") or []:
            type_of_action = kind.get("typeOfAction")
            if type_of_action:
                break
        if type_of_action:
            break

    return Call(
        programme_code=programme,
        native_id=str(native_id),
        title=title,
        topic_code=record.get("identifier"),
        call_identifier=record.get("callIdentifier"),
        opens_at=portal.opens_at(record),
        published_at=portal.published_at(record),
        deadline_at=portal.closing(record),
        deadline_precision="date" if portal.closing_is_date(record) else None,
        status=_CALL_STATUS.get(portal.status_name(record) or ""),
        regime=portal.regime(record) or "defence",
        source_url=portal.topic_url(record),
        type_of_action=type_of_action,
        cpv_codes=[str(c) for c in (record.get("additionalCpvs") or []) if c],
    )


# ------------------------------------------------------ grants: Spain (BDNS)

def from_bdns(detail: dict[str, Any], *, today: date | None = None) -> Call:
    """Map one BDNS call, in its detail form, to a Call.

    A Spanish call title is a legal citation -- "Resolucion de 11 de junio de 2026
    de la Direccion General del CDTI, por la que se aprueba..." -- so the title is
    that, whole: the register's notice forbids distorting the sense of the
    information, and a citation cut in the middle says something else. The issuing
    body is carried separately, because it is the first thing anybody asks about a
    call that names no programme.
    """
    from .sources import bdns

    number = detail.get("codigoBDNS") or detail.get("numeroConvocatoria")
    if not number:
        raise ValueError("call has no BDNS code")
    title = " ".join((detail.get("descripcion") or "").split())
    if not title:
        raise ValueError(f"call {number} has no description")
    organ = detail.get("organo") or {}
    budget = detail.get("presupuestoTotal")

    return Call(
        programme_code="ES-BDNS",
        native_id=str(number),
        title=title,
        topic_code=str(number),
        budget=float(budget) if budget not in (None, "") else None,
        budget_scope="call" if budget not in (None, "") else None,
        currency="EUR" if budget not in (None, "") else None,
        opens_at=bdns.opens_at(detail),
        published_at=bdns.received_at(detail),
        deadline_at=bdns.deadline(detail),
        deadline_precision="date" if bdns.deadline(detail) else None,
        eligibility_text=bdns.eligibility_text(detail) or None,
        conditions_raw=bdns.conditions(detail),
        status=bdns.status(detail, today=today),
        regime=bdns.regime(detail),
        source_url=bdns.call_url(number),
        type_of_action=detail.get("tipoConvocatoria"),
        country="ES",
        issuer=" / ".join(p for p in (organ.get("nivel2"), organ.get("nivel3")) if p) or None,
    )


# ------------------------------------------------------- grants: Poland (NCBR)

def from_ncbr(record: dict[str, Any], *, today: date | None = None) -> Call:
    """Map one NCBR competition to a Call.

    The identity is the page path, because the API carries no numeric id. A competition
    renamed upstream would therefore appear as a new one, which is noted in the source
    documentation and has not happened in the 364 seen.
    """
    from .sources import ncbr

    path = record.get("path")
    name = " ".join(str(record.get("name") or "").split())
    if not path:
        raise ValueError("competition has no path")
    if not name:
        raise ValueError(f"competition {path} has no name")
    amount, currency = ncbr.parse_budget(record.get("budget"))
    chosen = ncbr.regime(record)
    if chosen is None:
        raise ValueError(f"competition {path} carries no defence tag")

    return Call(
        programme_code="PL-NCBR",
        native_id=path,
        title=name[:500],
        # The register carries no code of its own: the name is a title, and the
        # reference some titles begin with is not a field. Null rather than the name.
        topic_code=None,
        budget=amount,
        budget_scope="call" if amount is not None else None,
        currency=currency,
        opens_at=ncbr.opens_at(record),
        published_at=ncbr.published_at(record),
        deadline_at=ncbr.deadline(record),
        deadline_precision="date" if ncbr.deadline_is_date(record) else None,
        eligibility_text=ncbr.eligibility_text(record) or None,
        conditions_raw=ncbr.conditions(record),
        status=ncbr.status(record, now=datetime.combine(today, datetime.min.time(), tzinfo=timezone.utc)
                           if today else None),
        regime=chosen,
        source_url=ncbr.call_url(record),
        type_of_action=", ".join(ncbr.programme_types(record)) or None,
        country="PL",
        issuer="Narodowe Centrum Badan i Rozwoju (NCBR)",
    )
