# The questions that need all three layers (concept section 5): what the product answers on 17 October 2026

Source: `docs/spec/eu-defence-access-portal-concept.md`, section 5 ("How the layers connect"). Written for WP-32. For
each of the four questions: what the product answers today, what it cannot answer yet and why, and what is built where
(tests named). A question is "answered" only where an honest answer can be given from the data we hold; where it cannot,
the product says so on the page and does not guess.

The three layers: 1 Opportunities (tenders and funding calls), 2 Networks (who took part in funded projects; CORDIS and
the EDF factsheets), 3 Readiness (what a company needs in order to qualify; the rules engine of WP-29).

## 1. "Show me open tenders in Spain and Portugal that I am eligible for today, and the ones I would become eligible for if I obtained AQAP 2110."

**Answered today: the first half of the filter only.** `/tenders?country=ES,PT` lists the open tenders of buyers in Spain and
Portugal (layer 1). Whether a company is *eligible* for a tender, and whether AQAP 2110 would change that, **cannot be answered**:

- A tender carries no certification requirement in our data. What is stored is a boolean "security clearance stated"
  (`opportunity.security_clearance_required`, used as a corroborating signal of the classification) and the CPV codes.
  Whether a tender asks for AQAP 2110, ISO 9001, an NCAGE code or an export licence is written in the notice's selection
  criteria and documents, which have not been read.
- What it needs: extraction of the certification requirements from tender notices and their documents, with a verbatim
  quote check and a strict schema, as `dgate/eligibility.py` does for funding calls (calls cost money to read: an
  owner decision), then a join with `requirement` (layer 3) so that "if I obtained AQAP 2110" becomes a filter. Not built.
- What exists for the second half: the requirement itself. `/requirements/aqap2110` says what it is, who issues it in each
  country, the cost and time as vendor ranges, and that no EDF, EDIP or SAFE rule makes it a condition of eligibility.
  `/readiness` computes the roadmap for a company. They answer "what would AQAP 2110 cost me and how long would it take",
  not "which tenders would it open".

The funding twin of this question is answered, see 3.

## 2. "Which consortia in counter-UAS have received EDF funding twice or more, and which of them lack a supplier in my component category?"

**Answered in part, by the networks package (WP-28), not by this one.** The data holds EDF projects with their consortium
(2021 to 2025 results), the capability category of 2023 to 2025 projects (a code such as `AIR`, `SENS`, `CYBER`) and the
topic code. "Counter-UAS" is not a field: it is a topic of a kind that the codes do not name, so it cannot be selected
exactly, and the answer for a capability area is an approximation by category and topic words. WP-28 defines "capability
area" from what the data carries and documents the limit (`GET /v1/analytics/consortium-gaps?programme=&topic=` and its page).

**Cannot be answered: "lack a supplier in my component category".** No organisation has a component or product category in our
data (CORDIS does not state one, the factsheets give a name and a country only). What can be said is who is *not* in a
consortium by country, role or size, which is what the narrow version in WP-28 does.

What this package adds for the same need: on each funding call page, "Partners from earlier projects" lists the organisations
that took part in projects of the call's area, ranked, with the projects as evidence (`GET /v1/funding/{slug}/partners`,
tests `tests/integration/test_wp32.py`, `tests/unit/test_wp32_areas.py`). It is a list of who has worked in the area, not a
list of gaps.

## 3. "This call closes in six weeks. Given my current certification status, can I realistically participate, and if not, what is the fastest path?"

**Answered, for the programmes that have rules (EDF, EDIP, EDIP Ukraine Support Instrument).** On the call page,
"Your readiness for this call" reads the profile saved in the browser (the five-step check of `/readiness`), and shows:

1. the rules read from the call's own document against the profile (`web/lib/fit.ts`; the same facts and the same
   conservative verdict as the older "Check your company" form, which keeps working), and
2. the programme's rules and the time left: `POST /v1/readiness/assess` with the call's id returns, for the programme
   the call belongs to, the verdict, the rules that block, the steps that would remove the block with their cost and time
   as vendor ranges, whether they fit before the deadline (`realistic`: yes, maybe, no, not_possible, depends, unknown,
   closed) and the fastest path in days.

The two are put together in one sentence that never says more than the weaker of them (`web/lib/call-readiness.ts`, checked in
`call-readiness.check.ts`). Without a profile the block is a path to the check and nothing is computed.

Tests: `tests/integration/test_readiness_api.py` (the timing, WP-29), `tests/integration/test_wp32.py`
(`test_an_edip_call_filed_under_the_edf_is_judged_by_the_edip_rules`), `web/lib/fit.check.ts`, `web/lib/call-readiness.check.ts`,
`web/e2e/fit.spec.ts`.

Limits, each said on the page:

- **Horizon and Digital Europe calls have no programme rules** in the readiness model (none was read for them): the block
  says "No readiness rules are encoded" and shows only what the call's document says, if it was read. SAFE has no calls.
- **The call's own rules exist for 82 of 159 EU calls** (the rest are "not read yet"); for those there is nothing to compare
  and the block says so. A rule from the work programme's general annexes is never shown as a plain yes.
- The profile has no question about **partners**, so a call that needs a consortium is at best "check".
- The EDIP calls are filed by the portal under the EDF; they are judged by the EDIP rules (this package fixed that in
  `readiness/api.py programmes_of_call`). A Ukrainian company is *not eligible* for the EDIP Programme and *is* for the Ukraine
  Support Instrument; the page shows that difference.

## 4. "Which prime contractors have partnered with Ukrainian suppliers in the last two years?"

**Answered by the networks package (WP-28)**: `GET /v1/analytics/ukraine-partners?since=` (coordinators and members of projects
with a participant established in Ukraine). Limits that the page there must state, and that come from the data and not from
the code:

- "Prime" is not a field. A coordinator is the nearest thing, and a coordinator can be a university or a research
  institute. The answer is "coordinators of projects with a Ukrainian participant".
- The CORDIS copy we read (SPARQL) ends in November 2025 and lags the monthly package, so the last months of any two-year
  window are missing; Ukraine became eligible for the EDF only with Regulation (EU) 2025/2653, so EDF projects with Ukrainian
  participants are few. The EDF participants come from factsheets read by a language model (names checked against the text).
- Procurement contracts (layer 1) say who won, not who partnered: the winner's country is not a partnership.

## Summary

| Question | Answered today | Built where | Not possible yet, and what it needs |
|---|---|---|---|
| 1. Tenders I am eligible for, and with AQAP 2110 | Open tenders by country; the requirement and its cost and time | `/tenders`, `/requirements/aqap2110`, `/readiness` | Certification requirements extracted from tenders (a model run, owner decision), joined to `requirement` |
| 2. Consortia funded twice, lacking my component | Consortia and categories (WP-28); partners by area (WP-32) | WP-28 analytics; `GET /v1/funding/{slug}/partners` | A component or product category per organisation: no source holds it |
| 3. This call closes in six weeks | Yes for EDF and EDIP calls; the document's rules for the 82 calls read | `POST /v1/readiness/assess` with `call`; `CallReadiness`; `fit.ts` | Horizon and Digital rules; the 77 calls whose rules are not read; a question about partners |
| 4. Primes partnered with Ukrainian suppliers | Coordinators of projects with a Ukrainian participant (WP-28) | WP-28 analytics | "Prime" as a class; CORDIS data after November 2025 |
