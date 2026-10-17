-- Grants for the readiness tables (WP-29), after the pattern of 0057 and 0059: the API role
-- reads them, the worker role loads them (the seed is applied when the worker starts), and
-- the backup, which runs as the worker, can read every table
-- (test_the_worker_role_can_read_every_table_so_pg_dump_can).
GRANT SELECT ON requirement, requirement_prerequisite, requirement_issuer,
                readiness_programme, programme_requirement TO dgate_api;
GRANT SELECT, INSERT, UPDATE ON requirement, requirement_prerequisite, requirement_issuer,
                readiness_programme, programme_requirement TO dgate_worker;
GRANT USAGE, SELECT ON SEQUENCE requirement_id_seq, requirement_issuer_id_seq,
                programme_requirement_id_seq TO dgate_worker;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO dgate_worker;
