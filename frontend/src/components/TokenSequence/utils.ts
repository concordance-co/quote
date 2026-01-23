import type { TopToken } from "@/types/api";

// Re-export TopToken for use in calculateBranchiness parameter type
export type { TopToken };

/**
 * Calculate flatness (normalized entropy) of a probability distribution.
 * Returns a value from 0 to 1, where 1 = perfectly flat (uniform), 0 = peaked.
 */
export function calculateFlatness(topTokens: TopToken[]): number | null {
  if (!topTokens || topTokens.length < 2) return null;

  // Convert logprobs to probabilities
  const probs = topTokens.map((t) => Math.exp(t.logprob));
  const totalProb = probs.reduce((a, b) => a + b, 0);

  // Normalize probabilities
  const normalizedProbs = probs.map((p) => p / totalProb);

  // Calculate entropy
  let entropy = 0;
  for (const p of normalizedProbs) {
    if (p > 0) {
      entropy -= p * Math.log2(p);
    }
  }

  // Maximum entropy for this distribution size
  const maxEntropy = Math.log2(topTokens.length);

  // Normalized entropy (flatness) = entropy / maxEntropy
  return maxEntropy > 0 ? entropy / maxEntropy : null;
}

/**
 * Get a continuous color for flatness value (0-1).
 * Interpolates: green (0%) → blue (40%) → orange (75%) → red (90%+)
 */
export function getFlatnessColor(flatness: number): string {
  // Color stops
  const green = { r: 16, g: 185, b: 129 }; // emerald-500
  const blue = { r: 59, g: 130, b: 246 }; // blue-500
  const orange = { r: 245, g: 158, b: 11 }; // amber-500
  const red = { r: 239, g: 68, b: 68 }; // red-500

  let r: number, g: number, b: number;

  if (flatness <= 0.4) {
    // Interpolate from green to blue (0% to 40%)
    const t = flatness / 0.4;
    r = Math.round(green.r + (blue.r - green.r) * t);
    g = Math.round(green.g + (blue.g - green.g) * t);
    b = Math.round(green.b + (blue.b - green.b) * t);
  } else if (flatness <= 0.75) {
    // Interpolate from blue to orange (40% to 75%)
    const t = (flatness - 0.4) / 0.35;
    r = Math.round(blue.r + (orange.r - blue.r) * t);
    g = Math.round(blue.g + (orange.g - blue.g) * t);
    b = Math.round(blue.b + (orange.b - blue.b) * t);
  } else if (flatness <= 0.9) {
    // Interpolate from orange to red (75% to 90%)
    const t = (flatness - 0.75) / 0.15;
    r = Math.round(orange.r + (red.r - orange.r) * t);
    g = Math.round(orange.g + (red.g - orange.g) * t);
    b = Math.round(orange.b + (red.b - orange.b) * t);
  } else {
    // Stay red (90%+)
    r = red.r;
    g = red.g;
    b = red.b;
  }

  return `rgb(${r}, ${g}, ${b})`;
}

/**
 * Get a continuous color for probability value (0-1).
 * High probability (confident) = green
 * Medium probability = yellow/amber
 * Low probability (uncertain) = red
 */
