-- PLACSP award winners (WP-60, 20 October 2026). Additive and idempotent; nothing is dropped or deleted.
--
--   award_notice.payload_hash        the hash of the (person-blanked) award payload the notice was last read
--                                    from. A PLACSP folder states its result again on every entry (ADJ, then
--                                    RES, sometimes a new winner after a renuncia), so a notice is read again
--                                    when this moves. TED notices are read once and leave it empty.
--   award_notice.payload_updated_at  the entry's own update stamp: an older entry never overwrites a newer read.
--   award.superseded_at              a winner a later read of the notice no longer names. `award` has DELETE
--                                    revoked, so a replaced winner is marked, not removed; the supplier map
--                                    reads only rows where this is empty.
--
-- The grants of 0079 are table grants and cover the new columns.

ALTER TABLE award_notice ADD COLUMN IF NOT EXISTS payload_hash TEXT;
ALTER TABLE award_notice ADD COLUMN IF NOT EXISTS payload_updated_at TIMESTAMPTZ;
ALTER TABLE award ADD COLUMN IF NOT EXISTS superseded_at TIMESTAMPTZ;

-- Where the PLACSP results are landed from: the same archives as `es_placsp`. It carries the raw records
-- and the run log only and is not a feed, so it stays inactive (as `ted_awards`). The licence is the
-- Ministerio de Hacienda aviso legal (docs/sources/es_placsp.md). Not served: DGATE_PLACSP_AWARDS_PUBLIC
-- keeps these winners out of the supplier map until the owner decides.
INSERT INTO source (code, name, country, kind, base_url, licence, attribution,
                    has_history, history_from, retention_years, update_freq, commercial_ok, active)
VALUES
  ('es_placsp_awards', 'PLACSP award results: winners', 'ES', 'tender',
   'https://contrataciondelsectorpublico.gob.es/sindicacion/sindicacion_643',
   'Ministerio de Hacienda aviso legal (Ley 37/2007): reuse for commercial and non-commercial purposes; '
   'cite the source and the date of last update; personal data under LO 3/2018',
   'Origen de los datos: Ministerio de Hacienda (Plataforma de Contratación del Sector Público)',
   TRUE, '2023-01-01', 10, 'on demand', TRUE, FALSE)
ON CONFLICT (code) DO NOTHING;
