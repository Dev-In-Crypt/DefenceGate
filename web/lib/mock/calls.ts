import raw from './calls.json';
import { sourceById } from './sources';
import { deadlineState, now } from '../deadline';
import { PROGRAMMES } from '../taxonomy';
import type { Call, CallFilters, CallStatus, CountryCode, CurrencyCode, EligibilityItem, Paginated, ProgrammeCode, Regime, RuleOutcome, RulesApply, WhoMayApply } from '../types';
import { DEFAULT_CURRENCY, DEFAULT_PAGE_SIZE, defaultCallSort } from '../filters';
import { parseQuery } from '../text-search';

interface RawCall {
  slug: string; programme: ProgrammeCode; programmeName?: string; callId: string | null; topicId: string;
  title: string; titleLanguage?: string; originalTitle?: string; originalLanguage?: string;
  regime: Regime; country: CountryCode; issuer?: string;
  opening: string | null; deadline: string | null;
  budget: [number, CurrencyCode] | null; budgetScope?: 'call' | 'topic';
  actionType: string | null; fundingRate: string | null; scope: string[];
  sourceId: string; retrievedAt: string; publishedAt?: string; firstSeenAt?: string;
  eligibility?: EligibilityItem[]; conditionsText?: string; cascade?: boolean; ukraine?: boolean;
  /** The EU portal's SME flag (or a national call whose applicants name SMEs): `whoMayApply` is then `companies`. */
  forSmes?: boolean;
  /** WP-92: who may apply as the call document states it (backend `call.who_may_apply_doc`), and its SME-only flag. */
  whoDoc?: WhoMayApply; smeOnly?: boolean;
  /** WP-92: the commercial summary of the topic description (detail only). */
  fundsSummary?: string;
}
const data = raw as unknown as { eligibility: Record<string, EligibilityItem[]>; calls: RawCall[] };

const FIRST_SEEN = '2026-09-01T06:00:00Z';

const EDF_CATEGORIES = new Set(['GROUND', 'CYBER', 'SPACE', 'NAVAL', 'AIR', 'UWW', 'SENS', 'C4ISR', 'MCBRN', 'DIGIT', 'ENERENV', 'MATCOMP', 'PROTMOB', 'SIMTRAIN', 'DIS', 'SME', 'SMERO', 'AIRDEF', 'DS']);

/** The area of the API's `partnerArea` (backend/dgate/partners.py `area_label`) for the demo calls: EDF category, or Horizon cluster and destination. */
function mockPartnerArea(topic: string): string | null {
  const t = topic.toUpperCase().split('-');
  if (t[0] === 'EDF') {
    const c = t.slice(1).find((x) => EDF_CATEGORIES.has(x));
    return c ? `EDF capability category ${c}` : 'all projects of the European Defence Fund';
  }
  const year = t.findIndex((x, i) => i >= 2 && /^20\d\d$/.test(x));
  if (t[0] !== 'HORIZON' || year < 0) return null;
  const rest = t.slice(year + 1);
  if (rest.length > 1 && /^\d{2}$/.test(rest[0]) && /^[A-Z]+$/.test(rest[1])) rest.shift();
  const family = t.slice(1, year).join('-');
  return /^[A-Z]+$/.test(rest[0] ?? '') ? `Horizon Europe, ${family}, destination ${rest[0]}` : `Horizon Europe, ${family}`;
}

/**
 * Who may apply, as the API's `WHO_MAY_APPLY` reads it (backend/dgate/funding.py): the EDIP actions of common procurement, support for
 * SEAPs and preparation of projects of common interest are for public bodies; any other call of the defence fund or EDIP, and a call
 * flagged for SMEs, is open to companies; anything else says nothing.
 */
export function mockWho(programme: string, topic: string, forSmes = false): WhoMayApply | null {
  const t = `-${topic.toUpperCase()}-`;
  if (['EDF', 'EDIP', 'EDIP-USI'].includes(programme)) {
    if (t.includes('-EDIP-') && (t.includes('-CPA-') || (t.includes('-SA-') && t.includes('-SEAP-')) || (t.includes('-CSA-') && t.includes('-PREP-')))) return 'public';
    return 'companies';
  }
  return forSmes ? 'companies' : null;
}

