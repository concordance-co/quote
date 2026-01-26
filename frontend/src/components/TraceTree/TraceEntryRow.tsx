import { memo, useCallback } from "react";
import { ChevronRight, ChevronDown, MessageSquarePlus } from "lucide-react";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import { EventBadge } from "./badges";
import { EventSummary } from "./EventSummary";
import { EventDetails } from "./EventDetails";
import { InlineCommentForm } from "./InlineCommentForm";
import { ModCallCard } from "./ModCallCard";
import { ActionCard } from "./ActionCard";
import { getStepColor, getStepColorContainer } from "./utils";
import type { TraceEntryRowProps } from "./types";

// Memoized TraceEntryRow component for better performance on large traces
export const TraceEntryRow = memo(
  function TraceEntryRow({
    entry,
    expanded,
    expandedNodes,
    expandedDetails,
    onToggle,
    onToggleDetails,
    selectedStep,
    registerStepRef,
    requestId,
    isCommenting,
    onStartComment,
    onCancelComment,
    onCommentAdded,
  }: TraceEntryRowProps) {
    const { event, modCalls, actions } = entry;
    const hasChildren = modCalls.length > 0 || actions.length > 0;
    const isSelected = selectedStep === event.step;
    const showDetails = expandedDetails.has(entry.id);

    // Memoized callbacks for child components
    const handleToggle = useCallback(
      (e: React.MouseEvent) => {
        e.stopPropagation();
        onToggle(entry.id);
      },
      [onToggle, entry.id],
    );

    const handleToggleDetails = useCallback(() => {
      onToggleDetails(entry.id);
    }, [onToggleDetails, entry.id]);

    const handleStartComment = useCallback(
      (e: React.MouseEvent) => {
        e.stopPropagation();
        onStartComment();
      },
      [onStartComment],
    );

    // Create callbacks for mod call toggles
    const createModCallToggle = useCallback(
      (modCallId: number) => () => {
        onToggle(`modcall-${modCallId}`);
      },
      [onToggle],
    );

    const createModCallDetailsToggle = useCallback(
      (modCallId: number) => () => {
        onToggleDetails(`modcall-${modCallId}`);
      },
      [onToggleDetails],
    );

    // Create callbacks for action toggles
    const createActionDetailsToggle = useCallback(
      (actionId: number) => () => {
        onToggleDetails(`action-${actionId}`);
      },
      [onToggleDetails],
    );

    return (
      <div
        className="relative"
        ref={(el) => {
          if (entry.isFirstInStep) {
            registerStepRef(event.step, el);
          }
        }}
      >
        {/* Step group indicator */}
        <div className="flex">
          {/* Colored step bar */}
          <div
            className={cn(
              "w-1 shrink-0 transition-colors",
              getStepColor(event.step),
              entry.isFirstInStep && "rounded-t",
              entry.isLastInStep && "rounded-b",
              isSelected &&
                "ring-1 ring-primary ring-offset-1 ring-offset-background",
            )}
          />

          {/* Main event card */}
          <div
            className={cn(
              "flex-1 relative border-y border-r transition-all duration-150 cursor-pointer group",
              entry.isFirstInStep && "rounded-tr border-t",
              entry.isLastInStep && "rounded-br border-b",
              !entry.isFirstInStep && "border-t-0",
              isSelected
                ? "bg-primary/10 border-primary/40"
                : "bg-card/30 border-border/40 hover:bg-card/50 hover:border-border/60",
              showDetails && "bg-card/50",
            )}
            onClick={handleToggleDetails}
          >
            <div className="flex items-start gap-2 p-1.5">
              {/* Step indicator */}
              <div className="flex flex-col items-center gap-0.5">
                <div
                  className={cn(
                    "w-6 h-6 rounded flex items-center justify-center text-2xs font-mono font-medium transition-colors",
                    entry.isFirstInStep
                      ? getStepColorContainer(event.step)
                      : "",
                  )}
                >
                  {entry.isFirstInStep ? event.step : ""}
                </div>
                {hasChildren && (
                  <button
                    onClick={handleToggle}
                    className={cn(
                      "w-4 h-4 rounded flex items-center justify-center transition-colors",
                      "text-muted-foreground hover:text-foreground hover:bg-muted",
                    )}
                  >
                    {expanded ? (
                      <ChevronDown className="h-3 w-3" />
                    ) : (
                      <ChevronRight className="h-3 w-3" />
                    )}
                  </button>
                )}
              </div>

              {/* Event content */}
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-1.5 mb-0.5">
                  <EventBadge type={event.event_type} />
                  {event.event_type === "Added" && event.forced && (
                    <span className="px-1 py-0 rounded text-2xs font-medium bg-pink-500/20 text-pink-300">
                      FORCED
                    </span>
                  )}
                  {hasChildren && (
                    <span className="text-2xs text-muted-foreground">
                      {modCalls.length > 0 &&
                        `${modCalls.length} mod${modCalls.length > 1 ? "s" : ""}`}
                      {modCalls.length > 0 && actions.length > 0 && " • "}
                      {actions.length > 0 &&
                        `${actions.length} action${actions.length > 1 ? "s" : ""}`}
                    </span>
                  )}
                </div>
                <div className="text-xs text-foreground/90">
                  <EventSummary event={event} />
                </div>
              </div>

              {/* Action buttons */}
              <div
                className={cn(
                  "flex items-center gap-1 transition-opacity",
                  showDetails
                    ? "opacity-100"
                    : "opacity-0 group-hover:opacity-100",
                )}
              >
                <Tooltip>
                  <TooltipTrigger asChild>
                    <button
                      onClick={handleStartComment}
                      className={cn(
                        "p-1 rounded hover:bg-muted text-muted-foreground hover:text-foreground transition-colors",
                        isCommenting && "bg-muted text-foreground",
                      )}
                    >
                      <MessageSquarePlus className="h-3 w-3" />
                    </button>
                  </TooltipTrigger>
                  <TooltipContent>
                    <p className="text-2xs">Add comment</p>
                  </TooltipContent>
                </Tooltip>
                <ChevronDown
                  className={cn(
                    "h-3 w-3 text-muted-foreground transition-transform",
                    showDetails && "rotate-180",
                  )}
                />
              </div>
            </div>

            {/* Expanded details panel */}
            {showDetails && (
              <div className="px-1.5 pb-1.5 pt-0">
                <div className="ml-8 bg-black/20 rounded p-2 text-2xs border border-border/30">
                  <EventDetails event={event} />
                </div>
              </div>
            )}

            {/* Inline comment form */}
            {isCommenting && (
              <div className="px-1.5 pb-1.5 pt-0">
                <InlineCommentForm
                  requestId={requestId}
                  reference={{
                    step: event.step,
                    eventType: event.event_type,
                    eventId: event.id,
                    label: `Step ${event.step} - ${event.event_type}`,
                  }}
                  onCancel={onCancelComment}
                  onSubmitted={onCommentAdded}
                />
              </div>
            )}
          </div>
        </div>

        {/* Children (mod calls and actions) */}
        {expanded && hasChildren && (
          <div className="ml-3 pl-2 border-l border-border/30 space-y-0.5 py-0.5">
            {/* Mod calls */}
            {modCalls.map((mc) => (
              <ModCallCard
                key={mc.modCall.id}
                mc={mc}
                expanded={expandedNodes.has(`modcall-${mc.modCall.id}`)}
                showDetails={expandedDetails.has(`modcall-${mc.modCall.id}`)}
                onToggle={createModCallToggle(mc.modCall.id)}
                onToggleDetails={createModCallDetailsToggle(mc.modCall.id)}
              />
            ))}

            {/* Actions */}
            {actions.map((action) => (
              <ActionCard
                key={action.action_id}
                action={action}
                showDetails={expandedDetails.has(`action-${action.action_id}`)}
                onToggleDetails={createActionDetailsToggle(action.action_id)}
                associatedEvent={event}
              />
            ))}
          </div>
        )}
      </div>
    );
  },
  // Custom comparison function for better memoization
  (prevProps, nextProps) => {
    // Check primitive props first (fast)
    if (
      prevProps.expanded !== nextProps.expanded ||
      prevProps.selectedStep !== nextProps.selectedStep ||
      prevProps.isCommenting !== nextProps.isCommenting ||
      prevProps.requestId !== nextProps.requestId
    ) {
      return false;
    }

    // Check entry identity
    if (prevProps.entry !== nextProps.entry) {
      return false;
    }

    // Check if relevant expanded states changed for this entry
    const entryId = prevProps.entry.id;
    if (
      prevProps.expandedDetails.has(entryId) !==
      nextProps.expandedDetails.has(entryId)
    ) {
      return false;
    }

    // Check mod call expanded states
    for (const mc of prevProps.entry.modCalls) {
      const mcKey = `modcall-${mc.modCall.id}`;
      if (
        prevProps.expandedNodes.has(mcKey) !==
          nextProps.expandedNodes.has(mcKey) ||
        prevProps.expandedDetails.has(mcKey) !==
          nextProps.expandedDetails.has(mcKey)
      ) {
        return false;
      }
    }

    // Check action expanded states
    for (const action of prevProps.entry.actions) {
      const actionKey = `action-${action.action_id}`;
      if (
        prevProps.expandedDetails.has(actionKey) !==
        nextProps.expandedDetails.has(actionKey)
      ) {
        return false;
      }
    }

    // Props are equal, skip re-render
    return true;
  },
);
