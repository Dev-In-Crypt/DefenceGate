# UK Parliament written statements (source note, WP-40, 18 October 2026)

Used for one fact: the position of the United Kingdom on SAFE, in the entry `safe-uk-unconfirmed` of the regulatory tracker.

| Question | Answer |
|---|---|
| What | Written statement HCWS1114, "Statement on UK-EU Relations", Paymaster General and Minister for the Cabinet Office, 1 December 2025. |
| Where it is read | The Parliament's public written-statements API, `https://questions-statements-api.parliament.uk/api/writtenstatements/statements?madeWhenFrom=2025-12-01&madeWhenTo=2025-12-01` (list) and `.../statements/1858440` (the text). The web page `questions-statements.parliament.uk/written-statements/detail/2025-12-01/hcws1114` answers an automated client with a bot check (Cloudflare "Just a moment"); it was not bypassed. The tracker links to that page, which a person can open. |
| Access | Anonymous JSON, no login, three requests in all, two seconds apart, honest `User-Agent` (`DefenceGate research (+https://defencegatehub.com)`). `robots.txt` of the API host answers 404 (no rules). |
| Licence | UK Parliament publishes its content under the Open Parliament Licence; this note did not re-read the licence text. Only one sentence of the statement is quoted, with its source and date, as for every tracker entry. Check the licence before reusing more. |
| Quoted | "However, we have not been able to conclude these negotiations with an agreement." The statement also says UK companies "will be able to participate and benefit from SAFE contracts to provide up to 35% of their content"; the tracker paraphrases that and does not quote it. |
| What it does not show | The position after 1 December 2025. No later primary text was found, so the entry's status stays `unconfirmed`. |

The Council's press pages (consilium.europa.eu) still answered with a browser check on 18 October 2026 and were not read. The Council decisions
that matter (2025/2134, 2026/444, 2026/1381) and the agreement with Canada (OJ L 2026/445) are Official Journal texts and were read from the Publications
Office (CELLAR), which has no bot check.
