import Navigation from "@/components/navigation";
import SkillDetailsView from "@/components/search/skill-details-view";
import SiteFooter from "@/components/site-footer";
import { API_BASE_URL } from "@/lib/api";

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

function getString(value: unknown): string | null {
  return typeof value === "string" ? value : null;
}

function getDescriptionFromPayload(payload: unknown): string | null {
  if (!payload || typeof payload !== "object") return null;
  const record = payload as Record<string, unknown>;

  const release = record.release;
  if (release && typeof release === "object") {
    const releaseDescription = getString((release as Record<string, unknown>).description_md);
    if (releaseDescription) return releaseDescription;
  }

  const latestRelease = record.latest_release;
  if (latestRelease && typeof latestRelease === "object") {
    const latestDescription = getString((latestRelease as Record<string, unknown>).description_md);
    if (latestDescription) return latestDescription;
  }

  const skill = record.skill;
  if (skill && typeof skill === "object") {
    return getString((skill as Record<string, unknown>).description_md);
  }

  return null;
}

export default async function SkillDetailsPage({
  params,
  searchParams,
}: {
  params: Promise<{ namespace: string; slug: string }>;
  searchParams: Promise<{ output?: string | string[] }>;
}) {
  const { namespace, slug } = await params;
  const { output } = await searchParams;
  const { slug: normalizedSlug, version } = splitSlugAndVersion(slug);
  const outputValue = Array.isArray(output) ? output[0] : output;

  if (outputValue === "plain") {
    const encodedNamespace = encodeURIComponent(namespace);
    const encodedSlug = encodeURIComponent(normalizedSlug);
    const skillUrl = `${API_BASE_URL}/v1/skills/${encodedNamespace}/${encodedSlug}`;

    let markdown = "No description provided.";

    try {
      if (version) {
        const releaseUrl = `${skillUrl}/releases/${encodeURIComponent(version)}`;
        const releaseResponse = await fetch(releaseUrl, { cache: "no-store" });
        if (releaseResponse.ok) {
          const releasePayload = (await releaseResponse.json()) as unknown;
          const releaseMarkdown = getDescriptionFromPayload(releasePayload);
          if (releaseMarkdown) {
            markdown = releaseMarkdown;
          }
        }
      }

      if (markdown === "No description provided.") {
        const skillResponse = await fetch(skillUrl, { cache: "no-store" });
        if (skillResponse.ok) {
          const skillPayload = (await skillResponse.json()) as unknown;
          const skillMarkdown = getDescriptionFromPayload(skillPayload);
          if (skillMarkdown) {
            markdown = skillMarkdown;
          }
        }
      }
    } catch {
      markdown = "Failed to load skill instructions.";
    }

    return <pre className="whitespace-pre-wrap p-4 font-mono text-sm">{markdown}</pre>;
  }

  return (
    <main className="relative min-h-screen">
      <Navigation />
      <SkillDetailsView namespace={namespace} slug={normalizedSlug} version={version} />
      <SiteFooter />
    </main>
  );
}
