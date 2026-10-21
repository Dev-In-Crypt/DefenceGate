import { EmptyState } from '@/components/dg/feedback';
import { Button } from '@/components/dg/button';

export default function TenderNotFound() {
  return (
    <EmptyState level="h1" title="This tender is not in the directory" action={<Button href="/tenders">Browse tenders</Button>}>
      The link may be wrong, or the notice is not one we collect.
    </EmptyState>
  );
}
