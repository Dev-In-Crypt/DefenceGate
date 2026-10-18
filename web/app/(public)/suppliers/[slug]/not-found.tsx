import { EmptyState } from '@/components/dg/feedback';
import { Button } from '@/components/dg/button';

export default function SupplierNotFound() {
  return (
    <EmptyState title="Supplier not found" action={<Button variant="secondary" href="/suppliers">Back to the supplier map</Button>}>
      No supplier with this address is on the map. It is built from the winners named in TED result notices, so a company that won
      contracts elsewhere is not on it.
    </EmptyState>
  );
}
