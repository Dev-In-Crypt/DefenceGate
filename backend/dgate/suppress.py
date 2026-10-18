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


def removed() -> HTTPException:
    """The answer for the detail URL of something removed on request: 410, neutral."""
    return HTTPException(410, REMOVED)


def not_published() -> HTTPException:
    """The answer for the detail URL of an organisation that is a natural person: 410, neutral."""
    return HTTPException(410, NOT_PUBLISHED)


def withheld(row: dict[str, Any] | None) -> bool:
    return bool(row and row.get("buyer_withheld"))
