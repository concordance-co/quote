import { useState, useMemo, useEffect } from "react";
import { ChevronDown, ChevronRight, Sparkles, Zap, Info } from "lucide-react";
import { cn } from "@/lib/utils";
import type { FeatureTimelineEntry, FeatureActivation } from "@/lib/api";
import type { LogResponse } from "@/types/api";
import { useTokenTimeline } from "@/components/TokenSequence";

interface FeatureTimelineProps {
  timeline: FeatureTimelineEntry[];
  log?: LogResponse;
  promptTokenCount?: number;
  className?: string;
  /** Callback when injection positions are calculated */
  onInjectionPositions?: (positions: number[]) => void;
}

/**
 * Extract forced token positions from the token timeline.
 * Uses useTokenTimeline's final items which correctly track forced status.
 *
 * @param log - The log response to process
 * @param promptTokenOffset - Number of prompt tokens to offset positions (default 0).
 */
function useInjectionPositions(log?: LogResponse, promptTokenOffset: number = 0): Set<number> {
  const { timeline } = useTokenTimeline(log ?? {
    request_id: '', created_ts: '', finished_ts: null, system_prompt: null,
    user_prompt: null, formatted_prompt: null, model_id: null, user_api_key: null,
    is_public: false, public_token: null, model_version: null, tokenizer_version: null,
    vocab_hash: null, sampler_preset: null, sampler_algo: null, rng_seed: null,
    max_steps: null, active_mod: null, final_tokens: null, final_text: null,
    sequence_confidence: null, eos_reason: null, request_tags: {}, favorited_by: [],
    tags: [], step_logit_summaries: [], inference_stats: null, discussion_count: 0,
  });

  return useMemo(() => {
    const positions = new Set<number>();
    if (!log || timeline.length === 0) return positions;

    // Get final snapshot (100% position)
    const finalSnapshot = timeline[timeline.length - 1];
    if (!finalSnapshot) return positions;

    // Extract forced positions from the final items
    // These are in generation order (0-indexed from start of generation)
    let genPosition = 0;
    for (const item of finalSnapshot.items) {
      if (item.type === "token" && !item.erased) {
        if (item.forced) {
          // Add prompt offset to get position in full sequence
          positions.add(promptTokenOffset + genPosition);
        }
        genPosition++;
      }
    }

    return positions;
  }, [log, timeline, promptTokenOffset]);
}

/**
 * Get Neuronpedia URL for a feature.
 * LlamaScope 8x (32K) SAEs are on Neuronpedia with this format.
 */
function getNeuronpediaUrl(featureId: number, layer: number = 16): string {
  return `https://www.neuronpedia.org/llama3.1-8b/${layer}-llamascope-res-32k/${featureId}`;
}

/**
 * Format a feature ID for display.
 */
function formatFeatureId(id: number): string {
  return `#${id.toLocaleString()}`;
}

interface FeatureLinkProps {
  id: number;
  layer?: number;
  className?: string;
}

/**
 * Clickable feature ID that links to Neuronpedia for interpretation.
 */
function FeatureLink({ id, layer = 16, className }: FeatureLinkProps) {
  return (
    <a
      href={getNeuronpediaUrl(id, layer)}
      target="_blank"
      rel="noopener noreferrer"
      className={cn(
        "font-mono text-emerald-600 hover:text-emerald-400 hover:underline transition-colors",
        className
      )}
      title={`View feature ${id} on Neuronpedia`}
    >
      {formatFeatureId(id)}
    </a>
  );
}

/**
 * Format an activation value for display.
 */
function formatActivation(activation: number): string {
  if (activation >= 1) {
    return activation.toFixed(1);
  }
  return activation.toFixed(2);
}

/**
 * Get a color class based on activation strength.
 */
function getActivationColor(activation: number, maxActivation: number): string {
  const normalized = maxActivation > 0 ? activation / maxActivation : 0;
  if (normalized > 0.8) return "bg-emerald-500/80 text-white";
  if (normalized > 0.6) return "bg-emerald-500/60 text-white";
  if (normalized > 0.4) return "bg-emerald-500/40 text-emerald-900";
  if (normalized > 0.2) return "bg-emerald-500/20 text-emerald-700";
  return "bg-emerald-500/10 text-emerald-600";
}

