"""Layer 2, networks: who took part in which funded project (WP-26).

Three jobs, all idempotent and all following the pipeline rule: land the raw payload, then
normalise, then archive.

    run_cordis()     CORDIS through its SPARQL service: organisations, projects, participations
    run_edf()        EDF factsheets: crawl the results pages, read each PDF, ask the model (strict
                     schema, quote check), resolve the participants
    snapshot_consortia()   the monthly composition snapshot and the `consortium.changed` event

Organisations are resolved by `dgate.resolution` (PIC first, then alias, then exact name; trigram
candidates go to the review queue and are never merged). A participation stores how its
organisation was reached. Nothing is deleted: a participant a later run no longer finds is marked
inactive, so a change of composition stays visible.
"""

from __future__ import annotations

import logging
from collections import Counter
from datetime import date
from typing import Any

import httpx
import psycopg
from psycopg.types.json import Jsonb

from . import db, individuals, llm
from .classify import DEFENCE_PROGRAMMES
from .config import settings
from .rawstore import BundleWriter, build_store, storage_key
from .resolution import resolve
from .resolution.cascade import propose_candidates
from .resolution.names import key_of
from .sources import USER_AGENT, RateLimited, cordis, ted
from .sources import edf_factsheets as edf

log = logging.getLogger(__name__)

ROLE_RANK = {"coordinator": 0, "participant": 1, "partner": 2, "associated_partner": 3,
             "international_partner": 4, "third_party": 5}
COMPLETE = 0.995         # a pass that read less of the service's own count than this has failed


def _better_role(a: str, b: str) -> str:
    return a if ROLE_RANK.get(a, 9) <= ROLE_RANK.get(b, 9) else b


def _land(conn: psycopg.Connection, writer: BundleWriter, src_id: int, code: str,
          known: set[str], payload: dict[str, Any], native_id: str) -> bool:
    """Land a payload unless this exact content has been landed before. True when written."""
    h = ted.content_hash(payload)
    if h in known:
        return False
    key = writer.put(storage_key(code, native_id, content_hash=h), payload)
    db.record_raw(conn, src_id, native_id, h, key)
    known.add(h)
    return True


def _checkpoint(conn: psycopg.Connection, writer: BundleWriter, run_id: int | None,
                c: Counter) -> None:
    """Drain the writer before the commit, as the other ingests do: no committed raw_ingest row may
    point at an object that was never written."""
    writer.drain()
    if run_id is not None:
        db.record_progress(conn, run_id, fetched=c["fetched"], new=c["new"], changed=c["changed"])
    conn.commit()


def _same(a: Any, b: Any) -> bool:
    if a is None or b is None:
        return a is None and b is None
    try:
        return round(float(a), 2) == round(float(b), 2)
    except (TypeError, ValueError):
        return a == b


# ================================================================== CORDIS

PROJECT_COLUMNS = ("programme_id", "cordis_id", "ga_number", "acronym", "title", "call_code",
                   "topic_code", "status", "total_cost", "eu_contribution", "start_date",
                   "end_date", "duration_months")


def _project_values(rec: cordis.ProjectRecord, programme_ids: dict[str, int]) -> dict[str, Any]:
    return {"programme_id": programme_ids.get(rec.programme or ""), "cordis_id": rec.rcn,
            "ga_number": rec.ga_number, "acronym": rec.acronym, "title": rec.title,
            "call_code": rec.call_code, "topic_code": rec.topic_code, "status": rec.status,
            "total_cost": rec.total_cost, "eu_contribution": rec.eu_contribution,
            "start_date": rec.start, "end_date": rec.end, "duration_months": rec.duration_months}


def _upsert_project(conn: psycopg.Connection, src_id: int, native_id: str,
                    values: dict[str, Any], existing: dict[str, Any] | None) -> tuple[int, str]:
    """Insert or update a project. Returns (id, 'new' | 'changed' | 'same')."""
    if existing is None:
        cols = ("source_id", "native_id", *values)
        row = conn.execute(
            f"INSERT INTO project ({', '.join(cols)}) VALUES ({', '.join(['%s'] * len(cols))}) "
            "RETURNING id", (src_id, native_id, *values.values())).fetchone()
        return row["id"], "new"
    if all(_same(existing[k], v) for k, v in values.items()):
        return existing["id"], "same"
    conn.execute(f"UPDATE project SET {', '.join(f'{k} = %s' for k in values)} WHERE id = %s",
                 (*values.values(), existing["id"]))
    return existing["id"], "changed"


