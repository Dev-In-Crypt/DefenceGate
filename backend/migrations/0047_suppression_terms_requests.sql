-- Durable suppression, terms acceptance, request log (owner decision of 15 October 2026,
-- docs/legal/OPEN_ITEMS_FOR_LAWYER.md "Engineering follow-up" 1, 2 and 5).
--
-- Additive and idempotent. Nothing in the archive is touched: `opportunity_version` keeps
-- every row; suppression is a flag on the serving row that every public read honours and
-- that a re-ingest cannot clear (a BEFORE INSERT/UPDATE trigger recomputes it from the
-- `suppression` table, so the worker, the replays and every ops tool are covered at once).

-- ---------------------------------------------------------------- suppression
CREATE TABLE IF NOT EXISTS suppression (
    id              bigserial PRIMARY KEY,
    kind            text NOT NULL CHECK (kind IN ('notice', 'organisation', 'document')),
    -- notice: source.code + the source's native id. document: programme.code + call native id.
    source_code     text,
    native_id       text,
    organisation_id bigint,
    reason          text NOT NULL CHECK (reason ~ '^[a-z][a-z_]{1,39}$'),
    requested_at    timestamptz NOT NULL,
    decided_by      text NOT NULL CHECK (length(decided_by) BETWEEN 1 AND 100),
    note            text NOT NULL DEFAULT '' CHECK (length(note) <= 1000),
    created_at      timestamptz NOT NULL DEFAULT now(),
    lifted_at       timestamptz,
    lifted_by       text,
    lifted_note     text,
    CHECK ((kind = 'organisation') = (organisation_id IS NOT NULL)),
    CHECK (kind = 'organisation' OR (source_code IS NOT NULL AND native_id IS NOT NULL))
);
-- One active entry per subject; lifted entries stay as the history.
CREATE UNIQUE INDEX IF NOT EXISTS suppression_one_active ON suppression
    (kind, coalesce(source_code, ''), coalesce(native_id, ''), coalesce(organisation_id, 0))
    WHERE lifted_at IS NULL;

ALTER TABLE opportunity  ADD COLUMN IF NOT EXISTS suppressed boolean NOT NULL DEFAULT false;
ALTER TABLE opportunity  ADD COLUMN IF NOT EXISTS buyer_withheld boolean NOT NULL DEFAULT false;
ALTER TABLE organisation ADD COLUMN IF NOT EXISTS suppressed boolean NOT NULL DEFAULT false;
ALTER TABLE call         ADD COLUMN IF NOT EXISTS suppressed boolean NOT NULL DEFAULT false;

-- Neither table is ever deleted from.
CREATE OR REPLACE FUNCTION dgate_no_delete() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION '% is append-only: rows are never deleted', TG_TABLE_NAME;
END
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS suppression_no_delete ON suppression;
CREATE TRIGGER suppression_no_delete BEFORE DELETE ON suppression
    FOR EACH ROW EXECUTE FUNCTION dgate_no_delete();

-- A notice or call that is written (first seen, or its buyer re-resolved) takes its flags
-- from the table, whoever writes it.
CREATE OR REPLACE FUNCTION dgate_opportunity_suppression() RETURNS trigger AS $$
BEGIN
    NEW.suppressed := EXISTS (
        SELECT 1 FROM suppression s JOIN source src ON src.code = s.source_code
         WHERE s.kind = 'notice' AND s.lifted_at IS NULL
           AND src.id = NEW.source_id AND s.native_id = NEW.native_id);
    NEW.buyer_withheld := NEW.buyer_org_id IS NOT NULL AND EXISTS (
        SELECT 1 FROM suppression s
         WHERE s.kind = 'organisation' AND s.lifted_at IS NULL
           AND s.organisation_id = NEW.buyer_org_id);
    RETURN NEW;
END
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS opportunity_suppression ON opportunity;
CREATE TRIGGER opportunity_suppression BEFORE INSERT OR UPDATE OF buyer_org_id, native_id
    ON opportunity FOR EACH ROW EXECUTE FUNCTION dgate_opportunity_suppression();

