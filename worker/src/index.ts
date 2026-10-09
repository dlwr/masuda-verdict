import { handle } from "./handler";

type Env = {
  AI: Ai;
  PER_IP_LIMITER: RateLimit;
  GLOBAL_LIMITER: RateLimit;
  BOOKMARKS_LIMITER: RateLimit;
};

const USER_AGENT = "masuda-verdict (+https://github.com/dlwr/masuda-verdict)";

const cacheKey = (url: string) => new Request(`https://masuda-verdict-cache.internal/${encodeURIComponent(url)}`);

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const cache = caches.default;
    return handle(request, {
      ai: env.AI as unknown as { run(model: string, input: unknown): Promise<unknown> },
      perIp: env.PER_IP_LIMITER,
      global: env.GLOBAL_LIMITER,
      bookmarksLimiter: env.BOOKMARKS_LIMITER,
      fetchText: async (url) => {
        const res = await fetch(url, { headers: { "User-Agent": USER_AGENT } });
        return { status: res.status, text: await res.text() };
      },
      cache: {
        get: async (url) => (await cache.match(cacheKey(url)))?.json() ?? null,
        put: async (url, value, ttlSeconds) =>
          ctx.waitUntil(
            cache.put(
              cacheKey(url),
              new Response(JSON.stringify(value), {
                headers: { "Content-Type": "application/json", "Cache-Control": `max-age=${ttlSeconds}` },
              }),
            ),
          ),
      },
      allowedOrigins: ["https://dlwr.github.io", "http://localhost:4321"],
    });
  },
};
