import { memo, useState } from "react";
import { MessageSquarePlus, Send, X, User } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { useUsername } from "@/hooks/useUsername";
import { createDiscussion } from "@/lib/api";
import { formatTraceReference } from "@/components/LogDetail/AddCommentDialog";
import type { InlineCommentFormProps } from "./types";

// Inline comment form component
export const InlineCommentForm = memo(function InlineCommentForm({
  requestId,
  reference,
  onCancel,
  onSubmitted,
}: InlineCommentFormProps) {
  const { username, setUsername, isSet: hasUsername } = useUsername();
  const [comment, setComment] = useState("");
  const [usernameInput, setUsernameInput] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [showUsernameInput, setShowUsernameInput] = useState(!hasUsername);

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
      const fullComment = `${formatTraceReference(reference)}\n\n${comment.trim()}`;
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
    <div className="ml-8 bg-primary/5 rounded p-2 border border-primary/20">
      <div className="flex items-center gap-2 mb-2">
        <MessageSquarePlus className="h-3 w-3 text-primary" />
        <span className="text-2xs font-medium text-primary">Add Comment</span>
        <span className="text-2xs text-muted-foreground">on</span>
        <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-2xs font-medium bg-primary/10 text-primary border border-primary/20">
          <span className="font-mono">{reference.step}</span>
          <span className="text-primary/60">•</span>
          <span>{reference.eventType}</span>
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
            (!hasUsername || showUsernameInput) && "opacity-50"
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
});
