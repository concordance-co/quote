import { useMemo, useState } from "react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip as RechartsTooltip,
  ResponsiveContainer,
  BarChart,
  Bar,
  Cell,
  PieChart,
  Pie,
  ReferenceDot,
} from "recharts";
import { MessageSquarePlus, Send, X, User } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import { useUsername } from "@/hooks/useUsername";
import { createDiscussion } from "@/lib/api";
import { formatChartReference, type ChartReference } from "./AddCommentDialog";
import type { LogResponse } from "@/types/api";
import {
  calculateBranchiness,
  getBranchinessColor,
  getBranchinessLabel,
} from "@/components/TokenSequence/utils";

interface MetricsViewProps {
  log: LogResponse;
  requestId: string;
  onCommentAdded?: () => void;
}

export function MetricsView({
  log,
  requestId,
  onCommentAdded,
}: MetricsViewProps) {
  const [commentingOnChart, setCommentingOnChart] = useState<string | null>(
    null,
  );

  // Build metrics from events (new schema) with fallback to legacy steps
  const probabilityData = useMemo(() => {
    const events = log.events || [];
    const forwardPassEvents = events.filter(
      (e) => e.event_type === "ForwardPass",
    );
    const addedEvents = events.filter((e) => e.event_type === "Added");
    const sampledEvents = events.filter((e) => e.event_type === "Sampled");

    // Helper function to calculate flatness (normalized entropy)
    // Returns 0-1 where 1 = perfectly flat (uniform), 0 = peaked
    const calculateFlatness = (
      topTokens: { logprob: number }[],
    ): number | null => {
      if (!topTokens || topTokens.length < 2) return null;
      const probs = topTokens.map((t) => Math.exp(t.logprob));
      const totalProb = probs.reduce((a, b) => a + b, 0);
      const normalizedProbs = probs.map((p) => p / totalProb);
      const entropy = -normalizedProbs.reduce((acc, p) => {
        if (p > 0) return acc + p * Math.log2(p);
        return acc;
      }, 0);
      const maxEntropy = Math.log2(topTokens.length);
      return maxEntropy > 0 ? entropy / maxEntropy : null;
    };

    // Build step data from events
    const stepData: {
      step: number;
      probability: number;
      entropy: number;
      surprisal: number;
      flatness: number | null;
      branchiness: number | null;
      nEff: number | null;
      margin: number | null;
      topKEntropy: number | null;
      forced: boolean;
      tokenStr?: string;
    }[] = [];

    forwardPassEvents.forEach((fp) => {
      // Get the corresponding Added event for forced status
      const addedEvent = addedEvents.find((a) => a.step === fp.step);

      // Skip if no Added event for this step
      if (!addedEvent) return;

      const forced = addedEvent.forced || false;

      // Get the corresponding Sampled event to find which token was actually chosen
      const sampledEvent = sampledEvents.find((s) => s.step === fp.step);
      const sampledTokenId = sampledEvent?.sampled_token;

      // Calculate probability from top_tokens if available
      let probability = 0;
      let entropy = 0;
      let surprisal = 0;
      let tokenStr: string | undefined;
      let branchiness: number | null = null;
      let nEff: number | null = null;
      let margin: number | null = null;
      let topKEntropy: number | null = null;

      if (
        fp.top_tokens &&
        Array.isArray(fp.top_tokens) &&
        fp.top_tokens.length > 0
      ) {
        // Find the actually sampled/added token in top_tokens
        // If not found, probability stays at 0
        if (sampledTokenId !== null && sampledTokenId !== undefined) {
          const found = fp.top_tokens.find((t) => t.token === sampledTokenId);
          if (found) {
            const logprob = found.logprob;
            probability = Math.exp(logprob) * 100;
            surprisal = -logprob / Math.log(2); // Convert to bits
            tokenStr = found.token_str;
          }
          // If sampled token not in top_tokens, probability remains 0
        }

        // Calculate entropy from all top tokens
        const probs = fp.top_tokens.map((t) => Math.exp(t.logprob));
        const totalProb = probs.reduce((a, b) => a + b, 0);
        const normalizedProbs = probs.map((p) => p / totalProb);
        entropy = -normalizedProbs.reduce((acc, p) => {
          if (p > 0) return acc + p * Math.log2(p);
          return acc;
        }, 0);

        // Calculate branchiness metrics
        const branchinessMetrics = calculateBranchiness(fp.top_tokens);
        if (branchinessMetrics) {
          branchiness = branchinessMetrics.branchiness;
          nEff = branchinessMetrics.nEff;
          margin = branchinessMetrics.margin;
          topKEntropy = branchinessMetrics.topKEntropy;
        }
      }

      // Calculate flatness
      const flatness =
        fp.top_tokens && fp.top_tokens.length >= 2
          ? calculateFlatness(fp.top_tokens)
          : null;

      stepData.push({
        step: fp.step,
        probability,
        entropy,
        surprisal,
        flatness,
        branchiness,
        nEff,
        margin,
        topKEntropy,
        forced,
        tokenStr,
      });
    });

    // Fall back to legacy steps if no event data
    if (stepData.length === 0 && log.steps) {
      return log.steps
        .filter((s) => s.prob !== null)
        .map((s) => ({
          step: s.step_index,
          probability: (s.prob ?? 0) * 100,
          entropy: s.entropy ?? 0,
          surprisal: s.surprisal ?? 0,
          flatness: null,
          branchiness: null,
          nEff: null,
          margin: null,
          topKEntropy: null,
          forced: s.forced,
        }));
    }

    return stepData.sort((a, b) => a.step - b.step);
  }, [log.events, log.steps]);

  const actionDistribution = useMemo(() => {
    const counts: Record<string, number> = {};
    (log.actions || []).forEach((a) => {
      counts[a.action_type] = (counts[a.action_type] || 0) + 1;
    });
    return Object.entries(counts).map(([name, value]) => ({ name, value }));
  }, [log.actions]);

  // Calculate forced vs sampled from events (new schema) or steps (legacy)
  const forcedVsSampled = useMemo(() => {
    const events = log.events || [];
    const addedEvents = events.filter((e) => e.event_type === "Added");

    if (addedEvents.length > 0) {
      // Count from events
      let forced = 0;
      let sampled = 0;

      addedEvents.forEach((event) => {
        const tokenCount =
          event.added_token_count || event.added_tokens?.length || 1;
        if (event.forced) {
          forced += tokenCount;
        } else {
          sampled += tokenCount;
        }
      });

      return [
        { name: "Forced", value: forced, color: "#ec4899" },
        { name: "Sampled", value: sampled, color: "#22c55e" },
      ];
    }

    // Fall back to legacy steps
    const steps = log.steps || [];
    const forcedCount = steps.filter((s) => s.forced).length;
    const sampledCount = steps.length - forcedCount;
    return [
      { name: "Forced", value: forcedCount, color: "#ec4899" },
      { name: "Sampled", value: sampledCount, color: "#22c55e" },
    ];
  }, [log.events, log.steps]);

  // Filter out forced tokens for charts and stats
  const sampledOnlyData = useMemo(() => {
    return probabilityData.filter((d) => !d.forced);
  }, [probabilityData]);

  // Get forced tokens for overlay dots
  const forcedTokens = useMemo(() => {
    return probabilityData.filter((d) => d.forced);
  }, [probabilityData]);

  const avgStats = useMemo(() => {
    // Use only sampled (non-forced) data for averages
    const probs = sampledOnlyData.map((d) => d.probability);
    const entropies = sampledOnlyData
      .map((d) => d.entropy)
      .filter((e) => e > 0);
    const surprisals = sampledOnlyData
      .map((d) => d.surprisal)
      .filter((s) => s > 0);
    const flatnesses = sampledOnlyData
      .map((d) => d.flatness)
      .filter((f): f is number => f !== null && f > 0);
    const branchinesses = sampledOnlyData
      .map((d) => d.branchiness)
      .filter((b): b is number => b !== null);

    return {
      avgProb:
        probs.length > 0
          ? probs.reduce((a, b) => a + b, 0) / probs.length
          : null,
      avgEntropy:
        entropies.length > 0
          ? entropies.reduce((a, b) => a + b, 0) / entropies.length
          : null,
      avgSurprisal:
        surprisals.length > 0
          ? surprisals.reduce((a, b) => a + b, 0) / surprisals.length
          : null,
      avgFlatness:
        flatnesses.length > 0
          ? flatnesses.reduce((a, b) => a + b, 0) / flatnesses.length
          : null,
      avgBranchiness:
        branchinesses.length > 0
          ? branchinesses.reduce((a, b) => a + b, 0) / branchinesses.length
          : null,
      maxBranchiness:
        branchinesses.length > 0 ? Math.max(...branchinesses) : null,
      perplexity:
        surprisals.length > 0
          ? Math.pow(
              2,
              surprisals.reduce((a, b) => a + b, 0) / surprisals.length,
            )
          : null,
    };
  }, [sampledOnlyData]);

  // Count high branchiness tokens (trajectory-critical)
  const highBranchinessCount = useMemo(() => {
    return sampledOnlyData.filter(
      (d) => d.branchiness !== null && d.branchiness >= 0.5,
    ).length;
  }, [sampledOnlyData]);

  return (
    <div className="space-y-2">
      {/* Summary Stats Row */}
      <div className="panel">
        <div className="px-3 py-2 flex items-center gap-6 text-xs flex-wrap">
          <div className="flex items-center gap-1.5">
            <span className="text-muted-foreground">Avg Prob:</span>
            <span className="font-medium">
              {avgStats.avgProb?.toFixed(1) ?? "—"}%
            </span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="text-muted-foreground">Avg Entropy:</span>
            <span className="font-medium">
              {avgStats.avgEntropy?.toFixed(3) ?? "—"}
            </span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="text-muted-foreground">Avg Surprisal:</span>
            <span className="font-medium">
              {avgStats.avgSurprisal?.toFixed(3) ?? "—"}
            </span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="text-muted-foreground">Avg Flatness:</span>
            <span className="font-medium">
              {avgStats.avgFlatness !== null
                ? `${(avgStats.avgFlatness * 100).toFixed(0)}%`
                : "—"}
            </span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="text-muted-foreground">Perplexity:</span>
            <span className="font-medium">
              {avgStats.perplexity?.toFixed(2) ?? "—"}
            </span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="text-muted-foreground">Avg Branchiness:</span>
            <span
              className="font-medium"
              style={{
                color:
                  avgStats.avgBranchiness !== null
                    ? getBranchinessColor(avgStats.avgBranchiness)
                    : undefined,
              }}
            >
              {avgStats.avgBranchiness !== null
                ? `${(avgStats.avgBranchiness * 100).toFixed(0)}%`
                : "—"}
            </span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="text-muted-foreground">Critical Steps:</span>
            <span
              className="font-medium"
              style={{
                color:
                  highBranchinessCount > 0
                    ? getBranchinessColor(0.7)
                    : undefined,
              }}
            >
              {highBranchinessCount}
            </span>
          </div>
        </div>
      </div>

      {/* Charts Grid */}
      <div className="grid gap-2 lg:grid-cols-2">
        {/* Probability Chart */}
        <div className="panel">
          <div className="panel-header flex items-center justify-between">
            <span className="panel-title">
              Added Token Probability (Sampled Only)
            </span>
            <Tooltip>
              <TooltipTrigger asChild>
                <button
                  onClick={() =>
                    setCommentingOnChart(
                      commentingOnChart === "probability"
                        ? null
                        : "probability",
                    )
                  }
                  className={cn(
                    "p-1 rounded hover:bg-muted text-muted-foreground hover:text-foreground transition-colors",
                    commentingOnChart === "probability" &&
                      "bg-muted text-foreground",
                  )}
                >
                  <MessageSquarePlus className="h-3 w-3" />
                </button>
              </TooltipTrigger>
              <TooltipContent>
                <p className="text-2xs">Add comment</p>
              </TooltipContent>
            </Tooltip>
          </div>
          {commentingOnChart === "probability" && (
            <InlineChartCommentForm
              requestId={requestId}
              chartId="probability"
              chartTitle="Added Token Probability (Sampled Only)"
              onCancel={() => setCommentingOnChart(null)}
              onSubmitted={() => {
                setCommentingOnChart(null);
                onCommentAdded?.();
              }}
            />
          )}
          <div className="panel-content">
            <div className="h-[180px]">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={sampledOnlyData}>
                  <CartesianGrid
                    strokeDasharray="3 3"
                    stroke="hsl(var(--border))"
                  />
                  <XAxis
                    dataKey="step"
                    type="number"
                    domain={["dataMin", "dataMax"]}
                    tick={{
                      fill: "hsl(var(--muted-foreground))",
                      fontSize: 10,
                    }}
                    tickLine={false}
                  />
                  <YAxis
                    tick={{
                      fill: "hsl(var(--muted-foreground))",
                      fontSize: 10,
                    }}
                    tickLine={false}
                    domain={[0, 100]}
                  />
                  <RechartsTooltip
                    contentStyle={{
                      backgroundColor: "hsl(var(--popover))",
                      border: "1px solid hsl(var(--border))",
                      borderRadius: "4px",
                      fontSize: "11px",
                    }}
                  />
                  <Line
                    type="monotone"
                    dataKey="probability"
                    stroke="hsl(var(--primary))"
                    strokeWidth={1.5}
                    dot={false}
                  />
                  {forcedTokens.map((ft) => (
                    <ReferenceDot
                      key={ft.step}
                      x={ft.step}
                      y={0}
                      r={4}
                      fill="#ec4899"
                      stroke="#ec4899"
                    />
                  ))}
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>

        {/* Entropy Chart */}
        <div className="panel">
          <div className="panel-header flex items-center justify-between">
            <span className="panel-title">
              Entropy Over Steps (Sampled Only)
            </span>
            <Tooltip>
              <TooltipTrigger asChild>
                <button
                  onClick={() =>
                    setCommentingOnChart(
                      commentingOnChart === "entropy" ? null : "entropy",
                    )
                  }
                  className={cn(
                    "p-1 rounded hover:bg-muted text-muted-foreground hover:text-foreground transition-colors",
                    commentingOnChart === "entropy" &&
                      "bg-muted text-foreground",
                  )}
                >
                  <MessageSquarePlus className="h-3 w-3" />
                </button>
              </TooltipTrigger>
              <TooltipContent>
                <p className="text-2xs">Add comment</p>
              </TooltipContent>
            </Tooltip>
          </div>
          {commentingOnChart === "entropy" && (
            <InlineChartCommentForm
              requestId={requestId}
              chartId="entropy"
              chartTitle="Entropy Over Steps (Sampled Only)"
              onCancel={() => setCommentingOnChart(null)}
              onSubmitted={() => {
                setCommentingOnChart(null);
                onCommentAdded?.();
              }}
            />
          )}
          <div className="panel-content">
            <div className="h-[180px]">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={sampledOnlyData}>
                  <CartesianGrid
                    strokeDasharray="3 3"
                    stroke="hsl(var(--border))"
                  />
                  <XAxis
                    dataKey="step"
                    tick={{
                      fill: "hsl(var(--muted-foreground))",
                      fontSize: 10,
                    }}
                    tickLine={false}
                  />
                  <YAxis
                    tick={{
                      fill: "hsl(var(--muted-foreground))",
                      fontSize: 10,
                    }}
                    tickLine={false}
                  />
                  <RechartsTooltip
                    contentStyle={{
                      backgroundColor: "hsl(var(--popover))",
                      border: "1px solid hsl(var(--border))",
                      borderRadius: "4px",
                      fontSize: "11px",
                    }}
                  />
                  <Line
                    type="monotone"
                    dataKey="entropy"
                    stroke="hsl(var(--chart-2))"
                    strokeWidth={1.5}
                    dot={false}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>

        {/* Branchiness Chart */}
        <div className="panel">
          <div className="panel-header flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="panel-title">
                Branchiness Score (Sampled Only)
              </span>
              <Tooltip>
                <TooltipTrigger asChild>
                  <span className="text-2xs text-muted-foreground cursor-help">
                    ⓘ
                  </span>
                </TooltipTrigger>
                <TooltipContent className="max-w-xs">
                  <p className="text-2xs">
                    Branchiness measures trajectory importance — positions where
                    the model is torn between a small number of plausible
                    options. High branchiness indicates steps where changing one
                    token could significantly alter downstream generation.
                  </p>
                </TooltipContent>
              </Tooltip>
            </div>
            <Tooltip>
              <TooltipTrigger asChild>
                <button
                  onClick={() =>
                    setCommentingOnChart(
                      commentingOnChart === "branchiness"
                        ? null
                        : "branchiness",
                    )
                  }
                  className={cn(
                    "p-1 rounded hover:bg-muted text-muted-foreground hover:text-foreground transition-colors",
                    commentingOnChart === "branchiness" &&
                      "bg-muted text-foreground",
                  )}
                >
                  <MessageSquarePlus className="h-3 w-3" />
                </button>
              </TooltipTrigger>
              <TooltipContent>
                <p className="text-2xs">Add comment</p>
              </TooltipContent>
            </Tooltip>
          </div>
          {commentingOnChart === "branchiness" && (
            <InlineChartCommentForm
              requestId={requestId}
              chartId="branchiness"
              chartTitle="Branchiness Score (Sampled Only)"
              onCancel={() => setCommentingOnChart(null)}
              onSubmitted={() => {
                setCommentingOnChart(null);
                onCommentAdded?.();
              }}
            />
          )}
          <div className="panel-content">
            <div className="h-[180px]">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart
                  data={sampledOnlyData.filter((d) => d.branchiness !== null)}
                >
                  <CartesianGrid
                    strokeDasharray="3 3"
                    stroke="hsl(var(--border))"
                  />
                  <XAxis
                    dataKey="step"
                    type="number"
                    domain={["dataMin", "dataMax"]}
                    tick={{
                      fill: "hsl(var(--muted-foreground))",
                      fontSize: 10,
                    }}
                    tickLine={false}
                  />
                  <YAxis
                    tick={{
                      fill: "hsl(var(--muted-foreground))",
                      fontSize: 10,
                    }}
                    tickLine={false}
                    domain={[0, 1]}
                    tickFormatter={(v) => `${(v * 100).toFixed(0)}%`}
                  />
                  <RechartsTooltip
                    contentStyle={{
                      backgroundColor: "hsl(var(--popover))",
                      border: "1px solid hsl(var(--border))",
                      borderRadius: "4px",
                      fontSize: "11px",
                    }}
                    formatter={(
                      value: number,
                      _name: string,
                      props?: {
                        payload?: {
                          nEff?: number | null;
                          margin?: number | null;
                          topKEntropy?: number | null;
                          tokenStr?: string;
                        };
                      },
                    ) => {
                      const label = getBranchinessLabel(value);
                      const details: string[] = [
                        `${(value * 100).toFixed(1)}% (${label})`,
                      ];
                      const payload = props?.payload;
                      if (payload?.tokenStr) {
                        details.push(`Token: "${payload.tokenStr}"`);
                      }
                      if (
                        payload?.nEff !== null &&
                        payload?.nEff !== undefined
                      ) {
                        details.push(`N_eff: ${payload.nEff.toFixed(2)}`);
                      }
                      if (
                        payload?.margin !== null &&
                        payload?.margin !== undefined
                      ) {
                        details.push(
                          `Margin: ${(payload.margin * 100).toFixed(1)}%`,
                        );
                      }
                      return [details.join(" · "), "Branchiness"];
                    }}
                  />
                  <Line
                    type="monotone"
                    dataKey="branchiness"
                    stroke="#ec4899"
                    strokeWidth={1.5}
                    dot={(props: {
                      cx?: number;
                      cy?: number;
                      payload?: { branchiness?: number | null };
                    }) => {
                      const { cx, cy, payload } = props;
                      if (
                        payload?.branchiness !== null &&
                        payload?.branchiness !== undefined &&
                        payload.branchiness >= 0.5
                      ) {
                        return (
                          <circle
                            key={`dot-${cx}-${cy}`}
                            cx={cx}
                            cy={cy}
                            r={4}
                            fill={getBranchinessColor(payload.branchiness)}
                            stroke={getBranchinessColor(payload.branchiness)}
                          />
                        );
                      }
                      return <circle key={`dot-${cx}-${cy}`} r={0} />;
                    }}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
            {/* Legend for branchiness levels */}
            <div className="flex items-center justify-center gap-4 mt-2 text-2xs">
              <div className="flex items-center gap-1">
                <span
                  className="w-2 h-2 rounded-full"
                  style={{ backgroundColor: getBranchinessColor(0.1) }}
                />
                <span className="text-muted-foreground">Confident</span>
              </div>
              <div className="flex items-center gap-1">
                <span
                  className="w-2 h-2 rounded-full"
                  style={{ backgroundColor: getBranchinessColor(0.4) }}
                />
                <span className="text-muted-foreground">Moderate</span>
              </div>
              <div className="flex items-center gap-1">
                <span
                  className="w-2 h-2 rounded-full"
                  style={{ backgroundColor: getBranchinessColor(0.65) }}
                />
                <span className="text-muted-foreground">High</span>
              </div>
              <div className="flex items-center gap-1">
                <span
                  className="w-2 h-2 rounded-full"
                  style={{ backgroundColor: getBranchinessColor(0.85) }}
                />
                <span className="text-muted-foreground">Critical</span>
              </div>
            </div>
          </div>
        </div>

        {/* Flatness Chart */}
        <div className="panel">
          <div className="panel-header flex items-center justify-between">
            <span className="panel-title">
              Distribution Flatness (Sampled Only)
            </span>
            <Tooltip>
              <TooltipTrigger asChild>
                <button
                  onClick={() =>
                    setCommentingOnChart(
                      commentingOnChart === "flatness" ? null : "flatness",
                    )
                  }
                  className={cn(
                    "p-1 rounded hover:bg-muted text-muted-foreground hover:text-foreground transition-colors",
                    commentingOnChart === "flatness" &&
                      "bg-muted text-foreground",
                  )}
                >
                  <MessageSquarePlus className="h-3 w-3" />
                </button>
              </TooltipTrigger>
              <TooltipContent>
                <p className="text-2xs">Add comment</p>
              </TooltipContent>
            </Tooltip>
          </div>
          {commentingOnChart === "flatness" && (
            <InlineChartCommentForm
              requestId={requestId}
              chartId="flatness"
              chartTitle="Distribution Flatness (Sampled Only)"
              onCancel={() => setCommentingOnChart(null)}
              onSubmitted={() => {
                setCommentingOnChart(null);
                onCommentAdded?.();
              }}
            />
          )}
          <div className="panel-content">
            <div className="h-[180px]">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart
                  data={sampledOnlyData.filter((d) => d.flatness !== null)}
                >
                  <CartesianGrid
                    strokeDasharray="3 3"
                    stroke="hsl(var(--border))"
                  />
                  <XAxis
                    dataKey="step"
                    type="number"
                    domain={["dataMin", "dataMax"]}
                    tick={{
                      fill: "hsl(var(--muted-foreground))",
                      fontSize: 10,
                    }}
                    tickLine={false}
                  />
                  <YAxis
                    tick={{
                      fill: "hsl(var(--muted-foreground))",
                      fontSize: 10,
                    }}
                    tickLine={false}
                    domain={[0, 1]}
                    tickFormatter={(v) => `${(v * 100).toFixed(0)}%`}
                  />
                  <RechartsTooltip
                    contentStyle={{
                      backgroundColor: "hsl(var(--popover))",
                      border: "1px solid hsl(var(--border))",
                      borderRadius: "4px",
                      fontSize: "11px",
                    }}
                    formatter={(value: number) => [
                      `${(value * 100).toFixed(1)}%`,
                      "Flatness",
                    ]}
                  />
                  <Line
                    type="monotone"
                    dataKey="flatness"
                    stroke="#f59e0b"
                    strokeWidth={1.5}
                    dot={false}
                  />
                  {forcedTokens
                    .filter((ft) => ft.flatness !== null)
                    .map((ft) => (
                      <ReferenceDot
                        key={ft.step}
                        x={ft.step}
                        y={0}
                        r={4}
                        fill="#ec4899"
                        stroke="#ec4899"
                      />
                    ))}
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>

        {/* Forced vs Sampled */}
        <div className="panel">
          <div className="panel-header flex items-center justify-between">
            <span className="panel-title">Forced vs Sampled</span>
            <Tooltip>
              <TooltipTrigger asChild>
                <button
                  onClick={() =>
                    setCommentingOnChart(
                      commentingOnChart === "forced-sampled"
                        ? null
                        : "forced-sampled",
                    )
                  }
                  className={cn(
                    "p-1 rounded hover:bg-muted text-muted-foreground hover:text-foreground transition-colors",
                    commentingOnChart === "forced-sampled" &&
                      "bg-muted text-foreground",
                  )}
                >
                  <MessageSquarePlus className="h-3 w-3" />
                </button>
              </TooltipTrigger>
              <TooltipContent>
                <p className="text-2xs">Add comment</p>
              </TooltipContent>
            </Tooltip>
          </div>
          {commentingOnChart === "forced-sampled" && (
            <InlineChartCommentForm
              requestId={requestId}
              chartId="forced-sampled"
              chartTitle="Forced vs Sampled"
              onCancel={() => setCommentingOnChart(null)}
              onSubmitted={() => {
                setCommentingOnChart(null);
                onCommentAdded?.();
              }}
            />
          )}
          <div className="panel-content">
            <div className="h-[180px]">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={forcedVsSampled}
                    cx="50%"
                    cy="50%"
                    innerRadius={40}
                    outerRadius={70}
                    paddingAngle={2}
                    dataKey="value"
                    label={({ name, percent }) =>
                      `${name} ${((percent ?? 0) * 100).toFixed(0)}%`
                    }
                    labelLine={false}
                  >
                    {forcedVsSampled.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={entry.color} />
                    ))}
                  </Pie>
                  <RechartsTooltip
                    contentStyle={{
                      backgroundColor: "hsl(var(--popover))",
                      border: "1px solid hsl(var(--border))",
                      borderRadius: "4px",
                      fontSize: "11px",
                    }}
                  />
                </PieChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>

        {/* Action Distribution */}
        {actionDistribution.length > 0 && (
          <div className="panel">
            <div className="panel-header flex items-center justify-between">
              <span className="panel-title">Action Distribution</span>
              <Tooltip>
                <TooltipTrigger asChild>
                  <button
                    onClick={() =>
                      setCommentingOnChart(
                        commentingOnChart === "action-distribution"
                          ? null
                          : "action-distribution",
                      )
                    }
                    className={cn(
                      "p-1 rounded hover:bg-muted text-muted-foreground hover:text-foreground transition-colors",
                      commentingOnChart === "action-distribution" &&
                        "bg-muted text-foreground",
                    )}
                  >
                    <MessageSquarePlus className="h-3 w-3" />
                  </button>
                </TooltipTrigger>
                <TooltipContent>
                  <p className="text-2xs">Add comment</p>
                </TooltipContent>
              </Tooltip>
            </div>
            {commentingOnChart === "action-distribution" && (
              <InlineChartCommentForm
                requestId={requestId}
                chartId="action-distribution"
                chartTitle="Action Distribution"
                onCancel={() => setCommentingOnChart(null)}
                onSubmitted={() => {
                  setCommentingOnChart(null);
                  onCommentAdded?.();
                }}
              />
            )}
            <div className="panel-content">
              <div className="h-[180px]">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={actionDistribution} layout="vertical">
                    <CartesianGrid
                      strokeDasharray="3 3"
                      stroke="hsl(var(--border))"
                    />
                    <XAxis
                      type="number"
                      tick={{
                        fill: "hsl(var(--muted-foreground))",
                        fontSize: 10,
                      }}
                      tickLine={false}
                    />
                    <YAxis
                      dataKey="name"
                      type="category"
                      tick={{
                        fill: "hsl(var(--muted-foreground))",
                        fontSize: 10,
                      }}
                      tickLine={false}
                      width={80}
                    />
                    <RechartsTooltip
                      contentStyle={{
                        backgroundColor: "hsl(var(--popover))",
                        border: "1px solid hsl(var(--border))",
                        borderRadius: "4px",
                        fontSize: "11px",
                      }}
                    />
                    <Bar
                      dataKey="value"
                      fill="hsl(var(--primary))"
                      radius={2}
                    />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// Inline comment form for charts
interface InlineChartCommentFormProps {
  requestId: string;
  chartId: string;
  chartTitle: string;
  onCancel: () => void;
  onSubmitted: () => void;
}

function InlineChartCommentForm({
  requestId,
  chartId,
  chartTitle,
  onCancel,
  onSubmitted,
}: InlineChartCommentFormProps) {
  const { username, setUsername, isSet: hasUsername } = useUsername();
  const [comment, setComment] = useState("");
  const [usernameInput, setUsernameInput] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [showUsernameInput, setShowUsernameInput] = useState(!hasUsername);

  const handleSetUsername = () => {
    if (usernameInput.trim()) {
      setUsername(usernameInput.trim());
      setShowUsernameInput(false);
      setUsernameInput("");
    }
  };

  const handleSubmit = async () => {
    if (!comment.trim() || !username) return;

    try {
      setSubmitting(true);
      const reference: ChartReference = {
        chartId,
        chartTitle,
      };
      const fullComment = `${formatChartReference(reference)}\n\n${comment.trim()}`;
      await createDiscussion(requestId, username, fullComment);
      onSubmitted();
    } catch (err) {
      console.error("Failed to create comment:", err);
    } finally {
      setSubmitting(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Escape") {
      onCancel();
    } else if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
      handleSubmit();
    }
  };

  return (
    <div className="mx-3 mb-3 bg-primary/5 rounded p-2 border border-primary/20">
      <div className="flex items-center gap-2 mb-2">
        <MessageSquarePlus className="h-3 w-3 text-primary" />
        <span className="text-2xs font-medium text-primary">Add Comment</span>
        <span className="text-2xs text-muted-foreground">on</span>
        <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-2xs font-medium bg-chart-1/10 text-chart-1 border border-chart-1/20">
          {chartTitle}
        </span>
        <button
          onClick={onCancel}
          className="ml-auto p-0.5 rounded hover:bg-muted text-muted-foreground hover:text-foreground transition-colors"
        >
          <X className="h-3 w-3" />
        </button>
      </div>

      {showUsernameInput || !hasUsername ? (
        <div className="flex items-center gap-2 mb-2">
          <User className="h-3 w-3 text-muted-foreground" />
          <input
            type="text"
            placeholder="Your username..."
            value={usernameInput}
            onChange={(e) => setUsernameInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleSetUsername()}
            className="flex-1 h-6 px-2 rounded border border-input bg-background text-xs focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
            autoFocus
          />
          <Button
            size="sm"
            className="h-6 text-xs px-2"
            onClick={handleSetUsername}
            disabled={!usernameInput.trim()}
          >
            Set
          </Button>
        </div>
      ) : (
        <div className="flex items-center gap-1 mb-2 text-2xs text-muted-foreground">
          <span>Posting as</span>
          <button
            onClick={() => setShowUsernameInput(true)}
            className="font-medium text-primary hover:underline"
          >
            {username}
          </button>
        </div>
      )}

      <div className="flex items-start gap-2">
        <textarea
          placeholder="Write your comment..."
          value={comment}
          onChange={(e) => setComment(e.target.value)}
          onKeyDown={handleKeyDown}
          className={cn(
            "flex-1 h-14 px-2 py-1 rounded border border-input bg-background text-xs resize-none",
            "focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring",
            (!hasUsername || showUsernameInput) && "opacity-50",
          )}
          disabled={!hasUsername || showUsernameInput}
          autoFocus={hasUsername}
        />
        <Button
          size="sm"
          className="h-8 w-8 p-0"
          onClick={handleSubmit}
          disabled={
            !comment.trim() || !hasUsername || showUsernameInput || submitting
          }
        >
          <Send className="h-3.5 w-3.5" />
        </Button>
      </div>
      <p className="text-2xs text-muted-foreground mt-1">⌘+Enter to submit</p>
    </div>
  );
}
