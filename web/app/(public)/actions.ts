'use server';

export interface WaitlistState {
  status: 'idle' | 'success' | 'error';
  errors?: Partial<Record<'email' | 'country' | 'staff' | 'consent', string>>;
}

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

/** Waitlist + company profile intake. Replace the TODO with the real API call (POST /v1/waitlist). */
export async function joinWaitlist(_prev: WaitlistState, form: FormData): Promise<WaitlistState> {
  const email = String(form.get('email') ?? '').trim();
  const country = String(form.get('country') ?? '');
  const staff = String(form.get('staff') ?? '');
  const errors: WaitlistState['errors'] = {};
  if (!EMAIL_RE.test(email)) errors.email = 'Enter a work email address, for example name@company.pl';
  if (!country) errors.country = 'Choose the country your company is based in';
  if (!staff) errors.staff = 'Choose a staff size';
  if (form.get('consent') !== 'on') errors.consent = 'Please confirm to continue';
  if (Object.keys(errors).length) return { status: 'error', errors };
  // TODO: POST to the API. Store company profile only; never display it publicly.
  return { status: 'success' };
}
