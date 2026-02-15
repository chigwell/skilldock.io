"use client";

import { Check, Copy } from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import ReactMarkdown from "react-markdown";
import { buildApiUrl } from "@/lib/api";

const SKILL_DETAILS_CACHE_TTL_MS = 5 * 60 * 1000;
const SKILL_DETAILS_CACHE_KEY_PREFIX = "skill-details-page-cache-v2";

type DownloadStats = {
  total: number;
  last_week: number;
  last_month: number;
};

type SkillSummary = {
  skill: {
    namespace: string;
    slug: string;
    title: string;
    summary: string;
    homepage_url?: string | null;
    description_md: string;
    tags: string[];
    created_at: string;
    updated_at: string;
    download_stats: DownloadStats;
  };
};

type SkillRelease = {
  version: string;
  status: string;
  created_at: string;
  published_at: string | null;
  description_md: string;
  manifest?: Record<string, unknown>;
  dependencies?: Array<{
    id: string;
    namespace: string;
    slug: string;
    version_requirement: string;
    release_version: string | null;
  }>;
  download_stats?: DownloadStats;
};

type SkillReleaseItem = {
  version: string;
  status: string;
  created_at: string;
  published_at: string | null;
};

type SkillDetailsResponse = SkillSummary & {
  latest_release: SkillRelease | null;
  releases: SkillReleaseItem[];
};

type SkillReleaseResponse = SkillSummary & {
  release: SkillRelease | null;
  releases?: SkillReleaseItem[];
};

type NormalizedSkillDetails = {
  skill: SkillSummary["skill"];
  selectedRelease: SkillRelease | null;
  releases: SkillReleaseItem[];
};

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function toRelease(value: unknown): SkillRelease | null {
  if (!isObject(value) || typeof value.version !== "string") {
    return null;
  }

  return {
    version: value.version,
    status: typeof value.status === "string" ? value.status : "unknown",
    created_at: typeof value.created_at === "string" ? value.created_at : "",
    published_at: typeof value.published_at === "string" ? value.published_at : null,
    description_md: typeof value.description_md === "string" ? value.description_md : "",
    manifest: isObject(value.manifest) ? value.manifest : undefined,
    dependencies: Array.isArray(value.dependencies)
      ? (value.dependencies as SkillRelease["dependencies"])
      : undefined,
    download_stats: isObject(value.download_stats)
      ? (value.download_stats as DownloadStats)
      : undefined,
  };
}

function toReleaseItems(value: unknown): SkillReleaseItem[] {
  if (!Array.isArray(value)) return [];
  return value
    .filter(
      (item): item is SkillReleaseItem =>
        isObject(item) &&
        typeof item.version === "string" &&
        typeof item.status === "string" &&
        typeof item.created_at === "string",
    )
    .map((item) => ({
      version: item.version,
      status: item.status,
      created_at: item.created_at,
      published_at: typeof item.published_at === "string" ? item.published_at : null,
    }));
}

function normalizeSkillDetailsResponse(payload: unknown): NormalizedSkillDetails | null {
  if (!isObject(payload) || !isObject(payload.skill)) {
    return null;
  }

  const skill = payload.skill as SkillSummary["skill"];
  if (
    typeof skill.namespace !== "string" ||
    typeof skill.slug !== "string" ||
    typeof skill.title !== "string"
  ) {
    return null;
  }

  const parsedPayload = payload as Partial<SkillDetailsResponse & SkillReleaseResponse>;
  const selectedRelease = toRelease(parsedPayload.release) ?? toRelease(parsedPayload.latest_release);
  const releaseItems = toReleaseItems(parsedPayload.releases);

  if (releaseItems.length > 0) {
    return { skill, selectedRelease, releases: releaseItems };
  }
  if (selectedRelease) {
    return {
      skill,
      selectedRelease,
      releases: [
        {
          version: selectedRelease.version,
          status: selectedRelease.status,
          created_at: selectedRelease.created_at,
          published_at: selectedRelease.published_at,
        },
      ],
    };
  }

  return { skill, selectedRelease: null, releases: [] };
}

function extractReleaseFromPayload(payload: unknown): SkillRelease | null {
  if (!isObject(payload)) return null;
  return toRelease(payload.release);
}

function getCached<T>(key: string): T | null {
  try {
    const cachedRaw = localStorage.getItem(key);
    if (!cachedRaw) return null;
    const cached = JSON.parse(cachedRaw) as { timestamp: number; data: T };
    if (Date.now() - cached.timestamp > SKILL_DETAILS_CACHE_TTL_MS) {
      localStorage.removeItem(key);
      return null;
    }
    return cached.data;
  } catch {
    localStorage.removeItem(key);
    return null;
  }
}

