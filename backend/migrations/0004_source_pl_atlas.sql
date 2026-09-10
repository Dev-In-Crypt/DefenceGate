-- Poland, historical: the Atlas Przetargow open dataset.
--
-- Registered as its own source rather than folded into pl_ezam because the two
-- differ in what they can prove. The live bulletin connector sees what is being
-- served now; this is a bulk archive of what was published before we started
-- collecting, and it is the part of the record a competitor starting after us
-- cannot obtain at any price.
--
-- The attribution string is not decoration. The dataset is CC BY 4.0, which
-- makes attribution a licence condition, and putting it on the source row means
-- it travels with the data rather than living in a comment somebody deletes.
--
-- has_history is TRUE from 2024-01-01: the 2026.Q2 release covers 2024 and 2025
-- only, verified against the record's file list rather than its README, which
-- says "2024 - present" without saying where present ends.

INSERT INTO source (code, name, country, kind, base_url, licence, attribution,
                    has_history, history_from, retention_years, update_freq, commercial_ok)
VALUES
  ('pl_atlas', 'Polish Public Tenders Dataset (Atlas Przetargow)', 'PL', 'tender',
   'https://zenodo.org/records/19634050',
   'CC BY 4.0 (Creative Commons Attribution 4.0 International)',
   'Atlas Przetargow (2026). Polish Public Tenders Dataset (BZP + TED), version 2026.Q2. DOI 10.5281/zenodo.19634050. Licensed CC BY 4.0.',
   TRUE, '2024-01-01', NULL, 'one-off', TRUE)
ON CONFLICT (code) DO NOTHING;
