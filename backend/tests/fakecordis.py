"""A stand-in for the CORDIS SPARQL service: answers robots.txt, the count queries and the keyset
pages of dgate.sources.cordis from three lists of rows. Enough to run the whole importer."""

from __future__ import annotations

import re

import httpx

ROBOTS = "User-agent: *\nDisallow: /data/\nDisallow: /search\n"


def _bindings(rows: list[dict[str, str]]) -> dict:
    return {"results": {"bindings": [{k: {"type": "literal", "value": v} for k, v in r.items()}
                                     for r in rows]}}


class FakeCordis:
    def __init__(self, orgs, projects, roles, *, claimed: dict[str, int] | None = None,
                 robots: str = ROBOTS) -> None:
        self.rows = {"organisations": orgs, "projects": projects, "roles": roles}
        self.claimed = claimed or {}
        self.robots = robots
        self.requests: list[str] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text=self.robots)
        query = request.url.params["query"]
        self.requests.append(query)
        if "AS ?n)" in query:
            kind = {"Organisation": "organisations", "Project": "projects",
                    "OrganisationRole": "roles"}[re.search(r"a e:(\w+)", query).group(1)]
            n = self.claimed.get(kind, len(self.rows[kind]))
            return httpx.Response(200, json=_bindings([{"n": str(n)}]))
        kind = ("roles" if "?x a e:OrganisationRole" in query else
                "organisations" if "?x a e:Organisation ." in query else "projects")
        m = re.search(r'FILTER \(STR\(\?x\) > "[^"]*?/([^/"]*)"\)', query)
        after = m.group(1) if m else ""
        limit = int(re.search(r"LIMIT (\d+)", query).group(1))
        page = [r for r in sorted(self.rows[kind], key=lambda r: r["key"]) if r["key"] > after]
        return httpx.Response(200, json=_bindings(page[:limit]))

    def sparql(self):
        from dgate.sources import cordis

        return cordis.Sparql(httpx.Client(transport=httpx.MockTransport(self.handler)),
                             min_interval=0, sleep=lambda s: None)


def dataset():
    orgs = [
        {"key": "o1", "pic": "111111111", "rcn": "1", "name": "ACME DEFENCE SA", "vat": "FR11111111111", "country": "FR"},
        {"key": "o2", "pic": "222222222", "rcn": "2", "name": "BETA SYSTEMS GMBH", "vat": "DE222222222", "country": "DE"},
        {"key": "o3", "pic": "333333333", "rcn": "3", "name": "GAMMA OPTICS LTD", "vat": "", "country": "UK"},
        {"key": "o4", "pic": "", "rcn": "4", "name": "DELTA ASSOCIATION", "vat": "", "country": "PL"},
    ]
    projects = [
        {"key": "p1", "rcn": "1001", "ga": "101000001", "title": "First project", "acronym": "FIRST",
         "start": "2022-01-01", "end": "2024-12-31", "duration": "36", "status": "SIGNED",
         "cost": "1000000", "fund": "800000", "call": "HORIZON-CL4-2021-X",
         "topic": "HORIZON_HORIZON-CL4-2021-X-01"},
        {"key": "p2", "rcn": "1002", "ga": "700002", "title": "Second project", "acronym": "SECOND",
         "start": "2016-03-01", "end": "2019-02-28", "duration": "36", "status": "CLOSED",
         "cost": "500000", "fund": "500000", "call": "H2020-SEC-2015", "topic": "H2020_SEC-2015-1"},
    ]
    roles = [
        {"key": "r1", "project": "1001", "org": "o1", "role": "coordinator", "amount": "300000"},
        {"key": "r2", "project": "1001", "org": "o2", "role": "participant", "amount": "500000"},
        {"key": "r3", "project": "1002", "org": "o1", "role": "participant", "amount": "100000"},
        {"key": "r4", "project": "1002", "org": "o3", "role": "thirdParty", "amount": ""},
        {"key": "r5", "project": "1002", "org": "o4", "role": "coordinator", "amount": "400000"},
    ]
    return orgs, projects, roles
