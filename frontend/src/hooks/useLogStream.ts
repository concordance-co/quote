import { useState, useEffect, useCallback, useRef } from "react";
import type { LogSummary } from "@/types/api";

// Debug flag - set to false for production
const DEBUG = import.meta.env.DEV;

// WebSocket URL - must connect directly to backend since proxies don't support WS
// Set VITE_WS_URL environment variable to your backend WebSocket endpoint
// For local development: VITE_WS_URL=ws://localhost:6767
// For production: VITE_WS_URL=wss://your-backend-server.example.com
const WS_BASE_URL = import.meta.env.VITE_WS_URL || "ws://localhost:6767";
const MAX_RECONNECT_ATTEMPTS = 6;

export interface UseLogStreamOptions {
  /** Whether the stream is enabled. Default: true */
  enabled?: boolean;
  /** API key for authentication (required for the stream to work) */
  apiKey?: string | null;
  /** Callback when a new log is received */
  onNewLog?: (log: LogSummary) => void;
  /** Callback when the connection status changes */
  onConnectionChange?: (connected: boolean) => void;
  /** Callback when messages were missed due to lag */
  onLagged?: (missedCount: number) => void;
}

export interface UseLogStreamResult {
  /** Whether the WebSocket connection is currently active */
  isConnected: boolean;
  /** The most recent error, if any */
  error: string | null;
  /** Manually reconnect to the stream */
  reconnect: () => void;
  /** Disconnect from the stream */
  disconnect: () => void;
}

/**
 * Hook for subscribing to real-time log updates via WebSocket.
 *
 * When a new log is ingested on the backend, it will be pushed to all
 * connected clients via this stream.
 */
export function useLogStream(
  options: UseLogStreamOptions = {},
): UseLogStreamResult {
  const {
    enabled = true,
    apiKey,
    onNewLog,
    onConnectionChange,
    onLagged,
  } = options;

  const [isConnected, setIsConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(
    null,
  );
  const reconnectAttempts = useRef(0);
  const enabledRef = useRef(enabled);
  const apiKeyRef = useRef(apiKey);

  // Store callbacks in refs to avoid re-creating the connection when they change
  const onNewLogRef = useRef(onNewLog);
  const onConnectionChangeRef = useRef(onConnectionChange);
  const onLaggedRef = useRef(onLagged);

  useEffect(() => {
    onNewLogRef.current = onNewLog;
    onConnectionChangeRef.current = onConnectionChange;
    onLaggedRef.current = onLagged;
    enabledRef.current = enabled;
    apiKeyRef.current = apiKey;
  }, [onNewLog, onConnectionChange, onLagged, enabled, apiKey]);

  const connect = useCallback(() => {
    // Clean up any existing connection
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }

    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }

    try {
      // Require API key for authentication
      const currentApiKey = apiKeyRef.current;
      if (!currentApiKey) {
        if (DEBUG)
          console.log("[WS] No API key available, skipping connection");
        setError("Authentication required for log stream");
        return;
      }

      // Connect directly to backend WebSocket URL (proxies don't support WS)
      // Include API key as query parameter for authentication
      const wsUrl = `${WS_BASE_URL}/logs/stream?api_key=${encodeURIComponent(currentApiKey)}`;

      if (DEBUG)
        console.log("[WS] Connecting to:", wsUrl.replace(currentApiKey, "***"));
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        if (DEBUG) console.log("[WS] Connected to log stream");
        setIsConnected(true);
        setError(null);
        reconnectAttempts.current = 0;
        onConnectionChangeRef.current?.(true);
      };

      ws.onclose = (event) => {
        if (DEBUG)
          console.log("[WS] Connection closed:", event.code, event.reason);
        setIsConnected(false);
        onConnectionChangeRef.current?.(false);
        wsRef.current = null;

        // Reconnect if not a clean close and still enabled
        if (event.code !== 1000 && enabledRef.current) {
          if (reconnectAttempts.current >= MAX_RECONNECT_ATTEMPTS) {
            setError("Log stream unavailable after multiple retries");
            if (DEBUG) {
              console.warn(
                `[WS] Reconnect limit reached (${MAX_RECONNECT_ATTEMPTS}), giving up`,
              );
            }
            return;
          }

          // Exponential backoff: 1s, 2s, 4s, 8s, max 30s
          const delay = Math.min(
            1000 * Math.pow(2, reconnectAttempts.current),
            30000,
          );
          reconnectAttempts.current++;

          if (DEBUG) {
            console.log(
              `[WS] Will reconnect in ${delay}ms (attempt ${reconnectAttempts.current})`,
            );
          }
          reconnectTimeoutRef.current = setTimeout(() => {
            if (enabledRef.current) {
              connect();
            }
          }, delay);
        }
      };

      ws.onerror = (event) => {
        if (DEBUG) console.error("[WS] Connection error:", event);
        setError("Connection error");
      };

      ws.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data);

          if (message.type === "new_log") {
            const data = message.data;
            // Transform the event to match LogSummary type
            const log: LogSummary = {
              request_id: data.request_id,
              created_ts: data.created_ts,
              finished_ts: data.finished_ts,
              model_id: data.model_id,
              user_api_key: data.user_api_key,
              final_text: data.final_text,
              total_steps: data.total_steps,
              favorited_by: data.favorited_by || [],
              discussion_count: data.discussion_count || 0,
            };
            if (DEBUG) console.log("[WS] Received new log:", log.request_id);
            onNewLogRef.current?.(log);
          } else if (message.type === "lagged") {
            const missed = message.missed || 0;
            if (DEBUG) console.warn(`[WS] Lagged, missed ${missed} events`);
            onLaggedRef.current?.(missed);
          }
        } catch {
          // Silently ignore parse errors in production
        }
      };
    } catch (err) {
      if (DEBUG) console.error("[WS] Failed to create WebSocket:", err);
      setError(err instanceof Error ? err.message : "Failed to connect");
      setIsConnected(false);
    }
  }, []);

  const disconnect = useCallback(() => {
    if (wsRef.current) {
      wsRef.current.close(1000, "Client disconnect");
      wsRef.current = null;
    }
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }
    setIsConnected(false);
    onConnectionChangeRef.current?.(false);
  }, []);

  const reconnect = useCallback(() => {
    reconnectAttempts.current = 0;
    connect();
  }, [connect]);

  // Connect when enabled and API key is available, disconnect when disabled
  useEffect(() => {
    if (enabled && apiKey) {
      connect();
    } else {
      disconnect();
    }

    return () => {
      disconnect();
    };
  }, [enabled, apiKey, connect, disconnect]);

  return {
    isConnected,
    error,
    reconnect,
    disconnect,
  };
}
