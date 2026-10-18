-- WP-40 (V2-B1, 18 October 2026): a readiness rule may be quoted from the Commission's call document.
--
-- Two EDIP calls name their applicants in the call document and not in the Official Journal: the calls for support to
-- SEAPs ("Only single applications by a SEAP are allowed") and for the preparation of projects of common interest ("be a
-- SEAP or a group of at least 4 EU Member States and EDIP associated countries"). Their rules (EDIP-SEAP-APPLICANT,
-- EDIP-PREP-APPLICANT) say so with the origin `call_document`, next to `primary` (checked against the Official Journal
-- text) and `notes` (quoted from the research notes). Additive and idempotent.
ALTER TABLE programme_requirement DROP CONSTRAINT IF EXISTS programme_requirement_text_origin_check;
ALTER TABLE programme_requirement
    ADD CONSTRAINT programme_requirement_text_origin_check CHECK (text_origin IN ('primary', 'notes', 'call_document'));
