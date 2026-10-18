"""European Defence Fund project factsheets: who is in each selected project.

EDF projects are not in CORDIS. Each call year publishes a results page with one factsheet PDF per
selected project (DG DEFIS website). This module finds the pages, collects the PDF links, reads
what the file name says, turns a PDF into text, and defines the strict schema in which a language
model reports the consortium. The model call itself is `dgate.llm.complete_json`, made by the
caller; nothing here talks to a model.

What was found on 17 October 2026 (docs/sources/edf_factsheets.md):

  * the result pages have four different URLs across the five years; the plan's pattern holds
    for 2024 and 2025 only. They are discovered from the site's own sitemap instead.
  * the file name convention of the plan holds for 2024 and 2025 (and has a few exceptions);
    2023, 2022 and 2021 each use another one. `parse_filename` reads all four.
  * a factsheet is two or three pages: page 1 the project (acronym, title, call, duration, total
    cost, maximum EU contribution, a technical description), then a table of the consortium. The
    table has no PIC, no per-entity amount and no SME flag; countries are written in full.
  * the table reads cleanly only with pypdf's layout mode, but a name wrapped over two lines is
    split by the country column there; the plain mode keeps it whole. The quote check accepts a
    name found in either.
  * the technical description is cut before the text is landed or sent anywhere: the product
    keeps commercial facts only.
"""

from __future__ import annotations

import hashlib
import io
import re
import time
from dataclasses import dataclass
from html import unescape
from typing import Any, Literal
from urllib.parse import unquote, urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import httpx
from pydantic import BaseModel

from . import USER_AGENT, RateLimited, retry_after
from .cordis import RobotsDisallowed

SOURCE_CODE = "edf_factsheets"
BASE = "https://defence-industry-space.ec.europa.eu"
SITEMAP = f"{BASE}/sitemap.xml"
MAX_PDF_BYTES = 15 * 1024 * 1024
MAX_PAGES = 12                  # a factsheet has two or three
FIRST_YEAR = 2021

# The result page of a call year. Four shapes are in use; the sitemap lists whichever exists.
_RESULT_PAGE = re.compile(
    r"/calls-proposals/(?:european-defence-fund-(\d{4})-calls-proposals-results"
    r"|results?-edf-(\d{4})-calls-proposals)_en$")
# Tried when the sitemap does not list a year.
_GUESSED_PAGES = ("{b}/funding-opportunities/calls-proposals/result-edf-{y}-calls-proposals_en",
                  "{b}/funding-and-grants/calls-proposals/result-edf-{y}-calls-proposals_en")

_NOT_A_PROJECT = re.compile(r"general|overview|summary|pesco|results\s*-", re.I)
CATEGORIES = {"GROUND", "CYBER", "SPACE", "NAVAL", "AIR", "UWW", "SENS", "C4ISR", "MCBRN", "DIGIT",
              "ENERENV", "MATCOMP", "PROTMOB", "SIMTRAIN", "DIS", "SME", "SMERO", "AIRDEF", "DS"}
ACTIONS = ("RA", "DA", "CSA")


# ------------------------------------------------------------------ the site

def robots(http: httpx.Client) -> RobotFileParser:
    r = http.get(f"{BASE}/robots.txt")
    if r.status_code != 200:
        raise RobotsDisallowed(f"robots.txt answered HTTP {r.status_code}; not reading {BASE}")
    parser = RobotFileParser()
    parser.parse(r.text.splitlines())
    return parser


def allowed(parser: RobotFileParser, url: str) -> bool:
    return parser.can_fetch(USER_AGENT, url)


def result_pages(sitemap_xml: str) -> dict[int, str]:
    """{call year: results page URL} from the sitemap."""
    out: dict[int, str] = {}
    for loc in re.findall(r"<loc>([^<]+)</loc>", sitemap_xml):
        m = _RESULT_PAGE.search(loc)
        if m:
            out.setdefault(int(m.group(1) or m.group(2)), loc.strip())
    return out


