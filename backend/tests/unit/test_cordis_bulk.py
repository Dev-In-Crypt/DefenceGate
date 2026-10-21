"""WP-70: reading the CORDIS bulk packages and the rules that decide what they may change."""

from __future__ import annotations

import json
import zipfile
from collections import Counter
from types import SimpleNamespace

import httpx
import pytest

from dgate.ops import cordis_bulk

ORG_HEAD = ('"projectID";"projectAcronym";"organisationID";"vatNumber";"name";"shortName";"SME";"activityType";'
            '"street";"postCode";"city";"country";"nutsCode";"geolocation";"organizationURL";"contactForm";'
            '"contentUpdateDate";"rcn";"order";"role";"ecContribution";"netEcContribution";"totalCost";'
            '"endOfParticipation";"active"')


def org_line(ga, pic, role, ec, country="FR"):
    return (f'"{ga}";"ACR";"{pic}";"FR1";"ALPHA SA";"";"false";"PRC";"1 RUE X";"75001";"Paris";"{country}";"FR101";'
            f'"48.8,2.3";"";"https://ec.europa.eu/contact-form/{pic}/{ga}";"2026-01-01";"9";"1";"{role}";"{ec}";"";"";'
            '"false";""')


def make_package(path, projects, orgs):
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("project.csv", '"id";"acronym";"title";"objective";"rcn"\n'
                   + "".join(f'"{ga}";"A";"T";"long; text\nwith a newline";"{rcn}"\n' for ga, rcn in projects))
        z.writestr("organization.csv", "﻿" + ORG_HEAD + "\n" + "".join(line + "\n" for line in orgs))
    return path


def test_the_reader_takes_only_the_allowed_columns_and_maps_the_commission_codes(tmp_path):
    p = make_package(tmp_path / "cordis-h2020projects-csv.zip", [("633053", "193157")], [
        org_line("633053", "999480726", "coordinator", "309235.2", "UK"),
        org_line("633053", "999480727", "thirdParty", "0", "EL"),
        org_line("633053", "999480728", "associatedPartner", ""),
        org_line("999999", "999480729", "participant", "10"),            # a project the package does not describe
        org_line("633053", "999480730", "23893.85", "1"),                 # a shifted row
        org_line("633053", "", "participant", "1"),                       # no PIC
    ])
    c = Counter()
    rows = list(cordis_bulk.read_package(p, c))
    assert c == {"bulk_rows": 4, "bulk_rows_skipped": 2}
    assert all(set(r) == {"rcn", "ga", "pic", "role", "ec", "country"} for r in rows)
    assert rows[0] == {"rcn": "193157", "ga": "633053", "pic": "999480726", "role": "coordinator", "ec": 309235.2,
                       "country": "GB"}
    assert (rows[1]["role"], rows[1]["ec"], rows[1]["country"]) == ("third_party", 0.0, "GR")
    assert rows[2]["ec"] is None and rows[3]["rcn"] is None
    assert not any("ALPHA" in str(v) or "contact" in str(v) for r in rows for v in r.values())


@pytest.mark.parametrize("args, want", [
    # no payment in the open data: the bulk figure
    (("participant", None, "no_payment_stated", "participant", 1000.0), (1000.0, None, "filled")),
    (("partner", None, "no_payment_stated", "partner", 0.0), (0.0, None, "filled")),
    (("third_party", None, "no_payment_stated", "third_party", 0.0), (None, "linked_third_party", "filled")),
    # a third party held as linked stays so, whatever the bulk says
    (("third_party", None, "linked_third_party", "third_party", 0.0), (None, "linked_third_party", None)),
    (("third_party", None, "linked_third_party", "third_party", 50.0), (None, "linked_third_party", None)),
    # the doubled payment of WP-43, and a tripled one
    (("participant", 92035.0, None, "participant", 46017.5), (46017.5, None, "multiple")),
    (("participant", 300.0, None, "participant", 100.0), (100.0, None, "multiple")),
    # a stated amount that differs otherwise is kept
    (("participant", 1652264.59, None, "participant", 1823370.98), (1652264.59, None, "differs_kept")),
    (("participant", 100.0, None, "participant", 0.0), (100.0, None, "differs_kept")),
    (("participant", 100.0, None, "participant", 100.004), (100.0, None, None)),
    # the bulk names another role, gives no amount, or nothing matched
    (("participant", None, "no_payment_stated", "coordinator", 5.0), (None, "no_payment_stated", "role_differs")),
    (("participant", None, "no_payment_stated", "participant", None), (None, "no_payment_stated", None)),
    (("participant", None, "no_payment_stated", None, None), (None, "no_payment_stated", None)),
])
def test_the_rules(args, want):
    assert cordis_bulk.corrected(*args) == want


def _hub(request: httpx.Request) -> httpx.Response:
    ds = request.url.path.rsplit("/", 1)[1]
    short = {"cordisfp7projects": "fp7", "cordish2020projects": "h2020"}.get(ds, "HORIZON")
    dists = [{"download_url": [f"https://cordis.europa.eu/data/cordis-{short}projects-csv.zip"]},
             {"download_url": [f"https://cordis.europa.eu/data/cordis-{short}projects-xlsx.zip"]},
             {"access_url": [f"https://cordis.europa.eu/data/cordis-{short}reports-csv.zip"]},
             {"access_url": ["https://cordis.europa.eu/datalab/visualisations/vis.php"]}]
    return httpx.Response(200, json={"result": {"distributions": dists}})


def test_the_package_urls_are_read_from_the_dataset_pages(monkeypatch):
    monkeypatch.setattr(cordis_bulk.time, "sleep", lambda s: None)
    with httpx.Client(transport=httpx.MockTransport(_hub)) as client:
        assert cordis_bulk.bulk_urls(client) == [
            "https://cordis.europa.eu/data/cordis-fp7projects-csv.zip",
            "https://cordis.europa.eu/data/cordis-h2020projects-csv.zip",
            "https://cordis.europa.eu/data/cordis-HORIZONprojects-csv.zip"]


def _file(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, content=b"x" * 1000, headers={"content-length": "1000"})


def test_a_download_is_refused_when_it_would_leave_too_little_disk(tmp_path):
    url = "https://cordis.europa.eu/data/cordis-fp7projects-csv.zip"
    with httpx.Client(transport=httpx.MockTransport(_file)) as client:
        with pytest.raises(RuntimeError, match="under"):
            cordis_bulk.download(url, tmp_path, client, free=lambda p: SimpleNamespace(free=cordis_bulk.MIN_FREE))
        assert not list(tmp_path.iterdir())
        got = cordis_bulk.download(url, tmp_path, client,
                                   free=lambda p: SimpleNamespace(free=cordis_bulk.MIN_FREE + 2000))
        assert got.read_bytes() == b"x" * 1000
        # present: not fetched again
        never = httpx.Client(transport=httpx.MockTransport(lambda r: pytest.fail("fetched twice")))
        assert cordis_bulk.download(url, tmp_path, never) == got
    assert json.dumps(sorted(p.name for p in tmp_path.iterdir())) == '["cordis-fp7projects-csv.zip"]'
