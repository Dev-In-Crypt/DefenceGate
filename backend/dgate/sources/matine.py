"""MATINE connector (Finland, the Ministry of Defence's scientific advisory board).

Pages:     https://defmin.fi/matine-maanpuolustuksen-tieteellinen-neuvottelukunta/
           and, beneath it, one page per year: `maararahahaku-YYYY`
Auth:      none
Operator:  Puolustusministerio (Ministry of Defence), MATINE
Licence:   not stated on the site; only facts (title, dates, sum) and a link are taken

MATINE funds research for the defence administration: one open call a year, for
EUR 0.85 to 1.9 million across 7 to 20 projects, decided in early December for the year
after. It is the Finnish ministry's own grant and the one defence call in the country
that has a date and a sum on a page. The 2027 call (page `maararahahaku-2027`) closed on
11 June 2026 at 16:00 for EUR 1,850,000.

Three properties decided the design.

1. **There is one call a year, and the page is named for the year it funds.** The call
   that closes in June 2026 is `maararahahaku-2027`. The landing page links the current
   one; every `maararahahaku-YYYY` link on it is read, none is guessed, and a landing
   page with none is an error and not "no calls".

2. **The date and the sum are in a sentence.** "...hakemusten (postileima) maaraaika on
   torstai 11.6.2026 klo 16:00" and "...yhteisarvoltaan enintaan 1 850 000 euroa". Finnish
   dates are `d.m.yyyy`, and the time is Helsinki time. Both are read from the sentence
   that names them and from nowhere else.

3. **The page ends in two named officials with telephone numbers.** "Lisatietoja ...
   Paasihteeri ... +358 ...". The text is cut where that block begins, before anything is
   landed, because a sweep for e-mail addresses would not remove a name and a number.
"""

from __future__ import annotations

import html
import logging
import re
import time
from datetime import UTC, date, datetime
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from . import MAX_HTML_CHARS, USER_AGENT, html_to_text_markup, request_with_retry

log = logging.getLogger(__name__)

SOURCE_CODE = "fi_matine"
SITE = "https://defmin.fi"
LANDING = "/matine-maanpuolustuksen-tieteellinen-neuvottelukunta"
HELSINKI = ZoneInfo("Europe/Helsinki")
REQUEST_PAUSE = 5.0           # the site's robots.txt asks for a crawl delay of 5 seconds
CONTACT_BLOCK = "Lisätietoja"

_CALL_LINK = re.compile(rf'href="({re.escape(SITE)}{re.escape(LANDING)}/maararahahaku-(\d{{4}}))"')
_DEADLINE = re.compile(
    r"(?:määräaika|viimeinen\s+lähetysaika)[^.]{0,200}?"
    r"(?P<d>\d{1,2})\.(?P<mo>\d{1,2})\.(?P<y>\d{4})(?:\s*klo\s*(?P<h>\d{1,2})[:.](?P<m>\d{2}))?",
    re.I)
_BUDGET = re.compile(r"yhteisarvoltaan\s+enintään\s+(?P<n>\d[\d\s ]*)\s*euroa", re.I)
_DECISION = re.compile(r"kokouksessaan\s+(?P<d>\d{1,2})\.(?P<mo>\d{1,2})\.(?P<y>\d{4})", re.I)
_PROJECTS = re.compile(r"(?P<lo>\d+)\s*-\s*(?P<hi>\d+)\s+tutkimushanketta", re.I)


def _client() -> httpx.Client:
    return httpx.Client(headers={"User-Agent": USER_AGENT}, follow_redirects=True)


# ---------------------------------------------------------------- fetching

def _get(client: httpx.Client, url: str) -> str:
    def send() -> httpx.Response:
        response = client.get(url, timeout=60.0)
        response.raise_for_status()
        return response

    return request_with_retry(send, attempts=5, max_delay=60.0,
                              what=f"{SOURCE_CODE} {url}").text


def _main_text(page: str) -> str:
    page = page[:MAX_HTML_CHARS]
    match = re.search(r"<main.*?</main>", page, re.S)
    markup = match.group(0) if match else page
    plain = re.sub(r"\s+", " ", html.unescape(html_to_text_markup(markup))).strip()
    cut = plain.find(CONTACT_BLOCK)
    return plain[:cut].strip() if cut > 0 else plain


def fetch_all(*, client: httpx.Client | None = None) -> list[dict[str, Any]]:
    """Every yearly call page linked from the landing page, with its text."""
    owns = client is None
    client = client or _client()
    try:
        landing = _get(client, SITE + LANDING)
        links = sorted(set(_CALL_LINK.findall(landing)), key=lambda m: m[1])
        if not links:
            raise RuntimeError(f"{SOURCE_CODE}: no maararahahaku page is linked from the "
                               f"landing page; the page changed shape")
        records: list[dict[str, Any]] = []
        for url, year in links:
            time.sleep(REQUEST_PAUSE)
            page = _get(client, url)
            title = re.search(r'<meta[^>]+property="og:title"[^>]+content="([^"]*)"', page)
            records.append({
                "url": url, "slug": url.rsplit("/", 1)[-1], "year": int(year),
                "title": html.unescape(title.group(1)).strip() if title else None,
                "text": _main_text(page),
            })
        return records
    finally:
        if owns:
            client.close()


# ------------------------------------------------------------------ parsing

def _moment(match: re.Match[str]) -> datetime | None:
    groups = match.groupdict()
    hour, minute = (int(groups["h"]), int(groups["m"])) if groups.get("h") else (23, 59)
    try:
        return datetime(int(groups["y"]), int(groups["mo"]), int(groups["d"]),
                        hour, minute, tzinfo=HELSINKI).astimezone(UTC)
    except ValueError:
        return None


def deadline(text: str) -> datetime | None:
    match = _DEADLINE.search(text or "")
    return _moment(match) if match else None


def decision_date(text: str) -> date | None:
    match = _DECISION.search(text or "")
    if not match:
        return None
    try:
        return date(int(match["y"]), int(match["mo"]), int(match["d"]))
    except ValueError:
        return None


def total_budget(text: str) -> float | None:
    """The sum the call states for all its projects together, in euro."""
    match = _BUDGET.search(text or "")
    if not match:
        return None
    try:
        return float(re.sub(r"[\s ]", "", match["n"]))
    except ValueError:
        return None


def project_range(text: str) -> tuple[int, int] | None:
    match = _PROJECTS.search(text or "")
    return (int(match["lo"]), int(match["hi"])) if match else None


def status(record: dict[str, Any], *, now: datetime | None = None) -> str:
    now = now or datetime.now(UTC)
    end = deadline(record.get("text") or "")
    if end is None:
        return "open"             # a call page is listed while it is live
    return "open" if end > now else "closed"


def in_scope(record: dict[str, Any], *, today: date | None = None) -> bool:
    """The call that is open, or that closed this year."""
    today = today or date.today()
    now = datetime.combine(today, datetime.min.time(), tzinfo=HELSINKI)
    if status(record, now=now) != "closed":
        return True
    end = deadline(record.get("text") or "")
    return bool(end and end.year == today.year)
