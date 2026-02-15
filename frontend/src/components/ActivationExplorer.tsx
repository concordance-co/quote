import { useCallback, useEffect, useMemo, useState } from "react";
import { AlertTriangle, Loader2, Play, RefreshCw, Search } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  getActivationExplorerFeatureDeltas,
  getActivationExplorerHealth,
  getActivationExplorerRows,
  getActivationExplorerRunSummary,
  getActivationExplorerTopFeatures,
  listActivationExplorerRuns,
  runActivationExplorer,
  type ActivationExplorerFeatureDeltasResponse,
  type ActivationExplorerHealthResponse,
  type ActivationExplorerRowsResponse,
  type ActivationExplorerRunResponse,
  type ActivationExplorerRunSummary,
  type ActivationExplorerTopFeaturesResponse,
} from "@/lib/api";

const DEFAULT_MODEL = "meta-llama/Llama-3.1-8B-Instruct";

type RunFormState = {
  prompt: string;
  modelId: string;
  maxTokens: number;
  inlineSae: boolean;
  saeId: string;
  saeLayer: number;
  saeTopK: number;
};

const DEFAULT_FORM: RunFormState = {
  prompt: "Give me a short paragraph on mechanistic interpretability and feature tracking.",
  modelId: DEFAULT_MODEL,
  maxTokens: 128,
  inlineSae: true,
  saeId: "llama_scope_lxr_8x",
  saeLayer: 16,
  saeTopK: 20,
};

function asNumber(value: unknown, fallback: number = 0): number {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim() !== "") {
    const parsed = Number(value);
    if (Number.isFinite(parsed)) return parsed;
  }
  return fallback;
}

function asString(value: unknown): string {
  return typeof value === "string" ? value : "";
}

