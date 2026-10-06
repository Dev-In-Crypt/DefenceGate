"""BDNS connector (Spain, Base de Datos Nacional de Subvenciones).

Endpoint:  GET https://www.infosubvenciones.es/bdnstrans/api/convocatorias/busqueda
           GET https://www.infosubvenciones.es/bdnstrans/api/convocatorias?numConv=<n>
Auth:      none
Operator:  Intervencion General de la Administracion del Estado (Ministerio de Hacienda)
Licence:   Aviso legal of the system; public-sector information, personal data excluded

Why this source. Spain publishes no single list of defence R&D grants, but every
subsidy call of every administration has to be registered here: 656,418 calls at
the time of writing, 52,744 of them registered in 2026. Anonymous JSON, with the
fields a supplier decides on -- issuing body, budget, opening and closing dates,
who may apply, the legal basis.

What it is not. It is not the Spanish defence R&D programme: the Ministry of
Defence's technology cooperation lines are contracts, not subsidies, and are not
in here. What is in here, measured on 6 October 2026 over the 1,344 calls central
government registered this year, is the Ministry of Defence's own subsidies (almost
all for personnel, sport and awards), INTA, and the CDTI -- the agency that funds
company R&D, with lines open to any technology SME. The last is why it is worth
collecting: CDTI is where a Spanish defence supplier's dual-use development gets
paid for.

The line this connector does not cross. The legal notice restricts reuse of
*personal data* in the register to control, transparency and research. Calls name
no persons; awards (`concesiones`) do, and are never fetched here.

Two measured properties decided the design.

1. **Search is cheap and shallow, detail is where the call is.** The search row
   carries only the body and a legal-citation description. Budget, dates, who may
   apply and the legal basis are in the detail record, one request each. So the
   search is walked in full -- 1,344 central calls a year, 14 pages -- and the
   detail is fetched only for the few that could be relevant.

2. **The register says who may apply.** `tiposBeneficiarios` separates companies
   (`GRAN EMPRESA`, `PYME ...`) from natural persons without economic activity,
   which is how INTA's scholarships and the Army's sport awards -- both issued
   by the Ministry of Defence -- are told apart from a call a supplier could answer.
"""

from __future__ import annotations

import logging
import re
import time
from datetime import UTC, date, datetime, timedelta
from datetime import time as dtime
from typing import Any, Iterator
from zoneinfo import ZoneInfo

import httpx

from . import USER_AGENT, request_with_retry

log = logging.getLogger(__name__)

SOURCE_CODE = "es_bdns"
API = "https://www.infosubvenciones.es/bdnstrans/api"
SEARCH_URL = f"{API}/convocatorias/busqueda"
DETAIL_URL = f"{API}/convocatorias"
PAGE_SIZE = 100
MAX_PAGES = 100                  # 10,000 rows; a window that reaches it was cut short
REQUEST_PAUSE = 1.0              # the notice reserves the right to restrict abusive access
MADRID = ZoneInfo("Europe/Madrid")

# Bodies whose calls are worth a detail request. The organ is the strongest signal
# the register offers; the sector code is two digits and says "research" or
# "administrative activities" and nothing sharper.
ORGAN = re.compile(
    r"DEFENSA|EJ[EÉ]RCITO|ARMADA|\bINTA\b|T[EÉ]CNICA AEROESPACIAL|"
    r"CENTRO PARA EL DESARROLLO TECNOL|CDTI|AGENCIA ESPACIAL", re.I)

# Of those, the ones under the Ministry of Defence: the regime is `defence`. INTA
# is an agency of the Ministry. CDTI is not: it is the Ministry of Science's, and
# its lines are dual-use at best.
DEFENCE_BODY = re.compile(r"DEFENSA|EJ[EÉ]RCITO|ARMADA|\bINTA\b|T[EÉ]CNICA AEROESPACIAL", re.I)

# Words that make a call from any other body worth a look. Only a reason to spend
# one request: the scope rules below decide, and a false candidate costs a second.
KEYWORD = re.compile(
    r"defens|militar|armament|munici[oó]n|\bdual\b|aeroesp|espacial|naval|"
    r"ciberseg|seguridad nacional|infraestructuras cr[ií]ticas", re.I)

