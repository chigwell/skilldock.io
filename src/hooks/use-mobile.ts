"use client";

import { useEffect, useState } from "react";

const MOBILE_BREAKPOINT = 768;

export function useIsMobile() {
  const [isMobile, setIsMobile] = useState<boolean>(false);

  useEffect(() => {
    const mediaQuery = window.matchMedia(
      `(max-width: ${MOBILE_BREAKPOINT - 1}px)`,
    );
    const onChange = () => setIsMobile(window.innerWidth < MOBILE_BREAKPOINT);

    onChange();
    mediaQuery.addEventListener("change", onChange);
    return () => mediaQuery.removeEventListener("change", onChange);
  }, []);

  return isMobile;
}
