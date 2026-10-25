"""A local stand-in for Creem's API, for the end-to-end test of WP-124 (web/e2e/wp124.spec.ts) only.

It answers the two calls the API makes (docs.creem.io: POST /v1/checkouts -> id, checkout_url; POST
/v1/customers/billing -> customer_portal_link), serves a plain page at the checkout and portal addresses
it hands out, and tells the test what the last checkout request was (GET /__last), so the test can sign
the event Creem would send. Nothing leaves 127.0.0.1. Started by tests/e2e_api.py when E2E_CREEM_MOCK_PORT is set.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def serve(port: int) -> ThreadingHTTPServer:
    state: dict = {"n": 0, "last": None}
    origin = f"http://127.0.0.1:{port}"

    class Handler(BaseHTTPRequestHandler):
        def _send(self, status: int, body: bytes, kind: str = "application/json") -> None:
            self.send_response(status)
            self.send_header("content-type", kind)
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self) -> None:  # noqa: N802 - the stdlib's name
            body = json.loads(self.rfile.read(int(self.headers.get("content-length") or 0)) or b"{}")
            if not self.headers.get("x-api-key"):
                return self._send(403, b'{"error": "no key"}')
            if self.path == "/v1/checkouts":
                state["n"] += 1
                cid = f"ch_e2e_{state['n']}"
                state["last"] = {"id": cid, **body}
                return self._send(200, json.dumps({"id": cid, "checkout_url": f"{origin}/checkout/{cid}"}).encode())
            if self.path == "/v1/customers/billing":
                link = f"{origin}/portal/{body.get('customer_id')}"
                return self._send(200, json.dumps({"customer_portal_link": link}).encode())
            self._send(404, b"{}")

        def do_GET(self) -> None:  # noqa: N802
            if self.path == "/__last":
                return self._send(200, json.dumps(state["last"]).encode())
            if self.path.startswith(("/checkout/", "/portal/")):
                title = "Mock Creem checkout" if self.path.startswith("/checkout/") else "Mock Creem customer portal"
                return self._send(200, f"<!doctype html><title>{title}</title><h1>{title}</h1>".encode(), "text/html")
            self._send(404, b"{}")

        def log_message(self, *_args) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server
