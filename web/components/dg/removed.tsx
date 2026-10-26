import { ContentPage } from './content-page';
import { PERSON_NOT_SHOWN } from '@/lib/api';

/**
 * WP-143 (owner, 26 October 2026): the page of a buyer withheld because the name identifies a private person. Nobody asked, so it
 * does not say "on request"; it names nobody. Not indexed (the buyer page's metadata).
 */
export function NotShownPerson() {
  return (
    <ContentPage
      crumbs={[{ label: 'Home', href: '/' }, { label: 'Buyers', href: '/buyers' }, { label: 'Name not shown', href: '/buyers' }]}
      title="Name not shown"
      lead={`${PERSON_NOT_SHOWN} Its notices are still listed, without the name.`}
    />
  );
}

/**
 * What a detail address shows for a notice, buyer or call that was removed on request (the API answers 410). Neutral
 * on purpose: it says nothing about why or who asked. The page is not indexed (its callers return noindex metadata).
 */
export function RemovedOnRequest({ what }: { what: 'notice' | 'buyer' | 'call' | 'organisation' | 'supplier' }) {
  const noun = what === 'notice' ? 'notice' : what === 'buyer' ? 'buyer page' : what === 'organisation' ? 'organisation page' : what === 'supplier' ? 'supplier page' : 'funding call';
  // An organisation page is also refused for an entry that looks like a natural person (nobody asked): say both.
  const person = what === 'organisation';
  return (
    <ContentPage
      crumbs={[{ label: 'Home', href: '/' }, { label: person ? 'Not shown' : 'Removed on request', href: '/' }]}
      title={person ? 'Not shown' : 'Removed on request'}
      lead={person
        ? 'This organisation page is not shown. It was removed on request, or the entry is the name of a natural person, which DefenceGate does not publish.'
        : `This ${noun} was removed from DefenceGate on request. It is no longer shown or listed here.`}
    />
  );
}
