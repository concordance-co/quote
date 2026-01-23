import { useState, useEffect, useCallback } from "react";
import { Link } from "react-router-dom";
import {
  ChevronRight,
  ChevronDown,
  Loader2,
  RefreshCw,
  Search,
  FileText,
  Circle,
  MessagesSquare,
  CheckCheck,
  Code,
  Palette,
  FolderPlus,
  X,
  Square,
  CheckSquare,
  Minus,
  Wifi,
  WifiOff,
  Star,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn, formatRelativeTime, truncateId } from "@/lib/utils";
import {
  fetchLogs,
  addFavorite,
  removeFavorite,
  listCollections,
  createCollection,
  addRequestToCollection,
  removeRequestFromCollection,
  getRequestCollections,
  type CollectionSummary,
} from "@/lib/api";
import type { LogSummary, ListLogsResponse } from "@/types/api";
import { useReadDiscussions } from "@/hooks/useReadDiscussions";
import { useLogStream } from "@/hooks/useLogStream";
import {
  InlineTokenSequence,
  type TokenColorMode,
} from "@/components/TokenSequence";
import CollectionHeader from "@/components/CollectionHeader";
import { useAuth } from "@/lib/auth";

const ITEMS_PER_PAGE = 45;

const STAR_LABELS = ["T", "M", "B"] as const;
type StarLabel = (typeof STAR_LABELS)[number];

const STAR_COLORS: Record<StarLabel, { active: string; inactive: string }> = {
  T: {
    active: "bg-amber-500 text-amber-950 border-amber-400",
    inactive:
      "bg-transparent text-muted-foreground border-muted-foreground/30 hover:border-amber-500/50 hover:text-amber-500",
  },
  M: {
    active: "bg-emerald-500 text-emerald-950 border-emerald-400",
    inactive:
      "bg-transparent text-muted-foreground border-muted-foreground/30 hover:border-emerald-500/50 hover:text-emerald-500",
  },
  B: {
    active: "bg-blue-500 text-blue-950 border-blue-400",
    inactive:
      "bg-transparent text-muted-foreground border-muted-foreground/30 hover:border-blue-500/50 hover:text-blue-500",
  },
};

export interface LogsListProps {
  collectionId?: number;
  collectionName?: string;
  collectionIsPublic?: boolean;
  collectionPublicToken?: string | null;
  apiKey?: string;
  /** When true, disables all editing features (favorites, selection, etc.) */
  readOnly?: boolean;
  /** Pre-loaded logs data (used for public view) */
  initialLogs?: LogSummary[];
  /** Total count when using initialLogs */
  initialTotal?: number;
  /** Hide the collection header */
  hideCollectionHeader?: boolean;
  /** Public collection token for constructing request links in public collection view */
  publicCollectionToken?: string;
  /** Callback when collection public status changes */
  onPublicStatusChange?: (
    isPublic: boolean,
    publicToken: string | null,
  ) => void;
}

