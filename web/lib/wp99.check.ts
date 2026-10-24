/**
 * Self-check of WP-99 (persona round of 23 October 2026, D: funding and eligibility), the browser half. The 60 verified pairs are
 * lib/wp93.check.ts; the profile migration is lib/profile.check.ts. Not part of the app. Run from web/:  node scripts/run-checks.mjs
 */
import assert from 'node:assert/strict';
import { check, type EligibilityFacts } from './eligibility-check';
import { BLOCKED_AS, NO_UA_PARTNER, callFit, fitLabel, shownFit } from './fit';
import { buildFundingAtom, feedCalls, fundingSubscription, FUNDING_FEED_MAX } from './funding-feed';
import { parseCallFilters } from './filters';
import { allCalls } from './mock/calls';
import { emptyProfile, type Profile } from './profile';
import { parseQuery } from './text-search';
import { EU_CUT_OFF_NOTE } from './ics';

const fact = (value: unknown, scope: 'call_document' | 'topic' | 'general' | 'programme' = 'call_document', note: string | null = null) =>
  ({ value, note, quote: 'q', confidence: 1, scope });

// ---- 9. the subscription of a funding search: webcal and Atom with exactly the filters, the calendar dropped for a Closed list
const s = fundingSubscription(parseCallFilters({ q: 'cyber', programme: 'DIGITAL', country: 'FR', status: 'open', page: '3', sort: 'budget-desc' }), 'https://defencegatehub.com');
assert.equal(s.ics, '/funding.ics?q=cyber&programme=DIGITAL&country=FR');
assert.equal(s.webcal, 'webcal://defencegatehub.com/funding.ics?q=cyber&programme=DIGITAL&country=FR');
assert.equal(s.atom, '/funding.atom?q=cyber&programme=DIGITAL&country=FR', 'the page and the order are not filters of a feed');
assert.deepEqual([fundingSubscription(parseCallFilters({ status: 'closed' }), 'https://x.test').ics, fundingSubscription(parseCallFilters({ status: 'closed' }), 'https://x.test').atom],
  [null, '/funding.atom?status=closed']);
const calls = allCalls();
const atom = buildFundingAtom(calls, { origin: 'https://defencegatehub.com', query: '?q=cyber', describe: 'the search “cyber”', total: calls.length, generatedAt: '2026-10-24T00:00:00Z' });
assert.ok(atom.startsWith('<?xml') && atom.includes('<link rel="self" type="application/atom+xml" href="https://defencegatehub.com/funding.atom?q=cyber"/>'));
assert.equal((atom.match(/<entry>/g) ?? []).length, Math.min(calls.length, FUNDING_FEED_MAX));
assert.ok(atom.includes(`tag:defencegatehub.com,2026:call:${feedCalls(calls)[0].id}`), 'each entry is the call itself, the newest first');
assert.ok(feedCalls(calls).every((c, i, a) => i === 0 || a[i - 1].firstSeenAt >= c.firstSeenAt));
assert.ok(!EU_CUT_OFF_NOTE.includes('17:00'), 'the calendar says what the page says: no time from the source');

// ---- 8. ASAP is searched with the EDIP calls; no successor note
assert.ok(parseQuery('asap')!.alsoSearched.includes('edip') && parseQuery('asap')!.matches('', 'EDF-EDIP-P-2027-LS-IRA-PE'));

// ---- 2. designated bodies: the words say who alone may apply, and that others only join one as a partner
const ua: Profile = { ...emptyProfile(), country: 'FR', legalForm: 'legal_person', applicantKind: 'company_or_research', orgKind: 'company', headcount: 'lt50', inGroup: 'no' };
const cp = { country: 'FR', orgType: 'sme' as const, hasPartners: '' as const, controlledAbroad: 'no' as const, kind: 'company' as const, size: { min: 0, max: 49 } };
const ncc = check({ designated_applicants: fact('National Coordination Centres', 'call_document', 'Others may take part in a consortium with them: ...') } as unknown as EligibilityFacts, cp);
assert.equal(ncc.lines[0].verdict, 'check');
assert.ok(ncc.lines[0].reason.startsWith('Only National Coordination Centres may apply; anybody else can take part only as a partner in a consortium with one.'));
const hubs = check({ designated_applicants: fact('National Cyber Hubs') } as unknown as EligibilityFacts, cp);
assert.equal(hubs.verdict, 'no');

// ---- 5. Horizon and the non-government controlled areas: not checked, and said
const occupied = { ...cp, country: 'UA', more: { legalPerson: true, company: true, managementCountry: 'UA', uaOccupied: 'yes' as const, uaPartner: '' as const, seapPartner: '' as const } };
const horizon = check({ eligible_countries: fact('EU Member States or Associated countries', 'topic') } as unknown as EligibilityFacts, occupied, { programme: 'HORIZON', topic: 'HORIZON-CL3-2026-01-BM-01' });
const line = horizon.lines.find((l) => l.key === 'territory');
assert.ok(line && line.verdict === 'check' && line.reason.includes('not checked here'));
assert.ok(!check({ eligible_countries: fact('EU Member States or Associated countries', 'topic') } as unknown as EligibilityFacts, occupied, { programme: 'DIGITAL', topic: 'X' }).lines.some((l) => l.key === 'territory'));

// ---- 4 and 5. what the badge says for the Ukraine Support Instrument: a fact, never a double negative, and never "nothing blocks you"
const usi = { state: 'read' as const, programme: 'EDF', topic: 'EDF-EDIP-USI-2026-LS-IRA-MAB', facts: { eligible_countries: fact('EU Member States and Ukraine') } as unknown as EligibilityFacts };
const programme = (rules: { rule: string; outcome: string }[], verdict: string, blocking: string[] = []) => ({
  assessments: [{ programme: 'EDIP-USI', name: 'EDIP: Ukraine Support Instrument', verdict, blocking,
    rules: rules.map((r) => ({ ...r, title: r.rule === 'USI-TERRITORY' ? 'Not established in a non-government controlled area of Ukraine' : 'The action involves Ukraine', requirement: null })) }],
  roadmap: { steps: [] },
}) as never;
const blocked = callFit(usi, { ...ua, country: 'UA' }, programme([{ rule: 'USI-TERRITORY', outcome: 'not_met' }], 'blocked', ['USI-TERRITORY']));
assert.equal(fitLabel(blocked).word, `Blocked: ${BLOCKED_AS['USI-TERRITORY']}`);
const partner = callFit(usi, { ...ua, uaPartner: 'no' }, programme([{ rule: 'USI-INVOLVES-UA', outcome: 'conditional' }], 'conditional'));
assert.equal(shownFit(partner), 'check');
assert.equal(fitLabel(partner).word, NO_UA_PARTNER);
const unanswered = callFit(usi, ua, programme([{ rule: 'USI-INVOLVES-UA', outcome: 'unknown' }], 'conditional'));
assert.ok(fitLabel(unanswered).word.startsWith('Nothing known blocks you'), 'without the answer it stays a question');

console.log('wp99 checks passed');
