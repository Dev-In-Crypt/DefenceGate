import type { Metadata } from 'next';
import Link from 'next/link';
import { dataOrNull, getAssociation } from '@/lib/account';
import { formatStamp } from '@/lib/account-format';
import { DIGEST_COUNTRIES } from '@/lib/digest';
import { PLAN_LABELS } from '@/lib/plans';
import { Button } from '@/components/dg/button';
import { Select, TextInput } from '@/components/dg/form';
import { AppHeader, Block, LoadFailed, Notice } from '@/components/account/ui';
import { saveAssociationDigest } from '../actions';

export const dynamic = 'force-dynamic';
export const metadata: Metadata = { title: 'Association', robots: { index: false, follow: false } };

type Props = { searchParams: Promise<{ n?: string | string[] }> };

const COUNTRY_OPTIONS = [{ value: '', label: 'All countries' },
  ...Object.entries(DIGEST_COUNTRIES).map(([value, label]) => ({ value, label })).sort((a, b) => a.label.localeCompare(b.label))];

/** WP-158: the cluster licence. The membership and the plan it gives, and the weekly digest under the association's name. */
export default async function AssociationPage({ searchParams }: Props) {
  const [result, { n }] = await Promise.all([getAssociation(), searchParams]);
  if (!result.ok && result.status === 404) {
    return (
      <>
        <AppHeader title="Association" />
        <p className="m-0 max-w-prose text-body text-ink-muted" data-association-none>This account is not a member of an association with a licence.</p>
      </>
    );
  }
  const a = dataOrNull(result);
  if (!a) return <LoadFailed href="/app/association" />;
  return (
    <>
      <AppHeader title={a.name} lead="Your account is part of this association's licence." />
      <Notice code={n} />

      <Block id="membership" title="Membership">
        <p className="m-0 max-w-prose text-body" data-association-plan>
          Through {a.name} your account has the {PLAN_LABELS[a.plan]} features{a.role === 'admin' ? ', as the association\'s admin' : ''}, for as long as the association&apos;s licence runs{a.licensedUntil ? <> (it ends at {formatStamp(a.licensedUntil)})</> : null}.
        </p>
        <p className="m-0 font-mono text-mono text-ink-muted">Member since {formatStamp(a.memberSince)}</p>
        {a.seats && (
          <p className="m-0 max-w-prose text-body text-ink-muted" data-association-seats>
            {a.seats.used} of {a.seats.cap} seats are used. To add or remove a member, write to us through the contact details in the <Link href="/imprint" className="font-semibold">imprint</Link>.
          </p>
        )}
      </Block>

      <Block id="digest" title="Weekly digest by e-mail">
        <p className="m-0 max-w-prose text-body text-ink-muted">
          Once a week, after the week ends: its new and amended defence tenders and funding calls, sent in the name of {a.name}: the same issue as
          the public <Link href="/digest" className="font-semibold">weekly digest</Link>, for the country and CPV codes you choose.
          {a.digest.lastWeek && <> Last sent: week {a.digest.lastWeek}.</>}
        </p>
        <form action={saveAssociationDigest} className="flex max-w-form flex-col gap-4" data-association-digest>
          <Select name="on" label="Send me the digest" defaultValue={a.digest.on ? 'on' : 'off'}
            options={[{ value: 'on', label: 'Yes, every week' }, { value: 'off', label: 'No' }]} />
          <Select name="country" label="Country" defaultValue={a.digest.country ?? ''} options={COUNTRY_OPTIONS} />
          <TextInput name="cpv" label="CPV codes" defaultValue={a.digest.cpv.join(', ')} maxLength={400}
            hint="Optional. Codes or their first digits, separated by commas (35, 3441): the tenders are narrowed to them. Funding calls have no CPV code and are all listed." />
          <div><Button type="submit">Save</Button></div>
        </form>
      </Block>
    </>
  );
}
