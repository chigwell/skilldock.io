import Image from "next/image";

export default function RegistryOverviewSection() {
  return (
    <section className="bg-white py-16 dark:bg-black md:py-20">
      <div className="mx-auto grid w-full max-w-6xl grid-cols-1 items-center gap-10 px-4 md:grid-cols-3 md:gap-14">
        <div className="flex justify-center md:col-span-1 md:justify-start">
          <Image
            src="/logo.png"
            alt="SkillDock logo"
            width={360}
            height={360}
            className="h-auto w-full max-w-[260px] object-contain md:max-w-[320px]"
          />
        </div>

        <div className="space-y-5 text-left text-slate-800 dark:text-slate-100 md:col-span-2">
          <p className="text-base leading-relaxed sm:text-lg">
            SkillDock.io is a registry of reusable AI skills built around the{" "}
            <a
              href="https://agentskills.io/what-are-skills"
              target="_blank"
              rel="noreferrer"
              className="text-blue-600 hover:underline dark:text-blue-400"
            >
              AgentSkills
            </a>{" "}
            specification, so skills can work across different agent runtimes.
          </p>

          <p className="text-base leading-relaxed sm:text-lg">
            SkillDock.io helps you discover and install skills published by the
            community, so you can add proven capabilities to your agents
            quickly and consistently.
          </p>

          <p className="text-base leading-relaxed sm:text-lg">
            Skill authors use SkillDock.io to publish and version skills with
            clear metadata and releases, making them easy to find, install, and
            run in OpenClaw, Claude, or any other agent that supports skills.
          </p>
        </div>
      </div>
    </section>
  );
}
