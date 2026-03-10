import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "ds-button inline-flex items-center justify-center whitespace-nowrap rounded-full border text-xs font-medium tracking-[0.04em] ring-offset-background transition-[background-color,border-color,box-shadow,transform] duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--brand-blue)] focus-visible:ring-offset-2 focus-visible:ring-offset-background disabled:pointer-events-none disabled:opacity-50",
  {
    variants: {
      variant: {
        default:
          "ds-button--default border-black/45 bg-black/90 text-white shadow-[0_1px_0_rgba(255,255,255,0.16)_inset] hover:-translate-y-px hover:bg-black hover:shadow-[0_10px_22px_rgba(8,8,8,0.28)]",
        destructive:
          "ds-button--destructive border-red-400/50 bg-red-500/20 text-red-200 hover:bg-red-500/30",
        outline:
          "ds-button--outline border-border bg-transparent text-foreground hover:-translate-y-px hover:bg-accent/50",
        secondary:
          "ds-button--secondary border-border bg-secondary text-foreground hover:-translate-y-px hover:bg-accent",
        ghost: "ds-button--ghost border-transparent bg-transparent text-foreground hover:bg-accent/50",
        link: "ds-button--link border-transparent bg-transparent text-primary underline-offset-4 hover:underline",
      },
      size: {
        default: "h-8 px-3.5 py-1.5",
        sm: "h-7 px-2.5",
        lg: "h-9 px-5",
        icon: "h-8 w-8",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  },
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : "button";
    return (
      <Comp
        className={cn(buttonVariants({ variant, size, className }))}
        ref={ref}
        {...props}
      />
    );
  },
);
Button.displayName = "Button";

export { Button, buttonVariants };
