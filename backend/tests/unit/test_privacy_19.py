"""Privacy 1.9 (11 November 2026): section 12 on e-mails we send to organisations (cold outreach), Google Workspace as
the mailbox processor, and a static copy of the text in docs/legal/versions."""

from __future__ import annotations

from pathlib import Path

from dgate import accounts

ROOT = Path(__file__).resolve().parents[3]
PAGE = ROOT / "web" / "app" / "(public)" / "privacy" / "page.tsx"


def test_privacy_19_describes_outreach_mail_and_its_opt_out():
    assert accounts.PRIVACY_VERSION == "1.9"
    text = PAGE.read_text(encoding="utf-8")
    assert 'lead="Version 1.9, published 11 November 2026 (e-mails we send to organisations, section 12).' in text
    assert '<Clause n={12} title="E-mails we send to organisations">' in text
    for must in ("Art. 6(1)(f) GDPR", "Art. 21(2) and (3) GDPR", "do-not-contact list", "12 months after our last message",
                 "no tracking pixel and no link tracking", "We do not buy lists", "'Google (Google Workspace), as a processor"):
        assert must in text, must
    assert (ROOT / "docs" / "legal" / "versions" / "privacy-v1.9-2026-11-11.md").is_file()
