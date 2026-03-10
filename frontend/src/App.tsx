import { useState, useEffect, useCallback } from "react";
import {
  BrowserRouter as Router,
  Routes,
  Route,
  Navigate,
  useLocation,
} from "react-router-dom";
import { AnalyticsProvider } from "@/components/AnalyticsProvider";
import { Key } from "lucide-react";

import { TooltipProvider } from "@/components/ui/tooltip";
import { Button } from "@/components/ui/button";
import LogsList from "@/components/LogsList";
import LogDetail from "@/components/LogDetail";
import PublicCollectionView from "@/components/PublicCollectionView";
import PublicCollectionRequestView from "@/components/PublicCollectionRequestView";
import PublicRequestView from "@/components/PublicRequestView";
import Playground from "@/components/Playground";
import ActivationExplorer from "@/components/ActivationExplorer";
import CollectionsSidebar, {
  type FilterType,
} from "@/components/CollectionsSidebar";
import { AuthProvider, useAuth } from "@/lib/auth";
import { LoginModal } from "@/components/LoginModal";
import SiteHeader from "@/components/SiteHeader";
import SiteFooter from "@/components/SiteFooter";

const FILTER_STORAGE_KEY = "concordance_last_filter";
const SHELL_TONE_STORAGE_KEY = "concordance_shell_tone";
type ShellTone = "paper" | "ink";

function useShellTone() {
  const [shellTone, setShellTone] = useState<ShellTone>(() => {
    if (typeof window === "undefined") return "paper";
    const stored = localStorage.getItem(SHELL_TONE_STORAGE_KEY);
    return stored === "ink" ? "ink" : "paper";
  });

  useEffect(() => {
    if (typeof document === "undefined") return;
    document.body.dataset.shellTone = shellTone;
    return () => {
      delete document.body.dataset.shellTone;
    };
  }, [shellTone]);

  const toggleShellTone = useCallback(() => {
    setShellTone((prev) => {
      const next: ShellTone = prev === "paper" ? "ink" : "paper";
      try {
        localStorage.setItem(SHELL_TONE_STORAGE_KEY, next);
      } catch (error) {
        console.error("Failed to save shell tone:", error);
      }
      return next;
    });
  }, []);

  return { shellTone, toggleShellTone };
}

