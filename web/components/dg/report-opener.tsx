'use client';

import { useState } from 'react';
import { Button } from './button';

/**
 * A counted report is made by a button, not by opening its page: `open` is a server action (a POST) that counts the report and returns
 * it rendered, or the refusal. Until then the page shows `children` and the button.
 */
export function ReportOpener({ slug, open, label, children }: {
  slug: string; open: (slug: string) => Promise<React.ReactNode>; label: string; children?: React.ReactNode;
}) {
  const [node, setNode] = useState<React.ReactNode>(null);
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);
  if (node !== null) return <>{node}</>;
  const go = async () => {
    setBusy(true);
    setFailed(false);
    const got = await open(slug).catch(() => null);
    setBusy(false);
    if (got === null) { setFailed(true); return; }
    setNode(got);
    window.scrollTo({ top: 0 });
  };
  return (
    <>
      {children}
      <form className="flex flex-col items-start gap-3 print:hidden" onSubmit={(e) => { e.preventDefault(); void go(); }} data-report-open>
        {failed && <p className="m-0 font-semibold text-alert" role="alert">The report could not be made just now. Try again in a moment.</p>}
        <Button type="submit" disabled={busy}>{busy ? 'Making the report…' : label}</Button>
      </form>
    </>
  );
}