def _upsert_participation(conn: psycopg.Connection, project_id: int, org_id: int, role: str,
                          contribution: float | None, method: str, confidence: float,
                          existing: dict[str, Any] | None, note: str | None = None,
                          stated: float | None = None) -> tuple[int, str]:
    if existing is None:
        row = conn.execute(
            """INSERT INTO participation (project_id, organisation_id, role, contribution,
                                          resolution_method, resolution_confidence,
                                          contribution_note, contribution_stated)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
            (project_id, org_id, role, contribution, method, round(confidence, 2), note,
             stated)).fetchone()
        return row["id"], "new"
    if (existing["role"] == role and _same(existing["contribution"], contribution)
            and existing["active"] and existing.get("contribution_note") == note
            and _same(existing.get("contribution_stated"), stated)):
        return existing["id"], "same"
    conn.execute(
        """UPDATE participation SET role = %s, contribution = %s, contribution_note = %s,
                  contribution_stated = %s, active = TRUE WHERE id = %s""",
        (role, contribution, note, stated, existing["id"]))
    return existing["id"], "changed"


# ------------------------------------------------------------------ what a contribution means

# `participation.contribution` is the EU funding CORDIS's open data pays to the participant (the
# grant payment of its role). It is NOT the "net EU contribution" the CORDIS web page prints: the
# page deducts what the participant passes on to its linked third parties, and the open data does
# not say which third party is linked to which beneficiary, nor what each was paid (it shows them
# at 0). So:
#   NULL      the amount is unknown; `contribution_note` says why
#               no_payment_stated      the service holds no payment for this role (recent grants)
#               linked_third_party     a third party, shown at 0: its share is inside another payment
#               exceeds_project_total  the project's amounts add up to more than its EU contribution;
#                                      none can be trusted, the figure as stated is in contribution_stated
#               source_states_none     EDF factsheets state no amount per participant
#   a number  the amount as stated; with the note `gross_of_third_parties` the project has third
#             parties, so the amount may include their share
#   0         stated as 0 (an associated partner, a partner organisation: not funded)
OVERSUM_TOLERANCE = 1.0          # EUR per participant: CORDIS rounds each amount to the cent or the euro
# ponytail: a flat 2 per cent of the project total is also allowed. An amendment moves a few thousand euro and the
# open data keeps either figure; below 2 per cent no row is wrong by more than that (measured on 17 October:
# project 241935, 148 participants, 0.2 per cent over, would have lost every amount). Raise or drop it when the
# bulk package, which has the net figures, replaces the open data.
OVERSUM_RELATIVE = 0.02
NOTE_CODES = ("no_payment_stated", "linked_third_party", "exceeds_project_total",
              "source_states_none", "gross_of_third_parties")


def source_view(role: str, contribution: float | None, note: str | None,
                stated: float | None) -> tuple[float | None, str | None]:
    """What the source said about a participation, recovered from a stored row, so that
    `settle_amounts` can be run again on rows written by an earlier version or by this one."""
    if note == "exceeds_project_total":
        return (None if stated is None else float(stated)), None
    if note in ("no_payment_stated", "linked_third_party"):
        return None, note
    if note == "source_states_none":
        return None, note
    value = None if contribution is None else float(contribution)
    if value == 0 and role == "third_party":
        return None, "linked_third_party"
    if value is None:
        return None, "no_payment_stated"
    return value, None


def settle_amounts(members: list[tuple[str, float | None, str | None]], fund: float | None
                   ) -> list[tuple[float | None, str | None, float | None]]:
    """(contribution, note, stated) for each member of one project, given as (role, amount as the
    source states it or None, note for a missing amount) and the project's EU contribution.

    The amounts of a project cannot add up to more than its EU contribution. When they do, which of
    them is wrong cannot be told (CORDIS pays an ERC grant that moved between two hosts to both in
    full; amendments move money and the open data keeps the old figures), so none is shown: every
    positive amount is withheld, kept in `stated`, and marked."""
    positive = [a for _, a, _ in members if a is not None and a > 0]
    if fund and fund > 0 and positive and sum(positive) > (
            fund * (1 + OVERSUM_RELATIVE) + OVERSUM_TOLERANCE * (len(members) + 1)):
        return [(None, "exceeds_project_total", a) if a is not None and a > 0 else (a, n, None)
                for _, a, n in members]
    has_tp = any(r == "third_party" for r, _, _ in members)
    return [(a, "gross_of_third_parties" if a is not None and a > 0 and has_tp
             and r in ("coordinator", "participant") else n, None) for r, a, n in members]


def _known_hashes(conn: psycopg.Connection, src_id: int) -> set[str]:
    return {r["content_hash"] for r in conn.execute(
        "SELECT content_hash FROM raw_ingest WHERE source_id = %s", (src_id,)).fetchall()}


def _switch_on(conn: psycopg.Connection, code: str) -> None:
    """The first finished run makes the source visible (it is seeded inactive, see migration 0060):
    from then on `/v1/health` and the sources list report it, and a failed or partial month shows."""
    conn.execute("UPDATE source SET active = TRUE WHERE code = %s AND NOT active", (code,))
    conn.commit()


def _settle_organisation(conn: psycopg.Connection, org_id: int, rec: cordis.OrgRecord, c: Counter) -> None:
    """After the cascade, for an organisation that holds the PIC this record states: its country and
    its name as CORDIS gives them now.

    Country. The cascade finds an organisation by PIC and does not look at the country, and it
    creates a new one with the country of the first record it meets. When the record's three signals
    say another country than the one stored (`cordis.seat_country`: CSIC, address Trento, site
    "Madrid ES", VAT ES), the stored country follows, with the basis and the countries seen, and the
    organisation's aliases move with it. A record whose address stands undisputed (basis 'address') never changes
    an organisation whose stored basis is None: its country may have come from the buyer side. When the two agree
    the basis is stored, so that no basis means "not looked at" (WP-43).

    Name. CORDIS prints the current name; the display name follows it, and the name it replaces
    stays an alias (it was recorded when the organisation first met it)."""
    if not rec.pic:
        return
    row = conn.execute(
        "SELECT country, country_basis, country_sites, display_name, eu_pic FROM organisation WHERE id = %s",
        (org_id,)).fetchone()
    if row is None or row["eu_pic"] != rec.pic:
        return
    have = (row["country"].strip(), row["country_basis"], list(row["country_sites"] or []))
    want = (rec.country, rec.country_basis, list(rec.country_sites))
    if rec.country and have != want:
        if row["country_basis"] is not None or rec.country_basis != "address":
            conn.execute(
                "UPDATE organisation SET country = %s, country_basis = %s, country_sites = %s WHERE id = %s",
                (rec.country, rec.country_basis, list(rec.country_sites) or None, org_id))
            if have[0] != rec.country:
                conn.execute(
                    """UPDATE organisation_alias a SET country_hint = %s
                        WHERE a.organisation_id = %s AND a.country_hint = %s
                          AND NOT EXISTS (SELECT 1 FROM organisation_alias b
                                           WHERE b.normalised_name = a.normalised_name
                                             AND b.country_hint = %s
                                             AND b.source_id IS NOT DISTINCT FROM a.source_id)""",
                    (rec.country, org_id, have[0], rec.country))
                c["countries_changed"] += 1
            else:
                c["bases_set"] += 1
        elif have[0] == rec.country:
            # the record's address and the stored country agree and nothing disputes them: say so
            conn.execute("UPDATE organisation SET country_basis = 'address' WHERE id = %s", (org_id,))
            c["bases_set"] += 1
        else:
            # an undisputed address against a country that has no basis (it may have come from the buyer side)
            c["address_differs_kept"] += 1
    shown = " ".join((row["display_name"] or "").split())
    # A rename, not a respelling: CORDIS prints names without accents and with its own punctuation (13 of the
    # 72,534 differ that way on 17 October), and "Fundación" is not improved by "FUNDACION".
    if not shown or key_of(rec.name)[0] != key_of(shown)[0]:
        conn.execute("UPDATE organisation SET display_name = %s WHERE id = %s", (rec.name[:300], org_id))
        c["names_refreshed"] += 1


def _complete(c: Counter, kind: str, expected: int, max_pages: int | None) -> None:
    got = c[f"{kind}_seen"]
    if max_pages is None and got < expected * COMPLETE:
        raise RuntimeError(f"cordis {kind}: read {got} of the {expected} the service counts; "
                           "not loading a partial copy")


def load_cordis(conn: psycopg.Connection, sp: cordis.Sparql, writer: BundleWriter, src_id: int,
                *, run_id: int | None = None, programmes: set[str] | None = None,
                max_pages: int | None = None, candidates: bool = False,
                counters: Counter | None = None) -> Counter:
    """One full pass over the service. `programmes` keeps only those frameworks' projects (the
    organisations are always all read); `max_pages` stops each kind early, for a rehearsal, and
    then nothing is marked inactive."""
    code = cordis.SOURCE_CODE
    c = counters if counters is not None else Counter()
    known = _known_hashes(conn, src_id)
    expected = {k: sp.count(k) for k in ("organisations", "projects", "roles")}
    c["expected_organisations"], c["expected_projects"], c["expected_roles"] = (
        expected["organisations"], expected["projects"], expected["roles"])

    def pages(kind: str):
        for n, page in enumerate(sp.pages(kind)):
            if max_pages is not None and n >= max_pages:
                return
            _land(conn, writer, src_id, code, known, page,
                  f"{kind}:{page['after'] or 'start'}")
            yield page

    # 1. organisations -> organisation_id (PIC first, then the name)
    org_map: dict[str, tuple[int, str, float]] = {}
    for page in pages("organisations"):
        for row in page["rows"]:
            c["organisations_seen"] += 1
            c["fetched"] += 1
            rec = cordis.org_record(row)
            if rec is None:
                c["organisations_unreadable"] += 1
                continue
            if rec.country is None:
                c["organisations_no_country"] += 1
                continue
            res = resolve(conn, rec.name, rec.country, {"pic": rec.pic, "vat": rec.vat},
                          {"source_id": src_id, "candidates": candidates})
            if res.org_id is None:
                continue
            _settle_organisation(conn, res.org_id, rec, c)
            org_map[rec.key] = (res.org_id, res.method, res.confidence)
            c[f"organisation_by_{res.method}"] += 1
            if res.created:
                c["organisations_new"] += 1
                c["new"] += 1
        _checkpoint(conn, writer, run_id, c)
    _complete(c, "organisations", expected["organisations"], max_pages)

    # 2. projects
    programme_ids = {r["code"]: r["id"] for r in conn.execute(
        "SELECT code, id FROM programme WHERE code = ANY(%s)", (["H2020", "HORIZON", "FP7"],))}
    proj_map: dict[str, int] = {}
    proj_fund: dict[int, float | None] = {}             # project id -> its EU contribution
    for page in pages("projects"):
        recs = []
        for row in page["rows"]:
            c["projects_seen"] += 1
            c["fetched"] += 1
            rec = cordis.project_record(row)
            if rec is None:
                c["projects_unreadable"] += 1
            elif programmes and rec.programme not in programmes:
                c["projects_out_of_scope"] += 1
            else:
                recs.append(rec)
        existing = {r["native_id"]: r for r in conn.execute(
            f"SELECT id, native_id, {', '.join(PROJECT_COLUMNS)} FROM project "
            "WHERE source_id = %s AND native_id = ANY(%s)",
            (src_id, [r.rcn for r in recs])).fetchall()}
        for rec in recs:
            pid, action = _upsert_project(conn, src_id, rec.rcn,
                                          _project_values(rec, programme_ids),
                                          existing.get(rec.rcn))
            proj_map[rec.rcn] = pid
            proj_fund[pid] = rec.eu_contribution
            if action != "same":
                c[f"projects_{action}"] += 1
                c["new" if action == "new" else "changed"] += 1
        _checkpoint(conn, writer, run_id, c)
    _complete(c, "projects", expected["projects"], max_pages)

    # 3. participations. The pages come in the order of the service's own role identifiers, so the
    #    roles of one project are scattered over the whole stream and an organisation that appears
    #    twice in a project (a coordinator and a third party, say) is met in two different pages.
    #    They are gathered first and written once, merged: writing the first sight and then the
    #    merge would change the row twice and make every second run report changes.
    pairs: dict[tuple[int, int], list[Any]] = {}            # (project, organisation) -> role, amount, how
    for page in pages("roles"):
        for row in page["rows"]:
            c["roles_seen"] += 1
            c["fetched"] += 1
            rec = cordis.role_record(row)
            if rec is None:
                c["roles_unreadable"] += 1
                continue
            project_id, org = proj_map.get(rec.project_rcn), org_map.get(rec.org_key)
            if project_id is None or org is None:
                c["roles_unlinked"] += 1
                continue
            pair = (project_id, org[0])
            held = pairs.get(pair)
            if held is None:
                pairs[pair] = [rec.role, rec.contribution, rec.note, org[1], org[2]]
            else:
                c["roles_duplicate"] += 1
                held[0] = _better_role(held[0], rec.role)
                if held[1] is not None or rec.contribution is not None:
                    held[1] = (held[1] or 0) + (rec.contribution or 0)
                    held[2] = None
                elif held[2] is None:
                    held[2] = rec.note
        _checkpoint(conn, writer, run_id, c)
    _complete(c, "roles", expected["roles"], max_pages)

    touched: set[int] = set()                               # participation ids this run saw
    by_project: dict[int, list[tuple[int, list[Any]]]] = {}
    for (project_id, org_id), held in pairs.items():
        by_project.setdefault(project_id, []).append((org_id, held))
    del pairs
    project_ids = sorted(by_project)
    for i in range(0, len(project_ids), 2000):
        chunk = project_ids[i:i + 2000]
        existing = {(r["project_id"], r["organisation_id"]): r for r in conn.execute(
            """SELECT id, project_id, organisation_id, role, contribution, active,
                      contribution_note, contribution_stated
                 FROM participation WHERE project_id = ANY(%s)""", (chunk,)).fetchall()}
        for project_id in chunk:
            members = by_project[project_id]
            settled = settle_amounts([(h[0], h[1], h[2]) for _, h in members], proj_fund.get(project_id))
            if any(n == "exceeds_project_total" for _, n, _ in settled):
                c["projects_amounts_withheld"] += 1
            for (org_id, (role, _contribution, _note, method, conf)), (amount, note, stated) in zip(
                    members, settled, strict=True):
                pid, action = _upsert_participation(conn, project_id, org_id, role, amount, method,
                                                    conf, existing.get((project_id, org_id)), note, stated)
                touched.add(pid)
                if action != "same":
                    c[f"participations_{action}"] += 1
                    c["new" if action == "new" else "changed"] += 1
        conn.commit()
    del by_project

    # 4. participants a complete pass no longer finds: marked, never deleted. Only in projects this
    #    pass read, so a programme filter cannot deactivate the rest.
    if max_pages is None:
        seen_projects = set(proj_map.values())
        gone = [r["id"] for r in conn.execute(
            """SELECT pa.id, pa.project_id FROM participation pa JOIN project p ON p.id = pa.project_id
                WHERE p.source_id = %s AND pa.active""", (src_id,)).fetchall()
                if r["id"] not in touched and r["project_id"] in seen_projects]
        for i in range(0, len(gone), 10000):
            conn.execute("UPDATE participation SET active = FALSE WHERE id = ANY(%s)",
                         (gone[i:i + 10000],))
        c["participations_deactivated"] = len(gone)
        conn.commit()
    return c


def reconcile_countries(conn: psycopg.Connection, sp: cordis.Sparql, writer: BundleWriter | None,
                        src_id: int, *, apply: bool = False, max_pages: int | None = None) -> Counter:
    """Read the organisations of CORDIS again (15 requests, no project and no participation) and bring
    the country and display name of the organisations that hold their PIC in line with
    `_settle_organisation`. `writer` lands the pages first (the pipeline rule); without `apply`
    nothing is written (the transaction is rolled back and nothing is landed)."""
    c: Counter = Counter()
    known = _known_hashes(conn, src_id)
    for n, page in enumerate(sp.pages("organisations")):
        if max_pages is not None and n >= max_pages:
            break
        if apply and writer is not None:
            _land(conn, writer, src_id, cordis.SOURCE_CODE, known, page,
                  f"organisations:{page['after'] or 'start'}")
        for row in page["rows"]:
            c["organisations_seen"] += 1
            rec = cordis.org_record(row)
            if rec is None or rec.country is None or not rec.pic:
                continue
            holder = conn.execute("SELECT id FROM organisation WHERE eu_pic = %s", (rec.pic,)).fetchone()
            if holder is None:
                c["organisations_not_held"] += 1
                continue
            if rec.country_basis == "several":
                c["organisations_several_countries"] += 1
            elif rec.country_basis == "vote":
                c["organisations_country_by_vote"] += 1
            _settle_organisation(conn, holder["id"], rec, c)
        if apply and writer is not None:
            writer.drain()
        conn.commit() if apply else conn.rollback()
    return c


def run_cordis(*, programmes: set[str] | None = None, max_pages: int | None = None,
               candidates: bool = True, sparql: cordis.Sparql | None = None) -> Counter:
    code = cordis.SOURCE_CODE
    cfg = settings()
    sp = sparql or cordis.Sparql()
    c: Counter = Counter()
    try:
        with db.connect(cfg.dsn) as conn, BundleWriter(build_store(), code) as writer:
            sp.check_robots()
            src_id = db.source_id(conn, code)
            run_id = db.start_run(conn, code, None if max_pages else cfg.cordis_floor)
            try:
                load_cordis(conn, sp, writer, src_id, run_id=run_id, programmes=programmes,
                            max_pages=max_pages, candidates=candidates, counters=c)
                writer.drain()
                db.finish_run(conn, run_id, fetched=c["fetched"], new=c["new"],
                              changed=c["changed"], detail=dict(c))
                _switch_on(conn, code)
            except Exception as exc:
                conn.rollback()
                db.finish_run(conn, run_id, fetched=c["fetched"], new=c["new"],
                              changed=c["changed"], status="failed", error=str(exc)[:500])
                raise
            refresh_organisation_network(conn)
    finally:
        if sparql is None:
            sp.close()
    log.info("%s done: %s", code, dict(c))
    return c


# ================================================================== EDF

def _edf_project_values(info: edf.FileInfo, facts: dict[str, Any], url: str,
                        programme_id: int | None, text: edf.FactsheetText) -> dict[str, Any]:
    shown = facts.get("acronym") or ""
    if not shown or not any(edf.norm(shown) in edf.norm(t) for t in (text.layout, text.plain)):
        shown = info.acronym.replace("_", " ")             # not printed in the file: the file name's
    title = (facts.get("title") or "").strip() or shown
    total, eu = facts.get("total_cost"), facts.get("eu_contribution")
    if total is not None and eu is not None and eu > total * 1.0001:
        eu = None                                       # a contribution above the cost is a misreading
    dur = facts.get("duration_months")
    return {"programme_id": programme_id, "ga_number": info.ga_number, "acronym": shown[:100],
            "title": title[:600], "topic_code": info.topic_code, "action_type": info.action,
            "category": info.category, "call_year": info.year, "total_cost": total,
            "eu_contribution": eu, "duration_months": dur if dur and 0 < dur < 240 else None,
            "factsheet_url": url}


EDF_COLUMNS = ("programme_id", "ga_number", "acronym", "title", "topic_code", "action_type",
               "category", "call_year", "total_cost", "eu_contribution", "duration_months",
               "factsheet_url")


def load_edf_factsheet(conn: psycopg.Connection, src_id: int, info: edf.FileInfo, url: str,
                       text: edf.FactsheetText, facts: dict[str, Any], c: Counter) -> int:
    """Store one factsheet's project and consortium. Idempotent."""
    programme_id = (conn.execute("SELECT id FROM programme WHERE code = 'EDF'").fetchone() or {}
                    ).get("id")
    values = _edf_project_values(info, facts, url, programme_id, text)
    native = info.key
    existing = conn.execute(
        f"SELECT id, {', '.join(EDF_COLUMNS)} FROM project WHERE source_id = %s AND native_id = %s",
        (src_id, native)).fetchone()
    project_id, action = _upsert_project(conn, src_id, native, values, existing)
    if action != "same":
        c[f"projects_{action}"] += 1
        c["new" if action == "new" else "changed"] += 1

    members: dict[int, list[Any]] = {}
    for p in facts.get("participants") or []:
        iso = p.get("country_iso")
        if not iso:
            c["participants_no_country"] += 1
            continue
        res = resolve(conn, p["name"], iso, None, {"source_id": src_id, "candidates": True})
        if res.org_id is None:
            continue
        c[f"participant_by_{res.method}"] += 1
        c["organisations_new"] += res.created
        c["new"] += res.created
        held = members.get(res.org_id)
        if held is None:
            members[res.org_id] = [p["role"], res.method, res.confidence]
        else:
            held[0] = _better_role(held[0], p["role"])
    existing_p = {r["organisation_id"]: r for r in conn.execute(
        """SELECT id, organisation_id, role, contribution, active, contribution_note,
                  contribution_stated FROM participation
            WHERE project_id = %s""", (project_id,)).fetchall()}
    for org_id, (role, method, conf) in members.items():
        _, act = _upsert_participation(conn, project_id, org_id, role, None, method, conf,
                                       existing_p.get(org_id), "source_states_none")
        if act != "same":
            c[f"participations_{act}"] += 1
            c["new" if act == "new" else "changed"] += 1
    gone = [o for o, r in existing_p.items() if r["active"] and o not in members]
    if gone and members:
        conn.execute("UPDATE participation SET active = FALSE WHERE project_id = %s "
                     "AND organisation_id = ANY(%s)", (project_id, gone))
        c["participations_deactivated"] += len(gone)
    return project_id


