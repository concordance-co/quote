import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center rounded border px-1.5 py-0.5 text-2xs font-medium transition-colors focus:outline-none focus:ring-1 focus:ring-ring",
  {
    variants: {
      variant: {
        default:
          "border-transparent bg-primary text-primary-foreground hover:bg-primary/80",
        secondary:
          "border-transparent bg-secondary text-secondary-foreground hover:bg-secondary/80",
        destructive:
          "border-transparent bg-destructive text-destructive-foreground hover:bg-destructive/80",
        outline: "text-foreground border-border",
        success: "border-green-700/50 bg-green-900/40 text-green-300",
        warning: "border-yellow-700/50 bg-yellow-900/40 text-yellow-300",
        info: "border-blue-700/50 bg-blue-900/40 text-blue-300",
        // Event types
        prefilled: "border-violet-700/50 bg-violet-900/40 text-violet-300",
        forwardpass: "border-blue-700/50 bg-blue-900/40 text-blue-300",
        sampled: "border-amber-700/50 bg-amber-900/40 text-amber-300",
        added: "border-green-700/50 bg-green-900/40 text-green-300",
        // Action types
        noop: "border-slate-600 bg-slate-800 text-slate-400",
        forcetokens: "border-pink-700/50 bg-pink-900/40 text-pink-300",
        forceoutput: "border-rose-700/50 bg-rose-900/40 text-rose-300",
        backtrack: "border-orange-700/50 bg-orange-900/40 text-orange-300",
        adjustedlogits: "border-cyan-700/50 bg-cyan-900/40 text-cyan-300",
        adjustedprefill:
          "border-indigo-700/50 bg-indigo-900/40 text-indigo-300",
        toolcalls: "border-teal-700/50 bg-teal-900/40 text-teal-300",
        emiterror: "border-red-700/50 bg-red-900/40 text-red-300",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  },
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, ...props }: BadgeProps) {
  return (
    <div className={cn(badgeVariants({ variant }), className)} {...props} />
  );
}

export { Badge, badgeVariants };
