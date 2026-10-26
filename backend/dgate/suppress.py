"""What the public read side says about a notice, buyer or call removed on request.

The decision lives in the `suppression` table (migration 0047) and is applied to the
serving rows as flags by database triggers, so every public query needs only
`NOT o.suppressed` (and `NOT o.buyer_withheld` where a buyer is aggregated). The
archive (`opportunity_version`) is never touched. The owner's CLI is `ops/suppress.py`.
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException

WITHHELD_NAME = "Name withheld on request"
REMOVED = "removed on request"
# An organisation the directory treats as a natural person (`individuals.py`): nobody asked, so the words
# differ; inside someone else's consortium its name is not shown either.
INDIVIDUAL_NAME = "Name not shown"
NOT_PUBLISHED = "not published"


# WP-143 (owner, 26 October 2026): a buyer withheld because it is a natural person (`ops.person_rows`: a suppression entry of reason
# `natural_person`, nobody asked) is not "withheld on request". The words the owner chose, for its name and for its page.
PERSON_NAME = "Name not shown: it identifies a private person."


def person_withheld(conn, org_ids) -> set[int]:
    """Of these organisations, the ones the data treats as a natural person (`organisation.individual_reason`, set by
    `ops.person_rows` and `ops.mark_individuals`). Read from `organisation` because the API role may not read `suppression`
    (who asked is not the read side's business); an entry made on a request (`ops.suppress add`) leaves the reason empty
    and keeps the words of a request."""
    ids = sorted({int(i) for i in org_ids if i})
    if not ids:
        return set()
    return {r["id"] for r in conn.execute(
        "SELECT id FROM organisation WHERE id = ANY(%s) AND individual_reason IS NOT NULL", (ids,)).fetchall()}


def withheld_buyer_name(r: dict[str, Any]) -> str | None:
    """The buyer name of an award row (`suppliers._award_rows`): as published; None when withheld on request (the page says
    so); PERSON_NAME when withheld as a natural person (`buyer_person`)."""
    if not r.get("buyer_withheld"):
        return r.get("buyer_name_raw")
    return PERSON_NAME if r.get("buyer_person") else None


def not_shown_person() -> HTTPException:
    """The answer for the buyer page of an organisation withheld as a natural person: 410, with the owner's words."""
    return HTTPException(410, PERSON_NAME)


def removed() -> HTTPException:
    """The answer for the detail URL of something removed on request: 410, neutral."""
    return HTTPException(410, REMOVED)


def not_published() -> HTTPException:
    """The answer for the detail URL of an organisation that is a natural person: 410, neutral."""
    return HTTPException(410, NOT_PUBLISHED)


def withheld(row: dict[str, Any] | None) -> bool:
    return bool(row and row.get("buyer_withheld"))