COMPETITIVE = "concurrencia competitiva"      # a call anybody eligible may answer
COMPANY = re.compile(r"EMPRESA|PYME", re.I)   # GRAN EMPRESA, PYME Y PERSONAS FISICAS ...


def day_param(day: date) -> str:
    """The register's own date format. ISO is silently ignored and returns nothing."""
    return day.strftime("%d/%m/%Y")


def search_params(since: date, page: int) -> dict[str, Any]:
    return {"page": page, "pageSize": PAGE_SIZE, "vpd": "GE",
            "tipoAdministracion": "C",              # central government
            "fechaDesde": day_param(since)}


def _client() -> httpx.Client:
    return httpx.Client(headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
                        follow_redirects=True)


def search_central(since: date, *, client: httpx.Client | None = None,
                   max_pages: int = MAX_PAGES) -> Iterator[dict[str, Any]]:
    """Every call central government registered since a date, oldest page last."""
    owns = client is None
    client = client or _client()
    try:
        for page in range(max_pages):
            def send(page: int = page) -> httpx.Response:
                response = client.get(SEARCH_URL, params=search_params(since, page), timeout=90.0)
                response.raise_for_status()
                return response

            payload = request_with_retry(send, attempts=6, max_delay=60.0,
                                         what=f"{SOURCE_CODE} page {page}").json()
            if not isinstance(payload, dict) or "content" not in payload:
                raise ValueError("expected a page of calls with a `content` list; the shape changed")
            yield from payload["content"]
            if payload.get("last") or not payload["content"]:
                return
            time.sleep(REQUEST_PAUSE)
        raise RuntimeError(f"{SOURCE_CODE}: {max_pages} pages and still more; "
                           f"the window was cut short, not complete")
    finally:
        if owns:
            client.close()


def fetch_detail(number: str | int, *, client: httpx.Client | None = None) -> dict[str, Any]:
    owns = client is None
    client = client or _client()
    try:
        def send() -> httpx.Response:
            response = client.get(DETAIL_URL, params={"numConv": number, "vpd": "GE"}, timeout=90.0)
            response.raise_for_status()
            return response

        detail = request_with_retry(send, attempts=6, max_delay=60.0,
                                    what=f"{SOURCE_CODE} call {number}").json()
        if not isinstance(detail, dict) or "organo" not in detail:
            raise ValueError(f"call {number}: no `organo` in the detail record; the shape changed")
        return detail
    finally:
        if owns:
            client.close()


# ------------------------------------------------------------- relevance

def organ_text(record: dict[str, Any]) -> str:
    """The issuing body as one string, from a search row or a detail record."""
    organ = record.get("organo")
    if isinstance(organ, dict):
        parts = (organ.get("nivel2"), organ.get("nivel3"))
    else:
        parts = (record.get("nivel2"), record.get("nivel3"))
    return " / ".join(str(p) for p in parts if p)


def is_candidate(row: dict[str, Any]) -> bool:
    """Worth one detail request: a body that funds defence or company R&D, or words
    that say the call is about it. Deliberately loose; `in_scope` decides."""
    return bool(ORGAN.search(organ_text(row)) or KEYWORD.search(row.get("descripcion") or ""))


def beneficiary_types(detail: dict[str, Any]) -> list[str]:
    return [str(b.get("descripcion", "")).strip()
            for b in detail.get("tiposBeneficiarios") or [] if b.get("descripcion")]


def in_scope(detail: dict[str, Any], *, today: date | None = None) -> bool:
    """A call a supplier could answer, from the right kind of body, still of interest.

    Three rules, each measured against what the register holds:

    * Competitive. `Concesion directa` is a grant to named entities, decided by the
      administration; there is nothing to apply for.
    * Open to companies. Natural persons without economic activity are the INTA
      scholarship and the Army's sport awards.
    * Open now, opening soon, or closed during this year -- the same window as the
      EU calendar, for the same reason: a closed call tells a supplier when the next
      one is likely to open.
    """
    today = today or date.today()
    if COMPETITIVE not in str(detail.get("tipoConvocatoria") or "").lower():
        return False
    if not any(COMPANY.search(b) for b in beneficiary_types(detail)):
        return False
    if not ORGAN.search(organ_text(detail)) and not KEYWORD.search(detail.get("descripcion") or ""):
        return False
    if detail.get("abierto"):
        return True
    closes = _day(detail.get("fechaFinSolicitud"))
    if closes is not None:
        return closes.year == today.year or closes >= today
    received = _day(detail.get("fechaRecepcion"))
    return bool(received and received.year == today.year)