/** Mirrors the API: ids are 1-based positions, slug is "<id>-<words>", conditionsText is detail-only. */
function toCall(r: RawCall, index: number, ref: Date, detail: boolean): Call {
  const src = sourceById(r.sourceId);
  const id = String(index + 1);
  const eligKey = r.programme === 'NATIONAL' ? `NATIONAL-${r.country}` : r.programme;
  const closed = r.deadline !== null && deadlineState(r.deadline, ref) === 'closed';
  const forthcoming = !closed && r.opening !== null && new Date(r.opening).getTime() > ref.getTime();
  const status: CallStatus = closed ? 'closed' : forthcoming ? 'forthcoming' : 'open';
  return {
    id, slug: `${id}-${r.slug}`, programme: r.programme,
    programmeName: r.programmeName ?? PROGRAMMES[r.programme].name,
    // The issuing body of a national call, otherwise the Commission (backend/dgate/funding.py funder_of).
    funder: r.issuer ?? (r.programme === 'NATIONAL' ? (r.programmeName ?? PROGRAMMES[r.programme].name) : 'European Commission'),
    callId: r.callId, topicId: r.topicId,
    title: r.title, titleLanguage: r.titleLanguage ?? 'en',
    originalTitle: r.originalTitle ?? null, originalLanguage: r.originalLanguage ?? null,
    regime: r.regime, funderCountry: r.country, issuer: r.issuer ?? null,
    status, sourceStatus: status, openingDate: r.opening, deadline: r.deadline,
    budget: r.budget ? { amount: r.budget[0], currency: r.budget[1] } : null,
    budgetScope: r.budget ? (r.budgetScope ?? 'topic') : null,
    // The API's reason for a call with no budget (backend/dgate/funding.py budget_note).
    budgetNote: r.budget ? null : { reason: 'source_none', short: 'The source states no budget', text: 'The source states no budget for this call.' },
    actionType: r.actionType, fundingRate: r.fundingRate, scope: r.scope,
    eligibility: r.eligibility ?? data.eligibility[eligKey] ?? [],
    cascade: r.cascade ?? null,
    openToUkraine: r.ukraine ?? null,
    // WP-92: the call document's answer first, the programme rules after (backend funding.WHO_MAY_APPLY)
    whoMayApply: r.whoDoc ?? mockWho(r.programme, r.topicId, r.forSmes),
    smeOnly: r.smeOnly ?? null,
    publishedAt: r.publishedAt ?? null,
    firstSeenAt: r.firstSeenAt ?? FIRST_SEEN, lastSeenAt: r.retrievedAt,
    source: {
      sourceId: src.id, sourceName: src.name, url: src.url ? `${src.url}/${r.topicId.toLowerCase()}` : null,
      retrievedAt: r.retrievedAt, licence: src.licence, attribution: src.attribution,
    },
    ...(detail && r.conditionsText ? { conditionsText: r.conditionsText } : {}),
    ...(detail ? { fundsSummary: r.fundsSummary ?? null } : {}),
    ...(detail ? { partnerArea: mockPartnerArea(r.topicId) } : {}),
    ...(detail ? mockDetail(r) : {}),
  };
}

