import type { Metadata } from 'next';
import type { Call, Tender } from './types';
import { safeHttpUrl } from './safe-url';
import { DESCRIPTION_MAX, TITLE_MAX, titleWithRef, trimAtPhrase } from './seo-trim';
import { displayName } from './display-name';
import { BUYER_COUNTRIES, COUNTRIES, countryName, cpvLabel } from './taxonomy';

export const SITE = {
  name: 'DefenceGate',
  url: process.env.NEXT_PUBLIC_SITE_URL || 'https://defencegatehub.com',
  tagline: 'Your way into European defence supply chains.',
} as const;

/**
 * The metadata of the site's 404 (app/not-found.tsx). A page that answers `notFound()` for one of its queries returns this
 * from its generateMetadata as well: Next resolves the page's metadata on its own, so the tab otherwise keeps the page's
 * title over the 404 body (WP-116: "/suppliers?group=defence" was titled "Defence supplier map").
 */
export const NOT_FOUND_META: Metadata = {
  title: 'Page not found',
  description: 'This address is not a page of DefenceGate. Browse defence tenders, buyers and funding calls from here.',
  robots: { index: false, follow: true },
};

/** Minimum content rules: thin pages render robots noindex. */
export const MIN_LIST_ITEMS = 3;

/**
 * A call needs a source URL and a title, and at least one of: structured eligibility, a deadline, an opening date.
 * (Several sources publish no structured eligibility, so it is not required.)
 */
export function meetsMinimumContent(entity: Call | { items: unknown[] }): boolean {
  if ('items' in entity) return entity.items.length >= MIN_LIST_ITEMS;
  return Boolean(
    safeHttpUrl(entity.source.url) && entity.title &&
    (entity.eligibility.length >= 1 || entity.deadline !== null || entity.openingDate !== null),
  );
}

/** A tender needs a source URL, a title and one of: a deadline, a publication date, a stated value. */
export function tenderMeetsMinimumContent(t: Tender): boolean {
  return Boolean(safeHttpUrl(t.source.url) && t.title && (t.deadline !== null || t.publishedAt !== null || t.estimatedValue !== null));
}

export function absoluteUrl(path: string): string {
  return new URL(path, SITE.url).toString();
}

export function buildMetadata({ title: fullTitle, description: fullDescription, path, noindex = false }: { title: string; description: string; path: string; noindex?: boolean }): Metadata {
  const url = absoluteUrl(path);
  // The one place the length rule lives: a title with the site template fits 60 characters, a description 160 (lib/seo-trim.ts).
  const title = trimAtPhrase(fullTitle, TITLE_MAX, 12);
  const description = trimAtPhrase(fullDescription, DESCRIPTION_MAX, 40, '.');
  return {
    title,
    description,
    alternates: { canonical: url },
    robots: noindex ? { index: false, follow: true } : { index: true, follow: true },
    openGraph: { type: 'website', siteName: SITE.name, title, description, url, locale: 'en_GB' },
    // No image is published, so the card is the plain one (a large-image card without an image is a broken preview).
    twitter: { card: 'summary', title, description },
  };
}

/**
 * The title of a list view (WCAG 2.4.2: a filtered or later page is not announced as the same page). The list's own title on its
 * unfiltered first page; otherwise what the view is, short first so the trim of `buildMetadata` keeps it: "Tenders in Germany",
 * "Tenders, page 3", "Funding calls (filtered), page 2: “drone”". `filters` is the list's count of active filters (country and
 * search included); a sort is not a filter.
 */
export function listViewTitle(full: string, short: string, v: { page?: number; countries?: readonly string[]; q?: string; filters?: number }): string {
  const page = v.page ?? 1;
  // A code with no name ("?country=XX") is no country to put in a title: the view is then only "(filtered)".
  const countries = (v.countries ?? []).filter((c) => c && countryName(c) !== c);
  const q = v.q?.trim();
  const others = (v.filters ?? 0) - (countries.length > 0 ? 1 : 0) - (q ? 1 : 0);
  if (page <= 1 && countries.length === 0 && !q && others <= 0) return full;
  const where = countries.length === 0 ? ''
    : countries.length <= 2 ? ` in ${countries.map(countryName).join(' and ')}` : ` in ${countries.length} countries`;
  return `${short}${where}${others > 0 ? ' (filtered)' : ''}${page > 1 ? `, page ${page}` : ''}${q ? `: “${q}”` : ''}`;
}

