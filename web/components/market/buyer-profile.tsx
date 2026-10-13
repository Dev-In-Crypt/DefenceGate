import Link from 'next/link';
import { cpvGroupTitle } from '@/lib/cpv';
import { formatNumber } from '@/lib/format';
import { daysText, percentText } from '@/lib/market';
import type { BuyerProfile } from '@/lib/types';
import { FactCell } from '@/components/dg/data-display';
import { BarChart, RankTable } from './charts';

const BASIS = 'm-0 max-w-[75ch] text-small text-ink-muted';

/**
 * What a buyer's own notices add up to: how many a year, on what subjects, how long it gives to respond,
 * how often it amends, and where the notices came from. Counts of notices, never spend; the API computes
 * them from the buyer's core-scope notices only, so the page says that too.
 */
export function BuyerProfileSection({ profile, name }: { profile: BuyerProfile; name: string }) {
  const w = profile.responseWindow;
  const a = profile.amendments;
  const years = profile.perYear;
  const lastYear = years[years.length - 1]?.year;
  return (
    <section aria-labelledby="buyer-profile" className="flex flex-col gap-4">
      <h2 id="buyer-profile" className="m-0 text-h2">Profile</h2>
      <p className="m-0 max-w-[75ch] text-body text-ink-muted">
        Counts of {name}&apos;s defence notices in our archive, from {profile.sources.length === 1 ? 'one source' : `${profile.sources.length} sources`}.
        They count notices, not contract value, and are only as complete as those sources: see <Link href="/data" className="font-semibold">source status</Link>.
      </p>
      <dl className="m-0 grid grid-cols-[repeat(auto-fit,minmax(220px,1fr))] gap-3">
        <FactCell label="Typical response window">
          <span>{daysText(w.median)}</span>
          <span className="block font-sans text-small font-normal text-ink-muted">
            {w.p25 !== null && w.p75 !== null ? `Middle half: ${w.p25} to ${w.p75} days. ` : ''}
            {formatNumber(w.notices)} {w.notices === 1 ? 'notice states' : 'notices state'} a deadline.
          </span>
        </FactCell>
        <FactCell label="With an amendment">
          <span>{percentText(a.share)}</span>
          <span className="block font-sans text-small font-normal text-ink-muted">
            {formatNumber(a.amended)} of {formatNumber(a.notices)} notices, counted from when we first saw each one (September 2026 at the earliest).
          </span>
        </FactCell>
      </dl>

      <div className="grid gap-4 lg:grid-cols-2">
        <div className="flex min-w-0 flex-col gap-3 rounded-lg bg-surface p-5 sm:p-6">
          <h3 className="m-0 text-h3">Notices per year</h3>
          <BarChart
            id="buyer-years"
            title={`Notices published per year by ${name}`}
            summary={`${formatNumber(years.reduce((n, y) => n + y.count, 0))} notices over the last ${years.length} years.`}
            bars={years.map((y) => ({ label: String(y.year), primary: y.count, partial: y.year === lastYear }))}
            primaryName="Notices"
            labelHeader="Year"
          />
          <p className={BASIS}>{profile.basis.perYear}</p>
        </div>

        <div className="flex min-w-0 flex-col gap-6">
          <div className="flex flex-col gap-3 rounded-lg bg-surface p-5 sm:p-6">
            <h3 className="m-0 text-h3">Subjects</h3>
            {profile.cpvGroups.length > 0 ? (
              <RankTable
                caption={`Notices by CPV group, ${name}`}
                labelHeader="CPV group"
                rows={profile.cpvGroups.map((g) => ({
                  key: g.group,
                  label: <span><span className="font-mono tabular-nums">{g.group}</span> <span>{cpvGroupTitle(g.group) ?? 'Group'}</span></span>,
                  count: g.count,
                }))}
              />
            ) : (
              <p className="m-0 text-body text-ink-muted">These notices state no CPV code.</p>
            )}
            <p className={BASIS}>{profile.basis.cpvGroups}</p>
          </div>
          <div className="flex flex-col gap-3 rounded-lg bg-surface p-5 sm:p-6">
            <h3 className="m-0 text-h3">Sources</h3>
            <RankTable
              caption={`Notices by source, ${name}`}
              labelHeader="Source"
              total={profile.tenderCount}
              rows={profile.sources.map((s) => ({ key: s.id, label: s.name, count: s.count }))}
            />
            <p className={BASIS}>{profile.basis.sources}</p>
          </div>
        </div>
      </div>
    </section>
  );
}
