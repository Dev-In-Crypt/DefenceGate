"""The pilot report for one funding call (WP-168): who may apply, which organisations did comparable projects, the consortium's gaps.

Internal, never served. One self-contained HTML file, print-ready (A4, the print rules of the readiness report,
web/components/readiness/report.tsx PRINT_CSS): the owner opens it in a browser and saves it as PDF.

    python -m dgate.ops.pilot_report --call EDF-EDIP-USI-2027-LS-IRA-CUXS --ukraine --out cuxs.html
    python -m dgate.ops.pilot_report --call 116 --country DE --consortium 123-acme,456-beta --out kec.html

Nothing here is a second definition of anything. Every section reads what the API serves, its route functions called as plain
functions on a READ ONLY session with a statement timeout (`Db`), in the JSON shape of the endpoint. On production only through the
worker image, read-only (the public site does not serve /v1/projects, /v1/organisations or /v1/analytics, so it cannot stand in):

    docker compose -f infra/docker-compose.yml --env-file infra/.env run --rm --no-deps -T worker         python -m dgate.ops.pilot_report --call EDF-EDIP-USI-2027-LS-IRA-CUXS --ukraine > cuxs.html

  1 The call            /v1/funding/{slug}              funding.get_funding (deadline, budget, the call document's total)
  2 Who may apply       the same                        eligibility facts with their quotes, who_apply limits, the Ukraine flag
  3 Organisations       /v1/funding/{id}/partners       partners.call_partners (area, topic words, past roles of WP-166)
                        /v1/analytics/ukraine-partners  network_api.ukraine_partners (--ukraine)
  4 Consortium gaps     /v1/projects/{id}               network_api.get_project: the consortia of the comparable projects that
                                                        section 3 names as evidence; /v1/organisations/{slug} for --consortium
  5 Method and limits   the sources and dates the payloads carry

Organisations only: the partner lists already leave out natural persons and organisations removed on request, and a project member
shown as "Name not shown" is counted, never named. No contact data and no description of any system: titles and codes only.
"""

from __future__ import annotations

import argparse
import html
import re
import statistics
import sys
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from .. import db
from ..config import settings
from ..normalise import http_url
from ..ukraine import EDF_IN_FORCE_URL

PARTNERS = 25            # organisations listed in section 3
SAMPLE = 15              # comparable projects read for the typical consortium (section 4)
UA_ROWS = 15             # rows of each Ukrainian table (--ukraine)
COMMON = 0.5             # a country in at least this share of the comparable projects is "usually present"
DISCLAIMER = "Indicative information, not legal advice, not an eligibility decision. The call document is authoritative."
_CODE = re.compile(r"^[A-Z0-9]+(-[A-Z0-9]+){2,}$", re.I)


# ------------------------------------------------------------------ where the payloads come from
class Db:
    """The served functions on a read-only session, their answers in the JSON shape the endpoints give."""

    def __init__(self, conn):
        self.conn = conn

    @staticmethod
    def _json(value: Any) -> Any:
        from fastapi.encoders import jsonable_encoder

        return jsonable_encoder(value)

    def call(self, ref: str) -> dict[str, Any]:
        from ..funding import get_funding

        if _CODE.match(ref) and not ref[0].isdigit():
            row = self.conn.execute(
                """SELECT id FROM call WHERE upper(topic_code) = upper(%s) AND NOT suppressed
                    ORDER BY deadline_at DESC NULLS LAST, id DESC LIMIT 1""", (ref,)).fetchone()
            if not row:
                raise SystemExit(f"no call with the topic code {ref}")
            ref = str(row["id"])
        return self._json(get_funding(ref, self.conn))

    def partners(self, call_id: str, *, prefer: str | None = None, country: str | None = None,
                 limit: int = PARTNERS) -> dict[str, Any]:
        from ..partners import call_partners

        return self._json(call_partners(call_id=int(call_id), country=country, prefer=prefer, limit=limit, conn=self.conn))

    def project(self, project_id: str) -> dict[str, Any]:
        from ..network_api import get_project

        return self._json(get_project(project_id, self.conn))

    def organisation(self, slug: str) -> dict[str, Any]:
        from ..network_api import get_organisation

        return self._json(get_organisation(slug, self.conn))

    def ukraine_partners(self) -> dict[str, Any]:
        from ..network_api import DEFAULT_SINCE, ukraine_partners

        return self._json(ukraine_partners(since=DEFAULT_SINCE, programme=None, q=None, conn=self.conn))


