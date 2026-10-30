'use server';

/**
 * WP-157: state changes of the team workspace and the client profiles. Server actions (Next.js checks Origin against Host), each
 * ending in a redirect with `?n=<code>` (components/account/ui.tsx NOTICES), so the forms work without JavaScript. The API checks
 * every rule (owner, seats, plan, the invited address); here the values are only shaped.
 */
import { cookies } from 'next/headers';
import { redirect } from 'next/navigation';
import { isTokenShaped, putShortlist, updateSearch, type AccountResult } from '@/lib/account';
import { parseCountry, parseCpvList, switchBack } from '@/lib/client-profile';
import { isUuid, numericRef } from '@/lib/refs';
import {
  cancelInvite, CLIENT_COOKIE, createClient, createWorkspace, deleteClient, dissolveWorkspace, inviteMember, joinWorkspace,
  leaveWorkspace, removeMember, updateClient,
} from '@/lib/workspace';
import { SHORTLIST_STATUSES } from '@/lib/account';
import type { ShortlistStatus } from '@/lib/types';

const CODES = new Set(['seats_full', 'plan_required', 'in_workspace', 'wrong_account', 'invalid_or_expired', 'already_member',
  'limit_reached', 'not_open', 'owner_only', 'owner_cannot_leave', 'invalid_email', 'rate_limited']);

function field(form: FormData, key: string, max = 256): string {
  const v = form.get(key);
  return typeof v === 'string' ? v.slice(0, max) : '';
}

/** Back to a page with the outcome; the API's own refusal code when the page has words for it. */
function back(path: string, r: AccountResult<unknown>, ok: string): never {
  if (!r.ok && r.status === 401) redirect('/auth/expired');
  const code = r.ok ? ok : CODES.has(r.error) ? r.error : r.status === 422 ? 'invalid' : 'error';
  redirect(`${path}?n=${code}`);
}

/* ---- the workspace ---- */

export async function startWorkspace(): Promise<void> {
  back('/app/team', await createWorkspace(), 'workspace_made');
}

export async function sendInvite(form: FormData): Promise<void> {
  const email = field(form, 'email', 320).trim();
  if (!email) redirect('/app/team?n=invalid_email');
  back('/app/team', await inviteMember(email), 'invited');
}

export async function withdrawInvite(form: FormData): Promise<void> {
  const id = field(form, 'id', 64);
  if (!isUuid(id)) redirect('/app/team?n=invalid');
  back('/app/team', await cancelInvite(id), 'removed');
}

export async function dropMember(form: FormData): Promise<void> {
  const id = field(form, 'id', 64);
  if (!isUuid(id)) redirect('/app/team?n=invalid');
  back('/app/team', await removeMember(id), 'removed');
}

export async function leaveTeam(): Promise<void> {
  back('/app/team', await leaveWorkspace(), 'left');
}

/** Ends the workspace; the box must be ticked (the form says what goes). */
export async function endWorkspace(form: FormData): Promise<void> {
  if (form.get('confirm') !== 'yes') redirect('/app/team?n=confirm_end');
  back('/app/team', await dissolveWorkspace(), 'workspace_ended');
}

/** The invited account accepts: the token comes from the mailed link, through the join page's form (never on a GET). */
export async function acceptInvite(form: FormData): Promise<void> {
  const token = field(form, 'token', 64);
  if (!isTokenShaped(token)) redirect('/app/team?n=invalid_or_expired');
  back('/app/team', await joinWorkspace(token), 'joined');
}

/* ---- client profiles ---- */

function clientValues(form: FormData) {
  const name = field(form, 'name', 240).trim();
  const country = parseCountry(field(form, 'country', 8));
  const cpvCodes = parseCpvList(field(form, 'cpv', 600));
  const note = field(form, 'note', 1000).trim().slice(0, 500);
  return !name || country === undefined || cpvCodes === null ? null : { name, country, cpvCodes, note };
}

export async function addClient(form: FormData): Promise<void> {
  const v = clientValues(form);
  if (!v) redirect('/app/clients?n=invalid');
  back('/app/clients', await createClient(v), 'saved');
}

export async function saveClient(form: FormData): Promise<void> {
  const id = field(form, 'id', 64);
  const v = clientValues(form);
  if (!isUuid(id) || !v) redirect('/app/clients?n=invalid');
  back('/app/clients', await updateClient(id, v), 'saved');
}

export async function removeClient(form: FormData): Promise<void> {
  const id = field(form, 'id', 64);
  if (!isUuid(id)) redirect('/app/clients?n=invalid');
  const r = await deleteClient(id);
  if (r.ok && (await cookies()).get(CLIENT_COOKIE)?.value === id) await setClientCookie('');
  back('/app/clients', r, 'removed');
}

async function setClientCookie(id: string): Promise<void> {
  (await cookies()).set(CLIENT_COOKIE, id, { httpOnly: true, secure: true, sameSite: 'lax', path: '/', maxAge: id ? 30 * 86400 : 0 });
}

/** The client switcher: the profile the searches, the shortlist and the company report work on ('' is all of them). */
export async function chooseClient(form: FormData): Promise<void> {
  const id = field(form, 'clientId', 64);
  await setClientCookie(isUuid(id) ? id : '');
  redirect(switchBack(field(form, 'back', 64)));
}

/** A saved search moved to a client profile, or off one (''). */
export async function setSearchClient(form: FormData): Promise<void> {
  const id = field(form, 'id', 64);
  const client = field(form, 'clientId', 64);
  if (!isUuid(id) || (client && !isUuid(client))) redirect('/app/searches?n=invalid');
  back('/app/searches', await updateSearch(id, { clientId: client || null }), 'saved');
}

/** A shortlist entry's status, note and client profile, from the shortlist page when the account has client profiles. */
export async function saveShortlistWithClient(form: FormData): Promise<void> {
  const kind = field(form, 'kind', 8);
  const ref = numericRef(field(form, 'ref', 64));
  const status = field(form, 'status', 16) as ShortlistStatus;
  const client = field(form, 'clientId', 64);
  if ((kind !== 'tender' && kind !== 'call') || ref === null || !SHORTLIST_STATUSES.includes(status) || (client && !isUuid(client))) {
    redirect('/app/shortlist?n=invalid');
  }
  const note = field(form, 'note', 1000).trim().slice(0, 500);
  back('/app/shortlist', await putShortlist(kind, ref, status, note, client || null), 'saved');
}
