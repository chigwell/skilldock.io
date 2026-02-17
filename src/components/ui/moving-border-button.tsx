"use client";

import React, { useRef } from "react";
import {
  motion,
  useAnimationFrame,
  useMotionTemplate,
  useMotionValue,
  useTransform,
} from "motion/react";

import { cn } from "@/lib/utils";

type MovingBorderProps = {
  children: React.ReactNode;
  duration?: number;
  rx?: string;
  ry?: string;
};

type MovingBorderButtonProps = React.ButtonHTMLAttributes<HTMLButtonElement> & {
  borderRadius?: string;
  containerClassName?: string;
  borderClassName?: string;
  duration?: number;
};

export function MovingBorderButton({
  borderRadius = "0.75rem",
  children,
  containerClassName,
  borderClassName,
  duration,
  className,
  ...otherProps
}: MovingBorderButtonProps) {
  return (
    <button
      className={cn(
        "relative overflow-hidden bg-transparent p-[1px]",
        "min-h-12 min-w-40",
        containerClassName,
      )}
      style={{ borderRadius }}
      {...otherProps}
    >
      <div
        className="absolute inset-0"
        style={{ borderRadius: `calc(${borderRadius} * 0.96)` }}
      >
        <MovingBorder duration={duration} rx="18%" ry="18%">
          <div
            className={cn(
              "h-20 w-20 opacity-80 bg-[radial-gradient(circle,var(--color-sky-500)_40%,transparent_60%)]",
              borderClassName,
            )}
          />
        </MovingBorder>
      </div>

      <div
        className={cn(
          "relative flex min-h-[calc(3rem-2px)] w-full items-center justify-center px-6 py-2 border border-slate-300 bg-white text-sm text-slate-900 antialiased backdrop-blur-xl dark:border-slate-800 dark:bg-slate-900/80 dark:text-white",
          className,
        )}
        style={{ borderRadius: `calc(${borderRadius} * 0.96)` }}
      >
        {children}
      </div>
    </button>
  );
}

export function MovingBorder({
  children,
  duration = 2000,
  rx,
  ry,
}: MovingBorderProps) {
  const pathRef = useRef<SVGRectElement | null>(null);
  const progress = useMotionValue(0);

  useAnimationFrame((time) => {
    const length = pathRef.current?.getTotalLength();
    if (!length) return;
    const pxPerMillisecond = length / duration;
    progress.set((time * pxPerMillisecond) % length);
  });

  const x = useTransform(progress, (value) => {
    return pathRef.current?.getPointAtLength(value).x ?? 0;
  });
  const y = useTransform(progress, (value) => {
    return pathRef.current?.getPointAtLength(value).y ?? 0;
  });

  const transform = useMotionTemplate`translateX(${x}px) translateY(${y}px) translateX(-50%) translateY(-50%)`;

  return (
    <>
      <svg
        xmlns="http://www.w3.org/2000/svg"
        preserveAspectRatio="none"
        className="absolute h-full w-full"
        width="100%"
        height="100%"
      >
        <rect ref={pathRef} fill="none" width="100%" height="100%" rx={rx} ry={ry} />
      </svg>
      <motion.div
        style={{
          position: "absolute",
          top: 0,
          left: 0,
          display: "inline-block",
          transform,
        }}
      >
        {children}
      </motion.div>
    </>
  );
}
