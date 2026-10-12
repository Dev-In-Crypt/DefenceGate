"""The limits that stand between one hostile or broken record, or one client, and
the rest of the system. Each test is a failure measured or reproduced in the
security review of 12 October 2026."""

from __future__ import annotations

import time
import zlib
from datetime import date

import pytest

from dgate import rawstore
from dgate.api import SNAPSHOT_FIELDS, public_snapshot
from dgate.hardening import TokenBuckets, request_cost
from dgate.normalise import (
    EMAIL_PLACEHOLDER,
    MAX_DEPTH,
    MAX_STRING,
    Call,
    Opportunity,
    http_url,
    redact_emails,
    scrub_opportunity,
    strip_personal_data,
)
from dgate.sources import (
    MAX_BODY_BYTES,
    ResponseTooLarge,
    html_to_text_markup,
    request_with_retry,
)
from dgate.sources.placsp import _same_site

# ------------------------------------------------------------- rate limiting

def test_a_client_may_burst_to_the_capacity_and_is_then_told_to_wait():
    clock = [0.0]
    buckets = TokenBuckets(capacity=10, refill=1.0, clock=lambda: clock[0])
    assert all(buckets.take("a", 1)[0] for _ in range(10))
    allowed, wait = buckets.take("a", 1)
    assert not allowed and wait == pytest.approx(1.0)
    clock[0] += 3
    assert buckets.take("a", 3)[0]


def test_one_clients_flood_does_not_spend_another_clients_tokens():
    buckets = TokenBuckets(capacity=5, refill=0.0)
    assert not all(buckets.take("noisy", 1)[0] for _ in range(9))
    assert buckets.take("quiet", 1)[0]


def test_the_archive_and_the_oracle_cost_more_than_a_list_page():
    assert request_cost("/v1/opportunities/5/versions", {}) == 5
    assert request_cost("/v1/organisations/resolve", {}) == 5
    assert request_cost("/v1/funding/slugs", {}) == 20
    assert request_cost("/v1/funding", {"pageSize": "500"}) == 3
    assert request_cost("/v1/opportunities", {"limit": "50"}) == 1
    assert request_cost("/v1/opportunities", {"limit": "not-a-number"}) == 1


def test_a_flood_of_distinct_addresses_cannot_grow_memory_without_bound():
    clock = [0.0]
    buckets = TokenBuckets(capacity=2, refill=1.0, clock=lambda: clock[0])
    for n in range(20_001):
        buckets.take(f"ip-{n}", 1)
    clock[0] += 60
    buckets.take("trigger", 1)
    assert len(buckets._buckets) < 20_000


# ---------------------------------------------------- the payload boundary

def _nested(depth: int):
    node: object = "x"
    for _ in range(depth):
        node = [node]
    return node


def test_a_payload_nested_far_beyond_reason_is_cut_not_a_crash():
    clean = strip_personal_data({"title": "t", "deep": _nested(1500)})
    assert clean["title"] == "t"
    node, depth = clean["deep"], 0
    while isinstance(node, list) and node:
        node, depth = node[0], depth + 1
    assert depth <= MAX_DEPTH


def test_a_nul_character_never_reaches_the_database_layer():
    clean = strip_personal_data({"orderObject": "ab\x00cd", "x\x00y": ["q\x00"]})
    assert "\x00" not in str(clean)


def test_a_text_of_absurd_length_is_cut_at_the_boundary():
    clean = strip_personal_data({"description": "a" * (MAX_STRING * 3)})
    assert len(clean["description"]) == MAX_STRING


def test_a_french_body_nested_beyond_the_json_parser_is_dropped_not_fatal():
    body = "[" * 100_000 + "]" * 100_000
    clean = strip_personal_data({"idweb": "26-1", "donnees": body})
    assert clean["donnees"] is None


def test_the_email_pattern_is_not_quadratic_on_a_long_run_of_address_characters():
    started = time.perf_counter()
    redact_emails("a" * 200_000 + "@")
    assert time.perf_counter() - started < 2.0


def test_an_address_is_still_found_and_replaced():
    assert redact_emails("write to a.b+c@x.example.eu today") == \
        f"write to {EMAIL_PLACEHOLDER} today"


# ------------------------------------------------------------------- links

@pytest.mark.parametrize("value", [
    "javascript:alert(1)", "data:text/html,x", "ftp://x.example/", "//x.example/a",
    "/relative", "https://", "https://x.example/a b", "https://x.example/a\nb", "", None, 5,
])
def test_only_an_absolute_http_or_https_link_is_a_link(value):
    assert http_url(value) is None


