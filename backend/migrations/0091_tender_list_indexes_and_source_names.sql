-- WP-52 (19 October 2026): the tenders list and the source names.
--
-- 1. Indexes in the three orders the list runs in (dgate/tenders.py ORDER_*), over the rows a list
--    can show (`is_defence AND NOT suppressed`), so that a page of any depth is a walk that stops after
--    `offset + limit` matching rows instead of a sort of 287,634. Before this the Closed list answered
--    pages 1 to 3 (from a snapshot) and returned 503 from page 4 (UX audit T3).
--    `opp_open_candidates` is the open set: 2,600 of 357,000 rows, found by index whatever else the
--    search names (a search word such as Bundeswehr matches 19,000 rows and timed out: T2).
-- 2. The names of the sources as their operators spell them (accents kept), 7 names and 8 attribution
--    lines that had lost them (UX audit T18). Display text only; the codes, which everything joins on,
--    are untouched.
-- Additive and idempotent.

CREATE INDEX IF NOT EXISTS opp_list_deadline_asc
    ON opportunity (deadline_at ASC NULLS LAST, id ASC)
    WHERE is_defence AND NOT suppressed;

CREATE INDEX IF NOT EXISTS opp_list_deadline_desc
    ON opportunity (deadline_at DESC NULLS LAST, published_at DESC NULLS LAST, id DESC)
    WHERE is_defence AND NOT suppressed;

CREATE INDEX IF NOT EXISTS opp_list_published
    ON opportunity ((coalesce(published_at, notice_date)) DESC NULLS LAST, id DESC)
    WHERE is_defence AND NOT suppressed;

CREATE INDEX IF NOT EXISTS opp_open_candidates
    ON opportunity (deadline_at)
    WHERE status = 'open' AND is_defence AND NOT suppressed;

UPDATE source SET
    name = 'Plataforma de Contratación del Sector Público',
    attribution = 'Source: Plataforma de Contratación del Sector Público, Ministerio de Hacienda'
 WHERE code = 'es_placsp';

UPDATE source SET
    attribution = 'Source: Plataforma de Contratación del Sector Público, Ministerio de Hacienda'
 WHERE code = 'es_placsp_agg';

UPDATE source SET
    name = 'Biuletyn Zamówień Publicznych (e-Zamówienia)',
    attribution = 'Source: Biuletyn Zamówień Publicznych, Urząd Zamówień Publicznych, Poland'
 WHERE code = 'pl_ezam';

UPDATE source SET name = 'Polish Public Tenders Dataset (Atlas Przetargów)'
 WHERE code = 'pl_atlas';

UPDATE source SET
    name = 'Bulletin officiel des annonces de marchés publics (BOAMP)',
    attribution = 'Source: BOAMP, Direction de l''information légale et administrative (DILA), France, Licence Ouverte'
 WHERE code = 'fr_boamp';

UPDATE source SET
    name = 'Narodowe Centrum Badań i Rozwoju (NCBR), competitions',
    attribution = 'Źródło: Narodowe Centrum Badań i Rozwoju (NCBR), gov.pl'
 WHERE code = 'pl_ncbr';

UPDATE source SET
    name = 'Agence de l''innovation de défense (AID), appels à projets',
    attribution = 'Source : Agence de l''innovation de défense (AID), Ministère des Armées, Licence Ouverte 2.0'
 WHERE code = 'fr_aid';

UPDATE source SET name = 'Bekanntmachungsservice (Datenservice Öffentlicher Einkauf)'
 WHERE code = 'de_bkms';

-- The statistics of the expression index (coalesce(published_at, notice_date)) exist only after an ANALYZE.
ANALYZE opportunity;
