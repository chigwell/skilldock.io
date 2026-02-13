import Navigation from "@/components/navigation";
import SkillDetailsView from "@/components/search/skill-details-view";
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

function splitSlugAndVersion(rawSlug: string): { slug: string; version?: string } {
  const decodedSlug = decodeSlugSegment(rawSlug);
  const atIndex = decodedSlug.lastIndexOf("@");
  if (atIndex <= 0 || atIndex === decodedSlug.length - 1) {
    return { slug: decodedSlug };
  }

  const slug = decodedSlug.slice(0, atIndex).trim();
  const version = decodedSlug.slice(atIndex + 1).trim();
  if (!slug || !version) {
    return { slug: decodedSlug };
  }

  return { slug, version };
}

export default async function SkillDetailsPage({
  params,
}: {
  params: Promise<{ namespace: string; slug: string }>;
}) {
  const { namespace, slug } = await params;
  const { slug: normalizedSlug, version } = splitSlugAndVersion(slug);

  return (
    <main className="relative min-h-screen">
      <Navigation />
      <SkillDetailsView namespace={namespace} slug={normalizedSlug} version={version} />
      <SiteFooter />
    </main>
  );
}
