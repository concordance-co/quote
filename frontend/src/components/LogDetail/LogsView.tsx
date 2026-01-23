import { useMemo, useState, useEffect, useRef, useCallback } from "react";
import { ExternalLink, MessageSquarePlus, Send, X, User } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import { useUsername } from "@/hooks/useUsername";
import { createDiscussion } from "@/lib/api";
import { formatLogReference, type LogReference } from "./AddCommentDialog";
import type { LogResponse, ModLogEntry, ModCallLog } from "@/types/api";

interface LogsViewProps {
  log: LogResponse;
  requestId: string;
  selectedLogId?: number | null;
  onNavigateToTrace?: (step: number) => void;
  onCommentAdded?: () => void;
}

export function LogsView({
  log,
  requestId,
  selectedLogId,
  onNavigateToTrace,
  onCommentAdded,
}: LogsViewProps) {
  const [commentingOnLog, setCommentingOnLog] = useState<number | null>(null);
  const logRefs = useRef<Map<number, HTMLDivElement>>(new Map());

  const registerLogRef = useCallback(
    (logId: number, element: HTMLDivElement | null) => {
      if (element) {
        logRefs.current.set(logId, element);
      } else {
        logRefs.current.delete(logId);
      }
    },
    [],
  );

  // Scroll to selected log when it changes
  useEffect(() => {
    if (selectedLogId !== null && selectedLogId !== undefined) {
      const element = logRefs.current.get(selectedLogId);
      if (element) {
        setTimeout(() => {
          element.scrollIntoView({ behavior: "smooth", block: "center" });
        }, 50);
      }
    }
  }, [selectedLogId]);
  // Build a lookup map from mod_call_id to ModCallLog
  const modCallMap = useMemo(() => {
    const map = new Map<number, ModCallLog>();
    for (const mc of log.mod_calls || []) {
      map.set(mc.id, mc);
    }
    return map;
  }, [log.mod_calls]);

  const sortedLogs = useMemo(() => {
    const logs = log.mod_logs || [];
    return [...logs].sort(
      (a, b) =>
        new Date(a.created_at).getTime() - new Date(b.created_at).getTime(),
    );
  }, [log.mod_logs]);

  return (
    <div className="panel h-full overflow-auto">
      <div className="panel-header">
        <span className="panel-title">Mod Logs</span>
        <span className="text-2xs text-muted-foreground">
          {sortedLogs.length} {sortedLogs.length === 1 ? "entry" : "entries"}
        </span>
      </div>
      <div className="panel-content p-0">
        <ScrollArea>
          {sortedLogs.length === 0 ? (
            <div className="flex items-center justify-center h-32 text-muted-foreground text-sm">
              No logs recorded
            </div>
          ) : (
            <div className="divide-y divide-border/30">
              {sortedLogs.map((entry) => (
                <LogEntry
                  key={entry.id}
                  entry={entry}
                  modCall={modCallMap.get(entry.mod_call_id)}
                  requestId={requestId}
                  isSelected={selectedLogId === entry.id}
                  onNavigateToTrace={onNavigateToTrace}
                  isCommenting={commentingOnLog === entry.id}
                  onStartComment={() => setCommentingOnLog(entry.id)}
                  onCancelComment={() => setCommentingOnLog(null)}
                  onCommentAdded={() => {
                    setCommentingOnLog(null);
                    onCommentAdded?.();
                  }}
                  registerRef={registerLogRef}
                />
              ))}
            </div>
          )}
        </ScrollArea>
      </div>
    </div>
  );
}

interface LogEntryProps {
  entry: ModLogEntry;
  modCall?: ModCallLog;
  requestId: string;
  isSelected?: boolean;
  onNavigateToTrace?: (step: number) => void;
  isCommenting: boolean;
  onStartComment: () => void;
  onCancelComment: () => void;
  onCommentAdded: () => void;
  registerRef: (logId: number, element: HTMLDivElement | null) => void;
}

