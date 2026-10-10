"""Vinnova connector (Sweden, the innovation agency).

Endpoint:  GET https://data.vinnova.se/api/{program,utlysningar,ansokningsomgangar}/<date>
Auth:      none
Operator:  Vinnova, Sweden's innovation agency
Licence:   Public Domain Mark. The agency's open-data page says the data "may be used
           freely without fees or other restrictions".

The structure is the agency's own: a **programme** has one or more **calls**
(utlysningar), and a call has one or more **application rounds**
(ansokningsomgangar). The round is what a supplier can act on -- it carries the opening
and closing dates -- so it is the unit stored here, with its call and programme named in
the payload.

Measured on 10 October 2026: 271 programmes, 1,211 calls, 3,840 rounds, of which 179
close in 2026 or later and 46 are open.

Four properties decided the design.

1. **The publisher names its defence programmes, and there are two** (and the
   aeronautics programme NFFP is added to them, as dual use, by the owner's decision). "Innovationsprogram-
   met for civil-militara synergier" is run jointly with the Armed Forces and funds
   "needs-driven defence innovation"; "Nationellt innovationsprogram for civilt forsvar"
   is the civil half of total defence. In 2026 they hold seven rounds, five of them
   public. Everything else Vinnova funds is civil innovation, and some of it names
   defence in passing (aeronautics research, cybersecurity inside digitalisation); that
   is the publisher mentioning it, not naming it, and is not collected.

2. **A round can be invited-only.** `Publik` is 0 for "special initiatives where only
   invited parties can apply": the "extra" rounds that follow a public one. A supplier
   cannot answer them and they are not kept.

3. **The date in the URL is "changed since", and the three lists are small.** The whole
   register is a few megabytes, so it is fetched whole each night: three requests, no
   window, no gap to heal. The call and programme are joined onto every round so a
   landed payload says what it belongs to without asking again.

4. **Dates are Stockholm time with no zone.** A close at 14:00 is 12:00 UTC in summer.
   A closing date of 1900-01-01 is the register's placeholder for "none", not a date.

The budget is prose, and usually a ceiling per project ("1-7 million kronor"), which is
not what the column means. A sum is read only from a sentence that is about the call's
own budget.
"""

from __future__ import annotations

import logging
import re
import time
from datetime import UTC, date, datetime
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from . import USER_AGENT, request_with_retry

log = logging.getLogger(__name__)

SOURCE_CODE = "se_vinnova"
BASE = "https://data.vinnova.se/api"
SINCE = "2000-01-01"
STOCKHOLM = ZoneInfo("Europe/Stockholm")
REQUEST_PAUSE = 1.0

# The publisher's own words for its defence programmes, in Swedish and English.
_DEFENCE = re.compile(r"civil-milit|milit[aä]r|military", re.I)
_CIVIL_DEFENCE = re.compile(r"civilt f[oö]rsvar|totalf[oö]rsvar|civil defen[cs]e|total defen[cs]e",
                            re.I)
# NFFP, the national aeronautics research programme, added by the owner's decision on
# 10 October 2026. Its calls name "defence capability" among the outcomes they expect
# and are open to companies; the programme is aeronautics, so it is dual use and not a
# defence programme. It is listed by name: nothing else in the register is added by it.
_AERONAUTICS = re.compile(r"flygtekniska forskningsprogram|national aeronautic", re.I)

# A digit may not sit between "budget" and the sum: "budget ... 30 projekt a 2 miljoner
# kronor" is a ceiling per project and must not be read as the call's budget. The unit
# is itself the currency in "5 mkr" and "10 MSEK"; "miljoner" is followed by "kronor".
_MONEY = re.compile(
    r"budget\w*[^.\d\n]{0,80}?(?P<num>\d[\d\s\u00a0]*(?:[.,]\d+)?)\s*"
    r"(?:(?P<unit>miljoner|miljon|miljarder|mnkr|msek|mkr)\b\s*(?:kronor|kr|sek)?"
    r"|(?:kronor|kr|sek)\b)", re.I)
