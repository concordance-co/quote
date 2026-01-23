import { useState, useMemo } from "react";
import { Eye, EyeOff, Palette } from "lucide-react";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import type {
  SequenceItem,
  HoveredToken,
  FilterMode,
  TokenColorMode,
} from "./types";
import { Token } from "./Token";
import {
  getFlatnessColor,
  getBranchinessColor,
  getBranchinessLabel,
  getProbabilityColor,
  getEntropyColor,
} from "./utils";

export interface TokenSequenceProps {
  /** The sequence items to display */
  items: SequenceItem[];
  /** Currently selected step */
  selectedStep?: number | null;
  /** Callback when navigating to a step */
  onNavigateToStep?: (step: number) => void;
  /** Compact mode for inline display */
  compact?: boolean;
  /** Show filter controls */
  showControls?: boolean;
  /** Show backtrack toggle control */
  showBacktrackToggle?: boolean;
  /** Show stats header */
  showStats?: boolean;
  /** Show legend */
  showLegend?: boolean;
  /** Maximum height with scroll (CSS value) */
  maxHeight?: string;
  /** Initial filter mode */
  initialFilterMode?: FilterMode;
  /** Initial show backtrack state */
  initialShowBacktrack?: boolean;
  /** Initial color mode for token coloring (uncontrolled) */
  initialColorMode?: TokenColorMode;
  /** Controlled color mode for token coloring (overrides initialColorMode) */
  colorMode?: TokenColorMode;
  /** Callback when color mode changes (for controlled mode) */
  onColorModeChange?: (mode: TokenColorMode) => void;
  /** Show color mode selector */
  showColorModeSelector?: boolean;
  /** Custom class name for container */
  className?: string;
}

