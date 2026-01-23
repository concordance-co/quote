import { useState, useEffect, useCallback } from "react";
import { useParams, Link } from "react-router-dom";
import { Loader2, AlertCircle, ArrowLeft, FolderOpen } from "lucide-react";
import { Button } from "@/components/ui/button";
import { getRequestViaCollection } from "@/lib/api";
import type { LogResponse } from "@/types/api";
import LogDetail from "@/components/LogDetail";

export default function PublicCollectionRequestView() {
  const { collectionToken, requestId } = useParams<{
    collectionToken: string;
    requestId: string;
  }>();
  const [log, setLog] = useState<LogResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadRequest = useCallback(async () => {
    if (!collectionToken || !requestId) return;

    try {
      setLoading(true);
      setError(null);
      const response = await getRequestViaCollection(collectionToken, requestId);
      setLog(response);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Failed to load request. The collection link may be invalid or the request may not be in this collection.",
      );
    } finally {
      setLoading(false);
    }
  }, [collectionToken, requestId]);

  useEffect(() => {
    loadRequest();
  }, [loadRequest]);

  if (loading) {
    return (
      <div className="min-h-screen bg-background text-foreground flex items-center justify-center">
        <div className="flex flex-col items-center gap-4">
          <Loader2 className="h-8 w-8 animate-spin text-primary" />
          <span className="text-sm text-muted-foreground">
            Loading request...
          </span>
        </div>
      </div>
    );
  }

  if (error || !log) {
    return (
      <div className="min-h-screen bg-background text-foreground flex items-center justify-center">
        <div className="max-w-md w-full mx-4 text-center">
          <div className="flex items-center justify-center w-16 h-16 rounded-full bg-destructive/10 mx-auto mb-4">
            <AlertCircle className="w-8 h-8 text-destructive" />
          </div>
          <h1 className="text-xl font-bold mb-2">Request Not Found</h1>
          <p className="text-muted-foreground mb-6">
            {error || "This request could not be found in the shared collection."}
          </p>
          <div className="flex flex-col gap-2">
            {collectionToken && (
              <Button variant="outline" asChild>
                <Link to={`/share/${collectionToken}`}>
                  <FolderOpen className="mr-2 h-4 w-4" />
                  Back to Collection
                </Link>
              </Button>
            )}
            <Button variant="ghost" asChild>
              <Link to="/">
                <ArrowLeft className="mr-2 h-4 w-4" />
                Go to Home
              </Link>
            </Button>
          </div>
        </div>
      </div>
    );
  }

  // Provide back link to the collection
  const backLink = collectionToken ? `/share/${collectionToken}` : "/";

  return (
    <div className="min-h-screen bg-background text-foreground flex flex-col">
      <main className="flex-1 container max-w-screen-2xl py-3 flex flex-col min-h-0 overflow-hidden">
        <LogDetail log={log} readOnly={true} isPublicView={true} backLink={backLink} />
      </main>
    </div>
  );
}
