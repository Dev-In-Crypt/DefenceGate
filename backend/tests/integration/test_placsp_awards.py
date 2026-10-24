"""PLACSP award winners (WP-60) against a real Postgres: the archive walk lands and loads the winners next to
the notices, keeps no person anywhere, is a no-op the second time, follows a winner that changes, does not
move a notice's hash, replays from the raw store without a download, and stays off the supplier map unless
switched on. The ops command resumes and marks what it finished.

The notice is the stripped real defence entry of `fixtures/placsp_live_entries.atom` (Directive 2009/81/EC),
made an awarded one. Every winner's name and number is made up.
"""

from __future__ import annotations

import io
import json
import zipfile
from datetime import date, datetime, timezone
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from dgate import api, config, pipeline, placsp_awards
from dgate.ops import placsp_archives
from dgate.rawstore import build_store
from dgate.sources import placsp

pytestmark = pytest.mark.integration

XML = (Path(__file__).resolve().parents[1] / "fixtures" / "placsp_live_entries.atom").read_text(encoding="utf-8")
NATIVE = "2026/ETSAE0921/00001111E"
START = XML.rindex("<entry>")                      # the third entry: the defence one
HEAD = XML[:XML.index("<entry>")]
DEFENCE = XML[START:XML.index("</entry>", START) + len("</entry>")]


def winner(name: str, ident: str, country: str = "ES") -> str:
    return (f"<cac:WinningParty><cac:PartyIdentification><cbc:ID schemeName=\"NIF\">{ident}</cbc:ID>"
            f"</cac:PartyIdentification><cac:PartyName><cbc:Name>{name}</cbc:Name></cac:PartyName>"
            f"<cac:PhysicalLocation><cac:Address><cbc:CityName>Ciudad Inventada</cbc:CityName>"
            f"<cac:Country><cbc:IdentificationCode>{country}</cbc:IdentificationCode></cac:Country>"
            f"</cac:Address></cac:PhysicalLocation></cac:WinningParty>")


def result(lot: str, party: str, code: str = "8") -> str:
    return (f"<cac:TenderResult><cbc:ResultCode>{code}</cbc:ResultCode><cbc:AwardDate>2026-09-15</cbc:AwardDate>"
            f"<cbc:ReceivedTenderQuantity>3</cbc:ReceivedTenderQuantity>{party}<cac:AwardedTenderedProject>"
            f"<cbc:ProcurementProjectLotID>{lot}</cbc:ProcurementProjectLotID><cac:LegalMonetaryTotal>"
            f"<cbc:TaxExclusiveAmount currencyID=\"EUR\">250000.00</cbc:TaxExclusiveAmount></cac:LegalMonetaryTotal>"
            f"</cac:AwardedTenderedProject></cac:TenderResult>")


ALFA = winner("ALFA DEFENSA INVENTADA, S.L.", "B99999997")
BETA = winner("BETA SISTEMAS INVENTADOS SA", "A99999971")
PERSON = winner("PEREZ GOMEZ ANTONIO", "***9999**")


def awarded(results: str, *, status: str = "ADJ", updated: str = "2026-09-20T10:00:00.000+02:00",
            folder: str = NATIVE) -> str:
    e = (DEFENCE.replace(">PUB</cbc-place-ext:ContractFolderStatusCode>",
                         f">{status}</cbc-place-ext:ContractFolderStatusCode>")
         .replace("<updated>2026-10-10T14:41:55.557+02:00</updated>", f"<updated>{updated}</updated>")
         .replace("<cac-place-ext:LocatedContractingParty>", results + "<cac-place-ext:LocatedContractingParty>"))
    return e.replace(NATIVE, folder)