# ------------------------------------------------------------------ small helpers
def e(value: Any) -> str:
    return html.escape("" if value is None else str(value))


def link(url: str | None, text: Any) -> str:
    safe = http_url(url) if url else None
    return f'<a href="{e(safe)}">{e(text)}</a>' if safe else e(text)


def site(path: str) -> str:
    return settings().site_url.rstrip("/") + path


def _when(value: Any) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def day(value: Any) -> str:
    d = _when(value)
    return f"{d.day} {d:%b %Y}" if d else "not stated"


def money(amount: float | None, currency: str = "EUR") -> str:
    return f"{currency} {amount:,.0f}" if amount is not None else "not stated"


def millions(amount: float, currency: str = "EUR") -> str:
    """As the call page says it (web/lib/format.ts millions): EUR 82 million, EUR 1.5 million."""
    m = amount / 1e6
    return f"{currency} {m:,.0f} million" if m == int(m) else f"{currency} {m:,.2f}".rstrip("0").rstrip(".") + " million"


def fact_value(value: Any) -> str:
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, list):
        return "; ".join(str(v) for v in value)
    return "" if value is None else str(value)


def section(sid: str, title: str, body: str) -> str:
    return f'<section class="report-section" id="{sid}"><h2>{e(title)}</h2>\n{body}\n</section>'


# ------------------------------------------------------------------ 1 the call
BUDGET_SCOPE = {"topic": "budget of this topic", "call": "shared across several topics of the same call"}


def section_call(call: dict[str, Any]) -> str:
    """Title, programme, identifiers, dates, the portal's budget with what it covers, the call document's total stated as such, and
    the two links: the official page and ours."""
    budget = call.get("budget")
    if budget:
        line = f"{money(budget['amount'], budget['currency'])} ({BUDGET_SCOPE.get(call.get('budgetScope') or '', 'as the portal states it')})"
    else:
        line = (call.get("budgetNote") or {}).get("short") or "The source states no budget."
    doc = call.get("documentBudget")
    if doc:
        voted = f", including {millions(doc['votedEu'], doc['currency'])} from the voted EU budget" if doc.get("votedEu") is not None else ""
        line += (f'<br>Call document total: {millions(doc["amount"], doc["currency"])}{voted} '
                 f'({link(doc.get("documentUrl"), "call document")}). The document states this figure; the portal states the one above.')
    rows = [
        ("Programme", call.get("programmeName")),
        ("Call ID", call.get("callId")),
        ("Topic ID", call.get("topicId")),
        ("Status", call.get("status")),
        ("Opening date", day(call.get("openingDate"))),
        ("Deadline", (f"{day(call['deadline'])}, {_when(call['deadline']):%H:%M} UTC" if call.get("deadline") and not call.get("deadlineIsDate")
                      else day(call.get("deadline")))),
    ]
    body = "<table class=\"facts\">" + "".join(f"<tr><th>{e(k)}</th><td>{e(v)}</td></tr>" for k, v in rows)
    body += f"<tr><th>Budget</th><td>{line}</td></tr></table>"
    src = call.get("source") or {}
    body += (f"<p>Official page: {link(src.get('url'), src.get('sourceName') or 'the source')}. "
             f"Our page: {link(site('/funding/' + call['slug']), site('/funding/' + call['slug']))}.</p>")
    return section("s-call", "1. The call", f"<p class=\"lead\">{e(call['title'])}</p>{body}")