export default function ActivationExplorer() {
  const [form, setForm] = useState<RunFormState>(DEFAULT_FORM);
  const [status, setStatus] = useState<string>("");
  const [error, setError] = useState<string | null>(null);
  const [isRunning, setIsRunning] = useState(false);
  const [isRefreshing, setIsRefreshing] = useState(false);

  const [health, setHealth] = useState<ActivationExplorerHealthResponse | null>(null);
  const [runs, setRuns] = useState<ActivationExplorerRunSummary[]>([]);

  const [selectedRequestId, setSelectedRequestId] = useState<string | null>(null);
  const [selectedSummary, setSelectedSummary] = useState<ActivationExplorerRunSummary | null>(null);
  const [selectedRows, setSelectedRows] = useState<ActivationExplorerRowsResponse | null>(null);
  const [selectedTopFeatures, setSelectedTopFeatures] =
    useState<ActivationExplorerTopFeaturesResponse | null>(null);
  const [lastRun, setLastRun] = useState<ActivationExplorerRunResponse | null>(null);

  const [featureIdInput, setFeatureIdInput] = useState<string>("");
  const [featureDeltas, setFeatureDeltas] = useState<ActivationExplorerFeatureDeltasResponse | null>(
    null,
  );
  const [isLoadingDeltas, setIsLoadingDeltas] = useState(false);

  const refreshRuns = useCallback(async () => {
    setIsRefreshing(true);
    try {
      const [healthResp, runsResp] = await Promise.all([
        getActivationExplorerHealth(),
        listActivationExplorerRuns({ limit: 25 }),
      ]);
      setHealth(healthResp);
      setRuns(runsResp.items);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to refresh activation explorer data.");
    } finally {
      setIsRefreshing(false);
    }
  }, []);

  const loadRequestDetails = useCallback(
    async (requestId: string) => {
      setError(null);
      setSelectedRequestId(requestId);
      try {
        const [summary, rows, topFeatures] = await Promise.all([
          getActivationExplorerRunSummary(requestId),
          getActivationExplorerRows(requestId, { limit: 500 }),
          getActivationExplorerTopFeatures(requestId, { n: 50 }),
        ]);
        setSelectedSummary(summary);
        setSelectedRows(rows);
        setSelectedTopFeatures(topFeatures);
        setFeatureDeltas(null);
        setFeatureIdInput("");
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load selected run details.");
      }
    },
    [],
  );

  useEffect(() => {
    void refreshRuns();
  }, [refreshRuns]);

  const runModel = useCallback(async () => {
    const prompt = form.prompt.trim();
    if (!prompt) {
      setError("Prompt is required.");
      return;
    }
    setError(null);
    setStatus("Running activation analysis...");
    setIsRunning(true);

    try {
      const response = await runActivationExplorer({
        prompt,
        model_id: form.modelId,
        max_tokens: form.maxTokens,
        collect_activations: true,
        inline_sae: form.inlineSae,
        sae_id: form.saeId,
        sae_layer: form.saeLayer,
        sae_top_k: form.saeTopK,
      });
      setLastRun(response);
      await refreshRuns();
      await loadRequestDetails(response.request_id);
      setStatus(`Completed run ${response.request_id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Activation run failed.");
      setStatus("Run failed.");
    } finally {
      setIsRunning(false);
    }
  }, [form, loadRequestDetails, refreshRuns]);

  const fetchFeatureDeltas = useCallback(async () => {
    if (!selectedRequestId) {
      setError("Select a run first.");
      return;
    }
    const featureId = Number(featureIdInput);
    if (!Number.isFinite(featureId) || featureId < 0) {
      setError("Feature ID must be a non-negative number.");
      return;
    }
    setError(null);
    setIsLoadingDeltas(true);
    try {
      const deltas = await getActivationExplorerFeatureDeltas(selectedRequestId, {
        feature_id: featureId,
        sae_layer: selectedSummary?.sae_layer ?? undefined,
        limit: 1024,
      });
      setFeatureDeltas(deltas);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load feature deltas.");
    } finally {
      setIsLoadingDeltas(false);
    }
  }, [featureIdInput, selectedRequestId, selectedSummary?.sae_layer]);

  const topFeaturesPreview = useMemo(() => {
    if (!selectedTopFeatures?.items?.length) return "No top features loaded.";
    return selectedTopFeatures.items
      .slice(0, 10)
      .map((item) => {
        const featureId = asNumber((item as Record<string, unknown>).feature_id, -1);
        const maxAct = asNumber((item as Record<string, unknown>).max_activation, 0).toFixed(3);
        const hits = asNumber((item as Record<string, unknown>).hits, 0);
        return `#${featureId}  max=${maxAct}  hits=${hits}`;
      })
      .join("\n");
  }, [selectedTopFeatures]);

  return (
    <div className="container max-w-7xl space-y-4">
      <div className="grid gap-4 lg:grid-cols-[1.3fr_1fr]">
        <Card>
          <CardHeader>
            <CardTitle>Activation Explorer (v0)</CardTitle>
            <CardDescription>
              Run inference with SAE feature extraction and inspect activation data.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <label className="block text-xs font-medium text-muted-foreground">Prompt</label>
            <textarea
              className="w-full min-h-28 rounded-md border border-border bg-background px-3 py-2 text-sm"
              value={form.prompt}
              onChange={(e) => setForm((prev) => ({ ...prev, prompt: e.target.value }))}
            />

            <div className="grid gap-3 md:grid-cols-2">
              <div>
                <label className="block text-xs font-medium text-muted-foreground">Model ID</label>
                <input
                  className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
                  value={form.modelId}
                  onChange={(e) => setForm((prev) => ({ ...prev, modelId: e.target.value }))}
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-muted-foreground">Max Tokens</label>
                <input
                  type="number"
                  min={1}
                  max={2048}
                  className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
                  value={form.maxTokens}
                  onChange={(e) =>
                    setForm((prev) => ({
                      ...prev,
                      maxTokens: Number.parseInt(e.target.value || "128", 10),
                    }))
                  }
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-muted-foreground">SAE ID</label>
                <input
                  className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
                  value={form.saeId}
                  onChange={(e) => setForm((prev) => ({ ...prev, saeId: e.target.value }))}
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-muted-foreground">SAE Layer</label>
                <input
                  type="number"
                  className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
                  value={form.saeLayer}
                  onChange={(e) =>
                    setForm((prev) => ({
                      ...prev,
                      saeLayer: Number.parseInt(e.target.value || "16", 10),
                    }))
                  }
                />
              </div>
            </div>

            <div className="flex flex-wrap items-center gap-2">
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={form.inlineSae}
                  onChange={(e) => setForm((prev) => ({ ...prev, inlineSae: e.target.checked }))}
                />
                Inline SAE
              </label>

              <Button onClick={runModel} disabled={isRunning}>
                {isRunning ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Play className="mr-2 h-4 w-4" />}
                Run
              </Button>
              <Button variant="outline" onClick={() => void refreshRuns()} disabled={isRefreshing}>
                {isRefreshing ? (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                ) : (
                  <RefreshCw className="mr-2 h-4 w-4" />
                )}
                Refresh
              </Button>
              {health && (
                <Badge variant={health.status === "ok" ? "secondary" : "destructive"}>
                  health: {health.status}
                </Badge>
              )}
            </div>

            {status && <p className="text-xs text-muted-foreground">{status}</p>}
            {error && (
              <div className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
                <div className="flex items-center gap-2">
                  <AlertTriangle className="h-4 w-4" />
                  <span>{error}</span>
                </div>
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Recent Runs</CardTitle>
            <CardDescription>Indexed metadata from backend run index.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-2">
            {runs.length === 0 && <p className="text-sm text-muted-foreground">No runs indexed yet.</p>}
            {runs.map((run) => (
              <button
                key={run.request_id}
                className={`w-full rounded-md border px-3 py-2 text-left text-sm transition-colors ${
                  selectedRequestId === run.request_id
                    ? "border-primary bg-primary/5"
                    : "border-border hover:bg-accent/30"
                }`}
                onClick={() => void loadRequestDetails(run.request_id)}
              >
                <div className="font-mono text-xs">{run.request_id}</div>
                <div className="text-xs text-muted-foreground">
                  {run.model_id || "model: unknown"} • {run.duration_ms}ms • features {run.unique_features_count}
                </div>
              </button>
            ))}
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Output + Summary</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {!selectedSummary && !lastRun && (
              <p className="text-sm text-muted-foreground">Run the model or select a recent request to inspect.</p>
            )}

            {selectedSummary && (
              <div className="grid gap-2 text-xs md:grid-cols-2">
                <div>request_id: {selectedSummary.request_id}</div>
                <div>status: {selectedSummary.status}</div>
                <div>duration_ms: {selectedSummary.duration_ms}</div>
                <div>output_tokens: {selectedSummary.output_tokens}</div>
                <div>events_count: {selectedSummary.events_count}</div>
                <div>actions_count: {selectedSummary.actions_count}</div>
                <div>activation_rows_count: {selectedSummary.activation_rows_count}</div>
                <div>unique_features_count: {selectedSummary.unique_features_count}</div>
              </div>
            )}

            {lastRun && selectedRequestId === lastRun.request_id && (
              <pre className="max-h-52 overflow-auto rounded-md border border-border bg-muted/30 p-3 text-xs whitespace-pre-wrap">
                {lastRun.output.text || "(empty output)"}
              </pre>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Top Features</CardTitle>
            <CardDescription>Aggregated by request (max activation + hit count).</CardDescription>
          </CardHeader>
          <CardContent>
            <pre className="max-h-64 overflow-auto rounded-md border border-border bg-muted/30 p-3 text-xs whitespace-pre-wrap">
              {topFeaturesPreview}
            </pre>
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Activation Rows</CardTitle>
            <CardDescription>Preview rows from SAE timeline.</CardDescription>
          </CardHeader>
          <CardContent>
            {!selectedRows && <p className="text-sm text-muted-foreground">No rows loaded.</p>}
            {selectedRows && (
              <div className="max-h-80 overflow-auto rounded-md border border-border">
                <table className="w-full text-xs">
                  <thead className="sticky top-0 bg-muted">
                    <tr>
                      <th className="p-2 text-left">step</th>
                      <th className="p-2 text-left">token_pos</th>
                      <th className="p-2 text-left">feature_id</th>
                      <th className="p-2 text-left">activation</th>
                      <th className="p-2 text-left">rank</th>
                    </tr>
                  </thead>
                  <tbody>
                    {selectedRows.rows.slice(0, 500).map((row, idx) => (
                      <tr key={idx} className="border-t border-border">
                        <td className="p-2">{asNumber((row as Record<string, unknown>).step)}</td>
                        <td className="p-2">{asNumber((row as Record<string, unknown>).token_position)}</td>
                        <td className="p-2">{asNumber((row as Record<string, unknown>).feature_id)}</td>
                        <td className="p-2">
                          {asNumber((row as Record<string, unknown>).activation_value).toFixed(4)}
                        </td>
                        <td className="p-2">{asNumber((row as Record<string, unknown>).rank)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Feature Delta Timeline</CardTitle>
            <CardDescription>Query per-feature activation deltas over generation.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="flex items-center gap-2">
              <input
                type="number"
                min={0}
                placeholder="Feature ID"
                className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
                value={featureIdInput}
                onChange={(e) => setFeatureIdInput(e.target.value)}
              />
              <Button onClick={() => void fetchFeatureDeltas()} disabled={isLoadingDeltas}>
                {isLoadingDeltas ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Search className="h-4 w-4" />
                )}
              </Button>
            </div>

            {!featureDeltas && (
              <p className="text-sm text-muted-foreground">
                Enter a feature ID from the rows table or top features panel.
              </p>
            )}

            {featureDeltas && (
              <div className="max-h-72 overflow-auto rounded-md border border-border bg-muted/30 p-3 font-mono text-xs">
                {featureDeltas.rows.map((row, idx) => {
                  const entry = row as Record<string, unknown>;
                  return (
                    <div key={idx}>
                      step={asNumber(entry.step)} pos={asNumber(entry.token_position)} act=
                      {asNumber(entry.activation_value).toFixed(4)} delta=
                      {entry.delta === null || entry.delta === undefined
                        ? "null"
                        : asNumber(entry.delta).toFixed(4)}
                      {" token="}
                      {asString(entry.token_id)}
                    </div>
                  );
                })}
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
