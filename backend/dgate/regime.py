"""The rules regime of a funding call, from its programme and topic code. Deterministic, no database.

A call says which rulebook applies to it only through its identifiers: the portal files the EDIP
calls under the EDF programme, and the topic code tells them apart (checked against the call
documents on 18 October 2026: an `EDF-EDIP-P-` document lists "EU Member States and EDIP associated
countries", an `EDF-EDIP-USI-` document lists "EU Member States ... and Ukraine").

`readiness` is the code of the readiness programme whose rules the call page shows (seed
`requirements.json`). A regime with no readiness programme is named, and the page says that no rules
of it are encoded; it never invents any.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Regime:
    code: str                    # EDF | EDIP | EDIP-USI | HORIZON | DIGITAL | CEF | NATIONAL
    name: str
    readiness: str | None        # readiness_programme.code, or None: no rules encoded
    why: str                     # one sentence: how the regime was read from the identifiers


EDF = Regime("EDF", "European Defence Fund", "EDF", "The topic code starts with EDF- and the programme is the EDF.")
EDIP = Regime("EDIP", "European Defence Industry Programme", "EDIP",
              "The topic code starts with EDF-EDIP-P-: an EDIP call, which the portal files under the EDF.")
USI = Regime("EDIP-USI", "EDIP Ukraine Support Instrument", "EDIP-USI",
             "The topic code starts with EDF-EDIP-USI-: a call of the Ukraine Support Instrument, which the portal files under the EDF.")
HORIZON = Regime("HORIZON", "Horizon Europe", None,
                 "A Horizon Europe call: its eligibility rules are in the work programme annexes and the topic, and no Horizon rules are encoded here.")
DIGITAL = Regime("DIGITAL", "Digital Europe Programme", None,
                 "A Digital Europe call: its rules are in the call document, and none are encoded here.")
CEF = Regime("CEF", "Connecting Europe Facility", None,
             "A Connecting Europe Facility call: its rules are in the call document, and none are encoded here.")
NATIONAL = Regime("NATIONAL", "National programme", None,
                  "A national call: its rules are the national funder's, and none are encoded here.")

_NATIONAL = re.compile(r"^[A-Z]{2}-")
BY_PROGRAMME = {"EDF": EDF, "EDIDP": None, "EDIP": EDIP, "HORIZON": HORIZON, "DIGITAL": DIGITAL, "CEF2027": CEF}


def regime_of(programme_code: str, topic_code: str | None) -> Regime | None:
    """The regime of one call, or None when the programme is one this does not know (EDIDP, a new
    programme): the page then shows no block rather than a guess."""
    topic = (topic_code or "").upper()
    if programme_code == "EDF":
        if topic.startswith("EDF-EDIP-USI-"):
            return USI
        if topic.startswith("EDF-EDIP-P-"):
            return EDIP
        return EDF
    if _NATIONAL.match(programme_code):
        return NATIONAL
    return BY_PROGRAMME.get(programme_code)


def action_of(programme_code: str, topic_code: str | None) -> str | None:
    """The kind of action of an EDIP call, from its topic code, or None when the code says none. The Regulation (and
    the call documents) open different kinds of action to different applicants, so the readiness rules that depend on
    it are scoped to it (`seed` rules with `applies_when` on the field `action`). Read from all twelve EDIP topic
    codes of 18 October 2026: `-FNLC-CPA-` common procurement (Article 11), `-FNLC-SA-SEAP` support for SEAPs
    (Article 13(1)(g)), `-FNLC-CSA-PREP` preparation of projects of common interest (Article 35), `-LS-IRA-`
    industrial reinforcement (Article 12)."""
    tokens = (topic_code or "").upper().split("-")
    if programme_code not in ("EDF", "EDIP") or "EDIP" not in tokens:
        return None
    if "CPA" in tokens:
        return "common_procurement"
    if "SA" in tokens and "SEAP" in tokens:
        return "seap_support"
    if "CSA" in tokens and "PREP" in tokens:
        return "edpci_preparation"
    if "IRA" in tokens:
        return "industrial_reinforcement"
    return None


# What the Regulation says beyond the rules the readiness seed encodes, verbatim from the Official
# Journal text (CELLAR, read on 18 October 2026). Shown only while the seed has no rule of kind
# `threshold` for the regime, so that the seed stays the single place a rule is kept once it is added.
ALSO_READ = {
    "EDIP": {
        "label": "Component origin: at most 35 % of the component cost from outside the Union and associated countries",
        "ref": "Regulation (EU) 2025/2643, Article 10(3); Article 10(4) sets the same share for industrial reinforcement actions",
        "text": "For procurement carried out pursuant to Articles 11, 13 and 35 which is supported by Union funding, the cost of "
                "components originating outside the Union and associated countries shall not be higher than 35 % of the estimated "
                "cost of the components of the end product.",
        "url": "http://data.europa.eu/eli/reg/2025/2643/oj",
    },
    "EDIP-USI": {
        "label": "Component origin: at most 35 % of the component cost from outside the Union and Ukraine",
        "ref": "Regulation (EU) 2025/2643, Article 27(3); Article 27(4) sets the same share for industrial reinforcement actions",
        "text": "For procurement carried out pursuant to paragraph 1, points (a) and (c), which is supported by Union funding, the cost of "
                "components originating outside the Union and Ukraine shall not be higher than 35 % of the estimated cost of the "
                "components of the end product.",
        "url": "http://data.europa.eu/eli/reg/2025/2643/oj",
    },
}
