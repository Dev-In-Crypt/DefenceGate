-- Whose budget the number on a call is.
--
-- The portal repeats one amount across sibling topics when they compete for a
-- single pot. Measured on 24 September 2026: all eleven topics of the 2026 EDF
-- development call carry 422,000,000, which is the call's budget and not any
-- topic's -- and the first version of this table served it as the topic's, which
-- would have told a supplier there was EUR 422 million behind the one topic it
-- was reading.
--
-- The amount is kept, because it is the only figure the portal gives and it is
-- useful once it is labelled. `budget_scope` is that label: 'topic' when the
-- figure is stated for this topic alone, 'call' when it is the pot the topic
-- competes in. Null means no figure was published.

ALTER TABLE call ADD COLUMN budget_scope TEXT;
