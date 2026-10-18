-- WP-33 (D10): an issuer that is the state itself (Spain's PECAL route, the Bundeswehr) is not a
-- commercial body, so the vendor price ranges of the research notes must not be shown for it.
-- Additive and idempotent; the seed (dgate.readiness.seed) fills it. Existing grants cover the column.
ALTER TABLE requirement_issuer ADD COLUMN IF NOT EXISTS state_route BOOLEAN NOT NULL DEFAULT FALSE;
