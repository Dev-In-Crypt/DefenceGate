"""Derive the defence buyer seed list from names that actually occur.

Why derived rather than typed: the buyer signal matches by normalised name, so
a seed entry is only worth anything if it is spelled the way the source spells
it. Typed from memory, "2 Regionalna Baza Logistyczna" misses the 511 notices
filed as "2. Regionalna Baza Logistyczna". So every name here is a real
spelling, counted, and the rules that put it on the list are written down.

Why rules at all: the buyer signal is strong -- a listed buyer qualifies a
notice on its own, whatever it buys. That makes inclusion a precision decision,
not a completeness one. Measured over the Polish backfill, a loose "anything
military" match finds 171 names and 50,959 notices, and a large share of them
are not defence procurement in any sense a supplier would recognise:

  - military hospitals (SP ZOZ), around 9,000 notices of drugs, food and
    cleaning, procured under healthcare rules;
  - the Military Property Agency, 3,598 notices of estate management;
  - police bodies caught by words like "centrum szkolenia".

Listing those would put a hospital's cleaning contract in the defence slice,
which is the fire-extinguisher failure the classifier has a test against. So
they are excluded, explicitly, and the exclusion is in code a reviewer can
read rather than in someone's judgement on the day.

Included: the ministry and its procurement agencies, logistics bases, military
economic units, military units, military academies and research institutes
working on armament and communications, cyber and military police commands,
naval port commands, and state defence-industry plants, which buy components
and are exactly where a tier-2 supplier wants in.

    python -m dgate.ops.derive_buyers --out seeds/defence_buyers.csv

Every other country (12 October 2026). Poland and Spain have written rules and a
national feed; the other countries have neither, only the names TED has shown us.
For those the names of the organisations we hold are read against a per-language
vocabulary (dgate/buyer_vocab.py) -- ministries of defence, armed forces,
procurement agencies, military units -- with explicit exclusions for military
hospitals, property agencies, civil protection, police and the rest, and one file
per country is written for a person to review:

    python -m dgate.ops.derive_buyers --derived-dir seeds/        # reads the database
    python -m dgate.ops.derive_buyers --derived-dir seeds/ --names-file names.tsv

`names.tsv` is `country<TAB>name<TAB>identifier<TAB>notices`, so a list can be
derived from a read-only export without a database connection. The files are
loaded as a buyer signal by `pipeline.seed_buyers` for rows at or above
`DERIVED_MIN_CONFIDENCE`, or marked `reviewed`.
"""

from __future__ import annotations

import argparse
import collections
import csv
import logging
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from ..normalise import normalise_org_name

log = logging.getLogger("derive_buyers")

def loose(raw: str) -> str:
    """Rule and grouping key. This used to fold ł, ø, ß and đ on top of
    normalise_org_name, which could not; the normaliser now does that itself,
    so the key and the stored name are the same string."""
    return normalise_org_name(raw)


# ------------------------------------------------------------------- Poland

PL_EXCLUDE = [
    ("military_healthcare", r"szpital|zaklad opieki zdrowotnej|\bsp ?zoz\b|spzoz"
                            r"|instytut medyczn|instytut medycyny|krwiodawstw|uzdrowisk"),
    ("property_agency", r"agencja mienia wojskowego"),
    ("police_or_border", r"polic|strazy granicznej|straz graniczna|sluzba ochrony panstwa"),
]

