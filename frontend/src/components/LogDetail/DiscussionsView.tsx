import { useState, useEffect, useCallback } from "react";
import {
  MessageCircle,
  Send,
  Edit2,
  Trash2,
  X,
  Check,
  User,
  ExternalLink,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import { useUsername } from "@/hooks/useUsername";
import {
  listDiscussions,
  createDiscussion,
  updateDiscussion,
  deleteDiscussion,
  type Discussion,
} from "@/lib/api";
import {
  parseAllTraceReferences,
  parseAllLogReferences,
  parseAllChartReferences,
} from "./AddCommentDialog";

interface DiscussionsViewProps {
  requestId: string;
  onNavigateToTrace?: (step: number) => void;
  onNavigateToLogs?: (logId: number) => void;
  onNavigateToMetrics?: (chartId: string) => void;
  onDiscussionCountChange?: (count: number) => void;
  /** When true, disables all editing functionality (create/edit/delete comments) */
  readOnly?: boolean;
}

export function DiscussionsView({
  requestId,
  onNavigateToTrace,
  onNavigateToLogs,
  onNavigateToMetrics,
  onDiscussionCountChange,
  readOnly = false,
}: DiscussionsViewProps) {
  const { username, setUsername, isSet: hasUsername } = useUsername();
  const [discussions, setDiscussions] = useState<Discussion[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [newComment, setNewComment] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editingText, setEditingText] = useState("");
  const [showUsernameInput, setShowUsernameInput] = useState(false);
  const [usernameInput, setUsernameInput] = useState("");

  const loadDiscussions = useCallback(async () => {
    try {
      setLoading(true);
      const response = await listDiscussions(requestId);
      setDiscussions(response.discussions);
      setError(null);
      // Report the discussion count to parent
      onDiscussionCountChange?.(response.discussions.length);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to load discussions",
      );
    } finally {
      setLoading(false);
    }
  }, [requestId, onDiscussionCountChange]);

  useEffect(() => {
    loadDiscussions();
  }, [loadDiscussions]);

  const handleSetUsername = () => {
    if (usernameInput.trim()) {
      setUsername(usernameInput.trim());
      setShowUsernameInput(false);
      setUsernameInput("");
    }
  };

  const handleSubmitComment = async () => {
    if (!newComment.trim() || !username || readOnly) return;

    try {
      setSubmitting(true);
      const response = await createDiscussion(
        requestId,
        username,
        newComment.trim(),
      );
      setDiscussions((prev) => [...prev, response.discussion]);
      setNewComment("");
    } catch (err) {
      console.error("Failed to create comment:", err);
    } finally {
      setSubmitting(false);
    }
  };

  const handleStartEdit = (discussion: Discussion) => {
    setEditingId(discussion.id);
    setEditingText(discussion.comment);
  };

  const handleCancelEdit = () => {
    setEditingId(null);
    setEditingText("");
  };

  const handleSaveEdit = async (discussionId: number) => {
    if (!editingText.trim()) return;

    try {
      const response = await updateDiscussion(
        requestId,
        discussionId,
        editingText.trim(),
      );
      setDiscussions((prev) =>
        prev.map((d) => (d.id === discussionId ? response.discussion : d)),
      );
      setEditingId(null);
      setEditingText("");
    } catch (err) {
      console.error("Failed to update comment:", err);
    }
  };

  const handleDelete = async (discussionId: number) => {
    if (!confirm("Are you sure you want to delete this comment?")) return;

    try {
      await deleteDiscussion(requestId, discussionId);
      setDiscussions((prev) => prev.filter((d) => d.id !== discussionId));
    } catch (err) {
      console.error("Failed to delete comment:", err);
    }
  };

  const formatTime = (dateStr: string) => {
    const date = new Date(dateStr);
    return date.toLocaleString(undefined, {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  };

  const isEdited = (discussion: Discussion) => {
    return discussion.updated_at !== discussion.created_at;
  };

  return (
    <div className="panel h-full flex flex-col">
      <div className="panel-header flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="panel-title">Discussion</span>
          <span className="text-2xs text-muted-foreground">
            {discussions.length}{" "}
            {discussions.length === 1 ? "comment" : "comments"}
          </span>
        </div>
        {!readOnly && (
          <div className="flex items-center gap-2">
            {hasUsername ? (
              <Tooltip>
                <TooltipTrigger asChild>
                  <button
                    onClick={() => setShowUsernameInput(true)}
                    className="flex items-center gap-1.5 px-2 py-1 rounded bg-muted text-xs hover:bg-muted/80 transition-colors"
                  >
                    <User className="h-3 w-3" />
                    <span>{username}</span>
                  </button>
                </TooltipTrigger>
                <TooltipContent>
                  <p className="text-2xs">Click to change username</p>
                </TooltipContent>
              </Tooltip>
            ) : (
              <Button
                size="sm"
                variant="outline"
                className="h-7 text-xs"
                onClick={() => setShowUsernameInput(true)}
              >
                <User className="h-3 w-3 mr-1.5" />
                Set Username
              </Button>
            )}
          </div>
        )}
      </div>

      {/* Username Input Modal */}
      {showUsernameInput && (
        <div className="px-3 py-2 border-b border-border bg-muted/30">
          <div className="flex items-center gap-2">
            <input
              type="text"
              placeholder="Enter your username..."
              value={usernameInput}
              onChange={(e) => setUsernameInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleSetUsername()}
              className="flex-1 h-8 px-2 rounded border border-input bg-background text-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
              autoFocus
            />
            <Button
              size="sm"
              className="h-8"
              onClick={handleSetUsername}
              disabled={!usernameInput.trim()}
            >
              <Check className="h-3.5 w-3.5" />
            </Button>
            <Button
              size="sm"
              variant="ghost"
              className="h-8"
              onClick={() => {
                setShowUsernameInput(false);
                setUsernameInput("");
              }}
            >
              <X className="h-3.5 w-3.5" />
            </Button>
          </div>
        </div>
      )}

      {/* Discussions List */}
      <ScrollArea className="flex-1 min-h-0">
        <div className="p-3 space-y-3">
          {loading ? (
            <div className="flex items-center justify-center py-8 text-muted-foreground text-sm">
              Loading discussions...
            </div>
          ) : error ? (
            <div className="flex flex-col items-center justify-center py-8 text-center">
              <p className="text-sm text-destructive mb-2">{error}</p>
              <Button size="sm" variant="outline" onClick={loadDiscussions}>
                Try Again
              </Button>
            </div>
          ) : discussions.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-8 text-center text-muted-foreground">
              <MessageCircle className="h-8 w-8 mb-2 opacity-50" />
              <p className="text-sm">No comments yet</p>
              <p className="text-xs">Be the first to start a discussion!</p>
            </div>
          ) : (
            discussions.map((discussion) => (
              <div
                key={discussion.id}
                className={cn(
                  "rounded-lg border p-3",
                  discussion.username === username
                    ? "border-primary/30 bg-primary/5"
                    : "border-border bg-muted/20",
                )}
              >
                <div className="flex items-start justify-between gap-2 mb-2">
                  <div className="flex items-center gap-2">
                    <span className="font-medium text-sm">
                      {discussion.username}
                    </span>
                    <span className="text-2xs text-muted-foreground">
                      {formatTime(discussion.created_at)}
                    </span>
                    {isEdited(discussion) && (
                      <span className="text-2xs text-muted-foreground/70">
                        (edited)
                      </span>
                    )}
                  </div>
                  {!readOnly &&
                    discussion.username === username &&
                    editingId !== discussion.id && (
                      <div className="flex items-center gap-1">
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <button
                              onClick={() => handleStartEdit(discussion)}
                              className="p-1 rounded hover:bg-muted transition-colors text-muted-foreground hover:text-foreground"
                            >
                              <Edit2 className="h-3 w-3" />
                            </button>
                          </TooltipTrigger>
                          <TooltipContent>
                            <p className="text-2xs">Edit</p>
                          </TooltipContent>
                        </Tooltip>
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <button
                              onClick={() => handleDelete(discussion.id)}
                              className="p-1 rounded hover:bg-muted transition-colors text-muted-foreground hover:text-destructive"
                            >
                              <Trash2 className="h-3 w-3" />
                            </button>
                          </TooltipTrigger>
                          <TooltipContent>
                            <p className="text-2xs">Delete</p>
                          </TooltipContent>
                        </Tooltip>
                      </div>
                    )}
                </div>
                {editingId === discussion.id ? (
                  <div className="space-y-2">
                    <textarea
                      value={editingText}
                      onChange={(e) => setEditingText(e.target.value)}
                      className="w-full h-20 px-2 py-1.5 rounded border border-input bg-background text-sm resize-none focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                      autoFocus
                    />
                    <div className="flex items-center gap-2 justify-end">
                      <Button
                        size="sm"
                        variant="ghost"
                        className="h-7 text-xs"
                        onClick={handleCancelEdit}
                      >
                        Cancel
                      </Button>
                      <Button
                        size="sm"
                        className="h-7 text-xs"
                        onClick={() => handleSaveEdit(discussion.id)}
                        disabled={!editingText.trim()}
                      >
                        Save
                      </Button>
                    </div>
                  </div>
                ) : (
                  <div className="text-sm whitespace-pre-wrap">
                    <CommentWithReferences
                      text={discussion.comment}
                      onNavigateToTrace={onNavigateToTrace}
                      onNavigateToLogs={onNavigateToLogs}
                      onNavigateToMetrics={onNavigateToMetrics}
                    />
                  </div>
                )}
              </div>
            ))
          )}
        </div>
      </ScrollArea>

      {/* New Comment Input */}
      <div className="border-t border-border p-3">
        {readOnly ? (
          <div className="text-center py-2">
            <p className="text-sm text-muted-foreground">
              Sign in to join the discussion
            </p>
          </div>
        ) : hasUsername ? (
          <div className="flex items-start gap-2">
            <textarea
              placeholder="Write a comment..."
              value={newComment}
              onChange={(e) => setNewComment(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
                  handleSubmitComment();
                }
              }}
              className="flex-1 h-16 px-2 py-1.5 rounded border border-input bg-background text-sm resize-none focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
            />
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  size="sm"
                  className="h-8 w-8 p-0"
                  onClick={handleSubmitComment}
                  disabled={!newComment.trim() || submitting}
                >
                  <Send className="h-4 w-4" />
                </Button>
              </TooltipTrigger>
              <TooltipContent>
                <p className="text-2xs">Send (⌘+Enter)</p>
              </TooltipContent>
            </Tooltip>
          </div>
        ) : (
          <div className="text-center py-2">
            <p className="text-sm text-muted-foreground mb-2">
              Set a username to join the discussion
            </p>
            <Button
              size="sm"
              variant="outline"
              onClick={() => setShowUsernameInput(true)}
            >
              <User className="h-3 w-3 mr-1.5" />
              Set Username
            </Button>
          </div>
        )}
      </div>
    </div>
  );
}

