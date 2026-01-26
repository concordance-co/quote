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
  matcher: ["/share/request/:path*"],
};

export default async function middleware(request: Request): Promise<Response | undefined> {
  const userAgent = request.headers.get("user-agent");

  // Regular browsers pass through to the SPA
  if (!isCrawler(userAgent)) {
    return undefined;
  }

  // For crawlers, proxy the request to the backend which returns HTML with OG tags
  const url = new URL(request.url);
  const pathname = url.pathname;

  try {
    const backendUrl = new URL(pathname, BACKEND_URL);

    const backendResponse = await fetch(backendUrl.toString(), {
      method: "GET",
      headers: {
        "User-Agent": userAgent || "",
        Accept: "text/html",
        Host: url.host,
      },
    });

    if (!backendResponse.ok) {
      // If backend fails, let request pass through to SPA
      return undefined;
    }

    const html = await backendResponse.text();

    return new Response(html, {
      status: 200,
      headers: {
        "Content-Type": "text/html; charset=utf-8",
        "Cache-Control": "public, max-age=3600, s-maxage=3600",
      },
    });
  } catch (error) {
    console.error("Middleware error proxying to backend:", error);
    // On error, let request pass through to SPA
    return undefined;
  }
}
