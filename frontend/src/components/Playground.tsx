import { useState, useCallback, useEffect } from "react";
import { Link } from "react-router-dom";
import {
  Play,
  Loader2,
  Code,
  Settings,
  Sparkles,
  ChevronDown,
  AlertTriangle,
  Check,
  Eye,
  EyeOff,
  Copy,
  Key,
  History,
  ExternalLink,
  X,
  Share2,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { useAuth } from "@/lib/auth";
import { trackAnalyticsEvent } from "@/hooks/useAnalytics";
import {
  generatePlaygroundKey,
  generateModCode,
  uploadMod,
  runPlaygroundInference,
  fetchLogDetail,
  fetchLogs,
  type InjectionPosition,
  type ModConfig,
  type ChatMessage,
} from "@/lib/api";
import type { LogResponse } from "@/types/api";
import { TokensView } from "@/components/LogDetail/index";
import { ShareDialog } from "@/components/Playground/ShareDialog";
import {
  getConfigFromUrl,
  type ShareablePlaygroundConfig,
} from "@/lib/shareUtils";

// Static configuration - no need to fetch from backend
const MODELS = [
  {
    id: "llama-3.1-8b",
    name: "Llama 3.1 8B",
    description: "Meta's Llama 3.1 8B Instruct model",
  },
  {
    id: "qwen-14b",
    name: "Qwen 14B",
    description: "Alibaba's Qwen 14B model",
  },
];

const POSITIONS = [
  {
    id: "start" as InjectionPosition,
    name: "Start of Generation",
    description: "Inject tokens at the very start of the model's response",
    requires_token_count: false,
    requires_sentence_count: false,
    requires_detect_phrase: false,
    requires_qwen: false,
  },
  {
    id: "after_tokens" as InjectionPosition,
    name: "After N Tokens",
    description: "Inject tokens after the model has generated N tokens",
    requires_token_count: true,
    requires_sentence_count: false,
    requires_detect_phrase: false,
    requires_qwen: false,
  },
  {
    id: "after_sentences" as InjectionPosition,
    name: "After N Sentences",
    description: "Inject tokens after N sentence-ending punctuation marks",
    requires_token_count: false,
    requires_sentence_count: true,
    requires_detect_phrase: false,
    requires_qwen: false,
  },
  {
    id: "eot_backtrack" as InjectionPosition,
    name: "Before End of Turn",
    description: "Detect end-of-turn token, backtrack, and inject before it",
    requires_token_count: false,
    requires_sentence_count: false,
    requires_detect_phrase: false,
    requires_qwen: false,
  },
  {
    id: "phrase_replace" as InjectionPosition,
    name: "Phrase Detection & Replace",
    description: "Detect a specific phrase in the output and replace it",
    requires_token_count: false,
    requires_sentence_count: false,
    requires_detect_phrase: true,
    requires_qwen: false,
  },
  // Reasoning model positions (Qwen only)
  {
    id: "reasoning_start" as InjectionPosition,
    name: "Start of Reasoning",
    description: "Inject right after <think> tag opens",
    requires_token_count: false,
    requires_sentence_count: false,
    requires_detect_phrase: false,
    requires_qwen: true,
  },
  {
    id: "reasoning_mid" as InjectionPosition,
    name: "Mid Reasoning",
    description: "Inject after N tokens within the <think> block",
    requires_token_count: true,
    requires_sentence_count: false,
    requires_detect_phrase: false,
    requires_qwen: true,
  },
  {
    id: "reasoning_end" as InjectionPosition,
    name: "End of Reasoning",
    description: "Inject right before </think> tag closes",
    requires_token_count: false,
    requires_sentence_count: false,
    requires_detect_phrase: false,
    requires_qwen: true,
  },
  {
    id: "response_start" as InjectionPosition,
    name: "Start of Response",
    description: "Inject right after </think> when the response begins",
    requires_token_count: false,
    requires_sentence_count: false,
    requires_detect_phrase: false,
    requires_qwen: true,
  },
  {
    id: "response_mid" as InjectionPosition,
    name: "Mid Response",
    description: "Inject after N tokens in the response (after reasoning)",
    requires_token_count: true,
    requires_sentence_count: false,
    requires_detect_phrase: false,
    requires_qwen: true,
  },
  {
    id: "response_end" as InjectionPosition,
    name: "End of Response",
    description: "Inject before EOS token in the response phase",
    requires_token_count: false,
    requires_sentence_count: false,
    requires_detect_phrase: false,
    requires_qwen: true,
  },
  {
    id: "reasoning_phrase_replace" as InjectionPosition,
    name: "Reasoning Phrase Replace",
    description: "Detect and replace a phrase within the <think> block",
    requires_token_count: false,
    requires_sentence_count: false,
    requires_detect_phrase: true,
    requires_qwen: true,
  },
  {
    id: "response_phrase_replace" as InjectionPosition,
    name: "Response Phrase Replace",
    description:
      "Detect and replace a phrase in the response (after reasoning)",
    requires_token_count: false,
    requires_sentence_count: false,
    requires_detect_phrase: true,
    requires_qwen: true,
  },
  {
    id: "full_stream_phrase_replace" as InjectionPosition,
    name: "Full Stream Phrase Replace",
    description: "Detect and replace a phrase across reasoning and response",
    requires_token_count: false,
    requires_sentence_count: false,
    requires_detect_phrase: true,
    requires_qwen: true,
  },
];

// localStorage key for persistent playground API key
const PLAYGROUND_API_KEY_STORAGE = "playground_api_key";
// Main app's API key storage (from auth.tsx)
const MAIN_APP_API_KEY_STORAGE = "concordance_api_key";
// localStorage key for dismissing the "What is this" section
const WHAT_IS_THIS_DISMISSED_KEY = "playground_what_is_this_dismissed";

type PlaygroundStep =
  | "configure"
  | "generating_key"
  | "generating_mod"
  | "uploading_mod"
  | "spinning_up_resources"
  | "running_inference"
  | "fetching_results"
  | "complete"
  | "error";

interface PlaygroundState {
  step: PlaygroundStep;
  apiKey: string | null;
  modCode: string | null;
  modName: string | null;
  inferenceResult: {
    text: string;
    requestId: string | null;
  } | null;
  logData: LogResponse | null;
  error: string | null;
}

// Simple Python syntax highlighting
function highlightPython(code: string): React.ReactNode[] {
  const lines = code.split("\n");

  return lines.map((line, lineIndex) => {
    // Preserve leading whitespace
    const leadingMatch = line.match(/^(\s*)/);
    const indent = leadingMatch ? leadingMatch[1] : "";
    let remaining = line.slice(indent.length);

    const elements: React.ReactNode[] = [];
    let key = 0;

    // Add preserved indentation
    if (indent) {
      elements.push(<span key={key++}>{indent}</span>);
    }

    // Process rest of line
    while (remaining.length > 0) {
      // Comments
      const commentMatch = remaining.match(/^(#.*)$/);
      if (commentMatch) {
        elements.push(
          <span key={key++} className="text-emerald-600">
            {commentMatch[1]}
          </span>,
        );
        remaining = "";
        continue;
      }

      // Decorators
      const decoratorMatch = remaining.match(/^(@\w+)/);
      if (decoratorMatch) {
        elements.push(
          <span key={key++} className="text-yellow-500">
            {decoratorMatch[1]}
          </span>,
        );
        remaining = remaining.slice(decoratorMatch[1].length);
        continue;
      }

      // Strings (double quotes)
      const doubleStringMatch = remaining.match(/^("(?:[^"\\]|\\.)*")/);
      if (doubleStringMatch) {
        elements.push(
          <span key={key++} className="text-amber-400">
            {doubleStringMatch[1]}
          </span>,
        );
        remaining = remaining.slice(doubleStringMatch[1].length);
        continue;
      }

      // Strings (single quotes)
      const singleStringMatch = remaining.match(/^('(?:[^'\\]|\\.)*')/);
      if (singleStringMatch) {
        elements.push(
          <span key={key++} className="text-amber-400">
            {singleStringMatch[1]}
          </span>,
        );
        remaining = remaining.slice(singleStringMatch[1].length);
        continue;
      }

      // Keywords
      const keywordMatch = remaining.match(
        /^(def|class|if|elif|else|for|while|return|import|from|as|not|and|or|in|is|None|True|False|dict|str|int|bool|list)\b/,
      );
      if (keywordMatch) {
        elements.push(
          <span key={key++} className="text-purple-400 font-medium">
            {keywordMatch[1]}
          </span>,
        );
        remaining = remaining.slice(keywordMatch[1].length);
        continue;
      }

      // Built-in functions
      const builtinMatch = remaining.match(
        /^(len|get|isinstance|print|range|type)\b/,
      );
      if (builtinMatch) {
        elements.push(
          <span key={key++} className="text-cyan-400">
            {builtinMatch[1]}
          </span>,
        );
        remaining = remaining.slice(builtinMatch[1].length);
        continue;
      }

      // Function definitions (name after def)
      const funcDefMatch = remaining.match(/^(\w+)(\s*\()/);
      if (funcDefMatch && elements.length > 0) {
        const lastEl = elements[elements.length - 1];
        if (
          typeof lastEl === "object" &&
          lastEl !== null &&
          "props" in lastEl
        ) {
          const props = lastEl.props as { children?: string };
          if (props.children === "def") {
            elements.push(
              <span key={key++} className="text-blue-400">
                {funcDefMatch[1]}
              </span>,
            );
            elements.push(<span key={key++}>{funcDefMatch[2]}</span>);
            remaining = remaining.slice(funcDefMatch[0].length);
            continue;
          }
        }
      }

      // Numbers
      const numberMatch = remaining.match(/^(\d+)/);
      if (numberMatch) {
        elements.push(
          <span key={key++} className="text-orange-400">
            {numberMatch[1]}
          </span>,
        );
        remaining = remaining.slice(numberMatch[1].length);
        continue;
      }

      // Default: take one character
      elements.push(<span key={key++}>{remaining[0]}</span>);
      remaining = remaining.slice(1);
    }

    return (
      <div key={lineIndex}>{elements.length > 0 ? elements : "\u00A0"}</div>
    );
  });
}

export default function Playground() {
  const { login, isAuthenticated } = useAuth();

  // Form state
  const [selectedModel, setSelectedModel] = useState<string>(MODELS[0].id);
  const [systemPrompt, setSystemPrompt] = useState<string>(
    "You are a helpful assistant.",
  );
  const [userPrompt, setUserPrompt] = useState<string>(
    "Tell me a fact about bread.",
  );
  const [injectionString, setInjectionString] = useState<string>(
    " [INJECTED: Remember to be helpful!] ",
  );
  const [injectionPosition, setInjectionPosition] =
    useState<InjectionPosition>("phrase_replace");
  const [tokenCount, setTokenCount] = useState<number | "">(10);
  const [sentenceCount, setSentenceCount] = useState<number | "">(1);
  const [detectPhrases, setDetectPhrases] = useState<string[]>([
    "",
    "",
    "",
    "",
  ]);
  const [replacementPhrases, setReplacementPhrases] = useState<string[]>([
    "",
    "",
    "",
    "",
  ]);
  const [maxTokens, setMaxTokens] = useState<number | "">(256);
  const [temperature, setTemperature] = useState<number>(0.7);
  const [enableMod, setEnableMod] = useState<boolean>(true);

  // UI state
  const [showGeneratedCode, setShowGeneratedCode] = useState(false);
  const [codeCopied, setCodeCopied] = useState(false);
  const [apiKeyCopied, setApiKeyCopied] = useState(false);
  const [shareDialogOpen, setShareDialogOpen] = useState(false);
  const [whatIsThisDismissed, setWhatIsThisDismissed] = useState(() => {
    if (typeof window !== "undefined") {
      return localStorage.getItem(WHAT_IS_THIS_DISMISSED_KEY) === "true";
    }
    return false;
  });

  const dismissWhatIsThis = useCallback(() => {
    setWhatIsThisDismissed(true);
    localStorage.setItem(WHAT_IS_THIS_DISMISSED_KEY, "true");
  }, []);

  // Persistent API key state
  const [playgroundApiKey, setPlaygroundApiKey] = useState<string | null>(null);

  // History state
  const [history, setHistory] = useState<LogResponse[]>([]);
  const [historyOpen, setHistoryOpen] = useState(() => {
    if (typeof window !== "undefined") {
      return window.innerWidth >= 1024; // lg breakpoint
    }
    return true;
  });
  const [historyLoading, setHistoryLoading] = useState(false);

  // Execution state
  const [state, setState] = useState<PlaygroundState>({
    step: "configure",
    apiKey: null,
    modCode: null,
    modName: null,
    inferenceResult: null,
    logData: null,
    error: null,
  });

  // Get current position info
  const currentPosition = POSITIONS.find((p) => p.id === injectionPosition);

  // Build mod config
  const buildModConfig = useCallback((): ModConfig => {
    const config: ModConfig = {
      injection_string: injectionString,
      position: injectionPosition,
    };

    if (
      injectionPosition === "after_tokens" ||
      injectionPosition === "reasoning_mid" ||
      injectionPosition === "response_mid"
    ) {
      config.token_count = tokenCount === "" ? 10 : tokenCount;
    } else if (injectionPosition === "after_sentences") {
      config.sentence_count = sentenceCount === "" ? 1 : sentenceCount;
    } else if (
      injectionPosition === "phrase_replace" ||
      injectionPosition === "reasoning_phrase_replace" ||
      injectionPosition === "response_phrase_replace" ||
      injectionPosition === "full_stream_phrase_replace"
    ) {
      // Filter out empty phrase pairs and build arrays
      const validPairs = detectPhrases
        .map((dp, i) => ({ detect: dp, replace: replacementPhrases[i] || dp }))
        .filter((pair) => pair.detect.trim() !== "");
      config.detect_phrases = validPairs.map((p) => p.detect);
      config.replacement_phrases = validPairs.map((p) => p.replace);
    }

    return config;
  }, [
    injectionString,
    injectionPosition,
    tokenCount,
    sentenceCount,
    detectPhrases,
    replacementPhrases,
  ]);

  // Initialize persistent API key on mount
  useEffect(() => {
    const initializeApiKey = async () => {
      try {
        // Check localStorage first
        const storedKey = localStorage.getItem(PLAYGROUND_API_KEY_STORAGE);
        if (storedKey) {
          setPlaygroundApiKey(storedKey);
          // Also sync with main app if not already authenticated
          if (!isAuthenticated) {
            localStorage.setItem(MAIN_APP_API_KEY_STORAGE, storedKey);
            login(storedKey);
          }
        } else {
          // Generate a new key and store it
          const response = await generatePlaygroundKey();
          localStorage.setItem(PLAYGROUND_API_KEY_STORAGE, response.api_key);
          // Also store for main app and login
          localStorage.setItem(MAIN_APP_API_KEY_STORAGE, response.api_key);
          setPlaygroundApiKey(response.api_key);
          login(response.api_key);
        }
      } catch (error) {
        console.error("Failed to initialize playground API key:", error);
      }
    };
    initializeApiKey();
  }, [isAuthenticated, login]);

  // Load history when API key is available
  const loadHistory = useCallback(async () => {
    if (!playgroundApiKey) return;
    setHistoryLoading(true);
    try {
      const logsResponse = await fetchLogs(20, 0, { apiKey: playgroundApiKey });
      if (logsResponse.data && logsResponse.data.length > 0) {
        // Fetch full details for each log
        const detailed = await Promise.all(
          logsResponse.data.map((log) =>
            fetchLogDetail(log.request_id, { apiKey: playgroundApiKey }),
          ),
        );
        setHistory(detailed);
      }
    } catch (error) {
      console.error("Failed to load history:", error);
    } finally {
      setHistoryLoading(false);
    }
  }, [playgroundApiKey]);

  useEffect(() => {
    if (playgroundApiKey) {
      loadHistory();
    }
  }, [playgroundApiKey, loadHistory]);

  // Reset injection position when switching models if current position doesn't match model type
  useEffect(() => {
    const isQwenModel = selectedModel.toLowerCase().includes("qwen");
    const currentPos = POSITIONS.find((p) => p.id === injectionPosition);
    if (isQwenModel && !currentPos?.requires_qwen) {
      setInjectionPosition("full_stream_phrase_replace");
    } else if (!isQwenModel && currentPos?.requires_qwen) {
      setInjectionPosition("phrase_replace");
    }
  }, [selectedModel, injectionPosition]);

  // Restore config from URL ?s= param on mount
  useEffect(() => {
    const sharedConfig = getConfigFromUrl();
    if (sharedConfig) {
      setSelectedModel(sharedConfig.model);
      setMaxTokens(sharedConfig.maxTokens);
      setTemperature(sharedConfig.temperature);
      setSystemPrompt(sharedConfig.systemPrompt);
      setUserPrompt(sharedConfig.userPrompt);
      setEnableMod(sharedConfig.enableMod);
      setInjectionPosition(sharedConfig.injectionPosition);
      if (sharedConfig.injectionString !== undefined) {
        setInjectionString(sharedConfig.injectionString);
      }
      if (sharedConfig.tokenCount !== undefined) {
        setTokenCount(sharedConfig.tokenCount);
      }
      if (sharedConfig.sentenceCount !== undefined) {
        setSentenceCount(sharedConfig.sentenceCount);
      }
      if (sharedConfig.detectPhrases) {
        // Pad with empty strings to ensure 4 elements
        const padded = [...sharedConfig.detectPhrases];
        while (padded.length < 4) padded.push("");
        setDetectPhrases(padded);
      }
      if (sharedConfig.replacementPhrases) {
        const padded = [...sharedConfig.replacementPhrases];
        while (padded.length < 4) padded.push("");
        setReplacementPhrases(padded);
      }
      // Clear the URL param after restoring (optional, for cleaner URL)
      window.history.replaceState({}, "", window.location.pathname);
    }
  }, []);

  // Build shareable config from current state
  const buildShareableConfig = useCallback((): ShareablePlaygroundConfig => {
    const config: ShareablePlaygroundConfig = {
      model: selectedModel,
      maxTokens: maxTokens === "" ? 256 : maxTokens,
      temperature,
      systemPrompt,
      userPrompt,
      enableMod,
      injectionPosition,
    };

    const currentPos = POSITIONS.find((p) => p.id === injectionPosition);

    if (!currentPos?.requires_detect_phrase && injectionString) {
      config.injectionString = injectionString;
    }
    if (currentPos?.requires_token_count) {
      config.tokenCount = tokenCount === "" ? 10 : tokenCount;
    }
    if (currentPos?.requires_sentence_count) {
      config.sentenceCount = sentenceCount === "" ? 1 : sentenceCount;
    }
    if (currentPos?.requires_detect_phrase) {
      config.detectPhrases = detectPhrases.filter((p) => p.trim());
      config.replacementPhrases = replacementPhrases.filter((_, i) =>
        detectPhrases[i]?.trim(),
      );
    }

    return config;
  }, [
    selectedModel,
    maxTokens,
    temperature,
    systemPrompt,
    userPrompt,
    enableMod,
    injectionPosition,
    injectionString,
    tokenCount,
    sentenceCount,
    detectPhrases,
    replacementPhrases,
  ]);

  // Run the full pipeline
  const handleRun = useCallback(async () => {
    if (!playgroundApiKey) {
      return;
    }

    setState({
      step: "generating_mod",
      apiKey: playgroundApiKey,
      modCode: null,
      modName: null,
      inferenceResult: null,
      logData: null,
      error: null,
    });

    try {
      // Use the persistent API key
      const apiKey = playgroundApiKey;

      let modName: string | null = null;
      let modCode: string | null = null;

      if (enableMod) {
        // Step 1: Generate mod code
        setState((prev) => ({ ...prev, step: "generating_mod" }));
        const modConfig = buildModConfig();
        const modRes = await generateModCode(modConfig);
        modCode = modRes.code;
        modName = modRes.mod_name;
        setState((prev) => ({ ...prev, modCode, modName }));

        // Step 2: Upload mod (with "spinning up resources" after 1 second)
        setState((prev) => ({ ...prev, step: "uploading_mod" }));
        const spinUpTimer = setTimeout(() => {
          setState((prev) => {
            // Only transition if we're still uploading
            if (prev.step === "uploading_mod") {
              return { ...prev, step: "spinning_up_resources" };
            }
            return prev;
          });
        }, 1000);

        try {
          await uploadMod(selectedModel, modCode, modName, apiKey);
        } finally {
          clearTimeout(spinUpTimer);
        }
      }

      // Step 3: Run inference
      setState((prev) => ({ ...prev, step: "running_inference" }));
      const messages: ChatMessage[] = [
        { role: "system", content: systemPrompt },
        { role: "user", content: userPrompt },
      ];
      const inferenceRes = await runPlaygroundInference(
        selectedModel,
        messages,
        apiKey,
        enableMod ? (modName ?? undefined) : undefined,
        maxTokens === "" ? 256 : maxTokens,
        temperature,
      );
      setState((prev) => ({
        ...prev,
        inferenceResult: {
          text: inferenceRes.text,
          requestId: inferenceRes.request_id,
        },
      }));

      // Step 5: Fetch detailed logs by polling for logs with our API key
      setState((prev) => ({ ...prev, step: "fetching_results" }));

      // Poll for the log to appear (inference server sends it asynchronously)
      let logData = null;
      const maxAttempts = 10;
      const delayMs = 1000;

      for (let attempt = 0; attempt < maxAttempts; attempt++) {
        await new Promise((resolve) => setTimeout(resolve, delayMs));
        try {
          // Fetch most recent log for this API key
          const logsResponse = await fetchLogs(1, 0, { apiKey });
          if (logsResponse.data && logsResponse.data.length > 0) {
            const recentLog = logsResponse.data[0];
            // Fetch the full log detail
            const detail = await fetchLogDetail(recentLog.request_id, {
              apiKey,
            });
            logData = detail;
            break;
          }
        } catch {
          // Log not ready yet, continue polling
        }
      }

      if (logData) {
        setState((prev) => ({ ...prev, logData, step: "complete" }));
        // Stay on configure tab - user can click "Explore" to see full results
      } else {
        setState((prev) => ({ ...prev, step: "complete" }));
      }

      // Track successful inference run (max 2 properties)
      trackAnalyticsEvent("playground_run", {
        model: selectedModel,
        mod_enabled: enableMod,
      });

      // Refresh history after completion
      loadHistory();
    } catch (err) {
      // Track failed inference run (max 2 properties)
      trackAnalyticsEvent("playground_error", {
        model: selectedModel,
        error_type: err instanceof Error ? err.name : "unknown",
      });

      setState((prev) => ({
        ...prev,
        step: "error",
        error: err instanceof Error ? err.message : "An error occurred",
      }));
    }
  }, [
    playgroundApiKey,
    selectedModel,
    systemPrompt,
    userPrompt,
    maxTokens,
    temperature,
    enableMod,
    buildModConfig,
    loadHistory,
  ]);

  // Reset to configure state
  const handleReset = useCallback(() => {
    setState({
      step: "configure",
      apiKey: playgroundApiKey,
      modCode: null,
      modName: null,
      inferenceResult: null,
      logData: null,
      error: null,
    });
  }, [playgroundApiKey]);

  // Handle share status changes from ShareDialog
  const handleShareStatusChange = useCallback(
    (isPublic: boolean, publicToken: string | null) => {
      setState((prev) => {
        if (!prev.logData) return prev;
        return {
          ...prev,
          logData: {
            ...prev.logData,
            is_public: isPublic,
            public_token: publicToken,
          },
        };
      });
    },
    [],
  );

  const isRunning = [
    "generating_mod",
    "uploading_mod",
    "spinning_up_resources",
    "running_inference",
    "fetching_results",
  ].includes(state.step);

  return (
    <div className="h-full flex flex-col bg-background px-2 sm:px-4">
      {/* Header */}
      <div className="shrink-0 flex items-center justify-between mb-3 sm:mb-4 px-1 max-w-5xl mx-auto w-full">
        <div className="flex items-center gap-2 sm:gap-3">
          <div className="flex items-center gap-1.5 sm:gap-2">
            <h1 className="text-sm sm:text-lg font-semibold font-mono text-foreground tracking-wide">
              <span className="xs:inline">Token Injection Lab</span>
            </h1>
          </div>
          <span className="hidden sm:inline px-2 py-0.5 text-[10px] font-mono uppercase tracking-wider bg-emerald-500/10 text-emerald-500 border border-emerald-500/50 rounded-sm">
            Beta
          </span>
        </div>

        <div className="flex items-center gap-2 sm:gap-3">
          {state.step !== "configure" && (
            <Button
              variant="outline"
              size="sm"
              onClick={handleReset}
              className="text-[10px] sm:text-[11px] px-2 sm:px-3"
            >
              <span className="hidden sm:inline">New </span>
            </Button>
          )}
        </div>
      </div>

      {/* Main Content */}
      <div className="flex-1 min-h-0 overflow-auto">
        <div className="flex flex-col lg:flex-row gap-4 w-full max-w-5xl mx-auto px-2 sm:px-4">
          {/* Sidebar - Left Column on desktop, top section on mobile */}
          <div className="shrink-0 max-w-3xl w-full lg:w-64 lg:self-start bg-card border border-border rounded relative flex flex-col overflow-hidden">
            {/* API Key Section - Desktop only */}
            {playgroundApiKey && (
              <div className="hidden lg:block border-b border-border shrink-0">
                <div className="flex items-center justify-between px-3 py-2 text-[10px] font-mono uppercase tracking-wider text-muted-foreground">
                  <span className="flex items-center gap-2">
                    <Key className="h-3 w-3" />
                    API Key
                  </span>
                  <button
                    className="p-1 rounded transition-colors hover:bg-muted"
                    onClick={() => {
                      navigator.clipboard.writeText(playgroundApiKey);
                      setApiKeyCopied(true);
                      setTimeout(() => setApiKeyCopied(false), 2000);
                    }}
                    title="Copy API key"
                  >
                    {apiKeyCopied ? (
                      <Check className="h-3 w-3 text-emerald-500" />
                    ) : (
                      <Copy className="h-3 w-3" />
                    )}
                  </button>
                </div>
                <div className="p-3">
                  <code className="text-[10px] block overflow-x-auto whitespace-nowrap font-mono bg-muted px-2 py-1 rounded">
                    {playgroundApiKey.slice(0, 20)}...
                  </code>
                  <p className="text-[10px] mt-2 text-muted-foreground">
                    Use with SDK for custom mods
                  </p>
                </div>
              </div>
            )}

            {/* History Section */}
            <div className="flex-1 flex flex-col min-h-0">
              <button
                onClick={() => setHistoryOpen(!historyOpen)}
                className="flex items-center justify-between w-full px-3 py-2 text-[10px] font-mono uppercase tracking-wider text-muted-foreground hover:text-foreground transition-colors border-b border-border shrink-0"
              >
                <span className="flex items-center gap-2">
                  <History className="h-3 w-3" />
                  <span className="hidden sm:inline">History</span>
                  {history.length > 0 && (
                    <span className="px-1.5 py-0.5 text-[9px] rounded bg-muted text-muted-foreground">
                      {history.length}
                    </span>
                  )}
                </span>
                <ChevronDown
                  className={cn(
                    "h-3 w-3 transition-transform",
                    historyOpen && "rotate-180",
                  )}
                />
              </button>

              {historyOpen && (
                <div className="max-h-64 lg:max-h-96 overflow-y-auto bg-card">
                  {historyLoading ? (
                    <div className="flex items-center justify-center p-4">
                      <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
                    </div>
                  ) : history.length === 0 ? (
                    <div className="p-4 text-center text-[11px] text-muted-foreground">
                      No experiments yet.
                    </div>
                  ) : (
                    history.map((log) => (
                      <button
                        key={log.request_id}
                        onClick={() => {
                          // Restore configuration from log
                          if (log.model_id) {
                            // Map full model ID to our model selector
                            const modelMatch = MODELS.find((m) =>
                              log.model_id
                                ?.toLowerCase()
                                .includes(m.id.replace("-", "")),
                            );
                            if (modelMatch) {
                              setSelectedModel(modelMatch.id);
                            }
                          }
                          if (log.system_prompt) {
                            setSystemPrompt(log.system_prompt);
                          }
                          if (log.user_prompt) {
                            setUserPrompt(log.user_prompt);
                          }
                          if (log.max_steps) {
                            setMaxTokens(log.max_steps);
                          }
                          // Show the result
                          setState((prev) => ({
                            ...prev,
                            logData: log,
                            step: "complete",
                          }));
                        }}
                        className="w-full text-left px-3 py-2 border-b border-border hover:bg-muted/50 transition-colors"
                      >
                        <div className="text-[10px] flex items-center gap-1 text-muted-foreground">
                          <span>{formatRelativeTime(log.created_ts)}</span>
                          <span>·</span>
                          <span className="text-emerald-500">
                            {getModelShortName(log.model_id)}
                          </span>
                        </div>
                        <div className="text-[11px] mt-1 truncate text-foreground">
                          {getPromptPreview(log)}
                        </div>
                        <div className="text-[11px] mt-1 truncate text-muted-foreground">
                          {getResponsePreview(log)}
                        </div>
                      </button>
                    ))
                  )}
                </div>
              )}
            </div>
          </div>

          {/* Main Config - Right Column */}
          <div className="flex-1 min-w-0 max-w-3xl space-y-4">
            {/* About Section */}
            {!whatIsThisDismissed && (
              <div className="px-3 py-2 text-sm text-muted-foreground bg-muted/30 border border-border/50 rounded relative pr-8">
                <button
                  onClick={dismissWhatIsThis}
                  className="absolute top-2 right-2 w-5 h-5 rounded-full bg-muted hover:bg-muted-foreground/20 flex items-center justify-center text-muted-foreground hover:text-foreground transition-colors"
                  aria-label="Dismiss"
                >
                  <X className="h-3 w-3" />
                </button>
                <span className="font-medium text-foreground">
                  What is this?
                </span>{" "}
                A playground for exploring token injection — inject words,
                concepts, or phrases directly into the LLM's generation stream
                to steer its output trajectory. See how forced tokens affect
                model behavior in real-time. Read our research paper{" "}
                <a
                  href="https://www.concordance.co/blog/token-injection-steering-llms"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-emerald-500 hover:underline"
                >
                  here
                </a>
                .
              </div>
            )}

            {/* Configuration Row - Model + Max Tokens + Temperature */}
            <div className="panel">
              <div className="panel-header">
                <span className="flex items-center gap-2">
                  <Settings className="h-3 w-3" />
                  <span className="panel-title">Configuration</span>
                </span>
              </div>
              <div className="p-3">
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                  <div>
                    <label className="block mb-1.5 text-[10px] font-mono font-medium uppercase tracking-wide text-muted-foreground">
                      Model
                    </label>
                    <select
                      value={selectedModel}
                      onChange={(e) => setSelectedModel(e.target.value)}
                      disabled={isRunning}
                      className="w-full px-2 py-1.5 text-xs font-mono bg-background border border-border rounded focus:outline-none focus:ring-1 focus:ring-primary"
                    >
                      {MODELS.map((model) => (
                        <option key={model.id} value={model.id}>
                          {model.name}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label className="block mb-1.5 text-[10px] font-mono font-medium uppercase tracking-wide text-muted-foreground">
                      Max Tokens
                    </label>
                    <input
                      type="number"
                      value={maxTokens}
                      onChange={(e) =>
                        setMaxTokens(
                          e.target.value === "" ? "" : parseInt(e.target.value),
                        )
                      }
                      onBlur={() =>
                        setMaxTokens((v) =>
                          v === "" || v < 1 ? 256 : Math.min(2048, v),
                        )
                      }
                      disabled={isRunning}
                      min={1}
                      max={2048}
                      className="w-full px-2 py-1.5 text-xs font-mono bg-background border border-border rounded focus:outline-none focus:ring-1 focus:ring-primary"
                    />
                  </div>
                  <div>
                    <label className="block mb-1.5 text-[10px] font-mono font-medium uppercase tracking-wide text-muted-foreground">
                      Temperature
                    </label>
                    <input
                      type="number"
                      value={temperature}
                      onChange={(e) =>
                        setTemperature(
                          Math.max(
                            0,
                            Math.min(2, parseFloat(e.target.value) || 0.7),
                          ),
                        )
                      }
                      disabled={isRunning}
                      min={0}
                      max={2}
                      step={0.1}
                      className="w-full px-2 py-1.5 text-xs font-mono bg-background border border-border rounded focus:outline-none focus:ring-1 focus:ring-primary"
                    />
                  </div>
                </div>
              </div>
            </div>

            {/* Prompts */}
            <div className="panel">
              <div className="panel-header">
                <span className="panel-title">Input</span>
              </div>
              <div className="p-3 space-y-3">
                <div>
                  <label className="block mb-1.5 text-[10px] font-mono font-medium uppercase tracking-wide text-muted-foreground">
                    System Prompt
                  </label>
                  <textarea
                    value={systemPrompt}
                    onChange={(e) => setSystemPrompt(e.target.value)}
                    disabled={isRunning}
                    rows={2}
                    className="w-full px-2 py-1.5 text-xs font-mono bg-background border border-border rounded focus:outline-none focus:ring-1 focus:ring-primary resize-none"
                    placeholder="You are a helpful assistant..."
                  />
                </div>
                <div>
                  <label className="block mb-1.5 text-[10px] font-mono font-medium uppercase tracking-wide text-muted-foreground">
                    User Prompt
                  </label>
                  <textarea
                    value={userPrompt}
                    onChange={(e) => setUserPrompt(e.target.value)}
                    disabled={isRunning}
                    rows={3}
                    className="w-full px-2 py-1.5 text-xs font-mono bg-background border border-border rounded focus:outline-none focus:ring-1 focus:ring-primary resize-none"
                    placeholder="What would you like to ask?"
                  />
                </div>
              </div>
            </div>

            {/* Token Injection - HERO ELEMENT */}
            <div className="panel border-emerald-500/50 shadow-[0_0_10px_rgba(16,185,129,0.1)]">
              <div className="panel-header flex items-center justify-between border-b-emerald-500/30">
                <span className="flex items-center gap-2 text-emerald-500">
                  <Sparkles className="h-3.5 w-3.5" />
                  <span className="panel-title text-emerald-500">
                    Token Injection Module
                  </span>
                </span>
                <label className="flex items-center gap-2 cursor-pointer">
                  <span className="text-[10px] uppercase tracking-wide text-muted-foreground">
                    Enable
                  </span>
                  <button
                    onClick={() => setEnableMod(!enableMod)}
                    disabled={isRunning}
                    className={cn(
                      "relative w-9 h-5 rounded-full transition-colors",
                      enableMod ? "bg-emerald-500" : "bg-muted",
                    )}
                  >
                    <span
                      className={cn(
                        "absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-white shadow transition-transform",
                        enableMod && "translate-x-4",
                      )}
                    />
                  </button>
                </label>
              </div>
              <div className={cn("p-3 space-y-3", !enableMod && "opacity-50")}>
                {/* Injection String - greyed out for phrase replace positions */}
                <div
                  className={cn(
                    currentPosition?.requires_detect_phrase && "opacity-50",
                  )}
                >
                  <label className="block mb-1.5 text-[10px] font-mono font-medium uppercase tracking-wide text-muted-foreground">
                    Injection String
                  </label>
                  {currentPosition?.requires_detect_phrase ? (
                    <div className="w-full px-2 py-2 text-xs font-mono bg-muted/50 border border-border rounded text-muted-foreground italic">
                      Use phrase pairs below in this mode
                    </div>
                  ) : (
                    <textarea
                      value={injectionString}
                      onChange={(e) => setInjectionString(e.target.value)}
                      disabled={isRunning || !enableMod}
                      rows={2}
                      className={cn(
                        "w-full px-2 py-1.5 text-xs font-mono bg-background border rounded focus:outline-none focus:ring-1 focus:ring-primary resize-none",
                        enableMod ? "border-emerald-500/50" : "border-border",
                      )}
                      placeholder="Text to inject..."
                    />
                  )}
                </div>

                {/* Position Selection */}
                <div>
                  <label className="block mb-1.5 text-[10px] font-mono font-medium uppercase tracking-wide text-muted-foreground">
                    Injection Position
                  </label>
                  <select
                    value={injectionPosition}
                    onChange={(e) =>
                      setInjectionPosition(e.target.value as InjectionPosition)
                    }
                    disabled={isRunning || !enableMod}
                    className="w-full px-2 py-1.5 text-xs font-mono bg-background border border-border rounded focus:outline-none focus:ring-1 focus:ring-primary"
                  >
                    {POSITIONS.filter((pos) => {
                      const isQwenModel = selectedModel
                        .toLowerCase()
                        .includes("qwen");
                      return isQwenModel
                        ? pos.requires_qwen
                        : !pos.requires_qwen;
                    }).map((pos) => (
                      <option key={pos.id} value={pos.id}>
                        {pos.name}
                      </option>
                    ))}
                  </select>
                  <p className="text-[10px] mt-1.5 text-muted-foreground">
                    {currentPosition?.description}
                  </p>
                </div>

                {/* Position-specific options */}
                {currentPosition?.requires_token_count && (
                  <div>
                    <label className="block mb-1.5 text-[10px] font-mono font-medium uppercase tracking-wide text-muted-foreground">
                      After N Tokens
                    </label>
                    <input
                      type="number"
                      value={tokenCount}
                      onChange={(e) =>
                        setTokenCount(
                          e.target.value === "" ? "" : parseInt(e.target.value),
                        )
                      }
                      onBlur={() =>
                        setTokenCount((v) => (v === "" || v < 1 ? 10 : v))
                      }
                      disabled={isRunning || !enableMod}
                      min={1}
                      className="w-full px-2 py-1.5 text-xs font-mono bg-background border border-border rounded focus:outline-none focus:ring-1 focus:ring-primary"
                    />
                  </div>
                )}

                {currentPosition?.requires_sentence_count && (
                  <div>
                    <label className="block mb-1.5 text-[10px] font-mono font-medium uppercase tracking-wide text-muted-foreground">
                      After N Sentences
                    </label>
                    <input
                      type="number"
                      value={sentenceCount}
                      onChange={(e) =>
                        setSentenceCount(
                          e.target.value === "" ? "" : parseInt(e.target.value),
                        )
                      }
                      onBlur={() =>
                        setSentenceCount((v) => (v === "" || v < 1 ? 1 : v))
                      }
                      disabled={isRunning || !enableMod}
                      min={1}
                      className="w-full px-2 py-1.5 text-xs font-mono bg-background border border-border rounded focus:outline-none focus:ring-1 focus:ring-primary"
                    />
                  </div>
                )}

                {currentPosition?.requires_detect_phrase && (
                  <div className="space-y-2">
                    <label className="block text-[10px] font-mono font-medium uppercase tracking-wide text-muted-foreground">
                      Phrase Pairs (detect → replace)
                    </label>
                    <p className="text-[10px] text-muted-foreground -mt-1">
                      Add up to 4 pairs to handle capitalization variants (e.g.,
                      "Cats" → "Lizards", "cats" → "lizards")
                    </p>
                    {[0, 1, 2, 3].map((i) => (
                      <div key={i} className="flex items-center gap-2">
                        <input
                          type="text"
                          value={detectPhrases[i]}
                          onChange={(e) => {
                            const newPhrases = [...detectPhrases];
                            newPhrases[i] = e.target.value;
                            setDetectPhrases(newPhrases);
                          }}
                          disabled={isRunning || !enableMod}
                          className="flex-1 px-2 py-1.5 text-xs font-mono bg-background border border-border rounded focus:outline-none focus:ring-1 focus:ring-primary"
                          placeholder={i === 0 ? "e.g., Cats" : ""}
                        />
                        <span className="text-muted-foreground text-xs">→</span>
                        <input
                          type="text"
                          value={replacementPhrases[i]}
                          onChange={(e) => {
                            const newPhrases = [...replacementPhrases];
                            newPhrases[i] = e.target.value;
                            setReplacementPhrases(newPhrases);
                          }}
                          disabled={isRunning || !enableMod}
                          className="flex-1 px-2 py-1.5 text-xs font-mono bg-background border border-border rounded focus:outline-none focus:ring-1 focus:ring-primary"
                          placeholder={i === 0 ? "e.g., Lizards" : ""}
                        />
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>

            {/* Run Button & Status */}
            <div className="space-y-4">
              <div className="flex gap-2">
                <Button
                  className="flex-1 py-3 bg-emerald-600 hover:bg-emerald-700 text-white"
                  onClick={handleRun}
                  disabled={isRunning || !userPrompt.trim()}
                >
                  {isRunning ? (
                    <>
                      <Loader2 className="h-4 w-4 animate-spin" />
                      {state.step === "generating_key" &&
                        "Generating API Key..."}
                      {state.step === "generating_mod" && "Generating Mod..."}
                      {state.step === "uploading_mod" && "Uploading Mod..."}
                      {state.step === "spinning_up_resources" &&
                        "Spinning Up Resources..."}
                      {state.step === "running_inference" &&
                        "Running Inference..."}
                      {state.step === "fetching_results" &&
                        "Fetching Results..."}
                    </>
                  ) : (
                    <>
                      <Play className="h-4 w-4" />
                      Run Experiment
                    </>
                  )}
                </Button>
                <Button
                  variant="outline"
                  className="py-3 px-4"
                  onClick={() => setShareDialogOpen(true)}
                  disabled={state.step !== "complete" || !state.logData}
                  title={
                    state.step !== "complete"
                      ? "Run an experiment first to share"
                      : "Share this experiment"
                  }
                >
                  <Share2 className="h-4 w-4" />
                </Button>
              </div>

              {/* Progress Indicators */}
              {isRunning && (
                <div className="flex items-center justify-center gap-2 text-xs text-muted-foreground">
                  {enableMod && (
                    <>
                      <div
                        className={cn(
                          "flex items-center gap-1",
                          state.modCode && "text-emerald-500",
                        )}
                      >
                        <span
                          className={cn(
                            "w-2 h-2 rounded-full",
                            state.modCode
                              ? "bg-emerald-500"
                              : state.step === "generating_mod"
                                ? "bg-yellow-500 animate-pulse"
                                : "bg-muted",
                          )}
                        />
                        Generate
                      </div>
                      <span className="text-muted-foreground/50">→</span>
                      <div
                        className={cn(
                          "flex items-center gap-1",
                          (state.step === "running_inference" ||
                            state.step === "fetching_results" ||
                            state.step === "complete") &&
                            "text-emerald-500",
                          (state.step === "uploading_mod" ||
                            state.step === "spinning_up_resources") &&
                            "text-yellow-500",
                        )}
                      >
                        <span
                          className={cn(
                            "w-2 h-2 rounded-full",
                            state.step === "running_inference" ||
                              state.step === "fetching_results" ||
                              state.step === "complete"
                              ? "bg-emerald-500"
                              : state.step === "uploading_mod" ||
                                  state.step === "spinning_up_resources"
                                ? "bg-yellow-500 animate-pulse"
                                : "bg-muted",
                          )}
                        />
                        Upload
                      </div>
                      <span className="text-muted-foreground/50">→</span>
                    </>
                  )}
                  <div
                    className={cn(
                      "flex items-center gap-1",
                      state.inferenceResult && "text-emerald-500",
                    )}
                  >
                    <span
                      className={cn(
                        "w-2 h-2 rounded-full",
                        state.inferenceResult
                          ? "bg-emerald-500"
                          : state.step === "running_inference"
                            ? "bg-yellow-500 animate-pulse"
                            : "bg-muted",
                      )}
                    />
                    Inference
                  </div>
                  <span className="text-muted-foreground/50">→</span>
                  <div
                    className={cn(
                      "flex items-center gap-1",
                      state.step === "complete" && "text-emerald-500",
                    )}
                  >
                    <span
                      className={cn(
                        "w-2 h-2 rounded-full",
                        state.step === "complete"
                          ? "bg-emerald-500"
                          : state.step === "fetching_results"
                            ? "bg-yellow-500 animate-pulse"
                            : "bg-muted",
                      )}
                    />
                    Results
                  </div>
                </div>
              )}

              {/* Error State */}
              {state.step === "error" && (
                <div className="p-3 rounded border border-red-500/50 bg-red-500/10">
                  <div className="flex items-start gap-2">
                    <AlertTriangle className="h-4 w-4 shrink-0 mt-0.5 text-red-500" />
                    <div>
                      <p className="text-sm font-medium text-red-500">Error</p>
                      <p className="text-[11px] mt-1 text-muted-foreground">
                        {state.error}
                      </p>
                    </div>
                  </div>
                </div>
              )}
            </div>

            {/* Generated Code Preview */}
            {state.modCode && (
              <div className="panel">
                <div className="panel-header flex items-center justify-between">
                  <span className="flex items-center gap-2">
                    <Code className="h-3 w-3" />
                    <span className="panel-title">Generated Mod Code</span>
                  </span>
                  <div className="flex items-center gap-1">
                    <button
                      className="p-1 rounded hover:bg-muted transition-colors"
                      onClick={(e) => {
                        e.stopPropagation();
                        navigator.clipboard.writeText(state.modCode || "");
                        setCodeCopied(true);
                        setTimeout(() => setCodeCopied(false), 2000);
                      }}
                      title="Copy code"
                    >
                      {codeCopied ? (
                        <Check className="h-3 w-3 text-emerald-500" />
                      ) : (
                        <Copy className="h-3 w-3" />
                      )}
                    </button>
                    <button
                      className="p-1 rounded hover:bg-muted transition-colors"
                      onClick={() => setShowGeneratedCode(!showGeneratedCode)}
                      title={showGeneratedCode ? "Hide code" : "Show code"}
                    >
                      {showGeneratedCode ? (
                        <EyeOff className="h-3 w-3" />
                      ) : (
                        <Eye className="h-3 w-3" />
                      )}
                    </button>
                  </div>
                </div>
                {showGeneratedCode && (
                  <pre className="p-4 text-[11px] overflow-x-auto max-h-96 overflow-y-auto leading-relaxed whitespace-pre font-mono bg-muted/30">
                    {highlightPython(state.modCode)}
                  </pre>
                )}
              </div>
            )}

            {/* Results - Token Sequence */}
            {state.logData && (
              <div className="panel mt-4">
                <div className="panel-header flex items-center justify-between">
                  <span className="flex items-center gap-2">
                    <Code className="h-3 w-3" />
                    <span className="panel-title">Token Sequence</span>
                  </span>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-6 text-[10px] gap-1 text-muted-foreground hover:text-foreground"
                    asChild
                  >
                    <Link to={`/logs/${state.logData.request_id}`}>
                      See More Details
                      <ExternalLink className="h-3 w-3" />
                    </Link>
                  </Button>
                </div>
                <div className="p-0">
                  <TokensView
                    log={state.logData}
                    selectedStep={null}
                    onSelectStep={() => {}}
                    hideUserPrompt
                    noScrollConstraints
                  />
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Share Dialog */}
      <ShareDialog
        open={shareDialogOpen}
        onOpenChange={setShareDialogOpen}
        config={buildShareableConfig()}
        outputText={
          state.logData?.final_text || state.inferenceResult?.text || ""
        }
        logData={state.logData}
        requestId={state.logData?.request_id || null}
        isPublic={state.logData?.is_public || false}
        publicToken={state.logData?.public_token || null}
        onStatusChange={handleShareStatusChange}
      />
    </div>
  );
}

// Helper functions for history display
function formatRelativeTime(timestamp: string): string {
  const date = new Date(timestamp);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMs / 3600000);
  const diffDays = Math.floor(diffMs / 86400000);

  if (diffMins < 1) return "Just now";
  if (diffMins < 60) return `${diffMins}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  if (diffDays < 7) return `${diffDays}d ago`;
  return date.toLocaleDateString();
}

function getPromptPreview(log: LogResponse): string {
  if (log.user_prompt) {
    return (
      log.user_prompt.slice(0, 50) + (log.user_prompt.length > 50 ? "..." : "")
    );
  }
  return "No prompt";
}

function getResponsePreview(log: LogResponse): string {
  if (log.final_text) {
    return (
      log.final_text.slice(0, 80) + (log.final_text.length > 80 ? "..." : "")
    );
  }
  return "No response";
}

function getModelShortName(modelId: string | null): string {
  if (!modelId) return "Unknown";
  if (modelId.includes("8b") || modelId.includes("8B")) return "8B";
  if (modelId.includes("14b") || modelId.includes("14B")) return "14B";
  if (modelId.includes("70b") || modelId.includes("70B")) return "70B";
  return modelId.split("/").pop()?.slice(0, 10) || "Unknown";
}
