import type { Metadata } from 'next';
import Link from 'next/link';
import { notFound, permanentRedirect } from 'next/navigation';
import { ArrowRight } from 'lucide-react';
import { getRequirement, getRequirements } from '@/lib/readiness-api';
import { CATEGORY_WORD, OBLIGATION_WORD, faqOf, formatDays, formatRange, groupIssuers, originWords, publicPassage, publicRef, requirementCode, requirementSlug, ruleSentence, siteDay, statusWords } from '@/lib/readiness';
import { countryName } from '@/lib/taxonomy';
import { plural } from '@/lib/format';
import { absoluteUrl, buildMetadata } from '@/lib/seo';
import { safeHttpUrl } from '@/lib/safe-url';
import { Button } from '@/components/dg/button';
import { ContentPage, ContentSection } from '@/components/dg/content-page';
import { JsonLd } from '@/components/dg/feedback';
import { Fact, FactsGrid } from '@/components/dg/facts-grid';

export const revalidate = 3600;

type Params = Promise<{ code: string }>;

/**
 * Shorter words for the browser tab and the search snippet, where the catalogue's name or summary does not fit (60 characters with
 * the site name, 160 for a description) and would be cut mid-phrase (re-audit NEW-5, WP-63). The page itself shows the full name
 * and summary. A requirement not listed here uses its own.
 */
const SHORT_META: Record<string, { name?: string; description?: string }> = {
  'REQ-AQAP2310': { name: 'AQAP 2310' },
  'REQ-EDIP-ELIG': { name: 'EDIP eligibility' },
  'REQ-EXPORT': { name: 'Export authorisation' },
  'REQ-EDF-ELIG': { description: 'Who may receive EDF funding: an entity established in the Union or an associated country, managed from there, not controlled by a non-associated third country.' },
  'REQ-SAFE-35': { description: 'In a SAFE-supported procurement, components from outside the Union, the EEA EFTA states and Ukraine may be at most 35 % of the estimated component cost.' },
};

async function load(params: Params) {
  const { code: slug } = await params;
  const code = requirementCode(slug);
  if (!code) return null;
  const requirement = await getRequirement(code);
  return requirement ? { requirement, slug } : null;
}

export async function generateMetadata({ params }: { params: Params }): Promise<Metadata> {
  const found = await load(params);
  if (!found) return { title: 'Page not found', robots: { index: false, follow: false } };
  const { requirement: r } = found;
  const what = r.kind === 'document' ? 'who issues it, cost and time' : 'what the rule says';
  const short = SHORT_META[r.code];
  return buildMetadata({
    title: `${short?.name ?? r.name}: ${what}`,
    description: short?.description ?? r.summary,
    path: `/requirements/${requirementSlug(r.code)}`,
  });
}

