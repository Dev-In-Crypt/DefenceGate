# Eligibility of calls that have no call document (WP-31, 17 October 2026)

Continues `ELIGIBILITY_FINDINGS.md` (in the owner checkout; the extraction results are in its last section).

## Что есть у таких вызовов

75 из 159 вызовов EU-портала не ссылаются на «Call document». Что у них есть (проверено по хранимым
`conditions_raw.documents` и `eligibility_text`):

- у 67 есть ссылка на общие приложения рабочей программы (`wp-15-general-annexes_horizon-2026-2027`, для старых
  вызовов `wp-14` и `wp-13`) или на рабочую программу EIC (`EIC-Work-Programme-2026.pdf`);
- у 70 в тексте условий есть собственные условия темы (разделы 3 «Other eligible conditions» и 6 «Legal and
  financial set-up»), которые говорят больше, чем «described in Annex B».

`eligibility.sources_of()` отображает вызов на источники детерминированно (без модели): общий источник
(`scope = general`, читается один раз на все вызовы программы) и текст темы (`scope = topic`, ключ
`call-text:<хеш>`). Проверка цитат и строгая схема те же. В `note` каждого факта сказано, общее ли это правило или
правило темы; общее правило никогда не даёт «нет» в форме «Can you apply?», только «проверьте». Факт темы с найденной
цитатой перекрывает общий. Запуск модели: `python -m dgate.ops.extract_eligibility --yes --scope general` и
`--scope topic` (по умолчанию команда без `--yes` только перечисляет). `PROMPT_VERSION` не менялся: системный
промпт тот же, для новых видов источника отличается только вводная строка перед текстом.