function setCached<T>(key: string, data: T) {
  localStorage.setItem(key, JSON.stringify({ timestamp: Date.now(), data }));
}

function formatDate(iso: string | null | undefined): string {
  if (!iso) return "N/A";
  try {
    return new Date(iso).toLocaleDateString();
  } catch {
    return iso;
  }
}

function asString(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value : null;
}

function formatCount(value: number): string {
  return new Intl.NumberFormat().format(value);
}

export default function SkillDetailsView({
  namespace,
  slug,
  version,
}: {
  namespace: string;
  slug: string;
  version?: string;
}) {
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<NormalizedSkillDetails | null>(null);
  const [isCopied, setIsCopied] = useState(false);
  const [isPromptCopied, setIsPromptCopied] = useState(false);

  const cacheKey = useMemo(
    () =>
      `${SKILL_DETAILS_CACHE_KEY_PREFIX}:${namespace}/${slug}${version ? `@${version}` : ""}`,
    [namespace, slug, version],
  );

  useEffect(() => {
    let isCancelled = false;
    const loadSkill = async () => {
      setIsLoading(true);
      setError(null);

      const cached = getCached<NormalizedSkillDetails>(cacheKey);
      if (cached) {
        if (!isCancelled) {
          setData(cached);
          setIsLoading(false);
        }
        return;
      }

      try {
        const encodedNamespace = encodeURIComponent(namespace);
        const encodedSlug = encodeURIComponent(slug);
        const skillPath = `/v1/skills/${encodedNamespace}/${encodedSlug}`;

        let parsed: NormalizedSkillDetails | null = null;
        if (version) {
          const releasePath = `${skillPath}/releases/${encodeURIComponent(version)}`;
          const [skillResponse, releaseResponse] = await Promise.all([
            fetch(buildApiUrl(skillPath)),
            fetch(buildApiUrl(releasePath)),
          ]);

          if (!skillResponse.ok || !releaseResponse.ok) {
            throw new Error(
              `Failed with skill=${skillResponse.status} release=${releaseResponse.status}`,
            );
          }

          const [skillRaw, releaseRaw] = (await Promise.all([
            skillResponse.json(),
            releaseResponse.json(),
          ])) as [unknown, unknown];
          const base = normalizeSkillDetailsResponse(skillRaw);
          const selectedRelease = extractReleaseFromPayload(releaseRaw);
          if (!base || !selectedRelease) {
            throw new Error("Unexpected response shape");
          }
          parsed = {
            skill: base.skill,
            releases: base.releases,
            selectedRelease,
          };
        } else {
          const response = await fetch(buildApiUrl(skillPath));
          if (!response.ok) {
            throw new Error(`Failed with ${response.status}`);
          }
          const parsedRaw = (await response.json()) as unknown;
          parsed = normalizeSkillDetailsResponse(parsedRaw);
          if (!parsed) {
            throw new Error("Unexpected response shape");
          }
        }

        setCached(cacheKey, parsed);
        if (!isCancelled) {
          setData(parsed);
        }
      } catch (err) {
        const reason = err instanceof Error && err.message ? ` (${err.message})` : "";
        if (!isCancelled) {
          setError(
            version
              ? `Failed to load this release${reason}.`
              : `Failed to load skill details${reason}.`,
          );
        }
      } finally {
        if (!isCancelled) {
          setIsLoading(false);
        }
      }
    };

    void loadSkill();
    return () => {
      isCancelled = true;
    };
  }, [cacheKey, namespace, slug, version]);

  const selectedVersion = data?.selectedRelease?.version ?? version;
  const skillIdentifier = `${namespace}/${slug}${selectedVersion ? `@${selectedVersion}` : ""}`;
  const installCommand = `skilldock install ${skillIdentifier}`;
  const selectedDescription = data?.selectedRelease?.description_md.trim() ?? "";
  const fallbackDescription = data?.skill.description_md.trim() ?? "";
  const descriptionMd = selectedDescription || fallbackDescription;
  const plainDescription = descriptionMd || "No description provided.";
  const llmInstructions = `To use this skill you need to install skilldock (if not already before):
Install the CLI
Preferred (pipx):
pipx install --force skilldock
skilldock --version
Fallback (pip, user mode):
python3 -m pip install --user --upgrade skilldock
skilldock --version

Install this skill:
skilldock install ${skillIdentifier}

${plainDescription}`;

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(installCommand);
      setIsCopied(true);
      window.setTimeout(() => setIsCopied(false), 1500);
    } catch {
      setIsCopied(false);
    }
  };

  const handleCopyPrompt = async () => {
    try {
      await navigator.clipboard.writeText(llmInstructions);
      setIsPromptCopied(true);
      window.setTimeout(() => setIsPromptCopied(false), 1500);
    } catch {
      setIsPromptCopied(false);
    }
  };

  if (isLoading) {
    return (
      <section className="relative overflow-hidden bg-slate-50 py-12 dark:bg-black">
        <div className="relative mx-auto w-full max-w-6xl px-4">
          <div className="mt-[75px] text-sm text-slate-700 dark:text-slate-300">
            Loading skill details...
          </div>
        </div>
      </section>
    );
  }

  if (error || !data) {
    return (
      <section className="relative overflow-hidden bg-slate-50 py-12 dark:bg-black">
        <div className="relative mx-auto w-full max-w-6xl px-4">
          <div className="mt-[75px] text-sm text-red-700 dark:text-red-300">
            {error ?? "Skill not found."}
          </div>
        </div>
      </section>
    );
  }

  const manifest = data.selectedRelease?.manifest;
  const author = asString(manifest?.author);
  const homepageFromSkill = asString(data.skill.homepage_url);
  const homepageFromManifest = asString(manifest?.homepage);
  const homepage = homepageFromSkill ?? homepageFromManifest;
  const repository = asString(manifest?.repository);
  const docs = asString(manifest?.documentation);
  const dependencies = data.selectedRelease?.dependencies ?? [];
  const downloadStats = data.skill.download_stats;
  const currentReleaseLabel = selectedVersion ? `@${selectedVersion}` : "latest";

  return (
    <section className="relative overflow-hidden bg-slate-50 py-12 dark:bg-black">
      <div className="absolute inset-0 bg-gradient-to-b from-[#f4f9ff] via-[#eef6ff] to-[#ffffff] dark:from-black dark:via-[#02142f] dark:to-black" />
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_top,rgba(30,144,255,0.12),transparent_40%)] dark:bg-[radial-gradient(circle_at_top,rgba(30,144,255,0.2),transparent_45%)]" />

      <div className="relative mx-auto w-full max-w-6xl px-4">
        <div className="mt-[75px]">
          <h1 className="text-3xl font-black tracking-tight text-slate-900 sm:text-4xl dark:text-slate-100">
            {data.skill.title}
          </h1>
          <p className="mt-2 text-sm text-slate-700 dark:text-slate-300">
            {namespace}/{slug}
            {selectedVersion ? `@${selectedVersion}` : ""}
          </p>
          <p className="mt-3 max-w-3xl text-sm text-slate-700 dark:text-slate-300">
            {data.skill.summary}
          </p>

          <div className="mt-5 flex max-w-full items-stretch gap-3">
            <div className="inline-flex max-w-full items-center gap-2 rounded-lg border border-slate-200 bg-white p-3 dark:border-slate-700 dark:bg-slate-900">
              <code className="overflow-x-auto text-sm text-slate-800 dark:text-slate-200">
                {installCommand}
              </code>
              <button
                type="button"
                onClick={() => void handleCopy()}
                className="inline-flex items-center rounded-md border border-slate-300 px-2 py-1 text-xs text-slate-700 hover:bg-slate-50 dark:border-slate-600 dark:text-slate-300 dark:hover:bg-slate-800"
                aria-label="Copy install command"
              >
                {isCopied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
              </button>
            </div>
            <button
              type="button"
              onClick={() => void handleCopyPrompt()}
              style={{ height: "50px" }}
              className="inline-flex h-full items-center rounded-lg border border-slate-300 bg-white p-3 text-sm font-medium text-slate-700 hover:bg-slate-50 dark:border-slate-600 dark:bg-slate-900 dark:text-slate-300 dark:hover:bg-slate-800"
              aria-label="Copy LLM instructions"
            >
              {isPromptCopied ? "Copied" : "Copy LLM Instructions"}
            </button>
          </div>
        </div>

        <div className="mt-8 grid grid-cols-1 gap-6 lg:grid-cols-4">
          <aside className="h-fit self-start space-y-5 rounded-xl border border-slate-200/80 bg-white/85 p-4 dark:border-slate-800 dark:bg-slate-950/50">
            <div>
              <p className="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">Current release</p>
              <p className="mt-1 text-sm text-slate-900 dark:text-slate-100">{currentReleaseLabel}</p>
              <Link
                href={`/skill/${encodeURIComponent(namespace)}/${encodeURIComponent(slug)}/releases`}
                className="mt-2 inline-block text-xs text-blue-700 hover:underline dark:text-blue-300"
              >
                View release history
              </Link>
            </div>
            <div>
              <p className="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">Created</p>
              <p className="mt-1 text-sm text-slate-900 dark:text-slate-100">
                {formatDate(data.skill.created_at)}
              </p>
            </div>
            <div>
              <p className="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">Last Updated</p>
              <p className="mt-1 text-sm text-slate-900 dark:text-slate-100">
                {formatDate(data.skill.updated_at)}
              </p>
            </div>
            <div>
              <p className="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">Downloads</p>
              <div className="mt-1 space-y-1 text-sm text-slate-900 dark:text-slate-100">
                <p>Total: {formatCount(downloadStats.total)}</p>
                <p>Last week: {formatCount(downloadStats.last_week)}</p>
                <p>Last month: {formatCount(downloadStats.last_month)}</p>
              </div>
            </div>
            <div>
              <p className="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">Author</p>
              <p className="mt-1 text-sm text-slate-900 dark:text-slate-100">{author ?? data.skill.namespace}</p>
            </div>
            <div>
              <p className="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">Dependencies</p>
              {dependencies.length > 0 ? (
                <ul className="mt-1 space-y-1 text-sm text-slate-900 dark:text-slate-100">
                  {dependencies.map((dep) => (
                    <li key={dep.id}>
                      {dep.namespace}/{dep.slug}
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="mt-1 text-sm text-slate-900 dark:text-slate-100">None</p>
              )}
            </div>
            <div>
              <p className="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">Tags</p>
              <div className="mt-1 flex flex-wrap gap-1.5">
                {data.skill.tags.length > 0 ? (
                  data.skill.tags.map((tag) => (
                    <span
                      key={tag}
                      className="rounded-full border border-blue-300/70 bg-blue-50 px-2 py-0.5 text-xs text-blue-700 dark:border-blue-400/40 dark:bg-blue-500/15 dark:text-blue-200"
                    >
                      {tag}
                    </span>
                  ))
                ) : (
                  <span className="text-sm text-slate-900 dark:text-slate-100">No tags</span>
                )}
              </div>
            </div>
            <div>
              <p className="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">Links</p>
              <div className="mt-1 space-y-1 text-sm">
                {homepage && <a href={homepage} target="_blank" rel="noopener noreferrer" className="text-blue-700 hover:underline dark:text-blue-300">Homepage</a>}
                {repository && <a href={repository} target="_blank" rel="noopener noreferrer" className="text-blue-700 hover:underline dark:text-blue-300">Repository</a>}
                {docs && <a href={docs} target="_blank" rel="noopener noreferrer" className="text-blue-700 hover:underline dark:text-blue-300">Documentation</a>}
                {!homepage && !repository && !docs && (
                  <span className="text-slate-900 dark:text-slate-100">No links</span>
                )}
              </div>
            </div>
          </aside>

          <main className="lg:col-span-3 rounded-xl border border-slate-200/80 bg-white/85 p-6 dark:border-slate-800 dark:bg-slate-950/50">
            <h2 className="text-xl font-semibold text-slate-900 dark:text-slate-100">
              Skill description
            </h2>
            <div className="mt-4 overflow-x-auto">
              <div className="min-w-full text-sm leading-relaxed text-slate-800 dark:text-slate-200 [&_a]:text-blue-700 [&_a]:underline dark:[&_a]:text-blue-300 [&_code]:rounded [&_code]:bg-slate-100 [&_code]:px-1 dark:[&_code]:bg-slate-800 [&_h1]:mt-4 [&_h1]:text-2xl [&_h1]:font-semibold [&_h2]:mt-4 [&_h2]:text-xl [&_h2]:font-semibold [&_h3]:mt-3 [&_h3]:text-lg [&_h3]:font-semibold [&_li]:ml-5 [&_li]:list-disc [&_p]:my-3 [&_pre]:max-w-full [&_pre]:overflow-x-auto [&_table]:block [&_table]:max-w-full [&_table]:overflow-x-auto">
                <ReactMarkdown>
                  {plainDescription}
                </ReactMarkdown>
              </div>
            </div>
          </main>
        </div>
      </div>
    </section>
  );
}
