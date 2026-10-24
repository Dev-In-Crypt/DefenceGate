/**
 * WP-106 (p02, p08): who may bid, said by the notice's legal basis and only as that act says it. A Portuguese supplier could not
 * tell whether it may bid in Spain, a Ukrainian one whether it may take part at all. The lines below paraphrase the articles they
 * name (EUR-Lex, the acts' own texts) and add nothing to them: no reading of national law, of a court ruling or of the notice. Pure
 * and import-light: lib/wp106.check.ts runs it on its own.
 */

export interface WhoMayBid {
  /** The act, as the page names it. */
  act: string;
  /** What the act says, in two or three sentences, each with its article. */
  text: string;
  /** The act is the EU defence and security directive (or its national transposition). */
  defence: boolean;
}

const PUBLIC_2014_24 =
  'The buyer must treat every company equally and without discrimination (Article 18), so a company from any EU country may bid on the same terms as one from the buyer’s country. ' +
  'Companies from a country that is party to the WTO Government Procurement Agreement, or to another agreement binding the EU, are treated in the same way for the contracts that agreement covers (Article 25). ' +
  'For companies from other countries the directive says no more: read the notice.';

const DEFENCE_2009_81 =
  'Each EU country decides whether its buyers may let companies from outside the EU take part (recital 18): the notice says what applies. ' +
  'The buyer may ask, or its country may require it to ask, the winner to subcontract a share of the contract, at most 30 % of its value, to subcontractors it chooses by competition (Article 21): a way to take part in the work without bidding.';

const RULES: { test: RegExp; act: string; text: string; defence?: boolean }[] = [
  { test: /^(32009L0081|.*2009\/81)/i, act: 'Directive 2009/81/EC (defence and security procurement)', text: DEFENCE_2009_81, defence: true },
  { test: /ley 24\/2011/i, act: 'Ley 24/2011, the Spanish law that transposes Directive 2009/81/EC', text: DEFENCE_2009_81, defence: true },
  { test: /^(32014L0024|.*2014\/24)/i, act: 'Directive 2014/24/EU (public procurement)', text: PUBLIC_2014_24 },
  { test: /ley 9\/2017/i, act: 'Ley 9/2017 (LCSP), the Spanish law that transposes Directive 2014/24/EU', text: PUBLIC_2014_24 },
  {
    test: /^(32014L0025|.*2014\/25)/i, act: 'Directive 2014/25/EU (utilities)',
    text: 'The buyer must treat every company equally and without discrimination (Article 36), so a company from any EU country may bid. ' +
      'Companies from a country that is party to the WTO Government Procurement Agreement, or to another agreement binding the EU, are treated in the same way for the contracts that agreement covers (Article 43). ' +
      'For companies from other countries the directive says no more: read the notice.',
  },
  {
    test: /^(32014L0023|.*2014\/23)/i, act: 'Directive 2014/23/EU (concessions)',
    text: 'The buyer must treat every company equally and without discrimination (Article 3), so a company from any EU country may bid. For companies from other countries, read the notice.',
  },
  {
    test: /^(32004L0018|.*2004\/18)/i, act: 'Directive 2004/18/EC (public procurement, replaced by Directive 2014/24/EU)',
    text: 'The buyer must treat every company equally and without discrimination (Article 2), so a company from any EU country may bid. ' +
      'Companies from a country that is party to the WTO Government Procurement Agreement are treated in the same way for the contracts it covers (Article 5). For companies from other countries, read the notice.',
  },
];

/** What a notice's legal basis says about who may bid; null when it is not one of the acts above (the page then sends to the notice). */
export function whoMayBid(legalBasis: string | null | undefined): WhoMayBid | null {
  const basis = (legalBasis ?? '').trim();
  if (!basis) return null;
  const rule = RULES.find((r) => r.test.test(basis));
  return rule ? { act: rule.act, text: rule.text, defence: rule.defence === true } : null;
}

/** The line for a notice whose legal basis is none of the acts above. */
export const WHO_MAY_BID_UNKNOWN = 'The notice states no legal basis we describe here. It says who may take part, in which language and how to submit.';
/** Under every line: what it is not. */
export const WHO_MAY_BID_NOTE = 'What the act says, not advice: the notice and the buyer set the conditions.';

/**
 * "Who wins such contracts": the supplier map under the notice's main code (to the 5-digit category: an 8-digit code often has no
 * winner yet) and the buyer's country. null without a code.
 */
export function winnersHref(cpv: string | null | undefined, country: string | null | undefined): string | null {
  const digits = /^\d{8}/.exec(cpv ?? '')?.[0];
  if (!digits) return null;
  const prefix = digits.replace(/0+$/, '').padEnd(2, '0').slice(0, 5);
  const q = new URLSearchParams({ cpv: prefix });
  if (country && /^[A-Z]{2}$/.test(country)) q.set('buyerCountry', country);
  return `/suppliers?${q.toString()}`;
}
