"use client";

import { Moon, Sun } from "lucide-react";
import { useEffect, useState } from "react";

const STORAGE_KEY = "skilldock-theme";

type Theme = "light" | "dark";

function applyTheme(theme: Theme) {
  document.documentElement.classList.toggle("light", theme === "light");
  document.documentElement.classList.toggle("dark", theme === "dark");
}

export function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>(() => {
    if (typeof window === "undefined") return "light";
    const savedTheme = localStorage.getItem(STORAGE_KEY) as Theme | null;
    return savedTheme === "light" || savedTheme === "dark"
      ? savedTheme
      : "light";
  });

  useEffect(() => {
    applyTheme(theme);
    localStorage.setItem(STORAGE_KEY, theme);
  }, [theme]);

  const toggleTheme = () => {
    setTheme((prevTheme) => (prevTheme === "dark" ? "light" : "dark"));
  };

  return (
    <button
      type="button"
      onClick={toggleTheme}
      aria-label="Toggle theme"
      className="inline-flex h-9 w-9 items-center justify-center rounded-md border border-neutral-300/80 bg-white/80 text-neutral-700 transition-colors hover:bg-white dark:border-white/20 dark:bg-black/40 dark:text-white dark:hover:bg-white/10"
    >
      {theme === "dark" ? (
        <Sun className="h-4 w-4" />
      ) : (
        <Moon className="h-4 w-4" />
      )}
    </button>
  );
}
