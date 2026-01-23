import { forwardRef } from "react";
import type { InjectionPosition } from "@/lib/api";

// Token data for display
export interface TokenDisplayData {
  text: string;
  forced: boolean;
  prob: number | null;
}

interface ShareableCardProps {
  model: string;
  maxTokens: number;
  temperature?: number;
  systemPrompt: string;
  userPrompt: string;
  injectionPosition?: InjectionPosition;
  injectionString?: string;
  tokenCount?: number;
  sentenceCount?: number;
  detectPhrases?: string[];
  replacementPhrases?: string[];
  outputText: string;
  shareUrl: string;
  tokens: TokenDisplayData[];
  showUncertainty?: boolean; // Default false - only highlight forced tokens
  showInjection?: boolean; // Default true for playground, false for log view
}

// Get descriptive position label
function getPositionLabel(
  position: InjectionPosition,
  tokenCount?: number,
  sentenceCount?: number
): string {
  switch (position) {
    case "start":
      return "Start of Generation";
    case "after_tokens":
      return tokenCount ? `After ${tokenCount} Tokens` : "After N Tokens";
    case "after_sentences":
      return sentenceCount ? `After ${sentenceCount} Sentences` : "After N Sentences";
    case "eot_backtrack":
      return "EOT Backtrack";
    case "phrase_replace":
      return "Phrase Replacement";
    case "reasoning_start":
      return "Start of Reasoning";
    case "reasoning_mid":
      return "Mid Reasoning";
    case "reasoning_end":
      return "End of Reasoning";
    case "response_start":
      return "Start of Response";
    case "response_mid":
      return "Mid Response";
    case "response_end":
      return "End of Response";
    case "reasoning_phrase_replace":
      return "Reasoning Phrase Replacement";
    case "response_phrase_replace":
      return "Response Phrase Replacement";
    case "full_stream_phrase_replace":
      return "Full Stream Phrase Replacement";
    default:
      return position;
  }
}

// Truncate text with ellipsis
function truncate(text: string, maxLen: number): string {
  if (text.length <= maxLen) return text;
  return text.slice(0, maxLen - 3) + "...";
}

// Get model display name
function getModelDisplay(model: string): string {
  const lower = model.toLowerCase();

  // Extract just the model name from paths like "Qwen/Qwen3-14B-GGUF/playground_mod"
  if (lower.includes("llama")) {
    if (lower.includes("70b")) return "llama-3.1-70b";
    if (lower.includes("8b")) return "llama-3.1-8b";
    return "llama-3.1";
  }
  if (lower.includes("qwen")) {
    if (lower.includes("32b")) return "qwen-32b";
    if (lower.includes("14b")) return "qwen-14b";
    if (lower.includes("7b")) return "qwen-7b";
    return "qwen";
  }
  if (lower.includes("deepseek")) return "deepseek";
  if (lower.includes("mistral")) return "mistral";

  // Fallback: get the last path segment and truncate if needed
  const segments = model.split("/");
  const name = segments[segments.length - 1] || model;
  return name.length > 20 ? name.slice(0, 17) + "..." : name;
}

// Get probability color (white = confident, orange/red = uncertain)
function getProbabilityColor(prob: number | null): string {
  if (prob === null) return "#e5e5e5"; // neutral white-ish

  // Color stops: white -> orange -> red
  const white = { r: 245, g: 245, b: 245 }; // near white
  const orange = { r: 251, g: 146, b: 60 }; // orange-400
  const red = { r: 248, g: 113, b: 113 }; // red-400

  let r: number, g: number, b: number;

  if (prob >= 0.7) {
    // High confidence = white
    r = white.r; g = white.g; b = white.b;
  } else if (prob >= 0.3) {
    // Medium confidence = fade to orange
    const t = (0.7 - prob) / 0.4;
    r = Math.round(white.r + (orange.r - white.r) * t);
    g = Math.round(white.g + (orange.g - white.g) * t);
    b = Math.round(white.b + (orange.b - white.b) * t);
  } else {
    // Low confidence = orange to red
    const t = Math.min(1, (0.3 - prob) / 0.25);
    r = Math.round(orange.r + (red.r - orange.r) * t);
    g = Math.round(orange.g + (red.g - orange.g) * t);
    b = Math.round(orange.b + (red.b - orange.b) * t);
  }

  return `rgb(${r}, ${g}, ${b})`;
}

