import { Link } from "react-router-dom";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

const navLinkVariants = cva(
  "transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 rounded-xs",
  {
    variants: {
      tone: {
        default:
          "text-muted-foreground hover:text-foreground font-semibold focus-visible:ring-ring focus-visible:ring-offset-background",
        red: "font-mono text-xs uppercase tracking-[0.08em] text-[var(--brand-ink)] hover:text-white focus-visible:ring-[var(--brand-ink)] focus-visible:ring-offset-transparent",
      },
      mobile: {
        true: "w-fit",
        false: "",
      },
      active: {
        true: "underline decoration-[1px] underline-offset-4",
        false: "",
      },
    },
    defaultVariants: {
      tone: "default",
      mobile: false,
      active: false,
    },
  },
);

export type DsNavLinkProps = VariantProps<typeof navLinkVariants> & {
  href: string;
  label: string;
  external?: boolean;
  className?: string;
};

export function DsNavLink({
  href,
  label,
  external,
  tone,
  mobile,
  active,
  className,
}: DsNavLinkProps) {
  const classes = cn(navLinkVariants({ tone, mobile, active }), className);

  if (external) {
    return (
      <a href={href} className={classes} target="_blank" rel="noopener noreferrer">
        {label}
      </a>
    );
  }

  return (
    <Link to={href} className={classes}>
      {label}
    </Link>
  );
}
