import Link from 'next/link';
import { cpvGroupName } from '@/lib/cpv';
import { formatNumber, plural } from '@/lib/format';
import { AboutData } from '@/components/dg/about-data';
import { amendmentsShown, daysText, percentText, profileYearBars } from '@/lib/market';
import type { BuyerProfile } from '@/lib/types';
import { FactCell } from '@/components/dg/data-display';
import { BarChart, RankTable } from './charts';

const BASIS = 'm-0 max-w-prose text-small text-ink-muted';

/**
 * What a buyer's own notices add up to: how many a year, on what subjects, how long it gives to respond,
 * how often it amends, and where the notices came from. Counts of notices, never spend; the API computes
 * them from the buyer's notices of the list's default scope (WP-96: All defence; it was the core scope).
 */
export function BuyerProfileSection({ profile, name }: { profile: BuyerProfile; name: string }) {
  const w = profile.responseWindow;
  const a = profile.amendments;
  // WP-87: the years with the notices before them and those without a date, so the bars add up to the total
  const bars = profileYearBars(profile);
  const counted = bars.reduce((n, b) => n + b.primary, 0);
  const watched = amendmentsShown(a, profile.asOf);
  return (
    <section aria-labelledby="buyer-profile" className="flex flex-col gap-4">
      <h2 id="buyer-profile" className="m-0 text-h2">Profile</h2>
      <AboutData summary="How we count">
      <p className="m-0">
        Counts of {name}&apos;s {formatNumber(profile.tenderCount)} defence notices in our archive (the “Tenders in archive” above: a notice published in TED and in a national portal is one), from {profile.sources.length === 1 ? 'one source' : `${profile.sources.length} sources`}.
        They count notices, not contract value, and are only as complete as those sources: see <Link href="/data" className="font-semibold">source status</Link>.
      </p>
      </AboutData>
      <dl className="facts-grid m-0 border-b border-line">
        <FactCell label="Typical response window">
          <span>{daysText(w.median)}</span>
          <span className="block font-sans text-small font-normal text-ink-muted">
            {w.p25 !== null && w.p75 !== null ? `Middle half: ${w.p25} to ${w.p75} days. ` : ''}
            {formatNumber(w.notices)} {w.notices === 1 ? 'notice states' : 'notices state'} a deadline.
          </span>
        </FactCell>
        <FactCell label="With an amendment">
          {watched.shown ? (
            <>
              <span>{percentText(a.share)}</span>
              <span className="block font-sans text-small font-normal text-ink-muted">
                {formatNumber(a.amended)} of {formatNumber(a.notices)} {plural(a.notices, 'notice')}, counted from when we first saw each one ({watched.since}).
              </span>
            </>
          ) : (
            <span className="block font-sans text-small font-normal text-ink-muted" data-amendments-pending>
              Not shown yet: we have watched this buyer’s notices only since {watched.since}, too short to say how often it amends. Shown after six months.
            </span>
          )}
        </FactCell>
      </dl>

      <div className="grid gap-4 lg:grid-cols-2">
        <div className="flex min-w-0 flex-col gap-3 rounded-lg border border-transparent bg-surface p-5 sm:p-7">
          <h3 className="m-0 text-h3">Notices per year</h3>
          <BarChart
            id="buyer-years"
            title={`Notices published per year by ${name}`}
            summary={`${formatNumber(counted)} ${plural(counted, 'notice')}, the total above.`}
            bars={bars}
            primaryName="Notices"
            labelHeader="Year"
          />
          <p className={BASIS}>{profile.basis.perYear}</p>
        </div>

        <div className="flex min-w-0 flex-col gap-6">
          <div className="flex flex-col gap-3 rounded-lg border border-transparent bg-surface p-5 sm:p-7">
            <h3 className="m-0 text-h3">Subjects</h3>
            {profile.cpvGroups.length > 0 ? (
              <RankTable
                caption={`Notices by CPV group, ${name}`}
                labelHeader="CPV group"
                rows={profile.cpvGroups.map((g) => ({
                  key: g.group,
                  label: <span><span className="font-mono tabular-nums">{g.group}</span> <span>{cpvGroupName(g.group) ?? 'Group'}</span></span>,
                  count: g.count,
                }))}
              />
            ) : (
              <p className="m-0 text-body text-ink-muted">These notices state no CPV code.</p>
            )}
            <p className={BASIS}>{profile.basis.cpvGroups}</p>
          </div>
          <div className="flex flex-col gap-3 rounded-lg border border-transparent bg-surface p-5 sm:p-7">
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