export function getProbabilityColor(prob: number): string {
  // Color stops - inverted from flatness (high prob = good = green)
  const green = { r: 16, g: 185, b: 129 }; // emerald-500 (high prob)
  const yellow = { r: 234, g: 179, b: 8 }; // yellow-500 (medium prob)
  const orange = { r: 245, g: 158, b: 11 }; // amber-500 (low prob)
  const red = { r: 239, g: 68, b: 68 }; // red-500 (very low prob)

  let r: number, g: number, b: number;

  if (prob >= 0.8) {
    // High probability - stay green
    r = green.r;
    g = green.g;
    b = green.b;
  } else if (prob >= 0.5) {
    // Interpolate from green to yellow (80% to 50%)
    const t = (0.8 - prob) / 0.3;
    r = Math.round(green.r + (yellow.r - green.r) * t);
    g = Math.round(green.g + (yellow.g - green.g) * t);
    b = Math.round(green.b + (yellow.b - green.b) * t);
  } else if (prob >= 0.2) {
    // Interpolate from yellow to orange (50% to 20%)
    const t = (0.5 - prob) / 0.3;
    r = Math.round(yellow.r + (orange.r - yellow.r) * t);
    g = Math.round(yellow.g + (orange.g - yellow.g) * t);
    b = Math.round(yellow.b + (orange.b - yellow.b) * t);
  } else if (prob >= 0.05) {
    // Interpolate from orange to red (20% to 5%)
    const t = (0.2 - prob) / 0.15;
    r = Math.round(orange.r + (red.r - orange.r) * t);
    g = Math.round(orange.g + (red.g - orange.g) * t);
    b = Math.round(orange.b + (red.b - orange.b) * t);
  } else {
    // Very low probability - stay red
    r = red.r;
    g = red.g;
    b = red.b;
  }

  return `rgb(${r}, ${g}, ${b})`;
}

/**
 * Get label for probability value.
 */
export function getProbabilityLabel(prob: number): string {
  if (prob >= 0.8) return "High";
  if (prob >= 0.5) return "Medium";
  if (prob >= 0.2) return "Low";
  if (prob >= 0.05) return "Very Low";
  return "Rare";
}

/**
 * Get a continuous color for entropy value (in bits).
 * Low entropy (certain) = green
 * Medium entropy = yellow/amber
 * High entropy (uncertain) = red/purple
 *
 * Typical LLM entropy ranges from 0-5+ bits depending on context.
 */
export function getEntropyColor(entropy: number): string {
  // Color stops
  const green = { r: 16, g: 185, b: 129 }; // emerald-500 (low entropy = certain)
  const yellow = { r: 234, g: 179, b: 8 }; // yellow-500 (medium entropy)
  const orange = { r: 245, g: 158, b: 11 }; // amber-500 (higher entropy)
  const red = { r: 239, g: 68, b: 68 }; // red-500 (high entropy)
  const purple = { r: 168, g: 85, b: 247 }; // purple-500 (very high entropy)

  let r: number, g: number, b: number;

  if (entropy <= 0.5) {
    // Very low entropy - stay green
    r = green.r;
    g = green.g;
    b = green.b;
  } else if (entropy <= 1.5) {
    // Interpolate from green to yellow (0.5 to 1.5 bits)
    const t = (entropy - 0.5) / 1.0;
    r = Math.round(green.r + (yellow.r - green.r) * t);
    g = Math.round(green.g + (yellow.g - green.g) * t);
    b = Math.round(green.b + (yellow.b - green.b) * t);
  } else if (entropy <= 2.5) {
    // Interpolate from yellow to orange (1.5 to 2.5 bits)
    const t = (entropy - 1.5) / 1.0;
    r = Math.round(yellow.r + (orange.r - yellow.r) * t);
    g = Math.round(yellow.g + (orange.g - yellow.g) * t);
    b = Math.round(yellow.b + (orange.b - yellow.b) * t);
  } else if (entropy <= 3.5) {
    // Interpolate from orange to red (2.5 to 3.5 bits)
    const t = (entropy - 2.5) / 1.0;
    r = Math.round(orange.r + (red.r - orange.r) * t);
    g = Math.round(orange.g + (red.g - orange.g) * t);
    b = Math.round(orange.b + (red.b - orange.b) * t);
  } else if (entropy <= 5.0) {
    // Interpolate from red to purple (3.5 to 5.0 bits)
    const t = (entropy - 3.5) / 1.5;
    r = Math.round(red.r + (purple.r - red.r) * t);
    g = Math.round(red.g + (purple.g - red.g) * t);
    b = Math.round(red.b + (purple.b - red.b) * t);
  } else {
    // Very high entropy - stay purple
    r = purple.r;
    g = purple.g;
    b = purple.b;
  }

  return `rgb(${r}, ${g}, ${b})`;
}

/**
 * Get label for entropy value (in bits).
 */
