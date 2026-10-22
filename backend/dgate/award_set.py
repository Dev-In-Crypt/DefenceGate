"""The award set (WP-85, owner decision of 22 October 2026: align the supplier map with the supplier report).

One definition of the award rows that the supplier map (`suppliers.py`: /v1/suppliers, /v1/suppliers/summary,
/v1/suppliers/{slug}) and the supplier report's demand answer (`demand.py`: /v1/readiness/demand,
/v1/readiness/winners) count. Both build on this module and repeat none of it, so a company named in "who to
approach" has a supplier page, and the map filtered by the same buyer countries and CPV codes gives it the same
number of contracts.

An award row is in the set when

- its notice is in the defence scope (`is_defence`, every signal, not only the core scope), not removed on request,
  and published in the last three years, rolling (`YEARS`, from `since(today)`; the publication date, else the
  notice date);
- its winner is a legal entity: not removed on request, not a natural person or sole trader (`individual_reason`:
  such a winner is counted where a count of persons is given, never named, listed or summed), not a winner string
  that is no supplier (`excluded_reason`), the row not superseded;
- it is from TED, or from PLACSP's award results while DGATE_PLACSP_AWARDS_PUBLIC is on; then an award that TED and
  PLACSP both publish counts once, under the row `award_twin_set` prefers, when that row is in the set (`NOT_TWIN`).

The unit counted is the procurement (`KEY`): one procurement published in several notices (TED and a national portal,
two result notices of one procedure, the two Polish sources of one notice) counts once.

Filters narrow the set and never decide which of two twins stands (the twin test is over the whole set): the buyer's
country (`o.country`), a CPV code of the notice, any of them, under a prefix (`CPV_MATCH`, `prefix`), the supplier.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone

from .config import settings

YEARS = 3


def since(today: date | None = None) -> date:
    """The first day of the window: three years back from `today` (UTC today by default)."""
    today = today or datetime.now(timezone.utc).date()
    return today - timedelta(days=round(365.25 * YEARS))


PLACSP_SOURCES = ("es_placsp", "es_placsp_agg")
PLACSP_IDS = "(SELECT id FROM source WHERE code IN (" + ", ".join(f"'{c}'" for c in PLACSP_SOURCES) + "))"
NOT_PLACSP = f"o.source_id NOT IN {PLACSP_IDS}"

# The rows, under the aliases every condition below is written over; `t` is the TED notice a national notice was
# forwarded as (for `KEY`).
FROM = """FROM award a
          JOIN opportunity o ON o.id = a.opportunity_id
          JOIN organisation raw_org ON raw_org.id = a.organisation_id
          JOIN organisation org ON org.id = COALESCE(raw_org.merged_into, raw_org.id)
          LEFT JOIN opportunity t ON o.ted_ref IS NOT NULL AND t.native_id = o.ted_ref
                                 AND t.source_id = (SELECT id FROM source WHERE code = 'ted')"""

# The notices: defence scope, not removed, in the window (`%(since)s`). Partial indexes on the defence scope apply.
NOTICES = "o.is_defence AND NOT o.suppressed AND COALESCE(o.published_at, o.notice_date) >= %(since)s"
# The winners: legal entities, not removed, not superseded, not a placeholder string (migration 0080,
# `ops/clean_suppliers.py`), not a natural person (`individuals.py`).
WINNERS = ("NOT org.suppressed AND NOT raw_org.suppressed AND a.excluded_reason IS NULL AND a.superseded_at IS NULL "
           "AND org.individual_reason IS NULL AND raw_org.individual_reason IS NULL")
BASE = f"{NOTICES} AND {WINNERS}"

# Any CPV code of the notice under one of the prefixes `%(prefixes)s` (index `opp_cpv_heads`, migration 0099).
CPV_MATCH = "dgate_cpv_heads(o.cpv_codes) && %(prefixes)s::text[]"

# One procurement, however many notices publish it: the eForms procedure identifier (of the notice, or of the TED
# notice a national notice was forwarded as), else the TED publication number, else the national number within its
# country (the two Polish sources share it). Over `o` and `t` of FROM.
KEY = """COALESCE('p:' || COALESCE(o.procedure_identifier, t.procedure_identifier),
                  'ted:' || COALESCE(o.ted_ref, CASE WHEN o.source_id = (SELECT id FROM source WHERE code = 'ted')
                                                     THEN o.native_id END),
                  o.country || ':' || o.native_id)"""
KEY_HASH = f"hashtextextended({KEY}, 0)"


def prefix(code: str) -> str:
    """The leading part a code stands for, by its level in the CPV tree: the code without its trailing zeros,
    never shorter than its division (34300000 -> 343, 44470000 -> 4447, 35000000 -> 35, 10000000 -> 10)."""
    head = code.rstrip("0")
    return head if len(head) >= 2 else code[:2]


_ALIASES = {"a": "k", "o": "ko", "org": "korg", "raw_org": "kraw"}


def _as_preferred(cond: str) -> str:
    """`cond`, written over FROM's aliases, rewritten over the preferred twin's."""
    return re.sub(r"\b(raw_org|org|o|a)\.", lambda m: _ALIASES[m[1]] + ".", cond)


# An award published in TED and in PLACSP counts once (WP-61, migration 0093): a row is left out when `award_twin_set`
# (migration 0098, rewritten by `awards.refresh_award_twins` after every award load) names a row preferred over it that
# is itself in the set. Uncorrelated, so the planner reads the pairs once per statement and hashes them (WP-75).
NOT_TWIN = ("a.id NOT IN (SELECT tw.award_id FROM award_twin_set tw JOIN award k ON k.id = tw.preferred_id "
            "JOIN opportunity ko ON ko.id = k.opportunity_id JOIN organisation kraw ON kraw.id = k.organisation_id "
            "JOIN organisation korg ON korg.id = COALESCE(kraw.merged_into, kraw.id) "
            f"WHERE {_as_preferred(BASE)})")


def scope() -> str:
    """The SQL condition of the set over FROM's aliases (parameter `%(since)s`): BASE, and without the PLACSP winners
    unless they are switched on; with them on, a TED+PLACSP twin once (`NOT_TWIN`)."""
    return f"{BASE} AND {NOT_TWIN}" if settings().placsp_awards_public else f"{BASE} AND {NOT_PLACSP}"
