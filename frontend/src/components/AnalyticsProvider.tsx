import { useAnalytics } from "@/hooks/useAnalytics";

/**
 * AnalyticsProvider component that initializes session and page tracking.
 * Must be placed inside a Router context since it uses useLocation.
 *
 * This component:
 * - Tracks session start/end with duration
 * - Tracks page views on route changes
 * - Tracks time spent on each page
 */
export function AnalyticsProvider({ children }: { children: React.ReactNode }) {
  // Initialize analytics tracking
  // The hook handles session start, page views, and session end automatically
  useAnalytics();

  return <>{children}</>;
}

export default AnalyticsProvider;
