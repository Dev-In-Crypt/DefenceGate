/**
 * WP-67: the supplier roadmap. A red / amber / green list, one line per requirement, built from the engine's answer (`POST
 * /v1/readiness/assess`) and the stored profile only. Nothing is decided here that the engine did not say: the colour is read from the
 * outcomes of the rules that name the requirement, the order is the engine's roadmap order (its prerequisite graph), and the cost and the
 * time are the requirement's one statement (`costStatement`, WP-89: the roadmap and the requirement pages print the same words; WP-67
 * printed a figure only for a primary source, so the report said "Not stated in a primary source" where the roadmap said "Free").
 * lib/wp67.check.ts runs it on the three sample companies.
 */
import { CERTIFICATES, REGISTRATIONS, type Profile } from './profile';
import { NOT_STATED, costStatement, joinWords, programmeName, timeStatement } from './readiness';
import type { Assessment, ProgrammeAssessment, RSource, RoadmapStep, RuleResult } from './readiness-types';

export type Rag = 'red' | 'amber' | 'green';
export const RAG_WORD: Record<Rag, string> = { red: 'Needed now', amber: 'Depends', green: 'In place' };
/** What a line without a requirement (a rule, a specialist's question) says for its cost and time. */
export const NO_FIGURE = NOT_STATED;

export interface RoadmapItem {
  /** A requirement code (REQ-RID), else the code of a rule or of a consultant flag. */
  key: string;
  name: string;
  rag: Rag;
  /** Why this colour, in a few words. */
  status: string;
  /** The reason of the rule that decided the colour, in the engine's words. */
  reason: string | null;
  neededFor: string[];
  /** The items of the list that come first (prerequisites). */
  after: string[];
  /** Null for what is in place. */
  cost: string | null;
  /** "vendor range, not a benchmark" beside a vendor's figure (the roadmap's label). */
  costLabel?: string | null;
  time: string | null;
  issuers: string[];
  /** What the step involves beyond cost and time (the PECAL chicken-and-egg). */
  note: string | null;
  consultant: string[];
  asks: string[];
  source: RSource | null;
  /** The requirement, for the link to its page; null for a rule or a flag. */
  requirement: string | null;
}

export interface SupplierRoadmap {
  items: RoadmapItem[];
  counts: Record<Rag, number>;
  specialists: number;
  summary: string;
}

type Entry = { r: RuleResult; a: ProgrammeAssessment };
const HOLDINGS = [...CERTIFICATES, ...REGISTRATIONS];
const uniq = <T,>(xs: T[]): T[] => [...new Set(xs)];
const n = (k: number, one: string, many: string) => `${k} ${k === 1 ? one : many}`;

function colour(entries: Entry[], step: RoadmapStep | undefined, held: boolean): { rag: Rag; status: string; decider: Entry | null } {
  if (held) return { rag: 'green', status: 'In place: you hold it.', decider: entries.find((e) => e.r.outcome === 'met') ?? entries[0] ?? null };
  const met = entries.filter((e) => e.r.outcome === 'met');
  if (met.length > 0 && entries.every((e) => e.r.outcome === 'met' || e.r.outcome === 'info')) return { rag: 'green', status: 'In place on your answers.', decider: met[0] };
  // a rule that sets a condition before the requirement can be obtained (Spain's NCAGE needs a justified need) outweighs "to obtain"
  const cond = entries.find((e) => e.r.outcome === 'conditional');
  if (cond) return { rag: 'amber', status: 'A condition comes first.', decider: cond };
  // the engine's rule (WP-73): a rule binds unless it is only recommended (a 'conditional' one binds where it applies: Spain's NCAGE with a justified need)
  const missing = entries.find((e) => e.r.outcome === 'not_met' || (e.r.outcome === 'to_obtain' && e.r.obligation !== 'recommended' && e.a.kind !== 'programme'));
  if (step?.optional) return { rag: 'amber', status: `Only ${step.when ?? 'when a contract names it'}.`, decider: missing ?? entries[0] ?? null };
  if (missing) return { rag: 'red', status: 'Missing, and needed for what you said you do.', decider: missing };
  // WP-73: a PIC the supplier page did not ask about is "unknown", not "to obtain"; only funding programmes read it, so it says so too
  const toObtain = entries.filter((e) => e.r.outcome === 'to_obtain');
  const open = entries.filter((e) => e.r.outcome === 'unknown');
  const funding = toObtain.length > 0 ? toObtain : open.length > 0 && entries.every((e) => e.a.kind === 'programme' || e.r.outcome === 'info') ? open : [];
  if (funding.length > 0) return { rag: 'amber', status: `Only if you apply for EU funding (${joinWords(uniq(funding.map((e) => programmeName(e.a.programme))))}).`, decider: funding[0] };
  const unknown = entries.find((e) => e.r.outcome === 'unknown');
  return { rag: 'amber', status: unknown ? 'Needs an answer.' : 'Depends on the contract.', decider: unknown ?? entries[0] ?? null };
}

