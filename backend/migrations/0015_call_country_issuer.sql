-- National grants: whose money it is.
--
-- A call under an EU programme is open to every member state and needs neither.
-- A call from a national body does: a Spanish CDTI line is a different proposition
-- to a Swedish supplier than to a Spanish one, and "which ministry or agency" is
-- the first thing a reader asks about a call whose title is a legal citation.
--
-- `country` is ISO 3166-1 alpha-2 of the body that issues the call (not of who may
-- apply). `issuer` is that body, as the source names it.

ALTER TABLE call ADD COLUMN country CHAR(2);
ALTER TABLE call ADD COLUMN issuer  TEXT;

CREATE INDEX call_country ON call (country) WHERE country IS NOT NULL;
