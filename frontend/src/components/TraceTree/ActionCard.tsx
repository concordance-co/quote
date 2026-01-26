import { memo } from "react";
import { ArrowLeftFromLine, Info } from "lucide-react";
import { cn } from "@/lib/utils";
import { ActionBadge } from "./badges";
import { ActionSummary } from "./ActionSummary";
import type { ActionCardProps } from "./types";

// Action card component - renders a single action
export const ActionCard = memo(function ActionCard({
  action,
  showDetails,
  onToggleDetails,
  associatedEvent,
}: ActionCardProps) {
  return (
    <div className="rounded border border-cyan-500/20 bg-cyan-500/5 hover:bg-cyan-500/10 transition-colors">
      <div className="flex items-center gap-1.5 px-1.5 py-1 group">
        <div className="w-5 h-5 rounded bg-cyan-500/20 flex items-center justify-center">
          <ArrowLeftFromLine className="h-2.5 w-2.5 text-cyan-400" />
        </div>

        <ActionBadge type={action.action_type} />
        <span className="text-xs text-foreground/80">
          <ActionSummary action={action} associatedEvent={associatedEvent} />
        </span>

        <button
          onClick={(e) => {
            e.stopPropagation();
            onToggleDetails();
          }}
          className={cn(
            "p-0.5 rounded opacity-0 group-hover:opacity-100 transition-opacity ml-auto",
            showDetails ? "bg-primary/20 text-primary" : "hover:bg-muted",
          )}
        >
          <Info className="h-2.5 w-2.5" />
        </button>
      </div>

      {/* Action details */}
      {showDetails && (
        <div className="px-1.5 pb-1.5">
          <div className="bg-black/20 rounded p-1.5 text-2xs border border-border/30">
            <pre className="whitespace-pre-wrap break-all font-mono">
              {JSON.stringify(action.payload, null, 2)}
            </pre>
          </div>
        </div>
      )}
    </div>
  );
});
