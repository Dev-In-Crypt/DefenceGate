-- Spain: the national subsidies register (BDNS), as a source of grant calls.
--
-- A call register, not a defence programme: Spanish defence R&D cooperation is
-- contracted, not subsidised, and is not here. What is here is every subsidy call of
-- every administration, 52,744 registered in 2026 so far. Central government's 1,344
-- are collected, the few that a supplier could answer are kept as calls: the
-- Ministry of Defence's own, INTA's, and the CDTI's company R&D lines. See
-- docs/sources/es_bdns.md for the twelve discovery answers and the measurements.
--
-- The legal notice restricts reuse of personal data to control, transparency and
-- research. Calls name no persons; awards do and are never fetched. The full text of
-- the notice is rendered by script and could not be read by the connector's author:
-- `commercial_ok` is TRUE on the strength of the register describing its reusers as
-- "commercial or non-commercial", and the notice itself still has to be read by a
-- person before launch.

INSERT INTO programme (code, name, legal_basis) VALUES
  ('ES-BDNS', 'Spanish national subsidy calls (BDNS)', 'Ley 38/2003, General de Subvenciones')
ON CONFLICT (code) DO NOTHING;

INSERT INTO source (code, name, country, kind, base_url, licence, attribution,
                    has_history, history_from, retention_years, update_freq, commercial_ok)
VALUES
  ('es_bdns', 'Base de Datos Nacional de Subvenciones (BDNS)', 'ES', 'grant',
   'https://www.infosubvenciones.es/bdnstrans/GE/es',
   'Aviso legal of the Sistema Nacional de Publicidad de Subvenciones; public-sector information, personal data excluded',
   'Fuente: Base de Datos Nacional de Subvenciones (BDNS), Intervencion General de la Administracion del Estado, Ministerio de Hacienda',
   TRUE, '2016-01-01', NULL, 'daily', TRUE)
ON CONFLICT (code) DO NOTHING;