/** The detail-only fields the demo shows: how the Ukraine flag was decided, and the rules block of an EDF call. */
function mockDetail(r: RawCall): Partial<Call> {
  const out: Partial<Call> = {};
  if (r.ukraine !== undefined) {
    out.ukraineBasis = { reason: 'call_document', evidence: 'non-EU countries: − Ukraine' };
  }
  if (r.topicId === 'EDF-2026-DA-MATCOMP-AMSP') {
    // The demo call whose rules were read: the contradiction of call 193 (no consortium, and four countries), a general-annex quote with a
    // footnote number glued to a word, and a country list. e2e/ux.spec.ts reads these.
    const fact = (value: unknown, quote: string, note: string | null = null) => ({ value, note, quote, confidence: 1, scope: 'call_document' as const });
    out.documentEligibility = {
      documentUrl: null, extractedAt: '2026-10-17T10:00:00Z', basis: 'call_document', sources: [],
      facts: {
        eligible_countries: fact('Legal entities established in EU Member States', 'Applicants must be established in an EU Member State.'),
        consortium_required: fact(false, 'A single applicant may apply only if it is a SEAP.', 'A single applicant only if it is a SEAP.'),
        min_entities: fact(1, 'At least one legal entity.'),
        min_countries: fact(4, 'Otherwise entities from at least four countries.'),
        sme_only: fact(false, 'Small mid-caps up to 499 staff may apply under Horizon Europe202 rules.'),
      },
    };
  }
  // The regimes with no rules encoded (backend/dgate/regime.py): the block names the regime and says so.
  const NOT_ENCODED: Partial<Record<ProgrammeCode, { code: string; name: string; why: string }>> = {
    HORIZON: { code: 'HORIZON', name: 'Horizon Europe', why: 'A Horizon Europe call: its eligibility rules are in the work programme annexes and the topic, and no Horizon rules are encoded here.' },
    DIGITAL: { code: 'DIGITAL', name: 'Digital Europe Programme', why: 'A Digital Europe call: its rules are in the call document, and none are encoded here.' },
    NATIONAL: { code: 'NATIONAL', name: 'National programme', why: 'A national call: its rules are the national funder’s, and none are encoded here.' },
  };
  const regime = NOT_ENCODED[r.programme];
  if (regime) out.rulesApply = { regime, encoded: false, rules: [], alsoRead: null, notice: 'Indicative, not legal advice. The call text and the contracting authority decide.' };
  // Horizon topic 7 stands for a call whose rules have not been read (a "Can you apply?" panel exists); topic 8 for the long source texts of WP-56.
  if (r.topicId === 'HORIZON-CL3-2026-INFRA-01-02') {
    out.eligibilityState = 'not_read';
    out.eligibilitySources = [];
    out.eligibility = [{ label: 'Decision expected', value: '2026-12-15' }, { label: 'Project start', value: '2027-01-04 to 2027-01-11' }];
  }
  if (r.topicId === 'HORIZON-CL4-2026-MAT-03-11') {
    const countries = Array.from({ length: 120 }, (_, i) => `Country${String(i).padStart(3, "0")}`).join('; ');
    out.whoCanApply = [
      { label: 'Eligible countries', value: `Participating States are ${countries}.` },
      { label: 'Other eligibility conditions', value: 'Described in section 6 of the call document.' },
      { label: 'Applicants', value: 'Described in section 6 of the call document.' },
    ];
    out.conditionsText = Array.from({ length: 80 }, (_, i) => `Condition ${i} of the call text is published by the source.`).join(' ');
  }
  // the EDIP topics the portal files under the EDF (the demo's other EDIP calls stand for the programme's own, with no block)
  if (r.topicId.startsWith('EDF-EDIP-')) out.rulesApply = mockEdipRules(r.programme === 'EDIP-USI' ? 'EDIP-USI' : 'EDIP', r.topicId);
  if (r.programme === 'EDF') {
    out.rulesApply = {
      regime: { code: 'EDF', name: 'European Defence Fund', why: 'The topic code starts with EDF- and the programme is the EDF.' },
      encoded: true, action: null,
      programme: { code: 'EDF', name: 'European Defence Fund', legalBasis: 'Regulation (EU) 2021/697, as amended by Regulation (EU) 2025/2653' },
      rules: [{
        rule: 'EDF-ESTABLISH', title: 'Established in the Union or an associated country', kind: 'establishment', requirement: 'REQ-EDF-ELIG',
        caveat: 'For an applicant established in Ukraine this is conditional on the EU-Ukraine association agreement, which is not confirmed: the EDF call documents say participation of entities established in Ukraine is pending its signature.',
        source: { url: 'http://data.europa.eu/eli/reg/2021/697/oj', ref: 'Regulation (EU) 2021/697, Article 9(1)', origin: 'primary', verificationStatus: 'V', lastReviewed: '2026-10-18',
          text: '[Regulation (EU) 2021/697, Article 9(1)] Recipients and subcontractors involved in an action shall be established in the Union or in an associated country.' },
      }],
      alsoRead: null,
      notice: 'Indicative, not legal advice. The call text and the contracting authority decide.',
      byCountry: {
        EU: [LEGAL('EDF'), o('EDF-ESTABLISH', 'Established in the Union or an associated country', 'met', [], 'Your company is established in an EU Member State or an EEA EFTA state. These are the Union and an associated country of the EDF.'), MGMT('EDF', 'an associated country')],
        EEA_EFTA: [LEGAL('EDF'), o('EDF-ESTABLISH', 'Established in the Union or an associated country', 'met', [], 'Your company is established in an EU Member State or an EEA EFTA state. These are the Union and an associated country of the EDF.'), MGMT('EDF', 'an associated country')],
        UA: [LEGAL('EDF'), o('EDF-ESTABLISH', 'Established in the Union or an associated country', 'conditional', [], 'Your company is established in Ukraine. Treat your participation as conditional on the association agreement, not confirmed.'), MGMT('EDF', 'an associated country')],
        OTHER: [LEGAL('EDF'), o('EDF-ESTABLISH', 'Established in the Union or an associated country', 'not_met', [], 'Your company is established outside the EU and the EEA EFTA states, and not in Ukraine. EDF recipients must be established in the Union or in an associated country.'), MGMT('EDF', 'an associated country')],
      },
      forCompany: [],
    };
  }
  return out;
}

