// Crawler user agents that need OG meta tags
const CRAWLER_USER_AGENTS = [
  "twitterbot",
  "slackbot",
  "facebookexternalhit",
  "linkedinbot",
  "discordbot",
  "telegrambot",
  "whatsapp",
  "googlebot",
  "bingbot",
  "applebot",
  "pinterest",
  "redditbot",
  "embedly",
  "quora link preview",
  "outbrain",
  "rogerbot",
  "showyoubot",
  "vkshare",
  "tumblr",
  "skypeuripreview",
  "nuzzel",
  "w3c_validator",
];

function isCrawler(userAgent: string | null): boolean {
  if (!userAgent) return false;
  const ua = userAgent.toLowerCase();
  return CRAWLER_USER_AGENTS.some((crawler) => ua.includes(crawler));
}

// Backend URL for API requests
const BACKEND_URL =
  process.env.BACKEND_URL ||
  "https://concordance--thunder-backend-thunder-server.modal.run";

export const config = {
  matcher: [
    // Match share routes that need OG metadata
    "/share/request/:path*",
  ],
};

export default async function middleware(request: Request) {
  const userAgent = request.headers.get("user-agent");
  const url = new URL(request.url);
  const pathname = url.pathname;

  // Only intercept for crawlers
  if (!isCrawler(userAgent)) {
    // Let the request through to the SPA
    return;
  }

  // For crawlers, proxy the request to the backend which returns HTML with OG tags
  try {
    const backendUrl = new URL(pathname, BACKEND_URL);

    // Forward the request to the backend
    const backendResponse = await fetch(backendUrl.toString(), {
      method: "GET",
      headers: {
        "User-Agent": userAgent || "",
        Accept: "text/html",
      },
    });

    // If backend returns an error, let it fall through to the SPA
    if (!backendResponse.ok) {
      return;
    }

    // Return the backend response (HTML with OG tags)
    const html = await backendResponse.text();

    return new Response(html, {
      status: 200,
      headers: {
        "Content-Type": "text/html; charset=utf-8",
        "Cache-Control": "public, max-age=3600",
      },
    });
  } catch (error) {
    // On error, fall through to the SPA
    console.error("Middleware error:", error);
    return;
  }
}