def guessed_pages(year: int) -> list[str]:
    return [g.format(b=BASE, y=year) for g in _GUESSED_PAGES]


@dataclass(frozen=True)
class Link:
    url: str
    filename: str


def factsheet_links(page_html: str, page_url: str) -> list[Link]:
    """The project factsheets a results page links to: every document download except the
    general factsheets and summaries, once per URL."""
    seen: dict[str, Link] = {}
    for href in re.findall(r'href="([^"]+)"', page_html):
        href = unescape(href)
        if "/document/download/" not in href or "filename=" not in href:
            continue
        name = unquote(href.split("filename=", 1)[1])
        if not name.lower().endswith(".pdf") or _NOT_A_PROJECT.search(name):
            continue
        url = urljoin(page_url, href)
        if urlsplit(url).netloc != urlsplit(BASE).netloc:
            continue                       # factsheets are on the DEFIS site and nowhere else
        seen.setdefault(url, Link(url, name))
    return list(seen.values())


# ------------------------------------------------------------------ the file name

@dataclass
class FileInfo:
    year: int
    acronym: str
    ga_number: str | None
    action: str | None
    category: str | None
    topic_code: str | None
    lump_sum: bool
    step: bool

    @property
    def key(self) -> str:
        """The project's key inside its call year: the acronym without punctuation."""
        return f"{self.year}:{re.sub(r'[^0-9a-z]+', '', self.acronym.casefold())}"


# The website appends _0 or _1 to a file uploaded twice, and some files are marked updated or v2.
# Once only: "5G_COMPAD_2_0" is the project 5G COMPAD 2.0 uploaded twice, and "FIRES 2" is a name.
_VERSION = re.compile(r"(?:_\d|_updated|[_ ]v\d+(?:\.\d+)?)$", re.I)


def _strip_version(s: str) -> str:
    return _VERSION.sub("", s.strip()).strip(" _-")


def category_of(tokens: list[str]) -> str | None:
    """The capability category a topic code names: the last category token. Codes carry more than one when a
    qualifier is spelled like a category: EDF-2026-LS-DIS-RA-SMERO-NT is a call for SMEs and research
    organisations (SMERO), EDF-2023-DA-DS-AIRDEF-EATMI one for air defence, and taking the first token
    gave the disruptive-technologies category (DIS) to the first and DS to the second (WP-41, N8)."""
    return next((t for t in reversed([t.upper() for t in tokens if t]) if t in CATEGORIES), None)


def _decode(year: int, tokens: list[str], acronym: str, ga: str | None) -> FileInfo:
    toks = [t.upper() for t in tokens if t]
    action = next((t for t in toks if t in ACTIONS), None)
    category = category_of(toks)
    code = f"EDF-{year}-" + "-".join(toks) if toks else None
    return FileInfo(year, acronym, ga, action, category, code,
                    "LS" in toks, "STEP" in toks)


