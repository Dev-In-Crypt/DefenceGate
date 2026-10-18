"""Layer 2b, the supplier map: who won the defence-relevant result notices of TED (WP-37).

The pipeline rule, as everywhere: land the raw payload, normalise, archive.

    land       the winner fields of each result notice, as TED returns them, in the raw store
               (source `ted_awards`), with the entries of natural persons blanked first
    normalise  `read_award()`: one `Winner` per winning organisation, natural persons and
               unidentifiable entries left out and counted
    archive    one `award` row per (notice, organisation), the organisation found by the
               resolution cascade of WP-26 (`dgate.resolution.resolve`; nothing else decides who
               a supplier is), and one `award_notice` row per notice read, so a second run asks
               TED about nothing it has already read

What the notices state and this module keeps: the winner's name, country and registration number
as the buyer published them. It keeps no contact, no person, no technical content. A winner that is
a natural person (a sole trader under their own name) is not a supplier profile: it is skipped and
counted, and its name never reaches the database or the raw store (see `is_natural_person`).

Values are not kept here: a notice's value is on the `opportunity` row, and a profile shows it only
when the notice names one winner (a value shared by several winners belongs to none of them).
"""

from __future__ import annotations

import copy
import logging
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from typing import Any

import httpx
import psycopg

from . import db
from .classify import CORE_SQL, military_cpv_codes
from .config import settings
from .normalise import _country2, normalise_identifier
from .rawstore import BundleWriter, build_store, storage_key
from .resolution import Resolution, resolve
from .resolution.cascade import add_review
from .resolution.names import key_of
from .sources import USER_AGENT, new_client, ted

log = logging.getLogger(__name__)

SOURCE_CODE = "ted_awards"
# The notice types that carry winners (TED `notice-type` can-standard, can-social, can-desg and the
# voluntary ex ante notices), as the `notice_subtype` column stores them; measured 18 October 2026.
AWARD_SUBTYPES = ("29", "30", "31", "33", "34", "35", "36", "37", "E1", "E2", "E3", "E4", "E5", "E6")
# eForms is mandatory from 25 October 2023 and optional from 25 October 2022; before that the API
# states no winner at all (measured: 735 of 10,894 result notices of 2023 name one, 9,859 of 11,795 of
# 2024). Older notices are not asked for.
DEFAULT_SINCE = date(2023, 1, 1)
PERSON_PLACEHOLDER = "[natural person]"

# ----------------------------------------------------------------------------- natural persons
#
# A notice does not say whether a winner is a person. The rule is deliberately on the side of
# leaving a company out: a supplier we miss is a gap in coverage, a person we publish is a harm.
#
#   marker      a legal form or a business word anywhere in the name: a legal entity, kept
#   no marker   two to four capitalised words ("Radek Nečas"), or a SURNAME in capitals with a
#               first name ("DUPONT Jean"), or a Polish trading name that ends in a person's two
#               names ("P.P.H.U. Krismark Krystyna Łopuszańska"): a natural person, skipped
#   a Cyrillic sole-trader form (ET, FOP, IP): skipped
# Words are compared lower-case, without accents and dots; a run of single letters is one word
# ("S. A." is "sa"). Measured on the 5,997 distinct (name, country) pairs of the core scope on
# 18 October 2026: docs/design/SUPPLIER_MAP_FEASIBILITY.md.

