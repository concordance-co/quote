import { useMemo } from "react";
import type { LogResponse, ActionLog, EventLog, TopToken } from "@/types/api";
import type { SequenceItem, TimelineSnapshot } from "./types";
import { calculateFlatness, calculateBranchiness } from "./utils";
import type { BranchinessMetrics } from "./utils";

interface UseTokenTimelineResult {
  timeline: TimelineSnapshot[];
  maxSequenceOrder: number;
}

/**
 * Hook to build a token timeline from log data.
 * Processes events and actions to create a sequence of snapshots
 * showing the token sequence at each point in time.
 */
export function useTokenTimeline(log: LogResponse): UseTokenTimelineResult {
  return useMemo(() => {
    const events = log.events || [];
    const actions = log.actions || [];
    const modCalls = log.mod_calls || [];

    // Sort events by sequence_order
    const sortedEvents = [...events].sort(
      (a, b) => a.sequence_order - b.sequence_order,
    );

    // Build lookup: step -> Sampled event (for getting token_text of sampled tokens)
    const stepToSampledEvent = new Map<number, EventLog>();
    for (const event of events) {
      if (event.event_type === "Sampled" && event.token_text) {
        stepToSampledEvent.set(event.step, event);
      }
    }

    // Build lookup: step -> ForwardPass event (to find associated mod_calls/actions)
    const stepToForwardPass = new Map<number, EventLog>();
    for (const event of events) {
      if (event.event_type === "ForwardPass") {
        stepToForwardPass.set(event.step, event);
      }
    }

    // Build lookup: step -> actions (via mod_calls)
    const stepToActions = new Map<number, ActionLog[]>();
    for (const mc of modCalls) {
      const mcActions = actions.filter((a) => a.mod_id === mc.id);
      if (mcActions.length > 0) {
        const existing = stepToActions.get(mc.step) || [];
        stepToActions.set(mc.step, [...existing, ...mcActions]);
      }
    }

    // Also index actions directly if they have no mod_call link
    for (const action of actions) {
      if (!action.mod_id) {
        const step = action.step_index;
        if (step !== null) {
          const existing = stepToActions.get(step) || [];
          if (!existing.includes(action)) {
            stepToActions.set(step, [...existing, action]);
          }
        }
      }
    }

    // Helper function to get flatness for a step from ForwardPass event
    const getFlatnessForStep = (step: number): number | null => {
      const fpEvent = stepToForwardPass.get(step);
      if (fpEvent?.top_tokens && Array.isArray(fpEvent.top_tokens)) {
        return calculateFlatness(fpEvent.top_tokens as TopToken[]);
      }
      return null;
    };

    // Helper function to get entropy (in bits) for a step from ForwardPass event
    const getEntropyForStep = (step: number): number | null => {
      const fpEvent = stepToForwardPass.get(step);
      if (fpEvent?.top_tokens && Array.isArray(fpEvent.top_tokens)) {
        const topTokens = fpEvent.top_tokens as TopToken[];
        if (topTokens.length < 2) return null;

        // Convert logprobs to probabilities
        const probs = topTokens.map((t) => Math.exp(t.logprob));
        const totalProb = probs.reduce((a, b) => a + b, 0);
        const normalizedProbs = probs.map((p) => p / totalProb);

        // Calculate entropy in bits
        let entropy = 0;
        for (const p of normalizedProbs) {
          if (p > 0) {
            entropy -= p * Math.log2(p);
          }
        }
        return entropy;
      }
      return null;
    };

    // Helper function to get branchiness metrics for a step from ForwardPass event
    const getBranchinessForStep = (
      step: number,
    ): {
      branchiness: number | null;
      branchinessMetrics: BranchinessMetrics | null;
    } => {
      const fpEvent = stepToForwardPass.get(step);
      if (fpEvent?.top_tokens && Array.isArray(fpEvent.top_tokens)) {
        const metrics = calculateBranchiness(fpEvent.top_tokens as TopToken[]);
        if (metrics) {
          return {
            branchiness: metrics.branchiness,
            branchinessMetrics: metrics,
          };
        }
      }
      return { branchiness: null, branchinessMetrics: null };
    };

    // Helper function to get probability and k-index for a sampled token
    const getProbAndKIndex = (
      step: number,
      tokenId: number,
    ): { prob: number | null; kIndex: number | null } => {
      const fpEvent = stepToForwardPass.get(step);
      if (!fpEvent?.top_tokens || !Array.isArray(fpEvent.top_tokens)) {
        return { prob: null, kIndex: null };
      }

      const topTokens = fpEvent.top_tokens as TopToken[];
      const index = topTokens.findIndex((t) => t.token === tokenId);

      if (index === -1) {
        return { prob: null, kIndex: null };
      }

      const token = topTokens[index];
      // Calculate probability from logprob if prob not directly available
      const prob = token.prob ?? Math.exp(token.logprob);

      return {
        prob,
        kIndex: index + 1, // 1-based index for UI
      };
    };

    // Helper function to get actions for a specific event (by event_id via mod_calls)
    const getActionsForEvent = (event: EventLog): ActionLog[] => {
      const result: ActionLog[] = [];

      // Find mod_calls linked to this event
      const eventModCalls = modCalls.filter((mc) => mc.event_id === event.id);

      // Find actions via mod_id matching
      for (const mc of eventModCalls) {
        const mcActions = actions.filter((a) => a.mod_id === mc.id);
        for (const action of mcActions) {
          if (!result.includes(action)) {
            result.push(action);
          }
        }
      }

      // Also find actions by step_index that aren't already linked via mod_calls
      const linkedModIds = new Set(eventModCalls.map((mc) => mc.id));
      for (const action of actions) {
        if (
          action.step_index === event.step &&
          (action.mod_id === null || !linkedModIds.has(action.mod_id))
        ) {
          if (!result.includes(action)) {
            result.push(action);
          }
        }
      }

      return result;
    };

    // Helper function to get actions for a step (matching TraceTree logic)
    const getActionsForStep = (step: number): ActionLog[] => {
      const result: ActionLog[] = [];

      // Find ALL mod_calls at this step (not just those linked to ForwardPass)
      // This is critical: mod_calls may be linked to different event types at the same step
      const stepModCalls = modCalls.filter((mc) => mc.step === step);

      // Find actions via mod_id matching for all mod_calls at this step
      for (const mc of stepModCalls) {
        const mcActions = actions.filter((a) => a.mod_id === mc.id);
        for (const action of mcActions) {
          if (!result.includes(action)) {
            result.push(action);
          }
        }
      }

      // Also find actions by step_index that aren't already linked via mod_calls
      const linkedModIds = new Set(stepModCalls.map((mc) => mc.id));
      for (const action of actions) {
        if (
          action.step_index === step &&
          (action.mod_id === null || !linkedModIds.has(action.mod_id))
        ) {
          if (!result.includes(action)) {
            result.push(action);
          }
        }
      }

      return result;
    };

    // Build timeline snapshots
    const snapshots: TimelineSnapshot[] = [];
    let currentItems: SequenceItem[] = [];
    let maxSeqOrder = 0;

    // Track which backtrack actions we've already processed (by action_id)
    const processedBacktrackActions = new Set<number>();

    // Track which ForceTokens/ForceOutput actions have been processed
    const processedForceActions = new Set<number>();

    // Helper to process a backtrack action for a given event
    const processBacktrack = (
      backtrackAction: ActionLog,
      event: EventLog,
    ): boolean => {
      if (processedBacktrackActions.has(backtrackAction.action_id)) {
        return false;
      }
      processedBacktrackActions.add(backtrackAction.action_id);

      const n = (backtrackAction.payload?.backtrack_steps ||
        backtrackAction.payload?.n ||
        0) as number;

      if (n > 0) {
        // Mark last N tokens as erased
        let eraseCount = 0;
        for (let i = currentItems.length - 1; i >= 0 && eraseCount < n; i--) {
          const item = currentItems[i];
          if (item.type === "token" && !item.erased) {
            currentItems[i] = { ...item, erased: true };
            eraseCount++;
          }
        }

        // Add backtrack marker
        currentItems.push({
          type: "backtrack",
          n,
          step: event.step,
          sequenceOrder: event.sequence_order,
        });

        // Check if the backtrack action also has forced tokens to add
        const backtrackTokens = backtrackAction.payload?.tokens as
          | number[]
          | undefined;
        const backtrackTokensAsText = backtrackAction.payload
          ?.tokens_as_text as string[] | undefined;

        if (backtrackTokens && backtrackTokens.length > 0) {
          const textArray = Array.isArray(backtrackTokensAsText)
            ? backtrackTokensAsText.map(String)
            : [];

          backtrackTokens.forEach((tokenId, idx) => {
            const tokenText = textArray[idx] || `[${tokenId}]`;
            currentItems.push({
              type: "token",
              token: tokenId,
              token_text: tokenText,
              step: event.step,
              forced: true,
              erased: false,
              sequenceOrder: event.sequence_order,
              flatness: null,
              entropy: null,
              prob: null,
              kIndex: null,
              branchiness: null,
              branchinessMetrics: null,
            });
          });
        }

        // Snapshot after backtrack (and any associated forced tokens)
        snapshots.push({
          sequenceOrder: event.sequence_order,
          items: [...currentItems],
        });

        return true;
      }
      return false;
    };

    for (const event of sortedEvents) {
      maxSeqOrder = Math.max(maxSeqOrder, event.sequence_order);

      // Get actions linked to this event
      const eventActions = getActionsForEvent(event);
      const backtrackActions = eventActions.filter(
        (a) => a.action_type === "Backtrack",
      );

      // For ForwardPass events: process backtracks BEFORE tokens are added
      if (event.event_type === "ForwardPass") {
        for (const backtrackAction of backtrackActions) {
          processBacktrack(backtrackAction, event);
        }
      }

      // Process Added events for tokens
      if (event.event_type === "Added" && event.added_tokens) {
        // Get actions for this step for token text lookup
        const stepActions = getActionsForStep(event.step);

        // Find action with tokens_as_text for this step (for forced tokens)
        let tokensAction = stepActions.find(
          (a) =>
            (a.action_type === "ForceTokens" ||
              a.action_type === "ForceOutput" ||
              a.action_type === "AdjustedPrefill") &&
            a.payload?.tokens_as_text &&
            !processedForceActions.has(a.action_id),
        );

        // Also check actions linked directly to THIS Added event via mod_calls
        // This handles cases where mod_call.event_id points to the Added event
        // but event.forced may be false
        if (!tokensAction) {
          const addedEventActions = getActionsForEvent(event);
          tokensAction = addedEventActions.find(
            (a) =>
              (a.action_type === "ForceTokens" ||
                a.action_type === "ForceOutput" ||
                a.action_type === "AdjustedPrefill") &&
              a.payload?.tokens_as_text &&
              !processedForceActions.has(a.action_id),
          );
        }

        // If still not found and event is forced, search all ForceTokens/ForceOutput actions by matching token arrays
        if (!tokensAction && event.forced && event.added_tokens) {
          tokensAction = actions.find(
            (a) =>
              (a.action_type === "ForceTokens" ||
                a.action_type === "ForceOutput" ||
                a.action_type === "AdjustedPrefill") &&
              a.payload?.tokens_as_text &&
              a.payload?.tokens &&
              !processedForceActions.has(a.action_id) &&
              Array.isArray(a.payload.tokens) &&
              a.payload.tokens.length === event.added_tokens!.length &&
              (a.payload.tokens as number[]).every(
                (t: number, i: number) => t === event.added_tokens![i],
              ),
          );
        }

        // Mark action as processed if found
        if (tokensAction) {
          processedForceActions.add(tokensAction.action_id);
        }

        // Get tokens_as_text array from action payload (for forced tokens)
        const tokensAsText = tokensAction?.payload?.tokens_as_text;
        const textArray: string[] = Array.isArray(tokensAsText)
          ? tokensAsText.map(String)
          : typeof tokensAsText === "string"
            ? [tokensAsText]
            : [];

        // Determine which tokens to add:
        // If we have a ForceTokens/ForceOutput action with its own tokens array,
        // use those tokens instead of event.added_tokens (which may be incomplete)
        const actionTokens = tokensAction?.payload?.tokens;
        const tokensToAdd: number[] =
          tokensAction && Array.isArray(actionTokens) && actionTokens.length > 0
            ? (actionTokens as number[])
            : event.added_tokens;

        // Determine how many tokens from event.added_tokens were naturally added
        // Tokens beyond this count are forced (from the ForceTokens/ForceOutput action)
        const naturalTokenCount = event.added_tokens.length;
        const hasForceAction =
          tokensAction !== undefined &&
          (tokensAction.action_type === "ForceTokens" ||
            tokensAction.action_type === "ForceOutput");

        // Helper to determine if a token at a given index is forced
        const isTokenForced = (idx: number): boolean => {
          if (event.forced) {
            // If the event itself is forced, all tokens are forced
            return true;
          }
          if (hasForceAction && idx >= naturalTokenCount) {
            // Tokens beyond the natural count are forced by the action
            return true;
          }
          return false;
        };

        // For sampled (non-forced) tokens, look up the Sampled event at this step
        const sampledEvent = stepToSampledEvent.get(event.step);

        // Add new tokens
        tokensToAdd.forEach((tokenId, idx) => {
          const forced = isTokenForced(idx);
          let tokenText: string;

          if (forced && textArray[idx]) {
            // Forced token with per-token text from action
            tokenText = textArray[idx];
          } else if (forced && event.token_text) {
            // Forced token with combined text from event
            tokenText = idx === 0 ? event.token_text : `[${tokenId}]`;
          } else if (!forced && sampledEvent?.token_text) {
            // Sampled token - use token_text from Sampled event
            tokenText = sampledEvent.token_text;
          } else if (!forced && textArray[idx]) {
            // Non-forced token but we have text from action (first token overlap case)
            tokenText = textArray[idx];
          } else {
            // Fallback to token ID
            tokenText = `[${tokenId}]`;
          }

          // Get flatness, entropy, prob, kIndex, and branchiness for sampled (non-forced) tokens
          const flatness = !forced ? getFlatnessForStep(event.step) : null;
          const entropy = !forced ? getEntropyForStep(event.step) : null;
          const { prob, kIndex } = !forced
            ? getProbAndKIndex(event.step, tokenId)
            : { prob: null, kIndex: null };
          const { branchiness, branchinessMetrics } = !forced
            ? getBranchinessForStep(event.step)
            : { branchiness: null, branchinessMetrics: null };

          currentItems.push({
            type: "token",
            token: tokenId,
            token_text: tokenText,
            step: event.step,
            forced,
            erased: false,
            sequenceOrder: event.sequence_order,
            flatness,
            entropy,
            prob,
            kIndex,
            branchiness,
            branchinessMetrics,
          });
        });

        // Snapshot after adding tokens
        snapshots.push({
          sequenceOrder: event.sequence_order,
          items: [...currentItems],
        });

        // For Added events: process backtracks AFTER tokens are added
        for (const backtrackAction of backtrackActions) {
          processBacktrack(backtrackAction, event);
        }
      }

      // For Sampled events: process backtracks AFTER
      if (event.event_type === "Sampled") {
        for (const backtrackAction of backtrackActions) {
          processBacktrack(backtrackAction, event);
        }
      }
    }

    // Process ForceTokens actions that weren't handled via Added events
    const forceTokensActions = actions.filter(
      (a) =>
        a.action_type === "ForceTokens" &&
        a.payload?.tokens_as_text &&
        !processedForceActions.has(a.action_id),
    );

    for (const ftAction of forceTokensActions) {
      const tokensAsText = ftAction.payload?.tokens_as_text;
      const textArray: string[] = Array.isArray(tokensAsText)
        ? tokensAsText.map(String)
        : typeof tokensAsText === "string"
          ? [tokensAsText]
          : [];

      const tokenIds = ftAction.payload?.tokens as number[] | undefined;

      // Check if the first forced token matches the last token in currentItems
      // If so, it was already added via an Added event and should be treated as a normal added token
      let startIdx = 0;
      if (tokenIds && tokenIds.length > 0 && currentItems.length > 0) {
        const lastItem = currentItems[currentItems.length - 1];
        if (lastItem.type === "token" && lastItem.token === tokenIds[0]) {
          // First forced token matches last added token - skip it (already added)
          startIdx = 1;
        }
      }

      // Add ForceTokens tokens
      let addedAny = false;
      textArray.forEach((tokenText, idx) => {
        // Skip tokens before startIdx (they were already added via Added event)
        if (idx < startIdx) {
          return;
        }

        const tokenId = tokenIds?.[idx] ?? -1;

        currentItems.push({
          type: "token",
          token: tokenId,
          token_text: tokenText,
          step: ftAction.step_index ?? maxSeqOrder,
          forced: true,
          erased: false,
          sequenceOrder: maxSeqOrder + 1,
          flatness: null,
          entropy: null,
          prob: null,
          kIndex: null,
          branchiness: null,
          branchinessMetrics: null,
        });
        addedAny = true;
      });

      if (addedAny) {
        maxSeqOrder = maxSeqOrder + 1;
        snapshots.push({
          sequenceOrder: maxSeqOrder,
          items: [...currentItems],
        });
      }

      // Mark as processed
      processedForceActions.add(ftAction.action_id);
    }

    // Process ForceOutput actions that may not have corresponding Added events
    const forceOutputActions = actions.filter(
      (a) =>
        a.action_type === "ForceOutput" &&
        a.payload?.tokens_as_text &&
        !processedForceActions.has(a.action_id),
    );

    for (const foAction of forceOutputActions) {
      const tokensAsText = foAction.payload?.tokens_as_text;
      const textArray: string[] = Array.isArray(tokensAsText)
        ? tokensAsText.map(String)
        : typeof tokensAsText === "string"
          ? [tokensAsText]
          : [];

      const tokenIds = foAction.payload?.tokens as number[] | undefined;

      // Check if the first forced token matches the last token in currentItems
      // If so, it was already added via an Added event and should be treated as a normal added token
      let startIdx = 0;
      if (tokenIds && tokenIds.length > 0 && currentItems.length > 0) {
        const lastItem = currentItems[currentItems.length - 1];
        if (lastItem.type === "token" && lastItem.token === tokenIds[0]) {
          // First forced token matches last added token - skip it (already added)
          startIdx = 1;
        }
      }

      // Add ForceOutput tokens
      let addedAny = false;
      textArray.forEach((tokenText, idx) => {
        // Skip tokens before startIdx (they were already added via Added event)
        if (idx < startIdx) {
          return;
        }

        const tokenId = tokenIds?.[idx] ?? -1;

        currentItems.push({
          type: "token",
          token: tokenId,
          token_text: tokenText,
          step: foAction.step_index ?? maxSeqOrder,
          forced: true,
          erased: false,
          sequenceOrder: maxSeqOrder + 1,
          flatness: null,
          entropy: null,
          prob: null,
          kIndex: null,
          branchiness: null,
          branchinessMetrics: null,
        });
        addedAny = true;
      });

      if (addedAny) {
        maxSeqOrder = maxSeqOrder + 1;
        snapshots.push({
          sequenceOrder: maxSeqOrder,
          items: [...currentItems],
        });
      }

      // Mark as processed
      processedForceActions.add(foAction.action_id);
    }

    return {
      timeline: snapshots,
      maxSequenceOrder: maxSeqOrder,
    };
  }, [log.events, log.actions, log.mod_calls]);
}
