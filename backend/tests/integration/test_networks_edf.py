"""The EDF factsheet import end to end: a fake website, a real PDF reader, a fake model."""

from __future__ import annotations

import json

import httpx
import pytest

from dgate import config, networks
from tests.pdfmaker import MEMBERS, factsheet_pdf

pytestmark = pytest.mark.integration

SITE = "https://defence-industry-space.ec.europa.eu"
PAGE_URL = f"{SITE}/funding-opportunities/calls-proposals/result-edf-2025-calls-proposals_en"
NAME = "FACTSHEET_EDF_2025_LS_RA_SI_CYBER_3RAV_STEP_101304998_STRATUS.pdf"
PDF_URL = f"{SITE}/document/download/3cea0490_en?filename={NAME}"


class Site:
    """The DEFIS website as far as the crawler sees it."""

    def __init__(self, pdf: bytes) -> None:
        self.pdf = pdf
        self.hits: list[str] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        self.hits.append(url)
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow: /admin/\nDisallow: /search/\n")
        if request.url.path == "/sitemap.xml":
            return httpx.Response(200, text=f"<urlset><url><loc>{PAGE_URL}</loc></url></urlset>")
        if url == PAGE_URL:
            return httpx.Response(200, text=(
                f'<a href="/document/download/3cea0490_en?filename={NAME}">x</a>'
                '<a href="/document/download/9999_en?filename=EDF%202025%20results%20-%20general%20factsheet.pdf">g</a>'))
        if request.url.path.startswith("/document/download/3cea0490"):
            return httpx.Response(200, content=self.pdf)
        return httpx.Response(404, text="not found")

    def client(self) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(self.handler))


class Model:
    """The language model: answers with what `answer` holds, counts its calls."""

    def __init__(self) -> None:
        self.calls = 0
        self.status = 200
        self.answer = self.good()

    @staticmethod
    def good() -> dict:
        def e(name, country, role="participant"):
            return {"name": name, "country": country, "role": role, "is_sme": None}

        return {
            "acronym": "STRATUS", "title": "STRATUS - Swarm Threat Resilience",
            "coordinator": {"name": "TALGEN CYBERSECURITY OU", "country": "Estonia"},
            "participants": [
                e("TALGEN CYBERSECURITY OU", "Estonia", "coordinator"),
                e("ALITER TECHNOLOGIES, AS", "Slovakia"),
                e("FUNDACION CENTRO TECNOLOXICO DE TELECOMUNICACIONS DE GALICIA", "Spain"),
                e("SAFRAN ELECTRONICS & DEFENSE", "France"),
                e("PHANTOM CORP", "France"),                   # not in the document
            ],
            "eu_contribution": 19946186.41, "total_cost": 19946187.63, "duration_months": 36}

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.calls += 1
        if self.status != 200:
            return httpx.Response(self.status, text="boom")
        body = {"status": "completed", "usage": {"input_tokens": 1500, "output_tokens": 300},
                "output": [{"type": "message", "content": [
                    {"type": "output_text", "text": json.dumps(self.answer)}]}]}
        return httpx.Response(200, json=body)

    def client(self) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(self.handler))