interface TokenCellProps {
  entry: FeatureTimelineEntry;
  isInjection: boolean;
  isSelected: boolean;
  maxActivation: number;
  onClick: () => void;
}

function TokenCell({ entry, isInjection, isSelected, maxActivation, onClick }: TokenCellProps) {
  const topActivation = entry.top_features[0]?.activation ?? 0;
  const activationColor = getActivationColor(topActivation, maxActivation);

  return (
    <button
      onClick={onClick}
      className={cn(
        "relative group flex flex-col items-center justify-center min-w-[40px] h-[50px] rounded border transition-all",
        isSelected
          ? "border-emerald-500 ring-2 ring-emerald-500/30 bg-emerald-500/10"
          : isInjection
            ? "border-yellow-500/50 bg-yellow-500/5 hover:border-yellow-500"
            : "border-border hover:border-foreground/30 bg-card",
      )}
    >
      {/* Injection marker */}
      {isInjection && (
        <div className="absolute -top-1 -right-1 w-3 h-3 rounded-full bg-yellow-500 flex items-center justify-center">
          <Zap className="w-2 h-2 text-yellow-900" />
        </div>
      )}

      {/* Token text */}
      <span
        className={cn(
          "text-[10px] font-mono truncate max-w-[38px] px-0.5",
          isInjection ? "text-yellow-600" : "text-foreground",
        )}
        title={entry.token_str}
      >
        {entry.token_str.replace(/\n/g, "\\n").slice(0, 6)}
      </span>

      {/* Activation indicator */}
      {topActivation > 0 && (
        <div
          className={cn(
            "text-[8px] font-mono px-1 py-0.5 rounded mt-0.5",
            activationColor,
          )}
        >
          {formatActivation(topActivation)}
        </div>
      )}

      {/* Position indicator on hover */}
      <div className="absolute -bottom-5 left-1/2 -translate-x-1/2 text-[8px] text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity">
        {entry.position}
      </div>
    </button>
  );
}

interface FeatureDetailProps {
  entry: FeatureTimelineEntry;
  isInjection: boolean;
  onClose: () => void;
}

function FeatureDetail({ entry, isInjection, onClose }: FeatureDetailProps) {
  return (
    <div className="p-3 bg-card border border-border rounded-lg">
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <span className="text-xs font-mono text-muted-foreground">
            Position {entry.position}
          </span>
          {isInjection && (
            <span className="flex items-center gap-1 text-[10px] bg-yellow-500/20 text-yellow-600 px-1.5 py-0.5 rounded">
              <Zap className="w-2.5 h-2.5" />
              Injected
            </span>
          )}
        </div>
        <button
          onClick={onClose}
          className="text-xs text-muted-foreground hover:text-foreground"
        >
          Close
        </button>
      </div>

      <div className="flex items-center gap-2 mb-3">
        <code className="text-sm font-mono bg-muted px-2 py-1 rounded">
          {entry.token_str.replace(/\n/g, "\\n")}
        </code>
        <span className="text-xs text-muted-foreground">
          Token ID: {entry.token}
        </span>
      </div>

      <div className="space-y-1">
        <div className="text-[10px] font-mono uppercase tracking-wider text-muted-foreground mb-2">
          Top Features
        </div>
        {entry.top_features.length === 0 ? (
          <div className="text-xs text-muted-foreground italic">
            No significant feature activations
          </div>
        ) : (
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-1.5">
            {entry.top_features.slice(0, 12).map((feat, idx) => (
              <div
                key={idx}
                className="flex items-center justify-between text-xs bg-muted/50 px-2 py-1 rounded"
              >
                <FeatureLink id={feat.id} />
                <span className="font-mono text-muted-foreground">
                  {formatActivation(feat.activation)}
                </span>
              </div>
            ))}
          </div>
        )}
        {entry.top_features.length > 12 && (
          <div className="text-[10px] text-muted-foreground mt-1">
            +{entry.top_features.length - 12} more features
          </div>
        )}
      </div>
    </div>
  );
}

