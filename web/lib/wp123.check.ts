/**
 * WP-123 self-check: the plan chosen on the pricing page and carried to /signup. Not part of the app.
 * Run from web/:  node scripts/run-checks.mjs   (or tsc this file alone, as the other checks)
 */
import assert from 'node:assert/strict';
import { planSentence, readPlanChoice } from './plans';

assert.deepEqual(readPlanChoice('pro', 'monthly'), { plan: 'pro', billing: 'monthly' });
assert.deepEqual(readPlanChoice(['team', 'x'], ['yearly']), { plan: 'team', billing: 'yearly' });
assert.deepEqual(readPlanChoice('consultant', 'weekly'), { plan: 'consultant', billing: null });
assert.deepEqual(readPlanChoice('free', 'yearly'), { plan: 'free', billing: null });
for (const bad of [undefined, null, '', 'platinum', 'PRO', 'toString', '__proto__', 42, ['nope']]) assert.equal(readPlanChoice(bad, 'monthly'), null, String(bad));

assert.equal(planSentence({ plan: 'pro', billing: 'monthly' }), 'You chose Pro, monthly. Payment opens soon.');
assert.equal(planSentence({ plan: 'founding', billing: 'yearly' }), 'You chose Founding customer, yearly. Payment opens soon.');
assert.equal(planSentence({ plan: 'team', billing: null }), 'You chose Team. Payment opens soon.');
assert.equal(planSentence({ plan: 'free', billing: null }), 'You chose Free.');
console.log('wp123 ok');
