import type { Metadata } from 'next';
import { ArrowRight } from 'lucide-react';
import { cpvDictionaryTitle } from '@/lib/cpv';
import { approachSentence, buyerLine, directiveShare, type Demand } from '@/lib/demand';
import { formatDateUtc } from '@/lib/format';
import { getDemandSample } from '@/lib/readiness-api';
import { buildMetadata } from '@/lib/seo';
import { WHAT_IS_SENT } from '@/lib/sent-copy';
import { countryName } from '@/lib/taxonomy';
import { Button } from '@/components/dg/button';
import { Callout } from '@/components/dg/blocks';
import { ContentPage, ContentSection } from '@/components/dg/content-page';

export const revalidate = 3600;

export const metadata: Metadata = buildMetadata({
  title: 'Spain automotive: who to approach in defence',
  description: 'For civilian manufacturers in Spain, such as automotive suppliers: who wins defence contracts under your CPV codes in seven countries, who buys, and the rules.',
  path: '/readiness/spain-automotive',
});

const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;

/** The live demand map for the sample codes: shown only when the API answered (no figure is made up or taken from demo data). */
function Sample({ d }: { d: Demand }) {
  return (
    <ContentSection title="Live from the demand map">
      <div className="flex flex-col gap-3 text-body" data-demand-sample>
        <p className="m-0">
          The codes of the supplier profile’s automotive button, the codes your report counts when you choose it, counted by the demand map on {formatDateUtc(d.until)} for the three years from{' '}
          {formatDateUtc(d.since)}:
        </p>
        <ul className="m-0 flex list-disc flex-col gap-1 pl-5">
          {d.codes.map((c) => (
            <li key={c.code}><span className="font-mono">{c.code}</span> {cpvDictionaryTitle(c.code) ?? ''}: {plural(c.procurements, 'procurement', 'procurements')}</li>
          ))}
        </ul>
        <p className="m-0">
          In the seven countries together: {plural(d.total.procurements, 'procurement', 'procurements')} by {buyerLine(d.total)}; under Directive 2009/81/EC:{' '}
          {directiveShare(d.total)}.
        </p>
        <ul className="m-0 flex list-disc flex-col gap-1 pl-5">
          {d.byCountry.map((c) => (
            <li key={c.country} data-demand-sample-country={c.country}>
              {countryName(c.country)}: {plural(c.procurements, 'procurement', 'procurements')} by {buyerLine(c)}; under Directive 2009/81/EC: {directiveShare(c)}.
            </li>
          ))}
        </ul>
        {d.approach && (
          <p className="m-0" data-demand-sample-approach>
            {approachSentence(d)}
          </p>
        )}
        <p className="m-0 text-small text-ink-muted">{d.coverage}</p>
        <p className="m-0 text-small text-ink-muted">Your own map is computed from the codes you choose on the supplier profile, and is part of your report.</p>
      </div>
    </ContentSection>
  );
}