FRESH_DAYS = 25


def process_factsheet(conn: psycopg.Connection, http, writer: BundleWriter, src_id: int,
                      known: set[str], link: edf.Link, info: edf.FileInfo, c: Counter,
                      llm_client=None, *, pace: dict[str, float] | None = None, sleep=None,
                      reread: bool = False) -> None:
    """One PDF: fetch, land, ask the model (unless this file was read before), store.

    A file read in the last 25 days with this prompt is not even fetched again (the site
    rate-limits, and a monthly job has no use for a second look within the month); `reread`
    forces it."""
    held = conn.execute(
        """SELECT sha256, prompt_version, facts, dropped,
                  extracted_at > now() - make_interval(days => %s) AS fresh
             FROM project_factsheet WHERE url = %s""", (FRESH_DAYS, link.url)).fetchone()
    if held and held["fresh"] and held["prompt_version"] == edf.PROMPT_VERSION and not reread:
        c["factsheets_recent"] += 1
        return
    content = edf.fetch_pdf(http, link.url, pace=pace, **({"sleep": sleep} if sleep else {}))
    text = edf.read_pdf(content)
    if held and held["sha256"] == text.sha256 and held["prompt_version"] == edf.PROMPT_VERSION:
        facts, dropped, usage = held["facts"], held["dropped"], None
        c["factsheets_held"] += 1
    else:
        _land(conn, writer, src_id, edf.SOURCE_CODE, known,
              {"url": link.url, "filename": link.filename, "sha256": text.sha256,
               "pages": text.pages, "layout": text.layout, "plain": text.plain},
              f"{info.year}:{link.filename}")
        writer.drain()
        conn.commit()
        answer, usage = llm.complete_json(
            conn, task=edf.TASK, system=edf.SYSTEM, user=f"Factsheet:\n\n{text.layout}",
            schema=_edf_schema(), schema_name="edf_factsheet", max_output_tokens=4000,
            client=llm_client)
        facts, dropped = edf.check_names(answer, text)
        c["factsheets_read"] += 1
        for k, v in dropped.items():
            c[f"dropped_{k}"] += v
        if not facts["participants"]:
            # a layout change or a misreading: the project is stored, but the run says so
            c["files_without_participants"] += 1
    project_id = load_edf_factsheet(conn, src_id, info, link.url, text, facts, c)
    if usage is not None:
        conn.execute(
            """INSERT INTO project_factsheet (url, project_id, sha256, pages, facts, dropped, model,
                                              prompt_version, input_tokens, output_tokens, cost_usd)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT (url) DO UPDATE SET project_id = EXCLUDED.project_id,
                 sha256 = EXCLUDED.sha256, pages = EXCLUDED.pages, facts = EXCLUDED.facts,
                 dropped = EXCLUDED.dropped, model = EXCLUDED.model,
                 prompt_version = EXCLUDED.prompt_version, input_tokens = EXCLUDED.input_tokens,
                 output_tokens = EXCLUDED.output_tokens, cost_usd = EXCLUDED.cost_usd,
                 extracted_at = now()""",
            (link.url, project_id, text.sha256, text.pages, Jsonb(facts), Jsonb(dropped),
             settings().openai_model or "", edf.PROMPT_VERSION, usage["input_tokens"],
             usage["output_tokens"], usage["cost_usd"]))
        c["cost_usd"] += usage["cost_usd"]


