import { EmptyState } from '@/components/dg/feedback';
import { Button } from '@/components/dg/button';

export default function CallNotFound() {
  return (
    <EmptyState title="This call is not in the directory" action={<Button href="/funding">Browse funding calls</Button>}>
      It may have been withdrawn at the source or the link may be wrong.
    </EmptyState>
  );
}
