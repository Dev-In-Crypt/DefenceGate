/**
 * Glossary entries: short plain-English explanations of terms a defence supplier meets in notices.
 * Each is at most three sentences and is not legal advice. Official sources are named, never linked
 * from here: the reader finds them by name.
 */
export interface GlossaryEntry {
  id: string;
  term: string;
  /** What the term stands for, when it is an abbreviation. */
  full?: string;
  body: string;
  /** Where the authoritative text is published, by name. */
  source?: string;
  see?: { label: string; href: string };
}

export const GLOSSARY: GlossaryEntry[] = [
  {
    id: 'cpv', term: 'CPV', full: 'Common Procurement Vocabulary',
    body: 'The EU code list that describes what a contract is for. A code has eight digits, and the first two give the division, the first three the group. Buyers put one main code and any number of additional codes on a notice.',
    see: { label: 'Find CPV codes', href: '/cpv' },
  },
  {
    id: 'competitive-dialogue', term: 'Competitive dialogue',
    body: 'A procedure for complex contracts. The buyer first discusses with selected suppliers how its needs could be met, then invites final tenders based on the solutions discussed.',
    source: 'Directive 2009/81/EC on EUR-Lex',
  },
  {
    id: 'contract-award-notice', term: 'Contract award notice',
    body: 'The notice that reports the result of a procurement: who was awarded the contract and, usually, its value. It is published after the award, so it can appear well after the tender closed.',
  },
  {
    id: 'contract-notice', term: 'Contract notice',
    body: 'The announcement that a buyer is launching a procurement and inviting bids or requests to take part. It normally states the subject, the procedure, the deadline and where to get the documents.',
  },
  {
    id: 'defence-and-security-procurement', term: 'Defence and security procurement',
    body: 'Public buying of military equipment, works and services, and of sensitive supplies for security. In the EU, contracts of this kind fall under Directive 2009/81/EC. Whether a particular purchase is covered is for the buyer and the law to decide, not for this site.',
    source: 'Directive 2009/81/EC on EUR-Lex',
  },
  {
    id: 'directive-2009-81-ec', term: 'Directive 2009/81/EC',
    body: 'The EU directive on the award of certain works, supply and service contracts in the fields of defence and security. It applies instead of the general public procurement directives to the contracts it covers. Among other things it contains rules on the security of information and the security of supply.',
    source: 'EUR-Lex',
    see: { label: 'How we use the legal basis', href: '/methodology' },
  },
  {
    id: 'dual-use', term: 'Dual-use',
    body: 'Goods, software or technology that can serve both civil and military purposes. In EU export law the word has a specific legal meaning, set by Regulation (EU) 2021/821. On a funding call here, “dual-use” is the regime the programme or source itself assigns; it is not an export-control classification.',
    source: 'EUR-Lex',
  },
  {
    id: 'eda', term: 'EDA', full: 'European Defence Agency',
    body: 'An agency of the European Union that supports member states in developing their defence capabilities and in cooperating on defence.',
    source: 'European Defence Agency',
  },
  {
    id: 'edf', term: 'EDF', full: 'European Defence Fund',
    body: 'An EU programme that funds collaborative defence research and development. Calls are published on the EU Funding & Tenders Portal, and applicants are normally consortia of several entities from several countries.',
    source: 'EU Funding & Tenders Portal',
    see: { label: 'EDF calls', href: '/funding?programme=EDF' },
  },
  {
    id: 'edip', term: 'EDIP', full: 'European Defence Industry Programme',
    body: 'An EU programme that supports the European defence industry. Its calls appear in our funding list under EDIP; read the programme’s own documents for its scope and rules.',
    see: { label: 'EDIP calls', href: '/funding?programme=EDIP' },
  },
  {
    id: 'eforms', term: 'eForms',
    body: 'The EU standard electronic format for public procurement notices, used on TED. It defines the fields a notice carries, so that notices from different countries can be read and compared in the same way.',
    source: 'TED and the Publications Office of the European Union',
  },
  {
    id: 'framework-agreement', term: 'Framework agreement',
    body: 'An agreement between a buyer and one or more suppliers that sets the terms for contracts to be awarded during a period. The buyer then places orders or runs mini-competitions under it. Being a party to a framework does not guarantee any order.',
  },
  {
    id: 'lot', term: 'Lot',
    body: 'A part of a procurement that can be bid for separately. Each lot can have its own scope and value, so check the lots in the original notice.',
  },
  {
    id: 'nda', term: 'NDA', full: 'Non-disclosure agreement',
    body: 'A contract in which a party promises not to share certain information. A buyer may ask suppliers to sign one before releasing the tender documents. We only flag that a notice mentions such a confidentiality requirement.',
  },
  {
    id: 'negotiated-procedure', term: 'Negotiated procedure',
    body: 'A procedure in which the buyer negotiates the terms of the contract with the suppliers it has selected. Under Directive 2009/81/EC it can be run with or without a prior notice, and the second case is allowed only in the circumstances the directive lists.',
    source: 'Directive 2009/81/EC on EUR-Lex',
  },
  {
    id: 'notice-amendment', term: 'Notice amendment and corrigendum',
    body: 'A buyer can correct or change a published notice, for example to move a deadline or fix a value. On TED this is done with a corrigendum or a change notice; a national portal may change the notice in place. DefenceGate keeps every version it observes, so the record shows what changed and when we saw it.',
    see: { label: 'How versions are kept', href: '/methodology' },
  },
  {
    id: 'notice-status', term: 'Notice status',
    body: 'Open means the notice is still taking bids. Closed means its deadline has passed, Awarded and Cancelled are the source’s own words, and Planned means it is announced but not yet open. Status unknown means the source does not say, so check the original.',
  },
  {
    id: 'prior-information-notice', term: 'Prior information notice', full: 'PIN',
    body: 'An advance announcement of a buyer’s plans, published before the contract notice. It gives suppliers early warning. Normally it does not itself invite bids; the notice says if it does.',
  },
  {
    id: 'restricted-procedure', term: 'Restricted procedure',
    body: 'A two-stage procedure. Any supplier may ask to take part, but only those the buyer selects after the first stage are invited to submit a tender.',
    source: 'Directive 2009/81/EC on EUR-Lex',
  },
  {
    id: 'safe', term: 'SAFE', full: 'Security Action for Europe',
    body: 'An EU instrument, adopted in 2025, under which the EU lends money to member states for defence procurement. It is a loan instrument for governments, not a grant for companies. Suppliers meet it through the procurement of the states that borrow.',
    source: 'European Commission',
  },
  {
    id: 'security-clearance', term: 'Security clearance',
    body: 'An official decision that a company or a person may handle classified information up to a stated level. It is issued by a national security authority. A notice that requires one says so in its conditions; DefenceGate only flags that the notice mentions it.',
  },
  {
    id: 'source-status', term: 'Source status',
    body: 'The result of a source’s last collection run, shown on the source status page as OK, partial, failed or never run. Partial means the run fetched less than we expected. Check it before concluding that a notice does not exist.',
    see: { label: 'Source status', href: '/data' },
  },
  {
    id: 'ted', term: 'TED', full: 'Tenders Electronic Daily',
    body: 'The EU online journal for public procurement notices, run by the Publications Office of the European Union. Buyers above the EU thresholds publish their notices there. It is one of the sources we collect from.',
    source: 'TED',
  },
  {
    id: 'veat', term: 'VEAT', full: 'Voluntary ex ante transparency notice',
    body: 'A voluntary notice a buyer publishes before awarding a contract without a prior call for competition. It states that the buyer intends to do so and gives its reasons, and it lets other suppliers react before the contract is signed.',
  },
];