const o = (rule: string, title: string, outcome: RuleOutcome['outcome'], asks: string[], reason: string): RuleOutcome => ({ rule, title, outcome, asks, reason });
const LEGAL = (p: string) => o(`${p}-LEGAL-ENTITY`, 'Legal entity: a legal person, or an entity without legal personality that is accepted', 'unknown', ['legal_form'], 'Answer the questions that are missing to see whether this applies to you.');
const MGMT = (p: string, where: string) => o(`${p}-EXEC-MGMT`, `Executive management in the Union or ${where}`, 'unknown', ['executive_management_country'], 'Answer the questions that are missing to see whether this applies to you.');

/** The rules block of the demo's EDIP and Ukraine Support Instrument calls, as backend/dgate/rules_apply.py builds it from the seed (WP-91). */
function mockEdipRules(programme: 'EDIP' | 'EDIP-USI', topic: string): RulesApply {
  const usi = programme === 'EDIP-USI';
  const est = (outcome: RuleOutcome['outcome'], reason: string) => usi
    ? o('USI-ESTABLISH', 'Established in the Union or in Ukraine', outcome, [], reason)
    : o('EDIP-ESTABLISH', 'Established in the Union or an associated country', outcome, [], reason);
  const involves = (outcome: RuleOutcome['outcome'], asks: string[]) => o('USI-INVOLVES-UA', 'The action involves Ukraine', outcome, asks,
    outcome === 'met' ? 'The action involves a legal entity established in Ukraine: your company, if it is established there.' : 'Say whether a legal entity established in Ukraine, with its executive management structure there, takes part in your planned consortium.');
  const p = usi ? 'USI' : 'EDIP';
  const where = usi ? 'in Ukraine' : 'an associated country';
  const byCountry: NonNullable<RulesApply['byCountry']> = usi ? {
    EU: [LEGAL(p), est('met', 'Your company is established in an EU Member State or in Ukraine.'), MGMT(p, where), involves('unknown', ['ua_partner'])],
    EEA_EFTA: [LEGAL(p), est('not_met', 'Your company is established outside the EU and Ukraine. EEA EFTA states are not named in this Article.'), MGMT(p, where), involves('unknown', ['ua_partner'])],
    UA: [LEGAL(p), est('met', 'Your company is established in an EU Member State or in Ukraine.'), MGMT(p, where),
      o('USI-TERRITORY', 'Not established in a non-government controlled area of Ukraine', 'unknown', ['ua_non_government_controlled_area'], 'Answer the questions that are missing to see whether this applies to you.'), involves('met', [])],
    OTHER: [LEGAL(p), est('not_met', 'Your company is established outside the EU and Ukraine.'), MGMT(p, where), involves('unknown', ['ua_partner'])],
  } : {
    EU: [LEGAL(p), est('met', 'Your company is established in an EU Member State.'), MGMT(p, where)],
    EEA_EFTA: [LEGAL(p), est('conditional', 'Your company is established in an EEA EFTA state. These count as associated countries of the Programme only if they apply the Regulation in accordance with the EEA Agreement. Check whether yours does.'), MGMT(p, where)],
    UA: [LEGAL(p), est('not_met', 'Ukraine is not an associated country of the Programme; Ukrainian companies are covered by the Ukraine Support Instrument, which has its own card.'), MGMT(p, where)],
    OTHER: [LEGAL(p), est('not_met', 'Your company is established outside the EU and the EEA EFTA states.'), MGMT(p, where)],
  };
  const cpa = topic.toUpperCase().includes('-CPA-');
  return {
    regime: usi
      ? { code: 'EDIP-USI', name: 'EDIP Ukraine Support Instrument', why: 'The topic code starts with EDF-EDIP-USI-: a call of the Ukraine Support Instrument, which the portal files under the EDF.' }
      : { code: 'EDIP', name: 'European Defence Industry Programme', why: 'The topic code starts with EDF-EDIP-P-: an EDIP call, which the portal files under the EDF.' },
    encoded: true, action: cpa ? 'common_procurement' : 'industrial_reinforcement',
    programme: { code: programme, name: usi ? 'EDIP: Ukraine Support Instrument' : 'European Defence Industry Programme (EDIP): the Programme', legalBasis: 'Regulation (EU) 2025/2643' },
    rules: [...new Map(Object.values(byCountry).flat().map((x) => [x.rule, x])).values()].map((x) => ({
      rule: x.rule, title: x.title, kind: 'establishment', requirement: null,
      source: { url: 'http://data.europa.eu/eli/reg/2025/2643/oj', ref: 'Regulation (EU) 2025/2643', text: null, origin: 'primary', verificationStatus: 'V', lastReviewed: '2026-10-18' },
    })),
    alsoRead: null, notice: 'Indicative, not legal advice. The call text and the contracting authority decide.',
    byCountry,
    forCompany: cpa ? [o('EDIP-CPA-APPLICANT', 'Who may apply: contracting authorities, international organisations, SEAPs and the EDA', 'not_met', [], 'A company or research body may not apply to a common procurement action.')] : [],
  };
}

