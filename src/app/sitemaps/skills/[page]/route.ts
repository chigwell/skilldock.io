import { buildUrlSetXml, getSkillsSitemapEntries, sitemapXmlResponse } from "@/lib/sitemap";

interface RouteContext {
  params: Promise<{ page: string }>;
}

export async function GET(_: Request, context: RouteContext): Promise<Response> {
  const { page } = await context.params;
  const pageNumber = Number.parseInt(page, 10);
  const entries = await getSkillsSitemapEntries(pageNumber);

  return sitemapXmlResponse(
    buildUrlSetXml(entries.map((entry) => ({ loc: entry.url, lastmod: entry.lastModified }))),
  );
}