def archive(*entries: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("part.atom", HEAD + "".join(entries) + "</feed>")
    return buf.getvalue()


class Portal:
    """Serves archives by URL and logs what was asked (GET and HEAD)."""

    def __init__(self, files: dict[str, bytes]):
        self.files, self.asked = files, []

    def client(self) -> httpx.Client:
        def handler(request: httpx.Request) -> httpx.Response:
            self.asked.append((request.method, str(request.url)))
            body = next((b for k, b in self.files.items() if str(request.url).endswith(k)), None)
            if body is None:
                return httpx.Response(404)
            return httpx.Response(200, content=b"" if request.method == "HEAD" else body,
                                  headers={"content-length": str(len(body))})
        return httpx.Client(transport=httpx.MockTransport(handler))


@pytest.fixture()
def env(conn, tmp_path, monkeypatch):
    monkeypatch.setenv("DGATE_RAW_BACKEND", "fs")
    monkeypatch.setenv("DGATE_RAW_DIR", str(tmp_path / "raw"))
    monkeypatch.delenv("DGATE_PLACSP_AWARDS_PUBLIC", raising=False)
    config.reset_cache()
    yield tmp_path
    config.reset_cache()


def ingest(body: bytes, label: str = "t") -> tuple[int, int, int]:
    stream = placsp.fetch_archive("https://example.test/a.zip", client=Portal({"a.zip": body}).client(),
                                  with_results=True)
    return pipeline._ingest_placsp(stream, label, replay=True, awards=placsp_awards.Loader)


def counts(conn) -> dict[str, int]:
    return {t: conn.execute(f"SELECT count(*) AS n FROM {t}").fetchone()["n"]
            for t in ("opportunity", "opportunity_version", "award", "award_notice", "organisation",
                      "organisation_alias", "raw_ingest")}


def winners(conn, current: bool = True) -> list[str]:
    return [r["name_as_stated"] for r in conn.execute(
        f"""SELECT name_as_stated FROM award WHERE superseded_at IS {'' if current else 'NOT '}NULL
             ORDER BY name_as_stated""").fetchall()]


def test_the_walk_files_the_notice_and_its_company_winners_and_keeps_no_person(conn, env):
    fetched, new, _ = ingest(archive(awarded(result("1", ALFA) + result("2", PERSON) + result("3", ALFA))))
    assert (fetched, new) == (1, 1)                       # a notice we did not hold: the 2025 gap's path
    assert winners(conn) == ["ALFA DEFENSA INVENTADA, S.L."]
    notice = conn.execute("SELECT * FROM award_notice").fetchone()
    assert (notice["winners_seen"], notice["winners_kept"], notice["skipped_person"], notice["status"]) == \
        (2, 1, 1, "loaded")
    org = conn.execute("SELECT * FROM organisation o JOIN award a ON a.organisation_id = o.id").fetchone()
    assert org["country"] == "ES" and org["national_reg_no"] == "B99999997"
    # no person: not in organisation, alias, award, nor the raw store
    for table, col in (("organisation", "canonical_name"), ("organisation_alias", "raw_name"),
                       ("award", "name_as_stated")):
        assert conn.execute(f"SELECT count(*) AS n FROM {table} WHERE {col} ILIKE '%%perez%%'").fetchone()["n"] == 0
    landed = build_store().get(notice["raw_key"])
    blob = json.dumps(landed, ensure_ascii=False)
    assert "PEREZ" not in blob and "***9999**" not in blob and "Ciudad Inventada" not in blob
    assert landed["natural_persons"] == 1 and notice["raw_key"].startswith("placsp_awards/")
    assert conn.execute("""SELECT count(*) AS n FROM raw_ingest r JOIN source s ON s.id = r.source_id
                            WHERE s.code = 'es_placsp_awards'""").fetchone()["n"] == 1


def test_a_second_walk_writes_nothing(conn, env):
    body = archive(awarded(result("1", ALFA) + result("2", PERSON)))
    ingest(body)
    before = counts(conn)
    ingest(body)
    assert counts(conn) == before


def test_the_awards_do_not_move_the_notice_hash_or_make_a_version(conn, env):
    """The same entries walked without and then with the award payloads: one version, the same hash."""
    body = archive(awarded(result("1", ALFA)))
    stream = placsp.fetch_archive("https://example.test/a.zip", client=Portal({"a.zip": body}).client())
    pipeline._ingest_placsp(stream, "plain", replay=True)
    v = conn.execute("SELECT raw_hash FROM opportunity_version").fetchall()
    ingest(body)
    assert conn.execute("SELECT raw_hash FROM opportunity_version").fetchall() == v and len(v) == 1
    assert winners(conn) == ["ALFA DEFENSA INVENTADA, S.L."]


def test_a_changed_winner_is_read_again_and_the_old_one_superseded_not_deleted(conn, env):
    ingest(archive(awarded(result("1", ALFA))))
    ingest(archive(awarded(result("1", BETA), status="RES", updated="2026-10-01T10:00:00.000+02:00")))
    assert winners(conn) == ["BETA SISTEMAS INVENTADOS SA"]
    assert winners(conn, current=False) == ["ALFA DEFENSA INVENTADA, S.L."]
    # an older entry read late does not bring the first winner back
    ingest(archive(awarded(result("1", ALFA), updated="2026-09-25T10:00:00.000+02:00")))
    assert winners(conn) == ["BETA SISTEMAS INVENTADOS SA"]
    # the first winner named again, by a newer entry, is current again: the same row, not a new one
    ingest(archive(awarded(result("1", ALFA) + result("2", BETA), status="RES",
                           updated="2026-10-05T10:00:00.000+02:00")))
    assert winners(conn) == ["ALFA DEFENSA INVENTADA, S.L.", "BETA SISTEMAS INVENTADOS SA"]
    assert conn.execute("SELECT count(*) AS n FROM award").fetchone()["n"] == 2


def test_the_winners_are_replayed_from_the_raw_store_without_a_download(conn, env, monkeypatch):
    ingest(archive(awarded(result("1", ALFA) + result("2", PERSON))))
    before = counts(conn)

    def no_network(*a, **k):
        raise AssertionError("the replay must not download")

    monkeypatch.setattr(placsp, "fetch_archive", no_network)
    got = placsp_awards.replay_from_store(conn)
    assert got["notices"] == 1 and got["payloads_read"] == 1
    assert counts(conn) == before and winners(conn) == ["ALFA DEFENSA INVENTADA, S.L."]


def test_a_land_only_walk_writes_no_award_and_the_store_load_does_it_later(conn, env):
    body = archive(awarded(result("1", ALFA) + result("2", PERSON)))
    stream = placsp.fetch_archive("https://example.test/a.zip", client=Portal({"a.zip": body}).client(),
                                  with_results=True)
    pipeline._ingest_placsp(stream, "t", replay=True,
                            awards=lambda c: placsp_awards.Loader(c, land_only=True))
    assert counts(conn)["award"] == 0 and counts(conn)["award_notice"] == 0
    assert counts(conn)["raw_ingest"] == 2                        # the notice's payload and the award payload
    dry = placsp_awards.replay_from_store(conn, commit=False)     # measured, rolled back
    assert dry["awards_new"] == 1 and dry["skipped_person"] == 1 and counts(conn)["award"] == 0
    placsp_awards.replay_from_store(conn)
    assert winners(conn) == ["ALFA DEFENSA INVENTADA, S.L."]
    assert conn.execute("SELECT skipped_person FROM award_notice").fetchone()["skipped_person"] == 1


def test_the_supplier_map_leaves_placsp_winners_out_unless_switched_on(conn, env, monkeypatch):
    ingest(archive(awarded(result("1", ALFA) + result("2", PERSON))))
    # The core scope wants a defence buyer for a 2009/81 notice; the buyer list is not seeded in this test.
    conn.execute("UPDATE opportunity SET buyer_class = 'defence'")
    conn.commit()
    with TestClient(api.app) as client:
        assert client.get("/v1/suppliers").json()["total"] == 0
        assert client.get("/v1/suppliers/summary").json()["skippedNaturalPersons"] == 0
        monkeypatch.setenv("DGATE_PLACSP_AWARDS_PUBLIC", "true")
        config.reset_cache()
        items = client.get("/v1/suppliers").json()["items"]
        assert [i["name"] for i in items] == ["ALFA DEFENSA INVENTADA, S.L."]
        assert client.get("/v1/suppliers/summary").json()["skippedNaturalPersons"] == 1


def test_the_command_runs_one_month_marks_it_and_skips_it_next_time(conn, env, monkeypatch):
    portal = Portal({"_202609.zip": archive(awarded(result("1", ALFA)))})
    real = placsp.fetch_archive
    monkeypatch.setattr(placsp, "fetch_archive", lambda url, ds, **kw: real(url, ds, client=portal.client(), **kw))
    monkeypatch.setattr(placsp_archives, "free_bytes", lambda: 50 * 2**30)
    todo = placsp_archives.units((2026, 9), (2026, 9), placsp.MAIN, date(2026, 10, 20))
    noon = lambda: datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc)   # noqa: E731 - outside the live window
    got = placsp_archives.run(todo, placsp.MAIN, floor=3 * 2**30, resume=True, pause=0, now=noon,
                              sleep=lambda s: None)
    assert got["done"] == ["es_placsp-202609"] and winners(conn) == ["ALFA DEFENSA INVENTADA, S.L."]
    assert conn.execute("SELECT count(*) AS n FROM backfill_day WHERE source_code = 'es_placsp-awards'"
                        ).fetchone()["n"] == 1
    again = placsp_archives.run(todo, placsp.MAIN, floor=3 * 2**30, resume=True, pause=0, now=noon,
                                sleep=lambda s: None)
    assert again["skipped"] == ["es_placsp-202609"] and len([a for a in portal.asked if a[0] == "GET"]) == 1


