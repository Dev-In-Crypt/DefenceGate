import { redirect } from 'next/navigation';
import { getCalls } from '@/lib/api';
import { lastPage, parseCallFilters, parseView, toQuery } from '@/lib/filters';
import { forwardedSearch } from '@/lib/list-bounds';

/**
 * A page past the end answers 307 (temporary: the last page moves as the list grows; WP-116) to the last page here, before the page renders (see lib/list-bounds.ts).
 *
 * There is no loading.tsx beside this layout on purpose (WP-43, verification 3): a loading file wraps the page in a Suspense boundary, and
 * the server then sends the skeleton in place and the real list as a hidden block that only a script swaps in. A visitor without scripts,
 * a crawler that does not run them and a background tab saw "Loading" and no call. Without it the first page of calls is ordinary HTML
 * in the first response. On a slow answer the browser keeps the page it is on until this one is ready.
 */
export default async function FundingListLayout({ children }: { children: React.ReactNode }) {
  const sp = await forwardedSearch();
  // WP-99: `fit=1` is every call on one page: no page to redirect
  if (sp && parseView(sp) === 'list' && sp.fit !== '1') {
    const filters = parseCallFilters(sp);
    let target: string | null = null;
    try {
      const result = await getCalls(filters);
      const last = lastPage(result.total, result.pageSize);
      if (result.total > 0 && (filters.page ?? 1) > last) target = `/funding${toQuery({ ...filters, page: last })}`;
    } catch {
      target = null;
    }
    if (target) redirect(target);
  }
  return children;
}