_LEGAL_FORMS = frozenset("""
    gmbh mbh ag kg ohg gbr ug se sa sas sasu sarl snc eurl sl slu srl spa bv nv cv vof bvba sprl cvba
    ltd limited llc llp lp inc plc corp co company companies compagnie compania companhia kompanie
    oy oyj ab aps as asa uab sia ou ood eood doo dd ad kft zrt nyrt rt zoo oo sp spolka spółka spoldzielnia
    spółdzielnia sro akciova spolocnost aktiebolag osakeyhtio osauhing aktsiaselts tulundusuhistu
    aktiengesellschaft gesellschaft genossenschaft verein gie eig ev scpa scarl lda unipessoal
    societe sociedad sociedade societa entreprise entreprises etablissements etablissement ets
    groupement consortium konsorcjum
    ооо оод еоод ад еад дздд дззд тов прат пат ао зао
""".split())
_BUSINESS = frozenset("""
    group groupe grupo gruppe holding holdings industries industrie industria industrial systems system
    systeme sistemas technologies technology technologie technik technical tech services service
    solutions solution defence defense defensa engineering engineers logistics logistik international
    internacional trading trade consulting consultants associates partners partnerschaft institute institut
    instytut university universität universidad universite università uniwersytet hospital ministry
    agency agentur association asociacion fundacion foundation stiftung cooperative cooperativa
    aerospace aeronautics electronics elektronik electric optics optical motors vehicles fahrzeugbau
    shipyard shipyards werft werke werk works factory fabrik pinselfabrik laboratories laboratoire
    laboratorium labor pharma medical medica med bank insurance telecom telecommunications energy power bau
    construction construcciones transport transportes security safety armaments arms ammunition munition
    munitions dynamics helicopters aircraft aviation marine naval maritime space satellite robotics
    instruments precision machinery metal metall steel plastics chemicals textile apparel uniforms
    clothing sports outdoor food catering cleaning printing publishing publications software digital data
    cyber studio design media advisory research development centre center centrum zentrum bureau buro office
    toimisto belgium belgique belgie france deutschland germany eesti estonia polska poland polen
    nederland netherlands espana spain italia italy europe europa european sverige sweden norge norway
    danmark denmark suomi finland latvija lietuva romania bulgaria czech ceska slovakia slovenija
    hrvatska hungary magyarorszag uk usa
    corporation corporations incorporated akcyjna ograniczona odpowiedzialnoscia komandytowa jawna
    partnerska korlatolt felelossegu tarsasag reszvenytarsasag nyilvanosan mukodo zartkoruen sabiedriba
    ierobezotu atbildibu elektronische electronic electronique computers computer facilities ordnance
    propellers autonomy advanced instrumentation ingenieure ingenieur ingenieurs architektur architects
    architekten schlauchboot izba politechnika uniwersytet universitaet ustav univerza fakulteta
    obedinenie sdruzeni sdruzenie ay ministerstwo ministerium ministere ministerio ministero ministerie
    ministerija
""".split())
_CORPORATE = _LEGAL_FORMS | _BUSINESS
_SOLE_TRADER = frozenset("ет фоп ип".split())
# forms that are a person trading, by country: PL spółka cywilna, DE eingetragener Kaufmann, RO PFA, FR EIRL
_SOLE_TRADER_BY_COUNTRY = {"PL": frozenset({"sc"}), "DE": frozenset({"ek"}), "RO": frozenset({"pfa"}),
                           "FR": frozenset({"eirl"})}
# letters NFKD does not decompose: the fold that makes "Spółka" and "spolka" one word
_FOLD = {ord("ł"): "l", ord("ø"): "o", ord("đ"): "d", ord("ß"): "ss", ord("ı"): "i", ord("ð"): "d",
         ord("æ"): "ae", ord("œ"): "oe"}
_PL_TRADING = re.compile(r"\b(?:PPHU|PHU|PUH|FHU|PPUH|PHPU|ZPUH)\b")
_PL_TRAILING_PERSON = re.compile(r",\s+[A-ZŁŚŻŹĆ][a-ząćęłńóśźż]+\s+[A-ZŁŚŻŹĆ][a-ząćęłńóśźż\-]+$")
# Poland: a trading name without a legal form is a sole proprietorship, i.e. a natural person
_PL_TRADE_WORDS = frozenset("""przedsiebiorstwo firma zaklad uslugi uslugowe handlowo produkcyjno agencja biuro
    pphu phu puh fhu ppuh phpu zphu zp mk pw ph""".split())
_ADDRESS = re.compile(r"\bul\.|\b\d{2}-\d{3}\b")
_PL_GIVEN = frozenset("""piotr andrzej jan krzysztof tomasz pawel michal marcin jacek grzegorz rafal marek adam lukasz
    waldemar kazimierz robert zbigniew stanislaw mariusz dariusz artur arkadiusz bartlomiej dawid krystyna anna
    iwona jadwiga malgorzata katarzyna agnieszka barbara ewa maria joanna magdalena monika teresa elzbieta zofia
    danuta halina renata beata aleksandra dorota wojciech jerzy henryk jozef ryszard slawomir tadeusz janusz
    roman miroslaw leszek edward bogdan damian kamil maciej przemyslaw sebastian jaroslaw radoslaw daniel
    mateusz karol szymon filip kacper patryk dominik norbert zdzislaw wladyslaw bernard cezary czeslaw
    ireneusz kornel lech marian mieczyslaw natalia stefan walenty zygmunt hanna ilona jolanta wanda lucyna
    alicja marzena urszula grazyna bozena sylwia paulina justyna karolina weronika wioletta ewelina kinga""".split())