export function TokenSequence({
  items,
  selectedStep,
  onNavigateToStep,
  compact = false,
  showControls = false,
  showBacktrackToggle = false,
  showStats = false,
  showLegend = false,
  maxHeight,
  initialFilterMode = "all",
  initialShowBacktrack = true,
  initialColorMode = "flatness",
  colorMode: controlledColorMode,
  onColorModeChange,
  showColorModeSelector = false,
  className,
}: TokenSequenceProps) {
  const [showBacktrack, setShowBacktrack] = useState(initialShowBacktrack);
  const [filterMode, setFilterMode] = useState<FilterMode>(initialFilterMode);
  const [internalColorMode, setInternalColorMode] =
    useState<TokenColorMode>(initialColorMode);

  // Use controlled color mode if provided, otherwise use internal state
  const colorMode = controlledColorMode ?? internalColorMode;
  const setColorMode = (mode: TokenColorMode) => {
    if (onColorModeChange) {
      onColorModeChange(mode);
    } else {
      setInternalColorMode(mode);
    }
  };
  const [hoveredToken, setHoveredToken] = useState<HoveredToken | null>(null);

  // Filter items based on settings
  const filteredItems = useMemo(() => {
    let filtered = items;

    // When showBacktrack is off, remove erased tokens but keep backtrack markers
    if (!showBacktrack) {
      filtered = filtered.filter((item) =>
        item.type === "token" ? !item.erased : true,
      );
    }

    switch (filterMode) {
      case "forced":
        return filtered.filter(
          (item) =>
            item.type === "backtrack" ||
            (item.type === "token" && item.forced && !item.erased),
        );
      case "sampled":
        return filtered.filter(
          (item) =>
            item.type === "backtrack" ||
            (item.type === "token" && !item.forced && !item.erased),
        );
      default:
        return filtered;
    }
  }, [items, showBacktrack, filterMode]);

  // Compute stats from all items
  const stats = useMemo(() => {
    const tokens = items.filter((i) => i.type === "token") as Extract<
      SequenceItem,
      { type: "token" }
    >[];
    const forced = tokens.filter((t) => t.forced && !t.erased).length;
    const sampled = tokens.filter((t) => !t.forced && !t.erased).length;
    const erased = tokens.filter((t) => t.erased).length;
    return { forced, sampled, erased, total: tokens.length };
  }, [items]);

  return (
    <div className={cn("space-y-2", className)}>
      {/* Header with stats and controls */}
      {(showStats ||
        showControls ||
        showBacktrackToggle ||
        showColorModeSelector) && (
        <div className="flex items-center justify-between gap-2 flex-wrap">
          {showStats && (
            <span className="text-2xs text-muted-foreground">
              {stats.total} tokens ({stats.forced} forced, {stats.sampled}{" "}
              sampled
              {stats.erased > 0 && `, ${stats.erased} erased`})
            </span>
          )}
          <div className="flex items-center gap-2">
            {showControls && (
              <select
                value={filterMode}
                onChange={(e) => setFilterMode(e.target.value as FilterMode)}
                className="h-6 text-2xs bg-muted border-0 rounded px-2 text-foreground"
              >
                <option value="all">All Tokens</option>
                <option value="forced">Forced Only</option>
                <option value="sampled">Sampled Only</option>
              </select>
            )}
            {showColorModeSelector && (
              <Tooltip>
                <TooltipTrigger asChild>
                  <div className="flex items-center gap-1">
                    <Palette className="h-3 w-3 text-muted-foreground" />
                    <select
                      value={colorMode}
                      onChange={(e) =>
                        setColorMode(e.target.value as TokenColorMode)
                      }
                      className="h-6 text-2xs bg-muted border-0 rounded px-2 text-foreground"
                    >
                      <option value="flatness">Color: Flatness</option>
                      <option value="branchiness">Color: Branchiness</option>
                      <option value="probability">Color: Probability</option>
                      <option value="entropy">Color: Entropy</option>
                    </select>
                  </div>
                </TooltipTrigger>
                <TooltipContent className="text-2xs max-w-xs">
                  {colorMode === "flatness" && (
                    <p>
                      <strong>Flatness:</strong> How uniform the probability
                      distribution is. High = many similar options.
                    </p>
                  )}
                  {colorMode === "branchiness" && (
                    <p>
                      <strong>Branchiness:</strong> Trajectory importance —
                      where the model is torn between a few plausible options.
                    </p>
                  )}
                  {colorMode === "probability" && (
                    <p>
                      <strong>Probability:</strong> How confident the model was
                      in this token choice.
                    </p>
                  )}
                  {colorMode === "entropy" && (
                    <p>
                      <strong>Entropy:</strong> Uncertainty in the distribution
                      (in bits). High entropy = more uncertainty.
                    </p>
                  )}
                </TooltipContent>
              </Tooltip>
            )}
            {showBacktrackToggle && (
              <Tooltip>
                <TooltipTrigger asChild>
                  <button
                    onClick={() => setShowBacktrack(!showBacktrack)}
                    className={cn(
                      "p-1.5 rounded hover:bg-muted flex items-center gap-1 text-2xs",
                      showBacktrack
                        ? "text-foreground"
                        : "text-muted-foreground",
                    )}
                  >
                    {showBacktrack ? (
                      <Eye className="h-3 w-3" />
                    ) : (
                      <EyeOff className="h-3 w-3" />
                    )}
                    <span>Backtrack</span>
                  </button>
                </TooltipTrigger>
                <TooltipContent className="text-2xs">
                  {showBacktrack
                    ? "Hide backtracked tokens"
                    : "Show backtracked tokens"}
                </TooltipContent>
              </Tooltip>
            )}
          </div>
        </div>
      )}

      {/* Token sequence */}
      <div
        className={cn(
          "flex flex-wrap items-center",
          compact ? "gap-0" : "gap-0.5",
          maxHeight && "overflow-auto scrollbar-thin",
        )}
        style={maxHeight ? { maxHeight } : undefined}
      >
        {filteredItems.map((item, idx) => {
          if (item.type === "backtrack") {
            return (
              <span key={`backtrack-${item.step}-${idx}`} className="contents">
                <span
                  className={cn(
                    "inline-flex items-center rounded font-mono border",
                    compact
                      ? "px-1.5 py-0.5 text-2xs bg-orange-900/40 text-orange-300 border-orange-700/30"
                      : "px-1.5 py-0.5 text-2xs bg-orange-900/60 text-orange-300 border-orange-700/50",
                  )}
                  style={{ marginTop: compact ? "3px" : "4px" }}
                >
                  ← {compact ? `B(${item.n})` : `Backtrack(${item.n})`}
                </span>
                {showBacktrack && !compact && <div className="w-full" />}
              </span>
            );
          }

          return (
            <Token
              key={`${item.step}-${item.token}-${idx}`}
              item={item}
              selectedStep={selectedStep}
              onNavigateToStep={onNavigateToStep}
              onHover={setHoveredToken}
              compact={compact}
              colorMode={colorMode}
            />
          );
        })}
        {filteredItems.length === 0 && (
          <span className="text-muted-foreground text-xs py-4 w-full text-center">
            No tokens to display
          </span>
        )}
      </div>

      {/* Shared Tooltip */}
      {hoveredToken && (
        <div
          className="fixed z-50 pointer-events-none"
          style={{
            left: hoveredToken.rect.left + hoveredToken.rect.width / 2,
            top: hoveredToken.rect.top - 8,
            transform: "translate(-50%, -100%)",
          }}
        >
          <div className="bg-popover border border-border rounded-md shadow-md px-2 py-1.5 text-2xs">
            <div className="space-y-0.5">
              <p>Step: {hoveredToken.item.step}</p>
              <p>Token ID: {hoveredToken.item.token}</p>
              <p
                className={cn(
                  hoveredToken.item.erased && "text-red-400",
                  hoveredToken.item.forced &&
                    !hoveredToken.item.erased &&
                    "text-pink-400",
                  !hoveredToken.item.forced &&
                    !hoveredToken.item.erased &&
                    "text-green-400",
                )}
              >
                {hoveredToken.item.erased
                  ? "Backtracked"
                  : hoveredToken.item.forced
                    ? "Forced"
                    : "Sampled"}
              </p>
              {!hoveredToken.item.forced &&
                !hoveredToken.item.erased &&
                hoveredToken.item.flatness !== null && (
                  <p>
                    <span className="text-muted-foreground">Flatness: </span>
                    <span
                      className="font-mono"
                      style={{
                        color: getFlatnessColor(hoveredToken.item.flatness),
                      }}
                    >
                      {(hoveredToken.item.flatness * 100).toFixed(0)}%
                    </span>
                  </p>
                )}
              {!hoveredToken.item.forced &&
                !hoveredToken.item.erased &&
                hoveredToken.item.prob !== null && (
                  <p>
                    <span className="text-muted-foreground">Prob: </span>
                    <span className="font-mono text-foreground">
                      {(hoveredToken.item.prob * 100).toFixed(1)}%
                    </span>
                  </p>
                )}
              {!hoveredToken.item.forced &&
                !hoveredToken.item.erased &&
                hoveredToken.item.kIndex !== null && (
                  <p>
                    <span className="text-muted-foreground">k-index: </span>
                    <span className="font-mono text-foreground">
                      {hoveredToken.item.kIndex}
                    </span>
                  </p>
                )}
              {!hoveredToken.item.forced &&
                !hoveredToken.item.erased &&
                hoveredToken.item.branchiness !== null && (
                  <div className="pt-1 mt-1 border-t border-border/50">
                    <p>
                      <span className="text-muted-foreground">
                        Branchiness:{" "}
                      </span>
                      <span
                        className="font-mono font-medium"
                        style={{
                          color: getBranchinessColor(
                            hoveredToken.item.branchiness,
                          ),
                        }}
                      >
                        {(hoveredToken.item.branchiness * 100).toFixed(0)}%
                      </span>
                      <span
                        className="ml-1 text-2xs"
                        style={{
                          color: getBranchinessColor(
                            hoveredToken.item.branchiness,
                          ),
                        }}
                      >
                        ({getBranchinessLabel(hoveredToken.item.branchiness)})
                      </span>
                    </p>
                    {hoveredToken.item.branchinessMetrics && (
                      <div className="mt-1 text-muted-foreground space-y-0.5">
                        <p className="text-3xs">
                          N<sub>eff</sub>:{" "}
                          <span className="font-mono text-foreground">
                            {hoveredToken.item.branchinessMetrics.nEff.toFixed(
                              2,
                            )}
                          </span>
                          <span className="mx-1">·</span>
                          Margin:{" "}
                          <span className="font-mono text-foreground">
                            {(
                              hoveredToken.item.branchinessMetrics.margin * 100
                            ).toFixed(1)}
                            %
                          </span>
                        </p>
                        <p className="text-3xs">
                          Top-k H:{" "}
                          <span className="font-mono text-foreground">
                            {(
                              hoveredToken.item.branchinessMetrics.topKEntropy *
                              100
                            ).toFixed(0)}
                            %
                          </span>
                          <span className="mx-1">·</span>
                          p₂/p₁:{" "}
                          <span className="font-mono text-foreground">
                            {(
                              hoveredToken.item.branchinessMetrics.ratio * 100
                            ).toFixed(0)}
                            %
                          </span>
                        </p>
                      </div>
                    )}
                  </div>
                )}
            </div>
          </div>
        </div>
      )}

      {/* Legend */}
      {showLegend && (
        <div className="flex items-center gap-4 text-2xs flex-wrap">
          {/* Token type legend */}
          <div className="flex items-center gap-1.5">
            <span className="w-3 h-3 rounded bg-pink-900/50 border border-pink-700/50" />
            <span className="text-muted-foreground">Forced</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="w-3 h-3 rounded bg-emerald-900/40 border border-emerald-700/50" />
            <span className="text-muted-foreground">Sampled</span>
          </div>
          {showBacktrack && (
            <div className="flex items-center gap-1.5">
              <span className="w-3 h-3 rounded bg-red-900/50 border border-red-700/50" />
              <span className="text-muted-foreground">Backtracked</span>
            </div>
          )}

          {/* Color scale legend based on color mode */}
          {showColorModeSelector && (
            <>
              <span className="text-muted-foreground/50 mx-1">|</span>
              {colorMode === "flatness" && (
                <>
                  <span className="text-muted-foreground">Flatness:</span>
                  <div className="flex items-center gap-1">
                    <span
                      className="w-2 h-2 rounded-full"
                      style={{ backgroundColor: getFlatnessColor(0.1) }}
                    />
                    <span className="text-muted-foreground">Low</span>
                  </div>
                  <div className="flex items-center gap-1">
                    <span
                      className="w-2 h-2 rounded-full"
                      style={{ backgroundColor: getFlatnessColor(0.5) }}
                    />
                    <span className="text-muted-foreground">Med</span>
                  </div>
                  <div className="flex items-center gap-1">
                    <span
                      className="w-2 h-2 rounded-full"
                      style={{ backgroundColor: getFlatnessColor(0.85) }}
                    />
                    <span className="text-muted-foreground">High</span>
                  </div>
                </>
              )}
              {colorMode === "branchiness" && (
                <>
                  <span className="text-muted-foreground">Branchiness:</span>
                  <div className="flex items-center gap-1">
                    <span
                      className="w-2 h-2 rounded-full"
                      style={{ backgroundColor: getBranchinessColor(0.1) }}
                    />
                    <span className="text-muted-foreground">Confident</span>
                  </div>
                  <div className="flex items-center gap-1">
                    <span
                      className="w-2 h-2 rounded-full"
                      style={{ backgroundColor: getBranchinessColor(0.45) }}
                    />
                    <span className="text-muted-foreground">Moderate</span>
                  </div>
                  <div className="flex items-center gap-1">
                    <span
                      className="w-2 h-2 rounded-full"
                      style={{ backgroundColor: getBranchinessColor(0.65) }}
                    />
                    <span className="text-muted-foreground">High</span>
                  </div>
                  <div className="flex items-center gap-1">
                    <span
                      className="w-2 h-2 rounded-full"
                      style={{ backgroundColor: getBranchinessColor(0.85) }}
                    />
                    <span className="text-muted-foreground">Critical</span>
                  </div>
                </>
              )}
              {colorMode === "probability" && (
                <>
                  <span className="text-muted-foreground">Probability:</span>
                  <div className="flex items-center gap-1">
                    <span
                      className="w-2 h-2 rounded-full"
                      style={{ backgroundColor: getProbabilityColor(0.9) }}
                    />
                    <span className="text-muted-foreground">High</span>
                  </div>
                  <div className="flex items-center gap-1">
                    <span
                      className="w-2 h-2 rounded-full"
                      style={{ backgroundColor: getProbabilityColor(0.5) }}
                    />
                    <span className="text-muted-foreground">Med</span>
                  </div>
                  <div className="flex items-center gap-1">
                    <span
                      className="w-2 h-2 rounded-full"
                      style={{ backgroundColor: getProbabilityColor(0.15) }}
                    />
                    <span className="text-muted-foreground">Low</span>
                  </div>
                  <div className="flex items-center gap-1">
                    <span
                      className="w-2 h-2 rounded-full"
                      style={{ backgroundColor: getProbabilityColor(0.02) }}
                    />
                    <span className="text-muted-foreground">Rare</span>
                  </div>
                </>
              )}
              {colorMode === "entropy" && (
                <>
                  <span className="text-muted-foreground">Entropy:</span>
                  <div className="flex items-center gap-1">
                    <span
                      className="w-2 h-2 rounded-full"
                      style={{ backgroundColor: getEntropyColor(0.3) }}
                    />
                    <span className="text-muted-foreground">Low</span>
                  </div>
                  <div className="flex items-center gap-1">
                    <span
                      className="w-2 h-2 rounded-full"
                      style={{ backgroundColor: getEntropyColor(1.5) }}
                    />
                    <span className="text-muted-foreground">Med</span>
                  </div>
                  <div className="flex items-center gap-1">
                    <span
                      className="w-2 h-2 rounded-full"
                      style={{ backgroundColor: getEntropyColor(3.0) }}
                    />
                    <span className="text-muted-foreground">High</span>
                  </div>
                  <div className="flex items-center gap-1">
                    <span
                      className="w-2 h-2 rounded-full"
                      style={{ backgroundColor: getEntropyColor(4.5) }}
                    />
                    <span className="text-muted-foreground">V.High</span>
                  </div>
                </>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}
