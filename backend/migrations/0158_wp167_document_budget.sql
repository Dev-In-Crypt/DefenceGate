-- WP-167 (owner, 31 October 2026): the call document's own budget total, next to the portal's figure.
-- The portal states the voted EU budget (EUR 180 000 000 for EDF-EDIP-USI-2026-LS-IRA); the call document states the
-- "estimated available call budget" (EUR 184 500 000) and, in a footnote, how much of it comes from the voted EU budget.
-- `document_budget` = {"total": <EUR>, "voted": <EUR or null>, "url": <the call document>}, derived from the stored text of the
-- call document (`call_document_text`) by `dgate.ops.call_budgets` (nightly in the worker; report / --yes by hand). Not versioned:
-- derived data, replaceable. Additive and idempotent.
ALTER TABLE call ADD COLUMN IF NOT EXISTS document_budget JSONB;