PL_INCLUDE = [
    ("ministry", r"^ministerstwo obrony narodowej$"),
    ("armament_agency", r"^agencja uzbrojenia$"),
    ("support_inspectorate", r"inspektorat wsparcia sil zbrojnych"),
    ("logistics_base", r"\bregionalna baza logistyczna\b"),
    ("economic_unit", r"\bwojskowy oddzial gospodarczy\b"),
    ("military_unit", r"\bjednostka wojskowa\b"),
    ("command", r"^dowodztwo (generalne|operacyjne|garnizonu|wojsk)"
                r"|wojsk obrony terytorialnej"),
    ("cyber_command", r"cyberprzestrzeni sil zbrojnych"),
    ("military_police", r"zandarmeri\w* wojskow"),
    ("intelligence", r"sluzba (kontrwywiadu|wywiadu) wojskowego"),
    ("naval_port_command", r"^komenda portu wojennego"),
    ("academy", r"^wojskowa akademia techniczna|^akademia marynarki wojennej"
                r"|^lotnicza akademia wojskowa|^akademia wojsk ladowych"
                r"|^akademia sztuki wojennej"),
    ("research_institute", r"wojskowy instytut (techniczny uzbrojenia|lacznosci"
                           r"|techniki inzynieryjnej|chemii i radiometrii)"
                           r"|wojskowe centrum geograficzne"),
    # Deliberately absent: Wojskowy Instytut Wydawniczy, the military publishing
    # house. It buys paper and printing, which is not the defence supply chain.
    ("defence_industry", r"^wojskowe zaklady (lotnicze|mechaniczne|lacznosci"
                         r"|elektroniczne|inzynieryjne|uzbrojenia|motoryzacyjne)"),
]


def pl_group(key: str) -> str:
    """The organisation a spelling belongs to.

    Merging spellings is an entity-resolution decision, so the grouping is
    deliberately narrow: a unit number is identity, a trailing city or patron's
    name is decoration. Anything not matched here stays its own organisation.
    """
    m = re.search(r"(\d+) regionalna baza logistyczna", key)
    if m:
        return f"{int(m.group(1))} regionalna baza logistyczna"
    # "35 Krakowski Wojskowy Oddzial Gospodarczy" is the 35th, in Krakow: an
    # adjective between number and type does not make a different unit.
    m = re.search(r"(\d+) (?:\w+ )?wojskowy oddzial gospodarczy", key)
    if m:
        return f"{int(m.group(1))} wojskowy oddzial gospodarczy"
    m = re.search(r"jednostka wojskowa (?:nr )?(\d+)", key)
    if m:
        return f"jednostka wojskowa nr {int(m.group(1))}"
    return re.sub(r" (im|imienia) .*$", "", key)


# -------------------------------------------------------------------- Spain

ES_EXCLUDE = [
    ("police", r"guardia civil|policia"),
    ("military_healthcare", r"hospital"),
    ("property_agency", r"\binvied\b|vivienda infraestructura y equipamiento"),
    ("not_defence", r"seguros de credito"),
]

ES_INCLUDE = [
    ("ministry", r"^ministerio de defensa$|junta de contratacion del ministerio de defensa"),
    ("armament_agency", r"direccion general de armamento|adquisiciones de armamento"),
    ("army_economic_unit", r"(asuntos economicos|economico.?administrativa|intendencia"
                           r"|gestion economica|adquisiciones).*"
                           r"(ejercito|armada|mando|fuerza terrestre|estado mayor de la defensa"
                           r"|cuartel general|base aerea|aerodromo militar|acuartelamiento"
                           r"|parque y centro|unidad militar de emergencias|guardia real"
                           r"|cuarto militar|comandancia gral|sistemas de informacion)"),
    ("maintenance_centre", r"^seccion de asuntos economicos del parque y centro"),
    ("intendance", r"^jefatura de intendencia de asuntos economicos"),
    ("service", r"^armada espanola$|^ejercito de tierra$|^ejercito del aire"),
    ("defence_engineering", r"ingenieria de sistemas para la defensa"),
    ("aerospace_institute", r"instituto nacional de tecnica aeroespacial"),
]


# ------------------------------------------------------------------ shared

@dataclass
class Decision:
    category: str | None     # None = not a defence buyer
    excluded_as: str | None  # set when a rule deliberately kept it out


def decide(name: str, include: list, exclude: list) -> Decision:
    key = loose(name)
    for label, pattern in exclude:
        if re.search(pattern, key):
            return Decision(None, label)
    for label, pattern in include:
        if re.search(pattern, key):
            return Decision(label, None)
    return Decision(None, None)


@dataclass
class SeedRow:
    country: str
    canonical_name: str
    raw_name: str
    category: str
    seen: int


