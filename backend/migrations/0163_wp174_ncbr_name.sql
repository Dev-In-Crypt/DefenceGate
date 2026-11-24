-- WP-174 (full QA of 24 November 2026, A-3): the Polish name of the National Centre for Research and Development with its
-- diacritics. "Narodowe Centrum Badan" stood in the funding feed's summaries, the calendar and the attribution line.
-- Reference text only: the source row, the programme's legal basis and the issuer the NCBR connector writes on its calls
-- (a living row, `db.upsert_call`; the connector writes the same name from now on, `normalise.from_ncbr`).
UPDATE source
   SET name = 'Narodowe Centrum Badań i Rozwoju (NCBR), competitions',
       attribution = 'Źródło: Narodowe Centrum Badań i Rozwoju (NCBR), gov.pl'
 WHERE code = 'pl_ncbr';

UPDATE programme
   SET legal_basis = 'Ustawa o Narodowym Centrum Badań i Rozwoju (2007)'
 WHERE code = 'PL-NCBR' AND legal_basis = 'Ustawa o Narodowym Centrum Badan i Rozwoju (2007)';

UPDATE call
   SET issuer = 'Narodowe Centrum Badań i Rozwoju (NCBR)'
 WHERE issuer = 'Narodowe Centrum Badan i Rozwoju (NCBR)';