// Component to render comment text with clickable trace and log references
interface CommentWithReferencesProps {
  text: string;
  onNavigateToTrace?: (step: number) => void;
  onNavigateToLogs?: (logId: number) => void;
  onNavigateToMetrics?: (chartId: string) => void;
}

function CommentWithReferences({
  text,
  onNavigateToTrace,
  onNavigateToLogs,
  onNavigateToMetrics,
}: CommentWithReferencesProps) {
  const traceRefs = parseAllTraceReferences(text);
  const logRefs = parseAllLogReferences(text);
  const chartRefs = parseAllChartReferences(text);

  // Combine all references and sort by position
  const allRefs: {
    type: "trace" | "log" | "chart";
    ref:
      | (typeof traceRefs)[0]["ref"]
      | (typeof logRefs)[0]["ref"]
      | (typeof chartRefs)[0]["ref"];
    start: number;
    end: number;
  }[] = [
    ...traceRefs.map((r) => ({ type: "trace" as const, ...r })),
    ...logRefs.map((r) => ({ type: "log" as const, ...r })),
    ...chartRefs.map((r) => ({ type: "chart" as const, ...r })),
  ].sort((a, b) => a.start - b.start);

  if (allRefs.length === 0) {
    return <>{text}</>;
  }

  const parts: React.ReactNode[] = [];
  let lastIndex = 0;

  allRefs.forEach(({ type, ref, start, end }, idx) => {
    // Add text before this reference
    if (start > lastIndex) {
      parts.push(
        <span key={`text-${idx}`}>{text.slice(lastIndex, start)}</span>,
      );
    }

    if (type === "trace") {
      const traceRef = ref as (typeof traceRefs)[0]["ref"];
      // Add the trace reference as a clickable badge
      parts.push(
        <button
          key={`trace-${idx}`}
          onClick={() => onNavigateToTrace?.(traceRef.step)}
          className={cn(
            "inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-2xs font-medium",
            "bg-primary/10 text-primary border border-primary/20",
            "hover:bg-primary/20 transition-colors cursor-pointer",
            onNavigateToTrace ? "" : "cursor-default",
          )}
        >
          <span className="font-mono">{traceRef.step}</span>
          <span className="text-primary/60">•</span>
          <span>{traceRef.eventType}</span>
          {onNavigateToTrace && <ExternalLink className="h-2.5 w-2.5 ml-0.5" />}
        </button>,
      );
    } else if (type === "log") {
      const logRef = ref as (typeof logRefs)[0]["ref"];
      // Add the log reference as a clickable badge
      parts.push(
        <button
          key={`log-${idx}`}
          onClick={() => onNavigateToLogs?.(logRef.logId)}
          className={cn(
            "inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-2xs font-medium",
            "bg-purple-500/10 text-purple-400 border border-purple-500/20",
            "hover:bg-purple-500/20 transition-colors cursor-pointer",
            onNavigateToLogs ? "" : "cursor-default",
          )}
        >
          <span>{logRef.modName}</span>
          <span className="text-purple-400/60">•</span>
          <span>{logRef.logLevel}</span>
          {onNavigateToLogs && <ExternalLink className="h-2.5 w-2.5 ml-0.5" />}
        </button>,
      );
    } else {
      const chartRef = ref as (typeof chartRefs)[0]["ref"];
      // Add the chart reference as a clickable badge
      parts.push(
        <button
          key={`chart-${idx}`}
          onClick={() => onNavigateToMetrics?.(chartRef.chartId)}
          className={cn(
            "inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-2xs font-medium",
            "bg-amber-500/10 text-amber-400 border border-amber-500/20",
            "hover:bg-amber-500/20 transition-colors cursor-pointer",
            onNavigateToMetrics ? "" : "cursor-default",
          )}
        >
          <span>{chartRef.chartTitle}</span>
          {onNavigateToMetrics && (
            <ExternalLink className="h-2.5 w-2.5 ml-0.5" />
          )}
        </button>,
      );
    }

    lastIndex = end;
  });

  // Add any remaining text after the last reference
  if (lastIndex < text.length) {
    parts.push(<span key="text-end">{text.slice(lastIndex)}</span>);
  }

  return <>{parts}</>;
}
