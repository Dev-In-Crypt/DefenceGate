'use server';

import { validateIntake, type IntakeErrors } from '@/lib/intake';

export interface WaitlistState {
  /** `closed`: input was valid but sign-ups are not open. Nothing is stored or sent. */
  status: 'idle' | 'closed' | 'error';
  errors?: IntakeErrors;
  message?: string;
}

/**
 * Waitlist intake is closed until a privacy page and a backend exist.
 * The input is still validated strictly, then dropped: this action stores nothing and sends nothing.
 */
export async function joinWaitlist(_prev: WaitlistState, form: FormData): Promise<WaitlistState> {
  const errors = validateIntake(form);
  if (Object.keys(errors).length > 0) return { status: 'error', errors };
  return { status: 'closed', message: 'Sign-ups are not open yet. Nothing you entered was stored or sent.' };
}
