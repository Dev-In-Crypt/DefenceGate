-- The Netherlands: TenderNed, the national procurement platform.
--
-- Its own source because what TED carries is above the European thresholds and
-- TenderNed also holds what is national-only (23 of 435 Defensie notices in
-- 2026). The defence directive is named by the form, so the legal-basis signal
-- comes from the source. Measured 10 October 2026; see docs/sources/nl_tenderned.md.
--
-- Licence: the dataset "Aankondigingen van overheidsopdrachten - TenderNed" is
-- listed on data.overheid.nl under CC0 1.0. The endpoint read here is the
-- portal's own, not the documented XML API (which needs credentials); that
-- difference is recorded in the source note and is the owner's to accept.

INSERT INTO source (code, name, country, kind, base_url, licence, attribution,
                    has_history, history_from, retention_years, update_freq, commercial_ok)
VALUES
  ('nl_tenderned', 'TenderNed', 'NL', 'tender',
   'https://www.tenderned.nl/papi/tenderned-rs-tns/v2/publicaties',
   'CC0 1.0 (dataset listing on data.overheid.nl)',
   'Bron: TenderNed (PIANOo), Nederland',
   TRUE, '2012-01-01', NULL, 'daily', TRUE)
ON CONFLICT (code) DO NOTHING;
