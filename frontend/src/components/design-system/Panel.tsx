import * as React from "react";
import { cn } from "@/lib/utils";

export const DsPanel = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement>
>(({ className, ...props }, ref) => (
  <section
    ref={ref}
    className={cn("panel ds-panel", className)}
    {...props}
  />
));
DsPanel.displayName = "DsPanel";

export const DsPanelHeader = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement>
>(({ className, ...props }, ref) => (
  <header
    ref={ref}
    className={cn("panel-header ds-panel-header", className)}
    {...props}
  />
));
DsPanelHeader.displayName = "DsPanelHeader";

export const DsPanelTitle = React.forwardRef<
  HTMLSpanElement,
  React.HTMLAttributes<HTMLSpanElement>
>(({ className, ...props }, ref) => (
  <span ref={ref} className={cn("panel-title ds-panel-title", className)} {...props} />
));
DsPanelTitle.displayName = "DsPanelTitle";

export const DsPanelContent = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement>
>(({ className, ...props }, ref) => (
  <div
    ref={ref}
    className={cn("panel-content ds-panel-content", className)}
    {...props}
  />
));
DsPanelContent.displayName = "DsPanelContent";