export default async function RequirementPage({ params }: { params: Params }) {
  const found = await load(params);
  if (!found) notFound();
  const { requirement: r, slug } = found;
  if (slug !== requirementSlug(r.code)) permanentRedirect(`/requirements/${requirementSlug(r.code)}`);
  const path = `/requirements/${requirementSlug(r.code)}`;
  const faq = faqOf(r);
  // Our own working document is not named on a public page: a quote shows the body it comes from, or none.
  const passages = (r.source.text ?? '').split('\n\n').filter(Boolean).map(publicPassage);
  const sourceRef = publicRef(r.source.ref);
  const { singles, groups } = groupIssuers(r.issuers);
  // The requirements that need this one are named, not shown by their code.
  const names = new Map((await getRequirements().catch(() => ({ items: [] }))).items.map((x) => [x.code, x.name]));
  const sourceUrl = safeHttpUrl(r.source.url);
  const article = {
    '@context': 'https://schema.org', '@type': 'Article', headline: r.name, description: r.summary,
    url: absoluteUrl(path), dateModified: r.lastReviewed, inLanguage: 'en',
    publisher: { '@type': 'Organization', name: 'DefenceGate' },
    ...(sourceUrl ? { isBasedOn: sourceUrl } : {}),
  };

  return (
    <ContentPage
      toc
      crumbs={[{ label: 'Home', href: '/' }, { label: 'Requirements', href: '/requirements' }, { label: r.name, href: path }]}
      title={r.name}
      lead={r.summary}
    >
      <JsonLd data={article} />
      {faq.length > 0 && (
        <JsonLd data={{ '@context': 'https://schema.org', '@type': 'FAQPage', mainEntity: faq.map((f) => ({ '@type': 'Question', name: f.q, acceptedAnswer: { '@type': 'Answer', text: f.a } })) }} />
      )}

      <ContentSection title="At a glance">
        <FactsGrid>
          <Fact label="Kind">{CATEGORY_WORD[r.category] ?? r.category}{r.kind === 'rule' ? ' (assessed, not obtained)' : ''}</Fact>
          {r.kind === 'document' && (
            <>
              <Fact label="Cost">
                <span className="block font-mono tabular-nums">{r.cost?.text ?? formatRange(r.cost)}</span>
                {r.vendorRangeLabel && <span className="block text-small font-bold">{r.vendorRangeLabel}</span>}
                {r.cost?.alt && <span className="block text-small text-ink-muted">{r.cost.alt.text}</span>}
              </Fact>
              <Fact label="Time">
                <span className="block font-mono tabular-nums">{formatDays(r.days)}</span>
                {r.durationNote && <span className="block text-small text-ink-muted">{r.durationNote}</span>}
              </Fact>
            </>
          )}
          {r.mandatoryFor && <Fact label="Needed for">{r.mandatoryFor}</Fact>}
          {r.legalBasis && <Fact label="Legal basis">{r.legalBasis}</Fact>}
          <Fact label="Last reviewed"><time dateTime={r.lastReviewed}>{siteDay(r.lastReviewed)}</time></Fact>
          <Fact label="Verification">{statusWords(r.verificationStatus, r.source.origin)}</Fact>
        </FactsGrid>
      </ContentSection>

      {r.description && (
        <ContentSection title={r.kind === 'document' ? 'What it is' : 'What the rules say'}>
          {r.description.split('\n\n').map((p, i) => <p key={i} className="m-0 text-body text-ink-muted">{p}</p>)}
        </ContentSection>
      )}

      {r.variants.length > 0 && (
        <ContentSection title="If you already hold a related certificate">
          <ul className="m-0 flex list-none flex-col gap-2 p-0 text-body text-ink-muted">
            {r.variants.map((v) => (
              <li key={v.whenHeld}>
                {v.cost?.text ?? formatRange(v.cost)}{v.days ? `, ${formatDays(v.days)}` : ''}. {v.cost?.label && <strong className="text-ink">{v.cost.label}.</strong>}
              </li>
            ))}
          </ul>
          {r.extras.without_prerequisite && <p className="m-0 text-body text-ink-muted">{r.extras.without_prerequisite.text}</p>}
          {(r.extras.other_figures ?? []).map((f) => <p key={f} className="m-0 text-small text-ink-muted">{f}</p>)}
        </ContentSection>
      )}

      {r.kind === 'document' && (
        <ContentSection title="Who issues it">
          {r.issuers.length > 0 ? (
            <ul className="m-0 flex list-none flex-col gap-3 p-0">
              {singles.map((i) => (
                <li key={`${i.country}-${i.name}`} className="flex flex-col gap-0.5">
                  <span className="font-bold">{i.country !== '*' ? countryName(i.country) : r.issuers.some((x) => x.country !== '*') ? 'Every other country' : 'Every country'}</span>
                  <span>{safeHttpUrl(i.url) ? <a href={i.url as string} target="_blank" rel="noopener noreferrer">{i.name}</a> : i.name}</span>
                  {i.notes && <span className="text-small text-ink-muted">{i.notes}</span>}
                  <span className="text-small text-ink-muted">{statusWords(i.verificationStatus, 'notes')}</span>
                </li>
              ))}
              {groups.map((g) => (
                <li key={g.name} className="flex flex-col gap-0.5">
                  <span className="font-bold">{g.name}: {g.countries.length} {plural(g.countries.length, 'country', 'countries')}</span>
                  <span className="max-w-prose">{g.countries.join(', ')}</span>
                  {g.notes && <span className="text-small text-ink-muted">{g.notes}</span>}
                  <span className="text-small text-ink-muted">{statusWords(g.verificationStatus, 'notes')}</span>
                </li>
              ))}
            </ul>
          ) : <p className="m-0 text-body text-ink-muted">No issuing body has been collected.</p>}
          {!r.issuers.some((i) => i.country === '*') && <p className="m-0 text-small text-ink-muted">For a country that is not listed, the issuing body has not been collected. We list none rather than guess.</p>}
        </ContentSection>
      )}

      {r.rules.length > 0 && (
        <ContentSection title="Which programmes ask for it">
          <ul className="m-0 flex list-none flex-col gap-3 p-0">
            {r.rules.map((x) => (
              <li key={`${x.programme}-${x.rule}`} className="flex flex-col gap-0.5">
                <span><strong>{x.programmeName}</strong>: {x.title} <span className="text-small text-ink-muted">({OBLIGATION_WORD[x.obligation]})</span></span>
                {ruleSentence(x.texts) && <span className="max-w-prose text-body text-ink-muted">{ruleSentence(x.texts)}</span>}
              </li>
            ))}
          </ul>
        </ContentSection>
      )}

      {(r.prerequisites.length > 0 || r.requiredBy.length > 0) && (
        <ContentSection title="What it depends on">
          {r.prerequisites.map((p) => (
            <p key={p.code} className="m-0 text-body text-ink-muted">
              {p.relation === 'before' ? 'Comes after ' : 'Before or together with '}<Link href={`/requirements/${requirementSlug(p.code)}`} className="font-semibold">{p.name}</Link>.
            </p>
          ))}
          {r.requiredBy.map((c) => (
            <p key={c} className="m-0 text-body text-ink-muted">Needed before <Link href={`/requirements/${requirementSlug(c)}`} className="font-semibold">{names.get(c) ?? requirementSlug(c).toUpperCase()}</Link>.</p>
          ))}
        </ContentSection>
      )}

      {faq.length > 0 && (
        <ContentSection title="Questions">
          <dl className="m-0 flex flex-col gap-3">
            {faq.map((f) => (
              <div key={f.q} className="flex flex-col gap-0.5">
                <dt className="font-bold">{f.q}</dt>
                <dd className="m-0 text-body text-ink-muted">{f.a}</dd>
              </div>
            ))}
          </dl>
        </ContentSection>
      )}

      <ContentSection title="Source">
        <p className="m-0 text-body text-ink-muted">
          {sourceRef ?? 'See the link'}
          {sourceUrl && <> · <a href={sourceUrl} target="_blank" rel="noopener noreferrer" className="font-semibold">Open the source</a></>}
        </p>
        {passages.map((p, i) => <blockquote key={i} className="m-0 break-words border-l-2 border-line pl-3 text-body">{p}</blockquote>)}
        <p className="m-0 text-small text-ink-muted">{originWords(r.source)} Last reviewed {siteDay(r.lastReviewed)}.</p>
      </ContentSection>

      <div className="flex flex-wrap gap-3">
        <Button href="/readiness" iconRight={ArrowRight}>Check where your company stands</Button>
        <Button href="/requirements" variant="secondary">All requirements</Button>
      </div>
    </ContentPage>
  );
}