def group_rows(country: str, counts: collections.Counter,
               include: list, exclude: list, grouper) -> tuple[list[SeedRow], dict]:
    """Turn counted raw spellings into seed rows, one canonical name per group."""
    groups: dict[str, list[tuple[str, int, str]]] = collections.defaultdict(list)
    excluded: collections.Counter = collections.Counter()
    for raw, seen in counts.items():
        d = decide(raw, include, exclude)
        # Count an exclusion only where it changed the outcome. Every civilian
        # hospital matches the healthcare rule too, and reporting those as
        # "excluded" overstated what the rule was keeping out by twenty times.
        if d.excluded_as and decide(raw, include, []).category:
            excluded[d.excluded_as] += seen
        if not d.category:
            continue
        groups[grouper(loose(raw))].append((raw, seen, d.category))

    rows: list[SeedRow] = []
    for spellings in groups.values():
        # The most used spelling names the organisation; ties broken by the
        # shorter name, which is the one without a city or patron appended.
        spellings.sort(key=lambda s: (-s[1], len(s[0])))
        canonical = spellings[0][0].strip().rstrip(".")
        for raw, seen, category in spellings:
            rows.append(SeedRow(country, canonical, raw.strip(), category, seen))
    rows.sort(key=lambda r: (r.country, r.canonical_name, -r.seen))
    return rows, dict(excluded)


def pl_counts(paths: Iterable[Path]) -> collections.Counter:
    from ..sources import atlas_pl

    counts: collections.Counter = collections.Counter()
    for path in paths:
        for row in atlas_pl.read_rows(path, batch_size=50_000, columns=["buyer"]):
            name = (row.get("buyer") or "").strip()
            if name:
                counts[name] += 1
    return counts


def es_counts(conn) -> collections.Counter:
    """Spanish contracting bodies as PLACSP has actually named them to us.

    The plan points at OrganosContratacion.xlsx, which is not in the source
    bundle. The spellings that matter are the ones our feed delivers anyway, and
    those are in organisation_alias.
    """
    rows = conn.execute(
        """SELECT a.raw_name, count(*) AS n
             FROM organisation_alias a JOIN organisation o ON o.id = a.organisation_id
            WHERE o.country = 'ES' GROUP BY a.raw_name"""
    ).fetchall()
    return collections.Counter({r["raw_name"]: r["n"] for r in rows})


def carried_over(derived: list[SeedRow]) -> list[SeedRow]:
    """Every entry of the hand-curated list that derivation did not produce.

    Taken verbatim from DEFENCE_BUYERS, so deriving Poland and Spain can never
    quietly drop a buyer someone chose on purpose -- including the countries
    only TED covers, where there is no national feed to derive from.
    """
    from ..pipeline import DEFENCE_BUYERS

    have = {(r.country, loose(r.raw_name)) for r in derived}
    have |= {(r.country, loose(r.canonical_name)) for r in derived}
    return [SeedRow(country, name, name, "curated", 0)
            for country, name in DEFENCE_BUYERS
            if (country, loose(name)) not in have]


def write_csv(rows: list[SeedRow], out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["country", "canonical_name", "raw_name", "category", "seen"])
        for r in rows:
            w.writerow([r.country, r.canonical_name, r.raw_name, r.category, r.seen])


# Countries with their own rules above; the vocabulary does not second-guess them.
OWN_RULES = {"PL", "ES"}
DERIVED_COLUMNS = ["country", "name", "identifier", "reason", "confidence", "reviewed"]


@dataclass
class Proposal:
    country: str
    name: str
    identifier: str
    reason: str
    confidence: float
    notices: int = 0


def vocabulary_proposals(rows: Iterable[tuple[str, str, str, int]]) -> list[Proposal]:
    """Defence bodies among (country, name, identifier, notices) rows.

    One proposal per organisation; the strongest rule that matches names it. A
    name an exclusion kept out is not proposed at all.
    """
    from ..buyer_vocab import defence_body

    out: list[Proposal] = []
    for country, name, identifier, notices in rows:
        if not country or country.upper() in OWN_RULES or not name:
            continue
        body = defence_body(name, country)
        if body.label:
            out.append(Proposal(country.upper(), name, identifier or "", body.label,
                                body.confidence, notices))
    out.sort(key=lambda p: (p.country, -p.confidence, p.name))
    return out


