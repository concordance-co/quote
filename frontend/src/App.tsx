import { useState, useEffect, useCallback } from "react";
import {
  BrowserRouter as Router,
  Routes,
  Route,
  Link,
  useLocation,
} from "react-router-dom";
import { ExternalLink, Key, Sparkles, Star } from "lucide-react";

import { TooltipProvider } from "@/components/ui/tooltip";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import LogsList from "@/components/LogsList";
import LogDetail from "@/components/LogDetail";
import PublicCollectionView from "@/components/PublicCollectionView";
import PublicCollectionRequestView from "@/components/PublicCollectionRequestView";
import PublicRequestView from "@/components/PublicRequestView";
import Playground from "@/components/Playground";
import CollectionsSidebar, {
  type FilterType,
} from "@/components/CollectionsSidebar";
import { AuthProvider, useAuth } from "@/lib/auth";
import { LoginModal, UserMenu } from "@/components/LoginModal";

const FILTER_STORAGE_KEY = "concordance_last_filter";

function AppContent() {
  const location = useLocation();
  const isDetailView = location.pathname.startsWith("/logs/");
  const { isAuthenticated, isLoading, user, logout } = useAuth();

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
      <div className="h-screen bg-background text-foreground flex flex-col">
        {/* Header */}
        <header className="sticky top-0 z-50 w-full border-b border-border bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/80">
          <div className="container flex h-10 max-w-5xl items-center">
            {/* Logo */}
            <div className="flex items-center gap-2">
              <img
                src="/elvis-logo.png"
                alt="Concordance"
                className="w-6 h-6 object-contain"
              />
              <span className="font-semibold text-sm">Concordance</span>
            </div>
          </div>
        </header>

        {/* Login Content */}
        <div className="flex-1 flex items-center justify-center">
          <div className="max-w-md w-full mx-4">
            <div className="text-center mb-8">
              <div className="flex items-center justify-center w-16 h-16 rounded-full bg-primary/10 mx-auto mb-4">
                <Key className="w-8 h-8 text-primary" />
              </div>
              <h1 className="text-2xl font-bold mb-2">
                Welcome to Concordance
              </h1>
              <p className="text-muted-foreground">
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

        {/* Footer */}
        <footer className="border-t border-border shrink-0">
          <div className="container flex items-center justify-between h-7 max-w-5xl text-2xs text-muted-foreground">
            <span>Concordance v1.0</span>
          </div>
        </footer>

        <LoginModal open={showLoginModal} onOpenChange={setShowLoginModal} />
      </div>
    );
  }

  return (
    <div className="h-screen bg-background text-foreground flex flex-col overflow-hidden">
      {/* Compact Header */}
      <header className="sticky top-0 z-50 w-full border-b border-border bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/80">
        <div className="container flex flex-wrap gap-2 py-2 max-w-5xl items-center min-h-10">
          {/* Logo */}
          <Link to="/" className="flex items-center gap-2 mr-2 shrink-0">
            <img
              src="/elvis-logo.png"
              alt="Concordance"
              className="w-6 h-6 object-contain"
            />
            <span className="font-semibold text-sm whitespace-nowrap">
              Concordance
            </span>
          </Link>

          {/* Navigation - Playground first, Logs second */}
          <nav className="flex items-center gap-1 flex-1 min-w-0">
            <Button
              variant={
                location.pathname === "/playground" ? "secondary" : "ghost"
              }
              size="sm"
              className="h-7 text-xs px-2 shrink-0 gap-1"
              asChild
            >
              <Link to="/playground">
                <Sparkles className="h-3 w-3" />
                Playground
              </Link>
            </Button>
            <Button
              variant={
                !isDetailView && location.pathname !== "/playground"
                  ? "secondary"
                  : "ghost"
              }
              size="sm"
              className="h-7 text-xs px-2 shrink-0"
              asChild
            >
              <Link to="/">Logs</Link>
            </Button>
            {filterLabel && !isDetailView && (
              <Badge
                variant="outline"
                className="h-5 text-2xs px-1.5 font-normal whitespace-nowrap"
              >
                {filterLabel}
              </Badge>
            )}
          </nav>

          {/* External Links */}
          <div className="flex items-center gap-1 shrink-0">
            <Button
              variant="ghost"
              size="sm"
              className="h-7 text-xs px-2"
              asChild
            >
              <a
                href="https://docs.concordance.co"
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-1"
              >
                Docs
                <ExternalLink className="h-3 w-3" />
              </a>
            </Button>
            <Button
              variant="ghost"
              size="sm"
              className="h-7 text-xs px-2"
              asChild
            >
              <a
                href="https://github.com/concordance-co/quote"
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-1"
              >
                <Star className="h-3 w-3" />
                GitHub
              </a>
            </Button>
          </div>

          {/* API & User Menu */}
          <div className="flex items-center gap-2 shrink-0">
            <Button
              variant="ghost"
              size="sm"
              className="h-7 text-xs px-2"
              asChild
            >
              <a
                href="/api/health"
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-1"
              >
                API
                <ExternalLink className="h-3 w-3" />
              </a>
            </Button>
            {user && (
              <UserMenu
                onLogout={logout}
                userName={user.name}
                isAdmin={user.isAdmin}
              />
            )}
          </div>
        </div>
      </header>

      {/* Main Content with Optional Sidebar (admin only) */}
      <div className="flex-1 flex min-h-0">
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
        <main className="flex-1 container max-w-7xl py-3 flex flex-col min-h-0 overflow-hidden">
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

      {/* Compact Footer */}
      <footer className="border-t border-border shrink-0">
        <div className="container flex items-center justify-between h-7 max-w-7xl text-2xs text-muted-foreground">
          <span>Concordance v1.0</span>
        </div>
      </footer>

      <LoginModal open={showLoginModal} onOpenChange={setShowLoginModal} />
    </div>
  );
}

