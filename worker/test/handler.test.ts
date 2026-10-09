import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { type Deps, handle } from "../src/handler";

const fixture = (name: string) => readFileSync(new URL(`../../tests/fixtures/${name}`, import.meta.url), "utf8");
const URL_ = "https://anond.hatelabo.jp/20261008133853";
const ORIGIN = "https://dlwr.github.io";

function deps(overrides: Partial<Deps> = {}): Deps & { aiCalls: number; store: Map<string, unknown> } {
  const store = new Map<string, unknown>();
  const d = {
    aiCalls: 0,
    store,
    ai: {
      run: async (_model: string, input: unknown) => {
        d.aiCalls++;
        const isComment = JSON.stringify(input).includes("ブックマークコメント");
        const probabilities = isComment ? { fiction: 1, fact: 0, none: 0 } : { fiction: 0.25, fact: 0.75 };
        return { answers: { verdict: { type: "choice", probabilities } } };
      },
    },
    perIp: { limit: async () => ({ success: true }) },
    global: { limit: async () => ({ success: true }) },
    fetchText: async (url: string) =>
      url.startsWith("https://b.hatena.ne.jp/entry/jsonlite/")
        ? { status: 200, text: fixture("jsonlite.json") }
        : { status: 200, text: fixture("anond.html") },
    cache: {
      get: async (key: string) => (store.get(key) as never) ?? null,
      put: async (key: string, value: unknown) => void store.set(key, value),
    },
    allowedOrigins: [ORIGIN],
    minMentions: 1,
    ...overrides,
  };
  return d;
}

const request = (query: string, init: RequestInit = {}) =>
  new Request(`https://api.example/api/judge?${query}`, {
    ...init,
    headers: { Origin: ORIGIN, "CF-Connecting-IP": "203.0.113.1", ...(init.headers ?? {}) },
  });

const judge = (d: Deps, url = URL_) => handle(request(`url=${encodeURIComponent(url)}`), d);

describe("handle", () => {
  it("rejects non-anond URLs", async () => {
    expect((await judge(deps(), "https://example.com/1")).status).toBe(400);
  });

  it("returns 404 for unknown paths", async () => {
    expect((await handle(new Request("https://api.example/"), deps())).status).toBe(404);
  });

  it("returns the model verdict", async () => {
    const body = await (await judge(deps())).json();
    expect(body.models.clef).toEqual({ fiction: 0.25, fact: 0.75 });
  });

  it("returns the crowd verdict", async () => {
    const body = await (await judge(deps())).json();
    expect(body.crowd).toEqual({ fiction: 1, fact: 0 });
  });

  it("returns the gap", async () => {
    const body = await (await judge(deps())).json();
    expect(body.gap).toBeCloseTo(0.75);
  });

  it("returns the title from bookmarks", async () => {
    const body = await (await judge(deps())).json();
    expect(body.title).toBe("嫁が出ていった");
  });

  it("returns how many comments were sampled", async () => {
    const body = await (await judge(deps())).json();
    expect(body.comment_count).toBe(2);
  });

  it("serves a cached result without calling the model", async () => {
    const d = deps();
    await judge(d);
    d.aiCalls = 0;
    await judge(d);
    expect(d.aiCalls).toBe(0);
  });

  it("bypasses the cache with fresh=1", async () => {
    const d = deps();
    await judge(d);
    d.aiCalls = 0;
    await handle(request(`url=${encodeURIComponent(URL_)}&fresh=1`), d);
    expect(d.aiCalls).toBeGreaterThan(0);
  });

  it("returns 429 when the per-IP limit is hit", async () => {
    expect((await judge(deps({ perIp: { limit: async () => ({ success: false }) } }))).status).toBe(429);
  });

  it("returns 429 when the global limit is hit", async () => {
    expect((await judge(deps({ global: { limit: async () => ({ success: false }) } }))).status).toBe(429);
  });

  it("returns 404 when the entry is gone", async () => {
    const d = deps({ fetchText: async () => ({ status: 404, text: "" }) });
    expect((await judge(d)).status).toBe(404);
  });

  it("returns 502 when the model fails", async () => {
    const d = deps({ ai: { run: async () => ({ unexpected: true }) } });
    expect((await judge(d)).status).toBe(502);
  });

  it("allows the site origin", async () => {
    expect((await judge(deps())).headers.get("Access-Control-Allow-Origin")).toBe(ORIGIN);
  });

  it("does not allow other origins", async () => {
    const res = await handle(request(`url=${encodeURIComponent(URL_)}`, { headers: { Origin: "https://evil.example" } }), deps());
    expect(res.headers.get("Access-Control-Allow-Origin")).toBeNull();
  });

  it("answers preflight requests", async () => {
    expect((await handle(request("", { method: "OPTIONS" }), deps())).status).toBe(204);
  });
});
