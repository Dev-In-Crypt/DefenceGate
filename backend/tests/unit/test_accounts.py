"""Pure parts of the account module: addresses, filters, route keys."""

from __future__ import annotations

import pytest

from dgate import accounts


@pytest.mark.parametrize("raw", ["A@x.com", "a@X.com", " a@x.com ", "a@x.com."])
def test_one_address_has_one_canonical_form(raw):
    assert accounts.canonical_email(raw)[0] == "a@x.com"


def test_gmail_dots_and_plus_tags_are_the_same_mailbox_and_other_domains_keep_dots():
    assert accounts.canonical_email("J.Smith+rfp@googlemail.com")[0] == "jsmith@gmail.com"
    assert accounts.canonical_email("j.smith+rfp@outlook.com")[0] == "j.smith@outlook.com"
    # at an ordinary company domain a plus tag or a dot may be a different mailbox
    assert accounts.canonical_email("j.smith+rfp@example.com")[0] == "j.smith+rfp@example.com"


def test_an_idn_domain_is_stored_as_punycode():
    assert accounts.canonical_email("a@bücher.de")[0] == "a@xn--bcher-kva.de"


@pytest.mark.parametrize("raw", ["", "no-at", "a@@x.com", "a b@x.com", "a@x", ".a@x.com", "a..b@x.com",
                                 "a@x.com\r\nBcc: v@x.com", "x" * 300 + "@x.com", "a@-.com"])
def test_a_non_address_is_refused(raw):
    with pytest.raises(ValueError):
        accounts.canonical_email(raw)


def test_filters_keep_only_the_public_parameters_and_check_each():
    ok = accounts.clean_filters("tender", {"q": " drone ", "country": "PL,DE", "min": 100, "from": "2026-10-01",
                                           "currency": "eur", "status": "open", "cpv": ""})
    assert ok == {"q": "drone", "country": "PL,DE", "min": "100", "from": "2026-10-01",
                  "currency": "eur", "status": "open"}


@pytest.mark.parametrize("kind,filters", [
    ("tender", {"sql": "1"}),                        # not a parameter
    ("tender", {"status": "everything"}),            # not in the enum
    ("tender", {"from": "yesterday"}),
    ("tender", {"min": "-1"}),
    ("tender", {"buyer": "1; drop table"}),
    ("tender", {"q": "x" * 101}),
    ("call", {"programme": "x" * 201}),
    ("call", {"sort": "published-desc"}),            # a tender sort
    ("tender", {"q": {"nested": 1}}),
])
def test_a_bad_filter_is_refused(kind, filters):
    with pytest.raises(accounts.AccountError) as e:
        accounts.clean_filters(kind, filters)
    assert e.value.status == 422


def test_a_page_not_a_record_is_counted():
    assert accounts.route_key("/tenders/123-armoured-vehicles?x=1") == "/tenders/[slug]"
    assert accounts.route_key("/tenders") == "/tenders"
    assert accounts.route_key("/") == "/"
    assert accounts.route_key("/wp-login.php") == "/other"
    assert accounts.route_key("/auth/verify?token=abc") == "/other"      # a token never becomes a key


def test_a_referrer_is_reduced_to_its_host_and_our_own_is_dropped(monkeypatch):
    from dgate import config
    monkeypatch.setenv("DGATE_SITE_URL", "https://defencegatehub.com")
    config.reset_cache()
    assert accounts.referrer_host("https://www.google.com/search?q=secret+words") == "www.google.com"
    assert accounts.referrer_host("https://defencegatehub.com/tenders") == ""
    assert accounts.referrer_host("not a url") == ""
    config.reset_cache()
