-- WP-99 (persona round of 23 October 2026, D): a call open only to designated bodies (the ECCC topics for National Cyber Hubs and the
-- Cross-Border Cyber Hubs) is neither "Companies can take part" nor "Public buyers only": `who_may_apply_doc` may be 'designated'
-- (dgate/who_apply.py, from the call's `designated_applicants` fact without a consortium route). The list filter `who` keeps its two
-- values, so such a call is in neither, as a call nothing we hold speaks for.
ALTER TABLE call DROP CONSTRAINT IF EXISTS call_who_may_apply_doc_check;
ALTER TABLE call ADD CONSTRAINT call_who_may_apply_doc_check
    CHECK (who_may_apply_doc IN ('public', 'companies', 'designated'));
