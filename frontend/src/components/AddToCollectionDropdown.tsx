import { useState, useEffect, useCallback } from "react";
import {
  FolderOpen,
  FolderPlus,
  Check,
  Loader2,
  Plus,
  X,
  ChevronDown,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import {
  listCollections,
  createCollection,
  addRequestToCollection,
  removeRequestFromCollection,
  getRequestCollections,
  type CollectionSummary,
} from "@/lib/api";

interface AddToCollectionDropdownProps {
  requestId: string;
  onCollectionChange?: () => void;
  variant?: "icon" | "button";
  className?: string;
}

export default function AddToCollectionDropdown({
  requestId,
  onCollectionChange,
  variant = "icon",
  className,
}: AddToCollectionDropdownProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [collections, setCollections] = useState<CollectionSummary[]>([]);
  const [requestCollectionIds, setRequestCollectionIds] = useState<Set<number>>(
    new Set()
  );
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Create collection state
  const [isCreating, setIsCreating] = useState(false);
  const [newCollectionName, setNewCollectionName] = useState("");
  const [createLoading, setCreateLoading] = useState(false);

  // Toggle loading state
  const [togglingId, setTogglingId] = useState<number | null>(null);

  const loadData = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);

      // Load all collections and collections containing this request in parallel
      const [collectionsResponse, requestCollectionsResponse] = await Promise.all([
        listCollections(100, 0),
        getRequestCollections(requestId),
      ]);

      setCollections(collectionsResponse.collections);
      setRequestCollectionIds(
        new Set(requestCollectionsResponse.collections.map((c) => c.id))
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load collections");
    } finally {
      setLoading(false);
    }
  }, [requestId]);

  useEffect(() => {
    if (isOpen) {
      loadData();
    }
  }, [isOpen, loadData]);

  const handleToggleCollection = async (collectionId: number) => {
    const isInCollection = requestCollectionIds.has(collectionId);

    try {
      setTogglingId(collectionId);

      if (isInCollection) {
        await removeRequestFromCollection(collectionId, requestId);
        setRequestCollectionIds((prev) => {
          const next = new Set(prev);
          next.delete(collectionId);
          return next;
        });
      } else {
        await addRequestToCollection(collectionId, requestId);
        setRequestCollectionIds((prev) => new Set(prev).add(collectionId));
      }

      onCollectionChange?.();
    } catch (err) {
      console.error("Failed to toggle collection:", err);
    } finally {
      setTogglingId(null);
    }
  };

  const handleCreateCollection = async () => {
    const name = newCollectionName.trim();
    if (!name) return;

    try {
      setCreateLoading(true);
      const response = await createCollection(name);

      // Add to collections list and mark as containing this request
      const newCollection: CollectionSummary = {
        ...response.collection,
        request_count: 0,
      };
      setCollections((prev) => [newCollection, ...prev]);

      // Add the request to the new collection
      await addRequestToCollection(response.collection.id, requestId);
      setRequestCollectionIds((prev) =>
        new Set(prev).add(response.collection.id)
      );

      setNewCollectionName("");
      setIsCreating(false);
      onCollectionChange?.();
    } catch (err) {
      console.error("Failed to create collection:", err);
    } finally {
      setCreateLoading(false);
    }
  };

  const inCollectionCount = requestCollectionIds.size;

  return (
    <div className={cn("relative", className)}>
      {/* Trigger Button */}
      {variant === "icon" ? (
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant="ghost"
              size="icon"
              className="h-7 w-7"
              onClick={() => setIsOpen(!isOpen)}
            >
              <FolderPlus
                className={cn(
                  "h-3.5 w-3.5",
                  inCollectionCount > 0 && "text-primary"
                )}
              />
              {inCollectionCount > 0 && (
                <span className="absolute -top-1 -right-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-primary px-1 text-2xs font-medium text-primary-foreground">
                  {inCollectionCount}
                </span>
              )}
            </Button>
          </TooltipTrigger>
          <TooltipContent>
            <p className="text-xs">
              {inCollectionCount > 0
                ? `In ${inCollectionCount} collection${inCollectionCount !== 1 ? "s" : ""}`
                : "Add to collection"}
            </p>
          </TooltipContent>
        </Tooltip>
      ) : (
        <Button
          variant="outline"
          size="sm"
          className="h-7 text-xs gap-1.5"
          onClick={() => setIsOpen(!isOpen)}
        >
          <FolderPlus className="h-3.5 w-3.5" />
          <span>Collections</span>
          {inCollectionCount > 0 && (
            <Badge variant="secondary" className="h-4 px-1 text-2xs">
              {inCollectionCount}
            </Badge>
          )}
          <ChevronDown className="h-3 w-3 ml-1" />
        </Button>
      )}

      {/* Dropdown */}
      {isOpen && (
        <>
          {/* Backdrop */}
          <div
            className="fixed inset-0 z-40"
            onClick={() => setIsOpen(false)}
          />

          {/* Dropdown Content */}
          <div className="absolute right-0 top-full mt-1 z-50 w-64 bg-popover border border-border rounded-md shadow-lg overflow-hidden">
            {/* Header */}
            <div className="px-3 py-2 border-b border-border/50 flex items-center justify-between">
              <span className="text-xs font-medium">Add to Collection</span>
              <Button
                variant="ghost"
                size="icon"
                className="h-5 w-5"
                onClick={() => setIsOpen(false)}
              >
                <X className="h-3 w-3" />
              </Button>
            </div>

            {/* Create New Collection */}
            <div className="px-2 py-2 border-b border-border/50">
              {isCreating ? (
                <div className="flex items-center gap-1">
                  <input
                    type="text"
                    value={newCollectionName}
                    onChange={(e) => setNewCollectionName(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") handleCreateCollection();
                      if (e.key === "Escape") {
                        setIsCreating(false);
                        setNewCollectionName("");
                      }
                    }}
                    placeholder="Collection name..."
                    className="flex-1 h-7 px-2 text-xs bg-background border border-border rounded focus:outline-none focus:ring-1 focus:ring-primary"
                    autoFocus
                    disabled={createLoading}
                  />
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-7 w-7 shrink-0"
                    onClick={handleCreateCollection}
                    disabled={createLoading || !newCollectionName.trim()}
                  >
                    {createLoading ? (
                      <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    ) : (
                      <Check className="h-3.5 w-3.5 text-green-500" />
                    )}
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-7 w-7 shrink-0"
                    onClick={() => {
                      setIsCreating(false);
                      setNewCollectionName("");
                    }}
                    disabled={createLoading}
                  >
                    <X className="h-3.5 w-3.5" />
                  </Button>
                </div>
              ) : (
                <Button
                  variant="ghost"
                  size="sm"
                  className="w-full h-7 justify-start text-xs gap-2"
                  onClick={() => setIsCreating(true)}
                >
                  <Plus className="h-3.5 w-3.5" />
                  Create New Collection
                </Button>
              )}
            </div>

            {/* Collections List */}
            <div className="max-h-64 overflow-y-auto">
              {loading ? (
                <div className="flex items-center justify-center py-8">
                  <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
                </div>
              ) : error ? (
                <div className="text-center py-4 px-3">
                  <p className="text-xs text-destructive mb-2">{error}</p>
                  <Button variant="ghost" size="sm" onClick={loadData}>
                    Retry
                  </Button>
                </div>
              ) : collections.length === 0 ? (
                <div className="text-center py-6 text-muted-foreground">
                  <FolderOpen className="h-8 w-8 mx-auto mb-2 opacity-50" />
                  <p className="text-xs">No collections yet</p>
                </div>
              ) : (
                <div className="py-1">
                  {collections.map((collection) => {
                    const isInCollection = requestCollectionIds.has(
                      collection.id
                    );
                    const isToggling = togglingId === collection.id;

                    return (
                      <button
                        key={collection.id}
                        onClick={() => handleToggleCollection(collection.id)}
                        disabled={isToggling}
                        className={cn(
                          "w-full flex items-center gap-2 px-3 py-2 text-left text-xs transition-colors",
                          isInCollection
                            ? "bg-primary/5"
                            : "hover:bg-muted/50",
                          isToggling && "opacity-50"
                        )}
                      >
                        <div
                          className={cn(
                            "w-4 h-4 rounded border flex items-center justify-center shrink-0",
                            isInCollection
                              ? "bg-primary border-primary"
                              : "border-muted-foreground/30"
                          )}
                        >
                          {isToggling ? (
                            <Loader2 className="h-3 w-3 animate-spin text-primary-foreground" />
                          ) : isInCollection ? (
                            <Check className="h-3 w-3 text-primary-foreground" />
                          ) : null}
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="truncate">{collection.name}</div>
                          {collection.description && (
                            <div className="text-2xs text-muted-foreground truncate">
                              {collection.description}
                            </div>
                          )}
                        </div>
                        <Badge
                          variant="secondary"
                          className="h-4 px-1 text-2xs shrink-0"
                        >
                          {collection.request_count ?? 0}
                        </Badge>
                      </button>
                    );
                  })}
                </div>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
