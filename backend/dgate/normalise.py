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

import logging
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone, tzinfo
from typing import Any
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
}


@dataclass
class Opportunity:
    """Unified record. Mirrors the opportunity table in schema.sql."""

    source_code: str
    native_id: str
    buyer_name_raw: str
    title_original: str
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
    # signals, populated by classify.py
    is_defence: bool = False
    sig_legal_basis: bool = False
    sig_cpv: bool = False
    sig_buyer: bool = False
    sig_clearance: bool = False
    security_clearance_required: bool = False
    nda_required: bool = False
    subcontracting_signal: bool = False
    # description kept in memory for enrichment, not persisted verbatim
    description: str | None = None


# --------------------------------------------------------------- helpers

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


def _country2(value: Any) -> str | None:
    raw = _first(value)
    if not raw:
        return None
    s = str(raw).strip().upper()
    if len(s) == 2:
        return s
    iso3 = {
        "ESP": "ES", "DEU": "DE", "FRA": "FR", "NLD": "NL", "POL": "PL",
        "PRT": "PT", "ROU": "RO", "CZE": "CZ", "LTU": "LT", "LVA": "LV",
        "EST": "EE", "ITA": "IT", "BEL": "BE", "SWE": "SE", "DNK": "DK",
        "FIN": "FI", "AUT": "AT", "GRC": "GR", "BGR": "BG", "HRV": "HR",
        "HUN": "HU", "IRL": "IE", "LUX": "LU", "MLT": "MT", "SVK": "SK",
        "SVN": "SI", "CYP": "CY", "NOR": "NO", "UKR": "UA",
    }
    return iso3.get(s, s[:2])


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


def normalise_org_name(raw: str, *, strip_noise: bool = False) -> str:
    """Canonical form for entity resolution.

    Fold accents, lowercase, strip legal form, collapse punctuation. Legal form
    is removed rather than kept because the same company appears with and
    without it across sources, and that difference alone should never create a
    duplicate organisation.
    """
    if not raw:
        return ""
    s = unicodedata.normalize("NFKD", raw)
    s = "".join(c for c in s if not unicodedata.combining(c))
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

    value = _parse_amount(g("estimated-value-lot"))
    currency = _first(g("estimated-value-cur-lot"))
    if value is None:
        value = _parse_amount(g("estimated-value-proc"))
        currency = currency or _first(g("estimated-value-cur-proc"))

    deadline = _parse_datetime(
        g("deadline-receipt-tender-date-lot"),
        g("deadline-receipt-tender-time-lot"),
    ) or _parse_datetime(g("deadline-receipt-request-date-lot"))

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
        country=_country2(g("buyer-country")),
        original_language=_lang2(g("official-language")),
        procedure_type=_first(g("notice-subtype")),
        legal_basis=_first(g("legal-basis")),
        value_amount=value,
        value_currency=(str(currency)[:3].upper() if currency else None),
        published_at=_parse_date(g("dispatch-date")),
        deadline_at=deadline,
        cpv_codes=_clean_cpv(g("classification-cpv")),
        source_url=str(url),
        notice_version=version,
        description=description,
        security_clearance_required=bool(clearance and str(clearance).strip()),
        nda_required=_as_bool(nda),
    )


def strip_personal_data(notice: dict[str, Any]) -> dict[str, Any]:
    """Remove personal-data fields before a payload is persisted or served.

    The raw archive keeps the original for reprocessing and audit, under
    restricted access. Everything downstream of this call is clean.
    """
    return {k: v for k, v in notice.items() if k not in PERSONAL_DATA_FIELDS}


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
    )


def _pl_status(notice_type: str | None) -> str:
    from .sources.ezamowienia import map_status

    return map_status(notice_type)
