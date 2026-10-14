-- Owner decision of 14 October 2026 (verification round 2, data-correctness:B4): two groups
-- of defence-qualified notice leave scope `core` for `supply`, never deleted:
--   directive_civil_buyer  the 2009/81/EC legal basis is the only defence signal and the
--                          buyer is a civil body;
--   security_buyer_cpv     a military CPV is the only signal and the buyer is a police,
--                          prison, border, customs or tax body.
-- Both are derived from columns the notice already carries (dgate/classify.py CORE_SQL), so
-- no column is added and no row is written: the scope moves with the code.
--
-- What this adds is the partial index the market overview counts through, rebuilt for the
-- new predicate. `opp_core_published` (migration 0038) keeps its old predicate and stops
-- being used by those queries; it is listed in docs/DELETION_CANDIDATES.md and not dropped.
-- Additive; writes nothing; a second run does nothing.
CREATE INDEX IF NOT EXISTS opp_core_published_v2
    ON opportunity (published_at)
    INCLUDE (source_id, country, deadline_at)
    WHERE is_defence AND (
        (sig_legal_basis AND NOT (
            sig_legal_basis AND NOT sig_cpv_military AND NOT sig_buyer
            AND NOT sig_linked_defence AND buyer_class IS NOT NULL
            AND buyer_class NOT IN ('defence', 'security')))
        OR (sig_cpv_military AND NOT dual_use AND NOT (
            sig_cpv_military AND NOT sig_legal_basis AND NOT dual_use AND NOT sig_buyer
            AND NOT sig_linked_defence AND buyer_class IS NOT DISTINCT FROM 'security')));
