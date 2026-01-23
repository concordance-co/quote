// Utility functions for TraceTree components

// Get color for step grouping bar
export function getStepColor(step: number): string {
  const colors = [
    "bg-blue-500/60",
    // "bg-emerald-500/60",
    // "bg-purple-500/60",
    // "bg-pink-500/60",
    "bg-amber-500/60",
    "bg-indigo-500/60",
    "bg-cyan-500/60",
    "bg-rose-500/60",
  ];
  return colors[step % colors.length];
}

// Get color for step grouping bar
export function getStepColorContainer(step: number): string {
  const colors = [
    "bg-blue-500/20 border-blue-500/30",
    // "bg-emerald-500/20 border-emerald-500/30 border",
    // "bg-purple-500/20 border-purple-500/30 border",
    // "bg-pink-500/20 border-pink-500/30 border",
    "bg-amber-500/20 border-amber-500/30",
    "bg-indigo-500/20 border-indigo-500/30",
    "bg-cyan-500/20 border-cyan-500/30",
    "bg-rose-500/20 border-rose-500/30",
  ];
  return colors[step % colors.length];
}

// Calculate flatness (normalized entropy) of a probability distribution
// Returns a value from 0 to 1, where 1 = perfectly flat (uniform), 0 = peaked
export function calculateFlatness(
  topTokens: { logprob: number }[],
): number | null {
  if (!topTokens || topTokens.length < 2) return null;

  // Convert logprobs to probabilities
  const probs = topTokens.map((t) => Math.exp(t.logprob));
  const totalProb = probs.reduce((a, b) => a + b, 0);

  // Normalize probabilities
  const normalizedProbs = probs.map((p) => p / totalProb);

  // Calculate entropy
  const entropy = -normalizedProbs.reduce((acc, p) => {
    if (p > 0) return acc + p * Math.log2(p);
    return acc;
  }, 0);

  // Max entropy for n items is log2(n)
  const maxEntropy = Math.log2(topTokens.length);

  // Normalized entropy (flatness) = entropy / maxEntropy
  return maxEntropy > 0 ? entropy / maxEntropy : null;
}
