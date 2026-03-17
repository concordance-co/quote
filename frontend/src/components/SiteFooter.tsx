import { cn } from "@/lib/utils";

type SiteFooterProps = {
  maxWidth?: "5xl" | "7xl";
};

export default function SiteFooter({ maxWidth = "5xl" }: SiteFooterProps) {
  return (
    <footer className="site-footer shrink-0">
      <div
        className={cn(
          "mx-auto flex w-full items-center justify-between gap-3 px-4 py-2 sm:px-6",
          maxWidth === "7xl" ? "max-w-[1380px]" : "max-w-[1220px]",
        )}
      >
        <span className="site-footer-text">© 2026 Concordance Holdings Inc</span>
        <div className="flex items-center gap-3">
          <a
            href="https://www.concordance.co/privacy"
            target="_blank"
            rel="noopener noreferrer"
            className="site-footer-link"
          >
            Privacy Policy
          </a>
        </div>
      </div>
    </footer>
  );
}
