import { useState, useEffect, useCallback, useMemo } from "react";
import {
  FolderOpen,
  Plus,
  ChevronRight,
  ChevronDown,
  Loader2,
  Trash2,
  Edit2,
  X,
  Check,
  FolderPlus,
  Key,
  Layers,
  User,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn, formatRelativeTime, truncateId } from "@/lib/utils";
import {
  listCollections,
  createCollection,
  deleteCollection,
  updateCollection,
  listApiKeys,
  type CollectionSummary,
  type ApiKeySummary,
} from "@/lib/api";
import { useAuth } from "@/lib/auth";

export type FilterType =
  | { type: "all" }
  | {
      type: "collection";
      id: number;
      name: string;
      isPublic: boolean;
      publicToken: string | null;
    }
  | { type: "api_key"; key: string };

interface CollectionsSidebarProps {
  activeFilter: FilterType;
  onFilterChange: (filter: FilterType) => void;
  onCollectionChange?: () => void;
  collapsed?: boolean;
  onToggleCollapsed?: () => void;
}

export default function CollectionsSidebar({
  activeFilter,
  onFilterChange,
  onCollectionChange,
  collapsed = false,
  onToggleCollapsed,
}: CollectionsSidebarProps) {
  const { user } = useAuth();
  const [collections, setCollections] = useState<CollectionSummary[]>([]);
  const [apiKeys, setApiKeys] = useState<ApiKeySummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Section collapse state
  const [collectionsExpanded, setCollectionsExpanded] = useState(true);
  const [apiKeysExpanded, setApiKeysExpanded] = useState(true);

  // Create collection state
  const [isCreating, setIsCreating] = useState(false);
  const [newCollectionName, setNewCollectionName] = useState("");
  const [createLoading, setCreateLoading] = useState(false);

  // Edit collection state
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editName, setEditName] = useState("");
  const [editLoading, setEditLoading] = useState(false);

  // Delete confirmation state
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const [deleteLoading, setDeleteLoading] = useState(false);

  const loadData = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const [collectionsResponse, apiKeysResponse] = await Promise.all([
        listCollections(100, 0),
        listApiKeys(),
      ]);
      setCollections(collectionsResponse.collections);
      setApiKeys(apiKeysResponse.api_keys);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load data");
    } finally {
      setLoading(false);
    }
  }, []);

  // Filter API keys based on user permissions
  // Admin users can see all API keys, non-admin users only see their own
  const filteredApiKeys = useMemo(() => {
    if (!user) return [];
    if (user.isAdmin) return apiKeys;
    // Non-admin users only see their allowed API key
    if (user.allowedApiKey) {
      return apiKeys.filter((key) => key.api_key === user.allowedApiKey);
    }
    return [];
  }, [apiKeys, user]);

  // Group collections by creator
  const groupedCollections = useMemo(() => {
    const groups: Record<string, typeof collections> = {};
    for (const collection of collections) {
      const creator = collection.created_by || "Unknown";
      if (!groups[creator]) {
        groups[creator] = [];
      }
      groups[creator].push(collection);
    }
    // Sort groups: current user first, then alphabetically
    const currentUserId = user?.allowedApiKey || user?.name || "";
    const sortedEntries = Object.entries(groups).sort(([a], [b]) => {
      if (a === currentUserId) return -1;
      if (b === currentUserId) return 1;
      return a.localeCompare(b);
    });
    return sortedEntries;
  }, [collections, user]);

  // Track which creator groups are expanded
  const [expandedCreators, setExpandedCreators] = useState<Set<string>>(
    new Set(),
  );

  // Initialize expanded creators when collections load
  useEffect(() => {
    if (groupedCollections.length > 0 && expandedCreators.size === 0) {
      // Expand all groups by default, or just the current user's group
      const allCreators = new Set(
        groupedCollections.map(([creator]) => creator),
      );
      setExpandedCreators(allCreators);
    }
  }, [groupedCollections, expandedCreators.size]);

  const toggleCreatorExpanded = (creator: string) => {
    setExpandedCreators((prev) => {
      const next = new Set(prev);
      if (next.has(creator)) {
        next.delete(creator);
      } else {
        next.add(creator);
      }
      return next;
    });
  };

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleCreateCollection = async () => {
    const name = newCollectionName.trim();
    if (!name) return;

    try {
      setCreateLoading(true);
      const response = await createCollection(name);
      setCollections((prev) => [
        {
          ...response.collection,
          request_count: 0,
        },
        ...prev,
      ]);
      setNewCollectionName("");
      setIsCreating(false);
      onCollectionChange?.();
      // Auto-select the new collection
      onFilterChange({
        type: "collection",
        id: response.collection.id,
        name: response.collection.name,
        isPublic: response.collection.is_public,
        publicToken: response.collection.public_token,
      });
    } catch (err) {
      console.error("Failed to create collection:", err);
    } finally {
      setCreateLoading(false);
    }
  };

  const handleUpdateCollection = async (id: number) => {
    const name = editName.trim();
    if (!name) return;

    try {
      setEditLoading(true);
      const response = await updateCollection(id, name);
      setCollections((prev) =>
        prev.map((c) =>
          c.id === id
            ? {
                ...c,
                name: response.collection.name,
                updated_at: response.collection.updated_at,
              }
            : c,
        ),
      );
      setEditingId(null);
      setEditName("");
      onCollectionChange?.();
      // Update filter if this collection is active
      if (activeFilter.type === "collection" && activeFilter.id === id) {
        onFilterChange({
          type: "collection",
          id,
          name: response.collection.name,
          isPublic: response.collection.is_public,
          publicToken: response.collection.public_token,
        });
      }
    } catch (err) {
      console.error("Failed to update collection:", err);
    } finally {
      setEditLoading(false);
    }
  };

  const handleDeleteCollection = async (id: number) => {
    try {
      setDeleteLoading(true);
      await deleteCollection(id);
      setCollections((prev) => prev.filter((c) => c.id !== id));
      setDeletingId(null);
      // If deleted collection was selected, clear filter
      if (activeFilter.type === "collection" && activeFilter.id === id) {
        onFilterChange({ type: "all" });
      }
      onCollectionChange?.();
    } catch (err) {
      console.error("Failed to delete collection:", err);
    } finally {
      setDeleteLoading(false);
    }
  };

  const startEditing = (collection: CollectionSummary) => {
    setEditingId(collection.id);
    setEditName(collection.name);
    setDeletingId(null);
  };

  const cancelEditing = () => {
    setEditingId(null);
    setEditName("");
  };

  const isAllActive = activeFilter.type === "all";
  const isCollectionActive = (id: number) =>
    activeFilter.type === "collection" && activeFilter.id === id;
  const isApiKeyActive = (key: string) =>
    activeFilter.type === "api_key" && activeFilter.key === key;

  if (collapsed) {
    return (
      <div className="w-10 border-r border-border bg-muted/30 flex flex-col items-center py-2 gap-2">
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8"
              onClick={onToggleCollapsed}
            >
              <Layers className="h-4 w-4" />
            </Button>
          </TooltipTrigger>
          <TooltipContent side="right">
            <p className="text-xs">Expand Filters</p>
          </TooltipContent>
        </Tooltip>
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant={isAllActive ? "secondary" : "ghost"}
              size="icon"
              className="h-8 w-8"
              onClick={() => onFilterChange({ type: "all" })}
            >
              <span className="text-xs font-medium">All</span>
            </Button>
          </TooltipTrigger>
          <TooltipContent side="right">
            <p className="text-xs">All Requests</p>
          </TooltipContent>
        </Tooltip>
        {collections.slice(0, 3).map((collection) => (
          <Tooltip key={collection.id}>
            <TooltipTrigger asChild>
              <Button
                variant={
                  isCollectionActive(collection.id) ? "secondary" : "ghost"
                }
                size="icon"
                className="h-8 w-8"
                onClick={() =>
                  onFilterChange({
                    type: "collection",
                    id: collection.id,
                    name: collection.name,
                    isPublic: collection.is_public,
                    publicToken: collection.public_token,
                  })
                }
              >
                <span className="text-xs font-medium">
                  {collection.name.charAt(0).toUpperCase()}
                </span>
              </Button>
            </TooltipTrigger>
            <TooltipContent side="right">
              <p className="text-xs">{collection.name}</p>
              <p className="text-2xs text-muted-foreground">
                {collection.request_count ?? 0} requests
              </p>
            </TooltipContent>
          </Tooltip>
        ))}
      </div>
    );
  }

  return (
    <div className="w-56 border-r border-border bg-muted/30 flex flex-col h-full">
      {/* Header */}
      <div className="px-3 py-2 border-b border-border/50 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Layers className="h-4 w-4 text-muted-foreground" />
          <span className="text-sm font-medium">Filters</span>
        </div>
        {onToggleCollapsed && (
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="ghost"
                size="icon"
                className="h-6 w-6"
                onClick={onToggleCollapsed}
              >
                <ChevronRight className="h-3.5 w-3.5" />
              </Button>
            </TooltipTrigger>
            <TooltipContent>
              <p className="text-xs">Collapse</p>
            </TooltipContent>
          </Tooltip>
        )}
      </div>

      {/* "All Requests" option */}
      <div className="px-2 py-1 border-b border-border/50">
        <button
          onClick={() => onFilterChange({ type: "all" })}
          className={cn(
            "w-full flex items-center gap-2 px-2 py-1.5 rounded text-left text-xs transition-colors",
            isAllActive
              ? "bg-primary/10 text-primary"
              : "hover:bg-muted text-muted-foreground hover:text-foreground",
          )}
        >
          <Layers className="h-3.5 w-3.5 shrink-0" />
          <span className="flex-1 truncate font-medium">All Requests</span>
        </button>
      </div>

      {/* Scrollable content */}
      <div className="flex-1 overflow-y-auto">
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
        ) : (
          <>
            {/* Collections Section */}
            <div className="border-b border-border/50">
              <div className="flex items-center gap-1 px-3 py-2">
                <button
                  onClick={() => setCollectionsExpanded(!collectionsExpanded)}
                  className="flex-1 flex items-center gap-2 text-xs font-medium text-muted-foreground hover:text-foreground transition-colors"
                >
                  {collectionsExpanded ? (
                    <ChevronDown className="h-3 w-3" />
                  ) : (
                    <ChevronRight className="h-3 w-3" />
                  )}
                  <FolderOpen className="h-3.5 w-3.5" />
                  <span className="flex-1 text-left">Collections</span>
                  <Badge variant="secondary" className="h-4 px-1 text-2xs">
                    {collections.length}
                  </Badge>
                </button>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <button
                      onClick={() => {
                        setIsCreating(true);
                        setCollectionsExpanded(true);
                      }}
                      className="p-1 hover:bg-muted rounded text-muted-foreground hover:text-foreground transition-colors"
                    >
                      <Plus className="h-3 w-3" />
                    </button>
                  </TooltipTrigger>
                  <TooltipContent>
                    <p className="text-xs">New Collection</p>
                  </TooltipContent>
                </Tooltip>
              </div>

              {collectionsExpanded && (
                <div className="px-2 pb-2">
                  {/* Create Collection Input */}
                  {isCreating && (
                    <div className="flex items-center gap-1 mb-1">
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
                        className="flex-1 h-6 px-2 text-xs bg-background border border-border rounded focus:outline-none focus:ring-1 focus:ring-primary"
                        autoFocus
                        disabled={createLoading}
                      />
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-6 w-6 shrink-0"
                        onClick={handleCreateCollection}
                        disabled={createLoading || !newCollectionName.trim()}
                      >
                        {createLoading ? (
                          <Loader2 className="h-3 w-3 animate-spin" />
                        ) : (
                          <Check className="h-3 w-3 text-green-500" />
                        )}
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-6 w-6 shrink-0"
                        onClick={() => {
                          setIsCreating(false);
                          setNewCollectionName("");
                        }}
                        disabled={createLoading}
                      >
                        <X className="h-3 w-3" />
                      </Button>
                    </div>
                  )}

                  {collections.length === 0 && !isCreating ? (
                    <div className="text-center py-3 text-muted-foreground">
                      <FolderPlus className="h-6 w-6 mx-auto mb-1 opacity-50" />
                      <p className="text-2xs">No collections</p>
                    </div>
                  ) : (
                    <div className="space-y-1">
                      {groupedCollections.map(
                        ([creator, creatorCollections]) => {
                          const isCurrentUser =
                            creator === (user?.allowedApiKey || user?.name);
                          const isExpanded = expandedCreators.has(creator);
                          const displayName = isCurrentUser
                            ? "My Collections"
                            : creator.length > 20
                              ? `${creator.slice(0, 20)}...`
                              : creator;

                          return (
                            <div key={creator} className="space-y-0.5">
                              {/* Creator group header */}
                              <button
                                onClick={() => toggleCreatorExpanded(creator)}
                                className="w-full flex items-center gap-1.5 px-1 py-1 text-2xs font-medium text-muted-foreground hover:text-foreground transition-colors rounded hover:bg-muted/50"
                              >
                                {isExpanded ? (
                                  <ChevronDown className="h-2.5 w-2.5" />
                                ) : (
                                  <ChevronRight className="h-2.5 w-2.5" />
                                )}
                                <User className="h-3 w-3" />
                                <span className="flex-1 text-left truncate">
                                  {displayName}
                                </span>
                                <Badge
                                  variant="outline"
                                  className="h-3.5 px-1 text-2xs"
                                >
                                  {creatorCollections.length}
                                </Badge>
                              </button>

                              {/* Collections in this group */}
                              {isExpanded && (
                                <div className="pl-3 space-y-0.5">
                                  {creatorCollections.map((collection) => (
                                    <div key={collection.id} className="group">
                                      {editingId === collection.id ? (
                                        <div className="flex items-center gap-1 py-0.5">
                                          <input
                                            type="text"
                                            value={editName}
                                            onChange={(e) =>
                                              setEditName(e.target.value)
                                            }
                                            onKeyDown={(e) => {
                                              if (e.key === "Enter")
                                                handleUpdateCollection(
                                                  collection.id,
                                                );
                                              if (e.key === "Escape")
                                                cancelEditing();
                                            }}
                                            className="flex-1 h-6 px-2 text-xs bg-background border border-border rounded focus:outline-none focus:ring-1 focus:ring-primary"
                                            autoFocus
                                            disabled={editLoading}
                                          />
                                          <Button
                                            variant="ghost"
                                            size="icon"
                                            className="h-6 w-6 shrink-0"
                                            onClick={() =>
                                              handleUpdateCollection(
                                                collection.id,
                                              )
                                            }
                                            disabled={
                                              editLoading || !editName.trim()
                                            }
                                          >
                                            {editLoading ? (
                                              <Loader2 className="h-3 w-3 animate-spin" />
                                            ) : (
                                              <Check className="h-3 w-3 text-green-500" />
                                            )}
                                          </Button>
                                          <Button
                                            variant="ghost"
                                            size="icon"
                                            className="h-6 w-6 shrink-0"
                                            onClick={cancelEditing}
                                            disabled={editLoading}
                                          >
                                            <X className="h-3 w-3" />
                                          </Button>
                                        </div>
                                      ) : deletingId === collection.id ? (
                                        <div className="flex items-center gap-1 py-0.5 px-2 bg-destructive/10 rounded">
                                          <span className="flex-1 text-xs text-destructive truncate">
                                            Delete?
                                          </span>
                                          <Button
                                            variant="ghost"
                                            size="icon"
                                            className="h-6 w-6 shrink-0"
                                            onClick={() =>
                                              handleDeleteCollection(
                                                collection.id,
                                              )
                                            }
                                            disabled={deleteLoading}
                                          >
                                            {deleteLoading ? (
                                              <Loader2 className="h-3 w-3 animate-spin" />
                                            ) : (
                                              <Check className="h-3 w-3 text-destructive" />
                                            )}
                                          </Button>
                                          <Button
                                            variant="ghost"
                                            size="icon"
                                            className="h-6 w-6 shrink-0"
                                            onClick={() => setDeletingId(null)}
                                            disabled={deleteLoading}
                                          >
                                            <X className="h-3 w-3" />
                                          </Button>
                                        </div>
                                      ) : (
                                        <div
                                          className={cn(
                                            "w-full flex items-center gap-2 px-2 py-1.5 rounded text-left text-xs transition-colors cursor-pointer",
                                            isCollectionActive(collection.id)
                                              ? "bg-primary/10 text-primary"
                                              : "hover:bg-muted text-muted-foreground hover:text-foreground",
                                          )}
                                          onClick={() =>
                                            onFilterChange({
                                              type: "collection",
                                              id: collection.id,
                                              name: collection.name,
                                              isPublic: collection.is_public,
                                              publicToken:
                                                collection.public_token,
                                            })
                                          }
                                        >
                                          <FolderOpen className="h-3.5 w-3.5 shrink-0" />
                                          <span className="flex-1 truncate">
                                            {collection.name}
                                          </span>
                                          <Badge
                                            variant="secondary"
                                            className="h-4 px-1 text-2xs shrink-0"
                                          >
                                            {collection.request_count ?? 0}
                                          </Badge>
                                          <div className="hidden group-hover:flex items-center gap-0.5 shrink-0">
                                            <button
                                              onClick={(e) => {
                                                e.stopPropagation();
                                                startEditing(collection);
                                              }}
                                              className="p-0.5 hover:bg-muted rounded"
                                            >
                                              <Edit2 className="h-2.5 w-2.5" />
                                            </button>
                                            <button
                                              onClick={(e) => {
                                                e.stopPropagation();
                                                setDeletingId(collection.id);
                                              }}
                                              className="p-0.5 hover:bg-destructive/10 hover:text-destructive rounded"
                                            >
                                              <Trash2 className="h-2.5 w-2.5" />
                                            </button>
                                          </div>
                                        </div>
                                      )}
                                    </div>
                                  ))}
                                </div>
                              )}
                            </div>
                          );
                        },
                      )}
                    </div>
                  )}
                </div>
              )}
            </div>

            {/* API Keys Section */}
            <div>
              <button
                onClick={() => setApiKeysExpanded(!apiKeysExpanded)}
                className="w-full flex items-center gap-2 px-3 py-2 text-xs font-medium text-muted-foreground hover:text-foreground transition-colors"
              >
                {apiKeysExpanded ? (
                  <ChevronDown className="h-3 w-3" />
                ) : (
                  <ChevronRight className="h-3 w-3" />
                )}
                <Key className="h-3.5 w-3.5" />
                <span className="flex-1 text-left">By API Key</span>
                <Badge variant="secondary" className="h-4 px-1 text-2xs">
                  {apiKeys.length}
                </Badge>
              </button>

              {apiKeysExpanded && (
                <div className="px-2 pb-2">
                  {filteredApiKeys.length === 0 ? (
                    <div className="text-center py-3 text-muted-foreground">
                      <Key className="h-6 w-6 mx-auto mb-1 opacity-50" />
                      <p className="text-2xs">No API keys found</p>
                    </div>
                  ) : (
                    <div className="space-y-0.5">
                      {filteredApiKeys.map((apiKey) => (
                        <Tooltip key={apiKey.api_key}>
                          <TooltipTrigger asChild>
                            <button
                              onClick={() =>
                                onFilterChange({
                                  type: "api_key",
                                  key: apiKey.api_key,
                                })
                              }
                              className={cn(
                                "w-full flex items-center gap-2 px-2 py-1.5 rounded text-left text-xs transition-colors",
                                isApiKeyActive(apiKey.api_key)
                                  ? "bg-primary/10 text-primary"
                                  : "hover:bg-muted text-muted-foreground hover:text-foreground",
                              )}
                            >
                              <Key className="h-3.5 w-3.5 shrink-0" />
                              <span className="flex-1 truncate font-mono">
                                {truncateId(apiKey.api_key, 12)}
                              </span>
                              <Badge
                                variant="secondary"
                                className="h-4 px-1 text-2xs shrink-0"
                              >
                                {apiKey.request_count}
                              </Badge>
                            </button>
                          </TooltipTrigger>
                          <TooltipContent side="right">
                            <p className="font-mono text-xs">
                              {apiKey.api_key}
                            </p>
                            <p className="text-2xs text-muted-foreground">
                              {apiKey.request_count} requests
                            </p>
                            <p className="text-2xs text-muted-foreground">
                              Latest:{" "}
                              {formatRelativeTime(apiKey.latest_request_at)}
                            </p>
                          </TooltipContent>
                        </Tooltip>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