export default function LogsList({
  collectionId,
  collectionName,
  collectionIsPublic,
  collectionPublicToken,
  apiKey,
  readOnly = false,
  initialLogs,
  hideCollectionHeader = false,
  publicCollectionToken,
  onPublicStatusChange,
}: LogsListProps = {}) {
  const { user, apiKey: authApiKey } = useAuth();
  const isAdmin = user?.isAdmin ?? false;
  const [logs, setLogs] = useState<LogSummary[]>(initialLogs || []);
  const [loading, setLoading] = useState(!initialLogs);
  const [error, setError] = useState<string | null>(null);
  const [offset, setOffset] = useState(0);
  const [hasMore, setHasMore] = useState(true);
  const [searchQuery, setSearchQuery] = useState("");
  const [refreshing, setRefreshing] = useState(false);
  const [activeFilters, setActiveFilters] = useState<Set<StarLabel>>(new Set());
  // Non-admin filter: "all", "favorites", or a model name
  const [nonAdminFilter, setNonAdminFilter] = useState<string>("all");
  const { markAllAsRead, hasUnread, getUnreadCount } = useReadDiscussions();
  const [expandedRows, setExpandedRows] = useState<Set<string>>(new Set());
  const [tokenColorMode, setTokenColorMode] =
    useState<TokenColorMode>("flatness");

  // Selection state
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());

  // SSE stream for real-time updates
  const handleNewLog = useCallback(
    (newLog: LogSummary) => {
      // Only add if viewing all logs (no collection/apiKey filter)
      // or if the log matches the current filter
      if (collectionId !== undefined || apiKey !== undefined) {
        // When filtering, we can't know if the new log matches without checking
        // So we skip auto-adding and user can refresh
        return;
      }

      setLogs((prev) => {
        // Check if log already exists (avoid duplicates)
        if (prev.some((l) => l.request_id === newLog.request_id)) {
          return prev;
        }
        // Prepend new log to the list
        return [newLog, ...prev];
      });
    },
    [collectionId, apiKey],
  );

  const { isConnected: sseConnected } = useLogStream({
    enabled: !readOnly,
    apiKey: authApiKey,
    onNewLog: handleNewLog,
    onLagged: (_missed) => {
      // Lagged events are handled by the useLogStream hook
    },
  });
  const [lastSelectedId, setLastSelectedId] = useState<string | null>(null);

  // Context menu state
  const [contextMenu, setContextMenu] = useState<{
    x: number;
    y: number;
    requestId: string;
  } | null>(null);

  // Add to collection modal state
  const [showAddToCollection, setShowAddToCollection] = useState(false);
  const [collections, setCollections] = useState<CollectionSummary[]>([]);
  const [collectionsLoading, setCollectionsLoading] = useState(false);
  const [addingToCollection, setAddingToCollection] = useState<number | null>(
    null,
  );
  const [newCollectionName, setNewCollectionName] = useState("");
  const [creatingCollection, setCreatingCollection] = useState(false);

  // Favorites collection for non-admin users (single star functionality)
  const [favoritesCollectionId, setFavoritesCollectionId] = useState<
    number | null
  >(null);
  const [favoritedRequestIds, setFavoritedRequestIds] = useState<Set<string>>(
    new Set(),
  );
  const [togglingFavorite, setTogglingFavorite] = useState<string | null>(null);

  // Find or create the "Favorites" collection for non-admin users
  useEffect(() => {
    if (isAdmin || readOnly) return;

    const initFavoritesCollection = async () => {
      try {
        const response = await listCollections(100, 0);
        const existing = response.collections.find(
          (c) => c.name === "Favorites",
        );

        if (existing) {
          setFavoritesCollectionId(existing.id);
        } else {
          // Create the Favorites collection
          const createResponse = await createCollection(
            "Favorites",
            "Your favorited requests",
          );
          setFavoritesCollectionId(createResponse.collection.id);
        }
      } catch (err) {
        console.error("Failed to initialize favorites collection:", err);
      }
    };

    initFavoritesCollection();
  }, [isAdmin, readOnly]);

  // Track which visible logs are in the favorites collection
  useEffect(() => {
    if (isAdmin || readOnly || !favoritesCollectionId || logs.length === 0)
      return;

    const checkFavorites = async () => {
      // Check each log's collections to see if it's in favorites
      const favorited = new Set<string>();
      for (const log of logs) {
        try {
          const response = await getRequestCollections(log.request_id);
          if (
            response.collections.some((c) => c.id === favoritesCollectionId)
          ) {
            favorited.add(log.request_id);
          }
        } catch {
          // Ignore errors for individual requests
        }
      }
      setFavoritedRequestIds(favorited);
    };

    checkFavorites();
  }, [isAdmin, readOnly, favoritesCollectionId, logs]);

  const handleToggleSimpleFavorite = useCallback(
    async (requestId: string) => {
      if (!favoritesCollectionId) return;

      const isCurrentlyFavorited = favoritedRequestIds.has(requestId);

      try {
        setTogglingFavorite(requestId);

        if (isCurrentlyFavorited) {
          await removeRequestFromCollection(favoritesCollectionId, requestId);
          setFavoritedRequestIds((prev) => {
            const next = new Set(prev);
            next.delete(requestId);
            return next;
          });
        } else {
          await addRequestToCollection(favoritesCollectionId, requestId);
          setFavoritedRequestIds((prev) => new Set(prev).add(requestId));
        }
      } catch (err) {
        console.error("Failed to toggle favorite:", err);
      } finally {
        setTogglingFavorite(null);
      }
    },
    [favoritesCollectionId, favoritedRequestIds],
  );

  const toggleRowExpanded = useCallback((requestId: string) => {
    setExpandedRows((prev) => {
      const next = new Set(prev);
      if (next.has(requestId)) {
        next.delete(requestId);
      } else {
        next.add(requestId);
      }
      return next;
    });
  }, []);

  const loadLogs = useCallback(
    async (reset = false) => {
      try {
        if (reset) {
          setLoading(true);
          setOffset(0);
        }
        const newOffset = reset ? 0 : offset;
        const response: ListLogsResponse = await fetchLogs(
          ITEMS_PER_PAGE,
          newOffset,
          { collectionId, apiKey },
        );

        if (reset) {
          setLogs(response.data);
          // Clear selection when logs change
          setSelectedIds(new Set());
          setLastSelectedId(null);
        } else {
          setLogs((prev) => [...prev, ...response.data]);
        }

        setHasMore(response.returned === ITEMS_PER_PAGE);
        setError(null);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load logs");
      } finally {
        setLoading(false);
        setRefreshing(false);
      }
    },
    [offset, collectionId, apiKey],
  );

  // Load logs on mount and when filters change
  // Skip if initialLogs is provided (public view uses pre-loaded data)
  useEffect(() => {
    if (!initialLogs) {
      loadLogs(true);
    }
  }, [collectionId, apiKey, initialLogs]);

  const handleRefresh = () => {
    setRefreshing(true);
    loadLogs(true);
  };

  const handleLoadMore = () => {
    setOffset((prev) => prev + ITEMS_PER_PAGE);
  };

  useEffect(() => {
    if (offset > 0) {
      loadLogs(false);
    }
  }, [offset]);

  const handleToggleFavorite = useCallback(
    async (requestId: string, label: StarLabel, isCurrentlyActive: boolean) => {
      try {
        if (isCurrentlyActive) {
          const response = await removeFavorite(requestId, label);
          setLogs((prev) =>
            prev.map((log) =>
              log.request_id === requestId
                ? { ...log, favorited_by: response.favorited_by }
                : log,
            ),
          );
        } else {
          const response = await addFavorite(requestId, label);
          setLogs((prev) =>
            prev.map((log) =>
              log.request_id === requestId
                ? { ...log, favorited_by: response.favorited_by }
                : log,
            ),
          );
        }
      } catch (err) {
        console.error("Failed to update favorite:", err);
      }
    },
    [],
  );

  const toggleFilter = (label: StarLabel) => {
    setActiveFilters((prev) => {
      const next = new Set(prev);
      if (next.has(label)) {
        next.delete(label);
      } else {
        next.add(label);
      }
      return next;
    });
  };

  const handleMarkAllAsRead = () => {
    markAllAsRead(
      logs.map((log) => ({
        requestId: log.request_id,
        discussionCount: log.discussion_count,
      })),
    );
  };

  // Selection handlers
  const handleRowSelect = useCallback(
    (requestId: string, event: React.MouseEvent) => {
      event.preventDefault();
      event.stopPropagation();

      const isShiftKey = event.shiftKey;
      const isMetaKey = event.metaKey || event.ctrlKey;

      setSelectedIds((prev) => {
        const next = new Set(prev);

        if (isShiftKey && lastSelectedId) {
          // Range selection
          const currentIndex = filteredLogs.findIndex(
            (l) => l.request_id === requestId,
          );
          const lastIndex = filteredLogs.findIndex(
            (l) => l.request_id === lastSelectedId,
          );

          if (currentIndex !== -1 && lastIndex !== -1) {
            const start = Math.min(currentIndex, lastIndex);
            const end = Math.max(currentIndex, lastIndex);

            for (let i = start; i <= end; i++) {
              next.add(filteredLogs[i].request_id);
            }
          }
        } else if (isMetaKey) {
          // Toggle individual selection
          if (next.has(requestId)) {
            next.delete(requestId);
          } else {
            next.add(requestId);
          }
        } else {
          // Single selection (replace)
          next.clear();
          next.add(requestId);
        }

        return next;
      });

      setLastSelectedId(requestId);
    },
    [lastSelectedId],
  );

  const handleSelectAll = useCallback(() => {
    if (selectedIds.size === filteredLogs.length) {
      // Deselect all
      setSelectedIds(new Set());
    } else {
      // Select all
      setSelectedIds(new Set(filteredLogs.map((l) => l.request_id)));
    }
  }, [selectedIds.size]);

  const handleClearSelection = useCallback(() => {
    setSelectedIds(new Set());
    setLastSelectedId(null);
  }, []);

  // Context menu handlers
  const handleContextMenu = useCallback(
    (event: React.MouseEvent, requestId: string) => {
      event.preventDefault();

      // If right-clicking on an unselected row, select it
      if (!selectedIds.has(requestId)) {
        setSelectedIds(new Set([requestId]));
        setLastSelectedId(requestId);
      }

      setContextMenu({
        x: event.clientX,
        y: event.clientY,
        requestId,
      });
    },
    [selectedIds],
  );

  // Close context menu when clicking outside
  useEffect(() => {
    const handleClick = () => setContextMenu(null);
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setContextMenu(null);
        handleClearSelection();
      }
    };

    document.addEventListener("click", handleClick);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("click", handleClick);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [handleClearSelection]);

  // Add to collection handlers
  const handleOpenAddToCollection = useCallback(async () => {
    setShowAddToCollection(true);
    setContextMenu(null);
    setCollectionsLoading(true);
    try {
      const response = await listCollections(100, 0);
      setCollections(response.collections);
    } catch (err) {
      console.error("Failed to load collections:", err);
    } finally {
      setCollectionsLoading(false);
    }
  }, []);

  const handleAddToCollection = useCallback(
    async (collectionId: number) => {
      const requestIds = Array.from(selectedIds);
      if (requestIds.length === 0) return;

      setAddingToCollection(collectionId);
      try {
        // Add all selected requests to the collection
        await Promise.all(
          requestIds.map((requestId) =>
            addRequestToCollection(collectionId, requestId),
          ),
        );
        setShowAddToCollection(false);
        handleClearSelection();
      } catch (err) {
        console.error("Failed to add to collection:", err);
      } finally {
        setAddingToCollection(null);
      }
    },
    [selectedIds, handleClearSelection],
  );

  const handleCreateAndAddToCollection = useCallback(async () => {
    const name = newCollectionName.trim();
    if (!name || selectedIds.size === 0) return;

    setCreatingCollection(true);
    try {
      const response = await createCollection(name);
      const newCollectionId = response.collection.id;

      // Add all selected requests to the new collection
      const requestIds = Array.from(selectedIds);
      await Promise.all(
        requestIds.map((requestId) =>
          addRequestToCollection(newCollectionId, requestId),
        ),
      );

      setShowAddToCollection(false);
      setNewCollectionName("");
      handleClearSelection();
    } catch (err) {
      console.error("Failed to create collection:", err);
    } finally {
      setCreatingCollection(false);
    }
  }, [newCollectionName, selectedIds, handleClearSelection]);

  // Count logs with unread discussions
  const unreadCount = logs.filter((log) =>
    hasUnread(log.request_id, log.discussion_count),
  ).length;

  // Get unique models for filter dropdown
  const uniqueModelsList = Array.from(
    new Set(logs.map((l) => l.model_id).filter(Boolean)),
  ).sort() as string[];

  const filteredLogs = logs.filter((log) => {
    // Apply star filters (admin only)
    if (isAdmin && activeFilters.size > 0) {
      const hasMatchingStar = Array.from(activeFilters).some((label) =>
        log.favorited_by.includes(label),
      );
      if (!hasMatchingStar) return false;
    }

    // Apply non-admin filter
    if (!isAdmin && nonAdminFilter !== "all") {
      if (nonAdminFilter === "favorites") {
        if (!favoritedRequestIds.has(log.request_id)) return false;
      } else {
        // Filter by model
        if (log.model_id !== nonAdminFilter) return false;
      }
    }

    // Apply search filter
    if (!searchQuery) return true;
    const query = searchQuery.toLowerCase();
    return (
      log.request_id.toLowerCase().includes(query) ||
      log.model_id?.toLowerCase().includes(query) ||
      log.user_api_key?.toLowerCase().includes(query) ||
      log.final_text?.toLowerCase().includes(query)
    );
  });

  // Stats
  const uniqueModels = new Set(logs.map((l) => l.model_id).filter(Boolean))
    .size;
  const avgSteps =
    logs.length > 0
      ? Math.round(
          logs.reduce((sum, l) => sum + l.total_steps, 0) / logs.length,
        )
      : 0;

  // Selection state
  const hasSelection = selectedIds.size > 0;
  const allSelected =
    filteredLogs.length > 0 && selectedIds.size === filteredLogs.length;
  const someSelected = hasSelection && !allSelected;

  if (loading && logs.length === 0) {
    return <LogsListSkeleton />;
  }

  if (error && logs.length === 0) {
    return (
      <div className="panel">
        <div className="flex flex-col items-center justify-center py-8 text-center">
          <FileText className="h-5 w-5 text-destructive mb-2" />
          <p className="text-sm font-medium mb-1">Failed to load logs</p>
          <p className="text-xs text-muted-foreground mb-3">{error}</p>
          <Button size="sm" onClick={() => loadLogs(true)}>
            Try Again
          </Button>
        </div>
      </div>
    );
  }

  // Use provided collection name or fallback to generic name
  const displayCollectionName =
    collectionName || (collectionId ? `Collection ${collectionId}` : "");

  return (
    <div className="h-full flex flex-col overflow-hidden">
      {/* Collection Header (when viewing a collection) */}
      {collectionId !== undefined && !hideCollectionHeader && !readOnly && (
        <CollectionHeader
          collectionId={collectionId}
          collectionName={displayCollectionName}
          isPublic={collectionIsPublic}
          publicToken={collectionPublicToken}
          onPublicStatusChange={onPublicStatusChange}
        />
      )}

      <div className="flex flex-col gap-3 flex-1 pt-3 min-h-0 overflow-hidden">
        {/* Selection Toolbar - admin only */}
        {hasSelection && !readOnly && isAdmin && (
          <div className="flex items-center justify-between gap-4 px-3 py-2 bg-primary/10 border border-primary/20 rounded-md">
            <div className="flex items-center gap-3">
              <span className="text-sm font-medium">
                {selectedIds.size} selected
              </span>
              <Button
                variant="ghost"
                size="sm"
                className="h-7 text-xs"
                onClick={handleClearSelection}
              >
                <X className="h-3 w-3 mr-1" />
                Clear
              </Button>
            </div>
            <div className="flex items-center gap-2">
              <Button
                variant="default"
                size="sm"
                className="h-7 text-xs gap-1.5"
                onClick={handleOpenAddToCollection}
              >
                <FolderPlus className="h-3.5 w-3.5" />
                Add to Collection
              </Button>
            </div>
          </div>
        )}

        {/* Header Row */}
        <div className="flex items-center justify-between gap-4">
          <div className="flex items-center gap-4">
            <h1 className="text-lg font-semibold">Requests</h1>
            {isAdmin ? (
              <div className="stats-row text-muted-foreground">
                <span>
                  <span className="stat-value text-foreground">
                    {logs.length}
                  </span>{" "}
                  loaded
                </span>
                <span className="text-border">•</span>
                <span>
                  <span className="stat-value text-foreground">
                    {uniqueModels}
                  </span>{" "}
                  models
                </span>
                <span className="text-border">•</span>
                <span>
                  avg{" "}
                  <span className="stat-value text-foreground">{avgSteps}</span>{" "}
                  steps
                </span>
              </div>
            ) : (
              <span className="text-xs text-muted-foreground">
                {filteredLogs.length}{" "}
                {nonAdminFilter !== "all" ? "filtered" : "requests"}
              </span>
            )}
          </div>
          <div className="flex items-center gap-2">
            {/* Token Color Mode Selector - admin only */}
            {isAdmin && (
              <Tooltip>
                <TooltipTrigger asChild>
                  <div className="flex items-center gap-1">
                    <Palette className="h-3 w-3 text-muted-foreground" />
                    <select
                      value={tokenColorMode}
                      onChange={(e) =>
                        setTokenColorMode(e.target.value as TokenColorMode)
                      }
                      className="h-6 text-2xs bg-muted border-0 rounded px-2 text-foreground"
                    >
                      <option value="flatness">Flatness</option>
                      <option value="branchiness">Branchiness</option>
                      <option value="probability">Probability</option>
                      <option value="entropy">Entropy</option>
                    </select>
                  </div>
                </TooltipTrigger>
                <TooltipContent className="text-2xs max-w-xs">
                  <p>Token preview border color mode</p>
                </TooltipContent>
              </Tooltip>
            )}

            {/* Star Filters - only for admin users */}
            {isAdmin ? (
              <div className="flex items-center gap-1">
                {STAR_LABELS.map((label) => (
                  <Tooltip key={label}>
                    <TooltipTrigger asChild>
                      <button
                        onClick={() => toggleFilter(label)}
                        className={cn(
                          "w-6 h-6 rounded-md border text-xs font-bold transition-colors flex items-center justify-center",
                          activeFilters.has(label)
                            ? STAR_COLORS[label].active
                            : STAR_COLORS[label].inactive,
                        )}
                      >
                        {label}
                      </button>
                    </TooltipTrigger>
                    <TooltipContent>
                      <p className="text-2xs">
                        {activeFilters.has(label)
                          ? `Showing ${label} starred`
                          : `Filter by ${label} star`}
                      </p>
                    </TooltipContent>
                  </Tooltip>
                ))}
                {activeFilters.size > 0 && (
                  <button
                    onClick={() => setActiveFilters(new Set())}
                    className="text-2xs text-muted-foreground hover:text-foreground ml-1"
                  >
                    Clear
                  </button>
                )}
              </div>
            ) : (
              // Non-admin users: filter by favorites or model
              <div className="flex items-center gap-1">
                <select
                  value={nonAdminFilter}
                  onChange={(e) => setNonAdminFilter(e.target.value)}
                  className="h-6 text-2xs bg-muted border-0 rounded px-2 text-foreground"
                >
                  <option value="all">All</option>
                  <option value="favorites">Favorites</option>
                  {uniqueModelsList.length > 0 && (
                    <optgroup label="Model">
                      {uniqueModelsList.map((model) => (
                        <option key={model} value={model}>
                          {model.length > 25
                            ? model.slice(0, 25) + "..."
                            : model}
                        </option>
                      ))}
                    </optgroup>
                  )}
                </select>
                {nonAdminFilter !== "all" && (
                  <button
                    onClick={() => setNonAdminFilter("all")}
                    className="text-2xs text-muted-foreground hover:text-foreground"
                  >
                    ×
                  </button>
                )}
              </div>
            )}
            <div className="relative">
              <Search className="absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
              <input
                type="text"
                placeholder="Search..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="h-7 w-[200px] rounded border border-input bg-background pl-7 pr-2 text-xs ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
              />
            </div>
            {/* SSE Connection Status - hide in read-only mode */}
            {!readOnly && (
              <Tooltip>
                <TooltipTrigger asChild>
                  <div
                    className={cn(
                      "flex items-center gap-1 px-2 h-7 rounded-md border text-xs",
                      sseConnected
                        ? "border-green-500/30 text-green-600 bg-green-500/5"
                        : "border-muted-foreground/30 text-muted-foreground bg-muted/30",
                    )}
                  >
                    {sseConnected ? (
                      <Wifi className="h-3 w-3" />
                    ) : (
                      <WifiOff className="h-3 w-3" />
                    )}
                    <span className="hidden sm:inline">
                      {sseConnected ? "Live" : "Offline"}
                    </span>
                  </div>
                </TooltipTrigger>
                <TooltipContent>
                  <p className="text-2xs">
                    {sseConnected
                      ? "Connected - new logs appear automatically"
                      : "Disconnected - refresh manually for updates"}
                  </p>
                </TooltipContent>
              </Tooltip>
            )}
            {!readOnly && (
              <Button
                variant="outline"
                size="sm"
                className="h-7 w-7 p-0"
                onClick={handleRefresh}
                disabled={refreshing}
              >
                <RefreshCw
                  className={cn("h-3.5 w-3.5", refreshing && "animate-spin")}
                />
              </Button>
            )}
            {unreadCount > 0 && !readOnly && (
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    variant="outline"
                    size="sm"
                    className="h-7 gap-1.5 text-xs"
                    onClick={handleMarkAllAsRead}
                  >
                    <CheckCheck className="h-3.5 w-3.5" />
                    Mark all read
                  </Button>
                </TooltipTrigger>
                <TooltipContent>
                  <p className="text-2xs">
                    {unreadCount} request{unreadCount !== 1 ? "s" : ""} with
                    unread discussions
                  </p>
                </TooltipContent>
              </Tooltip>
            )}
          </div>
        </div>

        {/* Table */}
        <div
          className="panel flex-1 flex flex-col min-h-0 overflow-hidden"
          style={{ maxHeight: "calc(100vh - 100px)" }}
        >
          {filteredLogs.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-8 text-center">
              <Search className="h-5 w-5 text-muted-foreground mb-2" />
              <p className="text-sm font-medium mb-1">No requests found</p>
              <p className="text-xs text-muted-foreground">
                {searchQuery || activeFilters.size > 0
                  ? "Try adjusting your search or filters"
                  : "No requests have been logged yet"}
              </p>
            </div>
          ) : (
            <div className="overflow-auto flex-1 min-h-0">
              <table
                className="data-table w-full"
                style={{ tableLayout: "auto" }}
              >
                <thead className="sticky top-0 bg-background z-10">
                  <tr>
                    {!readOnly && isAdmin && (
                      <th className="w-10 min-w-10">
                        <button
                          onClick={handleSelectAll}
                          className="flex items-center justify-center w-full h-full"
                        >
                          {allSelected ? (
                            <CheckSquare className="h-4 w-4 text-primary" />
                          ) : someSelected ? (
                            <div className="relative">
                              <Square className="h-4 w-4 text-muted-foreground" />
                              <Minus className="h-2 w-2 absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 text-primary" />
                            </div>
                          ) : (
                            <Square className="h-4 w-4 text-muted-foreground" />
                          )}
                        </button>
                      </th>
                    )}
                    {!readOnly && (
                      <th
                        className={cn(
                          isAdmin
                            ? "w-[70px] min-w-[70px]"
                            : "w-[50px] min-w-[50px]",
                        )}
                      >
                        {isAdmin ? "Stars" : "Fave"}
                      </th>
                    )}
                    <th className="w-6 min-w-6"></th>
                    <th className="w-[110px] min-w-[110px]">Request ID</th>
                    <th className="w-auto min-w-[120px] max-w-[280px]">
                      Model
                    </th>
                    <th className="w-auto">Output</th>
                    {!readOnly && (
                      <th className="w-14 min-w-14 text-right">Steps</th>
                    )}
                    {!readOnly && (
                      <th className="w-14 min-w-14 text-right">Disc.</th>
                    )}
                    {isAdmin && !readOnly && (
                      <th className="w-[100px] min-w-[100px]">API Key</th>
                    )}
                    <th className="w-[90px] min-w-[90px] text-right pr-2">
                      Time
                    </th>
                    <th className="w-8 min-w-8"></th>
                  </tr>
                </thead>
                <tbody>
                  {filteredLogs.map((log) => (
                    <LogRow
                      key={log.request_id}
                      log={log}
                      onToggleFavorite={handleToggleFavorite}
                      unreadCount={getUnreadCount(
                        log.request_id,
                        log.discussion_count,
                      )}
                      expanded={expandedRows.has(log.request_id)}
                      onToggleExpand={() => toggleRowExpanded(log.request_id)}
                      tokenColorMode={tokenColorMode}
                      isSelected={selectedIds.has(log.request_id)}
                      onSelect={handleRowSelect}
                      onContextMenu={handleContextMenu}
                      readOnly={readOnly}
                      publicCollectionToken={publicCollectionToken}
                      showApiKey={isAdmin && !readOnly}
                      showStepsAndDiscussions={!readOnly}
                      isAdmin={isAdmin}
                      isFavorited={favoritedRequestIds.has(log.request_id)}
                      onToggleSimpleFavorite={handleToggleSimpleFavorite}
                      isTogglingFavorite={togglingFavorite === log.request_id}
                    />
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* Load More */}
          {hasMore && filteredLogs.length > 0 && !searchQuery && (
            <div className="flex justify-center py-2 border-t border-border">
              <Button
                variant="ghost"
                size="sm"
                className="h-7 text-xs"
                onClick={handleLoadMore}
              >
                {loading ? (
                  <>
                    <Loader2 className="mr-1.5 h-3 w-3 animate-spin" />
                    Loading...
                  </>
                ) : (
                  "Load More"
                )}
              </Button>
            </div>
          )}
        </div>

        {/* Context Menu - admin only */}
        {contextMenu && isAdmin && (
          <div
            className="fixed z-50 bg-popover border border-border rounded-md shadow-lg py-1 min-w-[160px]"
            style={{ left: contextMenu.x, top: contextMenu.y }}
            onClick={(e) => e.stopPropagation()}
          >
            <button
              onClick={handleOpenAddToCollection}
              className="w-full flex items-center gap-2 px-3 py-1.5 text-xs hover:bg-muted transition-colors text-left"
            >
              <FolderPlus className="h-3.5 w-3.5" />
              Add to Collection
              {selectedIds.size > 1 && (
                <Badge
                  variant="secondary"
                  className="ml-auto text-2xs h-4 px-1"
                >
                  {selectedIds.size}
                </Badge>
              )}
            </button>
          </div>
        )}

        {/* Add to Collection Modal - admin only */}
        {showAddToCollection && isAdmin && (
          <>
            <div
              className="fixed inset-0 bg-black/50 z-50"
              onClick={() => setShowAddToCollection(false)}
            />
            <div className="fixed left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 z-50 w-full max-w-md bg-popover border border-border rounded-lg shadow-xl">
              <div className="flex items-center justify-between px-4 py-3 border-b border-border">
                <h3 className="text-sm font-semibold">
                  Add {selectedIds.size} request
                  {selectedIds.size !== 1 ? "s" : ""} to collection
                </h3>
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-6 w-6"
                  onClick={() => setShowAddToCollection(false)}
                >
                  <X className="h-4 w-4" />
                </Button>
              </div>

              <div className="p-4">
                {/* Create new collection */}
                <div className="mb-4">
                  <label className="text-xs font-medium text-muted-foreground mb-2 block">
                    Create new collection
                  </label>
                  <div className="flex items-center gap-2">
                    <input
                      type="text"
                      value={newCollectionName}
                      onChange={(e) => setNewCollectionName(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") handleCreateAndAddToCollection();
                      }}
                      placeholder="Collection name..."
                      className="flex-1 h-8 px-3 text-sm bg-background border border-border rounded focus:outline-none focus:ring-1 focus:ring-primary"
                      disabled={creatingCollection}
                    />
                    <Button
                      size="sm"
                      className="h-8"
                      onClick={handleCreateAndAddToCollection}
                      disabled={
                        !newCollectionName.trim() ||
                        creatingCollection ||
                        selectedIds.size === 0
                      }
                    >
                      {creatingCollection ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : (
                        "Create"
                      )}
                    </Button>
                  </div>
                </div>

                {/* Existing collections */}
                <div>
                  <label className="text-xs font-medium text-muted-foreground mb-2 block">
                    Or add to existing collection
                  </label>
                  <div className="max-h-64 overflow-y-auto border border-border rounded">
                    {collectionsLoading ? (
                      <div className="flex items-center justify-center py-8">
                        <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
                      </div>
                    ) : collections.length === 0 ? (
                      <div className="text-center py-6 text-muted-foreground">
                        <FolderPlus className="h-8 w-8 mx-auto mb-2 opacity-50" />
                        <p className="text-xs">No collections yet</p>
                      </div>
                    ) : (
                      <div className="divide-y divide-border">
                        {collections.map((collection) => (
                          <button
                            key={collection.id}
                            onClick={() => handleAddToCollection(collection.id)}
                            disabled={addingToCollection === collection.id}
                            className="w-full flex items-center gap-3 px-3 py-2 text-left hover:bg-muted transition-colors disabled:opacity-50"
                          >
                            <FolderPlus className="h-4 w-4 text-muted-foreground shrink-0" />
                            <div className="flex-1 min-w-0">
                              <div className="text-sm truncate">
                                {collection.name}
                              </div>
                              {collection.description && (
                                <div className="text-xs text-muted-foreground truncate">
                                  {collection.description}
                                </div>
                              )}
                            </div>
                            <Badge
                              variant="secondary"
                              className="text-2xs h-5 px-1.5 shrink-0"
                            >
                              {collection.request_count ?? 0}
                            </Badge>
                            {addingToCollection === collection.id && (
                              <Loader2 className="h-4 w-4 animate-spin shrink-0" />
                            )}
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

interface LogRowProps {
  log: LogSummary;
  onToggleFavorite: (
    requestId: string,
    label: StarLabel,
    isCurrentlyActive: boolean,
  ) => void;
  unreadCount: number;
  expanded: boolean;
  onToggleExpand: () => void;
  tokenColorMode: TokenColorMode;
  isSelected: boolean;
  onSelect: (requestId: string, event: React.MouseEvent) => void;
  onContextMenu: (event: React.MouseEvent, requestId: string) => void;
  readOnly?: boolean;
  /** Public collection token for constructing request links in public collection view */
  publicCollectionToken?: string;
  /** Whether to show the API key column (admin only) */
  showApiKey?: boolean;
  /** Whether to show steps and discussions columns */
  showStepsAndDiscussions?: boolean;
  /** Whether user is admin (shows T/M/B stars) or regular user (shows single star) */
  isAdmin?: boolean;
  /** For non-admin: whether this request is in the favorites collection */
  isFavorited?: boolean;
  /** For non-admin: callback to toggle favorite status */
  onToggleSimpleFavorite?: (requestId: string) => void;
  /** For non-admin: whether the favorite toggle is in progress */
  isTogglingFavorite?: boolean;
}

function LogRow({
  log,
  onToggleFavorite,
  unreadCount,
  expanded,
  onToggleExpand,
  tokenColorMode,
  isSelected,
  onSelect,
  onContextMenu,
  readOnly = false,
  publicCollectionToken,
  showApiKey = false,
  showStepsAndDiscussions = true,
  isAdmin = false,
  isFavorited = false,
  onToggleSimpleFavorite,
  isTogglingFavorite = false,
}: LogRowProps) {
  const isCompleted = !!log.finished_ts;

  // Construct the appropriate link based on context
  const requestLink = publicCollectionToken
    ? `/share/${publicCollectionToken}/request/${log.request_id}`
    : `/logs/${log.request_id}`;

  return (
    <>
      <tr
        className={cn(
          "group",
          isSelected && !readOnly && isAdmin && "bg-primary/5",
        )}
        onContextMenu={(e) =>
          !readOnly && isAdmin && onContextMenu(e, log.request_id)
        }
      >
        {!readOnly && isAdmin && (
          <td>
            <button
              onClick={(e) => onSelect(log.request_id, e)}
              className="flex items-center justify-center w-full h-full"
            >
              {isSelected ? (
                <CheckSquare className="h-4 w-4 text-primary" />
              ) : (
                <Square className="h-4 w-4 text-muted-foreground hover:text-foreground" />
              )}
            </button>
          </td>
        )}
        {!readOnly && (
          <td>
            {isAdmin ? (
              // Admin users: show T, M, B buttons
              <div className="flex items-center gap-1">
                {STAR_LABELS.map((label) => {
                  const isActive = log.favorited_by.includes(label);
                  return (
                    <Tooltip key={label}>
                      <TooltipTrigger asChild>
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            onToggleFavorite(log.request_id, label, isActive);
                          }}
                          className={cn(
                            "w-5 h-5 rounded border text-2xs font-bold transition-colors flex items-center justify-center",
                            isActive
                              ? STAR_COLORS[label].active
                              : STAR_COLORS[label].inactive,
                          )}
                        >
                          {label}
                        </button>
                      </TooltipTrigger>
                      <TooltipContent>
                        <p className="text-2xs">
                          {isActive
                            ? `Remove ${label} star`
                            : `Add ${label} star`}
                        </p>
                      </TooltipContent>
                    </Tooltip>
                  );
                })}
              </div>
            ) : (
              // Non-admin users: show single star for favorites
              <Tooltip>
                <TooltipTrigger asChild>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      onToggleSimpleFavorite?.(log.request_id);
                    }}
                    disabled={isTogglingFavorite}
                    className="flex items-center justify-center"
                  >
                    {isTogglingFavorite ? (
                      <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
                    ) : (
                      <Star
                        className={cn(
                          "h-4 w-4 transition-colors",
                          isFavorited
                            ? "fill-amber-500 text-amber-500"
                            : "text-muted-foreground hover:text-amber-500",
                        )}
                      />
                    )}
                  </button>
                </TooltipTrigger>
                <TooltipContent>
                  <p className="text-2xs">
                    {isFavorited ? "Remove from favorites" : "Add to favorites"}
                  </p>
                </TooltipContent>
              </Tooltip>
            )}
          </td>
        )}
        <td>
          <Circle
            className={cn(
              "h-2 w-2",
              isCompleted
                ? "fill-green-500 text-green-500"
                : "fill-yellow-500 text-yellow-500 animate-pulse",
            )}
          />
        </td>
        <td className="overflow-hidden">
          <Link
            to={requestLink}
            className="font-mono text-xs hover:text-primary transition-colors block truncate"
          >
            <Tooltip>
              <TooltipTrigger asChild>
                <span className="truncate">
                  {truncateId(log.request_id, 12)}
                </span>
              </TooltipTrigger>
              <TooltipContent side="right">
                <p className="font-mono text-2xs">{log.request_id}</p>
              </TooltipContent>
            </Tooltip>
          </Link>
        </td>
        <td>
          {log.model_id ? (
            <Tooltip>
              <TooltipTrigger asChild>
                <Badge
                  variant="outline"
                  className="font-mono text-2xs h-5 px-1.5 rounded truncate max-w-full block"
                >
                  {log.model_id}
                </Badge>
              </TooltipTrigger>
              <TooltipContent side="bottom">
                <p className="font-mono text-2xs">{log.model_id}</p>
              </TooltipContent>
            </Tooltip>
          ) : (
            <span className="text-muted-foreground">—</span>
          )}
        </td>
        <td>
          <div className="flex items-center gap-2 min-w-0">
            <Tooltip>
              <TooltipTrigger asChild>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    onToggleExpand();
                  }}
                  className={cn(
                    "p-1 rounded hover:bg-muted transition-colors shrink-0",
                    expanded ? "text-primary" : "text-muted-foreground",
                  )}
                >
                  {expanded ? (
                    <ChevronDown className="h-4 w-4" />
                  ) : (
                    <Code className="h-4 w-4" />
                  )}
                </button>
              </TooltipTrigger>
              <TooltipContent>
                <p className="text-2xs">
                  {expanded ? "Hide tokens" : "Show tokens"}
                </p>
              </TooltipContent>
            </Tooltip>
            {log.final_text ? (
              <span className="text-muted-foreground truncate block min-w-0 flex-1 max-w-[315px]">
                {log.final_text}
              </span>
            ) : (
              <span className="text-muted-foreground/50 flex-1">—</span>
            )}
          </div>
        </td>
        {showStepsAndDiscussions && (
          <td className="text-right">
            <span className="font-mono text-xs">{log.total_steps}</span>
          </td>
        )}
        {showStepsAndDiscussions && (
          <td className="text-right">
            <div className="flex items-center justify-end gap-1">
              {log.discussion_count > 0 ? (
                <Tooltip>
                  <TooltipTrigger asChild>
                    <div className="flex items-center gap-1">
                      <MessagesSquare className="h-3 w-3 text-muted-foreground" />
                      <span className="font-mono text-xs">
                        {log.discussion_count}
                      </span>
                      {unreadCount > 0 && (
                        <span className="flex h-4 min-w-4 items-center justify-center rounded-full bg-blue-500 px-1 text-2xs font-medium text-white">
                          {unreadCount}
                        </span>
                      )}
                    </div>
                  </TooltipTrigger>
                  <TooltipContent>
                    <p className="text-2xs">
                      {log.discussion_count} discussion
                      {log.discussion_count !== 1 ? "s" : ""}
                      {unreadCount > 0 && ` (${unreadCount} unread)`}
                    </p>
                  </TooltipContent>
                </Tooltip>
              ) : (
                <span className="text-muted-foreground/50">—</span>
              )}
            </div>
          </td>
        )}
        {showApiKey && (
          <td className="overflow-hidden">
            {log.user_api_key ? (
              <Tooltip>
                <TooltipTrigger asChild>
                  <span className="font-mono text-xs text-muted-foreground block truncate">
                    {truncateId(log.user_api_key, 12)}
                  </span>
                </TooltipTrigger>
                <TooltipContent side="right">
                  <p className="font-mono text-2xs">{log.user_api_key}</p>
                </TooltipContent>
              </Tooltip>
            ) : (
              <span className="text-muted-foreground">—</span>
            )}
          </td>
        )}
        <td className="text-right pr-2">
          <Tooltip>
            <TooltipTrigger asChild>
              <span className="text-muted-foreground text-xs whitespace-nowrap block">
                {formatRelativeTime(log.created_ts)}
              </span>
            </TooltipTrigger>
            <TooltipContent>
              <p className="text-2xs">
                {new Date(log.created_ts).toLocaleString()}
              </p>
            </TooltipContent>
          </Tooltip>
        </td>
        <td className="text-center pl-0">
          <Link
            to={requestLink}
            className="inline-flex items-center justify-center w-full"
          >
            <ChevronRight className="h-4 w-4 text-muted-foreground group-hover:text-foreground transition-colors" />
          </Link>
        </td>
      </tr>
      {expanded && (
        <tr>
          <td colSpan={readOnly ? 6 : showApiKey ? 11 : 10} className="p-0">
            <div className="px-4 py-3 bg-muted/30 border-b border-border/50">
              <InlineTokenSequence
                requestId={log.request_id}
                expanded={true}
                onToggle={onToggleExpand}
                maxHeight="250px"
                showToggle={false}
                colorMode={tokenColorMode}
                publicCollectionToken={publicCollectionToken}
              />
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

function LogsListSkeleton() {
  return (
    <div className="space-y-3">
      {/* Header skeleton */}
      <div className="flex items-center justify-between gap-4">
        <div className="flex items-center gap-4">
          <Skeleton className="h-6 w-24" />
          <Skeleton className="h-4 w-48" />
        </div>
        <div className="flex items-center gap-2">
          <Skeleton className="h-6 w-20" />
          <Skeleton className="h-7 w-[200px]" />
          <Skeleton className="h-7 w-7" />
        </div>
      </div>

      {/* Table skeleton */}
      <div className="panel">
        <div className="overflow-x-auto">
          <table className="data-table">
            <thead>
              <tr>
                <th className="w-10"></th>
                <th className="w-20">Stars</th>
                <th className="w-8"></th>
                <th>Request ID</th>
                <th>Model</th>
                <th>Output</th>
                <th className="text-right">Steps</th>
                <th className="text-right">Disc.</th>
                <th>API Key</th>
                <th className="text-right">Time</th>
                <th className="w-10"></th>
                <th className="w-6"></th>
              </tr>
            </thead>
            <tbody>
              {[...Array(12)].map((_, i) => (
                <tr key={i}>
                  <td>
                    <Skeleton className="h-4 w-4" />
                  </td>
                  <td>
                    <div className="flex items-center gap-1">
                      <Skeleton className="h-5 w-5 rounded" />
                      <Skeleton className="h-5 w-5 rounded" />
                      <Skeleton className="h-5 w-5 rounded" />
                    </div>
                  </td>
                  <td>
                    <Skeleton className="h-2 w-2 rounded-full" />
                  </td>
                  <td>
                    <Skeleton className="h-4 w-24" />
                  </td>
                  <td>
                    <Skeleton className="h-5 w-16" />
                  </td>
                  <td>
                    <Skeleton className="h-4 w-48" />
                  </td>
                  <td>
                    <Skeleton className="h-4 w-8 ml-auto" />
                  </td>
                  <td>
                    <Skeleton className="h-4 w-8 ml-auto" />
                  </td>
                  <td>
                    <Skeleton className="h-4 w-20" />
                  </td>
                  <td>
                    <Skeleton className="h-4 w-12 ml-auto" />
                  </td>
                  <td>
                    <Skeleton className="h-4 w-4" />
                  </td>
                  <td>
                    <Skeleton className="h-4 w-4" />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
