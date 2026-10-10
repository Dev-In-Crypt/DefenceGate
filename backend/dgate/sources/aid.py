"""AID connector (France, Agence de l'innovation de defense).

Pages:     https://www.defense.gouv.fr/aid/appels-projets/{cours,clotures}  (+ detail pages)
Auth:      none
Operator:  Agence de l'innovation de defense (AID), Ministere des Armees
Licence:   Licence Ouverte 2.0 (Etalab), stated in the site's legal notice, except
           third-party material and images, which are not taken.

There is no API and no feed. The agency publishes each call as a page under one of two
lists, "en cours" and "clotures", and the page's text says when it closes. Measured on
10 October 2026: 17 current, 19 closed, and RAPID, which is a standing call.

Four properties decided the design.

1. **Every call on this site is the publisher's own defence call.** The agency is the
   Ministry of Armed Forces' innovation agency, so there is no tag to read and none is
   needed: what it lists is defence (ASTRID and ASMA research grants run through the ANR,
   defis, expressions of interest by the DGA's innovation poles, Cyber Defense Factory,
   RAPID). The page's title says which kind.

2. **The dates are prose, in about ten phrasings.** "Limite de depot des projets :
   02/03/2026 a 15:00 CET", "Fermeture : 15/09/2023 a 15h00", "Les reponses sont attendues
   avant le vendredi 10 juillet 2026 a minuit", "avant le mardi 07/08/2026 a 18h CET",
   "Vous avez jusqu'au vendredi 29 mai pour candidater" (no year), "Du 6 janvier au
   2 mars : depot des candidatures". They are read in two tiers: an explicit label wins,
   and only without one is a sentence about applying read. A page with no date at all
   (a rolling call) has none, and is never given one.

3. **The list's label cannot be trusted.** "En cours" held a call whose deadline was
   15 January 2026 on 10 October. The status is worked out from the date; the list is
   used only for a page with no date.

4. **A page ends where the site's sharing and news block begins.** After "Partager la
   page" comes a carousel of other news with its own dates, which change daily. Read, it
   would have supplied wrong deadlines and made every page's hash change every night.
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

from . import USER_AGENT, request_with_retry

log = logging.getLogger(__name__)

SOURCE_CODE = "fr_aid"
SITE = "https://www.defense.gouv.fr"
LISTS = {"cours": "/aid/appels-projets/cours", "clotures": "/aid/appels-projets/clotures"}
STANDING = ["/aid/deposez-votre-projet/rapid-regime-dappui-linnovation-duale"]
PARIS = ZoneInfo("Europe/Paris")
REQUEST_PAUSE = 1.0
END_OF_PAGE = "Partager la page"

MONTHS = {"janvier": 1, "février": 2, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6,
          "juillet": 7, "août": 8, "aout": 8, "septembre": 9, "octobre": 10, "novembre": 11,
          "décembre": 12, "decembre": 12}
_MONTH = "|".join(MONTHS)
_WEEKDAY = r"(?:lundi|mardi|mercredi|jeudi|vendredi|samedi|dimanche)\s+"

_TIME = r"(?:\s*(?:à|a)\s*(?P<h>\d{1,2})\s*[h:]\s*(?P<m>\d{2})?|\s*(?:à|a)\s*(?P<midnight>minuit))?"
# Tier 0: a challenge that states the applications phase as a range. Its later steps carry
# "date limite" labels of their own (the file of the candidates already selected), and
# those are not the date a supplier has to apply by.
_APPLICATION_PHASE = re.compile(
    r"Phase\s+d.appel\s+[àa]\s+candidatures\s*:\s*du\s+\d{1,2}/\d{1,2}/\d{4}\s+au\s+"
    r"(?P<d>\d{1,2})/(?P<mo>\d{1,2})/(?P<y>\d{4})" + _TIME, re.I)
# Tier 1: the page labels the date as the closing one.
_LABELLED = [
    re.compile(r"Date\s+(?:limite|de\s+fermeture)[^:]{0,60}:\s*(?P<d>\d{1,2})/(?P<mo>\d{1,2})/"
               r"(?P<y>\d{2,4})" + _TIME, re.I),
    re.compile(r"Limite\s+(?:de\s+)?d[ée]p[ôo]t[^:]{0,40}:\s*(?P<d>\d{1,2})/(?P<mo>\d{1,2})/(?P<y>\d{4})"
               + _TIME, re.I),
    re.compile(r"Fermeture\s*:\s*(?P<d>\d{1,2})/(?P<mo>\d{1,2})/(?P<y>\d{4})" + _TIME, re.I),
    re.compile(r"Limite\s+(?:de\s+)?d[ée]p[ôo]t[^:]{0,40}:\s*(?P<d>\d{1,2})(?:er)?\s+"
               rf"(?P<mon>{_MONTH})\s+(?P<y>\d{{4}})" + _TIME, re.I),
    re.compile(r"Date\s+de\s+cl[ôo]ture\W{0,10}.{0,80}?avant\s+le\s+(?:" + _WEEKDAY + r")?"
               rf"(?P<d>\d{{1,2}})(?:er)?\s+(?P<mon>{_MONTH})\s+(?P<y>\d{{4}})" + _TIME, re.I),
]
# Tier 2: a sentence about applying that carries a date.
_BEFORE_WORDS = re.compile(r"candidat|dossier|r[ée]ponse|d[ée]p[ôo]t|inscription compl|d[ée]poser", re.I)
_BEFORE_NUMERIC = re.compile(
    r"(?:avant|pour)\s+le\s+(?:" + _WEEKDAY + r")?(?P<d>\d{1,2})/(?P<mo>\d{1,2})/(?P<y>\d{4})"
    + _TIME, re.I)
_BEFORE_WORDED = re.compile(
    r"avant\s+le\s+(?:" + _WEEKDAY + r")?(?P<d>\d{1,2})(?:er)?\s+"
    rf"(?P<mon>{_MONTH})(?:\s+(?P<y>\d{{4}}))?" + _TIME, re.I)
_UNTIL = re.compile(
    r"jusqu.(?:au|à)\s+(?:" + _WEEKDAY + r")?(?P<d>\d{1,2})(?:er)?\s+"
    rf"(?P<mon>{_MONTH})(?:\s+(?P<y>\d{{4}}))?\s+pour\s+candidater", re.I)
_RANGE = re.compile(
    rf"Du\s+\d{{1,2}}(?:er)?\s+(?:{_MONTH})\s+au\s+(?P<d>\d{{1,2}})(?:er)?\s+(?P<mon>{_MONTH})"
    r"(?:\s+(?P<y>\d{4}))?\s*:\s*d[ée]p[ôo]t\s+des\s+candidatures", re.I)
_OPENING = re.compile(
    r"Ouverture\s*:\s*(?P<d>\d{1,2})/(?P<mo>\d{1,2})/(?P<y>\d{4})" + _TIME, re.I)
_MAX_AID = re.compile(r"(?:inf[ée]rieure?|[ée]gale?|maximum|jusqu.[àa])[^.]{0,40}?(\d[\d\s]*)\s*k€",
                      re.I)


def _client() -> httpx.Client:
    return httpx.Client(headers={"User-Agent": USER_AGENT}, follow_redirects=True)


# ---------------------------------------------------------------- fetching

def _get(client: httpx.Client, path: str) -> str:
    def send() -> httpx.Response:
        response = client.get(SITE + path, timeout=60.0)
        response.raise_for_status()
        return response

    return request_with_retry(send, attempts=6, max_delay=60.0,
                              what=f"{SOURCE_CODE} {path}").text


def list_pages(client: httpx.Client) -> list[tuple[str, str]]:
    """(list name, path) of every call page under both lists, and the standing ones.

    An empty list is an error: the page changed shape, and an empty result recorded as
    "no calls" would let every stored call go on looking confirmed.
    """
    found: list[tuple[str, str]] = []
    for name, path in LISTS.items():
        body = _main(_get(client, path))
        paths = sorted(set(re.findall(rf'href="(/aid/appels-projets/{name}/[^"#?]+)"', body)))
        if not paths:
            raise RuntimeError(f"{SOURCE_CODE}: no call links on {path}; the page changed shape")
        found += [(name, p) for p in paths]
        time.sleep(REQUEST_PAUSE)
    found += [("standing", p) for p in STANDING]
    return found


def _main(page: str) -> str:
    match = re.search(r"<main.*?</main>", page, re.S)
    return match.group(0) if match else page


def _text(markup: str) -> str:
    markup = re.sub(r"<(script|style|nav|header|footer)[^>]*>.*?</\1>", " ", markup, flags=re.S)
    plain = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", markup))).strip()
    cut = plain.find(END_OF_PAGE)
    return plain[:cut].strip() if cut > 0 else plain


def _meta(page: str, name: str) -> str | None:
    match = re.search(rf'<meta[^>]+property="{re.escape(name)}"[^>]+content="([^"]*)"', page)
    return html.unescape(match.group(1)).strip() if match else None


def fetch_page(client: httpx.Client, kind: str, path: str) -> dict[str, Any]:
    page = _get(client, path)
    title = _meta(page, "og:title")
    if not title:
        raise ValueError(f"{path}: no title; the page changed shape")
    return {
        "url": SITE + path,
        "slug": path.rstrip("/").rsplit("/", 1)[-1],
        "list": kind,
        "title": title,
        "summary": _meta(page, "og:description"),
        "published": (_meta(page, "article:published_time") or "")[:10] or None,
        "modified": (_meta(page, "article:modified_time") or "")[:10] or None,
        "text": _text(_main(page)),
    }


def fetch_all(*, client: httpx.Client | None = None) -> list[dict[str, Any]]:
    """Every call page, one request a second. A page that cannot be read is skipped with
    a warning and the run is told, so one withdrawn page does not cost the others."""
    owns = client is None
    client = client or _client()
    records: list[dict[str, Any]] = []
    try:
        pages = list_pages(client)
        for kind, path in pages:
            try:
                records.append(fetch_page(client, kind, path))
            except (httpx.HTTPError, ValueError, RuntimeError) as exc:
                log.warning("%s: %s unreadable: %s", SOURCE_CODE, path, exc)
            time.sleep(REQUEST_PAUSE)
    finally:
        if owns:
            client.close()
    if not records:
        raise RuntimeError(f"{SOURCE_CODE}: no page could be read")
    return records


# ----------------------------------------------------------------- parsing

def _moment(match: re.Match[str], published: date | None) -> datetime | None:
    groups = match.groupdict()
    month = int(groups["mo"]) if groups.get("mo") else MONTHS.get((groups.get("mon") or "").lower())
    if not month:
        return None
    day = int(groups["d"])
    year = int(groups["y"]) if groups.get("y") else None
    if year is not None and year < 100:
        year += 2000
    if year is None:
        # No year written: the first such date on or after the page's own publication.
        base = published or date.today()
        year = base.year
        try:
            if date(year, month, day) < base:
                year += 1
        except ValueError:
            return None
    hour, minute = 23, 59                       # a date alone closes at the end of the day
    if groups.get("h"):
        hour, minute = int(groups["h"]), int(groups.get("m") or 0)
    try:
        return datetime(year, month, day, hour, minute, tzinfo=PARIS).astimezone(UTC)
    except ValueError:
        return None


def deadlines(text: str, published: date | None = None) -> list[datetime]:
    """Every closing date the page states, from the most explicit phrasing that is there.

    A labelled date ("Limite de depot ...", "Fermeture :") wins. Only without one are the
    sentences about applying read, and a sentence about a webinar is not one of them.
    """
    phase = [m for m in (_moment(x, published) for x in _APPLICATION_PHASE.finditer(text)) if m]
    if phase:
        return sorted(set(phase))
    labelled: list[datetime] = []
    for pattern in _LABELLED:
        labelled += [m for m in (_moment(x, published) for x in pattern.finditer(text)) if m]
    if labelled:
        return sorted(set(labelled))
    found: list[datetime] = []
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        if "webinaire" in sentence.lower():
            continue
        for pattern in (_UNTIL, _RANGE):
            found += [m for m in (_moment(x, published) for x in pattern.finditer(sentence)) if m]
        if _BEFORE_WORDS.search(sentence):
            for pattern in (_BEFORE_NUMERIC, _BEFORE_WORDED):
                found += [m for m in (_moment(x, published) for x in pattern.finditer(sentence)) if m]
    return sorted(set(found))


def opening(text: str) -> date | None:
    match = _OPENING.search(text)
    moment = _moment(match, None) if match else None
    return moment.astimezone(PARIS).date() if moment else None


def kind_of(title: str) -> str | None:
    """What sort of call the page is, from its title. Not a grant in every case: the
    agency's expressions of interest and challenges are calls to suppliers."""
    t = title.lower()
    if re.search(r"astrid|asma|maturation|th[eè]ses", t):
        return "research grant"
    if "rapid" in t:
        return "innovation grant (RAPID)"
    if re.search(r"d[ée]fi|challenge", t):
        return "challenge"
    if re.search(r"manifestation d.int[ée]r[êe]t|\bami\b", t):
        return "expression of interest"
    if re.search(r"appel[s]? [àa] projet", t):
        return "call for projects"
    return None


