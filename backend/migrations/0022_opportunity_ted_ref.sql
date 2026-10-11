-- The TED publication number a national notice was forwarded under.
--
-- A notice above the EU thresholds is published nationally and again in the
-- Official Journal, and several portals say so in the record itself (TenderNed's
-- pbNummerTed, the Polish bulletin's link to ted.europa.eu, the Atlas dataset's
-- ted_number). Measured on 11 October 2026, 434 of 463 Dutch and 531 of 1,699
-- Polish defence notices point at a TED notice this database holds.
--
-- The link is stored on the national row and joined to ted.native_id when
-- served. It is not a version-worthy fact, so it is not in VERSIONED_FIELDS and
-- no row is archived for it.
ALTER TABLE opportunity ADD COLUMN IF NOT EXISTS ted_ref TEXT;

CREATE INDEX IF NOT EXISTS opp_ted_ref ON opportunity (ted_ref) WHERE ted_ref IS NOT NULL;
