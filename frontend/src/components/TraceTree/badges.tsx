import { memo } from "react";
import { cn } from "@/lib/utils";
import type { BadgeStyle } from "./types";

// Event type badge with color coding
export const EventBadge = memo(function EventBadge({ type }: { type: string }) {
  const config: Record<string, BadgeStyle> = {
    Prefilled: {
      bg: "bg-blue-500/20",
      text: "text-blue-300",
      border: "border-blue-500/30",
    },
    ForwardPass: {
      bg: "bg-emerald-500/20",
      text: "text-emerald-300",
      border: "border-emerald-500/30",
    },
    Sampled: {
      bg: "bg-purple-500/20",
      text: "text-purple-300",
      border: "border-purple-500/30",
    },
    Added: {
      bg: "bg-pink-500/20",
      text: "text-pink-300",
      border: "border-pink-500/30",
    },
  };

  const style = config[type] || {
    bg: "bg-muted",
    text: "text-muted-foreground",
    border: "border-border",
  };

  return (
    <span
      className={cn(
        "px-1.5 py-0 rounded text-2xs font-medium border",
        style.bg,
        style.text,
        style.border
      )}
    >
      {type}
    </span>
  );
});

// Action type badge
export const ActionBadge = memo(function ActionBadge({
  type,
}: {
  type: string;
}) {
  const config: Record<string, BadgeStyle> = {
    ForceTokens: {
      bg: "bg-pink-500/20",
      text: "text-pink-300",
      border: "border-pink-500/30",
    },
    ForceOutput: {
      bg: "bg-rose-500/20",
      text: "text-rose-300",
      border: "border-rose-500/30",
    },
    Backtrack: {
      bg: "bg-orange-500/20",
      text: "text-orange-300",
      border: "border-orange-500/30",
    },
    AdjustedLogits: {
      bg: "bg-cyan-500/20",
      text: "text-cyan-300",
      border: "border-cyan-500/30",
    },
    AdjustedPrefill: {
      bg: "bg-teal-500/20",
      text: "text-teal-300",
      border: "border-teal-500/30",
    },
    ToolCalls: {
      bg: "bg-indigo-500/20",
      text: "text-indigo-300",
      border: "border-indigo-500/30",
    },
    EmitError: {
      bg: "bg-red-500/20",
      text: "text-red-300",
      border: "border-red-500/30",
    },
    Noop: {
      bg: "bg-slate-500/20",
      text: "text-slate-400",
      border: "border-slate-500/30",
    },
  };

  const style = config[type] || {
    bg: "bg-muted",
    text: "text-muted-foreground",
    border: "border-border",
  };

  return (
    <span
      className={cn(
        "px-1.5 py-0 rounded text-2xs font-medium border",
        style.bg,
        style.text,
        style.border
      )}
    >
      {type}
    </span>
  );
});

// Log level badge
export const LogLevelBadge = memo(function LogLevelBadge({
  level,
}: {
  level: string;
}) {
  const config: Record<string, { bg: string; text: string }> = {
    DEBUG: { bg: "bg-slate-500/20", text: "text-slate-400" },
    INFO: { bg: "bg-blue-500/20", text: "text-blue-400" },
    WARNING: { bg: "bg-yellow-500/20", text: "text-yellow-400" },
    ERROR: { bg: "bg-red-500/20", text: "text-red-400" },
  };

  const style = config[level] || {
    bg: "bg-muted",
    text: "text-muted-foreground",
  };

  return (
    <span
      className={cn(
        "px-1 py-0 rounded text-2xs font-medium shrink-0",
        style.bg,
        style.text
      )}
    >
      {level}
    </span>
  );
});
