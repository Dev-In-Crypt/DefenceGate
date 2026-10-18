-- WP-41 (18 October 2026): the networks data fixes found by the second verification (verify2-networks.md).
-- Additive and idempotent. Nothing is dropped, nothing in an entity or archive table is deleted.
--
-- 1. What a contribution means (N1, N2, N3).
--    `participation.contribution` is the EU funding that CORDIS's open data pays to the participant (the grant
--    payment of its role), in EUR. It is not the "net EU contribution" the CORDIS web page prints, which deducts
--    what the participant passes on to its linked third parties (the open data does not say which third party is
--    linked to which beneficiary, and shows every third party at 0).
--      NULL   the amount is unknown. `contribution_note` says why:
--               no_payment_stated      the service holds no payment for this role (grants not yet in it)
--               linked_third_party     a third party, shown at 0 by the service: its share is inside the payment
--                                      of the participant it is linked to
--               exceeds_project_total  the amounts of the project add up to more than its EU contribution, so none
--                                      can be trusted; the figure as the service stated it is in contribution_stated
--               source_states_none     EDF factsheets state no amount per participant
--      number the amount as stated. With the note `gross_of_third_parties` the project has third parties, so the
--             amount may include their share. 0 is a stated 0 (an associated partner is not funded).
--    A note is a code, not text; the list is closed.
ALTER TABLE participation ADD COLUMN IF NOT EXISTS contribution_note   TEXT;
ALTER TABLE participation ADD COLUMN IF NOT EXISTS contribution_stated NUMERIC(14,2);

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'participation_contribution_note_check') THEN
        ALTER TABLE participation ADD CONSTRAINT participation_contribution_note_check
            CHECK (contribution_note IS NULL OR contribution_note IN
                   ('no_payment_stated', 'linked_third_party', 'exceeds_project_total',
                    'source_states_none', 'gross_of_third_parties'));
    END IF;
END $$;

COMMENT ON COLUMN participation.contribution IS
    'EUR the open data of CORDIS pays to this participant (gross of its linked third parties). NULL = unknown, see contribution_note. 0 = stated as 0.';
COMMENT ON COLUMN participation.contribution_note IS
    'NULL, or why contribution is NULL (no_payment_stated, linked_third_party, exceeds_project_total, source_states_none), or a caveat on a stated amount (gross_of_third_parties).';
COMMENT ON COLUMN participation.contribution_stated IS
    'The amount as the source stated it, kept when contribution was withheld (note exceeds_project_total); otherwise NULL.';

-- 2. The country of an organisation with contradicting records (N4).
--    CORDIS gives the address country of each site; it also puts the country in the site's name and states a VAT
--    number. When a name and a VAT number agree against the address, the organisation's country follows them
--    (country_basis 'vote'); when the record has sites in several countries and nothing decides, the first is
--    kept and the list is stored (country_basis 'several'). NULL: the country is the address country, nothing
--    contradicts it. country_sites lists every country the record gave, when country_basis is not NULL.
ALTER TABLE organisation ADD COLUMN IF NOT EXISTS country_basis TEXT;
ALTER TABLE organisation ADD COLUMN IF NOT EXISTS country_sites CHAR(2)[];
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'organisation_country_basis_check') THEN
        ALTER TABLE organisation ADD CONSTRAINT organisation_country_basis_check
            CHECK (country_basis IS NULL OR country_basis IN ('vote', 'several'));
    END IF;
END $$;
COMMENT ON COLUMN organisation.country_basis IS
    'NULL = the address country of the source; vote = name and VAT number of the record overrule its address; several = sites in several countries, country is the first, see country_sites.';
COMMENT ON COLUMN organisation.country_sites IS
    'Every country the source record gave (address, site name, VAT), when country_basis is not NULL.';
