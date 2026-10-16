-- Funding changes (ux-funding F5, 16 October 2026). Additive and idempotent.
--
-- A call is a living row, not an archive (db.upsert_call): the serving row holds the current
-- truth and the earlier state is only in the raw store. So "the deadline moved" had no place
-- to be read from, and the change list and the Atom feed could say nothing about funding.
--
-- One row per date the SOURCE changed on a call it already held: the closing date or the
-- opening date. Written by upsert_call when the payload itself changed; never for our own
-- re-reading of an unchanged payload (a correction, not a move by the publisher). A new call
-- needs no row: `call.first_seen_at` is its first sighting.
--
-- Values are text (ISO date or timestamp) so one column serves both fields. Nothing here is
-- personal data and nothing describes a system.

CREATE TABLE IF NOT EXISTS call_change (
    id           BIGSERIAL PRIMARY KEY,
    call_id      BIGINT NOT NULL REFERENCES call(id),
    field        TEXT NOT NULL CHECK (field IN ('deadline_at', 'opens_at')),
    before_value TEXT,
    after_value  TEXT,
    observed_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS call_change_observed ON call_change (observed_at DESC);
CREATE INDEX IF NOT EXISTS call_change_call ON call_change (call_id);