def _edf_schema() -> dict[str, Any]:
    from .enrichment.base import strict_schema

    return strict_schema(edf.Factsheet)


def run_edf(*, years: set[int] | None = None, max_files: int | None = None, http=None,
            llm_client=None, sleep=None, reread: bool = False) -> Counter:
    """Crawl the EDF results pages and load every factsheet. One request a second."""
    import time

    from .sources import new_client

    code = edf.SOURCE_CODE
    cfg = settings()
    pause = sleep or time.sleep
    pace = {"delay": 1.0}           # seconds between two requests; the site slows it down, see fetch_pdf
    own = http is None
    http = http or new_client(timeout=120, follow_redirects=True, headers={"User-Agent": USER_AGENT})
    c: Counter = Counter()
    try:
        with db.connect(cfg.dsn) as conn, BundleWriter(build_store(), code) as writer:
            robots = edf.robots(http)
            src_id = db.source_id(conn, code)
            run_id = db.start_run(conn, code, None if (max_files or years) else cfg.edf_floor)
            known = _known_hashes(conn, src_id)
            try:
                if not edf.allowed(robots, edf.SITEMAP):
                    raise edf.RobotsDisallowed(f"robots.txt disallows {edf.SITEMAP}")
                sm = http.get(edf.SITEMAP)
                sm.raise_for_status()
                pages = edf.result_pages(sm.text)
                this_year = date.today().year
                for y in range(edf.FIRST_YEAR, this_year + 1):
                    if y not in pages:
                        for guess in edf.guessed_pages(y):
                            if not edf.allowed(robots, guess):
                                continue
                            pause(1.0)
                            r = http.get(guess)
                            if r.status_code == 200:
                                pages[y] = guess
                                break
                c["result_pages"] = len(pages)
                stopped = False
                for year, url in sorted(pages.items()):
                    if (years and year not in years) or stopped:
                        continue
                    if not edf.allowed(robots, url):
                        raise edf.RobotsDisallowed(f"robots.txt disallows {url}")
                    pause(1.0)
                    r = http.get(url)
                    r.raise_for_status()
                    # One file per project: a file uploaded twice appears as NAME.pdf and NAME_0.pdf,
                    # the second being the later upload. Reading both would make the project flip
                    # between them on every run.
                    chosen: dict[str, tuple[edf.Link, edf.FileInfo]] = {}
                    for link in edf.factsheet_links(r.text, url):
                        info = edf.parse_filename(link.filename, year)
                        if info is None:
                            c["files_unparsed"] += 1
                            log.warning("edf: %s is not a project factsheet name", link.filename)
                            continue
                        if info.key in chosen:
                            c["files_superseded"] += 1
                        chosen[info.key] = (link, info)
                    for link, info in chosen.values():
                        if max_files is not None and c["fetched"] >= max_files:
                            stopped = True
                            break
                        if not edf.allowed(robots, link.url):
                            c["files_disallowed"] += 1
                            continue
                        c["fetched"] += 1
                        pause(pace["delay"])
                        try:
                            process_factsheet(conn, http, writer, src_id, known, link, info, c,
                                              llm_client, pace=pace, sleep=pause, reread=reread)
                        except RateLimited as exc:
                            conn.rollback()
                            c["rate_limited"] = 1
                            c["files_not_read"] += 1
                            log.warning("edf: stopping, the site keeps refusing: %s", exc)
                            stopped = True
                            break
                        except llm.CapReached:
                            conn.rollback()
                            c["stopped_by_cap"] = 1
                            stopped = True
                            break
                        except (llm.LLMError, ValueError, httpx.HTTPError) as exc:
                            conn.rollback()
                            c["files_failed"] += 1
                            log.warning("edf: %s failed: %s", link.filename, exc)
                            continue
                        _checkpoint(conn, writer, run_id, c)
                writer.drain()
                problem = ("the site kept answering 'too many requests'; run again later"
                           if c["rate_limited"] else
                           "the monthly model budget was reached" if c["stopped_by_cap"]
                           else f"{c['files_failed']} factsheets could not be read"
                           if c["files_failed"]
                           else f"{c['files_without_participants']} factsheets gave no participants"
                           if c["files_without_participants"] else None)
                db.finish_run(conn, run_id, fetched=c["fetched"], new=c["new"],
                              changed=c["changed"], status="partial" if problem else "success",
                              error=problem, detail=dict(c))
                if c["factsheets_read"] or c["factsheets_held"] or c["factsheets_recent"]:
                    _switch_on(conn, code)
            except Exception as exc:
                conn.rollback()
                db.finish_run(conn, run_id, fetched=c["fetched"], new=c["new"],
                              changed=c["changed"], status="failed", error=str(exc)[:500])
                raise
            refresh_organisation_network(conn)
    finally:
        if own:
            http.close()
    log.info("%s done: %s", code, dict(c))
    return c


