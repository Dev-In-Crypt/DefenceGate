import { EmptyState } from '@/components/dg/feedback';
import { Button } from '@/components/dg/button';

export default function OrganisationNotFound() {
  return (
    <EmptyState title="This organisation is not in the directory" action={<Button href="/organisations">Browse organisations</Button>}>
      The link may be wrong, or the organisation has not taken part in a project we hold.
    </EmptyState>
  );
}
