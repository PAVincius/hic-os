import * as React from "react";
import { cn } from "@/lib/utils";

export const Badge = ({ className, hot, ...p }: React.HTMLAttributes<HTMLSpanElement> & { hot?: boolean }) => (
  <span
    className={cn("inline-flex rounded-full px-3 py-1 font-mono text-[11px] text-[var(--ink)]", hot ? "bg-[var(--work)]" : "bg-[var(--card-2)]", className)}
    {...p}
  />
);