const rawOf = (id: string): RawCall | undefined => data.calls[Number(id) - 1];

export function allCalls(ref: Date = now(), detail = false): Call[] {
  return data.calls.map((r, i) => toCall(r, i, ref, detail));
}

const time = (iso: string) => new Date(iso).getTime();

export function queryCalls(f: CallFilters, ref: Date = now()): Paginated<Call> {
  const query = f.q ? parseQuery(f.q) : undefined;
  const status = f.status ?? 'open';
  const currency = f.currency ?? DEFAULT_CURRENCY;
  /** Budget amount in the selected currency only. Amounts in other currencies are never compared with it. */
  const amountIn = (c: Call): number | null => (c.budget && c.budget.currency === currency ? c.budget.amount : null);

  let items = allCalls(ref).filter((c) => {
    if (status === 'open' && c.status !== 'open') return false;
    if (status === 'forthcoming' && c.status !== 'forthcoming') return false;
    if (status === 'open-forthcoming' && c.status !== 'open' && c.status !== 'forthcoming') return false;
    if (status === 'closed' && c.status !== 'closed') return false;
    if (status === 'closing-soon') {
      const st = deadlineState(c.deadline, ref);
      if (c.status !== 'open' || (st !== 'soon' && st !== 'urgent')) return false;
    }
    // WP-91: as the API, EDF holds every call the portal files under it (EDIP's included), EDIP its own calls and the instrument's
    if (f.programme && !f.programme.some((p) => p === c.programme || (p === 'EDF' && c.programme === 'EDIP-USI') || (p === 'EDIP' && c.programme === 'EDIP-USI'))) return false;
    // WP-109: `research` is its own answer (`researchMayApply`), as the API's RESEARCH_MAY_APPLY: the call's facts, else EDF and Horizon calls not for public bodies only
    if (f.who === 'research' ? (c.researchMayApply ?? (['EDF', 'EDIP-USI', 'HORIZON'].includes(c.programme) && c.whoMayApply !== 'public' ? true : null)) !== true
      : f.who && c.whoMayApply !== f.who) return false;
    if (f.regime && !f.regime.includes(c.regime)) return false;
    if (f.country && !f.country.includes(c.funderCountry)) return false;
    if (f.deadlineFrom || f.deadlineTo) {
      if (c.deadline === null) return false;
      if (f.deadlineFrom && time(c.deadline) < time(`${f.deadlineFrom}T00:00:00Z`)) return false;
      if (f.deadlineTo && time(c.deadline) > time(`${f.deadlineTo}T23:59:59Z`)) return false;
    }
    // The API's rule: a currency alone lists the calls that state a budget in it; a range is read in it (EUR when none is given).
    if (f.budgetMin !== undefined || f.budgetMax !== undefined || f.currency) {
      const amount = amountIn(c);
      if (amount === null) return false;
      if (f.budgetMin !== undefined && amount < f.budgetMin) return false;
      if (f.budgetMax !== undefined && amount > f.budgetMax) return false;
    }
    // the API's search text (backend/dgate/funding.py SEARCH_TEXT): the titles, the issuer, the source's topic keywords, SME where flagged
    const text = [c.title, c.originalTitle, c.issuer, ...c.scope, rawOf(c.id)?.forSmes ? 'SME' : null].filter(Boolean).join(' ');
    if (f.q && !(query && query.matches(text, [c.callId, c.topicId].filter(Boolean).join(' ')))) return false;
    return true;
  });
  // The calls with cascade funding among those that match every other filter (the API's `cascadeTotal`).
  const cascadeTotal = items.filter((c) => c.cascade === true).length;
  if (f.cascade) items = items.filter((c) => c.cascade === true);
  const ukraineTotal = items.length === 0 ? 0 : allCalls(ref).filter((c) => items.some((i) => i.id === c.id) && c.openToUkraine === true).length;
  if (f.ukraine) items = items.filter((c) => c.openToUkraine === true);

  const sort = f.sort ?? defaultCallSort(status);
  // Like the API (WP-87): the default order lists the defence calls first, then the dual-use ones, each part in its own order.
  const defenceFirst = sort === defaultCallSort(status);
  items = items.sort((a, b) => {
    if (defenceFirst && a.regime !== b.regime) return a.regime === 'dual-use' ? 1 : -1;
    // Closed calls always last; calls without a deadline after those with one.
    const closedA = a.status === 'closed', closedB = b.status === 'closed';
    if (closedA !== closedB) return closedA ? 1 : -1;
    if (sort === 'budget-desc') {
      const x = amountIn(a), y = amountIn(b);
      if ((x === null) !== (y === null)) return x === null ? 1 : -1;
      if (x !== null && y !== null && x !== y) return y - x;
      // The API's rule (WP-56): then the amounts in other currencies, one currency at a time and largest first within it, then no budget.
      if (x === null && y === null) {
        if ((a.budget === null) !== (b.budget === null)) return a.budget === null ? 1 : -1;
        if (a.budget && b.budget) {
          if (a.budget.currency !== b.budget.currency) return a.budget.currency < b.budget.currency ? -1 : 1;
          if (a.budget.amount !== b.budget.amount) return b.budget.amount - a.budget.amount;
        }
      }
    }
    const da = a.deadline, db = b.deadline;
    if ((da === null) !== (db === null)) return da === null ? 1 : -1;
    if (da === null || db === null) return 0;
    return sort === 'deadline-desc' ? time(db) - time(da) : time(da) - time(db);
  });

  const pageSize = f.pageSize ?? DEFAULT_PAGE_SIZE;
  const page = f.page ?? 1;
  return {
    items: items.slice((page - 1) * pageSize, page * pageSize), total: items.length, page, pageSize, cascadeTotal, ukraineTotal,
    search: f.q ? { terms: query?.terms ?? [], alsoSearched: query?.alsoSearched ?? [] } : null,
  };
}

/** Like the API: only the leading integer of "<id>-<words>" is looked up. */
export function findCall(slug: string, ref: Date = now()): Call | null {
  const id = /^(\d+)(?:-|$)/.exec(slug)?.[1];
  if (!id) return null;
  return allCalls(ref, true).find((c) => c.id === id) ?? null;
}
