import { useState, useCallback } from "react";
import { Plus, X, Pencil, Check, Tag } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import { addTag, removeTag } from "@/lib/api";

interface TagsManagerProps {
  requestId: string;
  tags: string[];
  onTagsChange: (tags: string[]) => void;
  /** When true, disables all editing functionality (add/remove tags) */
  readOnly?: boolean;
}

export function TagsManager({
  requestId,
  tags,
  onTagsChange,
  readOnly = false,
}: TagsManagerProps) {
  const [isEditing, setIsEditing] = useState(false);
  const [isAdding, setIsAdding] = useState(false);
  const [newTag, setNewTag] = useState("");
  const [loading, setLoading] = useState(false);

  const handleAddTag = useCallback(async () => {
    const trimmed = newTag.trim();
    if (!trimmed || loading || readOnly) return;

    try {
      setLoading(true);
      const response = await addTag(requestId, trimmed);
      onTagsChange(response.tags);
      setNewTag("");
      setIsAdding(false);
    } catch (err) {
      console.error("Failed to add tag:", err);
    } finally {
      setLoading(false);
    }
  }, [requestId, newTag, loading, onTagsChange, readOnly]);

  const handleRemoveTag = useCallback(
    async (tag: string) => {
      if (loading || readOnly) return;

      try {
        setLoading(true);
        const response = await removeTag(requestId, tag);
        onTagsChange(response.tags);
      } catch (err) {
        console.error("Failed to remove tag:", err);
      } finally {
        setLoading(false);
      }
    },
    [requestId, loading, onTagsChange, readOnly],
  );

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") {
      handleAddTag();
    } else if (e.key === "Escape") {
      setIsAdding(false);
      setNewTag("");
    }
  };

  return (
    <div className="flex items-center gap-2 flex-wrap">
      <div className="flex items-center gap-1 text-muted-foreground">
        <Tag className="h-3 w-3" />
        <span className="text-xs">Tags:</span>
      </div>

      {/* Existing Tags */}
      {tags.length === 0 && !isAdding && (
        <span className="text-xs text-muted-foreground/70">No tags</span>
      )}

      {tags.map((tag) => (
        <span
          key={tag}
          className={cn(
            "inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium",
            "bg-primary/10 text-primary border border-primary/20",
            isEditing && !readOnly && "pr-1",
          )}
        >
          {tag}
          {isEditing && !readOnly && (
            <button
              onClick={() => handleRemoveTag(tag)}
              disabled={loading}
              className="p-0.5 rounded-full hover:bg-primary/20 transition-colors"
            >
              <X className="h-3 w-3" />
            </button>
          )}
        </span>
      ))}

      {/* Add Tag Input - only show when not readOnly */}
      {!readOnly && (
        <>
          {isAdding ? (
            <div className="flex items-center gap-1">
              <input
                type="text"
                value={newTag}
                onChange={(e) => setNewTag(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="New tag..."
                className="h-6 w-24 px-2 rounded border border-input bg-background text-xs focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                autoFocus
                disabled={loading}
              />
              <Button
                size="sm"
                variant="ghost"
                className="h-6 w-6 p-0"
                onClick={handleAddTag}
                disabled={!newTag.trim() || loading}
              >
                <Check className="h-3 w-3" />
              </Button>
              <Button
                size="sm"
                variant="ghost"
                className="h-6 w-6 p-0"
                onClick={() => {
                  setIsAdding(false);
                  setNewTag("");
                }}
              >
                <X className="h-3 w-3" />
              </Button>
            </div>
          ) : (
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  size="sm"
                  variant="ghost"
                  className="h-6 w-6 p-0"
                  onClick={() => setIsAdding(true)}
                >
                  <Plus className="h-3.5 w-3.5" />
                </Button>
              </TooltipTrigger>
              <TooltipContent>
                <p className="text-2xs">Add tag</p>
              </TooltipContent>
            </Tooltip>
          )}

          {/* Edit Mode Toggle */}
          {tags.length > 0 && !isAdding && (
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  size="sm"
                  variant="ghost"
                  className={cn("h-6 w-6 p-0", isEditing && "text-primary")}
                  onClick={() => setIsEditing(!isEditing)}
                >
                  {isEditing ? (
                    <Check className="h-3.5 w-3.5" />
                  ) : (
                    <Pencil className="h-3 w-3" />
                  )}
                </Button>
              </TooltipTrigger>
              <TooltipContent>
                <p className="text-2xs">
                  {isEditing ? "Done editing" : "Edit tags"}
                </p>
              </TooltipContent>
            </Tooltip>
          )}
        </>
      )}
    </div>
  );
}
