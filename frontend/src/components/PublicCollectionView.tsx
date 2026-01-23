import { useState, useEffect, useCallback } from "react";
import { useParams, Link } from "react-router-dom";
import {
  FolderOpen,
  Loader2,
  AlertCircle,
  ArrowLeft,
  Globe,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { getPublicCollection, type PublicCollectionResponse } from "@/lib/api";
import type { LogSummary } from "@/types/api";
import LogsList from "@/components/LogsList";

export default function PublicCollectionView() {
  const { publicToken } = useParams<{ publicToken: string }>();
  const [data, setData] = useState<PublicCollectionResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadCollection = useCallback(async () => {
    if (!publicToken) return;

    try {
      setLoading(true);
      setError(null);
      // Load a larger batch for public view
      const response = await getPublicCollection(publicToken, 100, 0);
      setData(response);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Failed to load collection. The link may be invalid or expired.",
      );
    } finally {
      setLoading(false);
    }
  }, [publicToken]);

  useEffect(() => {
    loadCollection();
  }, [loadCollection]);

  if (loading) {
    return (
      <div className="min-h-screen bg-background text-foreground flex items-center justify-center">
        <div className="flex flex-col items-center gap-4">
          <Loader2 className="h-8 w-8 animate-spin text-primary" />
          <span className="text-sm text-muted-foreground">
            Loading collection...
          </span>
        </div>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="min-h-screen bg-background text-foreground flex items-center justify-center">
        <div className="max-w-md w-full mx-4 text-center">
          <div className="flex items-center justify-center w-16 h-16 rounded-full bg-destructive/10 mx-auto mb-4">
            <AlertCircle className="w-8 h-8 text-destructive" />
          </div>
          <h1 className="text-xl font-bold mb-2">Collection Not Found</h1>
          <p className="text-muted-foreground mb-6">
            {error || "This collection link is invalid or has expired."}
          </p>
          <Button variant="outline" asChild>
            <Link to="/">
              <ArrowLeft className="mr-2 h-4 w-4" />
              Go to Home
            </Link>
          </Button>
        </div>
      </div>
    );
  }

  const { collection, requests, total_requests } = data;

  // Transform CollectionRequest[] to LogSummary[] format
  const logs: LogSummary[] = requests.map((req) => ({
    request_id: req.request_id,
    created_ts: req.created_ts,
    finished_ts: req.finished_ts,
    model_id: req.model_id,
    user_api_key: null,
    final_text: req.final_text,
    total_steps: 0, // Not available in public view
    favorited_by: [],
    discussion_count: 0,
  }));

  return (
    <div className="h-screen bg-background text-foreground flex flex-col overflow-hidden">
      {/* Header */}
      <header className="sticky top-0 z-50 w-full border-b border-border bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/80">
        <div className="container flex flex-wrap gap-2 py-2 max-w-screen-2xl items-center min-h-10">
          <Link to="/" className="flex items-center gap-2 mr-2 shrink-0">
            <div className="flex items-center justify-center w-6 h-6 rounded bg-primary/10">
              <FolderOpen className="w-3.5 h-3.5 text-primary" />
            </div>
            <span className="font-semibold text-sm whitespace-nowrap">
              {collection.name}
            </span>
          </Link>

          <Badge
            variant="secondary"
            className="gap-1 text-green-600 bg-green-500/10 border-green-500/20"
          >
            <Globe className="h-3 w-3" />
            Shared Collection
          </Badge>

          <div className="flex-1" />

          <Badge variant="outline" className="text-xs">
            {total_requests} {total_requests === 1 ? "request" : "requests"}
          </Badge>
        </div>
      </header>

      {/* Description */}
      {collection.description && (
        <div className="border-b border-border bg-muted/30">
          <div className="container max-w-screen-2xl px-3 py-2">
            <p className="text-sm text-muted-foreground">
              {collection.description}
            </p>
          </div>
        </div>
      )}

      {/* Main Content */}
      <main className="flex-1 container max-w-screen-2xl py-3 flex flex-col min-h-0 overflow-hidden">
        <LogsList
          readOnly={true}
          initialLogs={logs}
          initialTotal={total_requests}
          hideCollectionHeader={true}
          publicCollectionToken={publicToken}
        />
      </main>

      {/* Read-only notice */}
      <div className="border-t border-border bg-muted/30">
        <div className="container max-w-screen-2xl py-3 text-center">
          <p className="text-sm text-muted-foreground">
            This is a read-only view of a shared collection.{" "}
            <Link to="/" className="text-primary hover:underline">
              Sign in
            </Link>{" "}
            to create collections and access more features.
          </p>
        </div>
      </div>
    </div>
  );
}
