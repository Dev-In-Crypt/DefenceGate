/**
 * The line a readiness form shows until its script has read the saved answers from this browser. Without JavaScript that
 * never happens: the line is hidden and a notice says what is needed (WP-116: "Loading your saved answers…" stood forever).
 */
export function SavedAnswersLoading() {
  // F-5: the space of a step of the form is held while the answers load, so the form does not push the page down when it appears
  // (layout shift 0.35 on /readiness and /readiness/supplier at 1440 px)
  return (
    <div className="min-h-[36rem]">
      <p role="status" data-js-loading className="m-0 text-body text-ink-muted">Loading your saved answers from this browser…</p>
      <noscript>
        <style>{'[data-js-loading]{display:none}'}</style>
        <p data-noscript-notice className="m-0 max-w-prose rounded-md bg-surface-inset px-4 py-3 text-body text-ink">
          This form needs JavaScript: your answers are kept in this browser by a script on this page. Turn JavaScript on to fill it in.
        </p>
      </noscript>
    </div>
  );
}
