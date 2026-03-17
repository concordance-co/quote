import { useState, useEffect } from "react";
import { Star } from "lucide-react";
import { cn } from "@/lib/utils";

const GITHUB_REPO = "concordance-co/quote";
const GITHUB_URL = `https://github.com/${GITHUB_REPO}`;

type GitHubStarButtonProps = {
  className?: string;
  countClassName?: string;
  tone?: "paper" | "ink";
};

export function GitHubStarButton({
  className,
  countClassName,
  tone = "paper",
}: GitHubStarButtonProps = {}) {
  const [starCount, setStarCount] = useState<number | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const fetchStarCount = async () => {
      try {
        // Check for cached data
        const cached = sessionStorage.getItem("github_star_count");
        const cachedTime = sessionStorage.getItem("github_star_count_time");
        const now = Date.now();

        // Use cache if less than 5 minutes old
        if (
          cached &&
          cachedTime &&
          now - parseInt(cachedTime) < 5 * 60 * 1000
        ) {
          setStarCount(parseInt(cached));
          setIsLoading(false);
          return;
        }

        const response = await fetch(
          `https://api.github.com/repos/${GITHUB_REPO}`,
          {
            headers: {
              Accept: "application/vnd.github.v3+json",
            },
          },
        );

        if (response.ok) {
          const data = await response.json();
          const count = data.stargazers_count;
          setStarCount(count);

          // Cache the result
          sessionStorage.setItem("github_star_count", count.toString());
          sessionStorage.setItem("github_star_count_time", now.toString());
        }
      } catch (error) {
        console.error("Failed to fetch GitHub star count:", error);
      } finally {
        setIsLoading(false);
      }
    };

    fetchStarCount();
  }, []);

  const formatCount = (count: number): string => {
    if (count >= 1000) {
      return `${(count / 1000).toFixed(1).replace(/\.0$/, "")}k`;
    }
    return count.toString();
  };

  return (
    <a
      href={GITHUB_URL}
      target="_blank"
      rel="noopener noreferrer"
      className={cn(
        "inline-flex h-7 items-center gap-1.5 px-0 font-mono text-xs uppercase tracking-[0.08em] transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-offset-transparent rounded-xs",
        tone === "ink"
          ? "text-white/85 hover:text-white focus-visible:ring-white/80"
          : "text-[var(--brand-ink)] hover:text-white focus-visible:ring-[var(--brand-ink)]",
        className,
      )}
    >
      <Star className="h-3.5 w-3.5" />
      <span>Star on GitHub</span>
      {!isLoading && starCount !== null && (
        <span
          className={cn(
            "ml-0.5 text-2xs font-medium",
            tone === "ink" ? "text-white/70" : "text-[var(--brand-ink)]/78",
            countClassName,
          )}
        >
          {formatCount(starCount)}
        </span>
      )}
    </a>
  );
}

export default GitHubStarButton;
