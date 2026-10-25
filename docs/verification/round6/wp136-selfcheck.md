# WP-136 self-check: 502s while the web container is replaced

Brief: `D:\DEFENCEGATE TESTS\verify-oct25\BUILDER-WP136.md`; evidence `D:\DEFENCEGATE TESTS\verify-oct25\ops-r10\04-caddy-deploy-window.log`.
Branch `wp-wp136` from `integration` (3d2a649). Infra only. No migration, no ops module. Production was only read (files and
logs over ssh; no exec, no reload, no restart). Lab: `D:\DEFENCEGATE TESTS\wp136\run.sh` and `lab\docker-compose.yml`.

## Before (production, r10 deploy, 25 Oct 2026)

- 10 x 502 from the site handler between 17:39:39 and 17:39:49 UTC, each in ~0.01 s; caddy.log:
  `dial tcp: lookup web on 127.0.0.11:53: server misbehaving`, duration 0.005 s. No hold of 30 s at all.
- The hold was never loaded. Read on the host:
  - `/opt/dgate/infra/Caddyfile`: inode 133590, 7313 bytes, changed 25 Oct 17:33:29 (the r10 checkout), 4 `lb_try_` lines.
  - The file the Caddy process sees (`/proc/<caddy pid>/root/etc/caddy/Caddyfile`): inode 180317, 6383 bytes, changed
    21 Oct 17:44, **0 `lb_try_` lines**. `cmp`: different.
  - The running config (`caddyconfig` volume, `caddy/autosave.json`, written 21 Oct 17:53): no `try_duration`.
  - caddy.log: both reloads of 25 Oct (16:46:53 and 17:39:55, the deploy's step 4) logged `config is unchanged`; the POST
    to `/load` was 4229 bytes, the size of the 21 Oct autosave.
- Cause: `./Caddyfile:/etc/caddy/Caddyfile:ro` is a single-file bind mount. Docker binds the inode that is there when the
  container starts; `git checkout` writes a new file and renames it over the old one, so the container kept reading the
  21 Oct file and every `caddy reload` re-read it. Not a DNS error class or a retry rule: Caddy 2.11.4 does retry a failed
  lookup as a dial error (lab below). The API path had no 502 in r10 only because almost nothing calls `/v1` through Caddy
  in those 20 s (the site calls `api:8000` directly); it had no hold either.
- Also not live since 21 Oct, for the same reason: WP-124's request body caps (64KB on `/api/billing/webhook`, 4KB
  elsewhere); production still caps every path, the billing webhook included, at 4KB. They go live with the first deploy
  below.

## Change

- `infra/Caddyfile` moved to `infra/caddy/Caddyfile` (content unchanged); compose mounts the directory:
  `./caddy:/etc/caddy:ro`. A rename inside a bind-mounted directory is visible in the container.
- New `infra/caddy-reload.sh` (`set -eu`), at the orchestrator's request: (1) `caddy validate` of the checked-out
  `infra/caddy/` in a throwaway container of the proxy's own image (`docker inspect` of `dgate-caddy-1`), `--network none`,
  `DGATE_DOMAIN` from `infra/.env`, before the running proxy is touched; (2) `caddy reload` in place, or with `RECREATE=1`
  `up -d --no-build --no-deps --force-recreate caddy`; (3) sha256 of `infra/caddy/Caddyfile` on the host against
  `/etc/caddy/Caddyfile` in the container, `exit 1` with both sums on a difference.
- Deploy order in the header of `infra/docker-compose.yml`: Caddy is now step 2 (`sh infra/caddy-reload.sh`), before api
  and web are replaced, so the hold is in force while they are. A failure stops the deploy there.
- Retry settings unchanged (WP-127): `lb_try_duration 30s`, `lb_try_interval 250ms`, no `retry_match`, so only a failed
  dial is retried for a non-GET; a request that reached the upstream is never sent twice.
- Path updates only (no assertion changed): `test_wp124.py`, `test_wp127.py`, `test_wp34.py`, `test_wp71.py`,
  `dgate/ops/logprune.py` (docstring), `docs/design/API_CONTRACT.md`. Left as they are (other packages' files, comments
  only): `web/app/(public)/auth/reset/page.tsx`, `web/app/(public)/organisations/page.tsx`, `web/e2e/wp63.spec.ts` still
  name `infra/Caddyfile` in a comment.

## Test

`backend/tests/unit/test_compose_env.py::test_caddy_mounts_the_directory_of_its_caddyfile_not_the_file`: caddy mounts
`./caddy:/etc/caddy:ro`, `infra/caddy/Caddyfile` exists, no file of the checkout is bind-mounted on its own (`./secrets/*`
excepted: not in the repository), the deploy order runs `infra/caddy-reload.sh` before `api` and `web`, and the script
validates before it reloads, checks the container's sha256 after, and exits 1 on a difference.

## Lab (caddy:2.11.4, Docker Desktop)

`run.sh file|dir <Caddyfile>`: caddy in front of two stand-ins (`web:3000`, and `api-edge:8000` on an `edge` network), each
listening 6 s after its container starts. The "host" directory is in the Docker VM (a volume's `_data`, bind-mounted by
path), because a Windows path goes through Docker Desktop's file sharing, which does not pin the inode (a first run from a
Windows path loaded the new file and showed no 502). It starts with the Caddyfile under test minus its `lb_try_` lines (as
production ran since 21 Oct), deploys like production (new file renamed over the old one, `caddy reload`), then under two
curl loops (`/` and `/v1/health`, every 0.1 s, 70 s): `up -d --force-recreate --wait api`, the same for `web`, then both
containers removed for 6 s (no such name, the case production logged) and started again.

