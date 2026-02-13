import Navigation from "@/components/navigation";
import SkillDetailsView from "@/components/search/skill-details-view";
import SiteFooter from "@/components/site-footer";

function splitSlugAndVersion(rawSlug: string): { slug: string; version?: string } {
  const atIndex = rawSlug.lastIndexOf("@");
  if (atIndex <= 0 || atIndex === rawSlug.length - 1) {
    return { slug: rawSlug };
  }

  const slug = rawSlug.slice(0, atIndex).trim();
  const version = rawSlug.slice(atIndex + 1).trim();
  if (!slug || !version) {
    return { slug: rawSlug };
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