export function getEntropyLabel(entropy: number): string {
  if (entropy <= 0.5) return "Very Low";
  if (entropy <= 1.5) return "Low";
  if (entropy <= 2.5) return "Medium";
  if (entropy <= 3.5) return "High";
  return "Very High";
}

/**
 * Branchiness metrics computed from token probability distribution.
 * These metrics help identify "trajectory-critical" tokens where
 * the model is torn between a small handful of plausible options.
 */
export interface BranchinessMetrics {
  /**
   * Effective number of choices = exp(entropy).
   * If N_eff ≈ 2-5, there are a few real options with significant mass.
   */
  nEff: number;

  /**
   * Probability margin between top-1 and top-2 tokens.
   * Small margin = model is indecisive between the best options.
   */
  margin: number;

  /**
   * Ratio of p2/p1 (top-2 prob / top-1 prob).
   * Higher ratio (closer to 1) = more competition between top choices.
   */
  ratio: number;

  /**
   * Normalized entropy among top-k tokens (0-1).
   * High value = top-k tokens are nearly tied (highly ambiguous).
   */
  topKEntropy: number;

  /**
   * Combined branchiness score (0-1).
   * High score = trajectory-critical token where alternative choices
   * could significantly alter downstream generation.
   */
  branchiness: number;
}

/**
 * Calculate branchiness metrics from top token probabilities.
 *
 * Branchiness captures "trajectory importance" - positions where the model
 * is torn between a small number of plausible options. These are the steps
 * where changing one token is most likely to flip the entire downstream trajectory.
 *
 * Based on research in:
 * - Token-level uncertainty estimation (TokUR, entropy-based methods)
 * - Stepwise uncertainty for reasoning (TouT, MUR)
 * - Typical decoding and entropy-guided sampling
 *
 * @param topTokens Array of top tokens with logprobs from the model
 * @param k Number of top tokens to consider for top-k entropy (default: 5)
 * @returns BranchinessMetrics or null if insufficient data
 */
export function calculateBranchiness(
  topTokens: TopToken[],
  k: number = 5,
): BranchinessMetrics | null {
  if (!topTokens || topTokens.length < 2) return null;

  // Convert logprobs to probabilities
  const probs = topTokens.map((t) => Math.exp(t.logprob));
  const totalProb = probs.reduce((a, b) => a + b, 0);

  // Normalize probabilities
  const normalizedProbs = probs.map((p) => p / totalProb);

  // Sort probabilities in descending order
  const sortedProbs = [...normalizedProbs].sort((a, b) => b - a);

  // 1. Calculate full entropy H_t = -Σ p(v) * log(p(v))
  let entropy = 0;
  for (const p of normalizedProbs) {
    if (p > 0) {
      entropy -= p * Math.log(p); // Natural log for N_eff calculation
    }
  }

  // 2. Effective number of choices: N_eff = exp(H)
  const nEff = Math.exp(entropy);

  // 3. Margin between top-1 and top-2
  const p1 = sortedProbs[0] || 0;
  const p2 = sortedProbs[1] || 0;
  const margin = p1 - p2;

  // 4. Ratio of p2/p1 (0 = p1 dominates, 1 = tied)
  const ratio = p1 > 0 ? p2 / p1 : 0;

  // 5. Top-k normalized entropy
  // Take top-k probs and renormalize
  const actualK = Math.min(k, sortedProbs.length);
  const topKProbs = sortedProbs.slice(0, actualK);
  const topKSum = topKProbs.reduce((a, b) => a + b, 0);
  const renormalizedTopK = topKProbs.map((p) => p / topKSum);

  // Calculate entropy among top-k
  let topKEntropyRaw = 0;
  for (const p of renormalizedTopK) {
    if (p > 0) {
      topKEntropyRaw -= p * Math.log(p);
    }
  }

  // Normalize by max entropy (log(k)) to get value in [0, 1]
  const maxTopKEntropy = Math.log(actualK);
  const topKEntropy = maxTopKEntropy > 0 ? topKEntropyRaw / maxTopKEntropy : 0;

  // 6. Compute combined branchiness score
  //
  // Intuition:
  // - Gate out steps with tons of options (N_eff too big) or only one (N_eff≈1)
  // - Within the "few options" regime, upweight cases where:
  //   - Top-k entropy is high (several plausible continuations)
  //   - Margin is small (model is indecisive between best few)
  //
  // Formula:
  // B = inFewOptionsRegime * topKEntropy * (1 - margin/marginMax)

  // Check if N_eff is in the "interesting" range (1.5 to 6)
  // Use a soft gate with smooth transitions
  let nEffGate: number;
  if (nEff < 1.2) {
    // Too peaked - one option dominates
    nEffGate = 0;
  } else if (nEff < 1.5) {
    // Transition zone from peaked to interesting
    nEffGate = (nEff - 1.2) / 0.3;
  } else if (nEff <= 6) {
    // Sweet spot - few real options
    nEffGate = 1;
  } else if (nEff <= 10) {
    // Transition zone from interesting to diffuse
    nEffGate = 1 - (nEff - 6) / 4;
  } else {
    // Too diffuse - model is just confused
    nEffGate = 0;
  }

  // Margin factor: small margin = high factor
  // Normalize margin to [0, 1] range and invert
  // marginMax is typically around 0.5 for decisive cases
  const marginMax = 0.5;
  const marginFactor = Math.max(0, 1 - margin / marginMax);

  // Combined branchiness score
  const branchiness = nEffGate * topKEntropy * marginFactor;

  return {
    nEff,
    margin,
    ratio,
    topKEntropy,
    branchiness,
  };
}

