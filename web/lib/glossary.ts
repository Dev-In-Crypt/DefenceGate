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
    id: 'scope', term: 'Scope (defence-relevant, core, supplies)',
    body: 'Defence-relevant is the default list: the core defence notices and the supplies to defence buyers together. Core means the notice itself is defence, by the defence procurement directive or a military product code. Supplies to defence buyers are notices that are here because their buyer is a defence body, or because of a single defence signal from the wrong kind of buyer. Each card says why it is on the list. A military code bought by a municipality or a hospital is dual-use and only appears under All.',
    see: { label: 'How a notice is judged', href: '/methodology' },
  },
  {
    id: 'cpv', term: 'CPV', full: 'Common Procurement Vocabulary',
    body: 'The EU code list that describes what a contract is for. A code has eight digits, and the first two give the division, the first three the group. Buyers put one main code and any number of additional codes on a notice.',
    see: { label: 'Find CPV codes', href: '/cpv' },
  },
  {
    id: 'civil-buyer-directive', term: 'Filed under the defence procurement directive by a civil buyer',
    body: 'The notice states Directive 2009/81/EC as its legal basis, and nothing else marks it as defence: no military product code, and a buyer that is not a defence or security body. We keep it in the supplies list rather than the defence notices, because the directive alone is not enough to call it defence.',
    source: 'Directive 2009/81/EC on EUR-Lex',
  },
  {
    id: 'defence-goods-only', term: 'Defence goods only',
    body: 'A switch in the tender filters. It keeps the notices that say defence themselves, by the defence procurement directive or a military product code, and drops those that are listed only because their buyer is a defence body or its product code is explained by the buyer’s own needs. It narrows the scope you chose; it never widens it.',
  },
  {
    id: 'security-body-cpv', term: 'Security-body purchase of a military-type product code',
    body: 'The notice carries a military product code and nothing else marks it as defence, and its buyer is a police, prison, border, customs or tax body. Such bodies buy items that sit in military codes for their own use, so we keep the notice in the supplies list rather than the defence notices.',
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
    body: 'Goods, software or technology that can serve both civil and military purposes. In EU export law the word has a specific legal meaning, set by Regulation (EU) 2021/821. On a funding call here, “dual-use” is a label DefenceGate gives, and the label is ours, not the programme’s, and not an export-control classification. We give it to all Digital Europe calls, to Horizon Europe’s civil-security, digital, industry and space areas and the European Innovation Council, and to Connecting Europe military-mobility topics. Calls under a defence programme (EDF, EDIP) are labelled defence. Because the rule names whole programmes, most open calls carry the label.',
    source: 'EUR-Lex',
    see: { label: 'The rule in the methodology', href: '/methodology#s-what-defence-and-dual-use-mean-here' },
  },
  {
    id: 'action-type', term: 'Action type',
    body: 'The kind of grant a funding call offers, as the EU portal codes it, for example EDF-LS for a European Defence Fund lump sum grant or HORIZON-EIC for a European Innovation Council grant. We show the portal’s code and do not interpret it; the call text explains what the grant covers.',
    source: 'EU Funding & Tenders Portal',
  },
  {
    id: 'call-and-topic', term: 'Call and topic',
    full: 'Call budget and topic budget',
    body: 'On the EU portal a call for proposals is split into topics, and you apply to a topic. Topics of one call can share a single budget: then the card says “Call budget” and the same figure appears on each of them, because the portal does not say how the pot is split. A figure marked “Topic budget” belongs to that topic alone.',
    source: 'EU Funding & Tenders Portal',
  },
  {
    id: 'call-status', term: 'Open, Opens soon, Opening date passed',
    body: 'Open: the call takes proposals and its deadline is ahead. Opens soon: the source lists the call as forthcoming and its opening day is still ahead. Opening date passed: the source still lists the call as forthcoming, its opening day has passed and it states no deadline. A call the source calls forthcoming whose opening day has passed and whose deadline is ahead is shown as Open, and says so. Closing soon: open, with a deadline within 30 days.',
  },
  {
    id: 'date-only-deadline', term: 'Date only (deadline)',
    body: 'The EU portal and several national sources give the closing day and not the hour. We show the date, say that the time is not published by the source, and keep the call open through the end of that day. If the call has an hour, it is in the call text.',
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
    body: 'An EU programme that supports the European defence industry. Its calls are listed with the EDF calls in our funding list; their identifiers begin EDF-EDIP. Read the programme’s own documents for its scope and rules.',
    see: { label: 'EDF and EDIP calls', href: '/funding?programme=EDF' },
  },
  {
    id: 'digital-europe', term: 'Digital Europe', full: 'Digital Europe Programme',
    body: 'An EU programme for 2021 to 2027 that funds digital capacity such as cybersecurity and artificial intelligence. It is a civil programme, and all its calls carry our dual-use label.',
    source: 'EU Funding & Tenders Portal',
    see: { label: 'Digital Europe calls', href: '/funding?programme=DIGITAL' },
  },
  {
    id: 'cef', term: 'CEF', full: 'Connecting Europe Facility',
    body: 'An EU programme for transport, energy and digital infrastructure. We list only its military-mobility topics, which adapt transport corridors so that armed forces can use them as well as civilians, and label them dual-use.',
    source: 'EU Funding & Tenders Portal',
  },
  {
    id: 'eic', term: 'EIC', full: 'European Innovation Council',
    body: 'A part of Horizon Europe that funds innovation by start-ups and small companies. Its Accelerator is a place where a single small company can apply without a consortium; each call’s own text says who may apply. We label its calls dual-use.',
    source: 'EU Funding & Tenders Portal',
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
    id: 'horizon-europe', term: 'Horizon Europe',
    body: 'The EU research and innovation programme for 2021 to 2027. Its calls are grouped in clusters and other parts; we list the civil-security, digital, industry and space areas and the European Innovation Council, and label them dual-use. It is not a defence fund.',
    source: 'EU Funding & Tenders Portal',
    see: { label: 'Horizon Europe calls', href: '/funding?programme=HORIZON' },
  },
  {
    id: 'horizon-cluster-3', term: 'Horizon Cluster 3', full: 'Civil Security for Society (CL3)',
    body: 'The part of Horizon Europe for civil security research, such as protection against crime, border management and resilience. Its topic codes begin HORIZON-CL3. It is a civil programme: we label its calls dual-use, and the call text, not our label, says who may apply.',
    source: 'EU Funding & Tenders Portal',
  },
  {
    id: 'lot', term: 'Lot',
    body: 'A part of a procurement that can be bid for separately. Each lot can have its own scope and value, so check the lots in the original notice.',
  },
  {
    id: 'nda', term: 'NDA', full: 'Non-disclosure agreement',
    body: 'A contract in which a party promises not to share certain information. A buyer may ask suppliers to sign one before releasing the tender documents. Some TED notices carry a security-clearance or confidentiality field, which we show as present or not detected; it also holds other declarations, so read the notice.',
  },
  {
    id: 'negotiated-procedure', term: 'Negotiated procedure',
    body: 'A procedure in which the buyer negotiates the terms of the contract with the suppliers it has selected. Under Directive 2009/81/EC it can be run with or without a prior notice, and the second case is allowed only in the circumstances the directive lists.',
    source: 'Directive 2009/81/EC on EUR-Lex',
  },
  {
    id: 'notice-amendment', term: 'Notice amendment and corrigendum',
    body: 'A buyer can correct or change a published notice, for example to move a deadline or fix a value. On TED this is done with a corrigendum or a change notice; a national portal may change the notice in place. DefenceGate keeps each version it observes in which the title, buyer, country, procedure, legal basis, value, currency, publication date, deadline, product codes, source link or status changed, so the record shows what changed and when we saw it.',
    see: { label: 'How versions are kept', href: '/methodology' },
  },
  {
    id: 'notice-status', term: 'Notice status',
    body: 'Open means the notice is still taking bids; a notice with no deadline counts as open for a year after publication. Closed means its deadline has passed, or that a notice without a deadline was published over a year ago. Awarded, Cancelled and Planned are read from the type of notice the source published. Status unknown means the source does not say, so check the original.',
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
    id: 'usi', term: 'USI', full: 'Ukraine Support Instrument',
    body: 'Some calls of the EDIP programme are run under the Ukraine Support Instrument: their identifiers contain EDIP-USI and the call text names the instrument. They are listed with the EDF calls.',
    source: 'EU Funding & Tenders Portal',
  },
  {
    id: 'safe', term: 'SAFE', full: 'Security Action for Europe',
    body: 'An EU instrument, adopted in 2025, under which the EU lends money to member states for defence procurement. It is a loan instrument for governments, not a grant for companies. Suppliers meet it through the procurement of the states that borrow.',
    source: 'European Commission',
  },
  {
    id: 'security-clearance', term: 'Security clearance',
    body: 'An official decision that a company or a person may handle classified information up to a stated level. It is issued by a national security authority. A notice that requires one says so in its conditions. For TED notices from 2024 on DefenceGate shows whether the notice has a security-clearance field; that field also carries sanctions declarations and criminal-record certificates, so its presence does not mean clearance is required, and for other notices the field is not read.',
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