CREATE OR REPLACE FUNCTION dgate_call_suppression() RETURNS trigger AS $$
BEGIN
    NEW.suppressed := EXISTS (
        SELECT 1 FROM suppression s JOIN programme p ON p.code = s.source_code
         WHERE s.kind = 'document' AND s.lifted_at IS NULL
           AND p.id = NEW.programme_id AND s.native_id = NEW.native_id);
    RETURN NEW;
END
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS call_suppression ON call;
CREATE TRIGGER call_suppression BEFORE INSERT OR UPDATE OF native_id, programme_id
    ON call FOR EACH ROW EXECUTE FUNCTION dgate_call_suppression();

-- Adding or lifting an entry applies it to the rows already held, in the same transaction.
CREATE OR REPLACE FUNCTION dgate_suppression_apply() RETURNS trigger AS $$
DECLARE
    on_ boolean := NEW.lifted_at IS NULL;
BEGIN
    IF NEW.kind = 'notice' THEN
        UPDATE opportunity o SET suppressed = on_
          FROM source s
         WHERE s.code = NEW.source_code AND o.source_id = s.id AND o.native_id = NEW.native_id;
    ELSIF NEW.kind = 'organisation' THEN
        UPDATE organisation SET suppressed = on_ WHERE id = NEW.organisation_id;
        UPDATE opportunity SET buyer_withheld = on_ WHERE buyer_org_id = NEW.organisation_id;
    ELSE
        UPDATE call c SET suppressed = on_
          FROM programme p
         WHERE p.code = NEW.source_code AND c.programme_id = p.id AND c.native_id = NEW.native_id;
    END IF;
    RETURN NULL;
END
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS suppression_apply ON suppression;
CREATE TRIGGER suppression_apply AFTER INSERT OR UPDATE OF lifted_at ON suppression
    FOR EACH ROW EXECUTE FUNCTION dgate_suppression_apply();

-- ------------------------------------------------------------- request log
-- What the owner types and nothing else: no requester name, address or message. A
-- request is closed by setting status and closed_at; a row is never deleted.
CREATE TABLE IF NOT EXISTS data_request (
    id           bigserial PRIMARY KEY,
    received_at  timestamptz NOT NULL,
    kind         text NOT NULL CHECK (kind IN ('access', 'rectification', 'erasure',
                     'restriction', 'objection', 'portability', 'removal', 'other')),
    status       text NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'closed', 'refused')),
    closed_at    timestamptz,
    handler_note text NOT NULL DEFAULT '' CHECK (length(handler_note) <= 1000),
    created_at   timestamptz NOT NULL DEFAULT now()
);
DROP TRIGGER IF EXISTS data_request_no_delete ON data_request;
CREATE TRIGGER data_request_no_delete BEFORE DELETE ON data_request
    FOR EACH ROW EXECUTE FUNCTION dgate_no_delete();

-- Both hold what the owner typed: the public API role and the accounts role never read them.
REVOKE ALL ON suppression, data_request FROM dgate_api, dgate_app;
REVOKE ALL ON SEQUENCE suppression_id_seq, data_request_id_seq FROM dgate_api, dgate_app;
-- The worker role runs the owner's CLIs; the delete triggers above refuse DELETE anyway.

-- ------------------------------------------------------------ terms acceptance
-- Recorded at the first verified sign-in and again when the versions change. The tick is
-- on the sign-in form; the versions travel on the one-time link row until it is used.
ALTER TABLE app_user ADD COLUMN IF NOT EXISTS terms_version text;
ALTER TABLE app_user ADD COLUMN IF NOT EXISTS privacy_version text;
ALTER TABLE app_user ADD COLUMN IF NOT EXISTS accepted_at timestamptz;
ALTER TABLE app_login_token ADD COLUMN IF NOT EXISTS terms_version text;
ALTER TABLE app_login_token ADD COLUMN IF NOT EXISTS privacy_version text;
ALTER TABLE app_login_token ADD COLUMN IF NOT EXISTS accepted_at timestamptz;
