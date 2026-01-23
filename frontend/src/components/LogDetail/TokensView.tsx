import { useState, useEffect, useMemo } from "react";
import { Play, Pause, RotateCcw, Eye, EyeOff, Palette } from "lucide-react";
import { Slider } from "@/components/ui/slider";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import type { LogResponse } from "@/types/api";
import {
  TokenSequence,
  useTokenTimeline,
  type SequenceItem,
  type FilterMode,
  type TokenColorMode,
  getFlatnessColor,
  getBranchinessColor,
  getProbabilityColor,
  getEntropyColor,
} from "@/components/TokenSequence";

interface TokensViewProps {
  log: LogResponse;
  selectedStep: number | null;
  onSelectStep: (step: number | null) => void;
  onNavigateToTrace?: (step: number) => void;
  /** Hide the user prompt panel (useful when prompt is shown elsewhere) */
  hideUserPrompt?: boolean;
  /** Disable internal max-height constraints to allow parent scrolling */
  noScrollConstraints?: boolean;
}

export function TokensView({
  log,
  selectedStep,
  onSelectStep,
  onNavigateToTrace,
  hideUserPrompt = false,
  noScrollConstraints = false,
}: TokensViewProps) {
  const [scrubberPosition, setScrubberPosition] = useState<number>(100);
  const [isPlaying, setIsPlaying] = useState(false);
  const [showBacktrack, setShowBacktrack] = useState(true);
  const [filterMode, setFilterMode] = useState<FilterMode>("all");
  const [colorMode, setColorMode] = useState<TokenColorMode>("probability");

  // Use the shared hook to build timeline
  const { timeline, maxSequenceOrder } = useTokenTimeline(log);

  // Get items at current scrubber position
  const itemsAtPosition = useMemo(() => {
    if (timeline.length === 0) return [];

    const targetSeqOrder = (scrubberPosition / 100) * maxSequenceOrder;
    let result: SequenceItem[] = [];

    for (const snapshot of timeline) {
      if (snapshot.sequenceOrder <= targetSeqOrder) {
        result = snapshot.items;
      } else {
        break;
      }
    }

    return result;
  }, [timeline, scrubberPosition, maxSequenceOrder]);

  // Filter items based on settings
  const filteredItems = useMemo(() => {
    let items = itemsAtPosition;

    // When showBacktrack is off, remove erased tokens but keep backtrack markers
    if (!showBacktrack) {
      items = items.filter((item) =>
        item.type === "token" ? !item.erased : true,
      );
    }

    switch (filterMode) {
      case "forced":
        return items.filter(
          (item) =>
            item.type === "backtrack" ||
            (item.type === "token" && item.forced && !item.erased),
        );
      case "sampled":
        return items.filter(
          (item) =>
            item.type === "backtrack" ||
            (item.type === "token" && !item.forced && !item.erased),
        );
      default:
        return items;
    }
  }, [itemsAtPosition, showBacktrack, filterMode]);

  // Compute stats from final state
  const stats = useMemo(() => {
    const finalItems =
      timeline.length > 0 ? timeline[timeline.length - 1].items : [];
    const tokens = finalItems.filter((i) => i.type === "token") as Extract<
      SequenceItem,
      { type: "token" }
    >[];
    const forced = tokens.filter((t) => t.forced && !t.erased).length;
    const sampled = tokens.filter((t) => !t.forced && !t.erased).length;
    const erased = tokens.filter((t) => t.erased).length;
    return { forced, sampled, erased, total: tokens.length };
  }, [timeline]);

  // Playback logic
  useEffect(() => {
    if (!isPlaying) return;

    const interval = setInterval(() => {
      setScrubberPosition((prev) => {
        if (prev >= 100) {
          setIsPlaying(false);
          return 100;
        }
        return Math.min(prev + 2, 100);
      });
    }, 100);

    return () => clearInterval(interval);
  }, [isPlaying]);

  const handlePlayPause = () => {
    if (scrubberPosition >= 100) {
      setScrubberPosition(0);
    }
    setIsPlaying(!isPlaying);
  };

  const handleReset = () => {
    setIsPlaying(false);
    setScrubberPosition(0);
  };

  const handleNavigateToStep = (step: number) => {
    if (onNavigateToTrace) {
      onNavigateToTrace(step);
    } else {
      onSelectStep(step);
    }
  };

  return (
    <div className="space-y-2">
      {/* Prompt */}
      {!hideUserPrompt && log.user_prompt && (
        <div className="panel">
          <div className="panel-header">
            <span className="panel-title">User Prompt</span>
          </div>
          <div className="panel-content">
            <div
              className={cn(
                "bg-black/30 rounded p-2 font-mono text-xs whitespace-pre-wrap",
                !noScrollConstraints &&
                  "max-h-[150px] overflow-auto scrollbar-thin",
              )}
            >
              {log.user_prompt}
            </div>
          </div>
        </div>
      )}
      {/* Final Output */}
      <div className="panel">
        <div className="panel-header">
          <span className="panel-title">Generated Output</span>
        </div>
        <div className="panel-content">
          <div
            className={cn(
              "bg-black/30 rounded p-2 font-mono text-xs whitespace-pre-wrap",
              !noScrollConstraints &&
                "max-h-[200px] overflow-auto scrollbar-thin",
            )}
          >
            {log.final_text || "No output generated"}
          </div>
        </div>
      </div>

      {/* Token Sequence with Scrubber */}
      <div className="panel">
        <div className="panel-header flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="panel-title">Token Sequence</span>
            <span className="text-2xs text-muted-foreground">
              {stats.total} tokens ({stats.forced} forced, {stats.sampled}{" "}
              sampled
              {stats.erased > 0 && `, ${stats.erased} erased`})
            </span>
          </div>
          <div className="flex items-center gap-2">
            {/* Filter dropdown */}
            <select
              value={filterMode}
              onChange={(e) => setFilterMode(e.target.value as FilterMode)}
              className="h-6 text-2xs bg-muted border-0 rounded px-2 text-foreground"
            >
              <option value="all">All Tokens</option>
              <option value="forced">Forced Only</option>
              <option value="sampled">Sampled Only</option>
            </select>
            {/* Color mode selector */}
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
                    <strong>Branchiness:</strong> Trajectory importance — where
                    the model is torn between a few plausible options.
                  </p>
                )}
                {colorMode === "probability" && (
                  <p>
                    <strong>Probability:</strong> How confident the model was in
                    this token choice.
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
            {/* Show/hide backtrack toggle */}
            <Tooltip>
              <TooltipTrigger asChild>
                <button
                  onClick={() => setShowBacktrack(!showBacktrack)}
                  className={cn(
                    "p-1.5 rounded hover:bg-muted flex items-center gap-1 text-2xs",
                    showBacktrack ? "text-foreground" : "text-muted-foreground",
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
          </div>
        </div>

        {/* Scrubber Controls */}
        <div className="px-3 py-2 border-b border-border/50 flex items-center gap-3">
          <div className="flex items-center gap-1">
            <Tooltip>
              <TooltipTrigger asChild>
                <button
                  onClick={handlePlayPause}
                  className="p-1.5 rounded hover:bg-muted transition-colors"
                >
                  {isPlaying ? (
                    <Pause className="h-3.5 w-3.5" />
                  ) : (
                    <Play className="h-3.5 w-3.5" />
                  )}
                </button>
              </TooltipTrigger>
              <TooltipContent className="text-2xs">
                {isPlaying ? "Pause" : "Play"}
              </TooltipContent>
            </Tooltip>
            <Tooltip>
              <TooltipTrigger asChild>
                <button
                  onClick={handleReset}
                  className="p-1.5 rounded hover:bg-muted transition-colors"
                >
                  <RotateCcw className="h-3.5 w-3.5" />
                </button>
              </TooltipTrigger>
              <TooltipContent className="text-2xs">Reset</TooltipContent>
            </Tooltip>
          </div>
          <div className="flex-1">
            <Slider
              value={scrubberPosition}
              min={0}
              max={100}
              step={1}
              onValueChange={(values) => setScrubberPosition(values[0])}
            />
          </div>
          <span className="text-2xs text-muted-foreground w-12 text-right">
            {Math.round(scrubberPosition)}%
          </span>
        </div>

        <div className="panel-content">
          <TokenSequence
            items={filteredItems}
            selectedStep={selectedStep}
            onNavigateToStep={handleNavigateToStep}
            initialShowBacktrack={showBacktrack}
            colorMode={colorMode}
          />
          {filteredItems.length === 0 && (
            <span className="text-muted-foreground text-xs py-4 w-full text-center block">
              {scrubberPosition < 100
                ? "Scrub timeline to see tokens..."
                : "No tokens match filter"}
            </span>
          )}
        </div>
      </div>

      {/* Legend */}
      <div className="panel">
        <div className="px-3 py-2 flex items-center gap-4 text-2xs flex-wrap">
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
        </div>
      </div>
    </div>
  );
}
