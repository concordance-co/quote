import { useState, useRef, useCallback, useEffect, useMemo } from "react";
import { toPng } from "html-to-image";
import { trackAnalyticsEvent } from "@/hooks/useAnalytics";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { ShareableCard, type TokenDisplayData } from "./ShareableCard";
import { makeRequestPublic, makeRequestPrivate } from "@/lib/api";
import type { ShareablePlaygroundConfig } from "@/lib/shareUtils";
import type { LogResponse } from "@/types/api";
import { useTokenTimeline } from "@/components/TokenSequence";
import { Download, Copy, Check, Loader2, Globe, Lock } from "lucide-react";

// Twitter/X icon component
function XIcon({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      fill="currentColor"
      viewBox="0 0 24 24"
      aria-hidden="true"
    >
      <path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z" />
    </svg>
  );
}

interface ShareDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  config: ShareablePlaygroundConfig;
  outputText: string;
  logData: LogResponse | null;
  // New props for backend token approach
  requestId: string | null;
  isPublic: boolean;
  publicToken: string | null;
  onStatusChange?: (isPublic: boolean, publicToken: string | null) => void;
}

export function ShareDialog({
  open,
  onOpenChange,
  config,
  outputText,
  logData,
  requestId,
  isPublic,
  publicToken,
  onStatusChange,
}: ShareDialogProps) {
  const cardRef = useRef<HTMLDivElement>(null);
  const [isGenerating, setIsGenerating] = useState(false);
  const [linkCopied, setLinkCopied] = useState(false);
  const [imageCopied, setImageCopied] = useState(false);

  // API flow state
  const [updating, setUpdating] = useState(false);
  const [localToken, setLocalToken] = useState<string | null>(publicToken);
  const [showConfirmDialog, setShowConfirmDialog] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Create a placeholder log for the hook when no data
  const emptyLog: LogResponse = {
    request_id: "",
    created_ts: "",
    finished_ts: null,
    system_prompt: null,
    user_prompt: null,
    formatted_prompt: null,
    model_id: null,
    user_api_key: null,
    is_public: false,
    public_token: null,
    model_version: null,
    tokenizer_version: null,
    vocab_hash: null,
    sampler_preset: null,
    sampler_algo: null,
    rng_seed: null,
    max_steps: null,
    active_mod: null,
    final_tokens: null,
    final_text: null,
    sequence_confidence: null,
    eos_reason: null,
    request_tags: {},
    favorited_by: [],
    tags: [],
    events: [],
    mod_calls: [],
    mod_logs: [],
    actions: [],
    steps: [],
    step_logit_summaries: [],
    inference_stats: null,
    discussion_count: 0,
  };

  // Extract tokens using the proper hook
  const { timeline } = useTokenTimeline(logData || emptyLog);

  // Get final tokens from timeline (filter out EOT tokens)
  const tokens: TokenDisplayData[] = useMemo(() => {
    if (timeline.length === 0) return [];
    const finalSnapshot = timeline[timeline.length - 1];
    return finalSnapshot.items
      .filter(
        (item): item is Extract<typeof item, { type: "token" }> =>
          item.type === "token" && !item.erased,
      )
      .filter((item) => {
        // Filter out EOT/EOS tokens
        const text = item.token_text.toLowerCase();
        return (
          !text.includes("<|eot_id|>") &&
          !text.includes("<|end|>") &&
          !text.includes("</s>") &&
          !text.includes("<|endoftext|>")
        );
      })
      .map((item) => ({
        text: item.token_text,
        forced: item.forced,
        prob: item.prob,
      }));
  }, [timeline]);

  // Sync localToken with prop when it changes
  useEffect(() => {
    setLocalToken(publicToken);
  }, [publicToken]);

  const effectiveToken = localToken || publicToken;
  const effectiveIsPublic = isPublic || !!localToken;

  // Build the shareable URL
  const getShareableUrl = useCallback(() => {
    if (!effectiveToken) return null;
    const baseUrl = window.location.origin;
    return `${baseUrl}/share/request/${effectiveToken}`;
  }, [effectiveToken]);

  const shareUrl = getShareableUrl();

  const generateImage = useCallback(async (): Promise<Blob | null> => {
    if (!cardRef.current) return null;

    try {
      const dataUrl = await toPng(cardRef.current, {
        width: 1200,
        height: 628,
        pixelRatio: 2, // 2x for retina quality
        backgroundColor: "#0a0a0a",
      });

      // Convert data URL to blob
      const res = await fetch(dataUrl);
      return await res.blob();
    } catch (err) {
      console.error("Failed to generate image:", err);
      return null;
    }
  }, []);

  const handleDownloadPng = useCallback(async () => {
    setIsGenerating(true);
    try {
      const blob = await generateImage();
      if (!blob) return;

      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = "concordance-experiment.png";
      link.style.display = "none";
      document.body.appendChild(link);

      link.click();

      // Delay cleanup for Firefox compatibility
      setTimeout(() => {
        document.body.removeChild(link);
        URL.revokeObjectURL(url);
      }, 100);
    } finally {
      setIsGenerating(false);
    }
  }, [generateImage]);

  const handleCopyImage = useCallback(async () => {
    setIsGenerating(true);
    try {
      const blob = await generateImage();
      if (!blob) return;

      await navigator.clipboard.write([
        new ClipboardItem({
          "image/png": blob,
        }),
      ]);
      setImageCopied(true);
      setTimeout(() => setImageCopied(false), 2000);
    } catch (err) {
      console.error("Failed to copy image:", err);
    } finally {
      setIsGenerating(false);
    }
  }, [generateImage]);

  const handleCopyLink = useCallback(async () => {
    if (!shareUrl) return;
    try {
      await navigator.clipboard.writeText(shareUrl);
      setLinkCopied(true);
      setTimeout(() => setLinkCopied(false), 2000);
    } catch (err) {
      console.error("Failed to copy link:", err);
    }
  }, [shareUrl]);

  const handleShareTwitter = useCallback(() => {
    if (!shareUrl) return;
    const tweetText =
      "Check out this token injection experiment on Concordance!";
    const params = new URLSearchParams({
      text: tweetText,
      url: shareUrl,
    });
    window.open(
      `https://twitter.com/intent/tweet?${params.toString()}`,
      "_blank",
      "noopener,noreferrer",
    );
  }, [shareUrl]);

  const handleMakePublic = useCallback(async () => {
    if (!requestId) return;

    try {
      setUpdating(true);
      setError(null);
      const response = await makeRequestPublic(requestId);
      setLocalToken(response.public_token);
      onStatusChange?.(true, response.public_token);
      setShowConfirmDialog(false);

      // Track share action (max 2 properties)
      trackAnalyticsEvent("playground_shared", {
        model: config.model,
        mod_enabled: config.enableMod,
      });
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to make request public",
      );
    } finally {
      setUpdating(false);
    }
  }, [requestId, onStatusChange]);

  const handleMakePrivate = useCallback(async () => {
    if (!requestId) return;

    try {
      setUpdating(true);
      setError(null);
      await makeRequestPrivate(requestId);
      setLocalToken(null);
      onStatusChange?.(false, null);
      setShowConfirmDialog(false);
      // Close the share dialog since there's no longer a shareable link
      onOpenChange(false);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to make request private",
      );
    } finally {
      setUpdating(false);
    }
  }, [requestId, onStatusChange, onOpenChange]);

  const openConfirmDialog = useCallback(() => {
    setError(null);
    setShowConfirmDialog(true);
  }, []);

  // If request is not yet public, show "Make Public" confirmation first
  if (!effectiveIsPublic && open) {
    return (
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Globe className="h-5 w-5" />
              Share Experiment Publicly
            </DialogTitle>
            <DialogDescription>
              This will create a public link that anyone can use to view this
              experiment. They will be able to see the prompts, injection
              config, token sequence, and output.
            </DialogDescription>
          </DialogHeader>
          {error && (
            <div className="text-sm text-destructive bg-destructive/10 p-3 rounded">
              {error}
            </div>
          )}
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={updating}
            >
              Cancel
            </Button>
            <Button
              onClick={handleMakePublic}
              disabled={updating || !requestId}
            >
              {updating ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Creating Link...
                </>
              ) : (
                <>
                  <Globe className="mr-2 h-4 w-4" />
                  Make Public
                </>
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    );
  }

  // Already public - show the full share dialog
  return (
    <>
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle className="text-base font-mono">
              Share Experiment
            </DialogTitle>
          </DialogHeader>

          <div className="space-y-4">
            {/* Card Preview - Centered with proper scaling */}
            <div className="flex justify-center bg-muted/30 rounded-lg p-3 border border-border">
              <div
                style={{
                  width: "600px",
                  height: "314px",
                }}
              >
                <div
                  style={{
                    width: "1200px",
                    height: "628px",
                    transform: "scale(0.5)",
                    transformOrigin: "top left",
                  }}
                >
                  <ShareableCard
                    ref={cardRef}
                    model={config.model}
                    maxTokens={config.maxTokens}
                    temperature={config.temperature}
                    systemPrompt={config.systemPrompt}
                    userPrompt={config.userPrompt}
                    injectionPosition={config.injectionPosition}
                    injectionString={config.injectionString}
                    tokenCount={config.tokenCount}
                    sentenceCount={config.sentenceCount}
                    detectPhrases={config.detectPhrases}
                    replacementPhrases={config.replacementPhrases}
                    outputText={outputText}
                    shareUrl={shareUrl || ""}
                    tokens={tokens}
                  />
                </div>
              </div>
            </div>

            {/* Actions */}
            <div className="grid grid-cols-3 gap-2">
              <Button
                variant="outline"
                onClick={handleDownloadPng}
                disabled={isGenerating}
                className="flex items-center justify-center gap-2"
              >
                {isGenerating ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Download className="h-4 w-4" />
                )}
                PNG
              </Button>

              <Button
                variant="outline"
                onClick={handleCopyImage}
                disabled={isGenerating}
                className="flex items-center justify-center gap-2"
              >
                {imageCopied ? (
                  <Check className="h-4 w-4 text-emerald-500" />
                ) : isGenerating ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Copy className="h-4 w-4" />
                )}
                {imageCopied ? "Copied!" : "Image"}
              </Button>

              <Button
                variant="default"
                onClick={handleShareTwitter}
                disabled={!shareUrl}
                className="flex items-center justify-center gap-2 bg-[#1DA1F2] hover:bg-[#1a8cd8] text-white"
              >
                <XIcon className="h-4 w-4" />
                Post
              </Button>
            </div>

            {/* Shareable Link */}
            {shareUrl && (
              <div className="flex items-center gap-2">
                <input
                  type="text"
                  readOnly
                  value={shareUrl}
                  className="flex-1 px-3 py-2 text-xs font-mono bg-muted border border-border rounded focus:outline-none truncate"
                />
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleCopyLink}
                  className="shrink-0 gap-1.5"
                >
                  {linkCopied ? (
                    <Check className="h-4 w-4 text-emerald-500" />
                  ) : (
                    <Copy className="h-4 w-4" />
                  )}
                  {linkCopied ? "Copied!" : "Copy Link"}
                </Button>
              </div>
            )}

            {/* Footer */}
            <div className="flex items-center justify-between text-[11px] text-muted-foreground">
              <span>Anyone with the link can view this experiment.</span>
              <Button
                variant="ghost"
                size="sm"
                onClick={openConfirmDialog}
                disabled={updating}
                className="h-auto py-1 px-2 text-[11px] text-muted-foreground hover:text-destructive"
              >
                <Lock className="h-3 w-3 mr-1" />
                Make Private
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Confirmation Dialog for making private */}
      <Dialog open={showConfirmDialog} onOpenChange={setShowConfirmDialog}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Make Experiment Private?</DialogTitle>
            <DialogDescription>
              This will revoke the public link. Anyone with the current link
              will no longer be able to view this experiment.
            </DialogDescription>
          </DialogHeader>
          {error && (
            <div className="text-sm text-destructive bg-destructive/10 p-3 rounded">
              {error}
            </div>
          )}
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setShowConfirmDialog(false)}
              disabled={updating}
            >
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={handleMakePrivate}
              disabled={updating}
            >
              {updating ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Making Private...
                </>
              ) : (
                "Make Private"
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
