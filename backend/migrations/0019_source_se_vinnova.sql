-- Sweden: Vinnova, the innovation agency, as a source of grant calls.
--
-- A register of every programme, call and application round the agency has run, with
-- an open API and no key. Most of it is civil innovation; two programmes are the
-- publisher's own defence ones -- the civil-military synergies programme, run with the
-- Armed Forces, and the civil defence programme -- and those are what is kept. See
-- docs/sources/se_vinnova.md.
--
-- Licence: the agency's open-data page states that the data may be used freely without
-- fees or other restrictions (Public Domain Mark). Contact persons are in the data and
-- are removed before anything is stored.

INSERT INTO programme (code, name) VALUES
  ('SE-VINNOVA', 'Vinnova calls in the civil-military and civil defence programmes')
ON CONFLICT (code) DO NOTHING;

INSERT INTO source (code, name, country, kind, base_url, licence, attribution,
                    has_history, history_from, retention_years, update_freq, commercial_ok)
VALUES
  ('se_vinnova', 'Vinnova open data: programmes, calls and application rounds', 'SE', 'grant',
   'https://data.vinnova.se/api',
   'Public Domain Mark (Vinnova open data)',
   'Källa: Vinnova, öppna data (Public Domain Mark)',
   TRUE, '2009-01-01', NULL, 'daily', TRUE)
ON CONFLICT (code) DO NOTHING;