def regime(detail: dict[str, Any]) -> str:
    """`defence` for the Ministry of Defence's own bodies, `dual_use` for the rest."""
    return "defence" if DEFENCE_BODY.search(organ_text(detail)) else "dual_use"


# ---------------------------------------------------------------- the fields

def _day(value: Any) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def opens_at(detail: dict[str, Any]) -> date | None:
    return _day(detail.get("fechaInicioSolicitud"))


def deadline(detail: dict[str, Any]) -> datetime | None:
    """The last day to apply, as the end of that day in Madrid.

    The register gives a date, and a deadline stated as a date means the whole of it.
    Midnight at the start would report a call closed on the day it is still open.
    """
    day = _day(detail.get("fechaFinSolicitud"))
    if day is None:
        return None
    return datetime.combine(day, dtime(23, 59, 59), tzinfo=MADRID).astimezone(UTC)


def status(detail: dict[str, Any], *, today: date | None = None) -> str:
    today = today or date.today()
    if detail.get("abierto"):
        return "open"
    start = opens_at(detail)
    if start and start > today:
        return "forthcoming"
    return "closed"


def call_url(number: str | int) -> str:
    return f"https://www.infosubvenciones.es/bdnstrans/GE/es/convocatorias/{number}"


def eligibility_text(detail: dict[str, Any]) -> str:
    """Who may apply and on what basis, as the sentence a reader wants."""
    parts: list[str] = []
    if beneficiary_types(detail):
        parts.append("Beneficiarios: " + "; ".join(beneficiary_types(detail)) + ".")
    if detail.get("descripcionFinalidad"):
        parts.append(f"Finalidad: {detail['descripcionFinalidad']}.")
    sectors = [s.get("descripcion") for s in detail.get("sectores") or [] if s.get("descripcion")]
    if sectors:
        parts.append("Sectores: " + "; ".join(sectors) + ".")
    if detail.get("descripcionBasesReguladoras"):
        parts.append(f"Bases reguladoras: {detail['descripcionBasesReguladoras']}")
    if detail.get("textFin"):
        parts.append(f"Plazo: {detail['textFin']}")
    return " ".join(parts)


def conditions(detail: dict[str, Any]) -> dict[str, Any]:
    """The structured side of the call, kept whole so nothing is read twice."""
    return {
        "call_type": detail.get("tipoConvocatoria"),
        "instruments": [i.get("descripcion") for i in detail.get("instrumentos") or []],
        "beneficiary_types": beneficiary_types(detail),
        "sectors": [{"code": s.get("codigo"), "name": s.get("descripcion")}
                    for s in detail.get("sectores") or []],
        "regions": [r.get("descripcion") for r in detail.get("regiones") or []],
        "purpose": detail.get("descripcionFinalidad"),
        "state_aid": detail.get("ayudaEstado"),
        "state_aid_url": detail.get("urlAyudaEstado"),
        "regulation": (detail.get("reglamento") or {}).get("descripcion"),
        "legal_basis": detail.get("descripcionBasesReguladoras"),
        "legal_basis_url": detail.get("urlBasesReguladoras"),
        "electronic_office": detail.get("sedeElectronica"),
        "application_start_text": detail.get("textInicio"),
        "application_end_text": detail.get("textFin"),
        "funds": [f.get("descripcion") for f in detail.get("fondos") or []],
        "documents": [d.get("nombreFic") for d in detail.get("documentos") or []
                      if d.get("nombreFic")],
        "published_in_official_gazette": detail.get("sePublicaDiarioOficial"),
    }


def window_start(days: int, today: date | None = None) -> date:
    return (today or date.today()) - timedelta(days=days)
