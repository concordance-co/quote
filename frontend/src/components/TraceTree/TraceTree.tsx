import {
  useState,
  useMemo,
  useEffect,
  useRef,
  useCallback,
  useLayoutEffect,
} from "react";
import { useVirtualizer } from "@tanstack/react-virtual";
import { Activity, FileText, Circle } from "lucide-react";
import { TraceEntryRow } from "./TraceEntryRow";
import type { TraceTreeProps, TraceEntry } from "./types";

export default function TraceTree({
  log,
  selectedStep,
  onSelectStep: _onSelectStep,
  requestId,
  onCommentAdded,
}: TraceTreeProps) {
  // Use lazy initializers to avoid creating new Sets on every render
  const [expandedNodes, setExpandedNodes] = useState<Set<string>>(
    () => new Set(),
  );
  const [expandedDetails, setExpandedDetails] = useState<Set<string>>(
    () => new Set(),
  );
  const [commentingOnEntry, setCommentingOnEntry] = useState<string | null>(
    null,
  );

  // Ref for the scroll container
  const scrollContainerRef = useRef<HTMLDivElement>(null);

  // Track the header height for scrollMargin
  const headerRef = useRef<HTMLDivElement>(null);
  const [headerHeight, setHeaderHeight] = useState(0);

  // Measure header height
  useLayoutEffect(() => {
    if (headerRef.current) {
      setHeaderHeight(headerRef.current.offsetHeight);
    }
  }, []);

  // Build linear trace entries from events
  const traceEntries = useMemo(() => {
    const events = log.events || [];
    const modCalls = log.mod_calls || [];
    const modLogs = log.mod_logs || [];
    const actions = log.actions || [];

    // Sort events by sequence_order
    const sortedEvents = [...events].sort(
      (a, b) => a.sequence_order - b.sequence_order,
    );

    const entries: TraceEntry[] = sortedEvents.map((event, idx) => {
      // Find mod calls for this event
      const eventModCalls = modCalls
        .filter((mc) => mc.event_id === event.id)
        .map((mc) => ({
          modCall: mc,
          logs: modLogs.filter((ml) => ml.mod_call_id === mc.id),
        }));

      // Find actions - match by mod_call_id or step
      const eventActions = actions.filter(
        (a) =>
          eventModCalls.some((mc) => mc.modCall.id === a.mod_id) ||
          (a.step_index === event.step &&
            event.event_type === "ForwardPass" &&
            !eventModCalls.some((mc) => mc.modCall.id === a.mod_id)),
      );

      // Determine step group position
      const prevStep = idx > 0 ? sortedEvents[idx - 1].step : null;
      const nextStep =
        idx < sortedEvents.length - 1 ? sortedEvents[idx + 1].step : null;
      const isFirstInStep = prevStep !== event.step;
      const isLastInStep = nextStep !== event.step;

      return {
        id: `entry-${event.id}`,
        event,
        modCalls: eventModCalls,
        actions: eventActions,
        isLast: idx === sortedEvents.length - 1,
        isFirstInStep,
        isLastInStep,
      };
    });

    return entries;
  }, [log.events, log.mod_calls, log.mod_logs, log.actions]);

  // Build a map from step number to entry index for scrollToIndex
  const stepToIndexMap = useMemo(() => {
    const map = new Map<number, number>();
    traceEntries.forEach((entry, idx) => {
      if (!map.has(entry.event.step)) {
        map.set(entry.event.step, idx);
      }
    });
    return map;
  }, [traceEntries]);

  // Auto-expand entries that have actions
  useEffect(() => {
    const idsToExpand = new Set<string>();
    traceEntries.forEach((entry) => {
      if (entry.actions.length > 0 || entry.modCalls.length > 0) {
        idsToExpand.add(entry.id);
      }
    });
    if (idsToExpand.size > 0) {
      setExpandedNodes(idsToExpand);
    }
  }, [traceEntries]);

  // Set up virtualizer
  const virtualizer = useVirtualizer({
    count: traceEntries.length,
    getScrollElement: () => scrollContainerRef.current,
    estimateSize: useCallback(
      (index: number) => {
        const entry = traceEntries[index];
        if (!entry) return 60;

        const isExpanded = expandedNodes.has(entry.id);
        const showDetails = expandedDetails.has(entry.id);
        const isCommenting = commentingOnEntry === entry.id;

        // Base height
        let height = 60;

        // Add height for expanded children
        if (isExpanded) {
          height += entry.modCalls.length * 44;
          height += entry.actions.length * 40;
        }

        // Add height for details panel
        if (showDetails) {
          height += 150;
        }

        // Add height for comment form
        if (isCommenting) {
          height += 160;
        }

        return height;
      },
      [expandedNodes, expandedDetails, commentingOnEntry, traceEntries],
    ),
    overscan: 5,
    getItemKey: useCallback(
      (index: number) => traceEntries[index]?.id ?? index,
      [traceEntries],
    ),
    // scrollMargin accounts for content before the virtualized list
    scrollMargin: headerHeight,
  });

  // Scroll to step function
  const scrollToStep = useCallback(
    (step: number) => {
      const index = stepToIndexMap.get(step);
      if (index !== undefined) {
        virtualizer.scrollToIndex(index, {
          align: "center",
          behavior: "auto",
        });
      }
    },
    [stepToIndexMap, virtualizer],
  );

  // Handle scroll when selectedStep changes
  useEffect(() => {
    if (selectedStep === null) return;

    // Small delay to ensure virtualizer is ready
    const timeoutId = setTimeout(() => {
      scrollToStep(selectedStep);
    }, 100);

    return () => clearTimeout(timeoutId);
  }, [selectedStep, scrollToStep]);

  const toggleNode = useCallback((nodeId: string) => {
    setExpandedNodes((prev) => {
      const next = new Set(prev);
      if (next.has(nodeId)) {
        next.delete(nodeId);
      } else {
        next.add(nodeId);
      }
      return next;
    });
  }, []);

  const toggleDetails = useCallback((nodeId: string) => {
    setExpandedDetails((prev) => {
      const next = new Set(prev);
      if (next.has(nodeId)) {
        next.delete(nodeId);
      } else {
        next.add(nodeId);
      }
      return next;
    });
  }, []);

  const expandAll = useCallback(() => {
    const allIds = new Set<string>();
    traceEntries.forEach((entry) => {
      allIds.add(entry.id);
      entry.modCalls.forEach((mc) => allIds.add(`modcall-${mc.modCall.id}`));
    });
    setExpandedNodes(allIds);
  }, [traceEntries]);

  const collapseAll = useCallback(() => {
    setExpandedNodes(new Set());
    setExpandedDetails(new Set());
  }, []);

  const handleStartComment = useCallback((entryId: string) => {
    setCommentingOnEntry(entryId);
  }, []);

  const handleCancelComment = useCallback(() => {
    setCommentingOnEntry(null);
  }, []);

  const handleCommentAdded = useCallback(() => {
    setCommentingOnEntry(null);
    onCommentAdded?.();
  }, [onCommentAdded]);

  // Empty state
  if (!log.events || log.events.length === 0) {
    return (
      <div className="panel">
        <div className="flex flex-col items-center justify-center py-12 text-center">
          <div className="w-12 h-12 rounded-full bg-muted/50 flex items-center justify-center mb-3">
            <FileText className="h-6 w-6 text-muted-foreground" />
          </div>
          <p className="text-sm font-medium mb-1">No trace data</p>
          <p className="text-xs text-muted-foreground">
            No events recorded for this request
          </p>
        </div>
      </div>
    );
  }

  // Summary stats
  const stats = useMemo(() => {
    const addedEvents = traceEntries.filter(
      (e) => e.event.event_type === "Added",
    );
    const forcedCount = addedEvents.filter((e) => e.event.forced).length;
    const sampledCount = addedEvents.filter((e) => !e.event.forced).length;
    const totalActions = traceEntries.reduce(
      (acc, e) => acc + e.actions.length,
      0,
    );
    return { forcedCount, sampledCount, totalActions };
  }, [traceEntries]);

  const virtualItems = virtualizer.getVirtualItems();

  return (
    <div className="panel overflow-hidden h-full flex flex-col">
      {/* Header */}
      <div className="panel-header flex items-center justify-between border-b border-border/50">
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <Activity className="h-4 w-4 text-primary" />
            <span className="panel-title">Execution Trace</span>
          </div>
          <div className="flex items-center gap-2 text-2xs">
            <span className="px-2 py-0.5 rounded-full bg-muted text-muted-foreground">
              {log.events?.length || 0} events
            </span>
            {stats.totalActions > 0 && (
              <span className="px-2 py-0.5 rounded-full bg-cyan-900/40 text-cyan-300">
                {stats.totalActions} actions
              </span>
            )}
          </div>
        </div>
        <div className="flex items-center gap-1">
          <button
            onClick={expandAll}
            className="text-2xs text-muted-foreground hover:text-foreground px-2.5 py-1.5 rounded-md hover:bg-muted/80 transition-colors"
          >
            Expand All
          </button>
          <button
            onClick={collapseAll}
            className="text-2xs text-muted-foreground hover:text-foreground px-2.5 py-1.5 rounded-md hover:bg-muted/80 transition-colors"
          >
            Collapse All
          </button>
        </div>
      </div>

      {/* Virtualized scroll container */}
      {/* Scroll container - this is what the virtualizer scrolls */}
      <div ref={scrollContainerRef} className="flex-1 min-h-0 overflow-auto">
        {/* Header/Start marker - measured for scrollMargin */}
        <div ref={headerRef} className="p-2 pb-0">
          <div className="flex items-center gap-2 mb-2 pb-2 border-b border-border/30">
            <div className="w-6 h-6 rounded bg-emerald-500/20 border border-emerald-500/30 flex items-center justify-center">
              <Circle className="h-2.5 w-2.5 text-emerald-400 fill-emerald-400" />
            </div>
            <div>
              <div className="font-medium text-emerald-400 text-xs">
                Generation Started
              </div>
              <div className="text-2xs text-muted-foreground">
                {log.model_id || "Unknown"} • {log.events?.length} events
              </div>
            </div>
          </div>
        </div>

        {/* Virtualized list container - directly in scroll container */}
        <div className="px-2">
          <div
            style={{
              height: `${virtualizer.getTotalSize()}px`,
              width: "100%",
              position: "relative",
            }}
          >
            {virtualItems.map((virtualRow) => {
              const entry = traceEntries[virtualRow.index];
              return (
                <div
                  key={virtualRow.key}
                  data-index={virtualRow.index}
                  ref={virtualizer.measureElement}
                  style={{
                    position: "absolute",
                    top: 0,
                    left: 0,
                    width: "100%",
                    transform: `translateY(${virtualRow.start - headerHeight}px)`,
                  }}
                >
                  <TraceEntryRow
                    entry={entry}
                    expanded={expandedNodes.has(entry.id)}
                    expandedNodes={expandedNodes}
                    expandedDetails={expandedDetails}
                    onToggle={toggleNode}
                    onToggleDetails={toggleDetails}
                    selectedStep={selectedStep}
                    registerStepRef={() => {}}
                    requestId={requestId}
                    isCommenting={commentingOnEntry === entry.id}
                    onStartComment={() => handleStartComment(entry.id)}
                    onCancelComment={handleCancelComment}
                    onCommentAdded={handleCommentAdded}
                  />
                </div>
              );
            })}
          </div>

          {/* End marker */}
          {log.finished_ts && (
            <div className="flex items-center gap-2 mt-2 pt-2 border-t border-border/30">
              <div className="w-6 h-6 rounded bg-blue-500/20 border border-blue-500/30 flex items-center justify-center">
                <Circle className="h-2.5 w-2.5 text-blue-400 fill-blue-400" />
              </div>
              <div>
                <div className="font-medium text-blue-400 text-xs">
                  Complete
                </div>
                <div className="text-2xs text-muted-foreground">
                  {stats.forcedCount} forced • {stats.sampledCount} sampled •{" "}
                  {stats.totalActions} actions
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
