"use client";

import { Search } from "lucide-react";
import { type FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { buildApiUrl } from "@/lib/api";

const STATS_CACHE_KEY = "landing-stats-cache-v1";
const STATS_CACHE_TTL_MS = 5 * 60 * 1000;

type StatsResponse = {
  total_downloads: number;
  total_skills: number;
  total_releases: number;
  total_users: number;
};

type DisplayStat = {
  label: string;
  value: number;
  suffix?: string;
  decimals?: number;
};

const nodeCoordinates = [
  [100, 100],
  [300, 150],
  [500, 120],
  [700, 200],
  [900, 150],
  [1100, 250],
  [150, 300],
  [400, 280],
  [600, 350],
  [850, 320],
  [1050, 400],
  [50, 500],
  [250, 480],
  [450, 550],
  [650, 500],
  [850, 580],
  [1100, 550],
  [200, 700],
  [400, 650],
  [600, 720],
  [800, 680],
  [1000, 750],
] as const;

const verticalLines = [
  { x1: 300, y1: 150, x2: 300, y2: 400 },
  { x1: 600, y1: 120, x2: 600, y2: 300 },
  { x1: 850, y1: 200, x2: 850, y2: 500 },
] as const;

const colors = {
  primary: "#1e90ff",
  secondary: "#0d47a1",
  glow: "rgba(30, 144, 255, 0.5)",
};

function CountUpStat({
  value,
  suffix = "",
  decimals = 0,
}: {
  value: number;
  suffix?: string;
  decimals?: number;
}) {
  const [count, setCount] = useState(0);

  useEffect(() => {
    const duration = 1400;
    const start = performance.now();
    let frameId = 0;

    const tick = (timestamp: number) => {
      const progress = Math.min((timestamp - start) / duration, 1);
      setCount(progress * value);
      if (progress < 1) {
        frameId = requestAnimationFrame(tick);
      }
    };

    frameId = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frameId);
  }, [value]);

  return (
    <span>
      {count.toFixed(decimals).replace(/\.0$/, "")}
      {suffix}
    </span>
  );
}

function formatStatValue(
  value: number,
  options?: { forcePlus?: boolean },
): Pick<DisplayStat, "value" | "suffix" | "decimals"> {
  let compactValue = value;
  let suffix = "";

  if (value > 1_000_000) {
    compactValue = value / 1_000_000;
    suffix = "m";
  } else if (value > 1_000) {
    compactValue = value / 1_000;
    suffix = "k";
  }

  const decimals = Number.isInteger(compactValue) ? 0 : 1;
  const roundedValue = Number(compactValue.toFixed(decimals));

  if (options?.forcePlus) {
    suffix += "+";
  }

  return { value: roundedValue, suffix, decimals };
}

function mapApiStatsToDisplayStats(stats: StatsResponse): DisplayStat[] {
  return [
    {
      label: "Skills",
      ...formatStatValue(stats.total_skills, { forcePlus: true }),
    },
    {
      label: "Releases",
      ...formatStatValue(stats.total_releases, { forcePlus: true }),
    },
    {
      label: "Downloads",
      ...formatStatValue(stats.total_downloads, { forcePlus: true }),
    }
  ];
}

