import { Building2, GitCompare, Layers, Link2, SearchCheck, ShieldCheck } from 'lucide-react';

/**
 * The texts of "Why DefenceGate", "How it works" and the questions (WP-117: they moved from the home page to /about, unchanged; the
 * home page keeps four of the questions). One module, so both pages read the same words.
 */
export const benefits = (names: string) => [
  { icon: SearchCheck, title: 'Many portals, one list', body: `TED notices and the national portals of ${names}, in one list with one layout. Other countries appear through TED only.` },
  { icon: GitCompare, title: 'See what changed', body: 'Deadlines move and values are corrected. We keep a new version when a notice’s deadline, value, status or another main field changes, so you see what changed and when. Our archive began in September 2026.' },
  { icon: Link2, title: 'Straight to the source', body: 'Each record links to its original publication. Check it there before you act: the source is the authority, not us.' },
  { icon: ShieldCheck, title: 'Know what we cover', body: 'Every source, when it last ran and whether it met the minimum we expect are public, with the span of publication dates held. Known gaps are listed on the status page.' },
  { icon: Layers, title: 'Tenders and funding side by side', body: 'EU and national funding calls are in the same directory as the procurement notices and on one deadline calendar. They are searched separately.' },
  { icon: Building2, title: 'The buyer in context', body: 'Open a buyer to see its current and past notices in one place before you decide to bid.' },
];

export const STEPS = [
  { title: 'We collect', body: 'Public notices and funding calls are collected from the sources listed on the status page, daily; the EU research datasets monthly.' },
  { title: 'You search and filter', body: 'By country, buyer, deadline, value or keyword. Every fact is shown with its source.' },
  { title: 'You verify and act', body: 'Open the original, confirm the details there, then bid or apply. We link; the decision is yours.' },
];

export interface QA { q: string; a: string }

const ACCOUNT_ANSWER_OPEN = 'Not to browse. An account, with your e-mail address and a password, lets you save searches, follow buyers and programmes and keep a shortlist.';

/** Every question, in the order /about shows them. The account answer follows whether sign-in is open. */
export function faqItems(portals: { count: string; names: string }, accountsOpen: boolean): QA[] {
  return [
    { q: 'What is DefenceGate?', a: 'An independent information service that collects publicly published defence and dual-use procurement notices and funding calls, shows them in one directory, and keeps a version history of the changes it observes.' },
    { q: 'Is it an official source?', a: 'No. We are not affiliated with the EU, TED or any government. Every record links to the original publication, which is the authoritative text.' },
    { q: 'Where does the data come from?', a: `From TED, the national tender portals and feeds of ${portals.names}, and public funding portals. The source status page lists each one with its licence, when it last ran and the known gaps.` },
    { q: 'How current is it?', a: 'Tender sources and funding portals are collected daily (the EU research datasets monthly), not in real time. The status page shows the last run per source. Always confirm deadlines in the original notice.' },
    { q: 'Is it complete?', a: `No, and we do not claim it is. Sources can fail or publish late, national tender portals are collected for ${portals.count} countries only (the others through TED), and some history is still being loaded. A notice you need may be missing, so check the portals relevant to you.` },
    { q: 'How do you decide what counts as defence or dual-use?', a: 'Automatically, from several signals such as the legal basis, the product classification and the buyer. It can be wrong and is not a legal determination. See the methodology page.' },
    { q: 'What does the version history show?', a: 'What changed in a notice between two of our observations and when we saw it, for example a moved deadline or a corrected value. A new version is kept when the title, buyer, country, procedure, legal basis, value, currency, publication date, deadline, product codes, source link or status changes. History starts when we first saw a notice (our archive began in September 2026); earlier states are not reconstructed.' },
    { q: 'Do I need an account?', a: accountsOpen ? ACCOUNT_ANSWER_OPEN : 'Not to browse. Alerts and a personal workspace are being prepared and are not open yet.' },
    { q: 'Is it free?', a: 'Browsing the catalogue is free today. Anything beyond that will be announced with its own terms before it is offered.' },
    { q: 'Do you give legal or bidding advice?', a: 'No. This is information only. For legal, export-control or eligibility questions, ask a qualified adviser.' },
    { q: 'How do I report an error?', a: 'Use the contact route in the imprint and tell us the record and what is wrong. We check it against the source.' },
  ];
}

/** The four the home page keeps (owner, 25 Oct 2026: free? where from? how current? what counts as defence?), in that order. */
export const HOME_QUESTIONS = ['Is it free?', 'Where does the data come from?', 'How current is it?', 'How do you decide what counts as defence or dual-use?'] as const;

export const homeFaq = (all: QA[]) => HOME_QUESTIONS.map((q) => all.find((f) => f.q === q)!);
