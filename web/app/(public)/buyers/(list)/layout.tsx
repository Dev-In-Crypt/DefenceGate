import { permanentRedirect } from 'next/navigation';
import { getBuyers } from '@/lib/api';
import { lastPage, parseBuyerFilters, toBuyerQuery } from '@/lib/filters';
import { forwardedSearch } from '@/lib/list-bounds';

/** A page past the end answers 308 to the last page here, ahead of the loading skeleton (see lib/list-bounds.ts). */
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
    if (target) permanentRedirect(target);
  }
  return children;
}