function AppContent() {
  const location = useLocation();
  const isDetailView = location.pathname.startsWith("/logs/");
  const { isAuthenticated, isLoading, user, logout } = useAuth();
  const { shellTone, toggleShellTone } = useShellTone();

  // Sidebar state - default to hidden on mobile
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [_showSidebar, setShowSidebar] = useState(() => {
    // Check if we're on a larger screen (>= 768px)
    if (typeof window !== "undefined") {
      return window.innerWidth >= 768;
    }
    return true;
  });
  const [isMobile, setIsMobile] = useState(() => {
    if (typeof window !== "undefined") {
      return window.innerWidth < 768;
    }
    return false;
  });

  // Handle window resize for responsive sidebar
  useEffect(() => {
    const handleResize = () => {
      const mobile = window.innerWidth < 768;
      setIsMobile(mobile);
      // Auto-hide sidebar when switching to mobile
      if (mobile && !isDetailView) {
        setShowSidebar(false);
      }
    };

    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, [isDetailView]);

  // Login modal state
  const [showLoginModal, setShowLoginModal] = useState(false);

  // Filter state
  const [activeFilter, setActiveFilter] = useState<FilterType>({ type: "all" });
  const [filterLoaded, setFilterLoaded] = useState(false);

  // Load filter from localStorage on mount
  useEffect(() => {
    try {
      const stored = localStorage.getItem(FILTER_STORAGE_KEY);
      if (stored) {
        const parsed = JSON.parse(stored);
        // Validate the filter structure
        if (parsed && typeof parsed === "object" && parsed.type) {
          setActiveFilter(parsed as FilterType);
        }
      }
    } catch (error) {
      console.error("Failed to load filter from localStorage:", error);
    } finally {
      setFilterLoaded(true);
    }
  }, []);

  // Save filter to localStorage when it changes
  const handleFilterChange = useCallback((filter: FilterType) => {
    setActiveFilter(filter);
    try {
      localStorage.setItem(FILTER_STORAGE_KEY, JSON.stringify(filter));
    } catch (error) {
      console.error("Failed to save filter to localStorage:", error);
    }
  }, []);

  // Handle collection public status change
  const handlePublicStatusChange = useCallback(
    (isPublic: boolean, publicToken: string | null) => {
      if (activeFilter.type === "collection") {
        const updatedFilter: FilterType = {
          ...activeFilter,
          isPublic,
          publicToken,
        };
        setActiveFilter(updatedFilter);
        try {
          localStorage.setItem(
            FILTER_STORAGE_KEY,
            JSON.stringify(updatedFilter),
          );
        } catch (error) {
          console.error("Failed to save filter to localStorage:", error);
        }
      }
    },
    [activeFilter],
  );

  // Hide sidebar on detail views for more space, and on mobile
  useEffect(() => {
    if (isDetailView) {
      setShowSidebar(false);
    } else if (!isMobile) {
      // Only auto-show on non-mobile when leaving detail view
      setShowSidebar(true);
    }
  }, [isDetailView, isMobile]);

  // Get filter label for display
  const getFilterLabel = () => {
    switch (activeFilter.type) {
      case "all":
        return null;
      case "collection":
        return activeFilter.name;
      case "api_key":
        return `API: ${activeFilter.key.slice(0, 8)}...`;
      default:
        return null;
    }
  };

  const filterLabel = getFilterLabel();

  // Show loading state
  if (isLoading) {
    return (
      <div className="h-screen bg-background text-foreground flex items-center justify-center">
        <div className="flex flex-col items-center gap-4">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
          <span className="text-sm text-muted-foreground">Loading...</span>
        </div>
      </div>
    );
  }

  // Show login prompt if not authenticated
  if (!isAuthenticated) {
    return (
      <div
        className={`brand-shell ${shellTone === "ink" ? "brand-shell-ink" : ""} relative min-h-screen flex flex-col`}
      >
        {/* Header */}
        <header className="sticky top-0 z-50 w-full border-b border-white/15 bg-background/70 backdrop-blur-xl">
          <div className="container flex h-10 max-w-5xl items-center">
            {/* Logo */}
            <div className="flex items-center gap-2">
              <img src="/concordance_icon_white.png" alt="Concordance" className="w-5 h-5 object-contain" />
              <span className="font-display text-sm">Concordance</span>
            </div>
          </div>
        </header>

        {/* Login Content */}
        <div className="relative z-[1] flex-1 flex items-center justify-center px-4">
          <div className="w-full max-w-lg rounded-2xl border border-white/20 bg-[rgba(255,255,255,0.1)] p-8 shadow-[0_24px_60px_rgba(8,8,8,0.35)] backdrop-blur-md">
            <div className="text-center mb-8">
              <div className="flex items-center justify-center w-16 h-16 rounded-full border border-white/25 bg-white/10 mx-auto mb-4">
                <Key className="w-8 h-8 text-primary" />
              </div>
              <h1 className="font-display text-[clamp(1.75rem,3.8vw,2.35rem)] leading-[1.05] mb-2">
                Concordance Operator Console
              </h1>
              <p className="text-sm text-muted-foreground">
                Sign in with your inference API key to view your logs and data.
              </p>
            </div>
            <Button
              className="w-full"
              size="lg"
              onClick={() => setShowLoginModal(true)}
            >
              <Key className="mr-2 h-4 w-4" />
              Sign In with API Key
            </Button>
            <p className="text-xs text-center text-muted-foreground mt-4">
              Use the same API key you use for inference requests.
            </p>
          </div>
        </div>

        <SiteFooter />

        <LoginModal open={showLoginModal} onOpenChange={setShowLoginModal} />
      </div>
    );
  }

  return (
    <div
      className={`brand-shell ${shellTone === "ink" ? "brand-shell-ink" : ""} relative min-h-screen flex flex-col`}
    >
      <SiteHeader
        activeRoute="logs"
        user={user}
        onLogout={logout}
        filterLabel={!isDetailView ? filterLabel : null}
        shellTone={shellTone}
        onToggleShellTone={toggleShellTone}
      />

      {/* Main Content with Optional Sidebar (admin only) */}
      <div
        className={`flex-1 flex min-h-0 ${shellTone === "ink" ? "bg-[#130e0f]" : ""}`}
      >
        {/* Collections Sidebar - only for admin users */}
        {user?.isAdmin && !isDetailView && filterLoaded && (
          <CollectionsSidebar
            activeFilter={activeFilter}
            onFilterChange={handleFilterChange}
            collapsed={sidebarCollapsed}
            onToggleCollapsed={() => setSidebarCollapsed(!sidebarCollapsed)}
          />
        )}

        {/* Main Content */}
        <main className="app-main-shell app-main-shell--logs flex-1 flex flex-col min-h-0 overflow-hidden">
          <div className="flex-1 min-h-0">
            <Routes>
              <Route
                path="/"
                element={
                  <LogsList
                    key={`${activeFilter.type}-${activeFilter.type === "collection" ? activeFilter.id : activeFilter.type === "api_key" ? activeFilter.key : "all"}`}
                    collectionId={
                      activeFilter.type === "collection"
                        ? activeFilter.id
                        : undefined
                    }
                    collectionName={
                      activeFilter.type === "collection"
                        ? activeFilter.name
                        : undefined
                    }
                    collectionIsPublic={
                      activeFilter.type === "collection"
                        ? activeFilter.isPublic
                        : undefined
                    }
                    collectionPublicToken={
                      activeFilter.type === "collection"
                        ? activeFilter.publicToken
                        : undefined
                    }
                    apiKey={
                      activeFilter.type === "api_key"
                        ? activeFilter.key
                        : undefined
                    }
                    onPublicStatusChange={handlePublicStatusChange}
                  />
                }
              />
              <Route path="/logs/:requestId" element={<LogDetail />} />
            </Routes>
          </div>
        </main>
      </div>

      <SiteFooter maxWidth="7xl" />

      <LoginModal open={showLoginModal} onOpenChange={setShowLoginModal} />
    </div>
  );
}

function PlaygroundPage() {
  const { user, logout } = useAuth();
  const { shellTone, toggleShellTone } = useShellTone();

  return (
    <div
      className={`brand-shell ${shellTone === "ink" ? "brand-shell-ink" : ""} relative min-h-screen flex flex-col`}
    >
      <SiteHeader
        activeRoute="playground"
        user={user}
        onLogout={logout}
        showActivationsNav
        shellTone={shellTone}
        onToggleShellTone={toggleShellTone}
      />

      {/* Main Content */}
      <main className="app-main-shell app-main-shell--playground flex-1 flex flex-col min-h-0 overflow-hidden">
        <Playground />
      </main>

      <SiteFooter />
    </div>
  );
}

function ActivationExplorerPage() {
  const { user, logout } = useAuth();
  const { shellTone, toggleShellTone } = useShellTone();

  return (
    <div
      className={`brand-shell ${shellTone === "ink" ? "brand-shell-ink" : ""} relative min-h-screen flex flex-col`}
    >
      <SiteHeader
        activeRoute="activations"
        user={user}
        onLogout={logout}
        showActivationsNav
        maxWidth="7xl"
        shellTone={shellTone}
        onToggleShellTone={toggleShellTone}
      />

      <main className="app-main-shell app-main-shell--activations flex-1 py-4 overflow-auto">
        <ActivationExplorer />
      </main>

      <SiteFooter maxWidth="7xl" />
    </div>
  );
}

function App() {
  return (
    <AuthProvider>
      <TooltipProvider>
        <Router>
          <AnalyticsProvider>
            <Routes>
              {/* Public routes - no auth required */}
              <Route path="/playground" element={<PlaygroundPage />} />
              <Route path="/activations" element={<ActivationExplorerPage />} />
              <Route
                path="/playground/activations"
                element={<Navigate to="/activations" replace />}
              />
              <Route
                path="/share/:publicToken"
                element={<PublicCollectionView />}
              />
              <Route
                path="/share/:collectionToken/request/:requestId"
                element={<PublicCollectionRequestView />}
              />
              <Route
                path="/share/request/:publicToken"
                element={<PublicRequestView />}
              />
              {/* All other routes go through AppContent which handles auth */}
              <Route path="/*" element={<AppContent />} />
            </Routes>
          </AnalyticsProvider>
        </Router>
      </TooltipProvider>
    </AuthProvider>
  );
}

export default App;
