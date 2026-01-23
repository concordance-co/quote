import { useState, useEffect, useCallback } from "react";

const STORAGE_KEY = "concordance_username";

export function useUsername() {
  const [username, setUsernameState] = useState<string | null>(() => {
    // Initialize from localStorage
    if (typeof window !== "undefined") {
      return localStorage.getItem(STORAGE_KEY);
    }
    return null;
  });

  // Sync with localStorage on mount (in case of SSR)
  useEffect(() => {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored !== username) {
      setUsernameState(stored);
    }
  }, []);

  const setUsername = useCallback((newUsername: string | null) => {
    if (newUsername === null || newUsername.trim() === "") {
      localStorage.removeItem(STORAGE_KEY);
      setUsernameState(null);
    } else {
      const trimmed = newUsername.trim();
      localStorage.setItem(STORAGE_KEY, trimmed);
      setUsernameState(trimmed);
    }
  }, []);

  const clearUsername = useCallback(() => {
    localStorage.removeItem(STORAGE_KEY);
    setUsernameState(null);
  }, []);

  return {
    username,
    setUsername,
    clearUsername,
    isSet: username !== null && username.length > 0,
  };
}
