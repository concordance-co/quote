import { memo } from "react";
import type { ActionLog, EventLog } from "@/types/api";

interface ActionSummaryProps {
  action: ActionLog;
  /** Associated event - used to filter out duplicate first token from ForceTokens display */
  associatedEvent?: EventLog;
}

// Action summary - inline description
export const ActionSummary = memo(function ActionSummary({
  action,
  associatedEvent,
}: ActionSummaryProps) {
  const payload = action.payload || {};

  switch (action.action_type) {
    case "ForceTokens":
    case "ForceOutput": {
      const tokensRaw = payload.tokens || payload.tokens_preview;
      const tokens: number[] = Array.isArray(tokensRaw) ? tokensRaw : [];
      const tokensAsTextRaw = payload.tokens_as_text;
      const tokensAsText: string[] = Array.isArray(tokensAsTextRaw)
        ? tokensAsTextRaw.map(String)
        : typeof tokensAsTextRaw === "string"
          ? [tokensAsTextRaw]
          : [];

      // Check if first token was already added naturally (not forced) by the associated event
      // If so, skip it from the ForceTokens display
      let startIdx = 0;
      if (
        associatedEvent &&
        associatedEvent.event_type === "Added" &&
        !associatedEvent.forced &&
        associatedEvent.added_tokens &&
        associatedEvent.added_tokens.length > 0 &&
        tokens.length > 0 &&
        tokens[0] === associatedEvent.added_tokens[0]
      ) {
        startIdx = 1;
      }

      const displayTokens = tokens.slice(startIdx);
      const displayTokensAsText = tokensAsText.slice(startIdx);
      const count = displayTokens.length;
      const text = displayTokensAsText.join("");

      // If all tokens were filtered out, don't show anything
      if (count === 0) {
        return (
          <span className="text-muted-foreground/50">
            (token already added naturally)
          </span>
        );
      }

      return (
        <span className="flex items-center gap-2">
          {text && (
            <span className="font-mono text-pink-300 bg-pink-500/10 px-1.5 py-0.5 rounded">
              "{String(text).slice(0, 40)}"
            </span>
          )}
          <span className="text-muted-foreground">
            {count} token{count !== 1 ? "s" : ""}
          </span>
        </span>
      );
    }

    case "Backtrack": {
      const n =
        (payload.backtrack_steps as number) || (payload.n as number) || 0;
      return (
        <span className="flex items-center gap-2">
          <span className="text-orange-300">Backtrack</span>
          <span className="font-mono text-orange-300 bg-orange-500/10 px-1.5 py-0.5 rounded">
            {n} step{n !== 1 ? "s" : ""}
          </span>
        </span>
      );
    }

    case "AdjustedLogits": {
      const shape = payload.logits_shape as number[] | string | undefined;
      return (
        <span className="flex items-center gap-2">
          <span className="text-muted-foreground">Logits shape:</span>
          <span className="font-mono text-cyan-300">
            [{Array.isArray(shape) ? shape.join(", ") : String(shape || "")}]
          </span>
        </span>
      );
    }

    case "AdjustedPrefill": {
      const maxSteps = payload.adjusted_max_steps as number | undefined;
      const count = (payload.token_count as number) || 0;
      return (
        <span className="flex items-center gap-2">
          <span className="font-mono text-teal-300">{count} tokens</span>
          {maxSteps && (
            <>
              <span className="text-muted-foreground/50">•</span>
              <span className="text-muted-foreground">
                max_steps: {maxSteps}
              </span>
            </>
          )}
        </span>
      );
    }

    case "ToolCalls":
      return <span className="text-muted-foreground">Tool calls executed</span>;

    case "EmitError": {
      const errorMsg = payload.error_message as string | undefined;
      return (
        <span className="flex items-center gap-2">
          <span className="text-red-400">
            {errorMsg ? String(errorMsg).slice(0, 50) : "Error occurred"}
          </span>
        </span>
      );
    }

    case "Noop":
      return <span className="text-muted-foreground/50">No operation</span>;

    default:
      return null;
  }
});