def parse_filename(filename: str, year: int) -> FileInfo | None:
    """What a factsheet's file name says, for the four conventions seen (None: not a project)."""
    stem = re.sub(r"\.pdf$", "", filename.strip(), flags=re.I)
    # 2024, 2025: FACTSHEET_EDF_<year>_<tokens>_<GA, nine digits>_<ACRONYM>   (GA is sometimes absent)
    m = re.match(r"FACTSHEET_EDF_(\d{4})_(.+)$", stem, re.I)
    if m:
        parts = m.group(2).split("_")
        for i, part in enumerate(parts):
            if re.fullmatch(r"\d{9}", part) and i + 1 < len(parts):
                acr = _strip_version("_".join(parts[i + 1:]))
                return _decode(year, parts[:i], acr, part) if acr else None
        acr = _strip_version(m.group(2))
        return _decode(year, [], acr, None) if acr else None
    # 2023: [FACTSHEET_]EDF-2023-<TOPIC-TOKENS>[ _]<[GA_]ACRONYM>
    m = re.match(r"(?:FACTSHEET_)?EDF[-_]2023[-_]+(?P<rest>.+)$", stem, re.I)
    if m:
        topic = re.match(r"(?P<t>[A-Z0-9]+(?:-[A-Z0-9]+)*)[ _]+(?P<r>.+)$", m.group("rest"))
        if not topic:
            return None
        rest, ga = topic.group("r"), None
        g = re.match(r"(\d{9})_(.+)$", rest)
        if g:
            ga, rest = g.group(1), g.group(2)
        acr = _strip_version(rest)
        return _decode(year, topic.group("t").split("-"), acr, ga) if acr else None
    # 2022: <ACRONYM> - Factsheet_EDF22[_0]
    m = re.match(r"(?P<a>.+?)\s*-\s*Factsheet_EDF22", stem, re.I)
    if m:
        acr = _strip_version(m.group("a"))
        return _decode(year, [], acr, None) if acr else None
    # 2021: Factsheet_EDF21_<ACRONYM>
    m = re.match(r"Factsheet_EDF21_\s*(.+)$", stem, re.I)
    if m:
        acr = _strip_version(m.group(1))
        return _decode(year, [], acr, None) if acr else None
    return None


# ------------------------------------------------------------------ the PDF

TRANSIENT = {429, 502, 503, 504}
MAX_PACE = 10.0


def fetch_pdf(http: httpx.Client, url: str, *, attempts: int = 5, sleep=time.sleep,
              pace: dict[str, float] | None = None) -> bytes:
    """One factsheet. The site answers HTTP 429 after about a hundred downloads at one a second
    (measured 17 October 2026: 125 of 284 refused), so a 429 or a 5xx is waited out (the
    Retry-After the site gives, else 10, 20, 40, 80 seconds), the shared `pace` is doubled for
    the rest of the run, and a site that keeps refusing raises RateLimited."""
    for attempt in range(1, attempts + 1):
        r = http.get(url)
        if r.status_code in TRANSIENT:
            if attempt == attempts:
                raise RateLimited(f"HTTP {r.status_code} for {url}", retry_after(r))
            if pace is not None:
                pace["delay"] = min(MAX_PACE, max(pace["delay"], 1.0) * 2)
            sleep(min(300.0, retry_after(r) or 10.0 * 2 ** (attempt - 1)))
            continue
        if r.status_code != 200:
            raise ValueError(f"HTTP {r.status_code}")
        if len(r.content) > MAX_PDF_BYTES:
            raise ValueError("file too large")
        if not r.content.startswith(b"%PDF"):
            raise ValueError("not a PDF")
        return r.content
    raise RateLimited(f"no answer for {url}")      # not reached


_DESCRIPTION = re.compile(r"SHORT\s+DESCRIPTION\s+OF\s+THE", re.I)


@dataclass
class FactsheetText:
    sha256: str
    pages: int
    layout: str          # what the model reads
    plain: str           # what the quote check also accepts


def read_pdf(content: bytes) -> FactsheetText:
    """The text of a factsheet, without its technical description.

    The description of the project follows the label "SHORT DESCRIPTION OF THE PROJECT" on the
    first page; everything from that label to the end of the page is cut. Pages without the label
    (the consortium table) are kept whole.
    """
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(content))
    if len(reader.pages) > MAX_PAGES:
        raise ValueError(f"{len(reader.pages)} pages: not a factsheet")
    layout: list[str] = []
    plain: list[str] = []
    for page in reader.pages:
        for mode, out in (("layout", layout), ("plain", plain)):
            text = page.extract_text(extraction_mode="layout") if mode == "layout" \
                else (page.extract_text() or "")
            text = text or ""
            m = _DESCRIPTION.search(text)
            out.append(text[:m.start()] if m else text)
    return FactsheetText(hashlib.sha256(content).hexdigest(), len(reader.pages),
                         "\n".join(layout), "\n".join(plain))


