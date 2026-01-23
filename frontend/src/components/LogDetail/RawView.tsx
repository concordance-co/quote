import { useState, useCallback } from "react";
import { ChevronRight, ChevronDown } from "lucide-react";
import { ScrollArea } from "@/components/ui/scroll-area";
import { cn } from "@/lib/utils";
import { CopyButton } from "./CopyButton";
import type { LogResponse } from "@/types/api";

interface RawViewProps {
  log: LogResponse;
}

export function RawView({ log }: RawViewProps) {
  return (
    <div className="panel h-full overflow-auto">
      <div className="panel-header">
        <span className="panel-title">Raw JSON</span>
        <CopyButton text={JSON.stringify(log, null, 2)} label="Copy JSON" />
      </div>
      <div className="panel-content p-0">
        <ScrollArea>
          <div className="p-3 bg-black/30 text-2xs font-mono">
            <JsonNode value={log} defaultExpanded />
          </div>
        </ScrollArea>
      </div>
    </div>
  );
}

interface JsonNodeProps {
  keyName?: string;
  value: unknown;
  defaultExpanded?: boolean;
  depth?: number;
}

function JsonNode({
  keyName,
  value,
  defaultExpanded = false,
  depth = 0,
}: JsonNodeProps) {
  const [expanded, setExpanded] = useState(defaultExpanded);

  const toggle = useCallback(() => setExpanded((e) => !e), []);

  const type = getType(value);
  const isExpandable = type === "object" || type === "array";

  // Render primitive values
  if (!isExpandable) {
    return (
      <div className="flex items-start gap-1 py-0.5">
        <span className="w-4" /> {/* Spacer for alignment */}
        {keyName !== undefined && (
          <>
            <span className="text-purple-400">{`"${keyName}"`}</span>
            <span className="text-muted-foreground">: </span>
          </>
        )}
        <ValueDisplay value={value} type={type} />
      </div>
    );
  }

  // Render objects and arrays
  const entries =
    type === "object"
      ? Object.entries(value as Record<string, unknown>)
      : (value as unknown[]).map((v, i) => [i, v] as [number, unknown]);

  const isEmpty = entries.length === 0;
  const bracketOpen = type === "object" ? "{" : "[";
  const bracketClose = type === "object" ? "}" : "]";

  return (
    <div className="py-0.5">
      <div
        className={cn(
          "flex items-start gap-1",
          isExpandable && "cursor-pointer hover:bg-white/5 rounded -mx-1 px-1",
        )}
        onClick={isExpandable ? toggle : undefined}
      >
        {isExpandable ? (
          <span className="text-muted-foreground w-4 shrink-0 flex items-center justify-center">
            {expanded ? (
              <ChevronDown className="h-3 w-3" />
            ) : (
              <ChevronRight className="h-3 w-3" />
            )}
          </span>
        ) : (
          <span className="w-4" />
        )}
        {keyName !== undefined && (
          <>
            <span className="text-purple-400">{`"${keyName}"`}</span>
            <span className="text-muted-foreground">: </span>
          </>
        )}
        <span className="text-muted-foreground">{bracketOpen}</span>
        {!expanded && (
          <>
            <span className="text-muted-foreground/60 text-2xs">
              {isEmpty
                ? ""
                : type === "object"
                  ? `${entries.length} ${entries.length === 1 ? "key" : "keys"}`
                  : `${entries.length} ${entries.length === 1 ? "item" : "items"}`}
            </span>
            <span className="text-muted-foreground">{bracketClose}</span>
          </>
        )}
      </div>
      {expanded && (
        <>
          <div className="ml-4 border-l border-border/30 pl-2">
            {entries.map(([key, val], idx) => (
              <JsonNode
                key={`${key}-${idx}`}
                keyName={type === "object" ? String(key) : undefined}
                value={val}
                depth={depth + 1}
                defaultExpanded={false}
              />
            ))}
            {isEmpty && (
              <span className="text-muted-foreground/50 py-0.5 block">
                empty
              </span>
            )}
          </div>
          <div className="flex items-center gap-1">
            <span className="w-4" />
            <span className="text-muted-foreground">{bracketClose}</span>
          </div>
        </>
      )}
    </div>
  );
}

interface ValueDisplayProps {
  value: unknown;
  type: string;
}

function ValueDisplay({ value, type }: ValueDisplayProps) {
  switch (type) {
    case "string":
      return (
        <span className="text-emerald-400">
          {`"${truncateString(String(value), 500)}"`}
        </span>
      );
    case "number":
      return <span className="text-amber-400">{String(value)}</span>;
    case "boolean":
      return <span className="text-blue-400">{String(value)}</span>;
    case "null":
      return <span className="text-red-400/70">null</span>;
    case "undefined":
      return <span className="text-muted-foreground">undefined</span>;
    default:
      return <span className="text-muted-foreground">{String(value)}</span>;
  }
}

function getType(value: unknown): string {
  if (value === null) return "null";
  if (value === undefined) return "undefined";
  if (Array.isArray(value)) return "array";
  return typeof value;
}

function truncateString(str: string, maxLength: number): string {
  if (str.length <= maxLength) return str;
  return str.slice(0, maxLength) + "…";
}
