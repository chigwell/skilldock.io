"use client";

import { useState } from "react";
import { Check, Copy } from "lucide-react";

import { MovingBorderButton } from "@/components/ui/moving-border-button";

function extractPromptMarkdown(raw: string): string {
  const trimmed = raw.trim();

  if (!trimmed) {
    return "";
  }

  const looksLikeHtml =
    trimmed.startsWith("<!DOCTYPE html") ||
    trimmed.startsWith("<html") ||
    trimmed.includes("<body");

  if (!looksLikeHtml) {
    return trimmed;
  }

  const doc = new DOMParser().parseFromString(raw, "text/html");
  const preText = doc.querySelector("pre")?.textContent?.trim();

  if (preText) {
    return preText;
  }

  return doc.body?.textContent?.trim() ?? "";
}

export default function OnePromptSection() {
  const [isCopying, setIsCopying] = useState(false);
  const [copied, setCopied] = useState(false);
  const [copyError, setCopyError] = useState<string | null>(null);
  const [cliCopied, setCliCopied] = useState(false);
  const [cliCopyError, setCliCopyError] = useState<string | null>(null);

  const handleCopyPrompt = async () => {
    setIsCopying(true);
    setCopyError(null);

    try {
      const response = await fetch(
        "https://skilldock.io/skill/skilldock/skilldock-cli-usage?output=plain",
      );

      if (!response.ok) {
        throw new Error("Unable to load prompt text.");
      }

      const prompt = extractPromptMarkdown(await response.text());

      if (!prompt.trim()) {
        throw new Error("Prompt text is empty.");
      }

      await navigator.clipboard.writeText(prompt);
      setCopied(true);
    } catch {
      setCopyError("Could not copy prompt. Please try again.");
      setCopied(false);
    } finally {
      setIsCopying(false);
    }
  };

  const handleCopyCliCommand = async () => {
    setCliCopyError(null);

    try {
      await navigator.clipboard.writeText("pip install skilldock");
      setCliCopied(true);
      setTimeout(() => setCliCopied(false), 1800);
    } catch {
      setCliCopyError("Could not copy command.");
      setCliCopied(false);
    }
  };

  return (
    <section className="bg-slate-100 py-16 dark:bg-slate-900 md:py-20">
      <div className="mx-auto w-full max-w-6xl px-4">
        <div className="p-6 sm:p-8">
          <h2 className="text-center text-2xl font-semibold text-slate-900 dark:text-slate-50 sm:text-3xl">
            One prompt, any agent
          </h2>
          <p className="mx-auto mt-3 max-w-3xl text-center text-base leading-relaxed text-slate-700 dark:text-slate-300 sm:text-lg">
            Copy a ready-to-use integration prompt, paste it into your agent or
            LLM,
          </p>
          <p className="mx-auto mt-1 max-w-3xl text-center text-base leading-relaxed text-slate-700 dark:text-slate-300 sm:text-lg">
            and start using SkillDock skills right away.
          </p>
          <div className="mt-6 flex justify-center">
            <MovingBorderButton
              type="button"
              onClick={handleCopyPrompt}
              disabled={isCopying}
              containerClassName="min-w-[18rem]"
            >
              {isCopying
                ? "Copying prompt..."
                : copied
                  ? "Prompt copied. Paste it into your agent."
                  : "Copy integration prompt"}
            </MovingBorderButton>
          </div>
          {copyError ? (
            <p className="mt-3 text-center text-sm text-red-600 dark:text-red-400">
              {copyError}
            </p>
          ) : null}
          <p className="mt-7 text-center text-sm font-medium text-slate-700 dark:text-slate-300">
            Or install the CLI directly
          </p>
          <div className="mt-2 flex justify-center">
            <div className="inline-flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100">
              <code className="font-mono">pip install skilldock</code>
              <button
                type="button"
                onClick={handleCopyCliCommand}
                aria-label="Copy pip install command"
                className="inline-flex h-7 w-7 items-center justify-center rounded-md text-slate-600 transition hover:bg-slate-100 hover:text-slate-900 dark:text-slate-300 dark:hover:bg-slate-800 dark:hover:text-white"
              >
                {cliCopied ? <Check size={16} /> : <Copy size={16} />}
              </button>
            </div>
          </div>
          {cliCopyError ? (
            <p className="mt-2 text-center text-xs text-red-600 dark:text-red-400">
              {cliCopyError}
            </p>
          ) : null}
        </div>
      </div>
    </section>
  );
}