/** The countries a TED title can open with: in English, and in the languages of the notices (eForms writes the prefix in the notice's language). */
const PLACES = new Set([...Object.values(COUNTRIES), ...Object.values(BUYER_COUNTRIES), 'Czech Republic',
  'Polska', 'Deutschland', 'España', 'România', 'Česko', 'Česká republika', 'Slovensko', 'Magyarország', 'Sverige', 'Suomi', 'Nederland',
  'België', 'Belgique', 'Lietuva', 'Latvija', 'Eesti', 'Italia', 'Danmark', 'Norge', 'Ελλάδα', 'България', 'Hrvatska', 'Slovenija',
  'Österreich', 'Éire', 'Κύπρος', 'Suisse', 'Schweiz', 'Svizzera', 'Ísland'].map((n) => n.toLowerCase()));

/**
 * WP-130: what a tender title says is bought, without the place TED puts first: "France-Toulon: Microwave tubes and equipment" (the
 * older English titles) and "Italy – Individual and support equipment – <the buyer's title>" (eForms, also in the notice's language:
 * "Polska – Pojazdy wojskowe …"). A title without such a prefix is returned as it is; one that is only the place gives ''.
 */
export function tenderSubject(title: string, country?: string | null): string {
  const s = title.trim();
  const place = (w: string) => PLACES.has(w.trim().toLowerCase()) || (!!country && w.trim().toLowerCase() === countryName(country).toLowerCase());
  const colon = s.indexOf(':');
  if (colon > 0 && place(s.slice(0, colon).split('-')[0])) return s.slice(colon + 1).trim();
  if (!s.includes(':') && /^[^\s-]+(?:\s[^\s-]+)?-\S+$/.test(s) && place(s.split('-')[0])) return '';
  const head = s.split(/\s[–—-]\s/)[0];
  return head !== s && place(head) ? s.slice(head.length).replace(/^\s[–—-]\s/, '').trim() : s;
}

/**
 * WP-130 (r7 audit: 2 of 3 sampled tender pages were titled "France-Toulon · DefenceGate", the notice number always cut away): a tender
 * page's title is its subject (else its main product code's label, else its buyer) and its notice number, within the title limit.
 */
export function tenderTitle(t: Pick<Tender, 'title' | 'noticeId' | 'country' | 'cpv' | 'buyerName'>, lead = ''): string {
  const subject = tenderSubject(displayName(t.title), t.country) || (t.cpv && cpvLabel(t.cpv)?.label) || displayName(t.buyerName, 'title');
  return titleWithRef(`${lead}${subject}`, t.noticeId);
}

/** `lang`: the language of the label when it is not English (a notice title). No `href`: a menu group with no page of its own. */
export interface Crumb { label: string; href?: string; lang?: string }

/**
 * WP-130: a crumb that is a link: it has an address, and no later crumb has the same one ("Companies" and "Won contracts" both led to
 * /suppliers). The others are plain text on the page and left out of the structured data.
 */
export function crumbLinks(items: readonly Crumb[]): boolean[] {
  return items.map((c, i) => Boolean(c.href) && !items.slice(i + 1).some((d) => d.href === c.href));
}

export function breadcrumbJsonLd(items: Crumb[]) {
  const linked = crumbLinks(items);
  // the page itself is always the last item
  const kept = items.filter((_, i) => linked[i] || i === items.length - 1).filter((c) => c.href);
  return {
    '@context': 'https://schema.org', '@type': 'BreadcrumbList',
    itemListElement: kept.map((c, i) => ({ '@type': 'ListItem', position: i + 1, name: c.label, item: absoluteUrl(c.href!) })),
  };
}

/** WP-130: who publishes the site's articles (the Organization of the homepage, with its logo), for `author` and `publisher`. */
export const PUBLISHER = { '@type': 'Organization', name: SITE.name, url: SITE.url, logo: { '@type': 'ImageObject', url: absoluteUrl('/brand/app-icon.svg') } } as const;

export function callJsonLd(call: Call) {
  const basedOn = safeHttpUrl(call.source.url);
  return {
    '@context': 'https://schema.org', '@type': 'MonetaryGrant',
    name: call.title, inLanguage: call.titleLanguage, identifier: call.topicId, url: absoluteUrl(`/funding/${call.slug}`),
    funder: { '@type': 'Organization', name: call.funder },
    ...(call.budget ? { amount: { '@type': 'MonetaryAmount', currency: call.budget.currency, value: call.budget.amount } } : {}),
    ...(basedOn ? { isBasedOn: basedOn } : {}),
    sdDatePublished: call.source.retrievedAt,
  };
}

export function organizationJsonLd() {
  return { '@context': 'https://schema.org', '@type': 'Organization', name: SITE.name, url: SITE.url, logo: absoluteUrl('/brand/app-icon.svg') };
}

export function faqJsonLd(items: { q: string; a: string }[]) {
  return {
    '@context': 'https://schema.org', '@type': 'FAQPage',
    mainEntity: items.map((i) => ({ '@type': 'Question', name: i.q, acceptedAnswer: { '@type': 'Answer', text: i.a } })),
  };
}
