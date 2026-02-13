"use client";

import { motion } from "motion/react";
import { cn } from "@/lib/utils";

export interface SkeletonProps {
  width?: string | number;
  height?: string | number;
  radius?: "none" | "sm" | "md" | "lg" | "xl" | "full";
  animation?: "pulse" | "wave" | "none";
  className?: string;
}

export default function Skeleton({
  width = "100%",
  height = "1rem",
  radius = "md",
  animation = "pulse",
  className,
}: SkeletonProps) {
  const radiusClasses = {
    none: "rounded-none",
    sm: "rounded-sm",
    md: "rounded-md",
    lg: "rounded-lg",
    xl: "rounded-xl",
    full: "rounded-full",
  };

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.98 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ duration: 0.25, ease: "easeOut" }}
      className={cn(
        "bg-linear-to-r from-slate-200 via-slate-100 to-slate-200 dark:from-slate-800 dark:via-slate-700 dark:to-slate-800",
        radiusClasses[radius],
        animation === "pulse" && "animate-pulse",
        animation === "wave" && "animate-shimmer [background-size:200%_100%]",
        className,
      )}
      style={{
        width: typeof width === "number" ? `${width}px` : width,
        height: typeof height === "number" ? `${height}px` : height,
      }}
    />
  );
}
