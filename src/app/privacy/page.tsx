import type { Metadata } from "next";
import Navigation from "@/components/navigation";
import SiteFooter from "@/components/site-footer";

export const metadata: Metadata = {
  title: "Privacy Policy | SkillDock",
  description: "Privacy Policy for SkillDock.io",
};

export default function PrivacyPage() {
  return (
    <main className="relative min-h-screen">
      <Navigation />

      <section className="relative overflow-hidden bg-slate-50 py-12 dark:bg-black">
        <div className="absolute inset-0 bg-gradient-to-b from-[#f4f9ff] via-[#eef6ff] to-[#ffffff] dark:from-black dark:via-[#02142f] dark:to-black" />
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_top,rgba(30,144,255,0.12),transparent_40%)] dark:bg-[radial-gradient(circle_at_top,rgba(30,144,255,0.2),transparent_45%)]" />

        <article className="relative mx-auto mt-[75px] w-full max-w-4xl rounded-xl border border-slate-200/80 bg-white/90 p-6 text-slate-800 shadow-sm dark:border-slate-800 dark:bg-slate-950/70 dark:text-slate-100 sm:p-8">
          <h1 className="text-3xl font-black tracking-tight sm:text-4xl">
            Privacy Policy
          </h1>
          <p className="mt-2 text-sm text-slate-600 dark:text-slate-300">
            <strong>Last updated:</strong> 13 February 2026
          </p>
          <p className="mt-6 text-sm leading-relaxed sm:text-base">
            This Privacy Policy explains how SkillDock.io ("SkillDock", "we",
            "us", "our") collects and uses personal data when you use our
            website and API services.
          </p>
          <p className="mt-3 text-sm leading-relaxed sm:text-base">
            SkillDock is a community registry for publicly available AI skills.
            We operate from the United Kingdom and aim to comply with UK GDPR
            and, where applicable, EU GDPR.
          </p>

          <h2 className="mt-8 text-xl font-semibold">1. Controller Contact</h2>
          <p className="mt-3 text-sm leading-relaxed sm:text-base">
            <strong>Controller:</strong> SkillDock.io
            <br />
            <strong>Email:</strong>{" "}
            <a
              className="text-blue-700 underline dark:text-blue-300"
              href="mailto:support@skilldock.io"
            >
              support@skilldock.io
            </a>
          </p>

          <h2 className="mt-8 text-xl font-semibold">2. Data We Collect</h2>
          <ul className="mt-3 list-disc space-y-2 pl-5 text-sm leading-relaxed sm:text-base">
            <li>
              <strong>Request and security data:</strong> IP address, user
              agent, timestamps, and error/security logs processed by our
              infrastructure providers to operate and protect the service.
            </li>
            <li>
              <strong>Usage and search data:</strong> search queries, requested
              pages/skills, and related API request metadata.
            </li>
            <li>
              <strong>Local browser storage:</strong> preferences (for example,
              theme choice) and short-lived cache entries used to improve
              performance.
            </li>
            <li>
              <strong>Contact data:</strong> information you send us directly
              by email (for example, support requests).
            </li>
          </ul>
          <p className="mt-3 text-sm leading-relaxed sm:text-base">
            We do not intentionally collect special category personal data. We
            do not sell personal data.
          </p>

          <h2 className="mt-8 text-xl font-semibold">
            3. Purposes and Legal Bases
          </h2>
          <ul className="mt-3 list-disc space-y-2 pl-5 text-sm leading-relaxed sm:text-base">
            <li>
              <strong>Operate and maintain SkillDock</strong> (search, delivery,
              reliability, and abuse prevention):
              {" "}
              <strong>Legitimate interests</strong>.
            </li>
            <li>
              <strong>Respond to support requests and service communications</strong>:
              {" "}
              <strong>Legitimate interests</strong> and, where relevant,
              <strong> Contract</strong>.
            </li>
            <li>
              <strong>Comply with legal obligations</strong>:
              {" "}
              <strong>Legal obligation</strong>.
            </li>
            <li>
              <strong>Optional updates</strong> (if introduced):{" "}
              <strong>Consent</strong> or legitimate interests where permitted
              by law, with opt-out.
            </li>
          </ul>

          <h2 className="mt-8 text-xl font-semibold">
            4. Community Skills and User Responsibility
          </h2>
          <p className="mt-3 text-sm leading-relaxed sm:text-base">
            Skills listed on SkillDock are published by community authors and
            are intended to be publicly available. We may index, parse, analyze,
            and display skill metadata/content to provide discovery and registry
            functionality.
          </p>
          <p className="mt-3 text-sm leading-relaxed sm:text-base">
            You are responsible for reviewing skills before installing or
            running them, including code, dependencies, licenses, and security
            implications. Do not execute untrusted code in sensitive
            environments.
          </p>

          <h2 className="mt-8 text-xl font-semibold">
            5. Processors, Sharing, and Transfers
          </h2>
          <ul className="mt-3 list-disc space-y-2 pl-5 text-sm leading-relaxed sm:text-base">
            <li>
              We use service providers (for example, hosting, networking, and
              security providers such as Cloudflare) to run the platform.
            </li>
            <li>
              We may share data with public authorities where required by law.
            </li>
            <li>We do not sell personal data.</li>
          </ul>
          <p className="mt-3 text-sm leading-relaxed sm:text-base">
            Data may be processed internationally. Where required, we rely on
            appropriate transfer safeguards.
          </p>

          <h2 className="mt-8 text-xl font-semibold">6. Retention</h2>
          <ul className="mt-3 list-disc space-y-2 pl-5 text-sm leading-relaxed sm:text-base">
            <li>
              Operational and security logs are retained only for as long as
              needed for security, integrity, and troubleshooting.
            </li>
            <li>
              Browser local storage is controlled by your browser and can be
              cleared at any time.
            </li>
            <li>
              Support emails are retained as needed to handle your request and
              maintain support records.
            </li>
          </ul>

          <h2 className="mt-8 text-xl font-semibold">7. Your Rights</h2>
          <p className="mt-3 text-sm leading-relaxed sm:text-base">
            Depending on your location, you may have rights to access, rectify,
            erase, restrict, object, and (where applicable) data portability,
            and to withdraw consent for consent-based processing.
          </p>
          <p className="mt-3 text-sm leading-relaxed sm:text-base">
            To exercise your rights, contact{" "}
            <a
              className="text-blue-700 underline dark:text-blue-300"
              href="mailto:support@skilldock.io"
            >
              support@skilldock.io
            </a>
            . You may also complain to your local supervisory authority. In the
            UK, this is the ICO (
            <a
              className="text-blue-700 underline dark:text-blue-300"
              href="https://ico.org.uk/"
              target="_blank"
              rel="noopener noreferrer"
            >
              ico.org.uk
            </a>
            ).
          </p>

          <h2 className="mt-8 text-xl font-semibold">
            8. Cookies and Similar Technologies
          </h2>
          <p className="mt-3 text-sm leading-relaxed sm:text-base">
            SkillDock uses only necessary browser storage/cookies for core
            functionality, security, and performance. We do not use third-party
            advertising cookies.
          </p>

          <h2 className="mt-8 text-xl font-semibold">
            9. Automated Processing
          </h2>
          <p className="mt-3 text-sm leading-relaxed sm:text-base">
            We may use automated controls such as rate limiting and abuse
            detection. These controls are used for service protection and do not
            produce legal or similarly significant effects.
          </p>

          <h2 className="mt-8 text-xl font-semibold">10. Children</h2>
          <p className="mt-3 text-sm leading-relaxed sm:text-base">
            SkillDock is not directed to children. If you are under 13 (or the
            minimum age in your jurisdiction), do not use the service.
          </p>

          <h2 className="mt-8 text-xl font-semibold">
            11. Service Disclaimer (Important)
          </h2>
          <p className="mt-3 text-sm leading-relaxed sm:text-base">
            SkillDock is provided free of charge on an "as is" and "as
            available" basis. We do not guarantee uninterrupted availability,
            correctness, safety, or fitness of community-published skills or
            related content.
          </p>
          <p className="mt-3 text-sm leading-relaxed sm:text-base">
            To the maximum extent permitted by law, SkillDock owners/operators
            are not responsible for losses or damages arising from use of
            community skills, third-party repositories, or external links.
          </p>

          <h2 className="mt-8 text-xl font-semibold">12. Changes</h2>
          <p className="mt-3 text-sm leading-relaxed sm:text-base">
            We may update this policy from time to time. The latest version will
            always include a revised "Last updated" date.
          </p>

          <h2 className="mt-8 text-xl font-semibold">13. Contact</h2>
          <p className="mt-3 text-sm leading-relaxed sm:text-base">
            Questions or requests:{" "}
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