export default function CircuitFlow() {
  const svgRef = useRef<SVGSVGElement>(null);
  const router = useRouter();
  const [searchQuery, setSearchQuery] = useState("");
  const [apiStats, setApiStats] = useState<StatsResponse>({
    total_downloads: 0,
    total_skills: 0,
    total_releases: 0,
    total_users: 0,
  });
  const stats = useMemo(
    () => mapApiStatsToDisplayStats(apiStats),
    [apiStats],
  );

  useEffect(() => {
    const loadStats = async () => {
      try {
        const cachedRaw = localStorage.getItem(STATS_CACHE_KEY);
        if (cachedRaw) {
          const cached = JSON.parse(cachedRaw) as {
            data: StatsResponse;
            timestamp: number;
          };
          if (Date.now() - cached.timestamp < STATS_CACHE_TTL_MS) {
            setApiStats(cached.data);
            return;
          }
        }
      } catch {
        localStorage.removeItem(STATS_CACHE_KEY);
      }

      try {
        const response = await fetch(buildApiUrl("/v1/stats"));
        if (!response.ok) return;

        const data = (await response.json()) as StatsResponse;
        setApiStats(data);
        localStorage.setItem(
          STATS_CACHE_KEY,
          JSON.stringify({ data, timestamp: Date.now() }),
        );
      } catch {
        // Keep fallback values if request fails.
      }
    };

    void loadStats();
  }, []);

  useEffect(() => {
    if (!svgRef.current) return;

    const svg = svgRef.current;
    const lines = svg.querySelectorAll<SVGGeometryElement>(".circuit-line");
    const circles = svg.querySelectorAll<SVGCircleElement>(".circuit-node");

    const animateLine = (line: SVGGeometryElement, delay: number) => {
      const length = line.getTotalLength();
      line.style.strokeDasharray = `${length}`;
      line.style.strokeDashoffset = `${length}`;
      line.animate(
        [
          { strokeDashoffset: length, opacity: 0 },
          { strokeDashoffset: 0, opacity: 1 },
          { strokeDashoffset: 0, opacity: 0.3 },
        ],
        {
          duration: 2000,
          delay,
          iterations: Number.POSITIVE_INFINITY,
        },
      );
    };

    const animateNode = (node: SVGCircleElement, delay: number) => {
      node.animate(
        [
          { r: 3, opacity: 0 },
          { r: 5, opacity: 1 },
          { r: 3, opacity: 0.4 },
        ],
        {
          duration: 2000,
          delay,
          iterations: Number.POSITIVE_INFINITY,
        },
      );
    };

    for (let i = 0; i < lines.length; i++) animateLine(lines[i], i * 200);
    for (let i = 0; i < circles.length; i++) animateNode(circles[i], i * 200);

    return () => {
      for (const line of lines) {
        for (const animation of line.getAnimations()) animation.cancel();
      }
      for (const circle of circles) {
        for (const animation of circle.getAnimations()) animation.cancel();
      }
    };
  }, []);

  const handleSearchSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const trimmedQuery = searchQuery.trim();
    const querySegment = trimmedQuery
      ? `?q=${encodeURIComponent(trimmedQuery)}`
      : "";
    router.push(`/search${querySegment}`);
  };

  return (
    <section className="relative flex min-h-screen items-center justify-center overflow-hidden bg-slate-50 dark:bg-black">
      <div className="absolute inset-0 bg-gradient-to-br from-[#f5fbff] via-[#e8f3ff] to-[#dbeafe] dark:from-black dark:via-[#021222] dark:to-[#0a1f3f]" />

      <svg
        ref={svgRef}
        className="absolute inset-0 h-full w-full opacity-40 dark:opacity-55"
        viewBox="0 0 1200 800"
        preserveAspectRatio="xMidYMid slice"
      >
        <title>Circuit animation background</title>
        <defs>
          <filter id="glow">
            <feGaussianBlur stdDeviation="2" result="coloredBlur" />
            <feMerge>
              <feMergeNode in="coloredBlur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
          <linearGradient id="lineGradient" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor={colors.primary} stopOpacity="0.3" />
            <stop offset="50%" stopColor={colors.primary} />
            <stop offset="100%" stopColor={colors.secondary} stopOpacity="0.3" />
          </linearGradient>
        </defs>

        <path
          className="circuit-line"
          d="M 100 100 L 300 150 L 500 120 L 700 200 L 900 150 L 1100 250"
          fill="none"
          stroke="url(#lineGradient)"
          strokeWidth="2"
          filter="url(#glow)"
        />
        <path
          className="circuit-line"
          d="M 150 300 L 400 280 L 600 350 L 850 320 L 1050 400"
          fill="none"
          stroke="url(#lineGradient)"
          strokeWidth="2"
          filter="url(#glow)"
        />
        <path
          className="circuit-line"
          d="M 50 500 L 250 480 L 450 550 L 650 500 L 850 580 L 1100 550"
          fill="none"
          stroke="url(#lineGradient)"
          strokeWidth="2"
          filter="url(#glow)"
        />
        <path
          className="circuit-line"
          d="M 200 700 L 400 650 L 600 720 L 800 680 L 1000 750"
          fill="none"
          stroke="url(#lineGradient)"
          strokeWidth="2"
          filter="url(#glow)"
        />

        {verticalLines.map((line) => (
          <line
            key={`line-${line.x1}-${line.y1}-${line.x2}-${line.y2}`}
            className="circuit-line"
            {...line}
            stroke={colors.primary}
            strokeWidth="1.5"
            opacity="0.6"
            filter="url(#glow)"
          />
        ))}

        {nodeCoordinates.map(([cx, cy]) => (
          <circle
            key={`node-${cx}-${cy}`}
            className="circuit-node"
            cx={cx}
            cy={cy}
            r="4"
            fill={colors.primary}
            filter="url(#glow)"
          />
        ))}
      </svg>

      <div className="absolute inset-0 bg-[radial-gradient(circle_at_top,rgba(30,144,255,0.12),transparent_45%)] dark:bg-[radial-gradient(circle_at_top,rgba(30,144,255,0.18),transparent_45%)]" />

      <div className="relative z-20 mx-auto w-full max-w-6xl px-4 pt-24 text-center">
        <div className="mx-auto max-w-5xl">
          <div className="mb-8 space-y-6 md:mb-10 md:space-y-8">
            {/*<Pill
              icon={<Sparkles className="w-3 h-3 md:w-4 md:h-4" />}
              status="active"
              className="mb-16 md:mb-16 bg-background/50 backdrop-blur-sm text-xs md:text-sm"
            >
              {`SkillDock: the system is operational`}
            </Pill>*/}

            <h1 className="px-2 text-4xl font-black leading-[0.9] tracking-tight sm:text-5xl md:text-7xl lg:text-8xl">
              <span className="bg-gradient-to-r from-[#0f274b] via-[#153a6e] to-[#1f4f94] bg-clip-text text-transparent dark:from-white dark:via-blue-100 dark:to-blue-300">
                Empower Your Agent
              </span>
              <br />
              <span className="bg-gradient-to-r from-[#1e90ff] via-[#67b8ff] to-[#9bd5ff] bg-clip-text text-transparent">
                with Skills
              </span>
            </h1>

            <p className="mx-auto max-w-3xl px-4 text-base leading-relaxed text-slate-700 sm:text-lg md:text-xl dark:text-slate-200/85">
              Find, install and publish the right AI Skills
            </p>
          </div>



          <div className="mb-12 px-4 md:mb-16">
            <form
              onSubmit={handleSearchSubmit}
              role="search"
              className="mx-auto flex h-14 w-full max-w-[560px] items-stretch gap-2"
            >
              <input
                type="search"
                name="q"
                placeholder="Search skills..."
                value={searchQuery}
                onChange={(event) => setSearchQuery(event.target.value)}
                className="h-full w-full rounded-md border border-blue-300/50 bg-white/85 px-4 text-base text-blue-950 placeholder:text-blue-800/60 outline-none transition-colors focus:border-blue-400 focus:ring-2 focus:ring-blue-300/50 dark:border-blue-300/35 dark:bg-blue-950/40 dark:text-blue-100 dark:placeholder:text-blue-200/65 dark:focus:border-blue-300 dark:focus:ring-blue-400/45"
              />
              <button
                type="submit"
                className="inline-flex h-full shrink-0 items-center justify-center rounded-md border border-blue-200/50 bg-[#1e90ff] px-5 text-base font-semibold text-white transition-colors hover:border-blue-300/60 hover:bg-[#197bdd] dark:border-blue-200/30 dark:hover:border-blue-200/45"
              >
                <Search className="h-4 w-4" />
              </button>
            </form>
          </div>

          <div className="flex items-center justify-center gap-8 px-4 text-center md:gap-14">
            {stats.map((stat, idx) => (
              <div key={stat.label} className="flex items-center">
                <div>
                  <div className="mb-1 bg-gradient-to-r from-blue-200 via-blue-300 to-blue-500 bg-clip-text text-2xl font-bold text-transparent sm:text-3xl">
                    <CountUpStat
                      value={stat.value}
                      suffix={stat.suffix}
                      decimals={stat.decimals}
                    />
                  </div>
                  <div className="text-xs text-slate-600 dark:text-slate-300 md:text-sm">
                    {stat.label}
                  </div>
                </div>
                {idx !== stats.length - 1 && (
                  <div className="ml-8 h-8 w-px bg-gradient-to-b from-transparent via-blue-400/40 to-transparent md:ml-14 md:h-12" />
                )}
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
