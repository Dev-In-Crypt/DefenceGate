"""dgate.ops.logprune: a request log never holds a line older than the limit."""

import json
import os
import time

from dgate.ops import logprune

DAY = 86400


def _line(age_days: float, now: float, uri: str = "/") -> bytes:
    return (json.dumps({"ts": now - age_days * DAY, "request": {"uri": uri}}) + "\n").encode()


def test_old_lines_leave_the_active_file_and_the_rest_is_untouched(tmp_path):
    now = time.time()
    active = tmp_path / "access.log"
    active.write_bytes(_line(20, now, "/old") + _line(15, now, "/old2") + _line(13, now, "/a")
                       + _line(1, now, "/b") + _line(0, now, "/c"))
    deleted, cut = logprune.prune(tmp_path, 14, now)
    assert (deleted, cut) == (0, 2)
    kept = [json.loads(x)["request"]["uri"] for x in active.read_bytes().splitlines()]
    assert kept == ["/a", "/b", "/c"]
    # a second pass has nothing to do
    assert logprune.prune(tmp_path, 14, now) == (0, 0)


def test_a_line_with_no_timestamp_takes_the_age_of_the_line_before_it(tmp_path):
    now = time.time()
    active = tmp_path / "caddy.log"
    active.write_bytes(_line(30, now) + b"not json, old\n" + _line(2, now, "/new") + b"tail\n")
    logprune.prune(tmp_path, 14, now)
    assert active.read_bytes().splitlines()[0].startswith(b"{") and b"not json" not in active.read_bytes()
    assert active.read_bytes().endswith(b"tail\n")


def test_a_file_with_only_old_lines_is_emptied_in_place(tmp_path):
    now = time.time()
    active = tmp_path / "access.log"
    active.write_bytes(_line(40, now) + _line(30, now))
    inode = active.stat().st_ino
    logprune.prune(tmp_path, 14, now)
    assert active.read_bytes() == b"" and active.stat().st_ino == inode


def test_rolled_files_go_by_their_last_write(tmp_path):
    now = time.time()
    old = tmp_path / "access-2026-09-01T10-00-00.000.log"
    old_gz = tmp_path / "access-2026-09-02T10-00-00.000.log.gz"
    fresh = tmp_path / "access-2026-10-14T10-00-00.000.log"
    for f, age in ((old, 20), (old_gz, 15), (fresh, 1)):
        f.write_bytes(b"x")
        os.utime(f, (now - age * DAY, now - age * DAY))
    assert logprune.prune(tmp_path, 14, now) == (2, 0)
    assert [p.name for p in tmp_path.iterdir()] == [fresh.name]


def test_each_directory_keeps_its_own_limit(tmp_path):
    """WP-126: one service prunes the proxy logs at 14 days and the security log at 90."""
    now = time.time()
    proxy, security = tmp_path / "logs", tmp_path / "security"
    proxy.mkdir()
    security.mkdir()
    (proxy / "access.log").write_bytes(_line(30, now, "/p30") + _line(1, now, "/p1"))
    (security / "security.log").write_bytes(_line(100, now, "/s100") + _line(30, now, "/s30"))
    assert logprune.main(["--dir", str(proxy), "--dir", f"{security}=90", "--days", "14"]) == 0
    assert b"/p30" not in (proxy / "access.log").read_bytes()
    assert (security / "security.log").read_bytes() == _line(30, now, "/s30")


def test_security_log_goes_to_its_file_as_lines_logprune_can_cut(tmp_path, monkeypatch, capsys):
    """WP-126: with DGATE_SECURITY_LOG set the account events are JSON lines with `ts` in that file
    and nothing reaches stderr (the container log, rotated by size only)."""
    from dgate import accounts
    from dgate.config import settings

    path = tmp_path / "security.log"
    monkeypatch.setenv("DGATE_SECURITY_LOG", str(path))
    settings.cache_clear()
    handlers, propagate = list(accounts.log.handlers), accounts.log.propagate
    try:
        accounts.security_log_to_file()
        accounts._audit("signed_in", 42)
        for h in accounts.log.handlers:
            h.flush()
        line = json.loads(path.read_bytes().splitlines()[-1])
        assert line["msg"] == "account event=signed_in user=42" and abs(line["ts"] - time.time()) < 60
        assert "signed_in" not in capsys.readouterr().err
        # aged past 90 days, logprune cuts it
        assert logprune.prune(tmp_path, 90, now=line["ts"] + 91 * DAY) == (0, 1)
    finally:
        for h in list(accounts.log.handlers):
            accounts.log.removeHandler(h)
            h.close()
        for h in handlers:
            accounts.log.addHandler(h)
        accounts.log.propagate = propagate
        settings.cache_clear()
