-- France: the Agence de l'innovation de defense (AID), as a source of calls.
--
-- No API and no feed: the agency publishes each call as a page, under a list of those
-- open and a list of those closed, and states the closing date in the text. Everything
-- it lists is its own defence call -- ASTRID and ASMA research grants run through the
-- ANR, challenges, expressions of interest by the DGA's innovation poles, the Cyber
-- Defense Factory -- and RAPID, the dual-use grant scheme, is a standing call with no
-- deadline. See docs/sources/fr_aid.md.
--
-- Licence: the site's legal notice puts its contents under the Licence Ouverte 2.0
-- (Etalab), except third-party material, images and audiovisual resources, which are
-- not taken. Attribution is a condition of that licence.

INSERT INTO programme (code, name) VALUES
  ('FR-AID', 'Agence de l''innovation de defense (AID) calls for projects and RAPID')
ON CONFLICT (code) DO NOTHING;

INSERT INTO source (code, name, country, kind, base_url, licence, attribution,
                    has_history, history_from, retention_years, update_freq, commercial_ok)
VALUES
  ('fr_aid', 'Agence de l''innovation de defense (AID), appels a projets', 'FR', 'grant',
   'https://www.defense.gouv.fr/aid/appels-projets',
   'Licence Ouverte 2.0 (Etalab), per the legal notice of defense.gouv.fr; images and third-party material excluded',
   'Source : Agence de l''innovation de defense (AID), Ministere des Armees, Licence Ouverte 2.0',
   FALSE, NULL, NULL, 'daily', TRUE)
ON CONFLICT (code) DO NOTHING;
