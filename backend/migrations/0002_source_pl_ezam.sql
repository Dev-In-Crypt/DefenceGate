-- Poland: Biuletyn Zamowien Publicznych, served by the e-Zamowienia platform.
--
-- Registered as its own source rather than folded into TED because this is the
-- national bulletin: it carries the below-threshold notices that never reach
-- TED, which is exactly the coverage a tier-2 supplier cannot get anywhere
-- else. Answers to the twelve discovery questions live in
-- docs/sources/ezamowienia.md.

INSERT INTO source (code, name, country, kind, base_url, licence, attribution,
                    has_history, history_from, retention_years, update_freq, commercial_ok)
VALUES
  ('pl_ezam', 'Biuletyn Zamowien Publicznych (e-Zamowienia)', 'PL', 'tender',
   'https://ezamowienia.gov.pl/mo-board/api/v1',
   'Open public sector information; the API regulations state the webservice is free and needs no access request',
   'Source: Biuletyn Zamowien Publicznych, Urzad Zamowien Publicznych, Poland',
   TRUE, '2021-01-01', NULL, 'daily', TRUE)
ON CONFLICT (code) DO NOTHING;