def write_derived(proposals: list[Proposal], directory: Path) -> dict[str, int]:
    """One reviewable file per country. A file that exists keeps its human
    decisions: a row already marked reviewed or rejected is carried over as it was."""
    by_country: dict[str, list[Proposal]] = collections.defaultdict(list)
    for p in proposals:
        by_country[p.country].append(p)
    directory.mkdir(parents=True, exist_ok=True)
    written: dict[str, int] = {}
    for country, items in sorted(by_country.items()):
        path = directory / f"defence_buyers_derived_{country}.csv"
        decided: dict[str, str] = {}
        if path.exists():
            with path.open(encoding="utf-8", newline="") as fh:
                for row in csv.DictReader(fh):
                    if (row.get("reviewed") or "").strip().lower() not in ("", "false"):
                        decided[row["name"]] = row["reviewed"]
        with path.open("w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(DERIVED_COLUMNS)
            for p in items:
                w.writerow([p.country, p.name, p.identifier, p.reason, f"{p.confidence:.2f}",
                            decided.get(p.name, "false")])
        written[country] = len(items)
    return written


def read_names_file(path: Path) -> list[tuple[str, str, str, int]]:
    rows = []
    with path.open(encoding="utf-8", newline="") as fh:
        for rec in csv.reader(fh, delimiter=chr(9)):
            if len(rec) < 2:
                continue
            rows.append((rec[0].strip(), rec[1].strip(),
                         rec[2].strip() if len(rec) > 2 else "",
                         int(rec[3]) if len(rec) > 3 and rec[3].strip().isdigit() else 0))
    return rows


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    p = argparse.ArgumentParser(prog="derive-buyers")
    p.add_argument("--out", type=Path, default=None,
                   help="the Poland and Spain seed file (needs the Atlas files and a database)")
    p.add_argument("--atlas-dir", type=Path, default=None)
    p.add_argument("--derived-dir", type=Path, default=None,
                   help="write one defence_buyers_derived_<CC>.csv per other country here")
    p.add_argument("--names-file", type=Path, default=None,
                   help="country<TAB>name<TAB>identifier<TAB>notices, instead of the database")
    a = p.parse_args(argv)
    if a.out is None and a.derived_dir is None:
        p.error("give --out, --derived-dir, or both")

    from .. import db
    from ..config import settings

    if a.derived_dir is not None:
        if a.names_file is not None:
            names = read_names_file(a.names_file)
        else:
            with db.connect(settings().dsn) as conn:
                names = [(r["country"], r["canonical_name"], r["national_reg_no"] or "", r["n"])
                         for r in conn.execute(
                             """SELECT g.country, g.canonical_name, g.national_reg_no,
                                       count(o.id) AS n
                                  FROM organisation g
                                  LEFT JOIN opportunity o ON o.buyer_org_id = g.id
                                 WHERE g.merged_into IS NULL
                                 GROUP BY g.id""").fetchall()]
        proposals = vocabulary_proposals(names)
        written = write_derived(proposals, a.derived_dir)
        by_conf = collections.Counter(round(p.confidence, 2) for p in proposals)
        print(f"derived: {len(proposals)} proposals in {len(written)} countries "
              f"({len(names)} organisations read); by confidence: {dict(sorted(by_conf.items()))}")
        for country, n in written.items():
            print(f"  {country}: {n}")
        if a.out is None:
            return 0

    from ..sources import atlas_pl

    atlas_dir = a.atlas_dir or Path(settings().atlas_dir)
    pl_rows, pl_out = group_rows(
        "PL", pl_counts(atlas_dir / f for f in atlas_pl.YEAR_FILES.values()),
        PL_INCLUDE, PL_EXCLUDE, pl_group)
    with db.connect(settings().dsn) as conn:
        es_rows, es_out = group_rows("ES", es_counts(conn), ES_INCLUDE, ES_EXCLUDE,
                                     lambda key: key)

    rows = pl_rows + es_rows
    rows += carried_over(rows)
    write_csv(rows, a.out)

    for country, rs, out in (("PL", pl_rows, pl_out), ("ES", es_rows, es_out)):
        orgs = {r.canonical_name for r in rs}
        unit = "notices" if country == "PL" else "alias rows"
        print(f"{country}: {len(orgs)} organisations, {len(rs)} spellings, "
              f"{sum(r.seen for r in rs)} {unit}; kept out by rule: {out}")
    print(f"wrote {len(rows)} rows to {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
