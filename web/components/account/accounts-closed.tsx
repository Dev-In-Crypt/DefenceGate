import { Callout } from '../dg/blocks';
import { Button } from '../dg/button';

/**
 * What every account page shows while the API says accounts are not open: no mail provider that passed its check yet, or the
 * privacy notice for password accounts not published yet (backend accounts.accounts_problem).
 */
export function AccountsClosed() {
  return (
    <Callout title="Sign-in is not open yet">
      <p className="m-0">Sign-in opens soon. Until then accounts are not available. Browsing tenders, buyers and funding calls needs no account.</p>
      <div className="flex flex-wrap gap-3 pt-2">
        <Button href="/tenders" variant="secondary">Browse tenders</Button>
        <Button href="/funding" variant="secondary">Browse funding calls</Button>
      </div>
    </Callout>
  );
}
