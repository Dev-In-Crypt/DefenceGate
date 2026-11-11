"""WP-148: privacy 1.8 (26 October 2026) publishes the owner-approved Cloudflare wording
(docs/legal/drafts/privacy-cloudflare-draft.md): Cloudflare as processor, the DPF sentence as approved, no United States
in the Cloudflare sentences, and the sovereignty page no longer says Cloudflare is not a proxy."""

from __future__ import annotations

from pathlib import Path

from dgate import accounts

ROOT = Path(__file__).resolve().parents[3]
PAGES = ROOT / "web" / "app" / "(public)"
DPF = ("'Cloudflare, Inc., as a processor: domain name service, network security and content delivery for all requests to the "
       "site (section 2). Where data is processed outside the EEA, the transfer is based on the EU-US Data Privacy Framework "
       "(Art. 45 GDPR).',")


def test_privacy_18_names_cloudflare_as_processor_without_the_united_states():
    assert accounts._version(accounts.PRIVACY_VERSION) >= accounts._version("1.8")   # 1.9 keeps the Cloudflare text
    assert accounts._version(accounts.PRIVACY_VERSION) >= accounts._version(accounts.PASSWORD_PRIVACY_VERSION)
    text = (PAGES / "privacy" / "page.tsx").read_text(encoding="utf-8")
    # The 1.8 lead named Cloudflare; 1.9 (11 Nov 2026) has its own lead, so the label is checked in the 1.8 record.
    record = ROOT / "docs" / "legal" / "versions" / "privacy-v1.8-2026-10-26.md"
    assert "(Cloudflare as processor for network security and content delivery)" in record.read_text(encoding="utf-8")
    assert DPF in text
    cloudflare = [line for line in text.splitlines() if "Cloudflare" in line]
    assert len(cloudflare) >= 7, cloudflare            # in short x2, section 2 x2, section 4 x2, section 8 (lead until 1.8)
    for line in cloudflare:
        assert "USA" not in line and "United States" not in line, line
    assert "does not pass through Cloudflare" not in text and "sets no cookie." not in text


def test_sovereignty_says_visitors_pass_through_cloudflare():
    text = (PAGES / "data" / "sovereignty" / "page.tsx").read_text(encoding="utf-8")
    assert "note: 'One virtual server. Visitors reach it through Cloudflare’s proxy (below).'," in text
    assert "what: 'Domain registration, name service (DNS) and the proxy in front of the server'," in text
    assert "It is not a proxy" not in text and "connect to it directly" not in text
    # where and eu of the Cloudflare row unchanged
    assert "who: 'Cloudflare, Inc.', where: 'United States company; DNS answers come from its worldwide network', eu: 'No'," in text