# ================================================================== stage 3 for what exists

def queue_candidates(conn: psycopg.Connection, *, after_id: int = 0, limit: int = 5000,
                     all_orgs: bool = False) -> dict[str, int]:
    """Stage 3 (trigram candidates into `resolution_review`) for organisations already held, in
    chunks of `limit`, resumable by id: the first load can run with `--no-candidates` and this
    follows at a time of the operator's choosing (about 30 ms an organisation on the host).
    By default only organisations with a PIC (the CORDIS ones); `all_orgs` takes every live one.
    Nothing is merged. Returns {processed, last_id, pairs: new pairs queued}."""
    rows = conn.execute(
        """SELECT id, canonical_name, country FROM organisation
            WHERE id > %s AND merged_into IS NULL AND (%s OR eu_pic IS NOT NULL)
            ORDER BY id LIMIT %s""", (after_id, all_orgs, limit)).fetchall()
    before = conn.execute("SELECT count(*) AS n FROM resolution_review").fetchone()["n"]
    for n, r in enumerate(rows, 1):
        propose_candidates(conn, r["id"], r["canonical_name"], r["country"])
        if n % 500 == 0:
            conn.commit()
    conn.commit()
    after = conn.execute("SELECT count(*) AS n FROM resolution_review").fetchone()["n"]
    return {"processed": len(rows), "last_id": rows[-1]["id"] if rows else after_id,
            "pairs": after - before}


