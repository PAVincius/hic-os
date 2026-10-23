import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-full text-xs font-mono tracking-wide transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--work)] disabled:pointer-events-none disabled:opacity-40",
  {
    variants: {
      variant: {
        solid: "bg-[var(--ink)] text-[var(--card)] hover:opacity-90",
        outline: "border border-[var(--ink)] text-[var(--ink)] hover:bg-[var(--ink)]/10",
        glass: "bg-[var(--glass)] border border-[var(--glass-line)] text-[var(--fg)] backdrop-blur-xl hover:bg-white/10",
        ghost: "text-[var(--fg)] hover:bg-[var(--glass)]",
      },
      size: { default: "h-8 px-4", sm: "h-7 px-3", icon: "size-9" },
    },
    defaultVariants: { variant: "solid", size: "default" },
  },
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : "button";
    return <Comp ref={ref} className={cn(buttonVariants({ variant, size }), className)} {...props} />;
  },
);
Button.displayName = "Button";
export { buttonVariants };
