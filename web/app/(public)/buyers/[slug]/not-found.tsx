import { EmptyState } from '@/components/dg/feedback';
import { Button } from '@/components/dg/button';

export default function BuyerNotFound() {
  return (
    <EmptyState title="This buyer is not in the directory" action={<Button href="/buyers">Browse buyers</Button>}>
      The link may be wrong, or the buyer has no notices in our archive.
    </EmptyState>
  );
}