# ================================================================== snapshots

SNAPSHOT_SQL = """
WITH cur AS (
  SELECT p.project_id,
         array_agg(DISTINCT COALESCE(o.merged_into, o.id) ORDER BY COALESCE(o.merged_into, o.id))
           AS members,
         min(COALESCE(o.merged_into, o.id)) FILTER (WHERE p.role = 'coordinator') AS coord,
         count(DISTINCT o.country) AS countries
    FROM participation p JOIN organisation o ON o.id = p.organisation_id
   WHERE p.active GROUP BY p.project_id),
last AS (
  SELECT DISTINCT ON (project_id) id, project_id, member_org_ids, coordinator_org_id
    FROM consortium_snapshot ORDER BY project_id, observed_at DESC, id DESC),
new AS (
  INSERT INTO consortium_snapshot (project_id, observed_at, member_org_ids, coordinator_org_id,
                                   member_count, country_count)
  SELECT c.project_id, %(day)s, c.members, c.coord, cardinality(c.members), c.countries
    FROM cur c LEFT JOIN last l ON l.project_id = c.project_id
   WHERE l.id IS NULL OR l.member_org_ids IS DISTINCT FROM c.members
      OR l.coordinator_org_id IS DISTINCT FROM c.coord
  ON CONFLICT (project_id, observed_at) DO NOTHING
  RETURNING id, project_id, member_org_ids, coordinator_org_id),
ev AS (
  INSERT INTO consortium_change (project_id, snapshot_id, prev_snapshot_id, observed_at,
                                 added_org_ids, removed_org_ids, coordinator_before,
                                 coordinator_after)
  SELECT n.project_id, n.id, l.id, %(day)s,
         ARRAY(SELECT unnest(n.member_org_ids) EXCEPT SELECT unnest(l.member_org_ids)),
         ARRAY(SELECT unnest(l.member_org_ids) EXCEPT SELECT unnest(n.member_org_ids)),
         l.coordinator_org_id, n.coordinator_org_id
    FROM new n JOIN last l ON l.project_id = n.project_id
  RETURNING id)
SELECT (SELECT count(*) FROM new) AS snapshots, (SELECT count(*) FROM ev) AS changes,
       (SELECT count(*) FROM cur) AS projects
"""


