// WP-166 self-check: the words of a partner's past roles, the one share note and its few-contracts line, and the menu's place for
// Contracts ending soon. Run: node scripts/run-checks.mjs
import assert from 'node:assert/strict';
import { UA_MARK, pastRolesWords } from './networks';
import { FEW_AWARDS, SHARE_NOTE, fewAwardsLine } from './coverage-copy';
import { FOOTER_GROUPS, MAIN_NAV } from './nav';

// past roles: most responsible first, zeros left out, "projects" said once; nothing when the data holds none
assert.equal(pastRolesWords({ coordinator: 3, participant: 12, thirdParty: 1, other: 0 }), 'coordinator in 3 projects, participant in 12, third party in 1');
assert.equal(pastRolesWords({ coordinator: 0, participant: 1, thirdParty: 0, other: 2 }), 'participant in 1 project, other partner roles in 2');
assert.equal(pastRolesWords({ coordinator: 0, participant: 0, thirdParty: 0, other: 0 }), null);
assert.equal(pastRolesWords(undefined), null);
assert.equal(pastRolesWords(null), null);
assert.equal(UA_MARK, 'Ukrainian organisation');

// one note, naming the sources, the coverage figure and its source, and that shares are indicative
for (const w of ['TED', 'national portals', 'about a tenth of EU defence spending', 'ECIPE Policy Brief 20/2025', 'indicative']) assert.ok(SHARE_NOTE.includes(w), w);
// the few-contracts line: below the signals' small-company threshold only
assert.equal(FEW_AWARDS, 10);
assert.equal(fewAwardsLine(9), 'Counted from 9 contracts only: too few for a share to say much.');
assert.equal(fewAwardsLine(1), 'Counted from 1 contract only: too few for a share to say much.');
assert.equal(fewAwardsLine(10), null);
assert.equal(fewAwardsLine(null), null);
assert.equal(fewAwardsLine(undefined), null);

// the menu: Funding leads Tenders & funding; Contracts ending soon is in it (and in the footer group), never top-level
const open = MAIN_NAV.find((n) => n.key === 'open')!;
assert.equal(open.label, 'Tenders & funding');
assert.equal(open.children![0].href, '/funding');
assert.ok(open.children!.some((c) => c.href === '/tenders/ending' && c.label === 'Contracts ending soon'));
assert.ok(!MAIN_NAV.some((n) => n.href === '/tenders/ending'));
assert.ok(FOOTER_GROUPS[0].links.some((l) => l.href === '/tenders/ending'));
console.log('wp166: ok');
