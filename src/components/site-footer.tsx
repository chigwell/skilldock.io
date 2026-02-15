import Link from "next/link";

const navItems = [
  { label: "Skills", href: "/search" },
  { label: "Docs", href: "https://docs.skilldock.io/" },
  { label: "Trending", href: "/trending" },
];

export default function SiteFooter() {
  return (
    <footer className="relative overflow-hidden bg-gradient-to-br from-[#021222] via-[#0a2f63] to-[#1e90ff] text-white">
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_20%_25%,rgba(103,184,255,0.22),transparent_45%),radial-gradient(circle_at_80%_70%,rgba(30,144,255,0.25),transparent_48%)]" />
      <div className="pointer-events-none absolute inset-0 bg-linear-to-t from-black/35 via-transparent to-transparent" />

      <div className="pointer-events-none absolute inset-x-0 bottom-0 flex justify-center">
        <span className="select-none text-[5rem] font-black leading-none tracking-tight text-white/8 sm:text-[8rem] md:text-[11rem]">
          SKILLDOCK
        </span>
      </div>

      <div className="relative mx-auto w-full max-w-6xl px-4 py-14 md:py-16">
        <div className="mb-10 grid gap-10 md:grid-cols-3">
          <div className="space-y-4 md:col-span-2">
            <p className="text-xs font-semibold uppercase tracking-[0.22em] text-blue-100/90">
              SkillDock.io
            </p>
            <h2 className="max-w-2xl text-2xl font-semibold leading-tight text-white sm:text-3xl md:text-4xl">
              Reusable AI skills, ready to plug into your agent stack.
            </h2>
            <p className="max-w-2xl text-sm leading-relaxed text-blue-100/85 sm:text-base">
              Discover trusted skills from the community, publish your own
              versions, and keep your agent workflows fast and consistent.
            </p>
          </div>

          <nav className="space-y-3 text-sm sm:text-base" aria-label="Footer">
            {navItems.map((item) => (
              <Link
                key={item.label}
                href={item.href}
                className="block text-blue-50/90 transition-colors hover:text-white"
              >
                {item.label}
              </Link>
            ))}
            <Link
              href="https://github.com/chigwell/skilldock.io"
              target="_blank"
              rel="noopener noreferrer"
              className="block text-blue-50/90 transition-colors hover:text-white"
            >
              GitHub
            </Link>
          </nav>
        </div>

        <div className="flex flex-col gap-3 border-t border-white/20 pt-5 text-xs text-blue-100/80 sm:flex-row sm:items-center sm:justify-between sm:text-sm">
          <p>Copyright © 2026 SkillDock.io</p>
          <div className="flex gap-5">
            <Link href="/privacy" className="transition-colors hover:text-white">
              Privacy
            </Link>
            <Link href="/terms" className="transition-colors hover:text-white">
              Terms
            </Link>
          </div>
        </div>
      </div>
    </footer>
  );
}