def snapshot_consortia(conn: psycopg.Connection, day: date | None = None) -> dict[str, int]:
    """Write a snapshot for every project whose composition differs from its last snapshot (or has
    none), and one `consortium_change` per project that had a snapshot before. A project whose
    members and coordinator are unchanged gets no new row: the last snapshot still describes it."""
    row = conn.execute(SNAPSHOT_SQL, {"day": day or date.today()}).fetchone()
    conn.commit()
    return {"snapshots": row["snapshots"], "changes": row["changes"], "projects": row["projects"]}


def run_snapshot() -> dict[str, int]:
    with db.connect(settings().dsn) as conn:
        out = snapshot_consortia(conn)
        out["directory"] = refresh_organisation_network(conn)["organisations"]
    log.info("consortium snapshot: %s", out)
    return out


# ================================================================== the directory (WP-28)

YEAR_SQL = "COALESCE(extract(year FROM p.start_date)::int, p.call_year::int)"

DEFENCE_IN = ", ".join(f"'{c}'" for c in DEFENCE_PROGRAMMES)

REFRESH_NETWORK_SQL = f"""
WITH part AS (
  SELECT COALESCE(h.id, COALESCE(l.live_id, pa.organisation_id)) AS org,
         COALESCE(l.live_id, pa.organisation_id) AS own, h.id IS NOT NULL AS in_family,
         pa.project_id, pa.role, pa.contribution, {YEAR_SQL} AS yr, pr.code AS prog
    FROM participation pa
    JOIN project p ON p.id = pa.project_id
    LEFT JOIN programme pr ON pr.id = p.programme_id
    LEFT JOIN organisation_merged_live l ON l.id = pa.organisation_id
    LEFT JOIN organisation_family_member fm ON fm.org_id = COALESCE(l.live_id, pa.organisation_id)
    LEFT JOIN organisation h ON h.id = fm.head_org_id AND h.merged_into IS NULL AND NOT h.suppressed
   WHERE pa.active AND NOT COALESCE(l.suppressed, FALSE)),
agg AS (
  SELECT org, count(DISTINCT project_id) AS projects,
         count(DISTINCT project_id) FILTER (WHERE role = 'coordinator') AS coordinated,
         sum(contribution) AS eu, min(yr) AS y0, max(yr) AS y1,
         array_remove(array_agg(DISTINCT prog ORDER BY prog), NULL) AS progs,
         array_agg(DISTINCT role ORDER BY role) AS roles,
         count(DISTINCT own) FILTER (WHERE in_family) AS variants,
         count(DISTINCT project_id) FILTER (WHERE prog IN ({DEFENCE_IN})) AS defence
    FROM part GROUP BY org)
INSERT INTO organisation_network (organisation_id, name, country, projects, coordinated,
                                  eu_contribution, first_year, last_year, programmes, roles,
                                  family_variants, defence_projects, refreshed_at)
SELECT a.org, COALESCE(o.display_name, o.canonical_name), o.country, a.projects, a.coordinated,
       a.eu, a.y0, a.y1, a.progs, a.roles, a.variants, a.defence, now()
  FROM agg a JOIN organisation o ON o.id = a.org
 WHERE NOT o.suppressed AND o.individual_reason IS NULL
ON CONFLICT (organisation_id) DO UPDATE SET
  name = EXCLUDED.name, country = EXCLUDED.country, projects = EXCLUDED.projects,
  coordinated = EXCLUDED.coordinated, eu_contribution = EXCLUDED.eu_contribution,
  first_year = EXCLUDED.first_year, last_year = EXCLUDED.last_year,
  programmes = EXCLUDED.programmes, roles = EXCLUDED.roles,
  family_variants = EXCLUDED.family_variants, defence_projects = EXCLUDED.defence_projects,
  refreshed_at = EXCLUDED.refreshed_at
"""


