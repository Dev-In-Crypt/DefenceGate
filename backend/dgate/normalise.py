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
    # mistake stays diagnosable from the serving row.
    status: str = "open"
    status_native: str | None = None
    # The TED publication number this national notice was forwarded under, when
    # the source states it ("696956-2026", leading zeros stripped). It is a
    # link, not a version-worthy fact: not part of VERSIONED_FIELDS, and left
    # out of the payload while empty so existing content hashes do not move.
    ted_ref: str | None = None
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
    security_clearance_required: bool = False
    nda_required: bool = False
    subcontracting_signal: bool = False
    # The notice's own text. It is persisted: opportunity_payload() serialises the
    # whole dataclass, so every archived version carries it. The API never serves it
    # (api.py whitelists the snapshot), and e-mail addresses in it are redacted.
    description: str | None = None

    def __post_init__(self) -> None:
        self.source_url = http_url(self.source_url)


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


def normalise_org_name(raw: str, *, strip_noise: bool = False) -> str:
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
#   corrigendum                                  open when it states a deadline
TED_RESULT_TYPES = frozenset(
    {"can-standard", "can-social", "can-desg", "can-tran", "can-modif", "veat", "compl"})
TED_STATUS_BY_TYPE: dict[str, str] = {
    **dict.fromkeys(("cn-standard", "cn-social", "cn-desg", "pin-cfc-standard",
                     "pin-cfc-social", "subco", "qu-sy", "corr"), "open"),
    **dict.fromkeys(TED_RESULT_TYPES, "awarded"),
    **dict.fromkeys(("pin-only", "pin-buyer", "pin-rtl", "pin-tran", "pmc"), "forthcoming"),
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

# An awarded notice says so in `nature`: ATTRIBUTION for the award itself,
# ANNULATION for a cancellation. Anything else is the notice of an open
# procedure until its deadline says otherwise.
_FR_STATUS = {
    "ATTRIBUTION": "awarded",
    "RESULTAT": "awarded",
    "ANNULATION": "cancelled",
    "RECTIFICATIF": "open",
    "APPEL_OFFRE": "open",
}


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


def _fr_cpv(body: dict[str, Any]) -> list[str]:
    """CPV codes from either notice shape.

    eForms puts them in `cbc:ItemClassificationCode` as `{"#text": "35700000"}`;
    the simplified French form uses `codeCPV.objetPrincipal.classPrincipale`
    and one per lot. Notices from before 2018 carry none at all, and none is
    what this returns for them -- an empty list, never a guess.
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
    seen: set[str] = set()
    return [c for c in codes if not (c in seen or seen.add(c))]


def _fr_value(body: dict[str, Any]) -> tuple[float | None, str | None]:
    """The estimated contract value, when the notice states one."""
    for value in _fr_walk(body, "EstimatedOverallContractAmount"):
        if isinstance(value, dict):
            text, currency = value.get("#text"), value.get("@currencyID")
        else:
            text, currency = value, None
        try:
            return float(str(text)), (currency or "EUR")
        except (TypeError, ValueError):
            continue
    return None, None


def _fr_description(body: dict[str, Any]) -> str | None:
    for value in _fr_walk(body, "description"):
        if isinstance(value, str) and len(value.strip()) > 10:
            return value.strip()
        if isinstance(value, dict) and isinstance(value.get("#text"), str):
            return value["#text"].strip()
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
        deadline_at=parse_iso_datetime(record.get("datelimitereponse"),
                                       default_tz=ZoneInfo(_FR_TZ)),
        cpv_codes=_fr_cpv(body),
        source_url=boamp.notice_url(record),
        status=_FR_STATUS.get(nature, "open"),
        status_native=f"{perimetre}/{nature}" if perimetre or nature else None,
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
        deadline_at=ends[-1] if ends else None,
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

# The publication type decides the lifecycle. A rectification (REC) and a
# market consultation (MAC) belong to a procedure that is still being run; a
# modification notice (AAW) amends a contract that was already awarded.
_NL_STATUS = {
    "AAO": "open", "VAK": "open", "MAC": "open", "REC": "open",
    "AGO": "awarded", "AAW": "awarded",
    "VBE": "cancelled",
}


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
    and from the detail's legal framework (`DEF`), whichever is present. Value is
    left empty: neither level carries one, and the description's "circa EUR ..."
    is prose, not a field.
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
    defence = "defensierichtlijn" in str(form.get("omschrijving") or "").lower() \
        or framework == "DEF"
    description = record.get("opdrachtBeschrijving") or detail.get("opdrachtBeschrijving")

    return Opportunity(
        source_code=tenderned.SOURCE_CODE,
        native_id=str(native_id),
        buyer_name_raw=str(record.get("opdrachtgeverNaam") or "").strip() or "UNKNOWN",
        title_original=str(record.get("aanbestedingNaam") or "").strip(),
        country="NL",
        original_language="NL",
        procedure_type=_dict(record.get("procedure")).get("omschrijving"),
        legal_basis="32009L0081" if defence else None,
        published_at=_parse_date(record.get("publicatieDatum")),
        deadline_at=parse_iso_datetime(record.get("sluitingsDatum"),
                                       default_tz=ZoneInfo(_NL_TZ)),
        cpv_codes=_nl_cpv(detail),
        source_url=tenderned.notice_url(record),
        status=_NL_STATUS.get(kind, "unknown"),
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
    "TenderResultNotice", "ContractPerformingNotice", "can-standard",
}
_ATLAS_OPEN_TYPES = {
    "ContractNotice", "NoticeUpdateNotice", "cn-standard", "pin-standard",
}


def _atlas_status(notice_type: str | None) -> str:
    """Live call, or a record of one that has already been decided.

    Anything unrecognised is `open`, matching the rest of the pipeline: a
    notice wrongly left open is visible and gets corrected, one wrongly closed
    is invisible and never does.
    """
    if notice_type in _ATLAS_CLOSED_TYPES:
        return "awarded"
    return "open"


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
        procedure_type=notice_type,
        legal_basis=None,
        value_amount=value,
        value_currency=currency,
        published_at=_parse_date(g("date")),
        deadline_at=deadline,
        cpv_codes=_clean_cpv(g("cpv_code")),
        source_url=url,
        status=_atlas_status(notice_type),
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
        tail = notice_number.rsplit("/", 1)[-1].strip()
        if tail.isdigit():
            version = int(tail)

    notice_type = _first(g("noticeType"))
    object_id = _first(g("objectId")) or _first(g("moIdentifier"))
    url = (f"https://ezamowienia.gov.pl/mp-client/search/list/ogloszenia/{object_id}"
           if object_id else None)

    deadline = parse_iso_datetime(g("submittingOffersDate"), default_tz=ZoneInfo(_PL_TZ))

    return Opportunity(
        source_code="pl_ezam",
        native_id=str(native_id),
        buyer_name_raw=str(_first(g("organizationName")) or "").strip() or "UNKNOWN",
        title_original=str(_first(g("orderObject")) or "").strip(),
        country=_country2(g("organizationCountry")) or "PL",
        original_language="PL",
        procedure_type=notice_type,
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
        status=_pl_status(notice_type),
        status_native=notice_type,
        ted_ref=ted_ref_from_url(g("pdfUrl")),
    )


def _pl_status(notice_type: str | None) -> str:
    from .sources.ezamowienia import map_status

    return map_status(notice_type)


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
        deadline_at=portal.deadline(record),
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
        topic_code=name[:200],
        budget=amount,
        budget_scope="call" if amount is not None else None,
        currency=currency,
        opens_at=ncbr.opens_at(record),
        deadline_at=ncbr.deadline(record),
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