# ------------------------------------------------------------------ 2 who may apply
WHO = {"companies": "Companies can take part", "public": "Public buyers only", "designated": "Designated bodies only"}
FACT_LABELS = (  # the call page's labels (web/components/funding/eligibility-check.tsx), in its order
    ("eligible_countries", "Where applicants must be established"), ("entity_types", "Who may apply"),
    ("designated_applicants", "Designated applicants"), ("consortium_required", "Consortium required"),
    ("min_entities", "Smallest consortium (legal entities)"), ("min_countries", "Smallest number of countries"),
    ("single_applicant_allowed", "A single applicant may apply"), ("required_partners", "Required partners"),
    ("sme_only", "Reserved for SMEs"), ("natural_persons_allowed", "Natural persons may apply"),
    ("ownership_control_restriction", "Ownership control restriction"),
)


def ukraine_verdict(call: dict[str, Any]) -> tuple[str, str]:
    """(word, sentence) of the call's Ukraine flag: eligible / check / not, in the words of the call page (web/lib/ukraine.ts
    ukraineSentence). Never stronger than the flag: an unknown flag is "check" whatever its sentence says."""
    flag, reason = call.get("openToUkraine"), (call.get("ukraineBasis") or {}).get("reason")
    if flag is True:
        if reason == "edf_association":
            return "Eligible", ("Ukrainian entities may take part in this call: Ukraine is an associated country of the European Defence "
                                "Fund since 16 October 2026, when the European Commission said its association agreement had come into force.")
        tail = (" Entities established in the non-government controlled areas of Ukraine are not eligible."
                if call.get("programme") == "EDIP-USI" else "")
        return "Eligible", "Ukrainian entities may take part in this call." + tail
    if flag is False:
        if reason == "call_document_closed_list":
            return "Not eligible", ("The call document lists the eligible countries one by one (the Member States and the EEA countries "
                                    "Norway, Iceland and Liechtenstein). Ukraine is not on the list.")
        return "Not eligible", "The source says Ukrainian entities may not take part in this call."
    if reason in ("edf_closed_before_association", "edf_association_unconfirmed"):
        return "Check", ("This call closed before 16 October 2026, when Ukraine's association with the European Defence Fund entered "
                         "into force; its call document said participation was pending the association agreement.")
    if reason == "call_document_no_funding":
        return "Check", ("The call document says Ukrainian entities cannot receive funding under this call; whether they may take part "
                         "without funding it does not say.")
    if reason == "programme_rule":
        return "Check", ("Entities established in Ukraine cannot receive EDIP funding: recipients must be established in the Union or in "
                         "an EEA EFTA associated country (Regulation (EU) 2025/2643, Articles 9(1) and 2). The call document names Ukraine, "
                         "if at all, in other roles; Ukrainian entities are served by the Ukraine Support Instrument.")
    return "Check", "Nothing we hold states whether Ukrainian entities may take part. Read the call document."


