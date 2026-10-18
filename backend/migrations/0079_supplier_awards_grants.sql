-- Grants and the source row for the supplier map (WP-37), after the pattern of 0060/0065.
-- The API role reads; the worker role loads and, being the backup role, can read everything
-- (test_the_worker_role_can_read_every_table_so_pg_dump_can). Rows are never deleted.
GRANT SELECT ON award, award_notice TO dgate_api;
GRANT SELECT, INSERT, UPDATE ON award, award_notice TO dgate_worker;
REVOKE DELETE ON award, award_notice FROM dgate_worker;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO dgate_worker;

-- Where the winners are read from: the same TED search API, asked by publication number. The source
-- only carries the raw records and the run log; it is not a feed, so it stays INACTIVE for good and
-- `/v1/health` (which lists the active sources) does not call it stale.
INSERT INTO source (code, name, country, kind, base_url, licence, attribution,
                    has_history, history_from, retention_years, update_freq, commercial_ok, active)
VALUES
  ('ted_awards', 'TED result notices: winners', NULL, 'tender',
   'https://api.ted.europa.eu',
   'Commission Decision 2011/833/EU; notices freely reusable incl. commercial',
   'Source: TED (Tenders Electronic Daily), © European Union',
   TRUE, '2023-01-01', 10, 'on demand', TRUE, FALSE)
ON CONFLICT (code) DO NOTHING;
