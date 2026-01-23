import { useState, useCallback } from "react";
import {
  Globe,
  Copy,
  Check,
  ExternalLink,
  Link as LinkIcon,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { LogShareDialog } from "./LogShareDialog";
import type { LogResponse } from "@/types/api";

interface RequestShareButtonProps {
  isPublic: boolean;
  publicToken: string | null;
  logData: LogResponse;
  onStatusChange?: (isPublic: boolean, publicToken: string | null) => void;
}

export default function RequestShareButton({
  isPublic,
  publicToken,
  logData,
  onStatusChange,
}: RequestShareButtonProps) {
  const [copied, setCopied] = useState(false);
  const [showDialog, setShowDialog] = useState(false);

  const getShareableUrl = useCallback(() => {
    if (!publicToken) return null;
    const baseUrl = window.location.origin;
    return `${baseUrl}/share/request/${publicToken}`;
  }, [publicToken]);

  const handleCopyLink = useCallback(async () => {
    const url = getShareableUrl();
    if (!url) return;

    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      console.error("Failed to copy:", err);
    }
  }, [getShareableUrl]);

  const shareableUrl = getShareableUrl();

  // If already public, show share controls with dialog trigger
  if (isPublic && shareableUrl) {
    return (
      <>
        <div className="flex items-center gap-1">
          <Tooltip>
            <TooltipTrigger asChild>
              <Badge
                variant="secondary"
                className="gap-1 cursor-pointer text-green-600 bg-green-500/10 border-green-500/20 hover:bg-green-500/20"
                onClick={() => setShowDialog(true)}
              >
                <Globe className="h-3 w-3" />
                Public
              </Badge>
            </TooltipTrigger>
            <TooltipContent>
              <p className="text-xs">Click to open share dialog</p>
            </TooltipContent>
          </Tooltip>

          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="ghost"
                size="sm"
                className="h-6 w-6 p-0"
                onClick={handleCopyLink}
              >
                {copied ? (
                  <Check className="h-3 w-3 text-green-500" />
                ) : (
                  <Copy className="h-3 w-3" />
                )}
              </Button>
            </TooltipTrigger>
            <TooltipContent>
              <p className="text-xs">{copied ? "Copied!" : "Copy share link"}</p>
            </TooltipContent>
          </Tooltip>

          <Tooltip>
            <TooltipTrigger asChild>
              <Button variant="ghost" size="sm" className="h-6 w-6 p-0" asChild>
                <a href={shareableUrl} target="_blank" rel="noopener noreferrer">
                  <ExternalLink className="h-3 w-3" />
                </a>
              </Button>
            </TooltipTrigger>
            <TooltipContent>
              <p className="text-xs">Open public link</p>
            </TooltipContent>
          </Tooltip>
        </div>

        <LogShareDialog
          open={showDialog}
          onOpenChange={setShowDialog}
          logData={logData}
          onStatusChange={onStatusChange}
        />
      </>
    );
  }

  // Not public - show share button that opens the dialog
  return (
    <>
      <Tooltip>
        <TooltipTrigger asChild>
          <Button
            variant="ghost"
            size="sm"
            className="h-7 gap-1.5 text-xs"
            onClick={() => setShowDialog(true)}
          >
            <LinkIcon className="h-3 w-3" />
            Share
          </Button>
        </TooltipTrigger>
        <TooltipContent>
          <p className="text-xs">Create a public shareable link</p>
        </TooltipContent>
      </Tooltip>

      <LogShareDialog
        open={showDialog}
        onOpenChange={setShowDialog}
        logData={logData}
        onStatusChange={onStatusChange}
      />
    </>
  );
}