def section_who(call: dict[str, Any]) -> str:
    """The reading of the call's eligibility rules with each sentence quoted and its source linked, the call's own limits, and the
    Ukraine verdict with its evidence."""
    parts = []
    who = WHO.get(call.get("whoMayApply") or "")
    if who:
        parts.append(f"<p class=\"lead\">{e(who)}.</p>")
    for lim in call.get("whoMayApplyLimits") or []:
        label = "Control from elsewhere" if lim.get("kind") == "control" else "Where an applicant must be established"
        parts.append(f"<p><b>{e(label)}:</b> <q>{e(lim['quote'])}</q> {e(lim.get('note') or '')}</p>")
    read = call.get("documentEligibility")
    if read:
        facts = read.get("facts") or {}
        rows = []
        for key, label in FACT_LABELS:
            f = facts.get(key)
            if not f or f.get("value") is None:
                continue
            rows.append(f"<tr class=\"report-row\"><th>{e(label)}</th><td><b>{e(fact_value(f['value']))}</b>"
                        + (f"<br>{e(f['note'])}" if f.get("note") else "")
                        + (f"<br><q>{e(f['quote'])}</q>" if f.get("quote") else "") + "</td></tr>")
        where = "the call document" if read.get("basis") == "call_document" else "the work programme"
        parts.append(f"<p>Read from {link(read.get('documentUrl'), where)} on {e(day(read.get('extractedAt')))}. "
                     "Each line quotes the document's own sentence.</p>")
        parts.append("<table class=\"facts\">" + "".join(rows) + "</table>")
    else:
        sources = " ".join(link(s.get("url"), s.get("label")) for s in call.get("eligibilitySources") or [] if s.get("url"))
        parts.append("<p>The rules of this call have not been read yet. They are written in: " + (sources or "the source's documents")
                     + ".</p>")
    word, sentence = ukraine_verdict(call)
    basis = call.get("ukraineBasis") or {}
    evidence = f"<br>Evidence: <q>{e(basis['evidence'])}</q>" if basis.get("evidence") else ""
    news = (f" {link(EDF_IN_FORCE_URL, 'European Commission, 16 October 2026')}"
            if basis.get("reason") in ("edf_association", "edf_closed_before_association") else "")
    parts.append(f"<h3>Ukrainian applicants: <span class=\"verdict\" data-ukraine=\"{e(word.lower())}\">{e(word)}</span></h3>"
                 f"<p>{e(sentence)}{evidence}{news}</p>")
    return section("s-who", "2. Who may apply", "\n".join(parts))


# ------------------------------------------------------------------ 3 matching organisations
def _roles(r: dict[str, Any] | None) -> str:
    if not r:
        return ""
    return f"coordinator {r.get('coordinator', 0)}, participant {r.get('participant', 0)}"


def partner_rows(partners: list[dict[str, Any]]) -> str:
    out = []
    for p in partners:
        if not p.get("slug"):
            continue       # a withheld name or a natural person carries no slug and is never named here
        ev = "; ".join(f"{link(site('/projects/' + x['projectId']), x.get('acronym') or 'project')} ({e(x.get('year') or '')}, {e(x.get('role'))})"
                       for x in p.get("evidence") or [])
        out.append(f"<tr class=\"report-row\"><td>{link(site('/organisations/' + p['slug']), p['name'])}</td><td>{e(p.get('country'))}</td>"
                   f"<td>{e(p.get('projects'))}{' (' + e(p['topical']) + ' on the topic)' if p.get('topical') else ''}</td>"
                   f"<td>{e(p.get('coordinated'))}</td><td>{e(_roles(p.get('roles')))}</td><td>{ev}</td></tr>")
    head = ("<tr><th>Organisation</th><th>Country</th><th>Projects in the area</th><th>Coordinated in the area</th>"
            "<th>Past roles, all EU projects</th><th>Comparable projects (year, role)</th></tr>")
    return f"<table class=\"list\">{head}{''.join(out)}</table>" if out else "<p>No organisation to list.</p>"


