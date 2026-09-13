-- Notes on archived versions: how an archive that cannot rewrite itself says
-- that some of what it wrote was wrong.
--
-- opportunity_version is append-only, enforced by trigger, and that is correct:
-- an archive that can be edited is not evidence of anything. But on
-- 13 September 2026 it held versions that never happened. PLACSP was read
-- newest first, and old content re-read on later runs was archived as change,
-- so 75 notices carried histories flipping between the same two states -- one
-- with twelve versions for a single real change, left showing "open" after it
-- was awarded.
--
-- Deleting those versions is exactly what the trigger forbids, and should.
-- Instead each is annotated, and a correcting version is appended where the
-- current state was wrong. The record of the mistake stays in the archive
-- alongside the record of its correction, which is the honest shape for it.
--
-- kind:
--   reread        this content was already archived at an earlier version
--   out_of_order  published before the version it followed, so it was history
--                 arriving late rather than a change
--   correction    appended by a repair to restore the true current state

CREATE TABLE IF NOT EXISTS opportunity_version_note (
    id                     BIGSERIAL PRIMARY KEY,
    opportunity_version_id BIGINT NOT NULL REFERENCES opportunity_version(id),
    kind                   TEXT NOT NULL CHECK (kind IN ('reread', 'out_of_order', 'correction')),
    note                   TEXT NOT NULL,
    created_at             TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    UNIQUE (opportunity_version_id, kind)
);