def test_the_command_stops_cleanly_when_the_disk_is_short(conn, env, monkeypatch):
    monkeypatch.setattr(placsp_archives, "free_bytes", lambda: 2 * 2**30)
    todo = placsp_archives.units((2026, 9), (2026, 9), placsp.MAIN, date(2026, 10, 20))
    noon = lambda: datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc)   # noqa: E731
    got = placsp_archives.run(todo, placsp.MAIN, floor=3 * 2**30, resume=True, pause=0, now=noon,
                              sleep=lambda s: None)
    assert got["stopped"] == ["es_placsp-202609"] and counts(conn)["opportunity"] == 0


def test_a_month_with_an_unreadable_member_is_loaded_but_not_marked_done(conn, env, monkeypatch):
    """WP-71 (QA M7): a member that fails to parse was skipped with a log line and the month marked done,
    a permanent and invisible hole."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("part.atom", HEAD + awarded(result("1", ALFA)) + "</feed>")
        zf.writestr("broken.atom", HEAD + "<entry><unclosed></feed>")
    portal = Portal({"_202609.zip": buf.getvalue()})
    real = placsp.fetch_archive
    monkeypatch.setattr(placsp, "fetch_archive", lambda url, ds, **kw: real(url, ds, client=portal.client(), **kw))
    monkeypatch.setattr(placsp_archives, "free_bytes", lambda: 50 * 2**30)
    todo = placsp_archives.units((2026, 9), (2026, 9), placsp.MAIN, date(2026, 10, 20))
    noon = lambda: datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc)   # noqa: E731
    got = placsp_archives.run(todo, placsp.MAIN, floor=3 * 2**30, resume=True, pause=0, now=noon,
                              sleep=lambda s: None)
    assert got["failed"] == ["es_placsp-202609"] and got["done"] == []
    assert winners(conn) == ["ALFA DEFENSA INVENTADA, S.L."]                  # what was read is kept
    assert conn.execute("SELECT count(*) AS n FROM backfill_day WHERE source_code = 'es_placsp-awards'"
                        ).fetchone()["n"] == 0
