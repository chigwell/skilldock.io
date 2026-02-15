"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { buildApiUrl } from "@/lib/api";

type SkillReleaseItem = {
  version: string;
  status: string;
  created_at: string;
  published_at: string | null;
};

type SkillDetailsPayload = {
  page: number;
  per_page: number;
  items?: SkillReleaseItem[];
  releases?: SkillReleaseItem[];
  has_more: boolean;
};

function formatDate(iso: string | null | undefined): string {
  if (!iso) return "N/A";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleDateString();
}

function toReleaseItems(value: unknown): SkillReleaseItem[] {
  if (!Array.isArray(value)) return [];

  return value
    .filter(
      (item): item is SkillReleaseItem =>
        typeof item === "object" &&
        item !== null &&
        typeof (item as SkillReleaseItem).version === "string" &&
        typeof (item as SkillReleaseItem).status === "string" &&
        typeof (item as SkillReleaseItem).created_at === "string",
    )
    .map((item) => ({
      version: item.version,
      status: item.status,
      created_at: item.created_at,
      published_at: typeof item.published_at === "string" ? item.published_at : null,
    }));
}

function parseHasMore(value: unknown): boolean {
  return typeof value === "boolean" ? value : false;
}

export default function SkillReleasesHistoryView({
  namespace,
  slug,
}: {
  namespace: string;
  slug: string;
}) {
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [releases, setReleases] = useState<SkillReleaseItem[]>([]);
  const [page, setPage] = useState(1);
  const [hasMore, setHasMore] = useState(false);

  useEffect(() => {
    let isCancelled = false;

    const loadReleases = async () => {
      setIsLoading(true);
      setError(null);

      try {
        const encodedNamespace = encodeURIComponent(namespace);
        const encodedSlug = encodeURIComponent(slug);
        const pagedPath = `/v1/skills/${encodedNamespace}/${encodedSlug}/releases?page=${page}&per_page=10`;
        const unpagedPath = `/v1/skills/${encodedNamespace}/${encodedSlug}/releases`;
        const legacyPath = `/v1/skills/${encodedNamespace}/${encodedSlug}`;

        let parsedReleases: SkillReleaseItem[] = [];
        let parsedHasMore = false;

        const pagedResponse = await fetch(buildApiUrl(pagedPath));
        if (pagedResponse.ok) {
          const payload = (await pagedResponse.json()) as SkillDetailsPayload | SkillReleaseItem[];
          if (Array.isArray(payload)) {
            parsedReleases = toReleaseItems(payload);
          } else {
            parsedReleases = toReleaseItems(payload.items ?? payload.releases);
            parsedHasMore = parseHasMore(payload.has_more);
          }
        } else {
          const unpagedResponse = await fetch(buildApiUrl(unpagedPath));
          if (unpagedResponse.ok) {
            const payload = (await unpagedResponse.json()) as SkillDetailsPayload | SkillReleaseItem[];
            if (Array.isArray(payload)) {
              parsedReleases = toReleaseItems(payload);
            } else {
              parsedReleases = toReleaseItems(payload.items ?? payload.releases);
              parsedHasMore = parseHasMore(payload.has_more);
            }
          } else {
            const legacyResponse = await fetch(buildApiUrl(legacyPath));
            if (!legacyResponse.ok) {
              throw new Error(
                `Failed with paged=${pagedResponse.status} unpaged=${unpagedResponse.status} legacy=${legacyResponse.status}`,
              );
            }
            const legacyPayload = (await legacyResponse.json()) as SkillDetailsPayload;
            parsedReleases = toReleaseItems(legacyPayload.releases);
            parsedHasMore = false;
          }
        }

        if (!isCancelled) {
          setReleases((prev) => (page === 1 ? parsedReleases : [...prev, ...parsedReleases]));
          setHasMore(parsedHasMore);
        }
      } catch {
        if (!isCancelled) {
          setError("Failed to load release history.");
        }
      } finally {
        if (!isCancelled) {
          setIsLoading(false);
        }
      }
    };

    void loadReleases();

    return () => {
      isCancelled = true;
    };
  }, [namespace, slug, page]);

  useEffect(() => {
    setPage(1);
    setReleases([]);
    setHasMore(false);
  }, [namespace, slug]);

  return (
    <section className="relative overflow-hidden bg-slate-50 py-12 dark:bg-black">
      <div className="absolute inset-0 bg-gradient-to-b from-[#f4f9ff] via-[#eef6ff] to-[#ffffff] dark:from-black dark:via-[#02142f] dark:to-black" />
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_top,rgba(30,144,255,0.12),transparent_40%)] dark:bg-[radial-gradient(circle_at_top,rgba(30,144,255,0.2),transparent_45%)]" />

      <div className="relative mx-auto w-full max-w-4xl px-4">
        <div className="mt-[75px]">
          <h1 className="text-3xl font-black tracking-tight text-slate-900 sm:text-4xl dark:text-slate-100">
            Release history
          </h1>
          <p className="mt-2 text-sm text-slate-700 dark:text-slate-300">
            {namespace}/{slug}
          </p>
          <Link
            href={`/skill/${encodeURIComponent(namespace)}/${encodeURIComponent(slug)}`}
            className="mt-3 inline-block text-sm text-blue-700 hover:underline dark:text-blue-300"
          >
            Back to skill details
          </Link>
        </div>

        <div className="mt-8 rounded-xl border border-slate-200/80 bg-white/85 p-4 dark:border-slate-800 dark:bg-slate-950/50 sm:p-6">
          {isLoading && (
            <p className="text-sm text-slate-700 dark:text-slate-300">Loading release history...</p>
          )}

          {!isLoading && error && (
            <p className="text-sm text-red-700 dark:text-red-300">{error}</p>
          )}

          {!isLoading && !error && releases.length === 0 && (
            <p className="text-sm text-slate-700 dark:text-slate-300">No releases found.</p>
          )}

          {!isLoading && !error && releases.length > 0 && (
            <>
              <ol className="space-y-0">
                {releases.map((release, index) => {
                  const isLast = index === releases.length - 1;
                  const releaseSlug = `${slug}@${release.version}`;

                  return (
                    <li key={`${release.version}-${index}`} className="grid grid-cols-[100px_24px_1fr] gap-2 sm:grid-cols-[140px_28px_1fr]">
                      <div className="pt-1 text-right text-xs text-slate-500 sm:text-sm dark:text-slate-400">
                        {formatDate(release.published_at ?? release.created_at)}
                      </div>
                      <div className="flex flex-col items-center">
                        <span className="mt-1 block h-3 w-3 rounded-full border border-blue-300 bg-blue-500/90 dark:border-blue-300/60" />
                        {!isLast && <span className="mt-1 block w-px flex-1 bg-slate-300 dark:bg-slate-700" />}
                      </div>
                      <div className="pb-6">
                        <Link
                          href={`/skill/${encodeURIComponent(namespace)}/${encodeURIComponent(releaseSlug)}`}
                          className="text-sm font-semibold text-blue-700 hover:underline dark:text-blue-300"
                        >
                          {release.version}
                        </Link>
                        <p className="mt-1 text-xs text-slate-600 dark:text-slate-400">
                          {release.status}
                        </p>
                      </div>
                    </li>
                  );
                })}
              </ol>
              {hasMore && (
                <div className="mt-4">
                  <button
                    type="button"
                    onClick={() => setPage((prev) => prev + 1)}
                    className="rounded-md border border-blue-300/60 bg-blue-50 px-3 py-1.5 text-sm font-medium text-blue-700 hover:bg-blue-100 dark:border-blue-400/45 dark:bg-blue-500/15 dark:text-blue-200 dark:hover:bg-blue-500/25"
                  >
                    Load more
                  </button>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </section>
  );
}