def section_partners(found: dict[str, Any], *, country: str | None, ua_area: dict[str, Any] | None,
                     ua: dict[str, Any] | None) -> str:
    """The organisations of comparable earlier projects (the call page's partner suggestions, its area rule and topic words), the
    preferred country first; with --ukraine, the Ukrainian organisations of the area and those of EU projects since 2021 with the
    coordinators that already worked with them."""
    area = found.get("area")
    parts = []
    if not area:
        parts.append(f"<p>{e(found.get('note') or 'No earlier projects can be compared with this call.')}</p>")
    else:
        words = ", ".join(area.get("topicWords") or [])
        parts.append(f"<p>Comparable projects: {e(area['label'])}, {e(area['projects'])} projects "
                     f"({e(area.get('firstYear'))} to {e(area.get('lastYear'))}), {e(area['organisations'])} organisations. {e(area['rule'])}"
                     + (f" Organisations whose projects share a topic word of the call's title ({e(words)}) come first." if words else "")
                     + (f" Organisations established in {e(country)} are listed first." if country else "") + "</p>")
        if found.get("note"):
            parts.append(f"<p>{e(found['note'])}</p>")
        parts.append(partner_rows(found.get("partners") or []))
        if country and not any(p.get("country") == country for p in found.get("partners") or []):
            parts.append(f"<p>No organisation established in {e(country)} took part in a comparable project.</p>")
    if ua_area is not None:
        n = ua_area.get("total") or 0
        parts.append("<h3>Ukrainian organisations</h3>")
        parts.append(f"<p>In the comparable projects: {n} organisation{'s' if n != 1 else ''} established in Ukraine.</p>"
                     + (partner_rows(ua_area.get("partners") or []) if n else ""))
    if ua is not None:
        orgs = [u for u in ua.get("ukrainianOrganisations") or [] if (u.get("organisation") or {}).get("slug")][:UA_ROWS]
        coords = [c for c in ua.get("coordinators") or [] if (c.get("organisation") or {}).get("slug")][:UA_ROWS]
        parts.append(f"<p>In all EU-funded projects since {e(ua.get('since'))} (mostly Horizon Europe, not this call's area): "
                     f"{e((ua.get('totals') or {}).get('ukrainianOrganisations'))} Ukrainian organisations took part.</p>")
        if orgs:
            parts.append("<table class=\"list\"><tr><th>Ukrainian organisation</th><th>Projects</th><th>Defence or dual-use projects</th>"
                         "<th>Coordinated</th><th>Last year</th></tr>" + "".join(
                f"<tr class=\"report-row\"><td>{link(site('/organisations/' + u['organisation']['slug']), u['organisation']['name'])}</td>"
                f"<td>{e(u.get('projects'))}</td><td>{e(u.get('relevantProjects'))}</td><td>{e(u.get('coordinated'))}</td>"
                f"<td>{e(u.get('lastYear'))}</td></tr>" for u in orgs) + "</table>")
        if coords:
            parts.append("<p>EU coordinators that already had a Ukrainian participant, defence projects first:</p>"
                         "<table class=\"list\"><tr><th>Coordinator</th><th>Country</th><th>Projects with a Ukrainian participant</th>"
                         "<th>Defence / dual-use</th><th>Ukrainian participants</th></tr>" + "".join(
                f"<tr class=\"report-row\"><td>{link(site('/organisations/' + c['organisation']['slug']), c['organisation']['name'])}</td>"
                f"<td>{e(c['organisation'].get('country'))}</td><td>{e(c.get('projects'))}</td>"
                f"<td>{e(c.get('defenceProjects'))} / {e(c.get('dualUseProjects'))}</td><td>"
                + "; ".join(e(x["organisation"]["name"]) for x in c.get("ukrainianParticipants") or [] if (x.get("organisation") or {}).get("slug"))
                + "</td></tr>" for c in coords) + "</table>")
        parts.append(f"<p>{e(ua.get('definition') or '')}</p>")
    return section("s-partners", "3. Matching organisations", "\n".join(parts))


# ------------------------------------------------------------------ 4 consortium gaps
def sample_ids(found: dict[str, Any], n: int = SAMPLE) -> list[str]:
    """The comparable projects the partner list names as evidence, in its order (topical projects first), at most n."""
    ids: list[str] = []
    for p in found.get("partners") or []:
        for x in p.get("evidence") or []:
            if x["projectId"] not in ids:
                ids.append(x["projectId"])
    return ids[:n]


