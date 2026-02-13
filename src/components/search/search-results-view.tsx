"use client";

import { Search } from "lucide-react";
import { motion } from "motion/react";
import { useRouter, useSearchParams } from "next/navigation";
import { type FormEvent, useEffect, useState } from "react";
import Skeleton from "@/components/ui/skeleton";
import { buildApiUrl } from "@/lib/api";

const SEARCH_CACHE_TTL_MS = 2 * 60 * 1000;
const SEARCH_CACHE_KEY_PREFIX = "skills-search-cache-v1";

interface SkillResult {
  namespace: string;
  slug: string;
  title: string;
  summary: string;
  tags: string[];
  updated_at: string;
}

interface SkillsSearchResponse {
  page: number;
  per_page: number;
  items: SkillResult[];
  has_more: boolean;
}

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString();
  } catch {
    return iso;
  }
}

function buildSearchCacheKey(query: string, page: number, perPage: number): string {
  return `${SEARCH_CACHE_KEY_PREFIX}:${query}:${page}:${perPage}`;
}

function getCached<T>(key: string): T | null {
  try {
    const cachedRaw = localStorage.getItem(key);
    if (!cachedRaw) return null;
    const cached = JSON.parse(cachedRaw) as { timestamp: number; data: T };
    if (Date.now() - cached.timestamp > SEARCH_CACHE_TTL_MS) {
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

function ResultCardSkeleton() {
  return (
    <div className="rounded-xl border border-slate-200/80 bg-white/85 p-5 shadow-sm dark:border-slate-800 dark:bg-slate-950/50">
      <div className="space-y-3">
        <Skeleton width="60%" height="1.4rem" radius="lg" animation="wave" />
        <Skeleton width="100%" height="0.95rem" radius="md" animation="wave" />
        <Skeleton width="88%" height="0.95rem" radius="md" animation="wave" />
      </div>
      <div className="mt-5 flex gap-2">
        <Skeleton width={70} height="1.45rem" radius="full" animation="wave" />
        <Skeleton width={84} height="1.45rem" radius="full" animation="wave" />
        <Skeleton width={62} height="1.45rem" radius="full" animation="wave" />
      </div>
      <div className="mt-5 flex items-center justify-between">
        <Skeleton width={120} height="0.95rem" animation="wave" />
        <Skeleton width={80} height="0.95rem" animation="wave" />
      </div>
    </div>
  );
}

export default function SearchResultsView() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const query = searchParams.get("q") ?? "";
  const page = Number(searchParams.get("page") ?? "1");
  const normalizedPage = Number.isFinite(page) && page > 0 ? page : 1;
  const perPage = 20;

  const [inputValue, setInputValue] = useState(query);
  const [isLoading, setIsLoading] = useState(true);
  const [results, setResults] = useState<SkillResult[]>([]);
  const [hasMore, setHasMore] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setInputValue(query);
  }, [query]);

  useEffect(() => {
    let isCancelled = false;
    const loadResults = async () => {
      setIsLoading(true);
      setError(null);

      const cacheKey = buildSearchCacheKey(query.trim(), normalizedPage, perPage);
      const cached = getCached<SkillsSearchResponse>(cacheKey);
      if (cached) {
        if (!isCancelled) {
          setResults(cached.items);
          setHasMore(cached.has_more);
          setIsLoading(false);
        }
        return;
      }

      try {
        const params = new URLSearchParams();
        if (query.trim()) params.set("q", query.trim());
        params.set("page", String(normalizedPage));
        params.set("per_page", String(perPage));

        const response = await fetch(buildApiUrl(`/v1/skills?${params.toString()}`));
        if (!response.ok) {
          throw new Error(`Search request failed with ${response.status}`);
        }

        const data = (await response.json()) as SkillsSearchResponse;
        setCached(cacheKey, data);

        if (!isCancelled) {
          setResults(data.items);
          setHasMore(data.has_more);
        }
      } catch {
        if (!isCancelled) {
          setResults([]);
          setHasMore(false);
          setError("Failed to load search results.");
        }
      } finally {
        if (!isCancelled) {
          setIsLoading(false);
        }
      }
    };

    void loadResults();
    return () => {
      isCancelled = true;
    };
  }, [query, normalizedPage]);

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const trimmedQuery = inputValue.trim();
    const querySegment = trimmedQuery
      ? `?q=${encodeURIComponent(trimmedQuery)}&page=1`
      : "?page=1";
    router.push(`/search${querySegment}`);
  };

  const updatePage = (nextPage: number) => {
    const params = new URLSearchParams();
    if (query.trim()) params.set("q", query.trim());
    params.set("page", String(nextPage));
    router.push(`/search?${params.toString()}`);
  };

  return (
    <section className="relative overflow-hidden bg-slate-50 py-12 dark:bg-black">
      <div className="absolute inset-0 bg-gradient-to-b from-[#f4f9ff] via-[#eef6ff] to-[#ffffff] dark:from-black dark:via-[#02142f] dark:to-black" />
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_top,rgba(30,144,255,0.12),transparent_40%)] dark:bg-[radial-gradient(circle_at_top,rgba(30,144,255,0.2),transparent_45%)]" />

      <div className="relative mx-auto w-full max-w-6xl px-4">
        <div className="mt-[75px] mb-8 space-y-4 text-center">
          <h1 className="text-3xl font-black tracking-tight text-slate-900 sm:text-4xl dark:text-slate-100">
            Search Skills
          </h1>
          <p className="mx-auto max-w-2xl text-sm text-slate-700 sm:text-base dark:text-slate-300">
            Public, active skills from the SkillDock API.
          </p>
        </div>

        <form
          onSubmit={handleSubmit}
          role="search"
          className="mx-auto mb-8 flex h-14 w-full max-w-xl items-stretch gap-2"
        >
          <input
            type="search"
            name="q"
            placeholder="Search skills..."
            value={inputValue}
            onChange={(event) => setInputValue(event.target.value)}
            className="h-full w-full rounded-md border border-blue-300/50 bg-white/90 px-4 text-base text-blue-950 placeholder:text-blue-800/60 outline-none transition-colors focus:border-blue-400 focus:ring-2 focus:ring-blue-300/50 dark:border-blue-300/35 dark:bg-blue-950/40 dark:text-blue-100 dark:placeholder:text-blue-200/65 dark:focus:border-blue-300 dark:focus:ring-blue-400/45"
          />
          <button
            type="submit"
            className="inline-flex h-full shrink-0 items-center justify-center rounded-md border border-blue-200/50 bg-[#1e90ff] px-5 text-base font-semibold text-white transition-colors hover:border-blue-300/60 hover:bg-[#197bdd] dark:border-blue-200/30 dark:hover:border-blue-200/45"
          >
            <Search className="h-4 w-4" />
          </button>
        </form>

        <div className="mb-6 text-sm text-slate-700 dark:text-slate-300">
          {isLoading ? (
            <span>Loading search results...</span>
          ) : error ? (
            <span>{error}</span>
          ) : (
            <span>
              {results.length} result{results.length === 1 ? "" : "s"}
              {query ? ` for "${query}"` : ""}
            </span>
          )}
        </div>

        {isLoading ? (
          <div className="grid grid-cols-1 gap-5 md:grid-cols-2">
            {Array.from({ length: 6 }, (_, index) => (
              <ResultCardSkeleton key={`skeleton-${index}`} />
            ))}
          </div>
        ) : results.length > 0 ? (
          <div className="grid grid-cols-1 gap-5 md:grid-cols-2">
            {results.map((result, index) => (
              <motion.article
                key={`${result.namespace}/${result.slug}`}
                initial={{ opacity: 0, y: 14 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.25, delay: index * 0.05 }}
                className="cursor-pointer rounded-xl border border-slate-200/80 bg-white/85 p-5 shadow-sm transition-shadow hover:shadow-md dark:border-slate-800 dark:bg-slate-950/50 dark:hover:shadow-slate-950/30"
                onClick={() => router.push(`/skill/${result.namespace}/${result.slug}`)}
              >
                <h2 className="mb-2 text-lg font-semibold text-slate-900 dark:text-slate-100">
                  {result.title}
                </h2>
                <p className="mb-4 text-sm leading-relaxed text-slate-700 dark:text-slate-300">
                  {result.summary}
                </p>
                <div className="mb-4 flex flex-wrap gap-2">
                  {result.tags.map((tag) => (
                    <span
                      key={`${result.namespace}/${result.slug}-${tag}`}
                      className="rounded-full border border-blue-300/70 bg-blue-50 px-2.5 py-1 text-xs font-medium text-blue-700 dark:border-blue-400/40 dark:bg-blue-500/15 dark:text-blue-200"
                    >
                      {tag}
                    </span>
                  ))}
                </div>
                <div className="flex items-center justify-between text-xs text-slate-600 dark:text-slate-400">
                  <span>{result.namespace}/{result.slug}</span>
                  <span>Updated {formatDate(result.updated_at)}</span>
                </div>
              </motion.article>
            ))}
          </div>
        ) : (
          <div className="rounded-xl border border-dashed border-slate-300/80 bg-white/70 p-10 text-center dark:border-slate-700 dark:bg-slate-950/40">
            <p className="text-base font-medium text-slate-900 dark:text-slate-100">
              No results found
            </p>
            <p className="mt-2 text-sm text-slate-700 dark:text-slate-300">
              Try a different query, for example: React, Django, or TypeScript.
            </p>
          </div>
        )}
        <div className="mt-8 flex items-center justify-center gap-3">
          <button
            type="button"
            disabled={normalizedPage <= 1 || isLoading}
            onClick={() => updatePage(normalizedPage - 1)}
            className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm text-slate-700 disabled:cursor-not-allowed disabled:opacity-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300"
          >
            Previous
          </button>
          <span className="text-sm text-slate-700 dark:text-slate-300">
            Page {normalizedPage}
          </span>
          <button
            type="button"
            disabled={!hasMore || isLoading}
            onClick={() => updatePage(normalizedPage + 1)}
            className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm text-slate-700 disabled:cursor-not-allowed disabled:opacity-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300"
          >
            Next
          </button>
        </div>
      </div>
    </section>
  );
}
