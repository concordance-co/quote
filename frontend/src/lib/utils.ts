import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatDate(date: string | Date | null | undefined): string {
  if (!date) return "N/A";
  const d = typeof date === "string" ? new Date(date) : date;
  return d.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function formatRelativeTime(date: string | Date | null | undefined): string {
  if (!date) return "N/A";
  const d = typeof date === "string" ? new Date(date) : date;
  const now = new Date();
  const diffMs = now.getTime() - d.getTime();
  const diffSecs = Math.floor(diffMs / 1000);
  const diffMins = Math.floor(diffSecs / 60);
  const diffHours = Math.floor(diffMins / 60);
  const diffDays = Math.floor(diffHours / 24);

  if (diffSecs < 60) return `${diffSecs}s ago`;
  if (diffMins < 60) return `${diffMins}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  if (diffDays < 7) return `${diffDays}d ago`;
  return formatDate(date);
}

export function formatDuration(ms: number | null | undefined): string {
  if (ms == null) return "N/A";
  if (ms < 1) return `${(ms * 1000).toFixed(2)}μs`;
  if (ms < 1000) return `${ms.toFixed(2)}ms`;
  if (ms < 60000) return `${(ms / 1000).toFixed(2)}s`;
  const minutes = Math.floor(ms / 60000);
  const seconds = ((ms % 60000) / 1000).toFixed(0);
  return `${minutes}m ${seconds}s`;
}

export function formatNumber(num: number | null | undefined, decimals = 2): string {
  if (num == null) return "N/A";
  if (Math.abs(num) >= 1e9) return `${(num / 1e9).toFixed(decimals)}B`;
  if (Math.abs(num) >= 1e6) return `${(num / 1e6).toFixed(decimals)}M`;
  if (Math.abs(num) >= 1e3) return `${(num / 1e3).toFixed(decimals)}K`;
  return num.toFixed(decimals);
}

export function formatTokensPerSec(tps: number | null | undefined): string {
  if (tps == null) return "N/A";
  return `${tps.toFixed(1)} tok/s`;
}

export function truncateText(text: string | null | undefined, maxLength = 100): string {
  if (!text) return "";
  if (text.length <= maxLength) return text;
  return text.slice(0, maxLength) + "...";
}

export function truncateId(id: string | null | undefined, length = 8): string {
  if (!id) return "N/A";
  if (id.length <= length) return id;
  return id.slice(0, length) + "...";
}
