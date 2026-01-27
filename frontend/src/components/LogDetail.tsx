import { useState, useEffect, useCallback } from "react";
import { useParams, useSearchParams, Link } from "react-router-dom";
import { trackAnalyticsEvent } from "@/hooks/useAnalytics";
import {
  AlertTriangle,
  Zap,
  GitBranch,
  FileText,
  BarChart3,
  Code,
  MessageSquareText,
  MessagesSquare,
  Globe,
  ArrowLeft,
  Star,
  Loader2,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import AddToCollectionDropdown from "@/components/AddToCollectionDropdown";
import RequestShareButton from "@/components/RequestShareButton";

import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { Badge } from "@/components/ui/badge";
import { cn, formatDate, formatDuration } from "@/lib/utils";
import {
  fetchLogDetail,
  addFavorite,
  removeFavorite,
  listCollections,
  createCollection,
  addRequestToCollection,
  removeRequestFromCollection,
  getRequestCollections,
} from "@/lib/api";
import { useReadDiscussions } from "@/hooks/useReadDiscussions";
import { useAuth } from "@/lib/auth";
import TraceTree from "@/components/TraceTree";
import type { LogResponse } from "@/types/api";
import {
  BackButton,
  CopyButton,
  StatItem,
  TokensView,
  MetricsView,
  ActionsView,
  LogsView,
  DiscussionsView,
  TagsManager,
  RawView,
  LogDetailSkeleton,
} from "@/components/LogDetail/index";

const VALID_TABS = [
  "trace",
  "tokens",
  "metrics",
  "actions",
  "logs",
  "discussions",
  "raw",
];

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

export interface LogDetailProps {
  /** Optional pre-loaded log data (used for public view) */
  log?: LogResponse;
  /** When true, disables all editing features (favorites, tags, collections, sharing) */
  readOnly?: boolean;
  /** When true, shows public view header instead of back button */
  isPublicView?: boolean;
  /** Optional custom back link for public view */
  backLink?: string;
  /** Optional callback for back button (overrides default navigation) */
  onBack?: () => void;
  /** Default tab to show (overrides URL param default, useful for embedded use) */
  defaultTab?: string;
  /** When true, hides the back button entirely */
  hideBackButton?: boolean;
  /** When true, hides the metadata sidebar to give more room to main content */
  hideSidebar?: boolean;
}

export default function LogDetail({
  log: externalLog,
  readOnly = false,
  isPublicView = false,
  backLink,
  onBack,
  defaultTab = "trace",
  hideBackButton = false,
  hideSidebar = false,
}: LogDetailProps = {}) {
  const { requestId } = useParams<{ requestId: string }>();
  const [searchParams, setSearchParams] = useSearchParams();
  const [log, setLog] = useState<LogResponse | null>(externalLog || null);
  const [loading, setLoading] = useState(!externalLog);
  const [error, setError] = useState<string | null>(null);
  const [favoritedBy, setFavoritedBy] = useState<string[]>(
    externalLog?.favorited_by || [],
  );
  const [tags, setTags] = useState<string[]>(externalLog?.tags || []);
  const [isPublic, setIsPublic] = useState(externalLog?.is_public || false);
  const [publicToken, setPublicToken] = useState<string | null>(
    externalLog?.public_token || null,
  );
  const [discussionsKey, setDiscussionsKey] = useState(0);
  const [discussionCount, setDiscussionCount] = useState(
    externalLog?.discussion_count || 0,
  );
  const { markAsRead, getUnreadCount } = useReadDiscussions();
  const { user } = useAuth();
  const isAdmin = user?.isAdmin ?? false;

  // Favorites collection for non-admin users (single star functionality)
  const [favoritesCollectionId, setFavoritesCollectionId] = useState<
    number | null
  >(null);
  const [isInFavorites, setIsInFavorites] = useState(false);
  const [togglingSimpleFavorite, setTogglingSimpleFavorite] = useState(false);

  // Get the effective request ID (from props log or URL params)
  const effectiveRequestId = externalLog?.request_id || requestId;

  // Initialize state from URL params
  const tabParam = searchParams.get("tab");
  const stepParam = searchParams.get("step");
  const logIdParam = searchParams.get("logId");
  const activeTab = VALID_TABS.includes(tabParam || "")
    ? tabParam!
    : defaultTab;
  const selectedStep = stepParam ? parseInt(stepParam, 10) : null;
  const selectedLogId = logIdParam ? parseInt(logIdParam, 10) : null;

  // Update URL when tab changes
  const setActiveTab = useCallback(
    (tab: string) => {
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev);
        if (tab === defaultTab) {
          next.delete("tab");
        } else {
          next.set("tab", tab);
        }
        return next;
      });
    },
    [setSearchParams, defaultTab],
  );

  // Mark discussions as read when visiting the discussions tab (only for authenticated view)
  useEffect(() => {
    if (
      !readOnly &&
      activeTab === "discussions" &&
      effectiveRequestId &&
      discussionCount > 0
    ) {
      markAsRead(effectiveRequestId, discussionCount);
    }
  }, [activeTab, effectiveRequestId, discussionCount, markAsRead, readOnly]);

  // Handler for when discussion count changes
  const handleDiscussionCountChange = useCallback(
    (count: number) => {
      setDiscussionCount(count);
      // If we're already on the discussions tab, mark as read immediately
      if (!readOnly && activeTab === "discussions" && effectiveRequestId) {
        markAsRead(effectiveRequestId, count);
      }
    },
    [activeTab, effectiveRequestId, markAsRead, readOnly],
  );

  // Calculate unread count (only for authenticated view)
  const unreadDiscussionCount =
    !readOnly && effectiveRequestId
      ? getUnreadCount(effectiveRequestId, discussionCount)
      : 0;

  // Find or create the "Favorites" collection for non-admin users
  useEffect(() => {
    if (isAdmin || readOnly || !effectiveRequestId) return;

    const initFavoritesCollection = async () => {
      try {
        const response = await listCollections(100, 0);
        const existing = response.collections.find(
          (c) => c.name === "Favorites",
        );

        if (existing) {
          setFavoritesCollectionId(existing.id);
          // Check if current request is in favorites
          const reqCollections =
            await getRequestCollections(effectiveRequestId);
          setIsInFavorites(
            reqCollections.collections.some((c) => c.id === existing.id),
          );
        } else {
          // Create the Favorites collection
          const createResponse = await createCollection(
            "Favorites",
            "Your favorited requests",
          );
          setFavoritesCollectionId(createResponse.collection.id);
          setIsInFavorites(false);
        }
      } catch (err) {
        console.error("Failed to initialize favorites collection:", err);
      }
    };

    initFavoritesCollection();
  }, [isAdmin, readOnly, effectiveRequestId]);

  // Toggle simple favorite for non-admin users
  const handleToggleSimpleFavorite = useCallback(async () => {
    if (!favoritesCollectionId || !effectiveRequestId) return;

    try {
      setTogglingSimpleFavorite(true);

      if (isInFavorites) {
        await removeRequestFromCollection(
          favoritesCollectionId,
          effectiveRequestId,
        );
        setIsInFavorites(false);
      } else {
        await addRequestToCollection(favoritesCollectionId, effectiveRequestId);
        setIsInFavorites(true);
      }
    } catch (err) {
      console.error("Failed to toggle favorite:", err);
    } finally {
      setTogglingSimpleFavorite(false);
    }
  }, [favoritesCollectionId, effectiveRequestId, isInFavorites]);

  // Update URL when step changes
  const setSelectedStep = useCallback(
    (step: number | null) => {
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev);
        if (step === null) {
          next.delete("step");
        } else {
          next.set("step", String(step));
        }
        return next;
      });
    },
    [setSearchParams],
  );

  // Callback for TokensView to navigate to trace tab and select a step
  const handleNavigateToTrace = useCallback(
    (step: number) => {
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev);
        // Always explicitly set trace tab (don't rely on default)
        next.set("tab", "trace");
        next.set("step", String(step));
        return next;
      });
    },
    [setSearchParams],
  );

  // Load log data if not provided externally
  useEffect(() => {
    async function loadLog() {
      // Skip if we have external log data
      if (externalLog) {
        setLog(externalLog);
        setFavoritedBy(externalLog.favorited_by || []);
        setTags(externalLog.tags || []);
        setDiscussionCount(externalLog.discussion_count || 0);
        setIsPublic(externalLog.is_public || false);
        setPublicToken(externalLog.public_token || null);
        setLoading(false);
        return;
      }

      if (!requestId) return;

      try {
        setLoading(true);
        setError(null);
        const data = await fetchLogDetail(requestId);

        setLog(data);
        setFavoritedBy(data.favorited_by || []);
        setTags(data.tags || []);
        setDiscussionCount(data.discussion_count || 0);
        setIsPublic(data.is_public || false);
        setPublicToken(data.public_token || null);

        // Track log detail view (max 2 properties)
        trackAnalyticsEvent("log_viewed", {
          has_trace: (data.events?.length || 0) > 0,
          token_count: data.inference_stats?.total_tokens || 0,
        });
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load log");
      } finally {
        setLoading(false);
      }
    }

    loadLog();
  }, [requestId, externalLog]);

  const handleToggleFavorite = useCallback(
    async (label: StarLabel, isCurrentlyActive: boolean) => {
      if (!effectiveRequestId || readOnly) return;
      try {
        if (isCurrentlyActive) {
          const response = await removeFavorite(effectiveRequestId, label);
          setFavoritedBy(response.favorited_by);
        } else {
          const response = await addFavorite(effectiveRequestId, label);
          setFavoritedBy(response.favorited_by);
        }
      } catch (err) {
        console.error("Failed to update favorite:", err);
      }
    },
    [effectiveRequestId, readOnly],
  );

  // Handle share status change
  const handleShareStatusChange = useCallback(
    (newIsPublic: boolean, newPublicToken: string | null) => {
      setIsPublic(newIsPublic);
      setPublicToken(newPublicToken);
    },
    [],
  );

  // Handle when a comment is added - refresh discussions
  const handleCommentAdded = useCallback(() => {
    setDiscussionsKey((k) => k + 1);
  }, []);

  // Handle navigating to logs tab with optional logId
  const handleNavigateToLogs = useCallback(
    (logId: number) => {
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev);
        next.set("tab", "logs");
        next.set("logId", String(logId));
        next.delete("step");
        return next;
      });
    },
    [setSearchParams],
  );

  // Handle navigating to metrics tab with optional chartId
  const handleNavigateToMetrics = useCallback(
    (chartId: string) => {
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev);
        next.set("tab", "metrics");
        next.set("chartId", chartId);
        next.delete("step");
        next.delete("logId");
        return next;
      });
    },
    [setSearchParams],
  );

  if (loading) {
    return <LogDetailSkeleton />;
  }

  if (error || !log) {
    return (
      <div className="space-y-3">
        {!isPublicView && !hideBackButton && <BackButton onClick={onBack} />}
        <div className="panel">
          <div className="flex flex-col items-center justify-center py-8 text-center">
            <AlertTriangle className="h-5 w-5 text-destructive mb-2" />
            <p className="text-sm font-medium mb-1">Failed to load request</p>
            <p className="text-xs text-muted-foreground mb-3">
              {error || "Request not found"}
            </p>
            <Button size="sm" asChild>
              <Link to={backLink || "/"}>
                {isPublicView ? "Go to Home" : "Back to Requests"}
              </Link>
            </Button>
          </div>
        </div>
      </div>
    );
  }

  const stepsCount = (log.steps || []).length;
  const forcedCount = (log.steps || []).filter((s) => s.forced).length;
  const actionsCount = (log.actions || []).length;
  const duration =
    log.finished_ts && log.created_ts
      ? formatDuration(
          new Date(log.finished_ts).getTime() -
            new Date(log.created_ts).getTime(),
        )
      : "—";

  return (
    <Tabs
      value={activeTab}
      onValueChange={setActiveTab}
      className="h-full flex flex-col gap-3"
    >
      {/* Compact Header */}
      <div className="flex items-center justify-between gap-4 shrink-0">
        <div className="flex items-center gap-3">
          {isPublicView ? (
            <div className="flex items-center gap-2">
              <Button variant="ghost" size="sm" className="h-7 gap-1.5" asChild>
                <Link to={backLink || "/"}>
                  <ArrowLeft className="h-3 w-3" />
                  <span className="text-xs">Home</span>
                </Link>
              </Button>
              <Badge
                variant="secondary"
                className="gap-1 text-green-600 bg-green-500/10 border-green-500/20"
              >
                <Globe className="h-3 w-3" />
                Shared Request
              </Badge>
            </div>
          ) : !hideBackButton ? (
            <BackButton onClick={onBack} />
          ) : null}
        </div>
        {/* Tab Navigation - icons only on small screens */}
        <TabsList className="h-8 p-0.5 bg-muted/50">
          <TabsTrigger value="trace" className="h-7 text-xs gap-1.5 px-2">
            <GitBranch className="h-3 w-3" />
            <span className="hidden min-[600px]:inline">Trace</span>
          </TabsTrigger>
          <TabsTrigger value="tokens" className="h-7 text-xs gap-1.5 px-2">
            <Code className="h-3 w-3" />
            <span className="hidden min-[600px]:inline">Tokens</span>
          </TabsTrigger>
          <TabsTrigger value="metrics" className="h-7 text-xs gap-1.5 px-2">
            <BarChart3 className="h-3 w-3" />
            <span className="hidden min-[600px]:inline">Metrics</span>
          </TabsTrigger>
          <TabsTrigger value="actions" className="h-7 text-xs gap-1.5 px-2">
            <Zap className="h-3 w-3" />
            <span className="hidden min-[600px]:inline">Actions</span>
          </TabsTrigger>
          <TabsTrigger value="logs" className="h-7 text-xs gap-1.5 px-2">
            <MessageSquareText className="h-3 w-3" />
            <span className="hidden min-[600px]:inline">Logs</span>
          </TabsTrigger>
          <TabsTrigger
            value="discussions"
            className="h-7 text-xs gap-1.5 px-2 relative"
          >
            <MessagesSquare className="h-3 w-3" />
            <span className="hidden min-[600px]:inline">Discussion</span>
            {unreadDiscussionCount > 0 && (
              <span className="absolute -top-1 -right-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-blue-500 px-1 text-2xs font-medium text-white">
                {unreadDiscussionCount}
              </span>
            )}
          </TabsTrigger>
          <TabsTrigger value="raw" className="h-7 text-xs gap-1.5 px-2">
            <FileText className="h-3 w-3" />
            <span className="hidden min-[600px]:inline">Raw</span>
          </TabsTrigger>
        </TabsList>
        <div className="flex items-center gap-2">
          {/* Share Button - only show when not in read-only mode */}
          {!readOnly && (
            <RequestShareButton
              isPublic={isPublic}
              publicToken={publicToken}
              logData={log}
              onStatusChange={handleShareStatusChange}
            />
          )}
          {/* Add to Collection - only show for admin users when not in read-only mode */}
          {!readOnly && isAdmin && (
            <AddToCollectionDropdown
              requestId={log.request_id}
              variant="button"
            />
          )}
          {/* Star Favorites */}
          {isAdmin ? (
            // Admin users: show T, M, B stars
            <div className="flex items-center gap-1">
              {STAR_LABELS.map((label) => {
                const isActive = favoritedBy.includes(label);
                return (
                  <Tooltip key={label}>
                    <TooltipTrigger asChild>
                      <button
                        onClick={() =>
                          !readOnly && handleToggleFavorite(label, isActive)
                        }
                        disabled={readOnly}
                        className={cn(
                          "w-6 h-6 rounded-md border text-xs font-bold transition-colors flex items-center justify-center",
                          isActive
                            ? STAR_COLORS[label].active
                            : STAR_COLORS[label].inactive,
                          readOnly && "cursor-default opacity-70",
                        )}
                      >
                        {label}
                      </button>
                    </TooltipTrigger>
                    <TooltipContent>
                      <p className="text-2xs">
                        {readOnly
                          ? isActive
                            ? `Starred: ${label}`
                            : `Not starred: ${label}`
                          : isActive
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
            !readOnly && (
              <Tooltip>
                <TooltipTrigger asChild>
                  <button
                    onClick={handleToggleSimpleFavorite}
                    disabled={togglingSimpleFavorite}
                    className="flex items-center justify-center p-1"
                  >
                    {togglingSimpleFavorite ? (
                      <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
                    ) : (
                      <Star
                        className={cn(
                          "h-5 w-5 transition-colors",
                          isInFavorites
                            ? "fill-amber-500 text-amber-500"
                            : "text-muted-foreground hover:text-amber-500",
                        )}
                      />
                    )}
                  </button>
                </TooltipTrigger>
                <TooltipContent>
                  <p className="text-2xs">
                    {isInFavorites
                      ? "Remove from favorites"
                      : "Add to favorites"}
                  </p>
                </TooltipContent>
              </Tooltip>
            )
          )}
        </div>
      </div>

      {/* Main Content Area - responsive layout */}
      <div
        className={cn(
          "flex-1 min-h-0 flex flex-col gap-3",
          !hideSidebar && "min-[1000px]:flex-row-reverse",
        )}
      >
        {/* Sidebar - right on wide screens, top on narrow */}
        {!hideSidebar && (
          <div className="shrink-0 min-[1000px]:w-64 flex flex-col gap-3">
            {/* Request ID & Stats */}
            <div className="panel">
              {/* Request ID */}
              <div className="px-3 py-2 border-b border-border/50">
                <div className="flex flex-row items-center justify-between">
                  <div className="text-2xs text-muted-foreground mb-1">
                    Request ID
                  </div>
                  <CopyButton text={log.request_id} label="Copy ID" />
                </div>
                <div className="text-2xs font-mono break-all">
                  {log.request_id}
                </div>
              </div>
              {/* Inline Stats */}
              <div className="px-3 py-2 flex flex-wrap items-center gap-x-6 gap-y-2 text-xs min-[1000px]:flex-col min-[1000px]:items-start min-[1000px]:gap-3">
                <StatItem label="Steps" value={stepsCount} />
                <StatItem label="Forced" value={forcedCount} highlight />
                <StatItem label="Actions" value={actionsCount} />
                <StatItem label="Model" value={log.model_id || "—"} />
                <StatItem label="Duration" value={duration} />
                {log.finished_ts && (
                  <span className="text-muted-foreground min-[1000px]:mt-2">
                    {formatDate(log.finished_ts)}
                  </span>
                )}
              </div>
              {/* Tags */}
              <div className="px-3 py-2 border-t border-border/50">
                <TagsManager
                  requestId={log.request_id}
                  tags={tags}
                  onTagsChange={setTags}
                  readOnly={readOnly}
                />
              </div>
            </div>
          </div>
        )}

        {/* Main Content */}
        <div className="flex-1 flex flex-col min-h-0">
          <TabsContent value="trace" className="mt-0 flex-1 min-h-0">
            <TraceTree
              log={log}
              selectedStep={selectedStep}
              onSelectStep={setSelectedStep}
              requestId={log.request_id}
              onCommentAdded={readOnly ? undefined : handleCommentAdded}
            />
          </TabsContent>

          <TabsContent
            value="tokens"
            className="mt-0 flex-1 min-h-0 overflow-auto"
          >
            <TokensView
              log={log}
              selectedStep={selectedStep}
              onSelectStep={setSelectedStep}
              onNavigateToTrace={handleNavigateToTrace}
            />
          </TabsContent>

          <TabsContent
            value="metrics"
            className="mt-0 flex-1 min-h-0 overflow-auto"
          >
            <MetricsView
              log={log}
              requestId={log.request_id}
              onCommentAdded={readOnly ? undefined : handleCommentAdded}
            />
          </TabsContent>

          <TabsContent
            value="actions"
            className="mt-0 flex-1 min-h-0 overflow-auto"
          >
            <ActionsView log={log} onNavigateToTrace={handleNavigateToTrace} />
          </TabsContent>

          <TabsContent
            value="logs"
            className="mt-0 flex-1 min-h-0 overflow-auto"
          >
            <LogsView
              log={log}
              requestId={log.request_id}
              selectedLogId={selectedLogId}
              onNavigateToTrace={handleNavigateToTrace}
              onCommentAdded={readOnly ? undefined : handleCommentAdded}
            />
          </TabsContent>

          <TabsContent
            value="discussions"
            className="mt-0 flex-1 min-h-0 overflow-auto"
          >
            <DiscussionsView
              key={discussionsKey}
              requestId={log.request_id}
              onNavigateToTrace={handleNavigateToTrace}
              onNavigateToLogs={handleNavigateToLogs}
              onNavigateToMetrics={handleNavigateToMetrics}
              onDiscussionCountChange={handleDiscussionCountChange}
              readOnly={readOnly}
            />
          </TabsContent>

          <TabsContent
            value="raw"
            className="mt-0 flex-1 min-h-0 overflow-auto"
          >
            <RawView log={log} />
          </TabsContent>
        </div>
      </div>

      {/* Read-only notice for public view */}
      {isPublicView && (
        <div className="shrink-0 p-3 rounded-lg border border-border bg-muted/30 text-center">
          <p className="text-sm text-muted-foreground">
            This is a read-only view of a shared request.{" "}
            <Link to="/" className="text-primary hover:underline">
              Sign in
            </Link>{" "}
            to add comments, tags, and other features.
          </p>
        </div>
      )}
    </Tabs>
  );
}