| run | mount | container sees new file | reload | `try_duration` running | site 502 | API 502 |
|---|---|---|---|---|---|---|
| `result-file-integration.txt` (integration's Caddyfile) | file | no (old inode, 0 `lb_try_`) | `config is unchanged` | 0 | **31** of 263 | **31** of 263 |
| `result-dir-wp-wp136.run1.txt` (this branch) | directory | yes (same inode, 4 `lb_try_`) | `load complete` | 2 | **0** of 234 | **0** of 230 |
| `result-dir-wp-wp136.txt` (repeat) | directory | yes | `load complete` | 2 | **0** of 225 | **0** of 223 |

Before, the errors were `connect: connection refused` x58 (container up, process not yet listening) and
`lookup web|api-edge: i/o timeout` x4 (no container; Docker Desktop's resolver times out where production's answers
"server misbehaving" at once; both are dial errors to Caddy). After, the slowest request was 14.6 s (held through two 5 s
lookup timeouts and the 6 s gap), below the 30 s hold. The API path (`api-edge`) behaves the same as the site path.

## Deploy lab for the script (`D:\DEFENCEGATE TESTS\wp136\deploy-lab\drive.sh`, `drive.log`)

A real compose project `dgate` (only `caddy`, dummy `.env`), the checkout in a Linux directory of the Docker VM, driven from
a `docker:27-cli` container. Start: integration's compose (single-file mount) with the WP-71 Caddyfile of 21 Oct, then a
"pull" to this branch (files renamed over, `infra/Caddyfile` gone, `infra/caddy/` new):

| step | result | running config after |
|---|---|---|
| A: `sh infra/caddy-reload.sh` on the old container | `Valid configuration`, reload, then **FAILED** host `1a318c8c...` container `5043ceb8...` (the same two sums as on production), exit 1 | `max_size` 4000 only, no `try_duration` |
| B: `RECREATE=1 sh infra/caddy-reload.sh` | ok `1a318c8c...`, exit 0 | `max_size` 64000 + 4000, `try_duration` 30 s x 2, `try_interval` 250 ms x 2 |
| C: next pull changes `lb_try_interval` to 200 ms, plain reload | ok, exit 0 | `try_interval` 200 ms x 2 |
| D: next pull leaves a broken Caddyfile | `caddy validate` fails (`unexpected EOF`), exit 1, no reload | unchanged (200 ms) |

## Validation of the full Caddyfile that goes live at round 11

`caddy:2.11.4 caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile` with `DGATE_DOMAIN=defencegatehub.com` and
this branch's `infra/caddy/`: `Valid configuration`, no warning or error line.

Production runs `infra/Caddyfile` of 2f01cb4 (WP-71, 21 Oct; sha256 `5043ceb8...`, 6383 bytes, matches the container's copy).
Changed since, in two commits (`git log -p` from 2f01cb4), all of it goes live in one step:

- 38a2fbd (WP-127): `lb_try_duration 30s` and `lb_try_interval 250ms` in `reverse_proxy api-edge:8000` and in
  `reverse_proxy web:3000` (a failed dial is held and retried up to 30 s; no `retry_match`, so a request that reached an
  upstream is not sent again, except a GET whose upstream failed after the connection, Caddy's default); comment above the
  site handler.
- 08ec387 (WP-124): the single `request_body { max_size 4KB }` becomes `@billing_webhook path /api/billing/webhook` +
  `request_body @billing_webhook { max_size 64KB }` and `@not_billing_webhook not path /api/billing/webhook` +
  `request_body @not_billing_webhook { max_size 4KB }`. Until then a Creem webhook over 4KB gets 413 at the proxy.
- Nothing else: the headers, methods, `@public` path list, `/v1` 404, `response_buffers`, the 500-to-503 handler, the logs
  and their token filter, and the www redirect are byte-for-byte the 21 Oct ones.

## What the deploy must do differently

1. At the first deploy of this branch (round 11), after the checkout and before api and web: `RECREATE=1 sh
   infra/caddy-reload.sh` (validates, recreates caddy with the directory mount, which drops connections for about a second;
   certificates stay in the `caddydata` volume; then the sha256 check). From then on WP-127's hold and WP-124's body caps
   are live.
2. Every later deploy: `sh infra/caddy-reload.sh` **before** replacing api and web, not a bare `caddy reload` after them;
   stop the deploy if it exits non-zero.

## Suite

Backend in `D:\DEFENCEGATE TESTS\wp136` (own venv, Postgres 17 `dgate-wp136`, removed after): ruff clean; unit 4028
passed (final tree); integration 1536 passed (16.5 min; the tree before `caddy-reload.sh`, which no integration test reads).
No web file changed, so no tsc or Playwright run. Lab containers, networks and volumes removed.

## Open

- The `caddy:2` tag in compose is not pinned; production's image is 2.11.4, the script validates with whatever image the
  running container uses, so validation and runtime always match. A pin is a separate decision.
- WP-127's comment says a request that reached the upstream is never sent twice. Without `lb_retry_match`, Caddy still
  retries a GET whose round trip failed after connecting (its default), within the 30 s; unchanged here.
