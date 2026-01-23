// Trace Reference format: [[trace:step:eventId:eventType:label]]
// Example: [[trace:19:1234:Prefilled:Step 19 - Prefilled]]

export interface TraceReference {
  step: number;
  eventType: string;
  eventId: number;
  label: string;
}

// Log Reference format: [[log:logId:step:modName:logLevel:truncatedMessage]]
// Example: [[log:5678:19:my_mod:INFO:Processing token...]]

export interface LogReference {
  logId: number;
  step: number | null;
  modName: string;
  logLevel: string;
  truncatedMessage: string;
}

// Chart Reference format: [[chart:chartId:chartTitle]]
// Example: [[chart:probability:Added Token Probability (Sampled Only)]]

export interface ChartReference {
  chartId: string;
  chartTitle: string;
}

export function formatTraceReference(ref: TraceReference): string {
  return `[[trace:${ref.step}:${ref.eventId}:${ref.eventType}:${ref.label}]]`;
}

export function parseTraceReference(text: string): TraceReference | null {
  const match = text.match(/\[\[trace:(\d+):(\d+):([^:]+):([^\]]+)\]\]/);
  if (match) {
    return {
      step: parseInt(match[1], 10),
      eventId: parseInt(match[2], 10),
      eventType: match[3],
      label: match[4],
    };
  }
  return null;
}

export function parseAllTraceReferences(
  text: string,
): { ref: TraceReference; start: number; end: number }[] {
  const regex = /\[\[trace:(\d+):(\d+):([^:]+):([^\]]+)\]\]/g;
  const matches: { ref: TraceReference; start: number; end: number }[] = [];
  let match;

  while ((match = regex.exec(text)) !== null) {
    matches.push({
      ref: {
        step: parseInt(match[1], 10),
        eventId: parseInt(match[2], 10),
        eventType: match[3],
        label: match[4],
      },
      start: match.index,
      end: match.index + match[0].length,
    });
  }

  return matches;
}

export function formatLogReference(ref: LogReference): string {
  const safeMessage = ref.truncatedMessage.replace(/[\]:|]/g, "_");
  return `[[log:${ref.logId}:${ref.step ?? "null"}:${ref.modName}:${ref.logLevel}:${safeMessage}]]`;
}

export function parseLogReference(text: string): LogReference | null {
  const match = text.match(
    /\[\[log:(\d+):(\d+|null):([^:]+):([^:]+):([^\]]+)\]\]/,
  );
  if (match) {
    return {
      logId: parseInt(match[1], 10),
      step: match[2] === "null" ? null : parseInt(match[2], 10),
      modName: match[3],
      logLevel: match[4],
      truncatedMessage: match[5],
    };
  }
  return null;
}

export function parseAllLogReferences(
  text: string,
): { ref: LogReference; start: number; end: number }[] {
  const regex = /\[\[log:(\d+):(\d+|null):([^:]+):([^:]+):([^\]]+)\]\]/g;
  const matches: { ref: LogReference; start: number; end: number }[] = [];
  let match;

  while ((match = regex.exec(text)) !== null) {
    matches.push({
      ref: {
        logId: parseInt(match[1], 10),
        step: match[2] === "null" ? null : parseInt(match[2], 10),
        modName: match[3],
        logLevel: match[4],
        truncatedMessage: match[5],
      },
      start: match.index,
      end: match.index + match[0].length,
    });
  }

  return matches;
}

export function formatChartReference(ref: ChartReference): string {
  const safeTitle = ref.chartTitle.replace(/[\]:|]/g, "_");
  return `[[chart:${ref.chartId}:${safeTitle}]]`;
}

export function parseChartReference(text: string): ChartReference | null {
  const match = text.match(/\[\[chart:([^:]+):([^\]]+)\]\]/);
  if (match) {
    return {
      chartId: match[1],
      chartTitle: match[2],
    };
  }
  return null;
}

export function parseAllChartReferences(
  text: string,
): { ref: ChartReference; start: number; end: number }[] {
  const regex = /\[\[chart:([^:]+):([^\]]+)\]\]/g;
  const matches: { ref: ChartReference; start: number; end: number }[] = [];
  let match;

  while ((match = regex.exec(text)) !== null) {
    matches.push({
      ref: {
        chartId: match[1],
        chartTitle: match[2],
      },
      start: match.index,
      end: match.index + match[0].length,
    });
  }

  return matches;
}
