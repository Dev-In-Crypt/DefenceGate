"""The account API for the end-to-end test of WP-123 (web/e2e/wp123.spec.ts), never for anything else.

    DGATE_DSN=... DGATE_MAIL_CATCHER_DIR=... DGATE_SITE_URL=https://localhost:3443 \
        python -m tests.e2e_api 8123

It is the real API with one change: accounts are opened as they will be once the privacy notice for password
accounts (1.7) is published, which the committed constants do not allow yet (accounts.accounts_problem). Mail goes
to the development catcher (.eml files), so the test reads the links without any provider. Refuses production.
"""

from __future__ import annotations

import os
import sys

import uvicorn

from dgate import accounts
from dgate.api import app

if __name__ == "__main__":
    if os.environ.get("DGATE_ENV", "").lower() == "production" or not os.environ.get("DGATE_MAIL_CATCHER_DIR"):
        sys.exit("e2e_api: development only, and DGATE_MAIL_CATCHER_DIR must be set")
    accounts.PASSWORD_PRIVACY_VERSION = accounts.PRIVACY_VERSION
    # WP-124 (web/e2e/wp124.spec.ts): Creem's API answered by a local stand-in; the billing settings come from the
    # environment as on the server (test values only), with DGATE_CREEM_API_URL pointing at the stand-in.
    if os.environ.get("E2E_CREEM_MOCK_PORT"):
        from tests.creem_mock import serve

        serve(int(os.environ["E2E_CREEM_MOCK_PORT"]))
    uvicorn.run(app, host="127.0.0.1", port=int(sys.argv[1] if len(sys.argv) > 1 else 8123), log_level="warning")