def _words(name: str) -> list[str]:
    folded = unicodedata.normalize("NFKD", name.replace(".", "").replace("/", ""))
    folded = "".join(c for c in folded if not unicodedata.combining(c)).lower().translate(_FOLD)
    merged: list[str] = []
    run = ""                      # a run of single letters is one word: "s a" is "sa", "d o o" is "doo"
    for w in re.findall(r"[^\W_]+", folded) + [""]:
        if len(w) == 1:
            run += w
            continue
        if run:
            merged.append(run)
            run = ""
        if w:
            merged.append(w)
    return merged


def _title(tok: str) -> bool:
    parts = tok.split("-")
    return all(len(p) >= 2 and p[0].isupper() and p[1:].islower() for p in parts)


def person_reason(name: str, identifier: str | None = None, country: str | None = None) -> str | None:
    """Why this winner is not published as a supplier, or None when it is a legal entity."""
    raw = (name or "").strip()
    if not raw or raw == PERSON_PLACEHOLDER or "natural person" in raw.lower() or "osoba fizyczna" in raw.lower():
        return "person_marked"
    words = set(_words(raw))
    if words & _SOLE_TRADER or words & _SOLE_TRADER_BY_COUNTRY.get(country or "", frozenset()):
        return "person_in_trading_name"
    has_marker = bool(words & _CORPORATE)
    legal_form = bool(words & _LEGAL_FORMS)
    if not legal_form and _ADDRESS.search(raw):
        return "person_in_trading_name"            # a street or a postal code in a name: a sole trader's
    tokens = [t.strip(",;()\"'") for t in raw.replace(".", " ").split()]
    tokens = [t for t in tokens if t]
    if _PL_TRAILING_PERSON.search(raw) and not has_marker:
        return "person_in_trading_name"
    if _PL_TRADING.search(raw.replace(".", "")) and len(tokens) >= 3 and all(_title(t) for t in tokens[-2:]):
        return "person_in_trading_name"
    if country == "PL" and not legal_form:
        first = _words(tokens[0])[:1] if tokens else []
        pair = [_words(t)[:1] for t in tokens[-2:]]
        if (words & _PL_TRADE_WORDS
                or (len(tokens) >= 3 and pair[0] and pair[0][0] in _PL_GIVEN and len(tokens[-1]) >= 3)
                or (len(tokens) >= 3 and first and first[0] in _PL_GIVEN
                     and (_title(tokens[1]) or tokens[1].isupper()))):
            return "person_in_trading_name"
    if has_marker or not 2 <= len(tokens) <= 4:
        return None
    titled = [t for t in tokens if _title(t)]
    caps = [t for t in tokens if len(t) >= 2 and t.isalpha() and t.isupper()]
    initials = [t for t in tokens if len(t) == 1 and t.isupper()]
    if len(titled) + len(initials) == len(tokens) and len(titled) >= 2:
        return "person_name"                       # Radek Nečas, Jean-Pierre Martin, Markus F. Strieder
    if titled and caps and len(titled) + len(caps) + len(initials) == len(tokens):
        return "person_name"                       # DUPONT Jean, Jan NOVAK
    return None


def is_natural_person(name: str, identifier: str | None = None, country: str | None = None) -> bool:
    return person_reason(name, identifier, country) is not None


# ----------------------------------------------------------------------------- reading a record

@dataclass
class Winner:
    name: str
    country: str | None
    identifier: str | None


@dataclass
class Read:
    winners: list[Winner] = field(default_factory=list)
    counts: Counter = field(default_factory=Counter)
    redacted: dict[str, Any] = field(default_factory=dict)
    winners_seen: int = 0               # distinct winning organisations the notice names, kept or not


def _lists(value: Any) -> list[list[str]]:
    """A multilingual block {lang: [..]} as its lists; a plain list as one list."""
    if isinstance(value, dict):
        return [[str(x).strip() for x in (v or [])] for v in value.values()]
    if isinstance(value, (list, tuple)):
        return [[str(x).strip() for x in value]]
    if value in (None, ""):
        return []
    return [[str(value).strip()]]