def test_a_normal_link_passes_unchanged():
    assert http_url("https://ted.europa.eu/en/notice/-/detail/1-2026") == \
        "https://ted.europa.eu/en/notice/-/detail/1-2026"
    assert http_url("http://x.example/a?b=1") == "http://x.example/a?b=1"


def test_the_record_types_refuse_a_hostile_link_when_they_are_built():
    opp = Opportunity(source_code="ted", native_id="1", buyer_name_raw="b", title_original="t",
                      source_url="javascript:alert(1)")
    call = Call(programme_code="X", native_id="1", title="t", source_url="data:x")
    assert opp.source_url is None and call.source_url is None


def test_a_connector_built_record_is_swept_of_addresses_and_nul():
    opp = Opportunity(source_code="es_placsp", native_id="1", buyer_name_raw="Ayto <a@b.es>",
                      title_original="t\x00", description="mail x@y.example now",
                      published_at=date(2026, 1, 1))
    scrub_opportunity(opp)
    assert EMAIL_PLACEHOLDER in opp.buyer_name_raw and "\x00" not in opp.title_original
    assert "x@y.example" not in opp.description


# --------------------------------------------------------- what is served

def test_a_version_snapshot_is_an_allow_list_and_loses_the_notice_text():
    payload = {"title_original": "Supply of x, contact a@b.example", "native_id": "1",
               "description": "full text with c@d.example", "buyer_org_id": 7,
               "sig_buyer": True, "source_url": "javascript:x", "cpv_codes": ["35000000"],
               "unknown_future_field": "secret"}
    shown = public_snapshot(payload)
    assert set(shown) <= set(SNAPSHOT_FIELDS)
    assert "description" not in shown and "unknown_future_field" not in shown
    assert "a@b.example" not in str(shown) and shown["source_url"] is None
    assert shown["cpv_codes"] == ["35000000"]


# --------------------------------------------------------------------- html

def test_blocks_and_tags_come_out_and_the_text_stays():
    page = "<header>menu</header><nav><a>x</a></nav><main><h1>Title</h1><p>Body</p></main>"
    text = " ".join(html_to_text_markup(page).split())
    assert text == "Title Body"


def test_a_page_of_unclosed_blocks_is_linear_not_a_stall():
    page = "<nav>" * 200_000 + "<p>end</p>"
    started = time.perf_counter()
    html_to_text_markup(page)
    assert time.perf_counter() - started < 5.0


def test_a_run_of_open_angle_brackets_is_linear_too():
    started = time.perf_counter()
    html_to_text_markup("<" * 1_500_000)
    assert time.perf_counter() - started < 5.0


# ------------------------------------------------------ fetched body sizes

class _Big:
    content = b"x" * (MAX_BODY_BYTES + 1)


def test_a_response_larger_than_the_ceiling_is_refused():
    with pytest.raises(ResponseTooLarge):
        request_with_retry(lambda: _Big(), what="test")


def test_a_next_link_must_stay_on_the_datasets_host():
    ref = "https://contrataciondelsectorpublico.gob.es/sindicacion/x.atom"
    assert _same_site("https://contrataciondelsectorpublico.gob.es/p2.atom", ref)
    assert not _same_site("http://contrataciondelsectorpublico.gob.es/p2.atom", ref)
    assert not _same_site("https://evil.example/p2.atom", ref)
    assert not _same_site("https://169.254.169.254/", ref)


def test_a_bundle_that_inflates_past_the_ceiling_is_refused_not_allocated():
    bomb = zlib.compress(b"\0" * 5_000_000)         # zlib, not gzip: wrap as gzip below
    import gzip
    import io
    buffer = io.BytesIO()
    with gzip.GzipFile(fileobj=buffer, mode="wb") as f:
        f.write(b"\0" * 5_000_000)
    assert len(rawstore._gunzip(buffer.getvalue(), limit=10_000_000)) == 5_000_000
    with pytest.raises(ValueError):
        rawstore._gunzip(buffer.getvalue(), limit=1_000_000)
    assert bomb  # silence "unused"


def test_an_identifier_from_a_source_is_checked_before_it_is_put_into_a_url():
    from dgate.sources import eu_portal, tenderned

    with pytest.raises(ValueError):
        tenderned.fetch_detail("../../admin", client=None)       # never reaches the network
    with pytest.raises(ValueError):
        eu_portal.fetch_topic_details("x/../../y", client=None)     # never reaches the network
