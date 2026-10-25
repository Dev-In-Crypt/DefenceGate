"""WP-134: 'zakladow' is a unit word, so the health-care unit names WP-129 found rejoined count as generic names."""

from __future__ import annotations

import re
from pathlib import Path

from dgate.ops.org_repair import ambiguous_name

GATED = Path(__file__).resolve().parents[3] / ".github" / "workflows" / "web-gated.yml"


def test_each_gated_spec_runs_in_ci_with_the_setting_it_waits_for():
    """The specs that skip themselves in the Web workflow's run (they need an account API or a billing-open build)."""
    text = GATED.read_text(encoding="utf-8").replace("\\\n", " ")
    runs = [line for line in text.splitlines() if "npx playwright test" in line]
    for spec, setting in (("wp79", "E2E_FAKE_ACCOUNTS=1"), ("wp123", "E2E_REAL_ACCOUNTS=1"),
                          ("wp124", "E2E_REAL_BILLING=1"), ("wp122", None)):
        line = next((x for x in runs if re.search(rf"e2e/{spec}\.spec\.ts\b", x)), "")
        assert line, spec
        assert setting is None or setting in line, spec
    assert re.search(r"NEXT_PUBLIC_BILLING_OPEN=1 .*npx next build", text)
    assert 'NEXT_PUBLIC_BILLING_OPEN: "1"' in text                 # wp122 reads it at test time too
    assert "E2E_MAIL_DIR" in text and "E2E_CREEM_MOCK_PORT" in text
    assert not re.search(r"smtp\.|api\.creem\.io|DGATE_SMTP_HOST", text)    # fake services only


def test_a_health_care_unit_group_without_its_place_is_a_generic_name():
    assert ambiguous_name("PL", "zespol zakladow opieki zdrowotnej")                                  # head 9206
    assert ambiguous_name("PL", "samodzielny publiczny zaklad opieki zdrowotnej zespol zakladow")     # head 10219


def test_the_same_names_with_their_place_stay_joinable():
    assert not ambiguous_name("PL", "zespol zakladow opieki zdrowotnej w wadowicach")
    assert not ambiguous_name("PL", "samodzielny publiczny zespol zakladow opieki zdrowotnej w lomzy")
