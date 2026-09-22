-- France: Bulletin officiel des annonces de marches publics (BOAMP), served by
-- DILA through the OpenDataSoft platform.
--
-- Its own source for the same reason as Poland's bulletin: what TED carries is
-- above the European thresholds, and the contracts a twenty-person
-- manufacturer wins outright are below them. BOAMP holds 1,708,130 notices
-- from 2 March 2015 onwards, and states the procurement regime in a column --
-- 4,650 of them under Directive 2009/81/EC. Answers to the twelve discovery
-- questions live in docs/sources/boamp.md.

INSERT INTO source (code, name, country, kind, base_url, licence, attribution,
                    has_history, history_from, retention_years, update_freq, commercial_ok)
VALUES
  ('fr_boamp', 'Bulletin officiel des annonces de marches publics (BOAMP)', 'FR', 'tender',
   'https://boamp-datadila.opendatasoft.com/api/explore/v2.1/catalog/datasets/boamp',
   'Licence Ouverte / Open Licence (Etalab)',
   'Source: BOAMP, Direction de l''information legale et administrative (DILA), France, Licence Ouverte',
   TRUE, '2015-03-02', NULL, 'daily', TRUE)
ON CONFLICT (code) DO NOTHING;