export default async function SpainAutomotivePage() {
  const sample = await getDemandSample();
  return (
    <ContentPage
      crumbs={[{ label: 'Home', href: '/' }, { label: 'Check my company', href: '/check' }, { label: 'Spain automotive', href: '/readiness/spain-automotive' }]}
      title="Supplier readiness: Spain automotive"
      lead="For civilian manufacturers in Spain, such as automotive suppliers, considering defence work: say what you make, and the report shows who wins and who buys it in seven countries, then the rules."
    >
      <div className="flex flex-wrap gap-3" data-useful>
        <Button href="/readiness/supplier" iconRight={ArrowRight}>Start the supplier profile</Button>
      </div>

      <Callout title="Indicative, sources linked, not legal advice">
        <p className="m-0">Each result names the rule it comes from, quotes its source and links to it, with the date the rule was last reviewed. Read the source before you act on a result.</p>
      </Callout>

      <ContentSection title="Who it is for">
        <p className="m-0 text-body text-ink-muted">
          Manufacturers established in Spain that make civilian products today, such as automotive components, castings, machined parts or electronics,
          and want to supply defence buyers: the Ministry of Defence, the NATO Support and Procurement Agency (NSPA), and the prime contractors that
          build for them. A company established elsewhere can use the profile too; the Spanish rules then do not apply to it.
        </p>
      </ContentSection>

      <ContentSection title="What you get">
        <ul className="m-0 flex list-disc flex-col gap-2 pl-5 text-body text-ink-muted">
          <li>
            <strong className="text-ink">Who to approach.</strong> The companies that won defence-scope contracts under the CPV codes you choose in Spain,
            Germany, France, Poland and the Netherlands over the last three years, from TED and the Spanish national procurement portal, each contract counted
            once: how many contracts, the sum of their values per currency where a notice states one for that company alone, the buyers they win
            from, the countries, the date of the latest notice, and a link
            to their supplier page. Prime contractors and large defence groups are marked, with the source of the list. Every company is named, from one award up;
            a winner who is a natural person is never named.
          </li>
          <li>
            <strong className="text-ink">Who buys what you make.</strong> The buyers of those codes in the seven countries (core defence buyers and others),
            how many procurements, how many under Directive 2009/81/EC, and the newest notices.
          </li>
          <li>
            <strong className="text-ink">The rules, as an appendix.</strong> Your answers against the rules of the Spanish Ministry of Defence supplier route,
            NATO supply and the EU defence programmes, each with its source; then the steps in order (what you hold, what you need now, what usually comes
            with a first contract, such as the PECAL quality certificate), each with the free guide and the regional grants that have paid for it.
          </li>
          <li><strong className="text-ink">A printable report</strong> of all of it, which you can print or save as a PDF.</li>
        </ul>
        <p className="m-0 text-body text-ink-muted">
          Why this order: automotive suppliers usually enter defence as subcontractors of the prime contractors and their large suppliers, and in Spain
          the rules are already explained for free (the CAETRA guides of the Región de Murcia, a course of ACCIÓ in Catalonia) and regional programmes
          have paid for the certifications. What we did not find elsewhere is who wins these contracts across the seven countries.
        </p>
        <p className="m-0 text-body text-ink-muted">
          The profile is one page. Where an answer needs a classification or a legal reading (export control, US-origin components, a foreign investor,
          a security clearance), the result says so and that a specialist is needed; it gives no answer of its own.
        </p>
      </ContentSection>

      <ContentSection title="What it is not">
        <ul className="m-0 flex list-disc flex-col gap-1 pl-5 text-body text-ink-muted">
          <li>It is not legal advice and does not replace the tender documents: each buyer sets its own conditions there.</li>
          <li>It does not find contracts or guarantee one. Meeting these requirements does not win a contract.</li>
          <li>
            It does not show what prime contractors need from their suppliers: those needs are not published in the sources we read. The report shows who
            won and who buys directly, not what primes need.
          </li>
          <li>It does not ask about the technical detail of any product, and never will.</li>
        </ul>
      </ContentSection>

      {sample && <Sample d={sample} />}

      <Callout title="Your answers are not stored on our server">
        <p className="m-0" data-what-is-sent>They are saved in this browser: there is no account and no copy on our server. {WHAT_IS_SENT}</p>
      </Callout>

      <section lang="es" aria-labelledby="s-resumen" className="flex min-w-0 flex-col gap-2" data-summary-es>
        <h2 id="s-resumen" className="m-0 text-h3">Resumen en español</h2>
        <p className="m-0 max-w-prose text-body text-ink-muted">
          Para fabricantes civiles establecidos en España, por ejemplo proveedores de componentes de automoción, que estudian suministrar a compradores de
          defensa. El informe empieza por las empresas que ganan contratos de defensa con sus códigos CPV en España, Alemania, Francia, Polonia y los
          Países Bajos, marcando los contratistas principales y los grandes grupos de defensa; sigue con quién compra esos códigos; y termina, como anexo,
          con las reglas de la ruta de proveedor del Ministerio de Defensa, del suministro OTAN y de los programas de defensa de la UE, cada una con su
          fuente, la guía gratuita y las ayudas regionales que han cubierto cada paso. Se puede imprimir. Es orientativo, no es asesoramiento jurídico y no
          garantiza ningún contrato.
          La herramienta está en inglés.
        </p>
      </section>

      <div className="flex flex-wrap gap-3">
        <Button href="/readiness/supplier" iconRight={ArrowRight}>Start the supplier profile</Button>
        <Button href="/readiness" variant="secondary">The readiness check for EU funding</Button>
      </div>
    </ContentPage>
  );
}
