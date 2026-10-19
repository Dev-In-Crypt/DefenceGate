import type { Metadata } from 'next';
import type { Call, Tender } from './types';
import { safeHttpUrl } from './safe-url';
import { DESCRIPTION_MAX, TITLE_MAX, trimAtWord } from './seo-trim';
import { countryName } from './taxonomy';

export const SITE = {
  name: 'DefenceGate',
  url: process.env.NEXT_PUBLIC_SITE_URL || 'https://defencegatehub.com',
  tagline: 'Your way into European defence supply chains.',
} as const;

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
  const title = trimAtWord(fullTitle, TITLE_MAX);
  const description = trimAtWord(fullDescription, DESCRIPTION_MAX);
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
  const countries = (v.countries ?? []).filter(Boolean);
  const q = v.q?.trim();
  const others = (v.filters ?? 0) - (countries.length > 0 ? 1 : 0) - (q ? 1 : 0);
  if (page <= 1 && countries.length === 0 && !q && others <= 0) return full;
  const where = countries.length === 0 ? ''
    : countries.length <= 2 ? ` in ${countries.map(countryName).join(' and ')}` : ` in ${countries.length} countries`;
  return `${short}${where}${others > 0 ? ' (filtered)' : ''}${page > 1 ? `, page ${page}` : ''}${q ? `: “${q}”` : ''}`;
}

/** `lang`: the language of the label when it is not English (a notice title). */
export interface Crumb { label: string; href: string; lang?: string }

export function breadcrumbJsonLd(items: Crumb[]) {
  return {
    '@context': 'https://schema.org', '@type': 'BreadcrumbList',
    itemListElement: items.map((c, i) => ({ '@type': 'ListItem', position: i + 1, name: c.label, item: absoluteUrl(c.href) })),
  };
}

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
