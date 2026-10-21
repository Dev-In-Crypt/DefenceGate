import Link from 'next/link';
import { CircleAlert, CircleCheck, CircleHelp, CircleX, Info, ListChecks, Minus, UserRoundSearch } from 'lucide-react';
import { OBLIGATION_WORD, OUTCOME_WORD, VERDICT_MEANING, VERDICT_WORD, isoDay, originWords, publicPassage, publicRef, statusWords } from '@/lib/readiness';
import type { Outcome, ProgrammeAssessment, RSource, RuleResult, Verdict } from '@/lib/readiness-types';
import { safeHttpUrl } from '@/lib/safe-url';
import { cleanQuote } from '@/lib/quote';
import { stepOfField, supplierAsks, wizardAsks } from '@/lib/profile';
import { Icon } from '@/components/dg/icon';
import { cn } from '@/lib/utils';

const OUTCOME_ICON = {
  met: CircleCheck, not_met: CircleX, to_obtain: ListChecks, conditional: CircleAlert, unknown: CircleHelp, not_applicable: Minus, info: Info,
} as const;
const VERDICT_ICON = { eligible: CircleCheck, obtain: ListChecks, blocked: CircleX, conditional: CircleAlert } as const;

/** A word and an icon, never a colour alone. */
export function OutcomeBadge({ outcome }: { outcome: Outcome }) {
  return (
    <span className="inline-flex shrink-0 items-center gap-1.5 whitespace-nowrap rounded-pill border border-line bg-surface-inset px-2.5 py-1 text-label">
      <Icon icon={OUTCOME_ICON[outcome]} size="inline" />{OUTCOME_WORD[outcome]}
    </span>
  );
}

export function VerdictBadge({ verdict, className }: { verdict: Verdict; className?: string }) {
  return (
    <span className={cn('inline-flex items-center gap-2 whitespace-nowrap rounded-pill border-strong border-ink bg-surface px-3.5 py-1.5 text-label font-bold', className)}>
      <Icon icon={VERDICT_ICON[verdict]} size="button" /><span>{VERDICT_WORD[verdict]}</span>
    </span>
  );
}

/** The source of a rule: where it is from, the link, the date, and the verbatim text on request. */
export function SourceNote({ source }: { source: RSource }) {
  const url = safeHttpUrl(source.url);
  const passages = (source.text ?? '').split('\n\n').filter(Boolean).map(publicPassage);
  return (
    <div className="flex flex-col gap-2 text-small text-ink-muted">
      <p className="m-0">
        Source: {publicRef(source.ref) ?? 'see the link'}
        {url && <> · <a href={url} target="_blank" rel="noopener noreferrer" className="font-semibold">Open the source</a></>}
        {' '}· Last reviewed {isoDay(source.lastReviewed)}
      </p>
      {passages.length > 0 && (
        <details>
          <summary className="inline-flex min-h-11 cursor-pointer items-center font-semibold text-ink">Show the text of the source</summary>
          <div className="flex flex-col gap-2 pb-2">
            {passages.map((p, i) => <blockquote key={i} className="m-0 break-words border-l-2 border-line pl-3 text-ink">{cleanQuote(p)}</blockquote>)}
            <p className="m-0">{originWords(source)} {statusWords(source.verificationStatus, source.origin, source.url)}</p>
          </div>
        </details>
      )}
    </div>
  );
}

export function RuleItem({ rule }: { rule: RuleResult }) {
  return (
    <li className="flex flex-col gap-2 border-t border-line py-4 first:border-t-0" data-rule={rule.rule} data-outcome={rule.outcome}>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <OutcomeBadge outcome={rule.outcome} />
        <h4 className="m-0 min-w-0 flex-1 text-body font-bold">{rule.title}</h4>
        <span className="text-small text-ink-muted">{OBLIGATION_WORD[rule.obligation]}</span>
      </div>
      <p className="m-0 max-w-prose text-body">{rule.reason}</p>
      {rule.note && <p className="m-0 max-w-prose text-small text-ink-muted">{rule.note}</p>}
      {rule.asks.length > 0 && (
        <ul className="m-0 flex list-none flex-col gap-1 p-0 text-small">
          {rule.asks.map((a) => <li key={a.field}>To answer: {a.question}</li>)}
        </ul>
      )}
      {rule.consultant && <ConsultantNote text={rule.consultant} />}
      {rule.requirement && (rule.outcome === 'not_met' || rule.outcome === 'to_obtain') && (
        <p className="m-0 text-small"><Link href={`/readiness/roadmap`} className="font-semibold">See the step in your roadmap</Link></p>
      )}
      <SourceNote source={rule.source} />
    </li>
  );
}

/** "Consultant needed" (WP-64): a word and an icon, never a colour alone. The service gives no answer on what it names. */
export function ConsultantNote({ text }: { text: string }) {
  return (
    <p className="m-0 flex max-w-prose items-start gap-2 text-small" data-consultant>
      <Icon icon={UserRoundSearch} size="inline" className="mt-0.5 shrink-0" />
      <span><strong>Consultant needed.</strong> {text}</span>
    </p>
  );
}

