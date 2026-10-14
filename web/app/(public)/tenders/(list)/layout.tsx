import { permanentRedirect } from 'next/navigation';
import { getTenders } from '@/lib/api';
import { lastPage, parseTenderFilters, toTenderQuery } from '@/lib/filters';
import { forwardedSearch } from '@/lib/list-bounds';

/**
 * A page past the end answers 308 to the last page here, ahead of the loading skeleton. The fetch is the page's own
 * (the same request, so it is made once); page 1 never passes through, and a list that failed is left to the page's
 * error state.
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
