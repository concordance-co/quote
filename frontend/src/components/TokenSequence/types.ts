import type { BranchinessMetrics } from "./utils";

// Token or marker in the sequence
export type SequenceItem =
  | {
      type: "token";
      token: number;
      token_text: string;
      step: number;
      forced: boolean;
      erased: boolean;
      sequenceOrder: number;
      flatness: number | null;
      /** Entropy of the distribution in bits */
      entropy: number | null;
      /** Probability of this token (from top_tokens) */
      prob: number | null;
      /** 1-based index in top_tokens (k-index) */
      kIndex: number | null;
      /** Combined branchiness score (0-1) indicating trajectory importance */
      branchiness: number | null;
      /** Detailed branchiness metrics for advanced analysis */
      branchinessMetrics: BranchinessMetrics | null;
    }
  | {
      type: "backtrack";
      n: number;
      step: number;
      sequenceOrder: number;
    };

export interface TimelineSnapshot {
  sequenceOrder: number;
  items: SequenceItem[];
}

// Hovered token info for shared tooltip
export interface HoveredToken {
  item: Extract<SequenceItem, { type: "token" }>;
  rect: DOMRect;
}

// Filter mode for token display
export type FilterMode = "all" | "forced" | "sampled";

// Color mode for token display
export type TokenColorMode =
  | "flatness"
  | "branchiness"
  | "probability"
  | "entropy";
