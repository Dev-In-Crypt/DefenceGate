# Backlog (feature freeze from 26 October 2026)

Agreed with the owner on 26 October 2026: no new verification rounds or polish packages. Only breakages are fixed (5xx,
broken pages, wrong data). Everything else is written here and not worked on until real users ask for it.

| Item | Why it waits |
|---|---|
| Search on page 2+ for common words (e.g. "fuel") takes ~4 s; only first pages are stored | slow, not broken |
| Generic Polish fire service (PSP) buyer rows 184800 and 174324 collect other towns' notices | data tidy-up, not wrong totals |
| 52 municipality (gmina) names to check against TERYT | cosmetic |
| 34 rejected merge candidates could be written as REJECT | bookkeeping |
| Detailed visitor statistics with self-hosted Umami (referrers, paths); owner asked 26 Oct 2026 | new feature; needs a privacy update |
| IDV Defence Vehicles España (436788) and "IDV Defensa ... (antes Iveco España)" (438966): one company, two rows; no merge tool for a reviewed non-BOAMP pair | one pair; a generic reviewed-merge mode first |
| Rheinmetall Electronics (3 rows) and Hensoldt Optronics (2 rows) under different numbers; marked "possibly this company" on the page | the owner's rule: different numbers are never merged without proof |
| Remaining French buyer groups (12) left out of the 27 Oct review: ministry-wide numbers, contradictions | need a person per group |
| React #418 hydration warning on /tenders?status=planned, intermittent (1 in 4 runs of wp52b-api on the fake API, 28 Oct 2026) | console warning, not seen by visitors; same class as the /app fix of WP-150 |
