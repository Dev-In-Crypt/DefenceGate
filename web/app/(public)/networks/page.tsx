import { permanentRedirect } from 'next/navigation';

/** WP-175 (D-19): the Partners group has no page of its own; its address leads to the organisations list instead of a 404. */
export default function NetworksPage() {
  permanentRedirect('/organisations');
}
