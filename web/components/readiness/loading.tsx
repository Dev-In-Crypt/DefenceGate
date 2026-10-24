/**
 * The line a readiness form shows until its script has read the saved answers from this browser. Without JavaScript that
 * never happens: the line is hidden and a notice says what is needed (WP-116: "Loading your saved answers…" stood forever).
 */
export function SavedAnswersLoading() {
  return (
    <>
      <p role="status" data-js-loading className="m-0 text-body text-ink-muted">Loading your saved answers from this browser…</p>
      <noscript>
        <style>{'[data-js-loading]{display:none}'}</style>
        <p data-noscript-notice className="m-0 max-w-prose rounded-md bg-surface-inset px-4 py-3 text-body text-ink">
          This form needs JavaScript: your answers are kept in this browser by a script on this page. Turn JavaScript on to fill it in.
        </p>
      </noscript>
    </>
  );
}