# ------------------------------------------------------------------ what the model reports

class Entity(BaseModel):
    name: str
    country: str | None
    role: Literal["coordinator", "participant"]
    is_sme: bool | None


class Party(BaseModel):
    name: str | None
    country: str | None


class Factsheet(BaseModel):
    acronym: str | None
    title: str | None
    coordinator: Party | None
    participants: list[Entity]
    eu_contribution: float | None
    total_cost: float | None
    duration_months: int | None


TASK = "edf_factsheet"
PROMPT_VERSION = 1

SYSTEM = (
    "You read the text of one project factsheet of the European Defence Fund and report who takes "
    "part, as fixed facts. Use only the text you are given. If a fact is not stated, return null: "
    "never fill a gap from general knowledge. `acronym` is the short name printed at the top and "
    "`title` the full name printed under it. `participants` lists every entity of the table of the "
    "consortium, the coordinator included, once each, with the name copied exactly as printed "
    "(without the word Coordinator), the country as printed, and role `coordinator` for the entity "
    "marked (Coordinator), `participant` for the others. `coordinator` repeats the coordinator. "
    "`is_sme` is true or false only when the text says so, otherwise null (the factsheets usually "
    "do not). Amounts are plain numbers in euros without separators; `duration_months` is the "
    "number of months. Do not describe the technical content of the project."
)

# Country names as the factsheets print them -> ISO 3166-1 alpha-2.
COUNTRIES = {
    "austria": "AT", "belgium": "BE", "bulgaria": "BG", "croatia": "HR", "cyprus": "CY",
    "czechia": "CZ", "czech republic": "CZ", "denmark": "DK", "estonia": "EE", "finland": "FI",
    "france": "FR", "germany": "DE", "greece": "GR", "hungary": "HU", "ireland": "IE",
    "italy": "IT", "latvia": "LV", "lithuania": "LT", "luxembourg": "LU", "malta": "MT",
    "netherlands": "NL", "the netherlands": "NL", "poland": "PL", "portugal": "PT",
    "romania": "RO", "slovakia": "SK", "slovenia": "SI", "spain": "ES", "sweden": "SE",
    "norway": "NO", "iceland": "IS", "liechtenstein": "LI", "ukraine": "UA",
    "united kingdom": "GB", "switzerland": "CH", "turkey": "TR", "turkiye": "TR",
    "north macedonia": "MK", "serbia": "RS", "moldova": "MD", "albania": "AL",
    "bosnia and herzegovina": "BA", "montenegro": "ME", "georgia": "GE", "canada": "CA",
    "united states": "US", "israel": "IL", "japan": "JP", "south korea": "KR",
}


def country_code(name: str | None) -> str | None:
    if not name:
        return None
    return COUNTRIES.get(re.sub(r"\s+", " ", name.strip().strip(".").casefold()))


def norm(text: str) -> str:
    return re.sub(r"\W+", " ", text.casefold()).strip()


def fold(text: str) -> str:
    """Letters and digits only. The factsheet table breaks and joins words at random: a name wrapped over
    two lines ("PLIROF" / "ORIAS"), a layout that glues words ("STISTECHNOLOGIES"), a PDF that hyphenates
    at a line end. The quote check compares in this form, where all of that is equal."""
    return re.sub(r"\W+", "", text.casefold())


_MIN_FOLD = 4


def _fold_index(text: str) -> tuple[str, list[int]]:
    """fold(text) and, for each of its characters, the position in `text` it came from."""
    chars, where = [], []
    for i, ch in enumerate(text):
        for c in ch.casefold():                 # "ß" folds to two letters: both point at the one character
            if re.match(r"\w", c):
                chars.append(c)
                where.append(i)
    return "".join(chars), where