def _longest(value: Any) -> list[str]:
    ls = _lists(value)
    return max(ls, key=len) if ls else []


def _flat(value: Any) -> list[str]:
    return [x for lst in _lists(value) for x in lst]


def read_award(rec: dict[str, Any]) -> Read:
    """The winners of one result notice, as TED's winner fields state them.

    `organisation-*-tenderer` are parallel lists, one entry per organisation of the tendering parties
    (they agree on a legal form and a country for 99.0 % of 1,226 pairs measured on 18 October 2026),
    and `winner-name` says which of them won. `winner-country` and `winner-identifier` are not read:
    in notices with several winners they are not in the order of `winner-name` (81 % agreement).
    A country or a number is taken from its list only when the list has one entry per organisation,
    or the notice has one organisation, or all entries are equal (countries only).
    """
    out = Read()
    won = set(_flat(rec.get("winner-name")))
    names = _longest(rec.get("organisation-name-tenderer"))
    if not won:
        out.counts["no_winner_name"] += 1
        return out
    if not names:
        out.counts["no_tenderer_block"] += 1
        return out
    countries = [_country2(c) for c in _flat(rec.get("organisation-country-tenderer"))]
    idents = _flat(rec.get("organisation-identifier-tenderer"))
    n = len(names)
    one_country = countries[0] if countries and len(set(countries)) == 1 else None
    blank: set[int] = set()
    seen: set[tuple[str, str | None]] = set()
    for i, name in enumerate(names):
        country = countries[i] if len(countries) == n else one_country
        ident = idents[i] if len(idents) == n else (idents[0] if n == 1 and idents else None)
        reason = person_reason(name, ident, country)
        if reason:
            blank.add(i)
        if name not in won or (name, country) in seen:
            continue
        seen.add((name, country))
        out.winners_seen += 1
        if reason:
            out.counts["skipped_" + reason] += 1
            out.counts["skipped_person"] += 1
        elif not country:
            out.counts["skipped_no_country"] += 1
        else:
            out.winners.append(Winner(name, country, ident or None))
    if not out.winners_seen:
        out.counts["winner_not_among_tenderers"] += 1
    out.redacted = _redact(rec, names, blank, len(idents) == n)
    return out


def _redact(rec: dict[str, Any], names: list[str], blank: set[int], ids_aligned: bool) -> dict[str, Any]:
    """The record with the names (and numbers) of natural persons blanked, positions kept."""
    red = copy.deepcopy(rec)
    if not blank:
        return red
    bad = {names[i] for i in blank}
    for key in ("winner-name", "organisation-name-tenderer"):
        v = red.get(key)
        if isinstance(v, dict):
            red[key] = {lang: [PERSON_PLACEHOLDER if x in bad else x for x in (lst or [])] for lang, lst in v.items()}
        elif isinstance(v, list):
            red[key] = [PERSON_PLACEHOLDER if x in bad else x for x in v]
    ids = red.get("organisation-identifier-tenderer")
    if isinstance(ids, list):
        red["organisation-identifier-tenderer"] = (
            ["" if i in blank else x for i, x in enumerate(ids)] if ids_aligned else [])
    red.pop("winner-identifier", None)
    return red


# ----------------------------------------------------------------------------- the loader

def _main_cpv(codes: list[str] | None) -> str | None:
    """The code a profile files the notice under: the first military code, else the first code."""
    mil = military_cpv_codes(codes)
    first = next((c for c in (codes or []) if c), None)
    return (mil[0] if mil else first) or None


def _attach_reg(conn: psycopg.Connection, org_id: int, ident: str | None, country: str) -> None:
    """Give an organisation the registration number the notice states, if it has none and nobody
    else of the country holds that number. The cascade's stage 1 finds it from then on."""
    reg = normalise_identifier(ident, country) if ident else None
    if not reg:
        return
    conn.execute(
        """UPDATE organisation
              SET national_reg_no = %s, identifier_method = 'identifier', identifier_confidence = %s
            WHERE id = %s AND national_reg_no IS NULL
              AND NOT EXISTS (SELECT 1 FROM organisation x WHERE x.country = %s AND x.national_reg_no = %s)""",
        (reg, db.CONF_IDENTIFIER_ATTACHED, org_id, country, reg))


