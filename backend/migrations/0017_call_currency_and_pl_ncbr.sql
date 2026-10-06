-- Currency on a call's budget, and Poland's NCBR as a source of grant calls.
--
-- Until now every budget was in euro: the EU portal and Spain's register both state
-- euro. NCBR's competitions state zloty or euro, in prose ("350 000 000 zl", "1 950 000
-- euro"), and a sum without its currency is not a sum. The existing budgets are
-- labelled euro, which is what they were; nothing is converted, because a rate is a
-- judgement the product should not make for its reader.

ALTER TABLE call ADD COLUMN currency CHAR(3);
UPDATE call SET currency = 'EUR' WHERE budget IS NOT NULL;

-- Poland. A competitions register with a JSON API behind the page: 364 competitions,
-- of which a few carry the publisher's own defence tags. See docs/sources/pl_ncbr.md.
--
-- NCBR's reuse policy allows commercial reuse with attribution, and the text of the
-- site is CC BY-SA 4.0. Descriptions are therefore kept in the raw archive and not
-- served; the product carries the facts and a link.

INSERT INTO programme (code, name, legal_basis) VALUES
  ('PL-NCBR', 'Polish National Centre for Research and Development (NCBR) competitions',
   'Ustawa o Narodowym Centrum Badan i Rozwoju (2007)')
ON CONFLICT (code) DO NOTHING;

INSERT INTO source (code, name, country, kind, base_url, licence, attribution,
                    has_history, history_from, retention_years, update_freq, commercial_ok)
VALUES
  ('pl_ncbr', 'Narodowe Centrum Badan i Rozwoju (NCBR), competitions', 'PL', 'grant',
   'https://www.gov.pl/web/ncbr/platforma-konkursowa',
   'NCBR public-sector information reuse policy: commercial reuse allowed, attribution required; site text CC BY-SA 4.0',
   'Zrodlo: Narodowe Centrum Badan i Rozwoju (NCBR), gov.pl',
   TRUE, '2019-01-01', NULL, 'daily', TRUE)
ON CONFLICT (code) DO NOTHING;