def _looks_glued(name: str) -> bool:
    """A word of 15 letters or more, or a lower-case letter followed by a capital inside a word
    ("HelzelMesstechnik", "InstalazaSA"): the signs of words the layout ran together. The plain text has
    its own faults ("SAS" printed "SA S"), so a spelling is taken from it only for a name that shows them."""
    return (any(len(re.sub(r"\W", "", t)) >= 15 for t in name.split())
            or re.search(r"[a-zà-ÿ][A-ZÀ-Þ]", name) is not None)


def printed_spelling(name: str, source: str, *, wrapped: bool = False) -> str:
    """The name as `source` (the plain text of the factsheet) prints it, spaces and all, when its letters
    are there; else `name` unchanged.

    The layout text collapses spaces ("UNIVERSITEDULUXEMBOURG", "DINAPOLI") and a model that copies it
    stores a glued name that then becomes an organisation of its own. The plain text keeps the spaces.
    A name that runs over two lines is printed with a line break that may fall inside a word, so such a
    span is used only with `wrapped` (a name the model never gave); and a printed spelling replaces
    `name` only if it has more spaces, so that a model that already repaired the glue is not undone."""
    f = fold(name)
    if len(f) < _MIN_FOLD or not (wrapped or _looks_glued(name)):
        return name
    folded, where = _fold_index(source)
    at = folded.find(f)
    if at < 0:
        return name
    span = source[where[at]:where[at + len(f) - 1] + 1]
    if "\n" in span and not wrapped:
        return name
    printed = re.sub(r"\s+", " ", span).strip()
    return printed if printed.count(" ") > name.count(" ") or wrapped else name


_TABLE_HEADER = re.compile(r"^\s*(?:NAME\s+COUNTRY|OF\s*THE\s*ENTITY\s+COUNTRY)\s*$", re.I)
_TABLE_NOISE = ("SELECTED PROJECTS", "EUROPEAN DEFENCE FUND", "MEMBERS OF THE CONSORTIUM", "MEMBERS OF THE",
                "COUNTRY OF", "OF THE ENTITY", "OF THEENTITY", "AND", "COUNTRY")


def table_entries(layout: str) -> list[tuple[str, str, bool]]:
    """(name as printed, country as printed, marked Coordinator) for each row of the consortium table, read
    from the layout text without a model.

    The table has a name column and a country column; a row is a block of lines between blank lines,
    a name wrapped over two lines is one block, and the country is the last cell of one of its lines.
    Used to check the model's answer (its country for a name; names it left out) and, by
    `recover_missing`, to add the rows the answer lost: a layout this does not recognise gives no rows
    and the check is silent."""
    rows: list[tuple[str, str, bool]] = []
    block: list[str] = []
    in_table = False

    def flush() -> None:
        nonlocal block
        names, country = [], None
        for line in block:
            cells = [c for c in re.split(r"\s{2,}", line.strip()) if c]
            if len(cells) >= 2 and country_code(cells[-1]):
                country = cells[-1]
                cells = cells[:-1]
            names.append(" ".join(cells))
        joined = " ".join(names)
        name = re.sub(r"\s+", " ", re.sub(r"\(coordinator\)", "", joined, flags=re.I)).strip()
        if name and country:
            rows.append((name, country, bool(re.search(r"\(coordinator\)", joined, re.I))))
        block = []

    for line in layout.splitlines():
        st = line.strip()
        if _TABLE_HEADER.match(line):
            flush()
            in_table = True
        elif not in_table:
            continue
        elif not st:
            flush()
        elif any(st.upper().startswith(x) for x in _TABLE_NOISE):
            flush()
        else:
            block.append(line)
    flush()
    return rows


def table_rows(layout: str) -> list[tuple[str, str]]:
    """(name as printed, country as printed) for each row of the consortium table (see `table_entries`)."""
    return [(n, c) for n, c, _ in table_entries(layout)]


