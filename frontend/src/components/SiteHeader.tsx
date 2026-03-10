import { useState } from "react";
import type { AuthUser } from "@/lib/auth";
import { cn } from "@/lib/utils";
import { Menu, Moon, Sun, X } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { UserMenu } from "@/components/LoginModal";
import { GitHubStarButton } from "@/components/GitHubStarButton";
import { BrandLockup } from "@/components/design-system/BrandLockup";
import { DsNavLink } from "@/components/design-system/NavLink";

type ShellTone = "paper" | "ink";

type SiteHeaderProps = {
  activeRoute: "logs" | "playground" | "activations";
  user: AuthUser | null;
  onLogout: () => void;
  filterLabel?: string | null;
  showActivationsNav?: boolean;
  maxWidth?: "5xl" | "7xl";
  shellTone?: ShellTone;
  onToggleShellTone?: () => void;
};

export default function SiteHeader({
  activeRoute,
  user,
  onLogout,
  filterLabel,
  showActivationsNav = false,
  maxWidth = "5xl",
  shellTone = "paper",
  onToggleShellTone,
}: SiteHeaderProps) {
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const navTone = "red";

  return (
    <header className="site-header sticky top-0 z-50 border-b border-black/25 py-1">
      <div
        className={cn(
          "mx-auto flex w-full min-h-10 items-center gap-3 px-4 py-2 sm:px-6",
          maxWidth === "7xl" ? "max-w-[1380px]" : "max-w-[1220px]",
        )}
      >
        <BrandLockup
          href="/"
          size="md"
          tone="dark"
          className="mr-2 shrink-0 uppercase"
          labelClassName="font-extrabold uppercase tracking-[0.045em]"
        />

        {/* Desktop nav */}
        <nav className="hidden md:flex min-w-0 flex-1 items-center gap-4 leading-none">
          <DsNavLink
            href="/playground"
            label="Playground"
            tone={navTone}
            active={activeRoute === "playground"}
          />
          {showActivationsNav && (
            <DsNavLink
              href="/activations"
              label="Activations"
              tone={navTone}
              active={activeRoute === "activations"}
            />
          )}
          <DsNavLink
            href="/"
            label="Logs"
            tone={navTone}
            active={activeRoute === "logs"}
          />
          {activeRoute === "logs" && filterLabel && (
            <Badge
              variant="outline"
              className="h-5 whitespace-nowrap px-1.5 font-mono text-2xs font-normal uppercase tracking-[0.07em]"
            >
              {filterLabel}
            </Badge>
          )}
        </nav>

        <div className="hidden shrink-0 items-center gap-3 lg:flex">
          <DsNavLink
            href="https://docs.concordance.co"
            label="Docs ↗"
            tone={navTone}
            external
          />
          <div className="hidden xl:block">
            <GitHubStarButton />
          </div>
        </div>

        <div className="ml-auto flex shrink-0 items-center gap-3">
          <DsNavLink
            href="/api/health"
            label="API ↗"
            tone={navTone}
            external
            className="hidden md:inline-flex"
          />
          {onToggleShellTone && (
            <button
              onClick={onToggleShellTone}
              className="inline-flex h-7 w-7 items-center justify-center rounded-full border border-black/35 bg-white/25 text-[var(--brand-ink)] transition-colors hover:bg-white/35"
              aria-label={shellTone === "ink" ? "Switch to paper mode" : "Switch to ink mode"}
              title={shellTone === "ink" ? "Switch to paper mode" : "Switch to ink mode"}
            >
              {shellTone === "ink" ? (
                <Sun className="h-3.5 w-3.5" />
              ) : (
                <Moon className="h-3.5 w-3.5" />
              )}
            </button>
          )}
          {user && (
            <div className="hidden md:flex">
              <UserMenu
                onLogout={onLogout}
                userName={user.name}
                isAdmin={user.isAdmin}
                tone={shellTone}
              />
            </div>
          )}
          {/* Mobile hamburger */}
          <button
            onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
            className="md:hidden rounded border border-black/25 bg-white/15 p-1.5 text-[var(--brand-ink)] transition-colors hover:bg-white/25"
            aria-label={mobileMenuOpen ? "Close menu" : "Open menu"}
          >
            {mobileMenuOpen ? <X className="h-4 w-4" /> : <Menu className="h-4 w-4" />}
          </button>
        </div>
      </div>

      {/* Mobile menu drawer */}
      {mobileMenuOpen && (
        <div className="md:hidden border-t border-black/15 animate-fade-in">
          <div
            className={cn(
              "mx-auto flex flex-col gap-3 px-4 py-3 sm:px-6",
              maxWidth === "7xl" ? "max-w-[1380px]" : "max-w-[1220px]",
            )}
          >
            <nav className="flex flex-col gap-2">
              <DsNavLink
                href="/playground"
                label="Playground"
                tone={navTone}
                active={activeRoute === "playground"}
                mobile
              />
              {showActivationsNav && (
                <DsNavLink
                  href="/activations"
                  label="Activations"
                  tone={navTone}
                  active={activeRoute === "activations"}
                  mobile
                />
              )}
              <DsNavLink
                href="/"
                label="Logs"
                tone={navTone}
                active={activeRoute === "logs"}
                mobile
              />
              <DsNavLink
                href="https://docs.concordance.co"
                label="Docs ↗"
                tone={navTone}
                external
                mobile
              />
              <DsNavLink
                href="/api/health"
                label="API ↗"
                tone={navTone}
                external
                mobile
              />
            </nav>
            {user && (
              <div className="border-t border-black/15 pt-3">
                <UserMenu
                  onLogout={onLogout}
                  userName={user.name}
                  isAdmin={user.isAdmin}
                  tone={shellTone}
                />
              </div>
            )}
          </div>
        </div>
      )}
    </header>
  );
}
