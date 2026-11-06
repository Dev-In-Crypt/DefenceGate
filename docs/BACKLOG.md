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
| React #418 hydration warning on /tenders?status=planned, intermittent (1 in 4 runs of wp52b-api on the fake API, 28 Oct 2026); also once on /suppliers/155001-fake-prime-sa/competitors (wp155-api, fake-api-desktop, 31 Oct 2026; passed on reruns) | console warning, not seen by visitors; same class as the /app fix of WP-150 |
| BOAMP contract periods 2015-2023 (WP-165, stopped 31 Oct 2026 by the owner's market focus). Census of ~1,600 stored notices: OBJET schema `OBJET/DUREE_DELAI/{DUREE_MOIS,DUREE_JOURS,DATE_DEBUT,DATE_FIN}`, per lot `OBJET/LOTS/LOT/DUREE_MOIS`, framework term `OBJET/ACCORD_CADRE/{DUREE_AN,DUREE_MOIS}` (only when nothing else), renewal `OBJET/CARACTERISTIQUES/RECONDUCTIONS/{OUI,NON,NB_RECONDUCTIONS[_MAX]}`, `LOT/RENOUVELLEMENT_OUI/_NON`; skip `CONDITION_DELAI/VALIDITE_OFFRE/DUREE_*`, `CARACTERISTIQUES/OPTIONS/DUREE_*`, `RECONDUCTIONS/DUREE_MOIS`. ~74% of sampled notices carry a period, awards almost none. 2024+ national forms: `FNSimple/initial/natureMarche/dureeMois`, `MAPA/initial/duree/{nbMois,nbJours,dateDebutPrestation,dateDebutTravaux}` (skip `MAPA/initial/delais/validite`) | demand for ending contracts in the EU not shown yet |
| Backups: on 6 Nov only four local dumps were left on the server (4, 5, 6 Nov and a pre-deploy one) although DGATE_BACKUP_KEEP_DAYS_LOCAL defaults to 7; the 3 Nov nightly dump is neither local nor offsite (the SFTP session leak of 2-5 Nov, fixed in 7a24e69). Check the local retention setting and whether anything else prunes /backups | only a gap of one night; offsite copies exist for 1, 2, 4, 5, 6 Nov |
