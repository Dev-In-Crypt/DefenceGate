-- WP-71 (QA M4): the archive guard let `valid_to` be rewritten -- set back to NULL, which
-- reopens a closed version, or moved -- and nothing stopped two open versions of one
-- notice, which `append_version` would then close together. Closing a version stays the
-- one permitted update, and it is allowed once: from NULL to a value.
--
-- Production was checked read-only before this was written (21 October 2026): no notice
-- has two open versions, none has none, and no `valid_to` precedes its `valid_from`.
-- The trigger keeps its name, so the break-glass step of docs/RUNBOOK.md still names it.

CREATE OR REPLACE FUNCTION opportunity_version_guard() RETURNS trigger AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION
            'opportunity_version is append-only: DELETE is never permitted (id=%)', OLD.id;
    END IF;

    IF NEW.id IS DISTINCT FROM OLD.id
       OR NEW.opportunity_id IS DISTINCT FROM OLD.opportunity_id
       OR NEW.version        IS DISTINCT FROM OLD.version
       OR NEW.observed_at    IS DISTINCT FROM OLD.observed_at
       OR NEW.valid_from     IS DISTINCT FROM OLD.valid_from
       OR NEW.payload::text  IS DISTINCT FROM OLD.payload::text
       OR NEW.changed_fields IS DISTINCT FROM OLD.changed_fields
       OR NEW.raw_hash       IS DISTINCT FROM OLD.raw_hash THEN
        RAISE EXCEPTION
            'opportunity_version is append-only: only valid_to may be updated (id=%)', OLD.id;
    END IF;

    IF OLD.valid_to IS NOT NULL AND NEW.valid_to IS DISTINCT FROM OLD.valid_to THEN
        RAISE EXCEPTION
            'opportunity_version is append-only: a closed version stays closed (id=%)', OLD.id;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE UNIQUE INDEX IF NOT EXISTS opportunity_version_one_open
    ON opportunity_version (opportunity_id) WHERE valid_to IS NULL;
