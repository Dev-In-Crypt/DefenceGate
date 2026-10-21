"""WP-65: the supplier profile of the web (/readiness/supplier) answers the WP-64 questions of the Spanish defence supplier route.

The three request bodies are the generated fixtures `web/e2e/fixtures/request-es-sup-*.json` (dgate.readiness.export), which the web's
own checks and e2e specs prove the page sends. Here: the API accepts them, the body stays under the proxy's 4096-byte limit, and the
open questions of the ES-MOD card before the supplier page (the same company with none of its answers) and after are what the
self-check reports. An answer left empty stays unknown and keeps its question.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dgate.readiness import api, engine
from dgate.readiness.export import SUPPLIER_PROFILES
from dgate.readiness.seed import load_file

ROOT = Path(__file__).resolve().parents[3]
CONTENT = load_file()
SUPPLIER_ONLY = {"REQ-RID", "REQ-PECAL"}


def request(key):
    return json.loads((ROOT / "web" / "e2e" / "fixtures" / f"request-{key}.json").read_text(encoding="utf-8"))


def before(body):
    """The same company before WP-65: none of the supplier page's answers, RID and PECAL never asked."""
    profile = {k: v for k, v in body["profile"].items() if k not in engine.SUPPLIER_FIELDS}
    profile["third_country_control"] = None          # it came from the page's "no foreign investor"
    return {"profile": profile, "statuses": {k: v for k, v in body["statuses"].items() if k not in SUPPLIER_ONLY}}


def missing(body, programme="ES-MOD"):
    payload = api.assess_payload(CONTENT, api.ProfileIn(**body["profile"]).to_engine(), body["statuses"])
    a = next(a for a in payload["assessments"] if a["programme"] == programme)
    return [m["field"] for m in a["missing"]], a["verdict"]


@pytest.mark.parametrize("key", sorted(SUPPLIER_PROFILES))
def test_the_supplier_requests_are_accepted_and_small(key):
    body = request(key)
    api.AssessIn.model_validate(body)
    assert len(json.dumps(body, separators=(",", ":")).encode()) < 4096
    # only fields the engine knows; a supplier answer that is not given is absent, not null
    extra = set(body["profile"]) - set(api.ProfileIn.model_fields)
    assert extra == set()
    assert all(body["profile"][f] is not None for f in engine.SUPPLIER_FIELDS if f in body["profile"])


@pytest.mark.parametrize("key, was, now, verdict", [
    # WP-73: the route counts its conditional rules where they apply, so an open condition (civil: NCAGE without a justified need)
    # or a missing answer (defence: the HSEM, which the page now asks and which is no longer "not held" when unanswered) is "conditional"
    ("es-sup-civil", 19, 0, "conditional"),
    ("es-sup-defence", 21, 1, "conditional"),
    ("es-sup-partial", 19, 15, "conditional"),
])
def test_open_questions_of_the_spanish_route_before_and_after_the_supplier_page(key, was, now, verdict):
    old, _ = missing(before(request(key)))
    new, v = missing(request(key))
    assert (len(old), len(new), v) == (was, now, verdict)
    assert set(new) <= set(old)


def test_an_unanswered_question_stays_unknown_with_its_question():
    new, _ = missing(request("es-sup-partial"))
    # the profile said nothing of PECAL ambitions, NATO bids or homologation: those rules still ask
    assert {"pecal_certificate_wanted", "nato_icb_bid", "specific_defence_use"} <= set(new)
    # what it did say is no longer asked: the RID (not ticked, so not held), foreign capital, control
    assert not {"REQ-RID", "foreign_capital", "third_country_control"} & set(new)
    body = request("es-sup-partial")
    payload = api.assess_payload(CONTENT, api.ProfileIn(**body["profile"]).to_engine(), body["statuses"])
    es = next(a for a in payload["assessments"] if a["programme"] == "ES-MOD")
    rid = next(r for r in es["rules"] if r["rule"] == "ES-RID")
    assert rid["outcome"] == "to_obtain"
