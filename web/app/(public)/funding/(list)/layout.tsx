import { permanentRedirect } from 'next/navigation';
import { getCalls } from '@/lib/api';
import { lastPage, parseCallFilters, parseView, toQuery } from '@/lib/filters';
import { forwardedSearch } from '@/lib/list-bounds';

/** A page past the end answers 308 to the last page here, ahead of the loading skeleton (see lib/list-bounds.ts). */
export default async function FundingListLayout({ children }: { children: React.ReactNode }) {
  const sp = await forwardedSearch();
  if (sp && parseView(sp) === 'list') {
    const filters = parseCallFilters(sp);
    let target: string | null = null;
    try {
      const result = await getCalls(filters);
      const last = lastPage(result.total, result.pageSize);
      if (result.total > 0 && (filters.page ?? 1) > last) target = `/funding${toQuery({ ...filters, page: last })}`;
    } catch {
      target = null;
    }
    if (target) permanentRedirect(target);
  }
  return children;
}
