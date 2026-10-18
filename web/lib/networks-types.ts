/**
 * Shapes of the networks API (layer 2: organisations, projects, partners), as docs/design/API_CONTRACT.md fixes them.
 * Organisation-level facts only: a name, a country, the PIC, roles, amounts, years. No person, no contact.
 */

/** An organisation as another record names it. One removed on request has no id and no slug. */
export interface OrgRef { id: string | null; slug: string | null; name: string; country: string | null }

export interface SourceNote {
  code: string; name: string; licence: string; attribution: string;
  /** When the newest finished run of this source ended; null before any run. */
  readAt: string | null; note: string;
}

export interface OrgListItem {
  id: string; slug: string; name: string; country: string;
  projects: number; coordinated: number;
  /** EUR, CORDIS only; null when the organisation took part only in EDF projects. */
  euContribution: number | null;
  firstYear: number | null; lastYear: number | null; programmes: string[];
}

export interface OrgPage {
  items: OrgListItem[];
  /** Capped at 10,000: `totalExact` is false then ("10,000+"). */
  total: number; totalExact: boolean; page: number; pageSize: number;
  meta: { updatedAt: string | null; sources: SourceNote[]; amountNote: string };
  staleAsOf?: string;
}

export interface ProgrammeFigures {
  code: string; name: string; projects: number; euContribution: number | null; firstYear: number | null; lastYear: number | null;
}

export interface OrgProfile {
  id: string; slug: string; name: string; country: string;
  pic: { value: string; method: string | null; confidence: number | null } | null;
  counts: {
    projects: number; participations: number; coordinated: number; euContribution: number | null;
    firstYear: number | null; lastYear: number | null;
  };
  programmes: ProgrammeFigures[];
  resolution: { note: string; participations: Record<string, number>; lowestConfidence: number | null };
  aliases: { total: number; items: { name: string; method: string; confidence: number | null; firstSeen: string; source: string | null }[] };
  /** How many other organisation rows were merged into this one. */
  mergedFrom: number;
  buyer: { slug: string; name: string; tenderCount: number } | null;
  sources: SourceNote[]; amountNote: string;
}

export interface FundingRow { programme: string; year: number | null; projects: number; euContribution: number | null; projectsWithoutAmount: number }
export interface OrgFunding {
  organisation: OrgRef; rows: FundingRow[];
  totals: { projects: number; euContribution: number | null }; amountNote: string;
}

export interface ProjectRef { slug: string; acronym: string | null; title: string; programme: string | null; year: number | null }

export interface PartnerRow {
  organisation: OrgRef; shared: number; firstYear: number | null; lastYear: number | null;
  programmes: string[]; projects: ProjectRef[];
}
export interface PartnerPage {
  organisation: OrgRef; items: PartnerRow[]; total: number;
  /** How many countries the partners (all pages, as filtered) are established in. */
  countries: number; page: number; pageSize: number; note: string;
}

export interface OrgProjectRow extends ProjectRef {
  role: string; contribution: number | null; status: string | null; topic: string | null; category: string | null;
  totalCost: number | null; projectEuContribution: number | null;
}
export interface OrgProjectPage { organisation: OrgRef; items: OrgProjectRow[]; total: number; page: number; pageSize: number }

export interface ProjectMember {
  organisation: OrgRef; role: string; contribution: number | null;
  resolution: { method: string; confidence: number | null };
}
export interface ProjectDetail {
  id: string; slug: string; acronym: string | null; title: string;
  programme: { code: string; name: string } | null;
  grantNumber: string | null; call: string | null; topic: string | null; actionType: string | null; category: string | null;
  callYear: number | null; status: string | null; startDate: string | null; endDate: string | null; durationMonths: number | null;
  totalCost: number | null; euContribution: number | null;
  coordinator: OrgRef | null; members: ProjectMember[]; memberCount: number; countryCount: number;
  source: { code: string; name: string; licence: string; attribution: string; url: string | null; urlLabel: string };
  factsheet: { readBy: string; readAt: string; pages: number; dropped: { kind: string; count: number; meaning: string }[]; note: string } | null;
  readAt: string | null; amountNote: string;
}
export interface ProjectHistory {
  project: { slug: string; acronym: string | null; title: string };
  firstObserved: { observedAt: string; memberCount: number; countryCount: number } | null;
  changes: { observedAt: string; added: OrgRef[]; removed: OrgRef[]; coordinatorBefore: OrgRef | null; coordinatorAfter: OrgRef | null }[];
  note: string;
}

export interface UkrainePartners {
  since: number; definition: string;
  totals: { projects: number; coordinators: number; ukrainianOrganisations: number; projectsCoordinatedFromUkraine: number };
  coordinators: {
    organisation: OrgRef; projects: number; ukrainianOrganisations: number; lastYear: number | null; programmes: string[];
    ukrainianParticipants: { organisation: OrgRef; projects: number }[]; recentProjects: ProjectRef[];
  }[];
  ukrainianOrganisations: { organisation: OrgRef; projects: number; coordinated: number; lastYear: number | null }[];
  limits: string[]; sources: SourceNote[];
}

export interface ConsortiumGaps {
  programme: string[]; topic: string | null; lacking: string; minProjects: number; projectsInArea: number;
  definition: string;
  items: { organisation: OrgRef; projects: number; partnerCountries: string[]; recentProjects: (ProjectRef & { category: string | null; countries: string[] })[] }[];
  areas: { code: string; projects: number }[];
  limits: string[]; sources: SourceNote[];
}

export interface OrgFilters {
  q?: string; country?: string[]; programme?: string[]; role?: string[]; minProjects?: number;
  sort?: 'projects' | 'name'; page?: number; pageSize?: number;
}
