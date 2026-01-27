import { useEffect, useRef, useCallback } from "react";
import { useLocation } from "react-router-dom";
import { track } from "@vercel/analytics";

// Session start timestamp
const sessionStartTime = Date.now();

// Track if we've already sent the session end event
let sessionEndSent = false;

/**
 * Get the current session duration in seconds
 */
function getSessionDuration(): number {
  return Math.round((Date.now() - sessionStartTime) / 1000);
}

/**
 * Categorize a route into a page type for analytics
 * Keeps it simple to stay within property limits
 */
function getPageType(pathname: string): string {
  if (pathname === "/" || pathname === "") return "home";
  if (pathname.startsWith("/logs/")) return "log_detail";
  if (pathname === "/playground") return "playground";
  if (pathname.startsWith("/share/")) return "shared_view";
  if (pathname.startsWith("/collections/")) return "collection";
  return "other";
}

/**
 * Track session end with duration
 * Uses both beforeunload and visibilitychange for reliability
 */
function trackSessionEnd() {
  if (sessionEndSent) return;

  const duration = getSessionDuration();
  // Only track sessions longer than 5 seconds to filter out bounces
  if (duration > 5) {
    sessionEndSent = true;
    // Max 2 properties per event
    track("session_end", {
      duration_seconds: duration,
      duration_bucket: getDurationBucket(duration),
    });
  }
}

/**
 * Get a human-readable duration bucket for easier analysis
 */
function getDurationBucket(seconds: number): string {
  if (seconds < 30) return "0-30s";
  if (seconds < 60) return "30s-1m";
  if (seconds < 300) return "1-5m";
  if (seconds < 600) return "5-10m";
  if (seconds < 1800) return "10-30m";
  return "30m+";
}

/**
 * Hook to track analytics events including session time
 *
 * Usage:
 * ```
 * const { trackEvent } = useAnalytics();
 * trackEvent("button_click", { button: "signup" });
 * ```
 */
export function useAnalytics() {
  const location = useLocation();
  const lastPathRef = useRef<string>("");
  const pageViewStartRef = useRef<number>(Date.now());

  // Set up session tracking on mount (once per app)
  useEffect(() => {
    // Track session start
    track("session_start", {
      referrer: document.referrer || "direct",
      page_type: getPageType(window.location.pathname),
    });

    // Handle page unload
    const handleBeforeUnload = () => {
      trackSessionEnd();
    };

    // Handle tab visibility change (more reliable on mobile)
    const handleVisibilityChange = () => {
      if (document.visibilityState === "hidden") {
        trackSessionEnd();
      }
    };

    // Handle page hide (most reliable for mobile browsers)
    const handlePageHide = () => {
      trackSessionEnd();
    };

    window.addEventListener("beforeunload", handleBeforeUnload);
    document.addEventListener("visibilitychange", handleVisibilityChange);
    window.addEventListener("pagehide", handlePageHide);

    return () => {
      window.removeEventListener("beforeunload", handleBeforeUnload);
      document.removeEventListener("visibilitychange", handleVisibilityChange);
      window.removeEventListener("pagehide", handlePageHide);
    };
  }, []);

  // Track page views on route change
  useEffect(() => {
    const currentPath = location.pathname;

    // Skip if same path (prevents double tracking)
    if (currentPath === lastPathRef.current) return;

    // Track time spent on previous page (if there was one)
    if (lastPathRef.current) {
      const timeOnPage = Math.round((Date.now() - pageViewStartRef.current) / 1000);
      if (timeOnPage > 2) {
        // Max 2 properties
        track("page_exit", {
          page_type: getPageType(lastPathRef.current),
          time_seconds: Math.min(timeOnPage, 9999), // Cap for analytics
        });
      }
    }

    // Track new page view
    track("page_view", {
      page_type: getPageType(currentPath),
      session_time: getSessionDuration(),
    });

    lastPathRef.current = currentPath;
    pageViewStartRef.current = Date.now();
  }, [location.pathname]);

  /**
   * Track a custom event with up to 2 properties
   */
  const trackEvent = useCallback(
    (
      eventName: string,
      properties?: Record<string, string | number | boolean | null>
    ) => {
      // Ensure we only send max 2 properties
      if (properties) {
        const keys = Object.keys(properties);
        if (keys.length > 2) {
          console.warn(
            `[Analytics] Event "${eventName}" has ${keys.length} properties, but max 2 are allowed. Truncating.`
          );
          const truncated: Record<string, string | number | boolean | null> = {};
          truncated[keys[0]] = properties[keys[0]];
          truncated[keys[1]] = properties[keys[1]];
          track(eventName, truncated);
          return;
        }
      }
      track(eventName, properties);
    },
    []
  );

  return { trackEvent, getSessionDuration };
}

/**
 * Standalone function to track events outside of React components
 * Useful for tracking in API calls, utilities, etc.
 */
export function trackAnalyticsEvent(
  eventName: string,
  properties?: Record<string, string | number | boolean | null>
) {
  if (properties) {
    const keys = Object.keys(properties);
    if (keys.length > 2) {
      console.warn(
        `[Analytics] Event "${eventName}" has ${keys.length} properties, but max 2 are allowed. Truncating.`
      );
      const truncated: Record<string, string | number | boolean | null> = {};
      truncated[keys[0]] = properties[keys[0]];
      truncated[keys[1]] = properties[keys[1]];
      track(eventName, truncated);
      return;
    }
  }
  track(eventName, properties);
}

export default useAnalytics;
