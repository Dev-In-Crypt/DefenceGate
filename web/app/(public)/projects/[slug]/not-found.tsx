import { EmptyState } from '@/components/dg/feedback';
import { Button } from '@/components/dg/button';

export default function ProjectNotFound() {
  return (
    <EmptyState title="This project is not in our data" action={<Button href="/organisations">Browse organisations</Button>}>
      The link may be wrong. Projects are those of CORDIS (Horizon Europe, Horizon 2020, FP7) and the European Defence Fund factsheets.
    </EmptyState>
  );
}
