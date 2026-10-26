"""WP-147: our side of Cloudflare's proxy mode. Caddy takes CF-Connecting-IP only from Cloudflare's published ranges and
sends that one address on to the API and the site; Let's Encrypt by HTTP-01 only; the ranges script and the origin lock
(prepared, not applied) do nothing without --yes. Lab runs with caddy:2.11.4, pebble and real ufw/iptables:
docs/verification/round6/wp147-selfcheck.md."""

from __future__ import annotations

import ipaddress
import os
import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
CADDYFILE = ROOT / "infra" / "caddy" / "Caddyfile"

# Cloudflare's lists as fetched on 26 Oct 2026 (https://www.cloudflare.com/ips-v4, /ips-v6).
CF_V4 = ("173.245.48.0/20 103.21.244.0/22 103.22.200.0/22 103.31.4.0/22 141.101.64.0/18 108.162.192.0/18 190.93.240.0/20 "
         "188.114.96.0/20 197.234.240.0/22 198.41.128.0/17 162.158.0.0/15 104.16.0.0/13 104.24.0.0/14 172.64.0.0/13 "
         "131.0.72.0/22").split()
CF_V6 = "2400:cb00::/32 2606:4700::/32 2803:f800::/32 2405:b500::/32 2405:8100::/32 2a06:98c0::/29 2c0f:f248::/32".split()


def _sh() -> str:
    """POSIX sh: /bin/sh on the server and CI, Git's usr/bin/sh.exe on the Windows dev machine (not Git's bin/sh.exe, a
    launcher that puts Git's own directories, real curl included, before the fakes on PATH)."""
    for c in (shutil.which("sh"), r"C:\Program Files\Git\usr\bin\sh.exe"):
        if c and Path(c).exists() and "system32" not in c.lower() and not c.lower().endswith(r"git\bin\sh.exe"):
            return c
    raise AssertionError("no POSIX sh found")


def _fakes(tmp: Path, scripts: dict[str, str]) -> dict[str, str]:
    """Commands of the same name first on PATH; each logs its arguments to calls.log."""
    bin_ = tmp / "bin"
    bin_.mkdir()
    for name, body in scripts.items():
        f = bin_ / name
        f.write_text(f'#!/bin/sh\necho "{name} $*" >> "{(tmp / "calls.log").as_posix()}"\n{body}\n', encoding="utf8", newline="\n")
        f.chmod(0o755)
    env = dict(os.environ)
    # the fakes first, then the shell's own tools (sed, awk, comm, mktemp: not on a Windows PATH)
    env["PATH"] = os.pathsep.join([str(bin_), str(Path(_sh()).parent), env["PATH"]])
    return env


