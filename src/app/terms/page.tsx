import type { Metadata } from "next";
import Navigation from "@/components/navigation";
import SiteFooter from "@/components/site-footer";

export const metadata: Metadata = {
  title: "Terms of Service | SkillDock",
  description: "Terms of Service for SkillDock.io",
};

export default function TermsPage() {
  return (
    <main className="relative min-h-screen">
      <Navigation />

      <section className="relative overflow-hidden bg-slate-50 py-12 dark:bg-black">
        <div className="absolute inset-0 bg-gradient-to-b from-[#f4f9ff] via-[#eef6ff] to-[#ffffff] dark:from-black dark:via-[#02142f] dark:to-black" />
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_top,rgba(30,144,255,0.12),transparent_40%)] dark:bg-[radial-gradient(circle_at_top,rgba(30,144,255,0.2),transparent_45%)]" />

        <article className="relative mx-auto mt-[75px] w-full max-w-4xl rounded-xl border border-slate-200/80 bg-white/90 p-6 text-slate-800 shadow-sm dark:border-slate-800 dark:bg-slate-950/70 dark:text-slate-100 sm:p-8">
          <h1 className="text-3xl font-black tracking-tight sm:text-4xl">
            Terms of Service
          </h1>
          <p className="mt-2 text-sm text-slate-600 dark:text-slate-300">
            <strong>Last updated:</strong> 13 February 2026
          </p>

          <h2 className="mt-8 text-xl font-semibold">1. Service Nature</h2>
          <p className="mt-3 text-sm leading-relaxed sm:text-base">
            SkillDock.io is a registry for community-published AI skills. We
            help users discover skills and related metadata.
          </p>

          <h2 className="mt-8 text-xl font-semibold">
            2. Community Content and User Responsibility
          </h2>
          <p className="mt-3 text-sm leading-relaxed sm:text-base">
            Skills listed on SkillDock are published by third parties. You are
            responsible for evaluating and using public skills, including their
            code, dependencies, licenses, and security impact, before
            installation or execution.
          </p>

          <h2 className="mt-8 text-xl font-semibold">3. No Warranty</h2>
          <p className="mt-3 text-sm leading-relaxed sm:text-base">
            SkillDock is provided free of charge on an "as is" and "as
            available" basis. To the maximum extent permitted by law, we make no
            warranties, express or implied, including availability, accuracy,
            security, non-infringement, or fitness for a particular purpose.
          </p>

          <h2 className="mt-8 text-xl font-semibold">4. Limitation of Liability</h2>
          <p className="mt-3 text-sm leading-relaxed sm:text-base">
            To the maximum extent permitted by law, SkillDock owners/operators
            are not liable for indirect, incidental, special, consequential, or
            punitive damages, or for loss of data, profits, or business arising
            from use of the service, community skills, or third-party content.
          </p>

          <h2 className="mt-8 text-xl font-semibold">5. Changes</h2>
          <p className="mt-3 text-sm leading-relaxed sm:text-base">
            We may update these terms. Continued use after updates means you
            accept the revised terms.
          </p>

          <h2 className="mt-8 text-xl font-semibold">6. Contact</h2>
          <p className="mt-3 text-sm leading-relaxed sm:text-base">
            Questions:{" "}
            <a
              className="text-blue-700 underline dark:text-blue-300"
              href="mailto:support@skilldock.io"
            >
              support@skilldock.io
            </a>
          </p>
        </article>
      </section>

      <SiteFooter />
    </main>
  );
}