interface ComparisonViewProps {
  position: number;
  timeline: FeatureTimelineEntry[];
}

function ComparisonView({ position, timeline }: ComparisonViewProps) {
  const before = position > 0 ? timeline[position - 1] : null;
  const current = timeline[position];
  const after = position < timeline.length - 1 ? timeline[position + 1] : null;

  const getFeatureChanges = (
    prev: FeatureTimelineEntry | null,
    curr: FeatureTimelineEntry,
  ): { appeared: FeatureActivation[]; disappeared: number[]; changed: { id: number; before: number; after: number }[] } => {
    const prevFeatures = new Map(prev?.top_features.map((f) => [f.id, f.activation]) ?? []);
    const currFeatures = new Map(curr.top_features.map((f) => [f.id, f.activation]));

    const appeared: FeatureActivation[] = [];
    const disappeared: number[] = [];
    const changed: { id: number; before: number; after: number }[] = [];

    // Find appeared and changed features
    for (const [id, activation] of currFeatures) {
      if (!prevFeatures.has(id)) {
        appeared.push({ id, activation });
      } else {
        const prevAct = prevFeatures.get(id)!;
        if (Math.abs(activation - prevAct) > 0.1) {
          changed.push({ id, before: prevAct, after: activation });
        }
      }
    }

    // Find disappeared features
    for (const [id] of prevFeatures) {
      if (!currFeatures.has(id)) {
        disappeared.push(id);
      }
    }

    return { appeared, disappeared, changed };
  };

  const changes = before ? getFeatureChanges(before, current) : null;

  return (
    <div className="p-3 bg-muted/30 border border-border rounded-lg space-y-3">
      <div className="text-[10px] font-mono uppercase tracking-wider text-muted-foreground">
        Before/After Injection at Position {position}
      </div>

      <div className="grid grid-cols-3 gap-2 text-center">
        <div className="text-xs">
          <div className="text-muted-foreground mb-1">Before</div>
          <code className="bg-muted px-1.5 py-0.5 rounded text-[10px]">
            {before?.token_str.replace(/\n/g, "\\n") ?? "-"}
          </code>
        </div>
        <div className="text-xs">
          <div className="text-yellow-600 mb-1">Injection</div>
          <code className="bg-yellow-500/10 text-yellow-700 px-1.5 py-0.5 rounded text-[10px]">
            {current?.token_str.replace(/\n/g, "\\n")}
          </code>
        </div>
        <div className="text-xs">
          <div className="text-muted-foreground mb-1">After</div>
          <code className="bg-muted px-1.5 py-0.5 rounded text-[10px]">
            {after?.token_str.replace(/\n/g, "\\n") ?? "-"}
          </code>
        </div>
      </div>

      {changes && (
        <div className="space-y-2 text-xs">
          {changes.appeared.length > 0 && (
            <div>
              <span className="text-emerald-600 font-medium">New features:</span>{" "}
              {changes.appeared.slice(0, 5).map((f, i) => (
                <span key={i}>
                  <FeatureLink id={f.id} className="text-emerald-700" />
                  {i < Math.min(4, changes.appeared.length - 1) ? ", " : ""}
                </span>
              ))}
              {changes.appeared.length > 5 && (
                <span className="text-muted-foreground"> +{changes.appeared.length - 5} more</span>
              )}
            </div>
          )}
          {changes.disappeared.length > 0 && (
            <div>
              <span className="text-red-500 font-medium">Disappeared:</span>{" "}
              {changes.disappeared.slice(0, 5).map((id, i) => (
                <span key={i}>
                  <FeatureLink id={id} className="text-red-600 hover:text-red-400" />
                  {i < Math.min(4, changes.disappeared.length - 1) ? ", " : ""}
                </span>
              ))}
              {changes.disappeared.length > 5 && (
                <span className="text-muted-foreground"> +{changes.disappeared.length - 5} more</span>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export function FeatureTimeline({ timeline, log, promptTokenCount = 0, className, onInjectionPositions }: FeatureTimelineProps) {
  const [selectedPosition, setSelectedPosition] = useState<number | null>(null);
  const [expanded, setExpanded] = useState(true);
  const [showComparisons, setShowComparisons] = useState(false);

  // Use the same token timeline logic as TokenSequence to determine forced positions
  // This guarantees consistency with the Token Sequence view
  const injectionPositions = useInjectionPositions(log, promptTokenCount);

  // Notify parent of injection positions when they change
  useEffect(() => {
    if (onInjectionPositions) {
      onInjectionPositions(Array.from(injectionPositions));
    }
  }, [injectionPositions, onInjectionPositions]);

  // Calculate max activation for color scaling
  const maxActivation = useMemo(() => {
    let max = 0;
    for (const entry of timeline) {
      if (entry.top_features.length > 0) {
        max = Math.max(max, entry.top_features[0].activation);
      }
    }
    return max;
  }, [timeline]);

  const selectedEntry = selectedPosition !== null ? timeline[selectedPosition] : null;

  if (timeline.length === 0) {
    return (
      <div className={cn("p-4 text-center text-sm text-muted-foreground", className)}>
        No feature timeline data available
      </div>
    );
  }

  return (
    <div className={cn("space-y-3", className)}>
      {/* Header */}
      <div className="flex items-center justify-between">
        <button
          onClick={() => setExpanded(!expanded)}
          className="flex items-center gap-2 text-sm font-medium hover:text-foreground transition-colors"
        >
          {expanded ? (
            <ChevronDown className="w-4 h-4" />
          ) : (
            <ChevronRight className="w-4 h-4" />
          )}
          <Sparkles className="w-4 h-4 text-emerald-500" />
          <span>SAE Feature Timeline</span>
          <span className="text-xs text-muted-foreground font-normal">
            ({timeline.length} positions)
          </span>
        </button>

        <div className="flex items-center gap-2 text-xs">
          {injectionPositions.size > 0 && (
            <button
              onClick={() => setShowComparisons(!showComparisons)}
              className={cn(
                "flex items-center gap-1 px-2 py-1 rounded transition-colors",
                showComparisons
                  ? "bg-yellow-500/20 text-yellow-600"
                  : "bg-muted text-muted-foreground hover:text-foreground",
              )}
            >
              <Zap className="w-3 h-3" />
              {injectionPositions.size} injection{injectionPositions.size !== 1 ? "s" : ""}
            </button>
          )}
          <div className="flex items-center gap-1 text-muted-foreground">
            <Info className="w-3 h-3" />
            Click token for details
          </div>
        </div>
      </div>

      {expanded && (
        <>
          {/* Timeline visualization */}
          <div className="overflow-x-auto pb-6">
            <div className="flex gap-1 min-w-max">
              {timeline.map((entry, idx) => (
                <TokenCell
                  key={idx}
                  entry={entry}
                  isInjection={injectionPositions.has(entry.position)}
                  isSelected={selectedPosition === idx}
                  maxActivation={maxActivation}
                  onClick={() =>
                    setSelectedPosition(selectedPosition === idx ? null : idx)
                  }
                />
              ))}
            </div>
          </div>

          {/* Selected position details */}
          {selectedEntry && (
            <FeatureDetail
              entry={selectedEntry}
              isInjection={injectionPositions.has(selectedEntry.position)}
              onClose={() => setSelectedPosition(null)}
            />
          )}

          {/* Injection comparisons */}
          {showComparisons && injectionPositions.size > 0 && (
            <div className="space-y-2">
              {Array.from(injectionPositions)
                .filter((pos) => pos < timeline.length)
                .slice(0, 5) // Limit to first 5 injections
                .map((pos) => (
                  <ComparisonView key={pos} position={pos} timeline={timeline} />
                ))}
              {injectionPositions.size > 5 && (
                <div className="text-xs text-muted-foreground text-center">
                  +{injectionPositions.size - 5} more injection points
                </div>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}
