import { memo } from "react";
import { cn } from "@/lib/utils";
import { calculateFlatness } from "./utils";
import type { EventLog } from "@/types/api";

interface EventSummaryProps {
  event: EventLog;
}

// Event summary - inline description
export const EventSummary = memo(function EventSummary({
  event,
}: EventSummaryProps) {
  switch (event.event_type) {
    case "Prefilled":
      return (
        <span className="flex items-center gap-1.5 flex-wrap">
          <span className="text-muted-foreground">Len:</span>
          <span className="font-mono text-blue-300">{event.prompt_length}</span>
          {event.max_steps && (
            <>
              <span className="text-muted-foreground/50">•</span>
              <span className="text-muted-foreground">Max:</span>
              <span className="font-mono text-blue-300">{event.max_steps}</span>
            </>
          )}
        </span>
      );

    case "ForwardPass": {
      const inputPreview = event.input_text
        ? event.input_text.length > 60
          ? event.input_text.slice(-60)
          : event.input_text
        : "";

      // Format top tokens
      const topTokens = Array.isArray(event.top_tokens)
        ? event.top_tokens.slice(0, 3)
        : [];
      const topTokensStr = topTokens
        .map((t) => {
          const prob = Math.exp(t.logprob);
          const tokenStr = t.token_str ? `"${t.token_str}"` : `[${t.token}]`;
          return `${tokenStr}: ${(prob * 100).toFixed(0)}%`;
        })
        .join(", ");

      // Calculate flatness from all available top tokens
      const allTopTokens = Array.isArray(event.top_tokens)
        ? event.top_tokens
        : [];
      const flatness = calculateFlatness(allTopTokens);

      return (
        <div className="space-y-0.5">
          <div className="flex items-center gap-1.5">
            <span className="font-mono text-emerald-300/80 truncate max-w-md text-2xs">
              "{inputPreview.replace(/\n/g, "↵")}"
            </span>
          </div>
          <div className="flex items-center gap-1.5 text-2xs flex-wrap">
            {topTokensStr && (
              <>
                <span className="text-muted-foreground">Top:</span>
                <span className="text-muted-foreground/80">{topTokensStr}</span>
              </>
            )}
            {flatness !== null && (
              <>
                <span className="text-muted-foreground/50">•</span>
                <span className="text-muted-foreground">Flatness:</span>
                <span
                  className={cn(
                    "font-mono",
                    flatness > 0.7
                      ? "text-amber-400"
                      : flatness > 0.4
                        ? "text-blue-400"
                        : "text-emerald-400"
                  )}
                >
                  {(flatness * 100).toFixed(0)}%
                </span>
              </>
            )}
          </div>
        </div>
      );
    }

    case "Sampled":
      return (
        <span className="flex items-center gap-1.5">
          <span className="font-mono text-purple-300 bg-purple-500/10 px-1 rounded">
            "{event.token_text}"
          </span>
          <span className="text-muted-foreground/50 text-2xs font-mono">
            ({event.sampled_token})
          </span>
        </span>
      );

    case "Added":
      return (
        <span className="flex items-center gap-1.5 flex-wrap">
          <span className="font-mono text-pink-300">
            {event.added_token_count}
          </span>
          <span className="text-muted-foreground">
            token{event.added_token_count !== 1 ? "s" : ""}
          </span>
          {event.token_text && (
            <span className="font-mono text-pink-300/80 bg-pink-500/10 px-1 rounded text-2xs">
              "{event.token_text}"
            </span>
          )}
        </span>
      );

    default:
      return <span className="text-muted-foreground">Step {event.step}</span>;
  }
});
