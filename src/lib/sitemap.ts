import { API_BASE_URL } from "@/lib/api";
import { getSiteUrl } from "@/lib/site-url";

const DEFAULT_SITEMAP_SKILLS_PER_PAGE = 100;
const DEFAULT_SKILLS_SITEMAP_PAGES = 1;

interface StatsResponse {
  stats?: {
    total_skills?: unknown;
    totalSkills?: unknown;
  };
  data?: {
    total_skills?: unknown;
    totalSkills?: unknown;
    stats?: {
      total_skills?: unknown;
      totalSkills?: unknown;
    };
  };
  total_skills?: unknown;
  totalSkills?: unknown;
}

interface SkillItem {
  namespace?: unknown;
  slug?: unknown;
  updated_at?: unknown;
  updatedAt?: unknown;
  skill?: {
    namespace?: unknown;
    slug?: unknown;
    updated_at?: unknown;
    updatedAt?: unknown;
  };
}

interface SkillsResponse {
  items?: unknown;
  skills?: unknown;
  results?: unknown;
  data?: {
    items?: unknown;
    skills?: unknown;
    results?: unknown;
  };
}

function asPositiveInteger(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value) && value > 0) {
    return Math.floor(value);
  }
  if (typeof value === "string") {
    const parsed = Number.parseInt(value, 10);
    if (Number.isFinite(parsed) && parsed > 0) return parsed;
  }
  return null;
}

function getSitemapSkillsPerPageValue(): number {
  const configured = asPositiveInteger(process.env.SITEMAP_SKILLS_PER_PAGE);
  if (!configured) return DEFAULT_SITEMAP_SKILLS_PER_PAGE;
  return Math.min(configured, 1000);
}

function escapeXml(value: string): string {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&apos;");
}

function isValidIsoDate(value: unknown): value is string {
  if (typeof value !== "string" || !value.trim()) return false;
  return !Number.isNaN(Date.parse(value));
}

export function sitemapXmlResponse(xmlBody: string): Response {
  return new Response(xmlBody, {
    headers: {
      "Content-Type": "application/xml; charset=utf-8",
      "Cache-Control": "public, s-maxage=900, stale-while-revalidate=86400",
    },
  });
}

export async function getSkillsSitemapPageCount(): Promise<number> {
  const perPage = getSitemapSkillsPerPageValue();
  try {
    const response = await fetch(`${API_BASE_URL}/v1/stats`, {
      next: { revalidate: 900 },
    });
    if (!response.ok) return DEFAULT_SKILLS_SITEMAP_PAGES;

    const payload = (await response.json()) as StatsResponse;
    const totalSkills =
      asPositiveInteger(payload.total_skills) ??
      asPositiveInteger(payload.totalSkills) ??
      asPositiveInteger(payload.stats?.total_skills) ??
      asPositiveInteger(payload.stats?.totalSkills) ??
      asPositiveInteger(payload.data?.total_skills) ??
      asPositiveInteger(payload.data?.totalSkills) ??
      asPositiveInteger(payload.data?.stats?.total_skills) ??
      asPositiveInteger(payload.data?.stats?.totalSkills);
    if (!totalSkills) return DEFAULT_SKILLS_SITEMAP_PAGES;

    return Math.max(1, Math.ceil(totalSkills / perPage));
  } catch {
    return DEFAULT_SKILLS_SITEMAP_PAGES;
  }
}

export async function getSkillsSitemapEntries(page: number): Promise<
  Array<{
    url: string;
    lastModified?: string;
  }>
> {
  const safePage = Number.isFinite(page) && page > 0 ? Math.floor(page) : 1;
  const perPage = getSitemapSkillsPerPageValue();
  const params = new URLSearchParams({
    page: String(safePage),
    per_page: String(perPage),
  });

  try {
    const response = await fetch(`${API_BASE_URL}/v1/skills?${params.toString()}`, {
      next: { revalidate: 900 },
    });
    if (!response.ok) return [];

    const payload = (await response.json()) as SkillsResponse;
    const itemsCandidate =
      payload.items ?? payload.skills ?? payload.results ?? payload.data?.items ?? payload.data?.skills ?? payload.data?.results;
    const items = Array.isArray(itemsCandidate) ? itemsCandidate : [];
    const siteUrl = getSiteUrl();

    return items.flatMap((raw) => {
      const skill = raw as SkillItem;
      const namespace =
        typeof skill.namespace === "string"
          ? skill.namespace
          : typeof skill.skill?.namespace === "string"
            ? skill.skill.namespace
            : null;
      const slug =
        typeof skill.slug === "string"
          ? skill.slug
          : typeof skill.skill?.slug === "string"
            ? skill.skill.slug
            : null;
      if (!namespace || !slug) {
        return [];
      }

      const encodedNamespace = encodeURIComponent(namespace);
      const encodedSlug = encodeURIComponent(slug);
      const url = `${siteUrl}/skill/${encodedNamespace}/${encodedSlug}`;
      const updatedAtRaw =
        skill.updated_at ?? skill.updatedAt ?? skill.skill?.updated_at ?? skill.skill?.updatedAt;
      const lastModified = isValidIsoDate(updatedAtRaw)
        ? new Date(updatedAtRaw).toISOString()
        : undefined;

      return [{ url, lastModified }];
    });
  } catch {
    return [];
  }
}

export function buildSitemapIndexXml(
  sitemaps: Array<{ loc: string; lastmod?: string }>,
): string {
  const urls = sitemaps
    .map(({ loc, lastmod }) => {
      const safeLoc = escapeXml(loc);
      const safeLastmod = lastmod ? `<lastmod>${escapeXml(lastmod)}</lastmod>` : "";
      return `<sitemap><loc>${safeLoc}</loc>${safeLastmod}</sitemap>`;
    })
    .join("");

  return `<?xml version="1.0" encoding="UTF-8"?>` +
    `<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">${urls}</sitemapindex>`;
}

export function buildUrlSetXml(
  urls: Array<{ loc: string; lastmod?: string; changefreq?: string; priority?: string }>,
): string {
  const entries = urls
    .map(({ loc, lastmod, changefreq, priority }) => {
      const safeLoc = escapeXml(loc);
      const safeLastmod = lastmod ? `<lastmod>${escapeXml(lastmod)}</lastmod>` : "";
      const safeChangeFreq = changefreq
        ? `<changefreq>${escapeXml(changefreq)}</changefreq>`
        : "";
      const safePriority = priority ? `<priority>${escapeXml(priority)}</priority>` : "";
      return `<url><loc>${safeLoc}</loc>${safeLastmod}${safeChangeFreq}${safePriority}</url>`;
    })
    .join("");

  return `<?xml version="1.0" encoding="UTF-8"?>` +
    `<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">${entries}</urlset>`;
}

export function getSkillsSitemapPerPage(): number {
  return getSitemapSkillsPerPageValue();
}
