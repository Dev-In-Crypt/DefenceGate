-- WP-74 (21 October 2026): two more states of a merge candidate. Additive and idempotent.
--
--   undone                 a merge `ops/undo_merges` reversed; the row is the audit record that
--                          `db.merge_organisations` wrote for the merge, kept, and never proposed again
--   rejected_public_units  a pair proved by a shared tax id where one side is a public authority or a
--                          unit of one (`ops/accept_merge_candidates`, rule `public_body`): one legal
--                          entity, but different buyers; shown as one buyer family instead
--                          (`ops/buyer_families`, rule `shared_tax_id`), never merged

ALTER TABLE organisation_merge_candidate
    DROP CONSTRAINT IF EXISTS organisation_merge_candidate_status_check;
ALTER TABLE organisation_merge_candidate
    ADD CONSTRAINT organisation_merge_candidate_status_check
    CHECK (status IN ('pending', 'merged', 'rejected', 'undone', 'rejected_public_units'));
