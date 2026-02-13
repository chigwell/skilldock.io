"use client";

import { Star } from "lucide-react";
import dynamic from "next/dynamic";
import Link from "next/link";
import { useEffect, useState } from "react";
import {
  MobileNav,
  MobileNavHeader,
  MobileNavMenu,
  MobileNavToggle,
  NavBody,
  Navbar,
  NavbarLogo,
  NavItems,
} from "@/components/ui/ResizeAbleNavbar";
const ThemeToggle = dynamic(
  () => import("@/components/ui/theme-toggle").then((mod) => mod.ThemeToggle),
  { ssr: false },
);

const REPO_API = "https://api.github.com/repos/chigwell/skilldock.io";
const REPO_URL = "https://github.com/chigwell/skilldock.io";

async function getGitHubStars(): Promise<number> {
  try {
    const response = await fetch(REPO_API, {
      headers: { Accept: "application/vnd.github+json" },
    });

    if (!response.ok) {
      return 0;
    }

    const data = (await response.json()) as { stargazers_count?: number };
    return data.stargazers_count ?? 0;
  } catch {
    return 0;
  }
}

function formatStarCount(count: number): string {
  if (count >= 1000) {
    return `${(count / 1000).toFixed(1)}k`;
  }
  return count.toString();
}

export default function Navigation() {
  const navItems = [
    { name: "Skills", link: "/search" },
    { name: "Docs", link: "https://docs.skilldock.io/" },
    { name: "Theme(Beta)", link: "/themes" },
  ];

  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
  const [stars, setStars] = useState<number | null>(null);

  useEffect(() => {
    getGitHubStars().then(setStars);
  }, []);

  return (
    <Navbar>
      <NavBody>
        <NavbarLogo />
        <NavItems items={navItems} />
        <div className="flex items-center gap-3">
          <ThemeToggle />
          <Link
            href={REPO_URL}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex h-9 items-center justify-center whitespace-nowrap rounded-md border border-neutral-300/80 bg-white/85 px-4 py-2 text-sm font-medium text-neutral-800 shadow-sm transition-colors hover:bg-white dark:border-white/20 dark:bg-black/40 dark:text-white dark:hover:bg-white/10"
          >
            <Star className="mr-2 h-4 w-4 fill-current" />
            {stars !== null ? (
              <>
                <span className="font-semibold">{formatStarCount(stars)}</span>
                <span className="ml-1">stars</span>
              </>
            ) : (
              "Star on GitHub"
            )}
          </Link>
        </div>
      </NavBody>

      <MobileNav>
        <MobileNavHeader>
          <NavbarLogo />
          <div className="flex items-center gap-2">
            <ThemeToggle />
            <MobileNavToggle
              isOpen={isMobileMenuOpen}
              onClick={() => setIsMobileMenuOpen(!isMobileMenuOpen)}
            />
          </div>
        </MobileNavHeader>

        <MobileNavMenu
          isOpen={isMobileMenuOpen}
          onClose={() => setIsMobileMenuOpen(false)}
        >
          {navItems.map((item) => (
            <Link
              key={item.name}
              href={item.link}
              onClick={() => setIsMobileMenuOpen(false)}
              className="text-neutral-700 transition-colors hover:text-neutral-950 dark:text-neutral-200 dark:hover:text-white"
            >
              <span className="block">{item.name}</span>
            </Link>
          ))}
          <div className="mt-2 flex w-full flex-col gap-4">
            <Link
              href={REPO_URL}
              target="_blank"
              rel="noopener noreferrer"
              onClick={() => setIsMobileMenuOpen(false)}
              className="inline-flex h-9 w-full items-center justify-center whitespace-nowrap rounded-md border border-neutral-300/80 bg-white/85 px-4 py-2 text-sm font-medium text-neutral-800 shadow-sm transition-colors hover:bg-white dark:border-white/20 dark:bg-black/40 dark:text-white dark:hover:bg-white/10"
            >
              <Star className="mr-2 h-4 w-4 fill-current" />
              {stars !== null ? (
                <>
                  <span className="font-semibold">
                    {formatStarCount(stars)}
                  </span>
                  <span className="ml-1">stars</span>
                </>
              ) : (
                "Star on GitHub"
              )}
            </Link>
          </div>
        </MobileNavMenu>
      </MobileNav>
    </Navbar>
  );
}
