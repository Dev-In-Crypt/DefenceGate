-- Two things the register's legal notice (read in full on 11 October 2026,
-- docs/sources/es_bdns.md) asks for.
--
-- 1. Cite the source in the form the notice suggests: "Origen de los datos:
--    Intervencion General de la Administracion del Estado".
-- 2. Show the register's own date for a call, where the record carries one. BDNS
--    states the day it received the call (fechaRecepcion); there is no
--    "last modified" field, so none is shown. A column of its own, because
--    first_seen_at is when this project saw the call, not when the source dated it.

ALTER TABLE call ADD COLUMN IF NOT EXISTS published_at DATE;

UPDATE source
   SET attribution = 'Origen de los datos: Intervención General de la Administración del Estado (Base de Datos Nacional de Subvenciones, Ministerio de Hacienda)'
 WHERE code = 'es_bdns';
