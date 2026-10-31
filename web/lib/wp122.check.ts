/**
 * Self-check of WP-122 (docs/verification/home/wp122-selfcheck.md): the owner's plans and prices of /pricing, the "coming" labels and
 * the sign-up links. Not part of the app and not imported by it. Run from web/:  npm run check
 */
import assert from 'node:assert/strict';
import { BILLING_OPEN, ON_REQUEST, PLANS, signupHref } from './pricing';

// The five plans, their ids and the exact prices (owner, 25 Oct 2026: EUR, excluding VAT)
assert.deepEqual(PLANS.map((p) => [p.id, p.name, p.monthly ?? null, p.yearly ?? null]), [
  ['free', 'Free', null, null],
  ['pro', 'Pro', '€59', '€590'],
  ['team', 'Team', '€149', '€1,490'],
  ['consultant', 'Consultant', '€299', '€2,990'],
  ['founding', 'Founding customer', null, '€390'],
]);
assert.equal(PLANS.find((p) => p.id === 'founding')!.priceNote, 'Price fixed');
assert.deepEqual(ON_REQUEST.map((o) => [o.name, o.price]), [
  ['Call & Consortium Brief', '€450–900, one-off'],
  ['Cluster or association licence', '€4,900–9,900 / year'],
  ['White-label, API or data licence', 'From €12,000 / year'],
  ['“Who to approach” report', '€450–900, one-off'],     // WP-155: the owner's one-off service
]);
// Free lists only what works today: nothing "coming" there
assert.ok(PLANS[0].features.every((f) => !f.coming), 'Free has nothing coming');
// Every feature that is not live carries "coming", and only those (alerts, saved searches, workspace, exports beyond the CSV,
// gap analysis as a paid feature, branded PDF, client profiles, members' access, co-branded digest, white-label, API)
const coming = [...PLANS, ...ON_REQUEST].flatMap((p) => p.features.filter((f) => f.coming).map((f) => f.text));
// WP-131 (round 7): saved searches and alerts are built and open with sign-in (/alerts says so), so they carry `signin`, not `coming`;
// consortium gap analysis is live and free (Partners > Consortium gaps), so it is not "coming"
// WP-155 (owner's plan split, 28 Oct 2026): the API and the named company reports are built (by licence, with sign-in)
// WP-156..158 (30 Oct 2026): the exports, the team workspace, client profiles and the association licence are built
// WP-160 (31 Oct 2026): contracts ending soon, the full list with alerts (Pro) and its CSV (Team)
assert.deepEqual(coming, ['White-label']);
assert.deepEqual([...PLANS, ...ON_REQUEST].flatMap((p) => p.features.filter((f) => f.signin).map((f) => f.text)), ['Up to 10 saved searches',
  'E-mail alerts', 'Full competitor lists', 'Company signals: the full lists', 'Contracts ending soon: the full list, with alerts', '3 company reports a month',
  'Export of the eligibility check',
  'Shared workspace: saved searches, shortlist and follows', 'Up to 50 saved searches', '15 company reports a month',
  'Company signals as CSV', 'Contracts ending soon as CSV', 'Supplier-map export', 'Up to 15 client profiles', 'Unlimited saved searches',
  'Unlimited company reports, with your firm’s name on them']);
// Sign-up links: plan id and billing period; billing is off unless the setting says so
assert.equal(signupHref('pro', 'monthly'), '/signup?plan=pro&billing=monthly');
assert.equal(signupHref('founding', 'yearly'), '/signup?plan=founding&billing=yearly');
assert.equal(BILLING_OPEN, ['1', 'true'].includes(process.env.NEXT_PUBLIC_BILLING_OPEN ?? ''));
console.log('wp122 ok');
