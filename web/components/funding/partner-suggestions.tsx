'use client';

import { useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { Users } from 'lucide-react';
import { formatDateUtc, formatNumber } from '@/lib/format';
import { countryName } from '@/lib/taxonomy';
import type { PartnersAnswer } from '@/lib/types';
import { Button } from '@/components/dg/button';
import { Select } from '@/components/dg/form';
import { ErrorState, Skeleton } from '@/components/dg/feedback';
import { useProfile } from '@/components/readiness/use-readiness';

/** A failure we word ourselves; any other (no answer, unreadable JSON) gets the standard sentence, never the browser's. */
class LoadError extends Error {}

type State = { state: 'idle' } | { state: 'loading' } | { state: 'error'; message: string } | { state: 'done'; data: PartnersAnswer };

/**
 * Partner suggestions for a call (WP-32): organisations that took part in earlier projects of the same area, from CORDIS
 * and the EDF factsheets. Nothing is fetched until the visitor asks, or has a saved profile (then the list loads by itself,
 * with nothing about the profile in the request). The profile's country goes to the server only when the visitor presses
 * "Put organisations from <country> first": the readiness page promises that the profile does not leave the browser except for
 * the verdict, and a country code in a request is part of it. The server does the ordering (`prefer`): a browser can only
 * re-sort the page it was given, and the organisations of a small country are never among the largest twenty of the whole
 * area (U1 of the UX verification).
 */
export function PartnerSuggestions({ callSlug }: { callSlug: string }) {
  const { profile, ready } = useProfile();
  const [asked, setAsked] = useState(false);
  const [country, setCountry] = useState('');
  const [result, setResult] = useState<State>({ state: 'idle' });
  const [attempt, setAttempt] = useState(0);
  const seq = useRef(0);
  const saved = ready && profile && profile.country && profile.country !== 'XX' ? profile.country : '';
  // The country is sent only after the visitor chooses to (see the comment above).
  const [mine, setMine] = useState(false);
  const own = mine ? saved : '';
  const go = asked || saved !== '';

  useEffect(() => {
    if (!go) return;
    const controller = new AbortController();
    const mine = ++seq.current;
    setResult((r) => (r.state === 'done' ? r : { state: 'loading' }));
    fetch(`/api/funding/${encodeURIComponent(callSlug)}/partners${country ? `?country=${country}` : own ? `?prefer=${own}` : ''}`, {
      headers: { accept: 'application/json' }, credentials: 'omit', signal: controller.signal,
    }).then(async (res) => {
      if (!res.ok) throw new LoadError(res.status === 429 ? 'Too many requests. Wait a minute and try again.' : 'The suggestions could not be loaded. Try again in a moment.');
      const data = (await res.json()) as PartnersAnswer;
      if (mine === seq.current) setResult({ state: 'done', data });
    }).catch((e: unknown) => {
      if (controller.signal.aborted || mine !== seq.current) return;
      setResult({ state: 'error', message: e instanceof LoadError ? e.message : 'The suggestions could not be loaded. Try again in a moment.' });
    });
    return () => controller.abort();
  }, [go, callSlug, country, own, attempt]);

  const data = result.state === 'done' ? result.data : null;
  const partners = data?.partners ?? [];

  if (!go) {
    return (
      <div className="flex flex-col gap-3">
        <p className="m-0 text-body">
          Organisations that took part in earlier funded projects of the same area as this call, from CORDIS and the EDF project factsheets, with the projects as evidence.
          They are loaded when you ask.
        </p>
        <Button type="button" variant="secondary" icon={Users} onClick={() => setAsked(true)} className="self-start whitespace-normal text-left">Show organisations from earlier projects</Button>
      </div>
    );
  }
  if (result.state === 'loading' || result.state === 'idle') {
    return <div role="status" aria-label="Loading partner suggestions" className="flex flex-col gap-3"><Skeleton className="h-6 w-72" /><Skeleton className="h-32" /></div>;
  }
  if (result.state === 'error') {
    return <ErrorState level="h3" title="The suggestions could not be loaded" onRetry={() => setAttempt((n) => n + 1)}>{result.message}</ErrorState>;
  }

  const d = result.data;
  const countries = [{ value: '', label: 'All countries' }, ...d.countries.map((c) => ({ value: c.country, label: `${countryName(c.country)} (${c.organisations})` }))];
  // The call names no capability category (or the category is too small): the list is the whole programme's, and says so.
  const wide = d.area !== null && (d.area.kind === 'edf' || d.area.kind === 'horizon-family');
  const ownHere = own ? d.countries.find((c) => c.country === own)?.organisations ?? 0 : 0;
  const hint = own && !country
    ? ownHere > 0
      ? `Organisations from ${countryName(own)}, the country of your saved profile, are listed first (${ownHere} in this area).`
      : `No organisation from ${countryName(own)}, the country of your saved profile, took part in an earlier project of this area.`
    : wide ? 'Start with your country: the unfiltered list is led by the largest organisations of the whole programme.' : undefined;
  const picker = d.area !== null && d.countries.length > 1 && (
    <div className="flex flex-col gap-1">
      <Select label="Show organisations from" options={countries} value={country} onChange={(e) => setCountry(e.target.value)} className="sm:max-w-xs" hint={hint} />
      {saved !== '' && !country && (
        <p className="m-0 flex flex-col items-start gap-0.5 text-small text-ink-muted">
          <button type="button" onClick={() => setMine(!mine)} className="inline-flex min-h-12 items-center border-0 bg-transparent p-0 text-left font-sans text-small font-semibold text-link underline">
            {mine ? 'Show the largest organisations of all countries instead' : `Put organisations from ${countryName(saved)} first`}
          </button>
          {!mine && <span>Your saved profile stays in this browser. This sends only the country code, {saved}, to our server with the request.</span>}
        </p>
      )}
    </div>
  );
  return (
    <div className="flex flex-col gap-4">
      {d.area === null ? (
        <p className="m-0 text-body text-ink-muted">{d.note}</p>
      ) : (
        <>
          {wide ? (
            <p className="m-0 text-body">
              {d.area.broaderThanCall
                ? 'The narrower area of this call has too few organisations, so this list is'
                : d.area.kind === 'edf' ? 'The code of this call names no capability category, so this list is' : 'This list is'}
              {' '}compared with the <strong>whole programme</strong>: {d.area.label}. {d.area.rule}
              {' '}It is led by the largest organisations of the programme. Choose a country first to see organisations closer to you.
            </p>
          ) : (
            <p className="m-0 text-body">Compared with <strong>{d.area.label}</strong>. {d.area.rule}</p>
          )}
          {wide && picker}
          <p className="m-0 text-small text-ink-muted">
            {d.area.projects === 0 ? 'No earlier project of this area is held yet.' : (
              <>{formatNumber(d.area.organisations)} organisations in {formatNumber(d.area.projects)} projects{d.area.firstYear ? `, ${d.area.firstYear} to ${d.area.lastYear}` : ''}.
                {' '}Ranked by the number of these projects an organisation took part in, then by the latest year.</>
            )}
          </p>
          {!wide && picker}
          {partners.length === 0 ? (
            <p className="m-0 text-body text-ink-muted">{d.note ?? (country ? `No organisation from ${countryName(country)} took part in an earlier project of this area.` : 'No organisation found.')}</p>
          ) : (
            <ol className="m-0 flex list-none flex-col gap-3 p-0">
              {partners.map((p) => (
                <li key={p.organisationId} className="flex flex-col gap-1 rounded-md border border-line p-4">
                  <p className="m-0 text-body font-semibold break-words">
                    <Link href={`/organisations/${p.slug}`}>{p.name}</Link>
                    <span className="ml-2 font-normal text-ink-muted">{countryName(p.country)}</span>
                  </p>
                  <p className="m-0 text-small">
                    {p.projects} {p.projects === 1 ? 'project' : 'projects'} in this area{p.coordinated > 0 ? `, ${p.coordinated} as coordinator` : ''}
                    {p.lastYear ? `, latest ${p.lastYear}` : ''}.
                  </p>
                  {p.evidence.length > 0 && (
                    <p className="m-0 break-words text-small text-ink-muted">
                      Projects: {p.evidence.map((e) => `${e.acronym ?? e.title}${e.year ? ` (${e.year}${e.role === 'coordinator' ? ', coordinator' : ''})` : e.role === 'coordinator' ? ' (coordinator)' : ''}`).join('; ')}
                      {p.projects > p.evidence.length ? '; and others' : ''}.
                    </p>
                  )}
                </li>
              ))}
            </ol>
          )}
        </>
      )}
      <p className="m-0 text-small text-ink-muted">
        An organisation that took part in an earlier project is not necessarily looking for partners, or a fit for this call: this is who has worked in the same area,
        not a recommendation. Sources: {d.source?.sources.join(' and ') ?? 'CORDIS and the EDF factsheets'}{d.source?.readAt ? `, read ${formatDateUtc(d.source.readAt)}` : ''}.
        The EDF participants were read from the factsheets (PDF) by a language model and checked against their text; the original factsheet is authoritative.
        {d.source?.licence ? ` Licence: ${d.source.licence}.` : ''}      </p>
    </div>
  );
}
