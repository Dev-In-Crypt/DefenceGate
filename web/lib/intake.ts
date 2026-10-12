import { AUDIENCE_COUNTRIES } from './taxonomy';

/**
 * Allowed values for the waitlist form, defined once. The form renders from these lists and the
 * server action rejects anything that is not a member. Free text is not collected.
 */
export const SECTORS: readonly string[] = ['Metalworking and machining', 'Electronics and electrical', 'Plastics and composites', 'Textiles', 'Chemicals and materials', 'Software and IT', 'Logistics and services', 'Other manufacturing'];
export const STAFF_SIZES: readonly string[] = ['20–49', '50–249', '250–500'];
export const CERTIFICATIONS: readonly string[] = ['ISO 9001', 'EN 9100 / AS9100', 'AQAP 2110', 'ISO 27001', 'None yet'];

export const EMAIL_MAX_LENGTH = 254;
/** Upper bound on the summed length of every submitted value; the allow-lists keep real input far below it. */
const TOTAL_MAX_LENGTH = 600;

// Local part up to 64 characters of RFC 5322 atext, then a dotted domain of LDH labels and an alphabetic TLD.
const EMAIL_RE = /^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]{1,64}@(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,24}$/;

export type IntakeField = 'email' | 'country' | 'sector' | 'staff' | 'certifications' | 'form';
export type IntakeErrors = Partial<Record<IntakeField, string>>;

/** Strict validation of the waitlist form. An empty result means the input is valid. */
export function validateIntake(form: FormData): IntakeErrors {
  let malformed = false;
  const read = (v: FormDataEntryValue | null): string => {
    if (v === null) return '';
    if (typeof v !== 'string') { malformed = true; return ''; } // a file upload is never expected
    return v;
  };
  const email = read(form.get('email'));
  const country = read(form.get('country'));
  const sector = read(form.get('sector'));
  const staff = read(form.get('staff'));
  const certs = form.getAll('certifications').map(read);

  const total = [email, country, sector, staff, ...certs].reduce((n, s) => n + s.length, 0);
  if (malformed || total > TOTAL_MAX_LENGTH) return { form: 'We could not read the form. Reload the page and try again.' };

  const errors: IntakeErrors = {};
  const e = email.trim();
  if (e.length > EMAIL_MAX_LENGTH || !EMAIL_RE.test(e) || e.includes('..')) {
    errors.email = 'Enter a work email address, for example name@company.pl';
  }
  if (!AUDIENCE_COUNTRIES.includes(country)) errors.country = 'Choose the country your company is based in';
  if (sector !== '' && !SECTORS.includes(sector)) errors.sector = 'Choose a sector from the list';
  if (!STAFF_SIZES.includes(staff)) errors.staff = 'Choose a staff size';
  if (
    certs.length > CERTIFICATIONS.length ||
    new Set(certs).size !== certs.length ||
    certs.some((c) => !CERTIFICATIONS.includes(c)) ||
    (certs.includes('None yet') && certs.length > 1)
  ) {
    errors.certifications = 'Choose from the listed certifications';
  }
  return errors;
}
