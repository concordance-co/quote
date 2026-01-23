import { memo } from "react";
import { cn } from "@/lib/utils";
import { calculateFlatness } from "./utils";
import type { EventLog } from "@/types/api";

interface EventDetailsProps {
  event: EventLog;
}

// Event details panel - shown on expand
export const EventDetails = memo(function EventDetails({
  event,
}: EventDetailsProps) {
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 gap-x-6 gap-y-2">
        <span className="text-muted-foreground">ID:</span>
        <span className="font-mono text-xs">{event.id}</span>
        <span className="text-muted-foreground">Step:</span>
        <span className="font-mono">{event.step}</span>
        <span className="text-muted-foreground">Sequence Order:</span>
        <span className="font-mono">{event.sequence_order}</span>
        <span className="text-muted-foreground">Created:</span>
        <span>{new Date(event.created_at).toLocaleTimeString()}</span>
      </div>

      {event.event_type === "Prefilled" && (
        <div className="grid grid-cols-2 gap-x-6 gap-y-2 pt-3 border-t border-border/30">
          <span className="text-muted-foreground">Prompt Length:</span>
          <span className="font-mono">{event.prompt_length}</span>
          <span className="text-muted-foreground">Max Steps:</span>
          <span className="font-mono">{event.max_steps ?? "—"}</span>
        </div>
      )}

      {event.event_type === "ForwardPass" && (
        <div className="pt-3 border-t border-border/30 space-y-3">
          <div>
            <span className="text-muted-foreground block mb-2">
              Input Text:
            </span>
            <div className="bg-black/40 rounded-md p-2.5 max-h-28 overflow-auto border border-border/30">
              <pre className="whitespace-pre-wrap break-all text-xs font-mono">
                {event.input_text}
              </pre>
            </div>
          </div>
          {event.top_tokens && Array.isArray(event.top_tokens) && (
            <div>
              <div className="flex items-center justify-between mb-2">
                <span className="text-muted-foreground">Top Tokens:</span>
                {event.top_tokens.length >= 2 &&
                  (() => {
                    const flatness = calculateFlatness(event.top_tokens);
                    if (flatness === null) return null;
                    return (
                      <div className="flex items-center gap-2 text-xs">
                        <span className="text-muted-foreground">Flatness:</span>
                        <div className="flex items-center gap-1.5">
                          <div className="w-16 h-1.5 bg-muted rounded-full overflow-hidden">
                            <div
                              className={cn(
                                "h-full rounded-full",
                                flatness > 0.7
                                  ? "bg-amber-500"
                                  : flatness > 0.4
                                    ? "bg-blue-500"
                                    : "bg-emerald-500"
                              )}
                              style={{ width: `${flatness * 100}%` }}
                            />
                          </div>
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
                        </div>
                      </div>
                    );
                  })()}
              </div>
              <div className="bg-black/40 rounded-md p-2.5 border border-border/30">
                <div className="space-y-1">
                  {event.top_tokens.slice(0, 10).map((tok, i) => (
                    <div key={i} className="flex items-center gap-3 text-xs">
                      <span className="text-muted-foreground/60 w-4">{i}.</span>
                      <span className="text-foreground/90 w-28 truncate font-mono">
                        {tok.token_str
                          ? `"${tok.token_str}"`
                          : `[${tok.token}]`}
                      </span>
                      <div className="flex-1 h-1.5 bg-muted rounded-full overflow-hidden">
                        <div
                          className="h-full bg-emerald-500 rounded-full"
                          style={{
                            width: `${Math.min(Math.exp(tok.logprob) * 100, 100)}%`,
                          }}
                        />
                      </div>
                      <span className="text-emerald-400 w-16 text-right">
                        {(Math.exp(tok.logprob) * 100).toFixed(1)}%
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {event.event_type === "Sampled" && (
        <div className="grid grid-cols-2 gap-x-6 gap-y-2 pt-3 border-t border-border/30">
          <span className="text-muted-foreground">Token ID:</span>
          <span className="font-mono">{event.sampled_token}</span>
          <span className="text-muted-foreground">Token Text:</span>
          <span className="font-mono bg-purple-500/10 px-2 py-0.5 rounded inline-block">
            "{event.token_text}"
          </span>
        </div>
      )}

      {event.event_type === "Added" && (
        <div className="pt-3 border-t border-border/30 space-y-2">
          <div className="grid grid-cols-2 gap-x-6 gap-y-2">
            <span className="text-muted-foreground">Token Count:</span>
            <span className="font-mono">{event.added_token_count}</span>
            <span className="text-muted-foreground">Forced:</span>
            <span
              className={cn(
                "font-medium",
                event.forced ? "text-pink-400" : "text-emerald-400"
              )}
            >
              {event.forced ? "Yes" : "No"}
            </span>
          </div>
          {event.added_tokens && (
            <div>
              <span className="text-muted-foreground block mb-2">
                Token IDs:
              </span>
              <div className="bg-black/40 rounded-md p-2.5 border border-border/30">
                <code className="text-xs font-mono">
                  [{event.added_tokens.join(", ")}]
                </code>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
});
