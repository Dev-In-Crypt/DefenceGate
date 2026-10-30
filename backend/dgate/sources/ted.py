"""TED Search API connector.

Endpoint:  POST https://api.ted.europa.eu/v3/notices/search
Auth:      none. The Search API is anonymous for published notices.
Docs:      https://docs.ted.europa.eu/api/latest/search.html
Fields:    https://docs.ted.europa.eu/ODS/latest/reuse/field-list.html
Licence:   Commission Decision 2011/833/EU. Notices freely reusable, including
           commercially. Metadata CC0 1.0.

Retention note: TED keeps notices on the website for ten years, then moves them
to a non-public internal archive. Anything we ingest today outlives the source.

History note: the Search API answers from 2017 onwards. Measured on 16 September
2026, the first week of June returned 9,497 notices in 2017 and 18,769 in 2025,
while the same week of 2015 and 2016 returned nothing at all. So "ten years of
history" is 2017 to now, about seven million notices -- and the 2016 half-year
that is already gone from the API is the answer to why the archive exists.

Personal data note: notices carry contact person names, emails and phone
numbers, and award notices can name natural persons as contractors. Those
fields are dropped in normalise.py and never reach the serving layer.

Field semantics, checked against the live API on 12 October 2026 (the raw payload
holds exactly what is requested, so a field added here reaches only notices
fetched afterwards -- `python -m dgate.ops.repair_ted --refetch` brings the
stored ones in line):

  notice-type              cn-standard, can-standard, pin-only, veat, corr, ...;
                           the same vocabulary for legacy notices
  publication-date         what TED shows; dispatch-date is 1 to 6 days earlier
  deadline-receipt-request the tender deadline, a full datetime with offset, one
                           per lot; set for every contract notice, never for
                           award, ex-ante or prior-information notices.
                           `deadline-date-lot` is BT-13, not a deadline
  total-value              the notice's total; for a result notice the awarded
                           value (`result-value-notice` is the same figure)
  estimated-value-lot      one string per lot that has a value; its currency list
                           is de-duplicated, one entry per distinct currency
  winner-selection-status  per lot, result notices of eForms only: selec-w,
                           clos-nw (closed, no winner), open-nw
  procedure-type           open, restricted, neg-w-call, neg-wo-call, ...;
                           a number on some legacy notices
  procedure-identifier     shared by a procedure's contract notice, corrigenda,
                           re-publications and award notice
  publication-number IN (a b c ...)   a hundred numbers answer in one request
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Iterator

import httpx

from . import USER_AGENT, new_client, request_with_retry

log = logging.getLogger(__name__)

TED_SEARCH_URL = "https://api.ted.europa.eu/v3/notices/search"
PAGE_SIZE = 250          # the API maximum; 500 is rejected outright
MAX_PAGES = 400          # hard stop so a bad query cannot run forever

# Exactly the fields we map in normalise.py. Requesting a narrow set keeps
# responses small and makes schema drift visible immediately.
TED_FIELDS = [
    "notice-identifier",
    "notice-title",
    "notice-type",
    "notice-subtype",
    "notice-version",
    "publication-number",
    "buyer-name",
    "buyer-identifier",
    "buyer-country",
    "official-language",
    "dispatch-date",
    # What TED shows as the publication date: one to six days after dispatch.
    "publication-date",
    "deadline-receipt-tender-date-lot",
    "deadline-receipt-tender-time-lot",
    "deadline-receipt-request-date-lot",
    "deadline-receipt-request-time-lot",
    # The tender deadline as a full datetime with offset, one per lot: the union of
    # BT-131, BT-1311 and BT-630, set for every contract notice in every era.
    # `deadline-date-lot` is BT-13 (additional information) and is not a deadline.
    "deadline-receipt-request",
    "classification-cpv",
    "estimated-value-lot",
    "estimated-value-cur-lot",
    "estimated-value-proc",
    "estimated-value-cur-proc",
    "total-value",
    "total-value-cur",
    "result-value-notice",
    "result-value-cur-notice",
    "winner-selection-status",
    "procedure-type",
    "procedure-identifier",
    "legal-basis",
    "contract-nature",
    "description-lot",
    "description-proc",
    "main-activity",
    "csecurity-clearance-description-lot",
    "non-disclosure-agreement-lot",
    "links",
    # WP-159: the contract period per lot (BT-36 number and unit, BT-536, BT-537, BT-58, BT-57), names from the
    # field list page of 30 October 2026; read by `normalise.contract_period`. Not yet seen in a live answer.
    "duration-period-value-lot",
    "duration-period-unit-lot",
    "contract-duration-start-date-lot",
    "contract-duration-end-date-lot",
    "renewal-maximum-lot",
    "renewal-description-lot",
]


@dataclass
class TedQuery:
    """An expert query plus paging state."""

    query: str
    fields: list[str]
    page: int = 1
    limit: int = PAGE_SIZE
    scope: str = "ALL"


def defence_query(since: date, until: date | None = None) -> str:
    """Build the TED expert query for defence-relevant notices.

    Three independent signals ORed together, matching classify.py:
      - legal basis is the defence directive
      - CPV sits in division 35
      - a security clearance requirement is stated (BT-732)

    The buyer-list signal cannot be expressed in the query language, so it is
    applied downstream after ingestion.
    """
    until = until or date.today()
    # Expert search dates are YYYYMMDD. An ISO date is rejected outright with
    # QUERY_INVALID_FIELD_FORMAT, which is how every live run failed until this
    # was checked against the API rather than against a fixture.
    window = (f"publication-date>={since.strftime('%Y%m%d')} AND "
              f"publication-date<={until.strftime('%Y%m%d')}")
    signals = " OR ".join(
        [
            'legal-basis IN ("32009L0081")',
            'classification-cpv=35*',
            'csecurity-clearance-description-lot=*',
        ]
    )
    return f"({window}) AND ({signals})"


def day_query(day: date) -> str:
    """Every notice published on one day, whatever it is for.

    The daily job asks the defence question in the query because it runs every
    morning and the answer is small. The history does not: it lands all seven
    million notices since 2017 and lets classification decide afterwards, the
    same rule the Polish and Spanish collections follow. A signal we learn to
    read next year is then a reclassification, not a refetch of a decade.

    A day is also the unit that fits: the API refuses paging past 15,000
    results in one query (page 60 works, page 80 is rejected), and the busiest
    day measured is 3,647.
    """
    stamp = day.strftime("%Y%m%d")
    return f"publication-date>={stamp} AND publication-date<={stamp}"


# Name stems for the history query below: TED's `buyer-name~` is a case- and accent-insensitive
# word match (`~Armees` finds "Économat des armées"; a trailing `*` is allowed, a leading one is
# refused). Read against the vocabulary of buyer_vocab.DEFENCE_INCLUDE, 16 October 2026. The
# classifier still decides: a stem only decides what is fetched. Short acronyms (DGA, DMO, BWI,
# HIL) are left out, they name civil bodies as often as defence ones.
DEFENCE_BUYER_STEMS = (
    "Defence", "Defense", "Defensie", "Defensa", "Defesa", "Difesa", "Verteidigung*",
    "Landesverteidigung", "Bundeswehr", "Bundesheer", "Streitkräfte", "Luftwaffe", "Marinearsenal",
    "Wehrtechnische", "Ausrüstung", "armee*", "\"armed forces\"", "army", "navy", "\"air force\"",
    "\"Marine nationale\"", "Mindef", "Minarm", "\"Leidos Supply\"", "military", "militare", "militar*",
    "Esercito", "Ejército", "Exército", "Armada", "Marinha", "\"Forças Armadas\"", "Landmacht",
    "Luchtmacht", "Wojsk*", "Obrony", "Uzbrojenia", "Obrany", "Vojensk*", "Armáda", "Obrane",
    "Obrambo", "Odbrane", "Vojska", "Oružane", "Honvéd*", "Honvédelmi", "Apărării", "\"Statul Major\"",
    "отбраната", "военн*", "Αμυνας", "Αμυντικ*", "Στρατιωτικ*", "Forsvar*", "Försvar*", "Puolustus*",
    "Kaitse*", "\"Aizsardzības ministrija\"", "Gynybos", "Kariuomen*", "NATO", "OCCAR",
)


def _cpv_terms() -> list[str]:
    from ..classify import CPV_MILITARY_ADJACENT, CPV_MILITARY_GROUPS

    return ([f"classification-cpv={g}*" for g in sorted(CPV_MILITARY_GROUPS)]
            + ["classification-cpv IN (" + " ".join(sorted(CPV_MILITARY_ADJACENT)) + ")"])


def defence_history_query(start: date, end: date) -> str:
    """Notices of a publication window that the classifier can qualify without the full day.

    Three server-side selections ORed: the legal basis 2009/81/EC; a military CPV (the groups
    and added codes classify.py reads; division 35 as a whole is not asked, the civil groups
    never qualify); a buyer whose name carries a defence stem. What it cannot see: a buyer
    listed under a name without any stem, and a notice qualified only by a link from a
    national defence notice (`sig_linked_defence`).
    """
    window = (f"publication-date>={start.strftime('%Y%m%d')} AND "
              f"publication-date<={end.strftime('%Y%m%d')}")
    signals = (['legal-basis IN ("32009L0081")'] + _cpv_terms()
               + [f"buyer-name~{stem}" for stem in DEFENCE_BUYER_STEMS])
    return f"({window}) AND ({' OR '.join(signals)})"


def _post(client: httpx.Client, payload: dict[str, Any]) -> dict[str, Any]:
    def send() -> httpx.Response:
        r = client.post(
            TED_SEARCH_URL,
            json=payload,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            timeout=60.0,
        )
        r.raise_for_status()
        return r

    return request_with_retry(send, what=f"TED page {payload.get('page')}").json()


def _complete_or_raise(seen: int, total: Any, query: str) -> None:
    """A list that ends before the count TED itself stated is a short day, not a small one."""
    if isinstance(total, int) and seen < total:
        raise RuntimeError(f"TED: {seen} of {total} notices returned; the result was "
                           f"cut short, not complete ({query[:80]})")


def search(
    query: str,
    fields: list[str] | None = None,
    *,
    client: httpx.Client | None = None,
    max_pages: int = MAX_PAGES,
    page_size: int = PAGE_SIZE,
    pause: float = 0.0,
) -> Iterator[dict[str, Any]]:
    """Yield raw notice records, following pagination.

    Yields the notice dicts exactly as TED returns them. Normalisation happens
    elsewhere, so that the raw payload can be archived unmodified and any
    downstream logic can be re-run against it without refetching.
    """
    fields = fields or TED_FIELDS
    owns_client = client is None
    client = client or new_client(headers={"User-Agent": USER_AGENT})
    try:
        page = 1
        seen = 0
        while page <= max_pages:
            payload = {
                "query": query,
                "fields": fields,
                "page": page,
                "limit": page_size,
                "scope": "ALL",
            }
            if page > 1 and pause:
                time.sleep(pause)
            data = _post(client, payload)
            notices = data.get("notices") or data.get("results") or []
            total = data.get("totalNoticeCount") or data.get("total")
            if not notices:
                _complete_or_raise(seen, total, query)
                break
            for n in notices:
                seen += 1
                yield n
            total = data.get("totalNoticeCount") or data.get("total")
            log.info("TED page %s: %s notices (running total %s of %s)",
                     page, len(notices), seen, total)
            if total is not None and seen >= total:
                break
            if len(notices) < page_size:
                _complete_or_raise(seen, total, query)
                break
            page += 1
        else:
            raise RuntimeError(f"TED: {max_pages} pages read and more are stated; "
                               f"the result was cut short, not complete ({query[:80]})")
    finally:
        if owns_client:
            client.close()


def count(query: str, *, client: httpx.Client | None = None) -> int:
    """How many notices a query matches, in one request (the API states it with any page)."""
    owns_client = client is None
    client = client or new_client(headers={"User-Agent": USER_AGENT})
    try:
        data = _post(client, {"query": query, "fields": ["publication-number"], "page": 1,
                              "limit": 1, "scope": "ALL"})
        return int(data.get("totalNoticeCount") or data.get("total") or 0)
    finally:
        if owns_client:
            client.close()


# The winners of a result notice (WP-37, the supplier map). The raw payloads of the daily pull do not carry them
# (TED_FIELDS above has no winner field), so the supplier loader asks for them by publication number.
#   organisation-name-tenderer / -country-tenderer / -identifier-tenderer  one entry per organisation of
#       the notice's tendering parties, in the same order (measured 18 October 2026: a legal form and a
#       country agree for 99.0 % of 1,226 name/country pairs; `winner-name` against `winner-country` agree
#       for 81 % in notices with several winners, so the winner fields must not be zipped)
#   winner-name   the name of the winning organisation, once per lot; it says WHICH tenderers won
#                 (every winner name is among the tenderers: 30,632 of 30,632 notices measured)
AWARD_FIELDS = [
    "publication-number",
    "winner-name",
    "organisation-name-tenderer",
    "organisation-country-tenderer",
    "organisation-identifier-tenderer",
]
AWARD_BATCH = 100        # "a hundred numbers answer in one request" (module docstring)
PUBLICATION_NUMBER = re.compile(r"\d{1,9}-\d{4}")      # 633131-2026; nothing else goes into a query


def fetch_by_numbers(numbers: list[str], fields: list[str] | None = None, *,
                     client: httpx.Client | None = None) -> dict[str, dict[str, Any]]:
    """The records of up to a hundred publication numbers, by number. A number TED does not
    know is simply absent from the answer."""
    if not numbers:
        return {}
    if len(numbers) > AWARD_BATCH:
        raise ValueError(f"at most {AWARD_BATCH} publication numbers per request")
    if not all(PUBLICATION_NUMBER.fullmatch(n) for n in numbers):
        raise ValueError("not a publication number")        # the query is built from them: no other text
    owns_client = client is None
    client = client or new_client(headers={"User-Agent": USER_AGENT})
    try:
        query = "publication-number IN (" + " ".join(numbers) + ")"
        data = _post(client, {"query": query, "fields": fields or AWARD_FIELDS, "page": 1,
                              "limit": len(numbers), "scope": "ALL"})
        return {_number(n): n for n in (data.get("notices") or data.get("results") or [])}
    finally:
        if owns_client:
            client.close()


NOTICE_XML_URL = "https://ted.europa.eu/en/notice/{number}/xml"     # the notice's `links.xml.MUL`


def fetch_notice_xml(number: str, *, client: httpx.Client) -> bytes | None:
    """The notice document of one publication number, as TED publishes it (WP-95: the winners of an older-format
    result notice are in the document only; the search API states none). None when TED has no such notice."""
    if not PUBLICATION_NUMBER.fullmatch(number):
        raise ValueError("not a publication number")

    def send() -> httpx.Response:
        r = client.get(NOTICE_XML_URL.format(number=number), headers={"Accept": "application/xml"}, timeout=60.0)
        if r.status_code != 404:
            r.raise_for_status()
        return r

    r = request_with_retry(send, what=f"TED notice {number}")
    return None if r.status_code == 404 else r.content


def _number(notice: dict[str, Any]) -> str:
    value = notice.get("publication-number") or notice.get("notice-identifier")
    if isinstance(value, list):
        value = value[0] if value else ""
    return str(value or "")


class DailyPull:
    """The daily window: the defence query over the whole window, then every notice
    of today and of yesterday.

    The defence query cannot express the buyer-list signal, so a notice that only a
    listed buyer makes defence waited for the full-day job of the next morning, and
    a day of them were absent from the list meanwhile. Whole days close that: they
    land everything and classification decides, the rule the history load follows.
    A notice both queries return is yielded once.

    `defence_fetched` counts what the defence query returned. It is what the
    coverage floor was measured against, so it is what the floor is applied to:
    counted over whole days it would be met by any answer at all.
    """

    def __init__(self, days_back: int = 1, *, today: date | None = None,
                 whole_days: int = 2, **kw: Any) -> None:
        self.days_back = days_back
        self.today = today
        self.whole_days = whole_days
        self.kw = kw
        self.defence_fetched = 0

    def __iter__(self) -> Iterator[dict[str, Any]]:
        today = self.today or date.today()
        seen: set[str] = set()
        for notice in search(defence_query(today - timedelta(days=self.days_back), today),
                             **self.kw):
            self.defence_fetched += 1
            seen.add(_number(notice))
            yield notice
        for back in range(self.whole_days):
            for notice in search(day_query(today - timedelta(days=back)), **self.kw):
                number = _number(notice)
                if number and number in seen:
                    continue
                seen.add(number)
                yield notice


def fetch_window(days_back: int = 1, **kw) -> DailyPull:
    """Daily incremental pull. Overlaps by design to survive a missed run."""
    return DailyPull(days_back, **kw)


def content_hash(notice: dict[str, Any]) -> str:
    """Stable hash for change detection.

    Sorted keys so that key ordering in the response cannot produce a spurious
    new version. This is what stops the archive filling with noise.
    """
    blob = json.dumps(notice, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()
