import { useState, useEffect } from "react";
import { Star } from "lucide-react";
import { Button } from "@/components/ui/button";

const GITHUB_REPO = "concordance-co/quote";
const GITHUB_URL = `https://github.com/${GITHUB_REPO}`;

export function GitHubStarButton() {
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
    <Button
      variant="ghost"
      size="sm"
      className="h-7 text-xs px-2 gap-1.5"
      asChild
    >
      <a
        href={GITHUB_URL}
        target="_blank"
        rel="noopener noreferrer"
        className="flex items-center"
      >
        <Star className="h-3.5 w-3.5" />
        <span>Star on GitHub</span>
        {!isLoading && starCount !== null && (
          <span className="ml-0.5 px-1.5 py-0.5 rounded bg-muted text-muted-foreground text-2xs font-medium">
            {formatCount(starCount)}
          </span>
        )}
      </a>
    </Button>
  );
}

export default GitHubStarButton;
