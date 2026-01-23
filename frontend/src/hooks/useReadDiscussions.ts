import { useState, useEffect, useCallback } from "react";

const STORAGE_KEY = "concordance:read-discussions";

interface ReadDiscussionState {
  [requestId: string]: number; // Stores the discussion count that was read
}

export function useReadDiscussions() {
  const [readCounts, setReadCountsState] = useState<ReadDiscussionState>(() => {
    // Initialize from localStorage
    if (typeof window !== "undefined") {
      const stored = localStorage.getItem(STORAGE_KEY);
      if (stored) {
        try {
          return JSON.parse(stored);
        } catch {
          return {};
        }
      }
    }
    return {};
  });

  // Sync with localStorage on mount (in case of SSR)
  useEffect(() => {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored) {
      try {
        const parsed = JSON.parse(stored);
        setReadCountsState(parsed);
      } catch {
        // Invalid JSON, ignore
      }
    }
  }, []);

  // Mark discussions as read for a request (stores the current count)
  const markAsRead = useCallback((requestId: string, count: number) => {
    setReadCountsState((prev) => {
      const next = { ...prev, [requestId]: count };
      localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
      return next;
    });
  }, []);

  // Get the number of unread discussions for a request
  const getUnreadCount = useCallback(
    (requestId: string, currentCount: number): number => {
      const lastReadCount = readCounts[requestId] ?? 0;
      return Math.max(0, currentCount - lastReadCount);
    },
    [readCounts],
  );

  // Check if there are unread discussions for a request
  const hasUnread = useCallback(
    (requestId: string, currentCount: number): boolean => {
      return getUnreadCount(requestId, currentCount) > 0;
    },
    [getUnreadCount],
  );

  // Get the last read count for a request
  const getLastReadCount = useCallback(
    (requestId: string): number => {
      return readCounts[requestId] ?? 0;
    },
    [readCounts],
  );

  // Mark all discussions as read
  const markAllAsRead = useCallback(
    (requests: Array<{ requestId: string; discussionCount: number }>) => {
      setReadCountsState((prev) => {
        const next = { ...prev };
        requests.forEach(({ requestId, discussionCount }) => {
          next[requestId] = discussionCount;
        });
        localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
        return next;
      });
    },
    [],
  );

  // Clear all read state
  const clearAll = useCallback(() => {
    localStorage.removeItem(STORAGE_KEY);
    setReadCountsState({});
  }, []);

  return {
    readCounts,
    markAsRead,
    getUnreadCount,
    hasUnread,
    getLastReadCount,
    markAllAsRead,
    clearAll,
  };
}