def check_names(answer: dict[str, Any], text: FactsheetText) -> tuple[dict[str, Any], dict[str, int]]:
    """Keep only the participants whose name is in the document; count what was dropped or corrected.

    A name must appear in the factsheet text (the layout text or the plain text, since a name
    wrapped over two lines is whole only in the second), or the entity is dropped and counted.
    Duplicates (same name and country) are folded into the first. The coordinator is kept only if
    its name is in the text too. Nothing the model says about an entity not printed in the file
    can reach the database.

    The model could still pair a printed name with the wrong printed country, or leave a row out.
    Both are checked against the table read without a model (`table_rows`): a country that differs
    from the one printed on the name's own row is replaced by it (`country_corrected`), and rows of
    the table the answer never mentions are counted (`missing_from_answer`). A layout the table
    reader does not recognise gives neither.
    """
    haystacks = (fold(text.layout), fold(text.plain))
    table = {fold(n): c for n, c in table_rows(text.layout)}
    dropped = {"not_in_text": 0, "duplicate": 0, "no_country": 0, "country_corrected": 0,
               "missing_from_answer": 0}
    kept: list[dict[str, Any]] = []
    seen: set[tuple[str, str | None]] = set()
    for p in answer.get("participants") or []:
        n = fold(p.get("name") or "")
        if len(n) < _MIN_FOLD or not any(n in h for h in haystacks):
            dropped["not_in_text"] += 1
            continue
        iso = country_code(p.get("country"))
        printed = country_code(table.get(n))
        if printed and printed != iso:
            iso = printed
            dropped["country_corrected"] += 1
        if (n, iso) in seen:
            dropped["duplicate"] += 1
            continue
        seen.add((n, iso))
        if iso is None:
            dropped["no_country"] += 1
        kept.append({**p, "name": printed_spelling(p["name"], text.plain), "country_iso": iso})
    answered = {fold(p["name"]) for p in kept}
    dropped["missing_from_answer"] = sum(1 for n in table if n not in answered)
    if sum(1 for p in kept if p["role"] == "coordinator") > 1:
        # one project has one coordinator: more than one is a misreading, none is believed
        for p in kept:
            if p["role"] == "coordinator":
                p["role"] = "participant"
        dropped["coordinator_doubtful"] = 1
    out = {**answer, "participants": kept}
    coord = answer.get("coordinator") or {}
    if coord.get("name") and not any(fold(coord["name"]) in h for h in haystacks):
        out["coordinator"] = None
    return out, dropped


def recover_missing(participants: list[dict[str, Any]], text: FactsheetText) -> list[dict[str, Any]]:
    """The rows of the consortium table that `participants` does not hold, read without a model: what the
    quote check used to drop for a wrapped or glued name, and what the model left out. Each is a
    participant dict like the model's, marked `recovered`, with the name as the plain text prints it
    (a break inside a word stays a break: the organisation resolver folds spaces). The coordinator mark
    is the table's own. Nothing is invented: a row is taken only if its letters are in the document."""
    have = {fold(p.get("name") or "") for p in participants}
    out: list[dict[str, Any]] = []
    for name, country, is_coordinator in table_entries(text.layout):
        f = fold(name)
        if len(f) < _MIN_FOLD or f in have or not any(f in h for h in (fold(text.layout), fold(text.plain))):
            continue
        iso = country_code(country)
        if iso is None:
            continue
        have.add(f)
        out.append({"name": printed_spelling(name, text.plain, wrapped=True), "country": country,
                    "country_iso": iso, "role": "coordinator" if is_coordinator else "participant",
                    "is_sme": None, "recovered": True})
    if sum(1 for p in participants if p["role"] == "coordinator") + sum(
            1 for p in out if p["role"] == "coordinator") > 1:
        for p in out:                    # one project has one coordinator: a second mark is a misreading
            p["role"] = "participant"
    return out
