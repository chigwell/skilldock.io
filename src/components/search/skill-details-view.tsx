"use client";

import { Check, Copy } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import ReactMarkdown from "react-markdown";
import { buildApiUrl } from "@/lib/api";

const SKILL_DETAILS_CACHE_TTL_MS = 5 * 60 * 1000;
const SKILL_DETAILS_CACHE_KEY_PREFIX = "skill-details-page-cache-v1";

type SkillDetailsResponse = {
  skill: {
    namespace: string;
    slug: string;
    title: string;
    summary: string;
    description_md: string;
    tags: string[];
    created_at: string;
    updated_at: string;
    download_stats: {
      total: number;
      last_week: number;
      last_month: number;
    };
  };
  latest_release: {
    version: string;
    status: string;
    created_at: string;
    published_at: string | null;
    manifest?: Record<string, unknown>;
    dependencies?: Array<{
      id: string;
      namespace: string;
      slug: string;
      version_requirement: string;
      release_version: string | null;
    }>;
  } | null;
  releases: Array<{
    version: string;
    status: string;
    created_at: string;
    published_at: string | null;
  }>;
};

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
}: {
  namespace: string;
  slug: string;
}) {
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<SkillDetailsResponse | null>(null);
  const [isCopied, setIsCopied] = useState(false);

  const cacheKey = useMemo(
    () => `${SKILL_DETAILS_CACHE_KEY_PREFIX}:${namespace}/${slug}`,
    [namespace, slug],
  );

  useEffect(() => {
    let isCancelled = false;
    const loadSkill = async () => {
      setIsLoading(true);
      setError(null);

      const cached = getCached<SkillDetailsResponse>(cacheKey);
      if (cached) {
        if (!isCancelled) {
          setData(cached);
          setIsLoading(false);
        }
        return;
      }

      try {
        const response = await fetch(
          buildApiUrl(
            `/v1/skills/${encodeURIComponent(namespace)}/${encodeURIComponent(slug)}`,
          ),
        );
        if (!response.ok) {
          throw new Error(`Failed with ${response.status}`);
        }
        const parsed = (await response.json()) as SkillDetailsResponse;
        setCached(cacheKey, parsed);
        if (!isCancelled) {
          setData(parsed);
        }
      } catch {
        if (!isCancelled) {
          setError("Failed to load skill details.");
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
  }, [cacheKey, namespace, slug]);

  const installCommand = `skilldock install ${namespace}/${slug}`;

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(installCommand);
      setIsCopied(true);
      window.setTimeout(() => setIsCopied(false), 1500);
    } catch {
      setIsCopied(false);
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

  const manifest = data.latest_release?.manifest;
  const author = asString(manifest?.author);
  const homepage = asString(manifest?.homepage);
  const repository = asString(manifest?.repository);
  const docs = asString(manifest?.documentation);
  const dependencies = data.latest_release?.dependencies ?? [];

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
          </p>
          <p className="mt-3 max-w-3xl text-sm text-slate-700 dark:text-slate-300">
            {data.skill.summary}
          </p>

          <div className="mt-5 inline-flex max-w-full items-center gap-2 rounded-lg border border-slate-200 bg-white p-3 dark:border-slate-700 dark:bg-slate-900">
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
        </div>

        <div className="mt-8 grid grid-cols-1 gap-6 lg:grid-cols-4">
          <aside className="h-fit self-start space-y-5 rounded-xl border border-slate-200/80 bg-white/85 p-4 dark:border-slate-800 dark:bg-slate-950/50">
            <div>
              <p className="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">Version</p>
              <p className="mt-1 text-sm text-slate-900 dark:text-slate-100">
                {data.latest_release?.version ?? "N/A"}
              </p>
            </div>
            <div>
              <p className="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">Released</p>
              <p className="mt-1 text-sm text-slate-900 dark:text-slate-100">
                {formatDate(data.latest_release?.published_at ?? data.latest_release?.created_at)}
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
                <p>Total: {formatCount(data.skill.download_stats.total)}</p>
                <p>Last week: {formatCount(data.skill.download_stats.last_week)}</p>
                <p>Last month: {formatCount(data.skill.download_stats.last_month)}</p>
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
                {homepage && <a href={homepage} target="_blank" className="text-blue-700 hover:underline dark:text-blue-300">Homepage</a>}
                {repository && <a href={repository} target="_blank" className="text-blue-700 hover:underline dark:text-blue-300">Repository</a>}
                {docs && <a href={docs} target="_blank" className="text-blue-700 hover:underline dark:text-blue-300">Documentation</a>}
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
            <div className="mt-4 text-sm leading-relaxed text-slate-800 dark:text-slate-200 [&_a]:text-blue-700 [&_a]:underline dark:[&_a]:text-blue-300 [&_code]:rounded [&_code]:bg-slate-100 [&_code]:px-1 dark:[&_code]:bg-slate-800 [&_h1]:mt-4 [&_h1]:text-2xl [&_h1]:font-semibold [&_h2]:mt-4 [&_h2]:text-xl [&_h2]:font-semibold [&_h3]:mt-3 [&_h3]:text-lg [&_h3]:font-semibold [&_li]:ml-5 [&_li]:list-disc [&_p]:my-3">
              <ReactMarkdown>
                {data.skill.description_md || "No description provided."}
              </ReactMarkdown>
            </div>
          </main>
        </div>
      </div>
    </section>
  );
}
