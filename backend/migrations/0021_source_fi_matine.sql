-- Finland: MATINE, the Ministry of Defence's scientific advisory board, as a source of
-- grant calls.
--
-- One research funding call a year, published as a page on the ministry's site and named
-- for the year it funds (`maararahahaku-2027` closed on 11 June 2026, for up to
-- EUR 1,850,000 across 10 to 20 projects). It is the Finnish ministry's own grant and the
-- only defence call in the country with a date and a sum on a page. See
-- docs/sources/fi_matine.md.
--
-- Licence: none is stated on defmin.fi, so `commercial_ok` is NULL, which is "unknown",
-- and only facts -- title, dates, sum -- and a link are taken; the Finnish text is not
-- served. Not a claim that the facts are free to reuse; a statement that nothing more than
-- facts is used.

INSERT INTO programme (code, name) VALUES
  ('FI-MATINE', 'Finnish Ministry of Defence research funding (MATINE)')
ON CONFLICT (code) DO NOTHING;

INSERT INTO source (code, name, country, kind, base_url, licence, attribution,
                    has_history, history_from, retention_years, update_freq, commercial_ok)
VALUES
  ('fi_matine', 'MATINE research funding call (Puolustusministerio)', 'FI', 'grant',
   'https://defmin.fi/matine-maanpuolustuksen-tieteellinen-neuvottelukunta',
   'No licence stated on defmin.fi; facts only (title, dates, sum) and a link are used',
   'Lähde: Puolustusministeriö, MATINE (Maanpuolustuksen tieteellinen neuvottelukunta)',
   FALSE, NULL, NULL, 'daily', NULL)
ON CONFLICT (code) DO NOTHING;
