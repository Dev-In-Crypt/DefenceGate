import { BUYER_COUNTRIES, TENDER_SCOPES } from '@/lib/taxonomy';
import { CADENCE_LABEL, ROLE_LABEL } from '@/lib/account-format';
import type { Cadence, Profile, Role } from '@/lib/types';
import { Choice, Fieldset, Select } from '../dg/form';

const trackValue = (p: Profile): 'tenders' | 'funding' | 'both' =>
  p.tracks.length === 1 ? p.tracks[0] : 'both';

/**
 * The five profile fields, shared by the welcome page and Settings. Plain form controls: the form posts to a
 * server action and works without script. Free-text fields do not exist on purpose.
 */
export function ProfileFields({ profile }: { profile: Profile }) {
  const tracks = trackValue(profile);
  // A saved code that is not in the buyer-country list stays selectable, so saving never drops it.
  const extra = profile.countries.filter((c) => !(c in BUYER_COUNTRIES));
  const countries = [...Object.keys(BUYER_COUNTRIES), ...extra];
  return (
    <div className="flex flex-col gap-6">
      <Select
        name="role" label="Your role" defaultValue={profile.role ?? 'supplier'}
        options={(Object.keys(ROLE_LABEL) as Role[]).map((r) => ({ value: r, label: ROLE_LABEL[r] }))}
      />
      <Fieldset legend="What do you want to follow?">
        {([['tenders', 'Tenders'], ['funding', 'Funding calls'], ['both', 'Both']] as const).map(([v, l]) => (
          <Choice key={v} type="radio" name="tracks" value={v} label={l} defaultChecked={tracks === v} />
        ))}
      </Fieldset>
      <Fieldset legend="Countries (optional, up to 20)">
        <div className="grid sm:grid-cols-2 lg:grid-cols-3">
          {countries.map((c) => (
            <Choice key={c} name="countries" value={c} defaultChecked={profile.countries.includes(c)}
              label={<span className="inline-flex gap-2"><span className="font-mono text-mono-strong">{c}</span>{BUYER_COUNTRIES[c] ?? ''}</span>} />
          ))}
        </div>
      </Fieldset>
      <Fieldset legend="Scope">
        <Choice type="radio" name="scope" value="core" label="Defence only" hint={TENDER_SCOPES.core.hint} defaultChecked={profile.scope === 'core'} />
        <Choice type="radio" name="scope" value="all" label="Include dual-use and supply notices" hint={TENDER_SCOPES.supply.hint} defaultChecked={profile.scope === 'all'} />
      </Fieldset>
      <Select
        name="cadence" label="How often should alerts reach you?" defaultValue={profile.cadence}
        hint="The default for searches you save later. Each search can have its own."
        options={(Object.keys(CADENCE_LABEL) as Cadence[]).map((c) => ({ value: c, label: CADENCE_LABEL[c] }))}
      />
    </div>
  );
}
