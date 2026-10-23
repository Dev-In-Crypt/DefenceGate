# WP-94 self-check: Spanish natural persons vs companies in the supplier cleaner (23 October 2026)

Branch `wp-wp94` from `integration` (a7ae02d). No deploy, no push, no production read or write.

## Problem

Persons loaded before the ES person rule have supplier pages ("GABRIELA GARCIA CARRASCAL", "JUAN JOSE FERNANDEZ BALONGO",
"JOSE ANTONIO GARCIA VERA": country ES, no stated number). The dry run of `python -m dgate.ops.clean_suppliers` on production
marked 1,711 rows (518 distinct names) as `person_name`, most of them companies ("DISA GAS S.A.U", "HIERROS BUENO SAL",
"Mazars Auditores, S.L.P."). Two causes: `clean_suppliers.verdict` ignored `identifier_as_stated` (a CIF protects an entity),
and `_es_person_name` took any 2-5 word capitals-only name without a marker; the run-together Spanish forms were not forms.

## Fix (backend/dgate/awards.py, backend/dgate/ops/clean_suppliers.py)

1. `verdict(name, country, ident)`: the stated number goes to `person_reason` (a contact detail typed in the field does not).
   The other callers already pass it (`read_award`, `placsp_awards`); UTE members and other-language spellings have none.
2. Legal forms: `sau slne sll slp sal sc scoop coop sccl scl sad sat aie sgps` added. `_words` already drops dots and joins
   single letters, so "S.A.U", "S. A. U.", "SAU", "S.L.L.", "S. COOP.", "S.COOP" all read as a form.
3. Spain: a name is a person only when the number says so (DNI, NIE, the publisher's mask), or it has the shape of a name
   AND holds a given name of `_ES_GIVEN` (255 Spanish, Catalan, Basque, Galician, Portuguese ones; no Victoria, Santiago,
   Luz, Paz, Salvador, Belén, Fátima, Ángeles) AND no legal form, no `_CORPORATE` word, no `_ES_TRADE` word (centro, talleres,
   comercial, hierros, autoescuela, iberia, gas, clientes, turbo, obras, construccion, ... san, santa). The generic
   "two title-case words" fallback no longer applies to ES. Given name anywhere: "GARCIA LOPEZ, JUAN" is a person.
4. `python -m dgate.ops.person_preview [--sample N] [--country ES]`: read-only transaction, same verdict, prints rows read,
   rows and distinct names that would be marked a person, by reason and country, and N random names.

Behaviour change asked for: "RECAMBIOS GOMEZ" (no given name, no number) was a person (an autónomo's trade name) and is now
published; the test moved it from the person list to the company list. Same with any person whose given name is not listed.

## Effect on the names (old code = integration awards.py, run side by side)

The PLACSP fixture holds no winners, so the run is over the 89 names of the person/company test lists (the 24 production
companies, the 3 production persons, the typical forms, the TED lists): before 28 wrong (all 28 companies read as persons),
after 0 wrong; no person changed verdict. Expected on production: the 518 distinct names fall to the ones with a listed given
name and no trade word, or a person's number. Check with the preview before `clean_suppliers --yes`.

## Tests (local, `D:\DEFENCEGATE TESTS\wp94`, Python 3.11, Postgres 17 `dgate-wp94` on 55494)

| Check | Result |
|---|---|
| ruff | All checks passed |
| unit | **3469 passed** |
| integration (`-m integration`) | **1262 passed**, 0 failed (award, PLACSP, supplier, wp39 suites included) |

New: `tests/unit/test_placsp_awards.py` (the 24 production companies and four person-name companies are companies, the
three production persons and the typical forms are persons, every dotted/run-together form, `verdict` reads the number);
`tests/integration/test_wp94.py` (preview writes nothing and counts 2 of 6; `clean_suppliers --yes` marks exactly the two).

## Follow-up: the production preview of 23 October 2026

The coordinator's read-only run of `person_preview` marked 217 rows: `person_name` 5 (all persons), `person_identifier` 10,
`person_marked` 202. Two false-positive classes, fixed in `person_reason` (shared by the loader and the cleaner):

1. `person_marked` on joint ventures: 202 rows were UTE names whose person members `joint_venture_name` had already blanked
   ("UTE THALES ESPAÑA - [natural person]"). A UTE with "[natural person]" and at least one other member (a lone legal form
   such as "- S.A." is no member) is a supplier; "UTE [natural person]", "UTE [natural person] - [natural person]" stay
   `person_marked`. Also found: the UTE splitter left "denominada “Matías Arrom Bibiloni" unblanked (the word "denominada"
   and the curly quote broke the name shape, and Matías was not a listed given name); fixed, tested.
2. `person_identifier` beating a legal form: a person's number (masked, DNI or NIE) no longer marks a name that has a legal form
   or a business word ("NAMMO PALENCIA SLU", "Sener Aerospace and Defence (SCR Division)"); logged at INFO, without name or
   number. This also changes the older test "ANY NAME AT ALL S.L." with a DNI: now an entity. `person_preview` prints the
   identifier class (none / masked / dni / nie / cif / other) per reason and per sample line, never the number.

Expected preview after this change: `person_name` 5, `person_identifier` 10 minus those whose name holds a legal form or business
word (at least the 2 named, so 8 or fewer), `person_marked` only the UTEs with no company member left (from 202 to the handful
that are all "[natural person]").

Re-run: ruff clean; unit 3485 passed; integration `test_wp94` and every award / PLACSP / supplier / wp39 / person suite
(`-k "award or placsp or supplier or wp39 or wp94 or person or individual or ezam"`) 118 passed.