/**
 * Get a continuous color for branchiness value (0-1).
 * Low branchiness (confident) = muted gray/blue
 * Medium branchiness = yellow/amber (attention-worthy)
 * High branchiness = bright magenta/pink (trajectory-critical)
 */
export function getBranchinessColor(branchiness: number): string {
  // Color stops
  const low = { r: 100, g: 116, b: 139 }; // slate-500 (muted, unimportant)
  const medium = { r: 234, g: 179, b: 8 }; // yellow-500 (attention)
  const high = { r: 236, g: 72, b: 153 }; // pink-500 (critical)
  const veryHigh = { r: 168, g: 85, b: 247 }; // purple-500 (highly critical)

  let r: number, g: number, b: number;

  if (branchiness <= 0.2) {
    // Low branchiness - stay muted
    const t = branchiness / 0.2;
    r = Math.round(low.r + (medium.r - low.r) * t * 0.3);
    g = Math.round(low.g + (medium.g - low.g) * t * 0.3);
    b = Math.round(low.b + (medium.b - low.b) * t * 0.3);
  } else if (branchiness <= 0.5) {
    // Transition to yellow/amber
    const t = (branchiness - 0.2) / 0.3;
    r = Math.round(low.r + (medium.r - low.r) * (0.3 + t * 0.7));
    g = Math.round(low.g + (medium.g - low.g) * (0.3 + t * 0.7));
    b = Math.round(low.b + (medium.b - low.b) * (0.3 + t * 0.7));
  } else if (branchiness <= 0.75) {
    // Transition to pink
    const t = (branchiness - 0.5) / 0.25;
    r = Math.round(medium.r + (high.r - medium.r) * t);
    g = Math.round(medium.g + (high.g - medium.g) * t);
    b = Math.round(medium.b + (high.b - medium.b) * t);
  } else {
    // Transition to purple for very high branchiness
    const t = (branchiness - 0.75) / 0.25;
    r = Math.round(high.r + (veryHigh.r - high.r) * t);
    g = Math.round(high.g + (veryHigh.g - high.g) * t);
    b = Math.round(high.b + (veryHigh.b - high.b) * t);
  }

  return `rgb(${r}, ${g}, ${b})`;
}

/**
 * Format branchiness as a human-readable label.
 */
export function getBranchinessLabel(branchiness: number): string {
  if (branchiness < 0.15) return "Confident";
  if (branchiness < 0.35) return "Low";
  if (branchiness < 0.55) return "Moderate";
  if (branchiness < 0.75) return "High";
  return "Critical";
}
