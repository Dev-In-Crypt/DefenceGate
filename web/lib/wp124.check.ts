/**
 * WP-124 self-check: the words of payment (Creem, merchant of record). Not part of the app.
 * Run from web/:  node scripts/run-checks.mjs   (or tsc this file alone, as the other checks)
 */
import assert from 'node:assert/strict';
import { foundingLine, offers, periodLine, STATUS_LABEL } from './billing';
import { billingOpen, planSentence } from './plans';

// closed (the default): as WP-123 said it; open: where payment comes
assert.equal(planSentence({ plan: 'pro', billing: 'monthly' }), 'You chose Pro, monthly. Payment opens soon.');
assert.equal(planSentence({ plan: 'pro', billing: 'monthly' }, true), 'You chose Pro, monthly. You pay for it after you sign in, under Billing.');
assert.equal(planSentence({ plan: 'free', billing: null }, true), 'You chose Free.');

// open only with the build switch AND the API's settings
assert.equal(billingOpen(false, { billing: true }), false);
assert.equal(billingOpen(true, { billing: false }), false);
assert.equal(billingOpen(true, { billing: true }), true);

// one offer per paid plan and period, with the prices of /pricing; Founding customer is yearly only
assert.deepEqual(offers().map((o) => [o.plan, o.billing, o.price]), [
  ['pro', 'monthly', '€59 / month'], ['pro', 'yearly', '€590 / year'],
  ['team', 'monthly', '€149 / month'], ['team', 'yearly', '€1,490 / year'],
  ['consultant', 'monthly', '€299 / month'], ['consultant', 'yearly', '€2,990 / year'],
  ['founding', 'yearly', '€390 / year'],
]);

// "N of 20 left" only from a count, and never a number that is not one
assert.equal(foundingLine(null, 20), null);
assert.equal(foundingLine(3, 20), '3 of 20 places left.');
assert.equal(foundingLine(0, 20), 'All 20 places are taken.');

// every state of the API has words; the period line says only what is true for the state
for (const s of ['active', 'trialing', 'past_due', 'unpaid', 'paused', 'scheduled_cancel', 'canceled', 'expired', 'disputed']) assert.ok(STATUS_LABEL[s], s);
const sub = (status: string) => ({ plan: 'pro' as const, period: 'monthly' as const, status, periodEnd: '2026-11-25T12:00:00Z' });
assert.equal(periodLine(sub('active')), 'Renews on 25 Nov 2026.');
assert.equal(periodLine(sub('scheduled_cancel')), 'Open until 25 Nov 2026.');
assert.equal(periodLine(sub('canceled')), null);
assert.equal(periodLine({ ...sub('active'), periodEnd: null }), null);
console.log('wp124 ok');
