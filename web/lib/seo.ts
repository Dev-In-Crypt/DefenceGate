import type { Metadata } from 'next';
import type { Call } from './types';
import { PROGRAMMES, COUNTRIES } from './taxonomy';
import { safeHttpUrl } from './safe-url';

export const SITE = {
  name: 'DefenceGate',
  url: process.env.NEXT_PUBLIC_SITE_URL || 'https://defencegate.eu',
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

export function absoluteUrl(path: string): string {
  return new URL(path, SITE.url).toString();
}

export function buildMetadata({ title, description, path, noindex = false }: { title: string; description: string; path: string; noindex?: boolean }): Metadata {
  const url = absoluteUrl(path);
  return {
    title,
    description,
    alternates: { canonical: url },
    robots: noindex ? { index: false, follow: true } : { index: true, follow: true },
    openGraph: { type: 'website', siteName: SITE.name, title, description, url, locale: 'en_GB' },
    twitter: { card: 'summary_large_image', title, description },
  };
}

export interface Crumb { label: string; href: string }

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
    funder: { '@type': 'Organization', name: call.programme === 'NATIONAL' ? (call.issuer ?? `${COUNTRIES[call.funderCountry]} national programme`) : PROGRAMMES[call.programme].name },
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
