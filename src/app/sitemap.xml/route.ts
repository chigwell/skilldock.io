import { getSiteUrl } from "@/lib/site-url";
import {
  buildSitemapIndexXml,
  getSkillsSitemapPageCount,
  sitemapXmlResponse,
} from "@/lib/sitemap";

export async function GET(): Promise<Response> {
  const siteUrl = getSiteUrl();
  const now = new Date().toISOString();
  const skillsPages = await getSkillsSitemapPageCount();

  const sitemaps = [
    { loc: `${siteUrl}/sitemaps/pages.xml`, lastmod: now },
    ...Array.from({ length: skillsPages }, (_, index) => ({
      loc: `${siteUrl}/sitemaps/skills/${index + 1}.xml`,
      lastmod: now,
    })),
  ];

  return sitemapXmlResponse(buildSitemapIndexXml(sitemaps));
}