@pytest.fixture
def env(conn, tmp_path, monkeypatch):
    monkeypatch.setenv("DGATE_RAW_BACKEND", "fs")
    monkeypatch.setenv("DGATE_RAW_DIR", str(tmp_path / "raw"))
    monkeypatch.setenv("DGATE_FLOOR_EDF_FACTSHEETS", "1")
    monkeypatch.setenv("DGATE_OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("DGATE_OPENAI_MODEL", "test-model")
    monkeypatch.setenv("DGATE_LLM_MONTHLY_CAP_USD", "5")
    config.reset_cache()
    conn.execute("UPDATE source SET active = FALSE WHERE code = 'edf_factsheets'")
    conn.commit()
    yield
    conn.execute("UPDATE source SET active = FALSE WHERE code = 'edf_factsheets'")
    conn.commit()
    config.reset_cache()


def _run(site: Site, model: Model, **kw):
    kw.setdefault("sleep", lambda s: None)
    return networks.run_edf(http=site.client(), llm_client=model.client(), **kw)


def _counts(conn):
    return {t: conn.execute(f"SELECT count(*) AS n FROM {t}").fetchone()["n"] for t in
            ("organisation", "organisation_alias", "project", "participation", "project_factsheet",
             "raw_ingest")}


def test_a_factsheet_becomes_a_project_with_its_resolved_consortium(conn, env):
    site, model = Site(factsheet_pdf()), Model()
    c = _run(site, model)
    assert c["fetched"] == 1 and c["factsheets_read"] == 1 and model.calls == 1
    assert c["dropped_not_in_text"] == 1                      # PHANTOM CORP

    p = conn.execute("""SELECT p.*, pr.code AS prog FROM project p JOIN programme pr
                         ON pr.id = p.programme_id""").fetchone()
    assert (p["prog"], p["acronym"], p["ga_number"], p["call_year"]) == ("EDF", "STRATUS", "101304998", 2025)
    assert (p["action_type"], p["category"], p["topic_code"]) == (
        "RA", "CYBER", "EDF-2025-LS-RA-SI-CYBER-3RAV-STEP")
    assert float(p["total_cost"]) == 19946187.63 and float(p["eu_contribution"]) == 19946186.41
    assert p["duration_months"] == 36 and p["factsheet_url"] == PDF_URL
    assert p["cordis_id"] is None

    rows = conn.execute("""SELECT o.display_name, o.country, pa.role, pa.resolution_method,
                                  pa.resolution_confidence, pa.contribution
                             FROM participation pa JOIN organisation o ON o.id = pa.organisation_id
                            ORDER BY o.display_name""").fetchall()
    assert [(r["display_name"], r["country"], r["role"]) for r in rows] == [
        ("ALITER TECHNOLOGIES, AS", "SK", "participant"),
        ("FUNDACION CENTRO TECNOLOXICO DE TELECOMUNICACIONS DE GALICIA", "ES", "participant"),
        ("SAFRAN ELECTRONICS & DEFENSE", "FR", "participant"),
        ("TALGEN CYBERSECURITY OU", "EE", "coordinator")]
    assert all(r["resolution_method"] == "exact_name" and float(r["resolution_confidence"]) == 0.95
               and r["contribution"] is None for r in rows)
    fact = conn.execute("SELECT * FROM project_factsheet").fetchone()
    assert fact["dropped"]["not_in_text"] == 1 and fact["prompt_version"] == 1
    assert float(fact["cost_usd"]) > 0 and fact["pages"] == 2
    run = conn.execute("SELECT status, detail FROM ingest_run").fetchone()
    assert run["status"] == "success"


def test_the_technical_description_never_reaches_the_store_or_the_model(conn, env):
    site, model = Site(factsheet_pdf()), Model()
    seen: list[str] = []
    real = model.handler

    def spy(request):
        seen.append(request.content.decode())
        return real(request)

    model.client = lambda: httpx.Client(transport=httpx.MockTransport(spy))
    _run(site, model)
    assert seen and "SECRET TECHNICAL" not in seen[0] and "TALGEN" in seen[0]
    import gzip
    import pathlib

    from dgate.config import settings

    stored = ""
    for path in pathlib.Path(settings().raw_dir).rglob("*"):
        if path.is_file():
            data = path.read_bytes()
            stored += (gzip.decompress(data) if path.suffix == ".gz" else data).decode("utf-8", "ignore")
    assert "TALGEN" in stored and "SECRET TECHNICAL" not in stored


def test_a_second_run_asks_the_model_nothing_and_creates_nothing(conn, env):
    site, model = Site(factsheet_pdf()), Model()
    _run(site, model)
    before = _counts(conn)
    c = _run(site, model)                         # read within 25 days: not even fetched again
    assert model.calls == 1 and c["factsheets_recent"] == 1
    assert not any(h.endswith(".pdf") or "document/download/3cea0490" in h for h in site.hits[-4:])
    assert _counts(conn) == before
    assert c["new"] == 0 and c["changed"] == 0
    c = _run(site, model, reread=True)            # fetched again: same hash, the model is not asked
    assert model.calls == 1 and c["factsheets_held"] == 1
    assert _counts(conn) == before
    assert c["new"] == 0 and c["changed"] == 0


def test_a_changed_factsheet_is_read_again_and_a_participant_who_left_is_marked_not_deleted(conn, env):
    site, model = Site(factsheet_pdf()), Model()
    _run(site, model)
    fewer = [m for m in MEMBERS if "SAFRAN" not in m[0]]
    site.pdf = factsheet_pdf(members=fewer)
    model.answer["participants"] = [p for p in model.answer["participants"]
                                    if "SAFRAN" not in p["name"]]
    c = _run(site, model, reread=True)
    assert model.calls == 2 and c["factsheets_read"] == 1 and c["participations_deactivated"] == 1
    assert conn.execute("SELECT count(*) AS n FROM participation").fetchone()["n"] == 4
    assert conn.execute("""SELECT pa.active FROM participation pa JOIN organisation o
                             ON o.id = pa.organisation_id WHERE o.display_name LIKE 'SAFRAN%'"""
                        ).fetchone()["active"] is False
    assert conn.execute("SELECT count(*) AS n FROM project").fetchone()["n"] == 1


def test_a_participant_who_is_already_an_organisation_we_hold_is_not_duplicated(conn, env):
    oid = conn.execute(
        "INSERT INTO organisation (canonical_name, country, eu_pic) VALUES "
        "('safran electronics & defense', 'FR', '999999999') RETURNING id").fetchone()["id"]
    conn.commit()
    _run(Site(factsheet_pdf()), Model())
    assert conn.execute("SELECT count(*) AS n FROM organisation WHERE country = 'FR'"
                        ).fetchone()["n"] == 1
    assert conn.execute("SELECT count(*) AS n FROM participation WHERE organisation_id = %s",
                        (oid,)).fetchone()["n"] == 1


def test_a_model_that_is_down_makes_the_run_partial_not_a_green_tick(conn, env):
    site, model = Site(factsheet_pdf()), Model()
    model.status = 500
    c = _run(site, model)
    assert c["files_failed"] == 1
    run = conn.execute("SELECT status, error_message FROM ingest_run").fetchone()
    assert run["status"] == "partial" and "could not be read" in run["error_message"]
    assert conn.execute("SELECT count(*) AS n FROM project").fetchone()["n"] == 0


def test_the_monthly_budget_stops_the_run_before_anything_is_sent(conn, env, monkeypatch):
    monkeypatch.setenv("DGATE_LLM_MONTHLY_CAP_USD", "0.000001")
    config.reset_cache()
    site, model = Site(factsheet_pdf()), Model()
    c = _run(site, model)
    assert model.calls == 0 and c["stopped_by_cap"] == 1
    assert conn.execute("SELECT status FROM ingest_run").fetchone()["status"] == "partial"


def test_a_factsheet_without_a_country_for_an_entity_keeps_the_rest(conn, env):
    site, model = Site(factsheet_pdf()), Model()
    # a printed name that is not a row of the table as such, with a country nobody can place
    model.answer["participants"][1].update(name="ALITER TECHNOLOGIES", country="Atlantis")
    c = _run(site, model)
    assert c["participants_no_country"] == 1
    assert conn.execute("SELECT count(*) AS n FROM participation").fetchone()["n"] == 3


def test_a_country_the_model_got_wrong_is_corrected_from_the_table_before_anything_is_stored(conn, env):
    site, model = Site(factsheet_pdf()), Model()
    model.answer["participants"][1]["country"] = "Spain"                 # ALITER is on a Slovak row
    c = _run(site, model)
    assert c["dropped_country_corrected"] == 1
    row = conn.execute("SELECT o.country FROM participation pa JOIN organisation o ON o.id = "
                       "pa.organisation_id WHERE o.display_name LIKE 'ALITER%'").fetchone()
    assert row["country"] == "SK"


def test_the_crawler_stays_on_the_pages_robots_allows_and_asks_politely(conn, env):
    site, model = Site(factsheet_pdf()), Model()
    _run(site, model)
    assert site.hits[0].endswith("/robots.txt")
    assert not any("/search/" in h or "/admin/" in h for h in site.hits)
    assert not any("general%20factsheet" in h for h in site.hits)


def test_a_robots_file_that_cannot_be_read_stops_the_run(conn, env):
    def handler(request):
        return httpx.Response(503)

    from dgate.sources import cordis

    with pytest.raises(cordis.RobotsDisallowed):
        networks.run_edf(http=httpx.Client(transport=httpx.MockTransport(handler)),
                         llm_client=Model().client(), sleep=lambda s: None)


def test_a_factsheet_that_gives_no_participants_makes_the_run_partial(conn, env):
    site, model = Site(factsheet_pdf()), Model()
    model.answer["participants"] = []
    c = _run(site, model)
    assert c["files_without_participants"] == 1
    run = conn.execute("SELECT status, error_message FROM ingest_run").fetchone()
    assert run["status"] == "partial" and "no participants" in run["error_message"]
    assert conn.execute("SELECT count(*) AS n FROM participation").fetchone()["n"] == 0


def test_a_file_uploaded_twice_is_one_project_and_the_later_upload_wins(conn, env):
    older = factsheet_pdf(members=MEMBERS[:2])
    newer = factsheet_pdf()
    twin = NAME.replace(".pdf", "_0.pdf")

    class Twice(Site):
        def handler(self, request):
            if str(request.url) == PAGE_URL:
                self.hits.append(PAGE_URL)
                return httpx.Response(200, text=(
                    f'<a href="/document/download/3cea0490_en?filename={NAME}">a</a>'
                    f'<a href="/document/download/4beb1501_en?filename={twin}">b</a>'))
            if request.url.path.startswith("/document/download/4beb1501"):
                self.hits.append(str(request.url))
                return httpx.Response(200, content=newer)
            return super().handler(request)

    site, model = Twice(older), Model()
    c = _run(site, model)
    assert c["files_superseded"] == 1 and c["fetched"] == 1 and model.calls == 1
    assert not any("3cea0490" in h for h in site.hits)          # the older upload is never fetched
    assert conn.execute("SELECT count(*) AS n FROM project").fetchone()["n"] == 1
    again = _run(site, model)
    assert again["new"] == 0 and again["changed"] == 0 and model.calls == 1


class Limited(Site):
    """A site that answers 429 to the first `refuse` requests for the PDF."""

    def __init__(self, pdf, refuse, retry_after=None):
        super().__init__(pdf)
        self.refuse, self.retry_after = refuse, retry_after
        self.pdf_requests = 0

    def handler(self, request):
        if request.url.path.startswith("/document/download/3cea0490"):
            self.pdf_requests += 1
            if self.pdf_requests <= self.refuse:
                headers = {"retry-after": str(self.retry_after)} if self.retry_after else {}
                return httpx.Response(429, headers=headers, text="slow down")
        return super().handler(request)


def test_a_429_is_waited_out_with_the_sites_retry_after_and_the_pace_slows_down(conn, env):
    site, model, waits = Limited(factsheet_pdf(), refuse=2, retry_after=7), Model(), []
    c = _run(site, model, sleep=waits.append)
    assert site.pdf_requests == 3 and c["factsheets_read"] == 1 and "files_failed" not in c
    assert waits.count(7.0) == 2                                   # the site's own figure
    assert conn.execute("SELECT status FROM ingest_run").fetchone()["status"] == "success"
    assert conn.execute("SELECT count(*) AS n FROM project").fetchone()["n"] == 1


def test_a_site_that_keeps_refusing_stops_the_run_as_partial_not_as_a_crash(conn, env):
    site, model, waits = Limited(factsheet_pdf(), refuse=99), Model(), []
    c = _run(site, model, sleep=waits.append)
    assert c["rate_limited"] == 1 and c["files_not_read"] == 1 and model.calls == 0
    assert max(waits) >= 40                                         # it backed off, it did not hammer
    run = conn.execute("SELECT status, error_message FROM ingest_run").fetchone()
    assert run["status"] == "partial" and "too many requests" in run["error_message"]


def test_the_source_is_switched_on_by_its_first_run_and_not_by_a_run_that_read_nothing(conn, env):
    def active():
        return conn.execute("SELECT active FROM source WHERE code = 'edf_factsheets'").fetchone()["active"]

    assert active() is False
    site = Site(factsheet_pdf())
    site.pdf = b"not a pdf"                     # every file fails; the run reads nothing
    c = _run(site, Model())
    assert c["files_failed"] == 1 and active() is False
    _run(Site(factsheet_pdf()), Model())
    assert active() is True


def test_every_address_is_asked_of_robots_first_the_sitemap_included(conn, env):
    class Closed(Site):
        def handler(self, request):
            if request.url.path == "/robots.txt":
                self.hits.append(str(request.url))
                return httpx.Response(200, text="User-agent: *" + chr(10) + "Disallow: /sitemap.xml" + chr(10))
            return super().handler(request)

    from dgate.sources import cordis

    site = Closed(factsheet_pdf())
    with pytest.raises(cordis.RobotsDisallowed):
        _run(site, Model())
    assert not any(h.endswith("/sitemap.xml") for h in site.hits)
    assert conn.execute("SELECT status FROM ingest_run").fetchone()["status"] == "failed"

