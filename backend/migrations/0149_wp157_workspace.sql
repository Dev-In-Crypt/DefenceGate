-- WP-157 (30 October 2026): the team workspace (Team, Consultant) and the client profiles (Consultant). dgate/workspace.py.
-- Built to docs/SECURITY_REQUIREMENTS.md O1-O3 and the token rules of A2 (random, hashed, single-use, expiring). Additive and
-- idempotent.

-- One workspace per owner. Its members share the owner's plan (billing.plan_of) and see one another's saved searches,
-- shortlist and follows. Goes with the owner's account.
CREATE TABLE IF NOT EXISTS workspace (
    id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id   uuid NOT NULL UNIQUE REFERENCES app_user (id) ON DELETE CASCADE,
    created_at timestamptz NOT NULL DEFAULT now()
);

-- Who is in it, the owner included (role 'owner'). An account is in one workspace at most.
CREATE TABLE IF NOT EXISTS workspace_member (
    workspace_id uuid NOT NULL REFERENCES workspace (id) ON DELETE CASCADE,
    user_id      uuid NOT NULL UNIQUE REFERENCES app_user (id) ON DELETE CASCADE,
    role         text NOT NULL CHECK (role IN ('owner', 'member')),
    joined_at    timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (workspace_id, user_id)
);
CREATE UNIQUE INDEX IF NOT EXISTS workspace_member_one_owner ON workspace_member (workspace_id) WHERE role = 'owner';

-- An invitation by e-mail: the address the owner typed (personal data, docs/legal/drafts/data-protection-workspace-draft.md) and the
-- SHA-256 of a 256-bit one-time token; the token itself is only in the mail. Used once, expires in 7 days, deleted a day
-- after either. One open invitation per address and workspace (a new one replaces it).
CREATE TABLE IF NOT EXISTS workspace_invite (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id    uuid NOT NULL REFERENCES workspace (id) ON DELETE CASCADE,
    email_canonical text NOT NULL CHECK (length(email_canonical) <= 320),
    email_display   text NOT NULL CHECK (length(email_display) <= 320),
    token_hash      bytea NOT NULL UNIQUE,
    created_at      timestamptz NOT NULL DEFAULT now(),
    expires_at      timestamptz NOT NULL,
    used_at         timestamptz,
    UNIQUE (workspace_id, email_canonical)
);
CREATE INDEX IF NOT EXISTS workspace_invite_expires ON workspace_invite (expires_at);

-- A consultant's client: commercial data only (a company name, its country, the CPV codes it sells under, a note).
CREATE TABLE IF NOT EXISTS app_client (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id uuid NOT NULL REFERENCES workspace (id) ON DELETE CASCADE,
    name         text NOT NULL CHECK (char_length(name) BETWEEN 1 AND 120),
    country      text CHECK (country ~ '^[A-Z]{2}$'),
    cpv_codes    text[] NOT NULL DEFAULT '{}' CHECK (cardinality(cpv_codes) <= 20),
    note         text NOT NULL DEFAULT '' CHECK (char_length(note) <= 500),
    created_at   timestamptz NOT NULL DEFAULT now(),
    updated_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS app_client_workspace ON app_client (workspace_id, name);

-- The shared rows: a member's saved searches, shortlist and follows carry the workspace while the member is in it; a saved
-- search or a shortlist entry can belong to a client. Leaving, a removal or the end of the workspace clears both.
ALTER TABLE app_saved_search ADD COLUMN IF NOT EXISTS workspace_id uuid REFERENCES workspace (id) ON DELETE SET NULL;
ALTER TABLE app_saved_search ADD COLUMN IF NOT EXISTS client_id uuid REFERENCES app_client (id) ON DELETE SET NULL;
ALTER TABLE app_shortlist ADD COLUMN IF NOT EXISTS workspace_id uuid REFERENCES workspace (id) ON DELETE SET NULL;
ALTER TABLE app_shortlist ADD COLUMN IF NOT EXISTS client_id uuid REFERENCES app_client (id) ON DELETE SET NULL;
ALTER TABLE app_follow ADD COLUMN IF NOT EXISTS workspace_id uuid REFERENCES workspace (id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS app_saved_search_workspace ON app_saved_search (workspace_id) WHERE workspace_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS app_shortlist_workspace ON app_shortlist (workspace_id) WHERE workspace_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS app_follow_workspace ON app_follow (workspace_id) WHERE workspace_id IS NOT NULL;

-- As for the other account tables: the accounts role writes them, the public API role reads nothing, the worker reads them
-- (the alert digest reads the owner's plan through the membership; pg_dump).
REVOKE ALL ON workspace, workspace_member, workspace_invite, app_client FROM dgate_api, dgate_worker;
GRANT SELECT, INSERT, UPDATE, DELETE ON workspace, workspace_member, workspace_invite, app_client TO dgate_app;
GRANT SELECT ON workspace, workspace_member, workspace_invite, app_client TO dgate_worker;
