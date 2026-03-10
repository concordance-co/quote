import * as React from "react";

import { cn } from "@/lib/utils";

type FormFieldProps = {
  label: string;
  required?: boolean;
  helperText?: string;
  errorText?: string;
  className?: string;
  children: React.ReactNode;
};

export function FormField({
  label,
  required = false,
  helperText,
  errorText,
  className,
  children,
}: FormFieldProps) {
  const hasError = Boolean(errorText);

  return (
    <label className={cn("grid gap-1.5", className)}>
      <span className="font-mono text-[10px] uppercase tracking-[0.08em] opacity-80">
        {label}
        {required ? " *" : ""}
      </span>
      {children}
      {hasError ? (
        <span className="font-mono text-[11px] text-destructive">{errorText}</span>
      ) : helperText ? (
        <span className="font-mono text-[11px] opacity-70">{helperText}</span>
      ) : null}
    </label>
  );
}

export const formFieldInputClassName =
  "ds-input w-full rounded-md border border-input bg-background px-3 py-2 text-sm text-foreground outline-none transition-[border-color,box-shadow] placeholder:text-muted-foreground focus:border-primary focus-visible:ring-2 focus-visible:ring-[var(--brand-blue)] disabled:opacity-50";

export const formFieldTextareaClassName = cn(
  formFieldInputClassName,
  "min-h-[86px] resize-y",
);
