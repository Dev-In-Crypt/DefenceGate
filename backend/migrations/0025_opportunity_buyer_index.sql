-- The tenders and buyers pages look an organisation's notices up by buyer_org_id
-- (its commonest spelling, its counts). Without an index each of those was a scan of
-- the whole table; the serving layer asks for a page of buyers at a time.
CREATE INDEX IF NOT EXISTS opp_buyer_org
    ON opportunity (buyer_org_id) WHERE is_defence;