/** One programme: the verdict, why, and every rule behind it. */
/** `general`: the rules that apply whichever route you take. They carry no verdict; what is not met is a to-do. */
export function ProgrammeCard({ a, headingLevel = 'h3', general = false }: { a: ProgrammeAssessment; headingLevel?: 'h2' | 'h3'; general?: boolean }) {
  const H = headingLevel;
  const blockers = a.rules.filter((r) => a.blocking.includes(r.rule));
  const conditions = a.rules.filter((r) => a.conditions.includes(r.rule));
  const toObtain = a.rules.filter((r) => a.toObtain.includes(r.rule));
  const applies = a.rules.filter((r) => r.outcome !== 'not_applicable');
  const apart = a.rules.filter((r) => r.outcome === 'not_applicable');
  const todo = a.rules.filter((r) => r.outcome === 'not_met' || r.outcome === 'to_obtain');
  const id = `prog-${a.programme}`;
  return (
    <article aria-labelledby={id} className="flex flex-col gap-4 rounded-lg border border-edge bg-surface p-5 sm:p-6" data-programme={a.programme} data-verdict={a.verdict}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <H id={id} className="m-0 min-w-0 flex-1 text-h3">{a.name}</H>
        {!general && <VerdictBadge verdict={a.verdict} />}
      </div>
      <p className="m-0 max-w-prose text-body text-ink-muted">{a.summary}</p>
      {!general && <p className="m-0 text-small font-semibold">{VERDICT_MEANING[a.verdict]}</p>}
      {general && todo.length > 0 && (
        <div className="flex flex-col gap-1 text-small">
          <p className="m-0 font-bold">To do for you:</p>
          <ul className="m-0 flex list-none flex-col gap-1 p-0">{todo.map((r) => <li key={r.rule}>{r.title}</li>)}</ul>
        </div>
      )}
      {general && todo.length === 0 && <p className="m-0 text-small font-semibold">Nothing to do under these rules on the answers given.</p>}
      {blockers.length > 0 && (
        <div className="flex flex-col gap-1 text-small">
          <p className="m-0 font-bold">Not met:</p>
          <ul className="m-0 flex list-none flex-col gap-1 p-0">{blockers.map((r) => <li key={r.rule}>{r.title}</li>)}</ul>
        </div>
      )}
      {toObtain.length > 0 && (
        <div className="flex flex-col gap-1 text-small">
          <p className="m-0 font-bold">To obtain first (see your roadmap):</p>
          <ul className="m-0 flex list-none flex-col gap-1 p-0">{toObtain.map((r) => <li key={r.rule}>{r.title}</li>)}</ul>
        </div>
      )}
      {conditions.length > 0 && (
        <div className="flex flex-col gap-1 text-small">
          <p className="m-0 font-bold">A condition applies:</p>
          <ul className="m-0 flex list-none flex-col gap-1 p-0">{conditions.map((r) => <li key={r.rule}>{r.title}</li>)}</ul>
        </div>
      )}
      {a.missing.length > 0 && (
        <div className="flex flex-col gap-1 text-small">
          <p className="m-0 font-bold">{a.missing.length === 1 ? '1 answer is missing:' : `${a.missing.length} answers are missing:`}</p>
          <ul className="m-0 flex list-none flex-col gap-0.5 p-0">
            {a.missing.map((m) => (
              <li key={m.field}>
                {wizardAsks(m.field)
                  ? <Link href={`/readiness?step=${stepOfField(m.field)}`} className="inline-flex min-h-12 items-center font-semibold">{m.question}</Link>
                  // WP-65: a question the supplier profile asks links to its field there
                  : supplierAsks(m.field)
                  ? <Link href={`/readiness/supplier#q-${m.field.replace(/^profile\./, '')}`} className="inline-flex min-h-12 items-center font-semibold" data-supplier-asks={m.field}>{m.question}</Link>
                  // a question of the Spanish, German or NATO/EU rules (WP-64) that the questionnaire does not ask yet: no step to link to
                  : <span className="inline-flex min-h-12 items-center" data-not-asked={m.field}>{m.question} <span className="ml-1 text-ink-muted">(not asked by the questionnaire yet)</span></span>}
              </li>
            ))}
          </ul>
        </div>
      )}
      {applies.length > 0 && <details>
        <summary className="inline-flex min-h-11 cursor-pointer items-center font-bold text-ink">
          Show the {applies.length} {applies.length === 1 ? 'rule' : 'rules'} behind this{apart.length > 0 ? ' that apply to you' : ''}
        </summary>
        <ul className="m-0 flex list-none flex-col p-0">{applies.map((r) => <RuleItem key={r.rule} rule={r} />)}</ul>
      </details>}
      {apart.length > 0 && (
        // A rule that does not apply to this company (a Spanish clearance for a Polish one) is kept apart, with its source, so that
        // its text is not read as part of the company's verdict (U13).
        <details>
          <summary className="inline-flex min-h-11 cursor-pointer items-center font-bold text-ink">
            {apart.length} {apart.length === 1 ? 'rule that does' : 'rules that do'} not apply to you
          </summary>
          <ul className="m-0 flex list-none flex-col p-0">{apart.map((r) => <RuleItem key={r.rule} rule={r} />)}</ul>
        </details>
      )}
      <p className="m-0 mt-auto pt-2 text-small text-ink-muted">
        {a.legalBasis ? <>Legal basis: {a.legalBasis}.</> : 'No legal basis is stated for this route.'}{' '}
        {safeHttpUrl(a.sourceUrl) && <a href={a.sourceUrl} target="_blank" rel="noopener noreferrer" className="font-semibold">{a.legalBasis ? 'Open the legal text' : 'Open the page of the source'}</a>}
      </p>
    </article>
  );
}
