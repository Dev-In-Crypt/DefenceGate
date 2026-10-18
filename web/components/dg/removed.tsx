import { ContentPage } from './content-page';

/**
 * What a detail address shows for a notice, buyer or call that was removed on request (the API answers 410). Neutral
 * on purpose: it says nothing about why or who asked. The page is not indexed (its callers return noindex metadata).
 */
export function RemovedOnRequest({ what }: { what: 'notice' | 'buyer' | 'call' | 'organisation' | 'supplier' }) {
  const noun = what === 'notice' ? 'notice' : what === 'buyer' ? 'buyer page' : what === 'organisation' ? 'organisation page' : what === 'supplier' ? 'supplier page' : 'funding call';
  return (
    <ContentPage
      crumbs={[{ label: 'Home', href: '/' }, { label: 'Removed on request', href: '/' }]}
      title="Removed on request"
      lead={`This ${noun} was removed from DefenceGate on request. It is no longer shown or listed here.`}
    />
  );
}
