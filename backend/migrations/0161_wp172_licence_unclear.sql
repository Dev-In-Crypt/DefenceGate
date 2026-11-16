-- WP-172 (owner, 16 November 2026): the licence reading of WP-171 found the commercial reuse of four sources unclear, so
-- their flag says so. NULL is "unclear": every reader serves a source's own words only where the flag is TRUE (api.get_call,
-- funding.to_call / get_funding, partners.facts_of), so the AID page lead stops being served as the call's summary; the
-- other three already had no text served (not on funding.SOURCE_TEXT_SOURCES). Facts (titles, dates, sums, links) are
-- served as before, and the licence and attribution texts stay as they are. Setting a flag back to TRUE serves the text again.
--   pl_ezam   no licence; the regulamin says only that use is free (Open Data Act art. 39 question open)
--   pl_atlas  CC BY 4.0, but built from e-Zamowienia: inherits its question
--   fr_aid    defense.gouv.fr: Licence Ouverte in the footer, "réutilisation non commerciale" on the reuse page
--   pl_ncbr   gov.pl texts CC BY-SA 4.0; whether share-alike reaches the structured data is open
UPDATE source SET commercial_ok = NULL WHERE code IN ('pl_ezam', 'pl_atlas', 'fr_aid', 'pl_ncbr');

COMMENT ON COLUMN source.commercial_ok IS
    'Commercial reuse of the source''s own words: TRUE allowed, FALSE not, NULL unclear. Only TRUE serves text (WP-71, WP-172).';
