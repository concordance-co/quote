import { useState, useMemo } from "react";
import { ChevronRight, Zap, ExternalLink } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn, formatDate } from "@/lib/utils";
import type { LogResponse, ActionLog, ModCallLog } from "@/types/api";

interface ActionsViewProps {
  log: LogResponse;
  onNavigateToTrace?: (step: number) => void;
}

export function ActionsView({ log, onNavigateToTrace }: ActionsViewProps) {
  const actions = log.actions || [];

  // Build a lookup map from mod_call id to ModCallLog
  const modCallMap = useMemo(() => {
    const map = new Map<number, ModCallLog>();
    for (const mc of log.mod_calls || []) {
      map.set(mc.id, mc);
    }
    return map;
  }, [log.mod_calls]);

  if (actions.length === 0) {
    return (
      <div className="panel">
        <div className="flex flex-col items-center justify-center py-8 text-center">
          <Zap className="h-5 w-5 text-muted-foreground mb-2" />
          <p className="text-sm font-medium mb-1">No actions recorded</p>
          <p className="text-xs text-muted-foreground">
            No mod actions were triggered during this request
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="panel h-full overflow-auto">
      <div className="panel-header">
        <span className="panel-title">Mod Actions</span>
        <span className="text-2xs text-muted-foreground">
          {actions.length} actions
        </span>
      </div>
      <div className="overflow-x-auto">
        <table className="data-table">
          <thead>
            <tr>
              <th>Type</th>
              <th>Step</th>
              <th>Details</th>
              <th className="text-right">Time</th>
            </tr>
          </thead>
          <tbody>
            {actions.map((action) => (
              <ActionRow
                key={action.action_id}
                action={action}
                modCall={
                  action.mod_id ? modCallMap.get(action.mod_id) : undefined
                }
                onNavigateToTrace={onNavigateToTrace}
              />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

interface ActionRowProps {
  action: ActionLog;
  modCall?: ModCallLog;
  onNavigateToTrace?: (step: number) => void;
}

function ActionRow({ action, modCall, onNavigateToTrace }: ActionRowProps) {
  const [isExpanded, setIsExpanded] = useState(false);
  const hasPayload = Object.keys(action.payload || {}).length > 0;

  return (
    <>
      <tr
        className={cn(hasPayload && "cursor-pointer")}
        onClick={() => hasPayload && setIsExpanded(!isExpanded)}
      >
        <td>
          <Badge
            variant="outline"
            className={cn(
              "text-2xs h-5 px-1.5 rounded font-mono",
              `badge-${action.action_type.toLowerCase()}`,
            )}
          >
            {action.action_type}
          </Badge>
        </td>
        <td className="font-mono text-xs">
          {(() => {
            const step = action.step_index ?? modCall?.step ?? null;
            if (step === null) return "—";
            return (
              <Tooltip>
                <TooltipTrigger asChild>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      onNavigateToTrace?.(step);
                    }}
                    className={cn(
                      "px-1.5 py-0.5 rounded bg-muted text-muted-foreground",
                      "flex items-center gap-1 hover:bg-primary/20 hover:text-primary transition-colors",
                    )}
                  >
                    {step}
                    <ExternalLink className="h-3 w-3" />
                  </button>
                </TooltipTrigger>
                <TooltipContent>
                  <p className="text-2xs">Go to step in trace</p>
                </TooltipContent>
              </Tooltip>
            );
          })()}
        </td>
        <td className="text-muted-foreground text-xs max-w-[300px] truncate">
          {getActionSummary(action)}
        </td>
        <td className="text-right text-xs text-muted-foreground whitespace-nowrap">
          {formatDate(action.created_at)}
          {hasPayload && (
            <ChevronRight
              className={cn(
                "inline-block ml-1 h-3 w-3 transition-transform",
                isExpanded && "rotate-90",
              )}
            />
          )}
        </td>
      </tr>
      {isExpanded && hasPayload && (
        <tr>
          <td colSpan={4} className="bg-black/20 p-0">
            <pre className="p-2 text-2xs font-mono overflow-auto max-h-[200px] scrollbar-thin">
              {JSON.stringify(action.payload, null, 2)}
            </pre>
          </td>
        </tr>
      )}
    </>
  );
}

function getActionSummary(action: ActionLog): string {
  const payload = action.payload || {};

  switch (action.action_type) {
    case "ForceTokens":
    case "ForceOutput": {
      const tokensAsTextRaw = payload.tokens_as_text;
      const text = Array.isArray(tokensAsTextRaw)
        ? tokensAsTextRaw.join("")
        : tokensAsTextRaw || "";
      const count = payload.token_count || payload.tokens?.length || 0;
      return `${count} token(s): "${text}"`;
    }
    case "AdjustedLogits": {
      const shape = payload.logits_shape;
      return shape
        ? `shape: [${Array.isArray(shape) ? shape.join(", ") : shape}]`
        : "";
    }
    case "Backtrack": {
      const n = payload.backtrack_steps || payload.n || 0;
      return `${n} steps`;
    }
    case "AdjustedPrefill": {
      const maxSteps = payload.adjusted_max_steps;
      const count = payload.token_count || 0;
      return `${count} tokens, max_steps: ${maxSteps ?? "—"}`;
    }
    case "ToolCalls":
      return "tool calls";
    case "EmitError":
      return payload.error_message
        ? String(payload.error_message).slice(0, 50)
        : "";
    default:
      return "";
  }
}
