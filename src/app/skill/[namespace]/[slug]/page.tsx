import Navigation from "@/components/navigation";
import SkillDetailsView from "@/components/search/skill-details-view";
import SiteFooter from "@/components/site-footer";

export default async function SkillDetailsPage({
  params,
}: {
  params: Promise<{ namespace: string; slug: string }>;
}) {
  const { namespace, slug } = await params;

  return (
    <main className="relative min-h-screen">
      <Navigation />
      <SkillDetailsView namespace={namespace} slug={slug} />
      <SiteFooter />
    </main>
  );
}
