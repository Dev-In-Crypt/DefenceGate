import { permanentRedirect } from 'next/navigation';
import { getTenders } from '@/lib/api';
import { lastPage, parseTenderFilters, toTenderQuery } from '@/lib/filters';
import { forwardedSearch } from '@/lib/list-bounds';

/**
 * A page past the end answers 308 to the last page here, before the page renders. The fetch is the page's own
 * (the same request, so it is made once); page 1 never passes through, and a list that failed is left to the page's
 * error state.
 *
 * No loading.tsx beside this layout, on purpose (WP-54, as for /funding in WP-43): a loading file wraps the page in a Suspense boundary, and the
 * server then sends the skeleton in place and the notices as a hidden block that only a script swaps in. Without scripts (and for a crawler that
 * runs none) the page said "Loading". Without it the first page of tenders is ordinary HTML in the first response.
 */
export default async function TendersListLayout({ children }: { children: React.ReactNode }) {
  const sp = await forwardedSearch();
  if (sp) {
    const filters = parseTenderFilters(sp);
    let target: string | null = null;
    try {
      const result = await getTenders(filters);
      const last = lastPage(result.total, result.pageSize);
      if (result.total > 0 && (filters.page ?? 1) > last) target = `/tenders${toTenderQuery({ ...filters, page: last })}`;
    } catch {
      target = null;
    }
    if (target) permanentRedirect(target);
  }
  return children;
}
