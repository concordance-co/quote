import { memo } from "react";
import { ChevronRight, ChevronDown, Zap, AlertTriangle, Info } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { LogLevelBadge } from "./badges";
import type { ModCallCardProps } from "./types";

// Mod call card component - renders a single mod call with its logs
export const ModCallCard = memo(function ModCallCard({
  mc,
  expanded,
  showDetails,
  onToggle,
  onToggleDetails,
}: ModCallCardProps) {
  const { modCall, logs } = mc;

  return (
    <div className="relative">
      {/* Mod call card */}
      <div className="rounded border border-yellow-500/20 bg-yellow-500/5 hover:bg-yellow-500/10 transition-colors">
        <div className="flex items-center gap-1.5 px-1.5 py-1 group">
          <div className="w-5 h-5 rounded bg-yellow-500/20 flex items-center justify-center">
            <Zap className="h-2.5 w-2.5 text-yellow-400" />
          </div>

          {logs.length > 0 && (
            <button
              onClick={onToggle}
              className="text-muted-foreground hover:text-foreground"
            >
              {expanded ? (
                <ChevronDown className="h-3 w-3" />
              ) : (
                <ChevronRight className="h-3 w-3" />
              )}
            </button>
          )}

          <span className="text-xs font-medium text-yellow-300">
            {modCall.mod_name}
          </span>
          <span className="text-2xs text-muted-foreground px-1 rounded bg-muted/50">
            {modCall.event_type}
          </span>

          {modCall.execution_time_ms && (
            <span className="text-2xs text-muted-foreground ml-auto">
              {modCall.execution_time_ms.toFixed(1)}ms
            </span>
          )}

          {modCall.exception_occurred && (
            <Badge variant="destructive" className="h-4 text-2xs px-1">
              <AlertTriangle className="h-2.5 w-2.5 mr-0.5" />
              Error
            </Badge>
          )}

          <button
            onClick={(e) => {
              e.stopPropagation();
              onToggleDetails();
            }}
            className={cn(
              "p-0.5 rounded opacity-0 group-hover:opacity-100 transition-opacity",
              showDetails
                ? "bg-primary/20 text-primary"
                : "hover:bg-muted"
            )}
          >
            <Info className="h-2.5 w-2.5" />
          </button>
        </div>

        {/* Mod call details */}
        {showDetails && (
          <div className="px-1.5 pb-1.5">
            <div className="bg-black/20 rounded p-1.5 text-2xs border border-border/30">
              <div className="grid grid-cols-2 gap-x-4 gap-y-1">
                <span className="text-muted-foreground">Event ID:</span>
                <span className="font-mono">{modCall.event_id}</span>
                <span className="text-muted-foreground">Step:</span>
                <span>{modCall.step}</span>
                {modCall.exception_message && (
                  <>
                    <span className="text-muted-foreground">Exception:</span>
                    <span className="text-red-400">
                      {modCall.exception_message}
                    </span>
                  </>
                )}
              </div>
            </div>
          </div>
        )}

        {/* Logs */}
        {expanded && logs.length > 0 && (
          <div className="px-1.5 pb-1.5 space-y-0.5">
            {logs.map((log) => (
              <div
                key={log.id}
                className="flex items-start gap-1.5 text-2xs bg-black/10 rounded p-1.5"
              >
                <LogLevelBadge level={log.log_level} />
                <span className="text-muted-foreground break-all whitespace-pre-wrap">
                  {log.log_message}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
});
