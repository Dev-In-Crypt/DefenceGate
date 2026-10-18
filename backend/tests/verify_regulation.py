"""Checks every quote of seeds/regulation_tracker.json against the text of its source.

Not a test of the suite (it needs the sources, fetched by hand and saved as text in one directory): run it by
hand when the seed changes.

    python verify_regulation.py <seed.json> <directory>

The directory holds <CELEX>.txt for each Official Journal text (fetched from the Publications Office, CELLAR),
and oeil-<procedure number without slashes>.txt / page-<last path part of the URL>.txt for the other sources.
Exit 0 only if every quote is found word for word (whitespace and quotation marks aside).
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path


def norm(text: str) -> str:
    text = text.replace("\xa0", " ").replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    text = re.sub(r"\s+", " ", text)
    # the Official Journal text puts a space before a full stop after a link: "Union ."
    return re.sub(r" ([.,;:])", lambda m: m.group(1), text).strip().lower()


def source_file(url: str) -> str:
    if m := re.search(r"/resource/celex/([0-9A-Z]+)$", url):
        return f"{m.group(1)}.txt"
    if m := re.search(r"reference=(\d{4})/(\d{4})", url):
        return f"oeil-{m.group(1)}{m.group(2)}.txt"
    return "page-" + url.rstrip("/").rsplit("/", 1)[-1] + ".txt"


def main(seed_path: str, directory: str) -> int:
    entries = json.loads(Path(seed_path).read_text(encoding="utf-8"))["entries"]
    bad = 0
    for e in entries:
        name = source_file(e["source_url"])
        path = Path(directory) / name
        if not path.exists():
            print(f"MISSING SOURCE {e['code']}: {name}")
            bad += 1
            continue
        found = norm(e["source_quote"]) in norm(path.read_text(encoding="utf-8", errors="replace"))
        print(f"{'ok  ' if found else 'FAIL'} {e['code']}  ({name})")
        bad += 0 if found else 1
    print(f"{len(entries) - bad} of {len(entries)} quotes found")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:3]))