def _kind(number: str) -> tuple[str, int | str]:
    """What sort of number this looks like: its length when it is all digits (a German VAT number is nine
    digits), its letter prefix otherwise (HRB, FN, ATU)."""
    if number.isdigit():
        return ("D", len(number.lstrip("0")))
    m = re.match(r"[A-Z]+", number)
    return ("A", m.group(0) if m else "")


def _distance(a: str, b: str) -> int:
    row = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        prev, row[0] = row[0], i
        for j, cb in enumerate(b, 1):
            prev, row[j] = row[j], min(row[j] + 1, row[j - 1] + 1, prev + (ca != cb))
    return row[-1]


def numbers_conflict(a: str, b: str) -> bool:
    """Two registration numbers that cannot be one body's. Notices write one company's number as a VAT
    number or as a register number, with or without a leading zero or a prefix, and with typos: in the
    replay of the real notices (18 October 2026) a plain inequality split 225 organisations, and most of
    the 40 read were such spellings. So they conflict only when they are of one kind (the same count of
    digits, or the same letter prefix), neither is the start of the other, and they differ by at least two
    characters."""
    za, zb = a.lstrip("0"), b.lstrip("0")
    if za == zb or za.startswith(zb) or zb.startswith(za):
        return False
    return _kind(a) == _kind(b) and _distance(a, b) >= 2


def _namesake_guard(conn: psycopg.Connection, res: Resolution, w: Winner) -> Resolution:
    """A match by name on a body that holds another registration number is a namesake, not this
    supplier ("Mueller Bau GmbH" exists in every German town): the number the notice states makes a
    body of its own, and the pair goes to the review queue. The cascade (stage 2) decides on the name
    alone, which is right for a buyer a notice names without a number and wrong for a supplier that
    states one."""
    reg = normalise_identifier(w.identifier, w.country) if w.identifier else None
    if not reg or res.org_id is None or res.method in ("pic", "national_id", "vat"):
        return res
    held = conn.execute("SELECT national_reg_no FROM organisation WHERE id = %s",
                        (res.org_id,)).fetchone()["national_reg_no"]
    if not held or not numbers_conflict(held, reg):
        return res
    if conn.execute("SELECT 1 FROM organisation WHERE country = %s AND national_reg_no = %s",
                    (w.country, reg)).fetchone():
        return res          # the number sits on a body whose name shares nothing with this one: a person decides
    key, _ = key_of(w.name)
    other = db._new_organisation(conn, key, w.country or "", reg)
    conn.execute("UPDATE organisation SET display_name = %s WHERE id = %s", (w.name[:300], other))
    add_review(conn, res.org_id, other, relation="same_name_other_id", method="id_conflict", confidence=0.50,
               evidence={"key": key, "country": w.country, "numbers": [held, reg]})
    return Resolution(other, "national_id_new", db.CONF_IDENTIFIER_ATTACHED, created=True)


def store_notice(conn: psycopg.Connection, src_id: int, opp: dict[str, Any], read: Read,
                 raw_key: str | None, c: Counter) -> None:
    """Archive one notice's winners. Idempotent: an award row exists once per (notice, organisation)."""
    kept = 0
    for w in read.winners:
        res = resolve(conn, w.name, w.country, {"reg": w.identifier},
                      {"source_id": src_id, "candidates": False})
        if res.org_id is None:
            c["skipped_unresolved"] += 1
            continue
        res = _namesake_guard(conn, res, w)
        _attach_reg(conn, res.org_id, w.identifier, w.country)
        row = conn.execute(
            """INSERT INTO award (opportunity_id, organisation_id, supplier_country, name_as_stated,
                                  identifier_as_stated, winners_in_notice, cpv_main,
                                  resolution_method, resolution_confidence)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT (opportunity_id, organisation_id) DO NOTHING RETURNING id""",
            (opp["id"], res.org_id, w.country, w.name[:300], (w.identifier or "")[:60] or None,
             read.winners_seen, _main_cpv(opp["cpv_codes"]), res.method, round(res.confidence, 2))).fetchone()
        c["awards_new"] += row is not None
        c["organisations_new"] += res.created
        c["by_" + res.method] += 1
        kept += 1
    status = "loaded" if kept else ("no_supplier" if read.winners_seen else "no_winner_data")
    conn.execute(
        """INSERT INTO award_notice (opportunity_id, raw_key, winners_seen, winners_kept, skipped_person,
                                     skipped_no_country, status)
           VALUES (%s, %s, %s, %s, %s, %s, %s)
           ON CONFLICT (opportunity_id) DO NOTHING""",
        (opp["id"], raw_key, read.winners_seen, kept, read.counts["skipped_person"],
         read.counts["skipped_no_country"], status))
    c["notices_" + status] += 1
    for k, v in read.counts.items():
        c[k] += v