/** `names`: requirement names by code, for what is held and is not a roadmap step (the step carries its own name). */
export function supplierRoadmap(result: Assessment, profile: Profile, names: Record<string, string> = {}): SupplierRoadmap {
  const all = [...result.assessments, ...result.general];
  const steps = new Map(result.roadmap.steps.map((s) => [s.code, s]));
  const byReq = new Map<string, Entry[]>();
  for (const a of all) for (const r of a.rules) {
    if (r.outcome === 'not_applicable' || !r.requirement) continue;
    byReq.set(r.requirement, [...(byReq.get(r.requirement) ?? []), { r, a }]);
  }
  const heldCodes = Object.entries(profile.statuses).filter(([, s]) => s === 'held').map(([c]) => c);
  const codes = uniq([...heldCodes, ...result.roadmap.steps.map((s) => s.code), ...byReq.keys()]);

  const preName = new Map(result.roadmap.steps.flatMap((s) => s.prerequisites.map((p) => [p.code, p.name] as const)));
  const items: RoadmapItem[] = [];
  const covered = new Set<string>();
  for (const code of codes) {
    const entries = byReq.get(code) ?? [];
    const step = steps.get(code);
    const held = heldCodes.includes(code);
    // a requirement that only some rule mentions for information (AQAP 2110 for an EDF applicant) is not on the list
    if (!held && !step && entries.every((e) => e.r.outcome === 'info')) continue;
    const { rag, status, decider } = colour(entries, step, held);
    entries.forEach((e) => covered.add(e.r.rule));
    items.push({
      key: code, requirement: code, rag, status,
      name: step?.name ?? names[code] ?? preName.get(code) ?? HOLDINGS.find((h) => h.code === code)?.label ?? code,
      reason: rag === 'green' && held ? null : decider?.r.reason ?? step?.summary ?? null,
      neededFor: uniq(entries.filter((e) => e.r.outcome !== 'info').map((e) => programmeName(e.a.programme))),
      after: (step?.prerequisites ?? []).filter((p) => p.relation === 'before').map((p) => p.code),
      cost: rag === 'green' ? null : costStatement(step?.cost ?? null),
      costLabel: rag === 'green' ? null : step?.cost?.label ?? null,
      time: rag === 'green' ? null : timeStatement(step?.days ?? null),
      issuers: rag === 'green' ? [] : (step?.issuers ?? []).map((i) => i.name),
      note: rag === 'green' ? null : step?.note ?? null,
      consultant: rag === 'green' ? [] : uniq(entries.map((e) => e.r.consultant).filter((c): c is string => !!c)),
      asks: rag === 'green' ? [] : uniq(entries.flatMap((e) => e.r.asks.map((q) => q.question))),
      source: decider?.r.source ?? null,
    });
  }
  // what no requirement covers: certificates no rule reads (IATF 16949), a supply-route rule that is not met (a foreign investor without
  // the authorisation), and every "consultant needed" flag of the answer that no line above carries (US components)
  for (const key of profile.supplier.held) {
    const h = HOLDINGS.find((x) => x.key === key);
    if (h) items.push({ key, requirement: null, name: h.label, rag: 'green', status: 'In place: you hold it. No rule of this check reads it.', reason: null,
      neededFor: [], after: [], cost: null, time: null, issuers: [], note: null, consultant: [], asks: [], source: null });
  }
  for (const a of all) for (const r of a.rules) {
    if (r.requirement || covered.has(r.rule) || a.kind === 'programme' || !(r.outcome === 'not_met' || r.consultant)) continue;
    covered.add(r.rule);
    items.push({ key: r.rule, requirement: null, name: r.title, rag: r.outcome === 'not_met' ? 'red' : 'amber',
      status: r.outcome === 'not_met' ? 'Missing, and needed for what you said you do.' : 'A specialist has to settle it.', reason: r.reason,
      neededFor: [programmeName(a.programme)], after: [], cost: NO_FIGURE, time: NO_FIGURE, issuers: [], note: null,
      consultant: r.consultant ? [r.consultant] : [], asks: r.asks.map((q) => q.question), source: r.source });
  }
  for (const f of result.consultants ?? []) {
    if (f.rule && covered.has(f.rule)) continue;
    const rule = f.rule ? all.flatMap((a) => a.rules).find((r) => r.rule === f.rule) : undefined;
    items.push({ key: f.key, requirement: null, name: f.title, rag: 'amber', status: 'A specialist has to settle it.', reason: null,
      neededFor: [], after: [], cost: NO_FIGURE, time: NO_FIGURE, issuers: [], note: null, consultant: [f.text], asks: f.asks.map((q) => q.question),
      source: rule?.source ?? null });
  }

  // order: what is in place, then what is needed now, then what depends; within each, the engine's roadmap order; and a prerequisite is
  // always placed before what needs it (ISO 9001 and the RID before PECAL), whatever its colour
  const rank: Record<Rag, number> = { green: 0, red: 1, amber: 2 };
  const pos = (i: RoadmapItem) => steps.get(i.key)?.order ?? 99;
  const sorted = items.map((it, i) => ({ it, i })).sort((x, y) => rank[x.it.rag] - rank[y.it.rag] || pos(x.it) - pos(y.it) || x.i - y.i).map((x) => x.it);
  const byKey = new Map(sorted.map((i) => [i.key, i]));
  const out: RoadmapItem[] = [];
  const place = (i: RoadmapItem) => {
    if (out.includes(i)) return;
    for (const p of i.after) { const pre = byKey.get(p); if (pre) place(pre); }
    out.push(i);
  };
  sorted.forEach(place);
  for (const i of out) i.after = i.after.map((c) => byKey.get(c)?.name ?? preName.get(c) ?? c);

  const counts: Record<Rag, number> = { red: 0, amber: 0, green: 0 };
  out.forEach((i) => { counts[i.rag] += 1; });
  const specialists = out.filter((i) => i.consultant.length > 0).length;
  const summary = [
    `${n(counts.green, 'item is', 'items are')} in place, ${n(counts.red, 'is', 'are')} needed now on your answers, and ${n(counts.amber, 'depends', 'depend')} on a contract, a condition or an answer.`,
    specialists > 0 ? `${n(specialists, 'item needs', 'items need')} a specialist.` : '',
    'Meeting these requirements does not win a contract: each buyer sets its own conditions in the tender documents.',
  ].filter(Boolean).join(' ');
  return { items: out, counts, specialists, summary };
}
