"""Link the bulletin's update notices to the notice they update (fields:D15).

A Polish `NoticeUpdateNotice` restates a notice that is listed itself, and the board names
its parent only by the parent's `moIdentifier` (`baseNoticeMOIdentifier`), which no column
holds. Left alone, `status=all` lists a procurement twice (3,025 rows on 13 October 2026).
This reads the stored payload of every pl_ezam notice, finds the notice whose own
`moIdentifier` is the one an update names, and sets `related_native_id` to that notice's
`native_id`, the same link a BOAMP rectificatif has, so the list collapses them the same way.

A link, not a fact the notice changed: written in place, no version, never over a link
already held. A parent that is not stored (not a defence notice) leaves the update
unlinked; nothing is guessed. Idempotent, no request: it reads the raw store only.

    python -m dgate.ops.link_ezam_updates            # report only
    python -m dgate.ops.link_ezam_updates --yes
"""

from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import dataclass

from .. import db
from ..config import settings
from ..rawstore import build_store
from .repair_ted import _chunks, _raw_keys

log = logging.getLogger("link_ezam_updates")

SOURCE = "pl_ezam"


@dataclass
class Result:
    read: int = 0
    naming_a_parent: int = 0      # records that state a base notice
    linked: int = 0               # parent found among the stored notices
    parent_not_stored: int = 0
    failed: int = 0

    def __str__(self) -> str:
        return (f"read {self.read}, naming a parent {self.naming_a_parent}, linked "
                f"{self.linked}, parent not stored {self.parent_not_stored}, "
                f"failed {self.failed}")


def run(*, write: bool = False, batch: int = 500, dsn: str | None = None) -> Result:
    from ..reprocess import _read_batch

    result = Result()
    with db.connect(dsn or settings().dsn) as conn:
        src_id = db.source_id(conn, SOURCE)
        held = {r["native_id"]: r["related_native_id"] for r in conn.execute(
            "SELECT native_id, related_native_id FROM opportunity WHERE source_id = %s",
            (src_id,)).fetchall()}
        keys = _raw_keys(conn, src_id, list(held))
        store = build_store()
        ordered = sorted(keys, key=lambda n: keys[n])
        mo_to_native: dict[str, str] = {}
        names_parent: dict[str, str] = {}
        for chunk in _chunks(ordered, batch):
            for number, payload in zip(
                    chunk, _read_batch(store, [keys[n] for n in chunk], 1, 4, 10.0),
                    strict=True):
                if isinstance(payload, Exception) or not isinstance(payload, dict):
                    result.failed += 1
                    continue
                result.read += 1
                own = payload.get("moIdentifier")
                if own:
                    mo_to_native.setdefault(str(own), number)
                base = payload.get("baseNoticeMOIdentifier")
                if base:
                    names_parent[number] = str(base)
        result.naming_a_parent = len(names_parent)
        for number, base in names_parent.items():
            parent = mo_to_native.get(base)
            if parent is None or parent == number:
                result.parent_not_stored += 1
                continue
            if held.get(number) is not None:
                continue                       # a link already held is never replaced
            result.linked += 1
            if write:
                conn.execute(
                    """UPDATE opportunity SET related_native_id = %s
                        WHERE source_id = %s AND native_id = %s AND related_native_id IS NULL""",
                    (parent, src_id, number))
        if write:
            conn.commit()
        else:
            conn.rollback()
    return result


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    p = argparse.ArgumentParser(prog="link-ezam-updates", description=__doc__.split("\n\n")[0])
    p.add_argument("--yes", action="store_true", help="write the links (default: report)")
    a = p.parse_args(argv)
    result = run(write=a.yes)
    print(result)
    return 0 if result.failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