def typical(projects: list[dict[str, Any]]) -> dict[str, Any] | None:
    """The typical consortium of the comparable projects: members and countries (median, range), the coordinators' countries and how
    often each country is present. Counts only; members whose name is not shown count, unnamed."""
    if not projects:
        return None
    members = [p["memberCount"] for p in projects]
    countries = [p["countryCount"] for p in projects]
    presence: Counter[str] = Counter()
    for p in projects:
        presence.update({(m.get("organisation") or {}).get("country") for m in p.get("members") or []} - {None})
    coord = Counter((p.get("coordinator") or {}).get("country") for p in projects if (p.get("coordinator") or {}).get("country"))
    return {"projects": len(projects), "members": (statistics.median(members), min(members), max(members)),
            "countries": (statistics.median(countries), min(countries), max(countries)),
            "presence": [(c, k / len(projects)) for c, k in sorted(presence.items(), key=lambda kv: (-kv[1], kv[0]))],
            "coordinators": coord.most_common()}


def _int(f: dict[str, Any] | None) -> int | None:
    v = (f or {}).get("value")
    return v if isinstance(v, int) and not isinstance(v, bool) else None


def gaps(call: dict[str, Any], typ: dict[str, Any] | None, members: list[dict[str, Any]]) -> list[str]:
    """What a given consortium lacks against the call's own minimum and the comparable projects, one plain sentence each."""
    facts = ((call.get("documentEligibility") or {}).get("facts")) or {}
    countries = {m.get("country") for m in members} - {None}
    out = []
    need_n, need_c = _int(facts.get("min_entities")), _int(facts.get("min_countries"))
    if need_n and len(members) < need_n:
        out.append(f"The call document asks for at least {need_n} legal entities; the consortium has {len(members)}.")
    if need_c and len(countries) < need_c:
        out.append(f"The call document asks for entities from at least {need_c} countries; the consortium has {len(countries)}.")
    if typ:
        med_n, med_c = typ["members"][0], typ["countries"][0]
        if len(members) < med_n:
            out.append(f"Comparable projects had a median of {med_n:g} members; the consortium has {len(members)} (indicative).")
        if len(countries) < med_c:
            out.append(f"Comparable projects had a median of {med_c:g} countries; the consortium has {len(countries)} (indicative).")
        usual = [c for c, share in typ["presence"] if share >= COMMON and c not in countries]
        if usual:
            out.append("Countries present in at least half of the comparable projects and missing from the consortium: "
                       + ", ".join(usual) + " (indicative).")
    if members and not any((m.get("coordinated") or 0) > 0 for m in members):
        out.append("No member has coordinated an EU-funded project in our data.")
    if call.get("programme") == "EDIP-USI" and "UA" not in countries:
        out.append("No member is established in Ukraine. This is a Ukraine Support Instrument call: check section 6 of the call document "
                   "for what it asks of Ukrainian participation.")
    return out


