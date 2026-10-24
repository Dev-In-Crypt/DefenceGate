import { getTenderSitemapPage } from '@/lib/api';
import { withEtag } from '@/lib/etag';
import { absoluteUrl } from '@/lib/seo';
import { XML_HEADERS, sitemapFiles, sitemapIndex } from '@/lib/sitemap';

/** WP-114: the sitemap index: the pages, the suppliers and the tenders as files of their own (app/sitemaps/[name]). */
export async function GET(request: Request): Promise<Response> {
  const pages = await getTenderSitemapPage(0).then((p) => p.pages).catch(() => 1);
  const body = sitemapIndex(sitemapFiles(pages).map((f) => ({ url: absoluteUrl(`/sitemaps/${f}`) })));
  return withEtag(request, new Response(body, { headers: XML_HEADERS }));
}