function PlaygroundPage() {
  const { user, logout } = useAuth();

  return (
    <div className="h-screen bg-background text-foreground flex flex-col overflow-hidden">
      {/* Header */}
      <header className="sticky top-0 z-50 w-full border-b border-border bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/80">
        <div className="container flex flex-wrap gap-2 py-2 max-w-5xl items-center min-h-10">
          {/* Logo */}
          <Link to="/" className="flex items-center gap-2 mr-2 shrink-0">
            <img
              src="/elvis-logo.png"
              alt="Concordance"
              className="w-6 h-6 object-contain"
            />
            <span className="font-semibold text-sm whitespace-nowrap">
              Concordance
            </span>
          </Link>

          {/* Navigation - Playground first, Logs second */}
          <nav className="flex items-center gap-1 flex-1 min-w-0">
            <Button
              variant="secondary"
              size="sm"
              className="h-7 text-xs px-2 shrink-0 gap-1"
              asChild
            >
              <Link to="/playground">
                <Sparkles className="h-3 w-3" />
                Playground
              </Link>
            </Button>
            <Button
              variant="ghost"
              size="sm"
              className="h-7 text-xs px-2 shrink-0"
              asChild
            >
              <Link to="/">Logs</Link>
            </Button>
          </nav>

          {/* External Links */}
          <div className="flex items-center gap-1 shrink-0">
            <Button
              variant="ghost"
              size="sm"
              className="h-7 text-xs px-2"
              asChild
            >
              <a
                href="https://docs.concordance.co"
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-1"
              >
                Docs
                <ExternalLink className="h-3 w-3" />
              </a>
            </Button>
            <Button
              variant="ghost"
              size="sm"
              className="h-7 text-xs px-2"
              asChild
            >
              <a
                href="https://github.com/concordance-co/quote"
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-1"
              >
                <Star className="h-3 w-3" />
                GitHub
              </a>
            </Button>
          </div>

          {/* API & User Menu */}
          <div className="flex items-center gap-2 shrink-0">
            <Button
              variant="ghost"
              size="sm"
              className="h-7 text-xs px-2"
              asChild
            >
              <a
                href="/api/health"
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-1"
              >
                API
                <ExternalLink className="h-3 w-3" />
              </a>
            </Button>
            {user && (
              <UserMenu
                onLogout={logout}
                userName={user.name}
                isAdmin={user.isAdmin}
              />
            )}
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="flex-1 py-4 flex flex-col min-h-0 overflow-hidden">
        <Playground />
      </main>

      {/* Footer */}
      <footer className="border-t border-border shrink-0">
        <div className="container flex items-center justify-between h-7 max-w-5xl text-2xs text-muted-foreground">
          <span>Concordance v1.0</span>
        </div>
      </footer>
    </div>
  );
}

function App() {
  return (
    <AuthProvider>
      <TooltipProvider>
        <Router>
          <Routes>
            {/* Public routes - no auth required */}
            <Route path="/playground" element={<PlaygroundPage />} />
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
        </Router>
      </TooltipProvider>
    </AuthProvider>
  );
}

export default App;
