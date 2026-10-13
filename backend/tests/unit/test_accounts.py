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
    # a known referrer is kept as the allow-list's own name, never as typed (review H1c)
    assert accounts.referrer_host("https://www.google.com/search?q=secret+words") == "google.com"
    assert accounts.referrer_host("https://defencegatehub.com/tenders") == ""
    assert accounts.referrer_host("https://www.defencegatehub.com/") == ""
    assert accounts.referrer_host("not a url") == ""
    config.reset_cache()


@pytest.mark.parametrize("value, stored", [
    ("https://www.google.pl/search?q=x", "google.com"),
    ("https://www.google.co.uk/", "google.com"),
    ("https://www.bing.com/", "bing.com"),
    ("https://duckduckgo.com/", "duckduckgo.com"),
    ("https://l.facebook.com/l.php?u=x", "facebook.com"),
    ("https://t.co/abc", "x.com"),
    ("https://news.ycombinator.com/item?id=1", "news.ycombinator.com"),
    ("https://en.wikipedia.org/wiki/X", "wikipedia.org"),
    ("linkedin.com", "linkedin.com"),                     # the site's counter sends a bare host
    ("", ""),
    ("https://some-newsletter.example/issue-42", "other"),
    ("https://mail.google.evil.example/", "other"),       # a name of ours under someone else's domain
    ("https://webmail.example.eu/message/9f3a", "other"),
])
def test_a_referrer_outside_the_allow_list_is_other_so_the_table_cannot_grow(value, stored, monkeypatch):
    from dgate import config
    monkeypatch.setenv("DGATE_SITE_URL", "https://defencegatehub.com")
    config.reset_cache()
    assert accounts.referrer_host(value) == stored
    config.reset_cache()


def test_five_hundred_distinct_referrer_hosts_are_one_value(monkeypatch):
    from dgate import config
    monkeypatch.setenv("DGATE_SITE_URL", "https://defencegatehub.com")
    config.reset_cache()
    assert {accounts.referrer_host(f"https://r{n}.host{n}.example/p") for n in range(500)} == {"other"}
    config.reset_cache()


# ---------------------------------------------------------------- internal boundary (review M1)

def _request(headers: dict[str, str]):
    from starlette.requests import Request
    return Request({"type": "http", "method": "GET", "path": "/v1/account/me", "query_string": b"",
                    "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()]})


@pytest.mark.parametrize("headers", [{"Origin": ""}, {"X-Forwarded-For": ""}, {"Origin": "https://x.test"}])
def test_an_empty_origin_or_forwarded_for_header_is_refused_too(headers, monkeypatch):
    from dgate import config
    monkeypatch.delenv("DGATE_INTERNAL_SECRET", raising=False)
    config.reset_cache()
    with pytest.raises(accounts.AccountError) as e:
        accounts.internal_only(_request(headers))
    assert e.value.status == 403
    accounts.internal_only(_request({}))             # no secret set: today's behaviour


def test_with_a_secret_set_the_site_must_present_it(monkeypatch):
    from dgate import config
    monkeypatch.setenv("DGATE_INTERNAL_SECRET", "s3cret-value")
    config.reset_cache()
    for headers in ({}, {"X-DG-Internal": ""}, {"X-DG-Internal": "wrong"}, {"X-DG-Internal": "s3cret-valuf"},
                    {"X-DG-Internal": "s3cret-value", "Origin": "https://x.test"},
                    {"X-DG-Internal": "s3cret-value", "X-Forwarded-For": ""}):
        with pytest.raises(accounts.AccountError) as e:
            accounts.internal_only(_request(headers))
        assert e.value.status == 403, headers
    accounts.internal_only(_request({"X-DG-Internal": "s3cret-value"}))
    config.reset_cache()


# ---------------------------------------------------------------- throttle keys (review M7)

def test_a_throttle_key_is_a_keyed_hmac_not_a_plain_hash(monkeypatch):
    import hashlib

    from dgate import config
    monkeypatch.setenv("DGATE_INTERNAL_SECRET", "key-one")
    config.reset_cache()
    one = accounts._event_key("addr", "ann@example.com")
    assert len(one) == 32
    assert one != hashlib.sha256(b"ann@example.com").digest()
    assert one != accounts._event_key("ip", "ann@example.com")          # kinds do not collide
    monkeypatch.setenv("DGATE_INTERNAL_SECRET", "key-two")
    config.reset_cache()
    assert accounts._event_key("addr", "ann@example.com") != one       # no key, no reversal
    monkeypatch.delenv("DGATE_INTERNAL_SECRET")
    monkeypatch.setenv("DGATE_APP_PASSWORD", "app-pw")                 # the fallback key
    config.reset_cache()
    assert accounts._event_key("addr", "ann@example.com") != one
    config.reset_cache()


# ---------------------------------------------------------------- caches and per-account limit (review M2)

def test_the_cache_is_an_lru_of_at_most_200_entries():
    accounts._cache.clear()
    for n in range(accounts.CACHE_ENTRIES):
        accounts._cached(("k", n), lambda n=n: n)
    accounts._cached(("k", 0), lambda: "recomputed")                 # touch the oldest: now the newest
    accounts._cached(("k", "new"), lambda: "x")                       # one over: the least recent goes
    assert len(accounts._cache) == accounts.CACHE_ENTRIES
    assert ("k", 0) in accounts._cache and ("k", 1) not in accounts._cache
    accounts._cache.clear()


def test_concurrent_identical_computes_share_one():
    import threading
    import time

    accounts._cache.clear()
    calls = []
    release = threading.Event()

    def compute():
        calls.append(1)
        release.wait(5)
        return {"total": 7}

    results: list = []
    threads = [threading.Thread(target=lambda: results.append(accounts._cached(("same",), compute)))
               for _ in range(8)]
    for t in threads:
        t.start()
    deadline = time.monotonic() + 5
    while len(accounts._inflight) < 1 and time.monotonic() < deadline:
        pass
    release.set()
    for t in threads:
        t.join(10)
    assert len(calls) == 1 and results == [{"total": 7}] * 8
    assert accounts._inflight == {}
    accounts._cache.clear()


def test_a_failed_compute_is_shared_and_not_cached():
    accounts._cache.clear()

    def boom():
        raise accounts.AccountError(422, "invalid_filters", "no")

    with pytest.raises(accounts.AccountError):
        accounts._cached(("bad",), boom)
    assert ("bad",) not in accounts._cache and accounts._inflight == {}
    assert accounts._cached(("bad",), lambda: 1) == 1


def test_an_account_gets_thirty_search_and_dashboard_calls_a_minute(monkeypatch):
    from dgate.hardening import TokenBuckets
    clock = [0.0]
    monkeypatch.setattr(accounts, "_user_buckets",
                        TokenBuckets(accounts.USER_RATE, accounts.USER_RATE / 60, clock=lambda: clock[0]))
    ann, bob = {"id": "ann"}, {"id": "bob"}
    for _ in range(30):
        assert accounts.throttled(ann) is ann
    with pytest.raises(accounts.AccountError) as e:
        accounts.throttled(ann)
    assert e.value.status == 429 and e.value.headers["Retry-After"] == "2"
    assert accounts.throttled(bob) is bob                              # another account is not affected
    clock[0] += 60
    assert accounts.throttled(ann) is ann


def test_a_reference_is_digits_without_leading_zeros():
    assert accounts._norm_ref("007") == "7"
    assert accounts._norm_ref("12") == "12"
    for bad in ("", "abc", "12a", "1 2", "-1", "99999999999999999999", "12\n"):
        assert accounts._norm_ref(bad) is None
