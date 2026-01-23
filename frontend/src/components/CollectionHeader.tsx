import { useState, useCallback } from "react";
import {
  FolderOpen,
  Globe,
  Lock,
  Copy,
  Check,
  Loader2,
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
import { makeCollectionPublic, makeCollectionPrivate } from "@/lib/api";
import { cn } from "@/lib/utils";

interface CollectionHeaderProps {
  collectionId: number;
  collectionName: string;
  isPublic?: boolean;
  publicToken?: string | null;
  onPublicStatusChange?: (
    isPublic: boolean,
    publicToken: string | null,
  ) => void;
}

export default function CollectionHeader({
  collectionId,
  collectionName,
  isPublic: initialIsPublic = false,
  publicToken: initialPublicToken = null,
  onPublicStatusChange,
}: CollectionHeaderProps) {
  const [isPublic, setIsPublic] = useState(initialIsPublic);
  const [publicToken, setPublicToken] = useState<string | null>(
    initialPublicToken,
  );
  const [updating, setUpdating] = useState(false);
  const [copied, setCopied] = useState(false);

  const getShareableUrl = useCallback(() => {
    if (!publicToken) return null;
    const baseUrl = window.location.origin;
    return `${baseUrl}/share/${publicToken}`;
  }, [publicToken]);

  const handleCopyLink = async () => {
    const url = getShareableUrl();
    if (!url) return;

    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      console.error("Failed to copy:", err);
    }
  };

  const handleTogglePublic = async () => {
    try {
      setUpdating(true);

      if (isPublic) {
        await makeCollectionPrivate(collectionId);
        setIsPublic(false);
        setPublicToken(null);
        onPublicStatusChange?.(false, null);
      } else {
        const response = await makeCollectionPublic(collectionId);
        setIsPublic(true);
        setPublicToken(response.public_token);
        onPublicStatusChange?.(true, response.public_token);
      }
    } catch (err) {
      console.error("Failed to update collection:", err);
    } finally {
      setUpdating(false);
    }
  };

  const shareableUrl = getShareableUrl();

  return (
    <div className="bg-muted/30 border-b border-border">
      <div className="flex flex-wrap items-center gap-3 px-3 py-2">
        {/* Collection Info */}
        <div className="flex items-center gap-2 min-w-0">
          <FolderOpen className="h-4 w-4 text-primary shrink-0" />
          <span className="text-sm font-medium whitespace-nowrap">
            {collectionName}
          </span>
          {isPublic ? (
            <Badge variant="secondary" className="shrink-0 gap-1">
              <Globe className="h-3 w-3" />
              Public
            </Badge>
          ) : (
            <Badge
              variant="outline"
              className="shrink-0 gap-1 text-muted-foreground"
            >
              <Lock className="h-3 w-3" />
              Private
            </Badge>
          )}
        </div>

        {/* Actions */}
        <div className="flex flex-wrap items-center gap-2 shrink-0 ml-auto">
          {/* Copy Link Button (only when public) */}
          {isPublic && shareableUrl && (
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  variant="outline"
                  size="sm"
                  className="h-7 text-xs gap-1.5"
                  onClick={handleCopyLink}
                >
                  {copied ? (
                    <>
                      <Check className="h-3 w-3 text-green-500" />
                      Copied!
                    </>
                  ) : (
                    <>
                      <Copy className="h-3 w-3" />
                      Copy Link
                    </>
                  )}
                </Button>
              </TooltipTrigger>
              <TooltipContent>
                <p className="text-xs">{shareableUrl}</p>
              </TooltipContent>
            </Tooltip>
          )}

          {/* Open Public Link (only when public) */}
          {isPublic && shareableUrl && (
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  variant="outline"
                  size="sm"
                  className="h-7 w-7 p-0"
                  asChild
                >
                  <a
                    href={shareableUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    <ExternalLink className="h-3 w-3" />
                  </a>
                </Button>
              </TooltipTrigger>
              <TooltipContent>
                <p className="text-xs">Open public link</p>
              </TooltipContent>
            </Tooltip>
          )}

          {/* Toggle Public/Private Button */}
          <Button
            variant={isPublic ? "outline" : "default"}
            size="sm"
            className={cn(
              "h-7 text-xs gap-1.5",
              isPublic &&
                "hover:bg-destructive/10 hover:text-destructive hover:border-destructive/50",
            )}
            onClick={handleTogglePublic}
            disabled={updating}
          >
            {updating ? (
              <>
                <Loader2 className="h-3 w-3 animate-spin" />
                {isPublic ? "Making Private..." : "Making Public..."}
              </>
            ) : isPublic ? (
              <>
                <Lock className="h-3 w-3" />
                Make Private
              </>
            ) : (
              <>
                <LinkIcon className="h-3 w-3" />
                Share
              </>
            )}
          </Button>
        </div>
      </div>
    </div>
  );
}
