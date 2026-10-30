import { Button } from '../dg/button';
import { Select } from '../dg/form';
import type { ClientProfile } from '@/lib/workspace';
import { chooseClient } from '@/app/(app)/app/team/actions';

/**
 * WP-157: which client profile the searches, the shortlist and the company report work on. A form (works without script); the
 * choice is a cookie of this site, checked by the API at every use.
 */
export function ClientSwitcher({ clients, active, back }: { clients: ClientProfile[]; active: ClientProfile | null; back: string }) {
  if (clients.length === 0) return null;
  return (
    <form action={chooseClient} className="flex flex-wrap items-end gap-3 rounded-lg border border-transparent bg-surface p-4" data-client-switcher>
      <input type="hidden" name="back" value={back} />
      <Select name="clientId" label="Working on" defaultValue={active?.id ?? ''} className="min-w-56"
        options={[{ value: '', label: 'All clients' }, ...clients.map((c) => ({ value: c.id, label: c.name }))]} />
      <Button type="submit" variant="secondary">Show</Button>
    </form>
  );
}
