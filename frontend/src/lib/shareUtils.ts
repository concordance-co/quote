import LZString from "lz-string";
import type { InjectionPosition } from "@/lib/api";

export interface ShareablePlaygroundConfig {
  model: string;
  maxTokens: number;
  temperature: number;
  systemPrompt: string;
  userPrompt: string;
  enableMod: boolean;
  injectionPosition: InjectionPosition;
  injectionString?: string;
  tokenCount?: number;
  sentenceCount?: number;
  detectPhrases?: string[];
  replacementPhrases?: string[];
}

/**
 * Compress playground config to URL-safe string using lz-string
 */
export function encodePlaygroundConfig(config: ShareablePlaygroundConfig): string {
  // Create a minimal object with only non-default/non-empty values
  const minimal: Record<string, unknown> = {
    m: config.model,
    mt: config.maxTokens,
    t: config.temperature,
    sp: config.systemPrompt,
    up: config.userPrompt,
    em: config.enableMod,
    ip: config.injectionPosition,
  };

  if (config.injectionString) {
    minimal.is = config.injectionString;
  }
  if (config.tokenCount !== undefined) {
    minimal.tc = config.tokenCount;
  }
  if (config.sentenceCount !== undefined) {
    minimal.sc = config.sentenceCount;
  }
  if (config.detectPhrases && config.detectPhrases.some((p) => p.trim())) {
    minimal.dp = config.detectPhrases;
  }
  if (config.replacementPhrases && config.replacementPhrases.some((p) => p.trim())) {
    minimal.rp = config.replacementPhrases;
  }

  const json = JSON.stringify(minimal);
  // Use base64 encoding for URL safety
  return LZString.compressToEncodedURIComponent(json);
}

/**
 * Decode playground config from URL-safe compressed string
 */
export function decodePlaygroundConfig(
  encoded: string
): ShareablePlaygroundConfig | null {
  try {
    const json = LZString.decompressFromEncodedURIComponent(encoded);
    if (!json) return null;

    const minimal = JSON.parse(json) as Record<string, unknown>;

    const config: ShareablePlaygroundConfig = {
      model: (minimal.m as string) || "llama-3.1-8b",
      maxTokens: (minimal.mt as number) || 256,
      temperature: (minimal.t as number) ?? 0.7,
      systemPrompt: (minimal.sp as string) || "You are a helpful assistant.",
      userPrompt: (minimal.up as string) || "",
      enableMod: (minimal.em as boolean) ?? true,
      injectionPosition: (minimal.ip as InjectionPosition) || "phrase_replace",
    };

    if (minimal.is !== undefined) {
      config.injectionString = minimal.is as string;
    }
    if (minimal.tc !== undefined) {
      config.tokenCount = minimal.tc as number;
    }
    if (minimal.sc !== undefined) {
      config.sentenceCount = minimal.sc as number;
    }
    if (minimal.dp !== undefined) {
      config.detectPhrases = minimal.dp as string[];
    }
    if (minimal.rp !== undefined) {
      config.replacementPhrases = minimal.rp as string[];
    }

    return config;
  } catch {
    console.error("Failed to decode playground config");
    return null;
  }
}

/**
 * Build full share URL with encoded config
 */
export function buildShareUrl(config: ShareablePlaygroundConfig): string {
  const encoded = encodePlaygroundConfig(config);
  const baseUrl = typeof window !== "undefined" ? window.location.origin : "";
  return `${baseUrl}/playground?s=${encoded}`;
}

/**
 * Get config from current URL if present
 */
export function getConfigFromUrl(): ShareablePlaygroundConfig | null {
  if (typeof window === "undefined") return null;

  const params = new URLSearchParams(window.location.search);
  const encoded = params.get("s");
  if (!encoded) return null;

  return decodePlaygroundConfig(encoded);
}

/**
 * Build Twitter share intent URL
 */
export function buildTwitterShareUrl(shareUrl: string, text?: string): string {
  const defaultText =
    "Check out this token injection experiment on Concordance!";
  const tweetText = text || defaultText;

  const params = new URLSearchParams({
    text: tweetText,
    url: shareUrl,
  });

  return `https://twitter.com/intent/tweet?${params.toString()}`;
}