def section_gaps(call: dict[str, Any], projects: list[dict[str, Any]], members: list[dict[str, Any]] | None) -> str:
    facts = ((call.get("documentEligibility") or {}).get("facts")) or {}
    parts = ["<h3>What the call asks</h3>"]
    rule = next((r["value"] for r in call.get("eligibility") or [] if r.get("label") == "Minimum consortium"), None)
    asked = [f"<li>Minimum consortium: {e(rule)}</li>"] if rule else []
    for key in ("consortium_required", "required_partners"):
        f = facts.get(key)
        if f and f.get("value") is not None:
            label = dict(FACT_LABELS)[key]
            asked.append(f"<li>{e(label)}: {e(fact_value(f['value']))}{'. ' + e(f['note']) if f.get('note') else ''}"
                         f"{' <q>' + e(f['quote']) + '</q>' if f.get('quote') else ''}</li>")
    parts.append(f"<ul>{''.join(asked)}</ul>" if asked else "<p>The rules we hold state no consortium requirement for this call.</p>")
    typ = typical(projects)
    parts.append("<h3>Typical consortium of comparable projects <span class=\"tag\">EDF/CORDIS data, indicative</span></h3>")
    if typ:
        mn, cn = typ["members"], typ["countries"]
        top = ", ".join(f"{c} {share:.0%}" for c, share in typ["presence"][:10])
        coords = ", ".join(f"{c} {k}" for c, k in typ["coordinators"][:6])
        parts.append(f"<ul><li>{typ['projects']} comparable projects read (the evidence projects of section 3).</li>"
                     f"<li>Members: median {mn[0]:g}, from {mn[1]} to {mn[2]}.</li>"
                     f"<li>Countries: median {cn[0]:g}, from {cn[1]} to {cn[2]}.</li>"
                     f"<li>Coordinators established in: {e(coords) or 'not stated'}.</li>"
                     f"<li>Share of the projects with a participant from: {e(top)}.</li></ul>"
                     "<p>This describes what earlier consortia looked like, not what the call requires.</p>")
    else:
        parts.append("<p>No comparable project to describe.</p>")
    if members is None:
        parts.append("<p>No consortium was given. Name its members (their DefenceGate organisation pages) for a gap check against the "
                     "call and the comparable projects.</p>")
    else:
        parts.append("<h3>The consortium</h3><table class=\"list\"><tr><th>Member</th><th>Country</th><th>EU projects</th>"
                     "<th>Coordinated</th></tr>" + "".join(
            f"<tr class=\"report-row\"><td>{link(site('/organisations/' + m['slug']), m['name'])}</td><td>{e(m.get('country'))}</td>"
            f"<td>{e(m.get('projects'))}</td><td>{e(m.get('coordinated'))}</td></tr>" for m in members) + "</table>")
        found = gaps(call, typ, members)
        parts.append("<h3>Gaps</h3>" + (f"<ul>{''.join(f'<li>{e(g)}</li>' for g in found)}</ul>" if found
                                        else "<p>None found against the call's stated minimum and the comparable projects.</p>"))
    return section("s-gaps", "4. Consortium gaps", "\n".join(parts))


# ------------------------------------------------------------------ 5 method and limits
def section_method(call: dict[str, Any], found: dict[str, Any], sample: int) -> str:
    src = call.get("source") or {}
    psrc = found.get("source") or {}
    read = call.get("documentEligibility") or {}
    items = [
        f"The call: {e(src.get('sourceName'))}, retrieved {e(day(src.get('retrievedAt')))}; licence: {e(src.get('licence'))}.",
        (f"Eligibility: read automatically from the call document on {e(day(read.get('extractedAt')))}; each fact is quoted. "
         "The document is authoritative." if read else "Eligibility: no reading of the call's rules is held."),
        "Ukraine: the call's flag and its evidence (a sentence of the call document, the regulation or the Commission's statement).",
        (f"Organisations: {e(', '.join(psrc.get('sources') or []))}, read {e(day(psrc.get('readAt')))}; licence: {e(psrc.get('licence'))}. "
         "The EDF factsheets are read by a language model; every name is checked against the factsheet text."),
        f"Typical consortium: {sample} comparable projects (the evidence projects of section 3), indicative only.",
        "Country is the country of establishment the source states. Past roles count every EU-funded project in our data "
        "(CORDIS and the EDF factsheets).",
        "Organisations only: natural persons are never named, organisations removed on request are left out. No contact data, "
        "no technical description of any system.",
        e(DISCLAIMER),
    ]
    return section("s-method", "5. Method and limits", "<ul>" + "".join(f"<li>{i}</li>" for i in items) + "</ul>")


