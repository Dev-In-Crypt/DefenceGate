-- WP-114, HELD BACK FOR THE OWNER (rule: nothing is deleted without approval). Apply only after the owner says yes; until
-- then the orchestrator keeps this file out of the deploy. It drops three indexes no query reads (about 100 MB of disk and
-- of the write cost of every load). Evidence (production, 24 October 2026; statistics since the 22 October restart):
--
--   index               table               size    idx_scan  readers in the code (backend/dgate, grep)
--   alias_norm_trgm     organisation_alias  56 MB   0         none: aliases are looked up by equality (db.py 615,
--                                                             resolution/cascade.py 197, api.py 807), served by the
--                                                             unique btree of migration 0005; the trigram search reads
--                                                             organisation.canonical_name (db.py 563)
--   opp_search          opportunity         38 MB   0         none: nothing reads search_tsv since the folded-title and
--                                                             opportunity_search indexes (migrations 0054, 0113)
--   opp_core_published  opportunity         5.9 MB  0         superseded by opp_core_published_v2 (migration 0045);
--                                                             already in docs/DELETION_CANDIDATES.md
--
-- NOT dropped: raw_plain_key (451 MB, idx_scan 0 since the restart). ops/compact_raw.py reads it on every batch
-- (`storage_key NOT LIKE '%#%' AND storage_key = ANY(...)`, lines 181 and 247, the index's own predicate); the
-- compaction has not run since the restart, which is why the counter is 0. Without it a compaction batch would read the
-- 3.2 GB table sequentially.
--
-- Recreating any of them is its CREATE INDEX statement in the migration named above.
DROP INDEX IF EXISTS alias_norm_trgm;
DROP INDEX IF EXISTS opp_search;
DROP INDEX IF EXISTS opp_core_published;
