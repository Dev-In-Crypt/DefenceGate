-- WP-72 (21 October 2026): the tenders list of one country and of one buyer, in each of the three
-- orders a list runs in (dgate/tenders.py ORDER_*), over the rows a list can show.
--
-- The QA audit of the production database (docs/verification/product/qa-full-database.md, section 14)
-- found the country lists (Malta: 165 defence rows) and the buyer pages walking the whole
-- `opp_list_published` / `opp_list_deadline_*` index (about 290,000 entries) and filtering by country
-- or buyer: EXPLAIN cost to 157,000-180,000 per page. With the country or buyer as the leading column
-- the walk is the matching rows only, already in the list's order, and stops after the page.
-- tenders._tender_filters writes one country and a one-row buyer family as a plain `=` so the planner
-- can use the order (an `= ANY(...)` gives no ordered path).
--
-- About 14 MB each on production (the existing list indexes are 12-16 MB). Additive and idempotent.
-- On production the orchestrator creates them CONCURRENTLY first (no write lock on `opportunity`
-- while a load runs); IF NOT EXISTS then makes this file a no-op there:
--   CREATE INDEX CONCURRENTLY IF NOT EXISTS opp_list_country_published ON opportunity (country, (coalesce(published_at, notice_date)) DESC NULLS LAST, id DESC) WHERE is_defence AND NOT suppressed;
--   (and the five below, the same way)

CREATE INDEX IF NOT EXISTS opp_list_country_published
    ON opportunity (country, (coalesce(published_at, notice_date)) DESC NULLS LAST, id DESC)
    WHERE is_defence AND NOT suppressed;

CREATE INDEX IF NOT EXISTS opp_list_country_deadline_asc
    ON opportunity (country, deadline_at ASC NULLS LAST, id ASC)
    WHERE is_defence AND NOT suppressed;

CREATE INDEX IF NOT EXISTS opp_list_country_deadline_desc
    ON opportunity (country, deadline_at DESC NULLS LAST, published_at DESC NULLS LAST, id DESC)
    WHERE is_defence AND NOT suppressed;

CREATE INDEX IF NOT EXISTS opp_list_buyer_published
    ON opportunity (buyer_org_id, (coalesce(published_at, notice_date)) DESC NULLS LAST, id DESC)
    WHERE is_defence AND NOT suppressed;

CREATE INDEX IF NOT EXISTS opp_list_buyer_deadline_asc
    ON opportunity (buyer_org_id, deadline_at ASC NULLS LAST, id ASC)
    WHERE is_defence AND NOT suppressed;

CREATE INDEX IF NOT EXISTS opp_list_buyer_deadline_desc
    ON opportunity (buyer_org_id, deadline_at DESC NULLS LAST, published_at DESC NULLS LAST, id DESC)
    WHERE is_defence AND NOT suppressed;

ANALYZE opportunity;
