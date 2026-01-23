import { memo } from "react";
import { cn } from "@/lib/utils";
import type { SequenceItem, HoveredToken, TokenColorMode } from "./types";
import {
  getFlatnessColor,
  getBranchinessColor,
  getProbabilityColor,
  getEntropyColor,
} from "./utils";

export interface TokenProps {
  item: Extract<SequenceItem, { type: "token" }>;
  selectedStep?: number | null;
  onNavigateToStep?: (step: number) => void;
  onHover?: (hovered: HoveredToken | null) => void;
  /** Compact mode for inline display (smaller text, less padding) */
  compact?: boolean;
  /** Color mode for token border coloring */
  colorMode?: TokenColorMode;
}

/**
 * Get the border color for a token based on the color mode.
 */
function getTokenBorderColor(
  item: Extract<SequenceItem, { type: "token" }>,
  colorMode: TokenColorMode,
): string {
  // Erased tokens always show red
  if (item.erased) {
    return "rgba(185, 28, 28, 0.5)";
  }

  // Forced tokens always show pink
  if (item.forced) {
    return "rgba(190, 24, 93, 0.5)";
  }

  // For sampled tokens, use the color mode
  switch (colorMode) {
    case "branchiness":
      if (item.branchiness !== null) {
        return getBranchinessColor(item.branchiness);
      }
      break;
    case "probability":
      if (item.prob !== null) {
        return getProbabilityColor(item.prob);
      }
      break;
    case "entropy":
      if (item.entropy !== null) {
        return getEntropyColor(item.entropy);
      }
      break;
    case "flatness":
    default:
      if (item.flatness !== null) {
        return getFlatnessColor(item.flatness);
      }
      break;
  }

  // Default fallback color (green for sampled)
  return "rgba(4, 120, 87, 0.5)";
}

export const Token = memo(function Token({
  item,
  selectedStep,
  onNavigateToStep,
  onHover,
  compact = false,
  colorMode = "flatness",
}: TokenProps) {
  // Check if token contains a newline
  const hasNewline = item.token_text.includes("\n");
  // Display text: replace newlines with visible indicator
  const displayText = hasNewline
    ? item.token_text.replace(/\n/g, "↵")
    : item.token_text;

  // Calculate border color based on color mode
  const borderColor = getTokenBorderColor(item, colorMode);

  const handleMouseEnter = (e: React.MouseEvent<HTMLButtonElement>) => {
    if (onHover) {
      const rect = e.currentTarget.getBoundingClientRect();
      onHover({ item, rect });
    }
  };

  const handleMouseLeave = () => {
    if (onHover) {
      onHover(null);
    }
  };

  const handleClick = () => {
    if (onNavigateToStep) {
      onNavigateToStep(item.step);
    }
  };

  return (
    <span className="contents">
      <button
        onClick={handleClick}
        onMouseEnter={handleMouseEnter}
        onMouseLeave={handleMouseLeave}
        className={cn(
          "inline-flex items-center rounded-sm font-mono transition-colors whitespace-pre",
          compact ? "px-0.5 py-0.5 text-2xs" : "px-1 py-0.5 text-2xs",
          item.erased
            ? "bg-red-900/50 text-red-300 line-through"
            : item.forced
              ? "bg-pink-900/50 text-pink-300 hover:bg-pink-900/70"
              : "bg-emerald-900/40 text-emerald-300 hover:bg-emerald-900/60",
          selectedStep === item.step &&
            "ring-1 ring-primary ring-offset-1 ring-offset-background",
        )}
        style={{
          borderWidth: "0.5px",
          borderStyle: "solid",
          marginTop: compact ? "3px" : "4px",
          paddingLeft: compact ? "3px" : "4px",
          paddingRight: compact ? "3px" : "4px",
          borderColor,
        }}
      >
        {displayText}
      </button>
      {hasNewline && <div className="w-full" />}
    </span>
  );
});