def _run(script: str, args: list[str], env: dict[str, str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run([_sh(), (ROOT / "infra" / script).as_posix(), *args], env=env, cwd=cwd,
                          capture_output=True, text=True, timeout=60)


def _ranges(text: str) -> list[str]:
    return re.search(r"^\t\ttrusted_proxies static (.+)$", text, re.M).group(1).split()


# ---- Caddyfile --------------------------------------------------------------------------------------------------------

def test_the_client_address_is_cloudflares_header_only_from_cloudflares_ranges():
    text = CADDYFILE.read_text(encoding="utf8")
    servers = re.search(r"^\tservers \{\n(.*?)^\t\}", text, re.M | re.S).group(1)
    assert re.search(r"^\t\tclient_ip_headers CF-Connecting-IP$", servers, re.M)
    ranges = _ranges(servers)
    assert ranges == CF_V4 + CF_V6                       # Cloudflare's lists, nothing private, nothing else
    for r in ranges:
        assert ipaddress.ip_network(r).is_global, r
    assert re.search(r"# cloudflare-ranges fetched \d{4}-\d{2}-\d{2} from https://www\.cloudflare\.com/ips-v4", servers)


def test_both_upstreams_get_the_resolved_address_alone():
    # Without it Caddy appends the peer to a trusted proxy's list, which starts with what the visitor sent: the site reads
    # the first entry (7.7.7.7, forged) and the API the last (Cloudflare's), measured in the lab.
    text = CADDYFILE.read_text(encoding="utf8")
    blocks = re.findall(r"reverse_proxy (\S+) \{(.*?)\n\t\t\}", text, re.S)
    assert {name for name, _ in blocks} == {"api-edge:8000", "web:3000"}
    for name, body in blocks:
        assert "header_up X-Forwarded-For {client_ip}" in body, name


def test_lets_encrypt_is_asked_for_http_01_only():
    text = CADDYFILE.read_text(encoding="utf8")
    issuer = re.search(r"^\tcert_issuer acme \{\n(.*?)^\t\}", text, re.M | re.S).group(1)
    assert issuer.strip() == "disable_tlsalpn_challenge"          # no other CA, no email: the stored certificates stay


# ---- infra/cloudflare-ranges.sh ---------------------------------------------------------------------------------------

def _ranges_env(tmp: Path, v4: str, v6: str) -> dict[str, str]:
    (tmp / "ips-v4").write_text(v4, encoding="utf8", newline="\n")
    (tmp / "ips-v6").write_text(v6, encoding="utf8", newline="\n")
    env = _fakes(tmp, {"curl": f'case "$*" in *ips-v4*) cat "{(tmp / "ips-v4").as_posix()}";; '
                               f'*ips-v6*) cat "{(tmp / "ips-v6").as_posix()}";; esac'})
    caddy = tmp / "Caddyfile"
    shutil.copy(CADDYFILE, caddy)
    env["CADDYFILE"] = caddy.as_posix()
    env["CF_IPS_BASE"] = "https://cloudflare.invalid"      # never the real address from a test, even if a fake is missed
    return env


def test_ranges_script_prints_the_change_and_writes_only_with_yes(tmp_path):
    # no newline after the last line, as Cloudflare sends the lists
    new_v4 = "\n".join([r for r in CF_V4 if r != "131.0.72.0/22"] + ["198.51.100.0/24"])
    env = _ranges_env(tmp_path, new_v4, "\n".join(CF_V6))
    caddy = Path(env["CADDYFILE"])
    before = caddy.read_text(encoding="utf8")

    dry = _run("cloudflare-ranges.sh", [], env, tmp_path)
    assert dry.returncode == 0, dry.stderr
    assert "+ 198.51.100.0/24" in dry.stdout and "- 131.0.72.0/22" in dry.stdout and "dry run" in dry.stdout
    assert caddy.read_text(encoding="utf8") == before
    calls = (tmp_path / "calls.log").read_text()
    assert calls.count("curl") == 2 and "/ips-v4" in calls and "/ips-v6" in calls
    assert "BASE=${CF_IPS_BASE:-https://www.cloudflare.com}" in (ROOT / "infra" / "cloudflare-ranges.sh").read_text()

    wet = _run("cloudflare-ranges.sh", ["--yes"], env, tmp_path)
    assert wet.returncode == 0, wet.stderr
    after = caddy.read_text(encoding="utf8")
    assert "198.51.100.0/24" in _ranges(after) and "131.0.72.0/22" not in _ranges(after)
    assert len(_ranges(after)) == len(CF_V4) + len(CF_V6)
    assert after.count("trusted_proxies static") == 1
    assert re.search(r"cloudflare-ranges fetched \d{4}-\d{2}-\d{2} ", after)
    # the rest of the file is untouched
    assert re.sub(r".*trusted_proxies static.*|.*cloudflare-ranges fetched.*", "", after) == \
        re.sub(r".*trusted_proxies static.*|.*cloudflare-ranges fetched.*", "", before)

    again = _run("cloudflare-ranges.sh", [], env, tmp_path)
    assert "unchanged" in again.stdout


def test_ranges_script_refuses_an_answer_that_is_not_a_list(tmp_path):
    env = _ranges_env(tmp_path, "<html>Attention Required</html>\n", "\n".join(CF_V6) + "\n")
    caddy = Path(env["CADDYFILE"])
    before = caddy.read_text(encoding="utf8")
    r = _run("cloudflare-ranges.sh", ["--yes"], env, tmp_path)
    assert r.returncode == 1 and "nothing written" in r.stderr
    assert caddy.read_text(encoding="utf8") == before


# ---- infra/origin-lock.sh ---------------------------------------------------------------------------------------------

AFTER_RULES = "# ufw after.rules\n*filter\n:ufw-after-input - [0:0]\nCOMMIT\n"


def _lock_env(tmp: Path, cf_ray: bool = True) -> dict[str, str]:
    ufw = tmp / "ufw"
    ufw.mkdir()
    (ufw / "after.rules").write_text(AFTER_RULES, encoding="utf8", newline="\n")
    header = r"cf-ray: 1-FRA\r\n" if cf_ray else ""
    returns = "\n".join(f"-A DOCKER-USER -s {r} -j RETURN" for r in CF_V4)
    env = _fakes(tmp, {
        "ufw": "exit 0",
        "iptables": f'case "$*" in "-S DOCKER-USER") printf "%s\\n" "{returns}";; '
                    f'"-S FORWARD") echo "-A FORWARD -j DOCKER-USER";; esac',
        "iptables-restore": "cat > /dev/null",
        "ip": 'echo "default via 172.31.1.1 dev eth0 proto dhcp src 2.29.42.177 metric 100"',
        "docker": "exit 0",
        "curl": f'while [ $# -gt 0 ]; do [ "$1" = -D ] && printf "HTTP/2 200\\r\\n{header}\\r\\n" > "$2"; shift; done',
    })
    env.update(CADDYFILE=CADDYFILE.as_posix(), UFW_DIR=ufw.as_posix(), DGATE_DOMAIN="example.test")
    return env


def _calls(tmp: Path) -> list[str]:
    log = tmp / "calls.log"
    return log.read_text().splitlines() if log.exists() else []


def test_origin_lock_changes_nothing_without_yes(tmp_path):
    env = _lock_env(tmp_path)
    r = _run("origin-lock.sh", [], env, tmp_path)
    assert r.returncode == 0, r.stderr
    assert "dry run" in r.stdout and "-A DOCKER-USER -i eth0 -p tcp -m multiport --dports 80,443 -s 173.245.48.0/20 -j RETURN" in r.stdout
    assert (tmp_path / "ufw" / "after.rules").read_text() == AFTER_RULES
    assert not [c for c in _calls(tmp_path) if c.startswith(("ufw", "iptables", "curl", "docker"))]
    undo = _run("origin-lock.sh", ["--undo"], env, tmp_path)
    assert undo.returncode == 0 and "would run: ufw allow 80/tcp" in undo.stdout
    assert not [c for c in _calls(tmp_path) if c.startswith(("ufw", "iptables"))]


def test_origin_lock_refuses_while_the_site_is_not_behind_cloudflare(tmp_path):
    env = _lock_env(tmp_path, cf_ray=False)
    r = _run("origin-lock.sh", ["--yes"], env, tmp_path)
    assert r.returncode == 1 and "not answered through Cloudflare" in r.stderr
    assert (tmp_path / "ufw" / "after.rules").read_text() == AFTER_RULES
    assert not [c for c in _calls(tmp_path) if c.startswith("ufw")]


def test_origin_lock_applies_once_and_undoes(tmp_path):
    env = _lock_env(tmp_path)
    after = tmp_path / "ufw" / "after.rules"
    for _ in range(2):                                  # a re-run (new ranges) replaces the block, never adds a second
        r = _run("origin-lock.sh", ["--yes"], env, tmp_path)
        assert r.returncode == 0, r.stderr
    text = after.read_text()
    assert text.startswith(AFTER_RULES) and text.count("# BEGIN dgate-origin-lock") == 1
    block = text[len(AFTER_RULES):]
    assert ":DOCKER-USER - [0:0]" in block and block.count("-j RETURN") == len(CF_V4)
    assert block.strip().splitlines()[-3:] == [
        "-A DOCKER-USER -i eth0 -p tcp -m multiport --dports 80,443 -j DROP", "COMMIT", "# END dgate-origin-lock"]
    assert "22" not in re.sub(r"\d+\.\d+\.\d+\.\d+/\d+", "", block)       # SSH is never in it
    calls = _calls(tmp_path)
    assert "ufw delete allow 80/tcp" in calls and "ufw delete allow 443/tcp" in calls and "ufw reload" in calls
    assert any(c.startswith("curl") and "https://www.example.test/" in c for c in calls)
    assert (tmp_path / "ufw" / "after.rules.before-origin-lock").read_text() == AFTER_RULES

    (tmp_path / "calls.log").unlink()
    u = _run("origin-lock.sh", ["--undo", "--yes"], env, tmp_path)
    assert u.returncode == 0, u.stderr
    assert after.read_text() == AFTER_RULES
    assert _calls(tmp_path) == ["iptables -F DOCKER-USER", "ufw allow 80/tcp", "ufw allow 443/tcp", "ufw reload"]


def test_the_warm_up_goes_to_this_server_not_through_cloudflare():
    text = (ROOT / "infra" / "warm-after-deploy.sh").read_text(encoding="utf8")
    assert '--resolve "${DOMAIN:-localhost}:443:127.0.0.1"' in text