def refresh_organisation_network(conn: psycopg.Connection) -> dict[str, int]:
    """Rebuild the directory table (migration 0068) from the participations: one row per live,
    unsuppressed organisation that is not a natural person, with an active participation. Rows of an
    organisation that no longer qualifies (merged away since, suppressed, an individual, all its
    participations inactive) are deleted: the table
    is derived, the participations are the record. One transaction (`now()` is its start), so a reader
    sees the old table or the new one."""
    # First the natural persons (WP-39): they are marked from the names of the organisations that took part, in
    # this same transaction, and the rebuild leaves them out like a suppressed organisation.
    persons = individuals.mark_individuals(conn)
    log.info("directory refresh: %s", persons)
    conn.execute(REFRESH_NETWORK_SQL)
    gone = conn.execute("DELETE FROM organisation_network WHERE refreshed_at < now()").rowcount
    n = conn.execute("SELECT count(*) AS n FROM organisation_network").fetchone()["n"]
    conn.commit()
    return {"organisations": n, "removed": gone}


def run_cordis_countries(*, apply: bool = False, max_pages: int | None = None,
                         sparql: cordis.Sparql | None = None) -> Counter:
    """`python -m dgate.pipeline cordis-countries [--yes]`: the targeted repair for N4 and N12. Reads the
    organisations of CORDIS again (about 15 requests, one a second, robots.txt first), lands the pages,
    and settles country and display name of the organisations that hold the PIC. No project, no
    participation, no model."""
    cfg = settings()
    sp = sparql or cordis.Sparql()
    try:
        with db.connect(cfg.dsn) as conn, BundleWriter(build_store(), cordis.SOURCE_CODE) as writer:
            sp.check_robots()
            src_id = db.source_id(conn, cordis.SOURCE_CODE)
            c = reconcile_countries(conn, sp, writer, src_id, apply=apply, max_pages=max_pages)
            if apply:
                c["directory_rows"] = refresh_organisation_network(conn)["organisations"]
    finally:
        if sparql is None:
            sp.close()
    log.info("cordis countries (%s): %s", "written" if apply else "dry run", dict(c))
    return c