def max_aid_eur(text: str) -> int | None:
    """The ceiling per project in kEUR, when the page states one. Not the call's budget."""
    match = _MAX_AID.search(text)
    if not match:
        return None
    try:
        return int(re.sub(r"\s", "", match.group(1))) * 1000
    except ValueError:
        return None


def status(record: dict[str, Any], *, now: datetime | None = None) -> str:
    """From the dates; the list's own label is used only for a page that has none."""
    now = now or datetime.now(UTC)
    published = date.fromisoformat(record["published"]) if record.get("published") else None
    ends = deadlines(record.get("text") or "", published)
    start = opening(record.get("text") or "")
    if ends:
        if now > ends[-1]:
            return "closed"
        if start and start > now.astimezone(PARIS).date():
            return "forthcoming"
        return "open"
    return "closed" if record.get("list") == "clotures" else "open"


def in_scope(record: dict[str, Any], *, today: date | None = None) -> bool:
    today = today or date.today()
    now = datetime.combine(today, datetime.min.time(), tzinfo=PARIS)
    if status(record, now=now) != "closed":
        return True
    published = date.fromisoformat(record["published"]) if record.get("published") else None
    ends = deadlines(record.get("text") or "", published)
    if ends:
        return ends[-1].year == today.year
    return bool(published and published.year == today.year)
