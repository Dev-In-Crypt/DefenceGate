import { redirect } from 'next/navigation';
import { getBuyers } from '@/lib/api';
import { lastPage, parseBuyerFilters, toBuyerQuery } from '@/lib/filters';
import { forwardedSearch } from '@/lib/list-bounds';

/**
 * A page past the end answers 307 (temporary: the last page moves as the list grows; WP-116) to the last page here, before the page renders (see lib/list-bounds.ts).
 *
 * No loading.tsx beside this layout, on purpose (WP-54, as for /funding in WP-43): a loading file wraps the page in a Suspense boundary, and the
 * server then sends the skeleton in place and the list as a hidden block that only a script swaps in. Without scripts (and for a crawler that
 * runs none) the page said "Loading". Without it the first page of buyers is ordinary HTML in the first response.
 */
export default async function BuyersListLayout({ children }: { children: React.ReactNode }) {
  const sp = await forwardedSearch();
  if (sp) {
    const filters = parseBuyerFilters(sp);
    let target: string | null = null;
    try {
      const result = await getBuyers(filters);
      const last = lastPage(result.total, result.pageSize);
      if (result.total > 0 && (filters.page ?? 1) > last) target = `/buyers${toBuyerQuery({ ...filters, page: last })}`;
    } catch {
      target = null;
    }
    if (target) redirect(target);
  }
  return children;
}
