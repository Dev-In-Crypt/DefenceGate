-- Germany: the national notice service (Bekanntmachungsservice, BKMS), day files in eForms.
--
-- Seeded INACTIVE and with `commercial_ok` NULL: the interface is open and anonymous, but
-- the licence text could not be found (docs/sources/de_national.md, question 9). Until the
-- owner has the lawyer's answer and sets `active = TRUE`:
--   * the scheduled job does nothing (worker.job_de_bkms), a manual run needs --force;
--   * every row of this source is held back from every public read, through the same flag
--     as a takedown (`opportunity.suppressed`), which the trigger below computes for any
--     writer, and which flips with `source.active` in one statement.
-- Nothing is deleted: the archive and the raw store keep what a forced run landed.
--
-- Additive and idempotent.

INSERT INTO source (code, name, country, kind, base_url, licence, attribution,
                    has_history, history_from, retention_years, update_freq, commercial_ok, active)
VALUES
  ('de_bkms', 'Bekanntmachungsservice (Datenservice Oeffentlicher Einkauf)', 'DE', 'tender',
   'https://oeffentlichevergabe.de/api/notice-exports',
   'Not verified: open-data interface, licence text not found (see docs/sources/de_national.md)',
   'Quelle: Bekanntmachungsservice, Beschaffungsamt des BMI (oeffentlichevergabe.de)',
   TRUE, '2023-10-25', NULL, 'daily', NULL, FALSE)
ON CONFLICT (code) DO NOTHING;

-- A notice written for an inactive source is never served. The flag has two reasons now,
-- a takedown entry and an inactive source; either one holds it.
CREATE OR REPLACE FUNCTION dgate_opportunity_suppression() RETURNS trigger AS $$
BEGIN
    NEW.suppressed := EXISTS (
        SELECT 1 FROM suppression s JOIN source src ON src.code = s.source_code
         WHERE s.kind = 'notice' AND s.lifted_at IS NULL
           AND src.id = NEW.source_id AND s.native_id = NEW.native_id)
        OR EXISTS (SELECT 1 FROM source src WHERE src.id = NEW.source_id
                      AND NOT COALESCE(src.active, TRUE));
    NEW.buyer_withheld := NEW.buyer_org_id IS NOT NULL AND EXISTS (
        SELECT 1 FROM suppression s
         WHERE s.kind = 'organisation' AND s.lifted_at IS NULL
           AND s.organisation_id = NEW.buyer_org_id);
    RETURN NEW;
END
$$ LANGUAGE plpgsql;

-- Lifting a takedown entry must not release a row whose source is inactive.
CREATE OR REPLACE FUNCTION dgate_suppression_apply() RETURNS trigger AS $$
DECLARE
    on_ boolean := NEW.lifted_at IS NULL;
BEGIN
    IF NEW.kind = 'notice' THEN
        UPDATE opportunity o SET suppressed = on_ OR NOT COALESCE(s.active, TRUE)
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

-- Switching a source on or off re-evaluates its rows, in the same transaction. Naming
-- `native_id` in the SET list fires `opportunity_suppression`, which recomputes the flag.
CREATE OR REPLACE FUNCTION dgate_source_active_apply() RETURNS trigger AS $$
BEGIN
    UPDATE opportunity SET native_id = native_id WHERE source_id = NEW.id;
    RETURN NULL;
END
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS source_active_apply ON source;
CREATE TRIGGER source_active_apply AFTER UPDATE OF active ON source
    FOR EACH ROW WHEN (OLD.active IS DISTINCT FROM NEW.active)
    EXECUTE FUNCTION dgate_source_active_apply();
