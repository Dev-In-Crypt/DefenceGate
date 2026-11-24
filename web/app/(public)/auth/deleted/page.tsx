import type { Metadata } from 'next';
import { ContentPage } from '@/components/dg/content-page';
import { Done } from '@/components/account/confirm-form';

export const metadata: Metadata = { title: 'Account deleted', robots: { index: false, follow: false } };

/** E-20: where deleting the account lands (it went to the home page without a word). Says only what happened; reads no cookie. */
export default function DeletedPage() {
  return (
    <ContentPage crumbs={[{ label: 'Home', href: '/' }, { label: 'Account deleted', href: '/auth/deleted' }]} title="Account deleted">
      <Done title="Your account is deleted" href="/" action="Go to the home page">
        Your address, profile, saved searches, shortlist, follows and sessions are removed, and you are signed out everywhere.
        A new account can be made with the same address at any time.
      </Done>
    </ContentPage>
  );
}
