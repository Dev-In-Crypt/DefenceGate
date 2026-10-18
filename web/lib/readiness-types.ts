/** The shapes of the readiness API (docs/design/API_CONTRACT.md, "Readiness"). */

export type VerificationStatus = 'V' | 'S' | 'U';
export type Verdict = 'eligible' | 'obtain' | 'blocked' | 'conditional';
export type Outcome = 'met' | 'not_met' | 'to_obtain' | 'conditional' | 'unknown' | 'not_applicable' | 'info';

export interface RMoney {
  min: number | null; max: number | null; currency: string | null;
  basis: 'free' | 'vendor_range' | 'not_stated'; text: string | null;
  alt: { min: number; max: number; currency: string; text: string } | null;
  /** "vendor range, not a benchmark" for a vendor range. */
  label: string | null;
}
export interface RSpan { min: number | null; max: number | null; text: string | null; note: string | null }

export interface RSource {
  url: string; ref: string | null; text: string | null; origin: 'primary' | 'notes';
  verificationStatus: VerificationStatus; lastReviewed: string;
}

export interface RIssuer { country: string; name: string; url: string | null; notes: string | null; verificationStatus: VerificationStatus }

export interface RequirementSummary {
  code: string; name: string; category: string; kind: 'document' | 'rule'; summary: string;
  cost: RMoney | null; days: RSpan | null; mandatoryFor: string | null; programmes: string[];
  verificationStatus: VerificationStatus; lastReviewed: string; sourceUrl: string;
}

export interface RequirementRule {
  programme: string; programmeName: string; rule: string; title: string; obligation: 'mandatory' | 'conditional' | 'recommended'; kind: string;
  texts: Record<string, string>; note: string | null; source: RSource;
}

export interface RequirementDetail extends RequirementSummary {
  description: string | null; legalBasis: string | null; durationNote: string | null;
  variants: { whenHeld: string; cost: RMoney | null; days: RSpan | null; sourceText: string }[];
  extras: { without_prerequisite?: { requirement: string; text: string }; other_figures?: string[] };
  prerequisites: { code: string; name: string; relation: 'before' | 'before_or_with' }[];
  requiredBy: string[];
  issuers: RIssuer[];
  rules: RequirementRule[];
  source: RSource;
  vendorRangeLabel: string | null;
}

export interface RuleResult {
  rule: string; title: string; outcome: Outcome; reason: string; obligation: 'mandatory' | 'conditional' | 'recommended';
  kind: string; requirement: string | null; note: string | null; denominator: string | null;
  asks: { field: string; question: string }[];
  source: RSource;
}

export interface ProgrammeAssessment {
  programme: string; name: string; kind: 'programme' | 'route' | 'general'; summary: string; legalBasis: string | null;
  sourceUrl: string; verdict: Verdict; incomplete: boolean; blocking: string[]; conditions: string[]; toObtain: string[];
  counts: Record<Outcome, number>; missing: { field: string; question: string }[]; rules: RuleResult[];
}

export interface RoadmapStep {
  order: number; code: string; name: string; category: string; summary: string;
  status: 'held' | 'in_progress' | 'not_held' | 'not_applicable';
  optional: boolean; when: string | null; blockingFor: string[];
  neededFor: { programme: string; rule: string; title: string }[];
  cost: RMoney | null; days: RSpan | null; variantUsed: string | null; branchNote: string | null;
  issuers: { country: string; name: string; url: string | null; notes: string | null; status: VerificationStatus }[];
  issuerNote: string | null;
  /** Why no price is shown (the issuer in the company's country is the state itself). */
  priceNote: string | null;
  prerequisites: { code: string; name: string; relation: 'before' | 'before_or_with'; status: string; step: number | null }[];
  parallelWith: number[]; verificationStatus: VerificationStatus; lastReviewed: string; sourceUrl: string;
}

export interface RoadmapTotals {
  cost: { currency: string; min: number; max: number; steps: string[] }[];
  freeSteps: string[]; days: { min: number; max: number };
}

export interface Roadmap {
  steps: RoadmapStep[]; tracks: string[][]; totals: RoadmapTotals; totalsWithOptional: RoadmapTotals;
  unknownCost: string[]; unknownDuration: string[];
  unknownCostWithOptional: string[]; unknownDurationWithOptional: string[];
  /** What a source says is on top of a range but gives no base for: shown, never added to a total. */
  notAdded: { code: string; text: string }[];
  label: string;
}

export interface CallTiming {
  programme: string; name: string; verdict: Verdict; deadline: string | null; daysLeft: number | null;
  steps: string[]; fastestPathDays: { min: number; max: number };
  notFixable: { rule: string; title: string; reason: string }[];
  realistic: 'yes' | 'maybe' | 'no' | 'not_possible' | 'depends' | 'unknown' | 'closed'; text: string;
}

export interface Assessment {
  generatedAt: string; rulesReviewed: string;
  assessments: ProgrammeAssessment[]; general: ProgrammeAssessment[];
  roadmap: Roadmap; call: unknown; notice: string;
}
