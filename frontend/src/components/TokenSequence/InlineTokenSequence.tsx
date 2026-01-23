import { useState, useEffect, useMemo, useCallback } from "react";
import {
  Loader2,
  AlertTriangle,
  ChevronDown,
  ChevronRight,
} from "lucide-react";
import { Link, useNavigate } from "react-router-dom";
import { fetchLogDetail, getRequestViaCollection } from "@/lib/api";
import type { LogResponse } from "@/types/api";
import { TokenSequence } from "./TokenSequence";
import { useTokenTimeline } from "./useTokenTimeline";
import type { SequenceItem, TokenColorMode } from "./types";

interface InlineTokenSequenceProps {
  /** Request ID to fetch log data for */
  requestId: string;
  /** Whether the sequence is expanded */
  expanded: boolean;
  /** Callback to toggle expanded state */
  onToggle: () => void;
  /** Optional max height for the token display */
  maxHeight?: string;
  /** Whether to show the toggle button (default: true) */
  showToggle?: boolean;
  /** Color mode for token coloring */
  colorMode?: TokenColorMode;
  /** Public collection token for accessing request via public collection */
  publicCollectionToken?: string;
}

/**
 * InlineTokenSequence is a wrapper that fetches log data on demand
 * and displays a compact token sequence inline.
 */
export function InlineTokenSequence({
  requestId,
  expanded,
  onToggle,
  maxHeight = "200px",
  showToggle = true,
  colorMode = "flatness",
  publicCollectionToken,
}: InlineTokenSequenceProps) {
  const [log, setLog] = useState<LogResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Fetch log data when expanded
  useEffect(() => {
    if (!expanded || log) return;

    async function fetchLog() {
      try {
        setLoading(true);
        setError(null);
        // Use public API when in public collection context
        const data = publicCollectionToken
          ? await getRequestViaCollection(publicCollectionToken, requestId)
          : await fetchLogDetail(requestId);
        setLog(data);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load");
      } finally {
        setLoading(false);
      }
    }

    fetchLog();
  }, [expanded, requestId, log, publicCollectionToken]);

  return (
    <div className="w-full">
      {/* Expand toggle button */}
      {showToggle && (
        <button
          onClick={onToggle}
          className="flex items-center gap-1 text-2xs text-muted-foreground hover:text-foreground transition-colors py-1"
        >
          {expanded ? (
            <ChevronDown className="h-3 w-3" />
          ) : (
            <ChevronRight className="h-3 w-3" />
          )}
          <span>{expanded ? "Hide" : "Show"} tokens</span>
        </button>
      )}

      {/* Expanded content */}
      {expanded && (
        <div className="mt-2 border border-border/50 rounded-md bg-background/50 p-2">
          {loading && (
            <div className="flex items-center justify-center py-4">
              <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
              <span className="ml-2 text-xs text-muted-foreground">
                Loading tokens...
              </span>
            </div>
          )}

          {error && (
            <div className="flex items-center justify-center py-4">
              <AlertTriangle className="h-4 w-4 text-destructive" />
              <span className="ml-2 text-xs text-destructive">{error}</span>
            </div>
          )}

          {log && !loading && (
            <InlineTokenDisplay
              log={log}
              maxHeight={maxHeight}
              requestId={requestId}
              colorMode={colorMode}
              publicCollectionToken={publicCollectionToken}
            />
          )}
        </div>
      )}
    </div>
  );
}

/**
 * Internal component that displays the tokens once log data is loaded
 */
function InlineTokenDisplay({
  log,
  maxHeight,
  requestId,
  colorMode,
  publicCollectionToken,
}: {
  log: LogResponse;
  maxHeight: string;
  requestId: string;
  colorMode: TokenColorMode;
  publicCollectionToken?: string;
}) {
  const navigate = useNavigate();
  const { timeline } = useTokenTimeline(log);

  // Get final items (at 100% scrubber position)
  const items = useMemo(() => {
    if (timeline.length === 0) return [];
    return timeline[timeline.length - 1].items;
  }, [timeline]);

  // Compute stats
  const stats = useMemo(() => {
    const tokens = items.filter((i) => i.type === "token") as Extract<
      SequenceItem,
      { type: "token" }
    >[];
    const forced = tokens.filter((t) => t.forced && !t.erased).length;
    const sampled = tokens.filter((t) => !t.forced && !t.erased).length;
    return { forced, sampled, total: tokens.length };
  }, [items]);

  // Construct the appropriate link based on context
  const detailLink = publicCollectionToken
    ? `/share/${publicCollectionToken}/request/${requestId}`
    : `/logs/${requestId}`;

  // Navigate to trace view with the selected step
  const handleNavigateToStep = useCallback(
    (step: number) => {
      navigate(`${detailLink}?step=${step}`);
    },
    [navigate, detailLink],
  );

  if (items.length === 0) {
    return (
      <div className="text-xs text-muted-foreground text-center py-2">
        No tokens to display
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {/* Stats header with link to full view */}
      <div className="flex items-center justify-between text-2xs">
        <span className="text-muted-foreground">
          {stats.total} tokens ({stats.forced} forced, {stats.sampled} sampled)
        </span>
        <Link
          to={`${detailLink}?tab=tokens`}
          className="text-primary hover:underline"
        >
          View full →
        </Link>
      </div>

      {/* Token sequence in compact mode */}
      <TokenSequence
        items={items}
        compact={true}
        maxHeight={maxHeight}
        initialShowBacktrack={false}
        onNavigateToStep={handleNavigateToStep}
        colorMode={colorMode}
      />
    </div>
  );
}
