"""Checks every verbatim passage of seeds/requirements.json against its source text.

Not a test of the suite (it needs the Official Journal texts, fetched from the Publications Office
and saved as <CELEX>.txt in one directory, and the technical appendix): run it by hand when the
seed changes.

    python verify_quotes.py <seed.json> <directory with CELEX .txt files> <technical appendix .md>
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path


def norm(text: str) -> str:
    text = text.replace("\xa0", " ").replace("’", "'").replace("‘", "'")
    text = re.sub(r"\*\*|\[[VSU]\]", "", text)
    return re.sub(r"\s+", " ", text).strip().lower()


def main(seed_path: str, texts_dir: str, appendix_path: str) -> int:
    seed = json.loads(Path(seed_path).read_text(encoding="utf-8"))
    appendix = norm(Path(appendix_path).read_text(encoding="utf-8"))
    cache: dict[str, str] = {}
    bad = 0
    checked = 0

    def check(owner: str, passage: dict) -> None:
        nonlocal bad, checked
        text = norm(passage["text"])
        celex = passage.get("celex")
        if celex:
            body = cache.setdefault(celex, norm((Path(texts_dir) / f"{celex}.txt").read_text(encoding="utf-8")))
            # a quote may drop the paragraph number and the "(a)" line breaks of the source
            where = f"OJ {celex}"
        else:
            body, where = appendix, "appendix"
        checked += 1
        if text not in body:
            bad += 1
            print(f"NOT FOUND [{where}] {owner}: {passage['text'][:110]}")

    for r in seed["requirements"]:
        for p in r.get("passages", []):
            check(r["code"], p)
        for v in r.get("variants", []):
            for p in v.get("passages", []):
                check(r["code"] + " variant", p)
    for r in seed["rules"]:
        for p in r.get("passages", []):
            check(r["code"], p)
    print(f"{checked} passages checked, {bad} not found")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:4]))
