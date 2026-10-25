/**
 * How many questions each check asks, in one place for every page that says it (home, /check, /readiness, a call page's note).
 * Counted on the forms themselves, the way e2e/wp121.spec.ts counts (each group once, each field outside a group):
 *  - the readiness check's five steps: 24 on the shortest route (e2e/wp125.spec.ts), 35 on the longest;
 *  - the supplier profile (WP-131, round 7: the tile said 18 to 35; 17 is asked of a company outside the EU, and 53 in Spain with every
 *    follow-up opened): e2e/wp131.spec.ts walks every country, products and services, with nothing answered and with every follow-up
 *    opened, and fails when this range is not the one found.
 * lib/wp131.check.ts fails when a page writes a range by hand instead of reading it here.
 */
export interface QuestionRange { min: number; max: number }

export const STEPS_QUESTIONS: QuestionRange = { min: 24, max: 35 };
export const SUPPLIER_QUESTIONS: QuestionRange = { min: 17, max: 53 };

/** "24 to 35" */
export const rangeWords = (r: QuestionRange): string => `${r.min} to ${r.max}`;
