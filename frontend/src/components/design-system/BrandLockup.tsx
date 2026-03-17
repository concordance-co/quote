import { Link } from "react-router-dom";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

type Tone = "light" | "dark";

type BaseProps = {
  className?: string;
  iconClassName?: string;
  labelClassName?: string;
  label?: string;
  href?: string;
  tone?: Tone;
  showLabel?: boolean;
} & VariantProps<typeof lockupVariants>;

const lockupVariants = cva("inline-flex items-center", {
  variants: {
    size: {
      sm: "gap-2",
      md: "gap-3",
      lg: "gap-3.5",
    },
  },
  defaultVariants: {
    size: "md",
  },
});

const iconVariants = cva("object-contain shrink-0", {
  variants: {
    size: {
      sm: "h-4 w-4",
      md: "h-5 w-5",
      lg: "h-8 w-8 md:h-10 md:w-10",
    },
  },
  defaultVariants: {
    size: "md",
  },
});

const labelVariants = cva("font-display font-semibold leading-none tracking-tight", {
  variants: {
    size: {
      sm: "text-sm",
      md: "text-[0.95rem]",
      lg: "text-[1.8rem] md:text-[2.15rem]",
    },
    tone: {
      light: "text-white",
      dark: "text-[var(--brand-ink)]",
    },
  },
  defaultVariants: {
    size: "md",
    tone: "dark",
  },
});

function iconSrcForTone(tone: Tone): string {
  return tone === "light"
    ? "/concordance_icon_white.png"
    : "/concordance_icon_black.png";
}

function LockupContent({
  size,
  tone = "dark",
  iconClassName,
  labelClassName,
  label = "Concordance",
  showLabel = true,
}: Pick<
  BaseProps,
  "size" | "tone" | "iconClassName" | "labelClassName" | "label" | "showLabel"
>) {
  return (
    <>
      <img
        src={iconSrcForTone(tone)}
        alt=""
        aria-hidden="true"
        className={cn(iconVariants({ size }), iconClassName)}
      />
      {showLabel ? (
        <span className={cn(labelVariants({ size, tone }), labelClassName)}>{label}</span>
      ) : null}
    </>
  );
}

export function BrandLockup({
  className,
  iconClassName,
  labelClassName,
  label,
  href,
  tone = "dark",
  size,
  showLabel = true,
}: BaseProps) {
  if (href) {
    return (
      <Link
        to={href}
        aria-label="Concordance home"
        className={cn(
          lockupVariants({ size }),
          "rounded-sm transition-transform duration-150 hover:scale-[1.02] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--brand-blue)] focus-visible:ring-offset-2 focus-visible:ring-offset-transparent",
          className,
        )}
      >
        <LockupContent
          size={size}
          tone={tone}
          iconClassName={iconClassName}
          labelClassName={labelClassName}
          label={label}
          showLabel={showLabel}
        />
      </Link>
    );
  }

  return (
    <div className={cn(lockupVariants({ size }), className)}>
      <LockupContent
        size={size}
        tone={tone}
        iconClassName={iconClassName}
        labelClassName={labelClassName}
        label={label}
        showLabel={showLabel}
      />
    </div>
  );
}