function LogEntry({
  entry,
  modCall,
  requestId,
  isSelected,
  onNavigateToTrace,
  isCommenting,
  onStartComment,
  onCancelComment,
  onCommentAdded,
  registerRef,
}: LogEntryProps) {
  const date = new Date(entry.created_at);
  const time = date.toLocaleTimeString(undefined, {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
  const ms = date.getMilliseconds().toString().padStart(3, "0");
  const timeWithMs = `${time}.${ms}`;

  return (
    <div
      ref={(el) => registerRef(entry.id, el)}
      className={cn(
        "px-3 py-2 hover:bg-white/5 transition-colors",
        isSelected && "bg-primary/10 ring-1 ring-primary/30",
      )}
    >
      <div className="flex items-center gap-2 mb-1">
        <LogLevelBadge level={entry.log_level} />
        {modCall && (
          <button
            onClick={() => onNavigateToTrace?.(modCall.step)}
            className={cn(
              "text-2xs font-mono px-1.5 py-0.5 rounded bg-muted text-muted-foreground",
              "flex items-center gap-1 hover:bg-primary/20 hover:text-primary transition-colors",
            )}
          >
            Step {modCall.step}
            <ExternalLink className="h-3 w-3" />
          </button>
        )}
        <span className="text-2xs font-medium text-purple-400">
          {entry.mod_name}
        </span>
        <Tooltip>
          <TooltipTrigger asChild>
            <button
              onClick={onStartComment}
              className={cn(
                "p-1 rounded hover:bg-muted text-muted-foreground hover:text-foreground transition-colors ml-auto",
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
        <span className="text-2xs text-muted-foreground font-mono">
          {timeWithMs}
        </span>
      </div>
      <pre className="text-xs font-mono whitespace-pre-wrap break-words text-foreground/90">
        {entry.log_message}
      </pre>

      {/* Inline comment form */}
      {isCommenting && (
        <InlineLogCommentForm
          requestId={requestId}
          entry={entry}
          step={modCall?.step ?? null}
          onCancel={onCancelComment}
          onSubmitted={onCommentAdded}
        />
      )}
    </div>
  );
}

interface LogLevelBadgeProps {
  level: ModLogEntry["log_level"];
}

function LogLevelBadge({ level }: LogLevelBadgeProps) {
  return (
    <span
      className={cn(
        "text-2xs font-medium px-1.5 py-0.5 rounded",
        level === "DEBUG" && "bg-gray-500/20 text-gray-400",
        level === "INFO" && "bg-blue-500/20 text-blue-400",
        level === "WARNING" && "bg-amber-500/20 text-amber-400",
        level === "ERROR" && "bg-red-500/20 text-red-400",
      )}
    >
      {level}
    </span>
  );
}

// Inline comment form for log entries
interface InlineLogCommentFormProps {
  requestId: string;
  entry: ModLogEntry;
  step: number | null;
  onCancel: () => void;
  onSubmitted: () => void;
}

function InlineLogCommentForm({
  requestId,
  entry,
  step,
  onCancel,
  onSubmitted,
}: InlineLogCommentFormProps) {
  const { username, setUsername, isSet: hasUsername } = useUsername();
  const [comment, setComment] = useState("");
  const [usernameInput, setUsernameInput] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [showUsernameInput, setShowUsernameInput] = useState(!hasUsername);

  const truncatedMessage =
    entry.log_message.length > 30
      ? entry.log_message.slice(0, 30) + "..."
      : entry.log_message;

  const handleSetUsername = () => {
    if (usernameInput.trim()) {
      setUsername(usernameInput.trim());
      setShowUsernameInput(false);
      setUsernameInput("");
    }
  };

  const handleSubmit = async () => {
    if (!comment.trim() || !username) return;

    try {
      setSubmitting(true);
      const reference: LogReference = {
        logId: entry.id,
        step,
        modName: entry.mod_name,
        logLevel: entry.log_level,
        truncatedMessage,
      };
      const fullComment = `${formatLogReference(reference)}\n\n${comment.trim()}`;
      await createDiscussion(requestId, username, fullComment);
      onSubmitted();
    } catch (err) {
      console.error("Failed to create comment:", err);
    } finally {
      setSubmitting(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Escape") {
      onCancel();
    } else if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
      handleSubmit();
    }
  };

  return (
    <div className="mt-2 bg-primary/5 rounded p-2 border border-primary/20">
      <div className="flex items-center gap-2 mb-2">
        <MessageSquarePlus className="h-3 w-3 text-primary" />
        <span className="text-2xs font-medium text-primary">Add Comment</span>
        <span className="text-2xs text-muted-foreground">on</span>
        <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-2xs font-medium bg-purple-500/10 text-purple-400 border border-purple-500/20">
          <span>{entry.mod_name}</span>
          <span className="text-purple-400/60">•</span>
          <span>{entry.log_level}</span>
        </span>
        <button
          onClick={onCancel}
          className="ml-auto p-0.5 rounded hover:bg-muted text-muted-foreground hover:text-foreground transition-colors"
        >
          <X className="h-3 w-3" />
        </button>
      </div>

      {showUsernameInput || !hasUsername ? (
        <div className="flex items-center gap-2 mb-2">
          <User className="h-3 w-3 text-muted-foreground" />
          <input
            type="text"
            placeholder="Your username..."
            value={usernameInput}
            onChange={(e) => setUsernameInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleSetUsername()}
            className="flex-1 h-6 px-2 rounded border border-input bg-background text-xs focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
            autoFocus
          />
          <Button
            size="sm"
            className="h-6 text-xs px-2"
            onClick={handleSetUsername}
            disabled={!usernameInput.trim()}
          >
            Set
          </Button>
        </div>
      ) : (
        <div className="flex items-center gap-1 mb-2 text-2xs text-muted-foreground">
          <span>Posting as</span>
          <button
            onClick={() => setShowUsernameInput(true)}
            className="font-medium text-primary hover:underline"
          >
            {username}
          </button>
        </div>
      )}

      <div className="flex items-start gap-2">
        <textarea
          placeholder="Write your comment..."
          value={comment}
          onChange={(e) => setComment(e.target.value)}
          onKeyDown={handleKeyDown}
          className={cn(
            "flex-1 h-14 px-2 py-1 rounded border border-input bg-background text-xs resize-none",
            "focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring",
            (!hasUsername || showUsernameInput) && "opacity-50",
          )}
          disabled={!hasUsername || showUsernameInput}
          autoFocus={hasUsername}
        />
        <Button
          size="sm"
          className="h-8 w-8 p-0"
          onClick={handleSubmit}
          disabled={
            !comment.trim() || !hasUsername || showUsernameInput || submitting
          }
        >
          <Send className="h-3.5 w-3.5" />
        </Button>
      </div>
      <p className="text-2xs text-muted-foreground mt-1">⌘+Enter to submit</p>
    </div>
  );
}
