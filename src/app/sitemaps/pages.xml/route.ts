import { getSiteUrl } from "@/lib/site-url";
import { buildUrlSetXml, sitemapXmlResponse } from "@/lib/sitemap";

export async function GET(): Promise<Response> {
  const siteUrl = getSiteUrl();
  const now = new Date().toISOString();

  const pages = [
    { loc: `${siteUrl}/`, changefreq: "daily", priority: "1.0" },
    { loc: `${siteUrl}/search`, changefreq: "daily", priority: "0.9" },
    { loc: `${siteUrl}/trending`, changefreq: "hourly", priority: "0.8" },
    { loc: `${siteUrl}/terms`, changefreq: "monthly", priority: "0.2" },
    { loc: `${siteUrl}/privacy`, changefreq: "monthly", priority: "0.2" },
  ].map((page) => ({ ...page, lastmod: now }));

  return sitemapXmlResponse(buildUrlSetXml(pages));
}
