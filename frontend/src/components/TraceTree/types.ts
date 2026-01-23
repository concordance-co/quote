import type {
  EventLog,
  ModCallLog,
  ModLogEntry,
  ActionLog,
  LogResponse,
} from "@/types/api";

// Reference to a trace element for comments
export interface TraceReference {
  step: number;
  eventType: string;
  eventId: number;
  label: string;
}

export interface TraceTreeProps {
  log: LogResponse;
  selectedStep: number | null;
  onSelectStep: (step: number | null) => void;
  requestId: string;
  onCommentAdded?: () => void;
}

// Mod call with its associated logs
export interface ModCallWithLogs {
  modCall: ModCallLog;
  logs: ModLogEntry[];
}

// Processed trace entry combining events with their mod calls and actions
export interface TraceEntry {
  id: string;
  event: EventLog;
  modCalls: ModCallWithLogs[];
  actions: ActionLog[];
  isLast: boolean;
  isFirstInStep: boolean;
  isLastInStep: boolean;
}

export interface TraceEntryRowProps {
  entry: TraceEntry;
  expanded: boolean;
  expandedNodes: Set<string>;
  expandedDetails: Set<string>;
  onToggle: (id: string) => void;
  onToggleDetails: (id: string) => void;
  selectedStep: number | null;
  registerStepRef: (step: number, element: HTMLDivElement | null) => void;
  requestId: string;
  isCommenting: boolean;
  onStartComment: () => void;
  onCancelComment: () => void;
  onCommentAdded: () => void;
}

export interface InlineCommentFormProps {
  requestId: string;
  reference: TraceReference;
  onCancel: () => void;
  onSubmitted: () => void;
}

export interface ModCallCardProps {
  mc: ModCallWithLogs;
  expanded: boolean;
  showDetails: boolean;
  onToggle: () => void;
  onToggleDetails: () => void;
}

export interface ActionCardProps {
  action: ActionLog;
  showDetails: boolean;
  onToggleDetails: () => void;
}

// Badge style configuration
export interface BadgeStyle {
  bg: string;
  text: string;
  border?: string;
}
