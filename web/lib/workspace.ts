import 'server-only';
/**
 * WP-157: the team workspace (Team, Consultant) and the client profiles (Consultant) of the account API
 * (backend/dgate/workspace.py). Server only, through lib/account `call` (session header, internal secret, never throws).
 */
import { cookies } from 'next/headers';
import { call } from './account';
import { isUuid } from './refs';

/** The client profile picked in the switcher. Not a secret (a UUID of the account's own workspace, checked by the API on every use). */
export const CLIENT_COOKIE = '__Host-dg_client';

export interface WorkspaceMember { id: string; email: string; role: 'owner' | 'member'; joinedAt: string; me: boolean }
export interface WorkspaceInvite { id: string; email: string; createdAt: string; expiresAt: string }
export interface WorkspaceState {
  workspace: { id: string; role: 'owner' | 'member'; active: boolean; seats: number; members: WorkspaceMember[]; invites: WorkspaceInvite[] } | null;
  canCreate: boolean;
  seats: number;
}
export interface ClientProfile { id: string; name: string; country: string | null; cpvCodes: string[]; note: string }
export interface ClientList { items: ClientProfile[]; limit: number; allowed: boolean }

const isRecord = (v: unknown): v is Record<string, unknown> => typeof v === 'object' && v !== null && !Array.isArray(v);
const text = (v: unknown, max: number): string => (typeof v === 'string' ? v.slice(0, max) : '');
const list = (v: unknown): Record<string, unknown>[] => (Array.isArray(v) ? v.filter(isRecord) : []);
const num = (v: unknown): number => (typeof v === 'number' && Number.isFinite(v) && v >= 0 ? Math.floor(v) : 0);

function toWorkspace(raw: unknown): WorkspaceState {
  if (!isRecord(raw)) throw new Error('bad workspace');
  const w = isRecord(raw.workspace) ? raw.workspace : null;
  return {
    canCreate: raw.canCreate === true,
    seats: num(raw.seats),
    workspace: w && typeof w.id === 'string' ? {
      id: w.id, role: w.role === 'owner' ? 'owner' : 'member', active: w.active === true, seats: num(w.seats),
      members: list(w.members).map((m) => ({ id: text(m.id, 36), email: text(m.email, 320), role: m.role === 'owner' ? 'owner' : 'member',
        joinedAt: text(m.joinedAt, 40), me: m.me === true })),
      invites: list(w.invites).map((i) => ({ id: text(i.id, 36), email: text(i.email, 320), createdAt: text(i.createdAt, 40), expiresAt: text(i.expiresAt, 40) })),
    } : null,
  };
}

function toClient(raw: unknown): ClientProfile {
  if (!isRecord(raw) || typeof raw.id !== 'string') throw new Error('bad client');
  return {
    id: raw.id, name: text(raw.name, 120), country: typeof raw.country === 'string' ? raw.country.slice(0, 2) : null,
    cpvCodes: Array.isArray(raw.cpvCodes) ? raw.cpvCodes.filter((c): c is string => typeof c === 'string').slice(0, 20) : [],
    note: text(raw.note, 500),
  };
}

export const getWorkspace = () => call<WorkspaceState>('/workspace', {}, toWorkspace);
export const createWorkspace = () => call<void>('/workspace', { method: 'POST' });
export const dissolveWorkspace = () => call<void>('/workspace', { method: 'DELETE' });
export const inviteMember = (email: string) => call<void>('/workspace/invites', { method: 'POST', json: { email } });
export const cancelInvite = (id: string) => call<void>(`/workspace/invites/${encodeURIComponent(id)}`, { method: 'DELETE' });
export const joinWorkspace = (token: string) => call<void>('/workspace/join', { method: 'POST', json: { token } });
export const leaveWorkspace = () => call<void>('/workspace/leave', { method: 'POST' });
export const removeMember = (id: string) => call<void>(`/workspace/members/${encodeURIComponent(id)}`, { method: 'DELETE' });

export interface ClientIn { name: string; country: string | null; cpvCodes: string[]; note: string }
export const listClients = () => call<ClientList>('/clients', {}, (raw) => {
  if (!isRecord(raw)) throw new Error('bad clients');
  return { items: list(raw.items).map(toClient), limit: num(raw.limit), allowed: raw.allowed === true };
});
export const createClient = (c: ClientIn) => call<ClientProfile>('/clients', { method: 'POST', json: c }, toClient);
export const updateClient = (id: string, c: ClientIn) => call<ClientProfile>(`/clients/${encodeURIComponent(id)}`, { method: 'PATCH', json: c }, toClient);
export const deleteClient = (id: string) => call<void>(`/clients/${encodeURIComponent(id)}`, { method: 'DELETE' });

/** The client profile picked in the switcher, when it is still one of the account's (else none). */
export async function activeClient(clients: ClientProfile[]): Promise<ClientProfile | null> {
  const v = (await cookies()).get(CLIENT_COOKIE)?.value ?? '';
  return isUuid(v) ? clients.find((c) => c.id === v) ?? null : null;
}

/** The account's client profiles and the one picked, for a page that offers them; nothing when the plan has none. */
export async function clientContext(features: readonly string[]): Promise<{ clients: ClientProfile[]; active: ClientProfile | null }> {
  if (!features.includes('client_profiles')) return { clients: [], active: null };
  const r = await listClients();
  const clients = r.ok ? r.data.items : [];
  return { clients, active: await activeClient(clients) };
}