_UNITS = {"miljoner": 1e6, "miljon": 1e6, "mnkr": 1e6, "msek": 1e6, "mkr": 1e6, "miljarder": 1e9}


def _client() -> httpx.Client:
    return httpx.Client(headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
                        follow_redirects=True)


# ---------------------------------------------------------------- fetching

def _get_list(client: httpx.Client, resource: str, since: str) -> list[dict[str, Any]]:
    def send() -> httpx.Response:
        response = client.get(f"{BASE}/{resource}/{since}", timeout=180.0)
        response.raise_for_status()
        return response

    payload = request_with_retry(send, attempts=5, max_delay=60.0,
                                 what=f"{SOURCE_CODE} {resource}").json()
    if not isinstance(payload, list):
        raise ValueError(f"{resource}: expected a list, got {type(payload).__name__}; "
                         "the shape changed")
    return payload


def join(rounds: list[dict[str, Any]], calls: list[dict[str, Any]],
         programmes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Each round with its call and programme named inside it."""
    by_programme = {p.get("Diarienummer"): p for p in programmes}
    by_call = {c.get("Diarienummer"): c for c in calls}
    out: list[dict[str, Any]] = []
    for record in rounds:
        call = by_call.get(record.get("DiarienummerUtlysning"))
        programme = by_programme.get((call or {}).get("DiarienummerProgram"))
        out.append({
            **record,
            "utlysning": ({k: call.get(k) for k in
                           ("Diarienummer", "Titel", "TitelEngelska", "DiarienummerProgram")}
                          if call else None),
            "program": ({k: programme.get(k) for k in ("Diarienummer", "Titel", "TitelEngelska")}
                        if programme else None),
        })
    return out


def fetch_all(*, client: httpx.Client | None = None, since: str = SINCE) -> list[dict[str, Any]]:
    """Every application round the agency has published, joined to call and programme.

    Raises if the register comes back empty or without programmes: a join against an
    empty list would silently drop every round out of scope.
    """
    owns = client is None
    client = client or _client()
    try:
        programmes = _get_list(client, "program", since)
        time.sleep(REQUEST_PAUSE)
        calls = _get_list(client, "utlysningar", since)
        time.sleep(REQUEST_PAUSE)
        rounds = _get_list(client, "ansokningsomgangar", since)
    finally:
        if owns:
            client.close()
    if not rounds or not calls or not programmes:
        raise RuntimeError(f"{SOURCE_CODE}: empty register ({len(programmes)} programmes, "
                           f"{len(calls)} calls, {len(rounds)} rounds); refusing to continue")
    return join(rounds, calls, programmes)


# ------------------------------------------------------------------ parsing

def programme_title(record: dict[str, Any]) -> str:
    programme = record.get("program") or {}
    return " | ".join(t for t in (programme.get("Titel"), programme.get("TitelEngelska")) if t)


def regime(record: dict[str, Any]) -> str | None:
    """`defence` for the civil-military programme, `dual_use` for civil defence and for
    the aeronautics programme, None for everything else Vinnova funds."""
    title = programme_title(record)
    if _DEFENCE.search(title):
        return "defence"
    if _CIVIL_DEFENCE.search(title) or _AERONAUTICS.search(title):
        return "dual_use"
    return None


def _moment(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        naive = datetime.fromisoformat(str(value)[:19])
    except ValueError:
        return None
    if naive.year <= 1900:                      # the register's "no date"
        return None
    return naive.replace(tzinfo=STOCKHOLM).astimezone(UTC)


def opens_at(record: dict[str, Any]) -> date | None:
    start = _moment(record.get("Oppningsdatum"))
    return start.astimezone(STOCKHOLM).date() if start else None


def deadline(record: dict[str, Any]) -> datetime | None:
    return _moment(record.get("Stangningsdatum"))


def status(record: dict[str, Any], *, now: datetime | None = None) -> str:
    now = now or datetime.now(UTC)
    start, end = _moment(record.get("Oppningsdatum")), deadline(record)
    if start and start > now:
        return "forthcoming"
    if end and end > now:
        return "open"
    return "closed"


def in_scope(record: dict[str, Any], *, today: date | None = None) -> bool:
    """A round a supplier could answer, in a defence programme, of interest this year."""
    today = today or date.today()
    if regime(record) is None or not record.get("Diarienummer") or not record.get("Titel"):
        return False
    if int(record.get("Publik") or 0) != 1:     # invited-only
        return False
    end = deadline(record)
    if end is None:
        return False
    now = datetime.combine(today, datetime.min.time(), tzinfo=STOCKHOLM)
    if status(record, now=now) in ("open", "forthcoming"):
        return True
    return end.year == today.year


def parse_total_budget(text: Any) -> float | None:
    """The call's own budget in kronor, from a sentence that is about the budget.

    "Den totala budgeten for utlysningen ar 10 miljoner kronor" is 10,000,000. "Maximalt
    800 000 kronor per projekt" and "1-7 miljoner kronor" are ceilings per project and
    have no "budget" in them, so they are not read as one.
    """
    match = _MONEY.search(str(text or ""))
    if not match:
        return None
    raw = re.sub(r"[\s ]", "", match.group("num")).replace(",", ".")
    try:
        amount = float(raw)
    except ValueError:
        return None
    return amount * _UNITS.get((match.group("unit") or "").lower(), 1.0)


# ----------------------------------------------------------------- the fields

def web_texts(record: dict[str, Any]) -> list[dict[str, str]]:
    items = record.get("WebTextLista")
    if not isinstance(items, list):
        return []
    return [{"sv": " ".join(str(i.get("TextSv") or "").split()),
             "en": " ".join(str(i.get("TextEn") or "").split())}
            for i in items if isinstance(i, dict)]


def _real(text: Any) -> str:
    """A title in English, or nothing: the register fills untranslated ones with "x"."""
    value = " ".join(str(text or "").split())
    return "" if value.lower() in ("x", "") else value


def title(record: dict[str, Any]) -> str:
    return _real(record.get("TitelEngelska")) or " ".join(str(record.get("Titel") or "").split())


def eligibility_text(record: dict[str, Any]) -> str:
    """What the call says about who may apply and on what terms, in English where the
    agency wrote it and in Swedish where it did not."""
    parts = [t["en"] or t["sv"] for t in web_texts(record)]
    return " ".join(p for p in parts if p)


def apply_url(record: dict[str, Any]) -> str | None:
    for link in record.get("LankLista") or []:
        if isinstance(link, dict) and link.get("URL") and "ansök" in str(link.get("Beskrivning")).lower():
            return str(link["URL"])
    return None


def conditions(record: dict[str, Any]) -> dict[str, Any]:
    call = record.get("utlysning") or {}
    programme = record.get("program") or {}
    return {
        "programme": programme.get("TitelEngelska") or programme.get("Titel"),
        "programme_dnr": programme.get("Diarienummer"),
        "call_dnr": call.get("Diarienummer"),
        "call_title": call.get("TitelEngelska") or call.get("Titel"),
        "title_sv": record.get("Titel"),
        "web_text_sv": [t["sv"] for t in web_texts(record)],
        "decision_expected": record.get("UppskattatBeslutsdatum"),
        "project_start_earliest": record.get("TidigastProjektstart"),
        "project_start_latest": record.get("SenastProjektstart"),
        "project_end_latest": record.get("SenastProjektslut"),
        "documents": [{"title": d.get("Titel"), "url": d.get("fileURL"), "lang": d.get("Lang"),
                       "primary": d.get("Primary")}
                      for d in record.get("DokumentLista") or [] if isinstance(d, dict)],
    }
