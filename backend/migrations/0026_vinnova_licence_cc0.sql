-- Vinnova's open-data page now states the data is free to use as CC0; the Public Domain
-- Mark wording came from a 2017 API document. The register and the attribution line shown
-- with each record follow the publisher's current statement (checked 12 October 2026).
UPDATE source
   SET licence = 'CC0 (Vinnova open data: free use without fees or other restrictions)',
       attribution = 'Källa: Vinnova, öppna data (CC0)'
 WHERE code = 'se_vinnova';