/**
 * Visual card component optimized for screenshot capture.
 * Dimensions: 1200x628px (Twitter card aspect ratio)
 * Styling: Lab theme (dark bg, cyan accents, IBM Plex Mono font)
 */
export const ShareableCard = forwardRef<HTMLDivElement, ShareableCardProps>(
  (
    {
      model,
      maxTokens,
      temperature,
      systemPrompt,
      userPrompt,
      injectionPosition,
      injectionString,
      tokenCount,
      sentenceCount,
      detectPhrases,
      replacementPhrases,
      outputText,
      shareUrl,
      tokens,
      showUncertainty = false,
      showInjection = true,
    },
    ref
  ) => {
    const isPhraseReplace = injectionPosition?.includes("phrase_replace") ?? false;

    // Build phrase pairs for display
    const phrasePairs: Array<{ detect: string; replace: string }> = [];
    if (isPhraseReplace && detectPhrases) {
      detectPhrases.forEach((detect, i) => {
        if (detect.trim()) {
          phrasePairs.push({
            detect,
            replace: replacementPhrases?.[i] || detect,
          });
        }
      });
    }

    // Truncate the share URL for display
    const urlWithoutProtocol = shareUrl.replace(/^https?:\/\//, "");
    const displayUrl = urlWithoutProtocol.length > 50
      ? urlWithoutProtocol.slice(0, 50) + "..."
      : urlWithoutProtocol;

    // Use all tokens - let CSS handle overflow
    const hasTokenData = tokens.length > 0;

    return (
      <div
        ref={ref}
        style={{
          width: "1200px",
          height: "628px",
          fontFamily: "'IBM Plex Mono', 'Menlo', monospace",
          fontSize: "14px",
          lineHeight: "1.5",
        }}
        className="bg-[#0a0a0a] text-[#e5e5e5] flex flex-col overflow-hidden"
      >
        {/* Header */}
        <div className="flex items-center justify-between px-8 py-5 border-b border-[#262626]">
          <div className="flex items-center gap-3">
            <span className="text-emerald-400 text-xl">&#9699;</span>
            <span className="text-[20px] font-semibold tracking-wide text-white">
              {showInjection ? "TOKEN INJECTION LAB" : "INFERENCE LOG"}
            </span>
          </div>
          <span className="text-[16px] text-[#a3a3a3] tracking-wider">
            Concordance.co
          </span>
        </div>

        {/* Config Badges */}
        <div className="flex items-center gap-4 px-8 py-3 border-b border-[#262626]">
          <span className="px-3 py-1.5 bg-[#1a1a1a] border border-[#333] rounded text-[14px] text-emerald-400">
            {getModelDisplay(model)}
          </span>
          <span className="text-[#525252]">&#8226;</span>
          <span className="px-3 py-1.5 bg-[#1a1a1a] border border-[#333] rounded text-[14px] text-[#a3a3a3]">
            {maxTokens} tokens
          </span>
          {temperature !== undefined && (
            <>
              <span className="text-[#525252]">&#8226;</span>
              <span className="px-3 py-1.5 bg-[#1a1a1a] border border-[#333] rounded text-[14px] text-[#a3a3a3]">
                temp {temperature}
              </span>
            </>
          )}
        </div>

        {/* Prompts Section */}
        <div className="flex-1 px-8 py-4 flex flex-col gap-4 overflow-hidden">
          {/* User + System Prompts */}
          <div className="flex gap-10">
            <div className={systemPrompt ? "flex-1" : "flex-[2]"}>
              <div className="text-[13px] font-semibold tracking-wider text-[#737373] mb-1.5">
                USER
              </div>
              <div className="text-[17px] text-white leading-snug">
                {truncate(userPrompt, systemPrompt ? 55 : 120)}
              </div>
            </div>
            {systemPrompt && (
              <div className="flex-1">
                <div className="text-[13px] font-semibold tracking-wider text-[#737373] mb-1.5">
                  SYSTEM
                </div>
                <div className="text-[15px] text-[#a3a3a3] leading-snug">
                  {truncate(systemPrompt, 55)}
                </div>
              </div>
            )}
          </div>

          {/* Injection Config - Only shown for playground */}
          {showInjection && injectionPosition && (
            <div className="border-t border-b border-[#262626] py-4">
              <div className="flex items-center gap-3 mb-3">
                <span className="text-emerald-400 text-[22px]">&#9889;</span>
                <span className="text-[20px] font-semibold tracking-wide text-emerald-400">
                  INJECTION
                </span>
              </div>
              <div className="flex items-center gap-8 text-[17px]">
                <div>
                  <span className="text-[#737373]">POSITION: </span>
                  <span className="text-emerald-400">{getPositionLabel(injectionPosition, tokenCount, sentenceCount)}</span>
                </div>
                {isPhraseReplace && phrasePairs.length > 0 ? (
                  <div className="flex flex-wrap items-center gap-3">
                    <span className="text-[#737373]">REPLACE: </span>
                    {phrasePairs.slice(0, 2).map((pair, i) => (
                      <span
                        key={i}
                        className="text-[16px] px-3 py-1 bg-[#1a1a1a] border border-[#333] rounded"
                      >
                        <span className="text-[#f97316]">"{pair.detect}"</span>
                        <span className="text-[#525252] mx-2">→</span>
                        <span className="text-emerald-400">"{pair.replace}"</span>
                      </span>
                    ))}
                    {phrasePairs.length > 2 && (
                      <span className="text-[16px] text-[#525252]">
                        +{phrasePairs.length - 2} more
                      </span>
                    )}
                  </div>
                ) : injectionString ? (
                  <div>
                    <span className="text-[#737373]">STRING: </span>
                    <span className="text-emerald-400">"{truncate(injectionString, 35)}"</span>
                  </div>
                ) : null}
              </div>
            </div>
          )}

          {/* Output - Larger font with token coloring */}
          <div className="flex-1 overflow-hidden">
            <div className="text-[12px] font-semibold tracking-wider text-[#737373] mb-2">
              OUTPUT
            </div>
            <div
              className="text-[18px] leading-[1.65] overflow-hidden"
              style={{ maxHeight: showInjection ? "140px" : "240px" }}
            >
              {hasTokenData ? (
                // Render with token coloring - limit tokens to ~400 chars
                (() => {
                  let charCount = 0;
                  const maxChars = showInjection ? 350 : 600;
                  const displayTokens: typeof tokens = [];
                  let truncated = false;

                  for (const token of tokens) {
                    if (charCount + token.text.length > maxChars) {
                      truncated = true;
                      break;
                    }
                    displayTokens.push(token);
                    charCount += token.text.length;
                  }

                  return (
                    <>
                      <span className="text-[#525252]">"</span>
                      {displayTokens.map((token, i) => (
                        <span
                          key={i}
                          style={{
                            color: token.forced
                              ? "#f9a8d4" // pink for forced/injected
                              : showUncertainty
                                ? getProbabilityColor(token.prob)
                                : "#e5e5e5", // white when uncertainty off
                            backgroundColor: token.forced
                              ? "rgba(219, 39, 119, 0.25)"
                              : undefined,
                            padding: token.forced ? "1px 0" : undefined,
                            borderRadius: token.forced ? "2px" : undefined,
                          }}
                        >
                          {token.text}
                        </span>
                      ))}
                      {truncated && <span className="text-[#525252]">...</span>}
                      <span className="text-[#525252]">"</span>
                    </>
                  );
                })()
              ) : (
                // Fallback to plain text
                <span className="text-white">"{truncate(outputText, showInjection ? 350 : 600)}"</span>
              )}
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="px-8 py-4 border-t border-[#262626] bg-[#0f0f0f] flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="text-[14px] text-[#525252]">&#128279;</span>
            <span className="text-[14px] text-emerald-400">{displayUrl}</span>
          </div>
          {/* Legend */}
          <div className="flex items-center gap-5 text-[14px]">
            <span className="flex items-center gap-2">
              <span
                className="w-3 h-3 rounded border"
                style={{
                  backgroundColor: "rgba(219, 39, 119, 0.25)",
                  borderColor: "rgba(219, 39, 119, 0.5)"
                }}
              />
              <span className="text-[#f9a8d4] font-medium">injected</span>
            </span>
            {showUncertainty && (
              <>
                <span className="flex items-center gap-2">
                  <span className="w-3 h-3 rounded" style={{ backgroundColor: "rgb(251, 146, 60)" }} />
                  <span className="text-[#737373]">uncertain</span>
                </span>
                <span className="flex items-center gap-2">
                  <span className="w-3 h-3 rounded" style={{ backgroundColor: "rgb(248, 113, 113)" }} />
                  <span className="text-[#737373]">very uncertain</span>
                </span>
              </>
            )}
          </div>
        </div>
      </div>
    );
  }
);

ShareableCard.displayName = "ShareableCard";