# ------------------------------------------------------------------ the document
CSS = """
:root { color-scheme: light; }
body { font: 11pt/1.45 system-ui, -apple-system, "Segoe UI", Roboto, Arial, sans-serif; color: #1a1a1a; background: #fff;
       max-width: 60rem; margin: 0 auto; padding: 1.5rem 1rem; }
h1 { font-size: 20pt; margin: 0 0 .25rem; } h2 { font-size: 15pt; margin: 0 0 .5rem; border-bottom: 2px solid #1a1a1a; }
h3 { font-size: 12pt; margin: 1rem 0 .3rem; } .lead { font-weight: 600; font-size: 12pt; }
.report-section { margin: 1.5rem 0; } table { border-collapse: collapse; width: 100%; margin: .5rem 0; }
th, td { text-align: left; vertical-align: top; padding: .3rem .4rem; border-bottom: 1px solid #ccc; overflow-wrap: anywhere; }
table.facts th { width: 28%; } table.list { font-size: 9.5pt; } q { font-style: italic; }
.verdict { border: 1.5px solid currentColor; border-radius: 999px; padding: 0 .5rem; }
.tag { font-size: 9pt; font-weight: 400; border: 1px solid #888; border-radius: 4px; padding: 0 .3rem; }
.meta, footer { color: #555; font-size: 9.5pt; } footer { margin-top: 2rem; border-top: 1px solid #ccc; padding-top: .5rem; }
a { color: #0b4f9c; }
@media print {
  @page { size: A4; margin: 16mm 14mm; }
  body { max-width: none; padding: 0; font-size: 10.5pt; }
  .report-section + .report-section { break-before: page; }
  .report-row, li { break-inside: avoid; }
  a[href^="http"]::after { content: " (" attr(href) ")"; font-size: 8pt; color: #555; overflow-wrap: anywhere; }
}
"""


def render(call: dict[str, Any], body: list[str], today: date) -> str:
    title = f"Pilot report: {call['title']}"
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(title)}</title><style>{CSS}</style></head>
<body><main class="report">
<header><p class="meta">DefenceGate pilot report · {e(call.get('topicId'))}</p><h1>{e(call['title'])}</h1>
<p><b>{e(DISCLAIMER)}</b></p></header>
{chr(10).join(body)}
<footer>Pilot report, prepared by DefenceGate on {today.day} {today:%B %Y}.</footer>
</main></body></html>
"""


def build(src, ref: str, *, country: str | None = None, ukraine: bool = False, consortium: list[str] | None = None,
          today: date | None = None) -> str:
    call = src.call(ref)
    found = src.partners(call["id"], prefer=country)
    ids = sample_ids(found)
    projects = [src.project(i) for i in ids]
    members = None
    if consortium:
        members = []
        for slug in consortium:
            o = src.organisation(slug)
            members.append({"slug": o["slug"], "name": o["name"], "country": o.get("country"),
                            "projects": (o.get("counts") or {}).get("projects"), "coordinated": (o.get("counts") or {}).get("coordinated")})
    ua_area = src.partners(call["id"], country="UA") if ukraine and found.get("area") else None
    ua = src.ukraine_partners() if ukraine else None
    body = [section_call(call), section_who(call),
            section_partners(found, country=country, ua_area=ua_area, ua=ua),
            section_gaps(call, projects, members), section_method(call, found, len(projects))]
    return render(call, body, today or datetime.now(timezone.utc).date())


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m dgate.ops.pilot_report", description=__doc__.split("\n\n")[0])
    ap.add_argument("--call", required=True, help="the call's id, slug or topic code (EDF-EDIP-USI-2027-LS-IRA-CUXS)")
    ap.add_argument("--country", type=str.upper, default=None, help="ISO-2: list this country's organisations first")
    ap.add_argument("--ukraine", action="store_true", help="add Ukrainian organisations and the EU partners they worked with")
    ap.add_argument("--consortium", default="", help="comma-separated organisation slugs of a consortium to check for gaps")
    ap.add_argument("--out", type=Path, default=None)
    a = ap.parse_args(argv)
    consortium = [s.strip() for s in a.consortium.split(",") if s.strip()]
    with db.connect(settings().dsn) as conn:
        conn.execute("SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY")
        conn.execute("SET statement_timeout = '30s'")
        try:
            doc = build(Db(conn), a.call, country=a.country, ukraine=a.ukraine, consortium=consortium)
        finally:
            conn.rollback()
    if a.out:
        a.out.write_text(doc, encoding="utf-8")
        print(f"written {a.out} ({len(doc)} characters)")
    else:
        sys.stdout.buffer.write(doc.encode("utf-8"))     # a redirect to a file is UTF-8 whatever the locale
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
