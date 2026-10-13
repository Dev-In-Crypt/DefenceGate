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
        return s
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


def normalise_org_name(raw: str, *, strip_noise: bool = False, fold_state: bool = False) -> str:
    """Canonical form for entity resolution.

    Fold accents (by decomposition, then by explicit transliteration for letters
    such as Polish ł that do not decompose), lowercase, strip legal form,
    collapse punctuation. Legal form
    is removed rather than kept because the same company appears with and
    without it across sources, and that difference alone should never create a
    duplicate organisation.
    """
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
            or _ID_UUID.search(text)):
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
    return s


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


def _ted_value(g, notice_type: str | None, lots: int | None
               ) -> tuple[float | None, str | None, str | None]:
    """(amount, currency, kind): which of TED's several values is the notice's.

    `kind` records the choice, so a figure can be told from an approximation:
      total      TED's own notice total (`total-value`; for a result notice the
                 awarded value, `result-value-notice` failing that)
      estimated  the procedure's estimated value
      lot_sum    every lot has a value, all in one currency: their sum
      first_lot  none of the above, so the first lot's value, which may be one of
                 several and is flagged as such rather than shown as the total
    """
    def pair(amount: str, currency: str) -> tuple[float | None, str | None]:
        got = _parse_amount(g(amount))
        cur = _first(g(currency))
        return got, (str(cur) if cur else None)

    if notice_type in TED_RESULT_TYPES:
        for amount, cur in (("total-value", "total-value-cur"),
                            ("result-value-notice", "result-value-cur-notice")):
            got, c = pair(amount, cur)
            if got is not None:
                return got, c, "total"
    got, c = pair("estimated-value-proc", "estimated-value-cur-proc")
    if got is not None:
        return got, c, "estimated"
    # Before the lots: a legacy notice states only this, and it is the figure TED
    # itself calls the notice's total.
    got, c = pair("total-value", "total-value-cur")
    if got is not None:
        return got, c, "total"

    amounts = [a for a in (_parse_amount(v) for v in _each(g("estimated-value-lot")))
               if a is not None]
    if not amounts:
        return None, None, None
    currencies = {str(c).strip().upper() for c in _each(g("estimated-value-cur-lot"))}
    # TED lists each distinct currency once, not one per lot.
    if len(currencies) == 1 and len(amounts) == (lots or len(amounts)):
        return round(sum(amounts), 2), next(iter(currencies)), "lot_sum"
    first_cur = _first(g("estimated-value-cur-lot"))
    return amounts[0], (str(first_cur) if first_cur else None), "first_lot"


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
    body = clean.pop("donnees", None) if "idweb" in clean else None
    clean = _redact_emails(_bound(clean))
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
    scrubbed = _redact_emails(_scrub_contacts(_bound(parsed)))
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
    """A positive, plausible amount from `12500`, `"12 500,50"` or `"12500.00"`.

    Zero is "not stated", not a value: the simplified form writes `0.00` for a
    lot whose estimate the buyer left blank (102 of 102 sampled zeros). Anything
    the NUMERIC(16,2) column could not hold is dropped rather than failing the
    notice.
    """
    if isinstance(raw, bool) or raw is None:
        return None
    text = str(raw).replace("\xa0", "").replace(" ", "")
    if re.fullmatch(r"\d+,\d{1,2}", text):
        text = text.replace(",", ".")
    if not re.fullmatch(r"\d+(\.\d+)?", text):
        return None
    amount = float(text)
    return amount if 0 < amount < 10 ** 14 else None


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
    deadline = parse_iso_datetime(record.get("datelimitereponse"),
                                  default_tz=ZoneInfo(_FR_TZ))

    return Opportunity(
        source_code=boamp.SOURCE_CODE,
        native_id=str(native_id),
        buyer_name_raw=str(record.get("nomacheteur") or "").strip() or "UNKNOWN",
        title_original=str(record.get("objet") or "").strip(),
        country="FR",
        original_language="FR",
        procedure_type=(record.get("procedure_libelle") or record.get("nature_libelle")),
        legal_basis=("32009L0081" if perimetre in _FR_DEFENCE_PERIMETERS else None),
        value_amount=amount,
        value_currency=currency,
        published_at=_parse_date(record.get("dateparution")),
        deadline_at=deadline,
        cpv_codes=_fr_cpv(body),
        source_url=boamp.notice_url(record),
        status=_fr_status(record, deadline is not None),
        status_native=f"{perimetre}/{nature}" if perimetre or nature else None,
        related_native_id=_fr_corrected_notice(record, body, str(native_id)),
        procedure_identifier=_fr_procedure_id(record),
        description=_fr_description(body),
    )


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
        },
        status=aid.status(record, now=now),
        regime="defence",
        source_url=record.get("url"),
        type_of_action=aid.kind_of(title),
        country="FR",
        issuer="Agence de l'innovation de defense (AID)",
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
    codes: list[str] = []
    listed = detail.get("cpvCodes")
    for entry in listed if isinstance(listed, list) else []:
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
        deadline_at=parse_iso_datetime(record.get("sluitingsDatum"),
                                       default_tz=ZoneInfo(_NL_TZ)),
        cpv_codes=_nl_cpv(detail),
        source_url=tenderned.notice_url(record),
        status=status,
        status_native=f"{kind}/{form.get('code')}" if kind or form.get("code") else None,
        ted_ref=canonical_ted_ref(detail.get("pbNummerTed")),
        description=str(description).strip() if description else None,
    )


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

    deadline = parse_iso_datetime(g("submitting_offers_date"),
                                  default_tz=ZoneInfo(_PL_TZ))
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
    object_id = _first(g("objectId")) or _first(g("moIdentifier"))
    url = (f"https://ezamowienia.gov.pl/mp-client/search/list/ogloszenia/{object_id}"
           if object_id else None)

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
