-- The twin pairs of `award_twin` (migration 0093), stored (WP-75, 22 October 2026). Additive and idempotent:
-- a table, its grants and its first fill; nothing dropped, the view stays the definition.
--
-- Why: the view is a self-join of every current award (two copies of each procedure's rows, and a twin-link
-- join with an OR), recomputed by every statement that reads it. Measured on production on 22 October 2026
-- (34,306 PLACSP + 9,826 TED live awards): `SELECT count(*) FROM award_twin` 5.0 s for 1,105 pairs, and the
-- supplier map reads it in every query with DGATE_PLACSP_AWARDS_PUBLIC on: /v1/suppliers 5.19 s, over the
-- API's 5 s budget. Against this table the same statements take 0.2 to 0.5 s.
--
-- Derived and replaceable, like `organisation_network`: `awards.refresh_award_twins()` rewrites it from the
-- view in one transaction (a reader sees the old pairs or the new ones) after every award load (TED winners,
-- the PLACSP walk and archive replay), after the daily twin links (`ops/link_twins`) and every four hours with
-- the list snapshots (`ops/warm_lists`), which covers organisation merges. The map still checks the preferred
-- row of each pair live (suppression, scope, natural persons), so only the pairing itself can be up to four
-- hours behind a merge.

CREATE TABLE IF NOT EXISTS award_twin_set (
    award_id          BIGINT NOT NULL,     -- the second copy of a logical award: left out of the map
    preferred_id      BIGINT NOT NULL,     -- the row that stands for it
    procedure_method  TEXT NOT NULL,       -- procedure_id | ted_ref
    winner_method     TEXT NOT NULL,       -- organisation | identifier
    PRIMARY KEY (award_id, preferred_id)
);
CREATE INDEX IF NOT EXISTS award_twin_set_preferred ON award_twin_set (preferred_id);

INSERT INTO award_twin_set (award_id, preferred_id, procedure_method, winner_method)
SELECT award_id, preferred_id, procedure_method, winner_method FROM award_twin
ON CONFLICT DO NOTHING;

GRANT SELECT ON award_twin_set TO dgate_api;
GRANT SELECT, INSERT, DELETE ON award_twin_set TO dgate_worker;
