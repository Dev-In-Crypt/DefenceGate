-- WP-132 (round-7 funding audit, 25 October 2026). Additive and idempotent.
--
-- 1. `unlisted_runs`: how many complete, successful nightly runs of the call's source in a row did not list the call (the EU portal's
--    snapshot of open, forthcoming and this year's closed topics). Reset to 0 whenever the source lists it again (db.upsert_call).
--    A call the source last called open or forthcoming that it has stopped listing for funding.UNLISTED_AFTER_RUNS runs is served as
--    `unlisted` (funding.EFFECTIVE_STATUS): out of the open lists, the counts, the calendar and Fits my profile; the row is kept.
--    The calls already held are counted from the run history by `python -m dgate.ops.wp132_funding --yes`.
ALTER TABLE call ADD COLUMN IF NOT EXISTS unlisted_runs smallint NOT NULL DEFAULT 0;

-- 2. `consortium_rule`: the "Minimum consortium" row of the call, built from the call's verified eligibility facts (min_entities,
--    min_countries, single_applicant_allowed) with the place they were read (who_apply.consortium_of); NULL where those facts say
--    nothing, and the row then comes from the topic's own conditions (`min_consortium_size`, `min_member_states`).
ALTER TABLE call ADD COLUMN IF NOT EXISTS consortium_rule text;
