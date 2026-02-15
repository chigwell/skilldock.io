import Navigation from "@/components/navigation";
import SkillReleasesHistoryView from "@/components/search/skill-releases-history-view";
import SiteFooter from "@/components/site-footer";

function decodeSlugSegment(segment: string): string {
  let decoded = segment;
  for (let i = 0; i < 2; i += 1) {
    try {
      const next = decodeURIComponent(decoded);
      if (next === decoded) break;
      decoded = next;
    } catch {
      break;
    }
  }
  return decoded;
}

function normalizeSlug(rawSlug: string): string {
  const decodedSlug = decodeSlugSegment(rawSlug);
  const atIndex = decodedSlug.lastIndexOf("@");
  if (atIndex <= 0) {
    return decodedSlug;
  }

  const normalized = decodedSlug.slice(0, atIndex).trim();
  return normalized || decodedSlug;
}

export default async function SkillReleasesHistoryPage({
  params,
}: {
  params: Promise<{ namespace: string; slug: string }>;
}) {
  const { namespace, slug } = await params;
  const normalizedSlug = normalizeSlug(slug);

  return (
    <main className="relative min-h-screen">
      <Navigation />
      <SkillReleasesHistoryView namespace={namespace} slug={normalizedSlug} />
      <SiteFooter />
    </main>
  );
}
