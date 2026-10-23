import * as React from "react";
import { cn } from "@/lib/utils";

export const Card = ({ className, ...p }: React.HTMLAttributes<HTMLDivElement>) => (
  <div className={cn("rounded-[var(--r)] bg-[var(--card)] text-[var(--ink)] p-4", className)} {...p} />
);
export const CardLabel = ({ className, ...p }: React.HTMLAttributes<HTMLDivElement>) => (
  <div className={cn("font-mono text-[10px] uppercase tracking-[.14em] text-[var(--ink-mute)]", className)} {...p} />
);
