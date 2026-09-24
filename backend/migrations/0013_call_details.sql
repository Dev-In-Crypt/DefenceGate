-- The detail document of a topic, folded into the call it describes.
--
-- The calendar says a call exists; the topic page says whether it is worth
-- applying to -- the budget, the conditions, and for the programmes that state
-- it in words, how many members the consortium needs and from how many
-- countries. It is a separate document per topic and a separate fetch, so it
-- gets its own hash: a call whose calendar entry is unchanged can still have
-- its budget corrected, and `details_seen_at` is how the refresh knows which
-- ones it has looked at recently.

ALTER TABLE call ADD COLUMN details_hash    TEXT;
ALTER TABLE call ADD COLUMN details_seen_at TIMESTAMPTZ;

-- The refresh reads this: no details yet, or details older than the window.
CREATE INDEX call_details_seen ON call (details_seen_at NULLS FIRST);