def candidates(conn: psycopg.Connection, src_id: int, since: date, limit: int | None) -> list[dict[str, Any]]:
    """TED result notices of the core scope that no run has read yet, newest first."""
    return conn.execute(
        f"""SELECT o.id, o.native_id, o.cpv_codes FROM opportunity o
             WHERE o.source_id = %s AND o.is_defence AND NOT o.suppressed AND {CORE_SQL}
               AND o.notice_subtype = ANY(%s) AND o.published_at >= %s
               AND NOT EXISTS (SELECT 1 FROM award_notice n WHERE n.opportunity_id = o.id)
             ORDER BY o.published_at DESC, o.id LIMIT %s""",
        (src_id, list(AWARD_SUBTYPES), since, limit or 1_000_000)).fetchall()


def run_awards(*, since: date = DEFAULT_SINCE, limit: int | None = None,
               client: httpx.Client | None = None, pause: float = 1.0,
               sleep=None) -> Counter:
    """Read the winners of the result notices we hold and have not read. One request a second."""
    import time

    nap = sleep or time.sleep
    cfg = settings()
    c: Counter = Counter()
    owns = client is None
    client = client or new_client(headers={"User-Agent": USER_AGENT})
    try:
        with db.connect(cfg.dsn) as conn, BundleWriter(build_store(), SOURCE_CODE) as writer:
            src_id = db.source_id(conn, SOURCE_CODE)
            ted_id = db.source_id(conn, "ted")
            run_id = db.start_run(conn, SOURCE_CODE, None)
            try:
                load_awards(conn, client, writer, src_id, ted_id, since=since, limit=limit,
                            counters=c, pause=pause, sleep=nap)
                writer.drain()
                db.finish_run(conn, run_id, fetched=c["fetched"], new=c["awards_new"], changed=0,
                              detail=dict(c))
            except Exception as exc:
                conn.rollback()
                db.finish_run(conn, run_id, fetched=c["fetched"], new=c["awards_new"], changed=0,
                              status="failed", error=str(exc)[:500])
                raise
    finally:
        if owns:
            client.close()
    log.info("%s done: %s", SOURCE_CODE, dict(c))
    return c


def load_awards(conn: psycopg.Connection, client: httpx.Client, writer: BundleWriter, src_id: int,
                ted_id: int, *, since: date, limit: int | None, counters: Counter,
                pause: float = 1.0, sleep=None) -> None:
    import time

    nap = sleep or time.sleep
    known = {r["content_hash"] for r in conn.execute(
        "SELECT content_hash FROM raw_ingest WHERE source_id = %s", (src_id,)).fetchall()}
    todo = candidates(conn, src_id=ted_id, since=since, limit=limit)
    counters["candidates"] = len(todo)
    for i in range(0, len(todo), ted.AWARD_BATCH):
        batch = [o for o in todo[i:i + ted.AWARD_BATCH] if ted.PUBLICATION_NUMBER.fullmatch(o["native_id"])]
        counters["skipped_bad_number"] += len(todo[i:i + ted.AWARD_BATCH]) - len(batch)
        if i:
            nap(pause)
        got = ted.fetch_by_numbers([o["native_id"] for o in batch], client=client)
        for opp in batch:
            rec = got.get(opp["native_id"])
            if rec is None:
                counters["not_returned"] += 1       # not marked read: the next run asks again
                continue
            counters["fetched"] += 1
            read = read_award(rec)
            raw_key = None
            if read.redacted:
                h = ted.content_hash(read.redacted)
                raw_key = writer.put(storage_key(SOURCE_CODE, opp["native_id"], content_hash=h), read.redacted)
                if h not in known:
                    db.record_raw(conn, src_id, opp["native_id"], h, raw_key)
                    known.add(h)
            store_notice(conn, src_id, opp, read, raw_key, counters)
        writer.drain()        # the bundle is written before the rows that point into it are committed
        conn.commit()
