import { commentLabel, summarize, type Verdict } from "./aggregate";
import { extractBody, parseAnondUrl, parseBookmarks } from "./anond";
import { type Ai, decide } from "./clef";
import { BODY_QUESTION, COMMENT_QUESTION, NARRATIVE_QUESTION } from "./questions";

const MAX_COMMENTS = 50;
const BODY_MAX_CHARS = 4000;
const AI_CONCURRENCY = 6;
const JUDGMENT_TTL_SECONDS = 6 * 60 * 60;
const BOOKMARKS_TTL_SECONDS = 60 * 60;

type RateLimit = { limit(options: { key: string }): Promise<{ success: boolean }> };

export type Deps = {
  ai: Ai;
  perIp: RateLimit;
  global: RateLimit;
  bookmarksLimiter: RateLimit;
  fetchText(url: string): Promise<{ status: number; text: string }>;
  cache: { get(key: string): Promise<unknown | null>; put(key: string, value: unknown, ttlSeconds: number): Promise<void> };
  allowedOrigins: string[];
  minMentions?: number;
};

function corsHeaders(request: Request, deps: Deps): Record<string, string> {
  const origin = request.headers.get("Origin");
  if (!origin || !deps.allowedOrigins.includes(origin)) return {};
  return { "Access-Control-Allow-Origin": origin, "Access-Control-Allow-Methods": "GET", Vary: "Origin" };
}

async function mapLimit<T, R>(items: T[], limit: number, fn: (item: T) => Promise<R>): Promise<R[]> {
  const results: R[] = new Array(items.length);
  let next = 0;
  const worker = async () => {
    while (next < items.length) {
      const i = next++;
      results[i] = await fn(items[i]);
    }
  };
  await Promise.all(Array.from({ length: Math.min(limit, items.length) }, worker));
  return results;
}

async function judge(url: string, deps: Deps) {
  const page = await deps.fetchText(url);
  const body = page.status === 200 ? extractBody(page.text) : null;
  if (body === null) return null;

  const bookmarks = await fetchBookmarks(url, deps);
  const { eid, title, count, comments, totalComments } =
    bookmarks.status === 200
      ? parseBookmarks(bookmarks.text, MAX_COMMENTS)
      : { eid: null, title: body.split("\n")[0], count: 0, comments: [], totalComments: 0 };

  const bodyText = `タイトル: ${title}\n\n${body.slice(0, BODY_MAX_CHARS)}`;
  const tasks = [
    () => decide(deps.ai, bodyText, BODY_QUESTION),
    () => decide(deps.ai, bodyText, NARRATIVE_QUESTION),
    ...comments.map(
      (c) => () => decide(deps.ai, `記事タイトル: ${title}\nブックマークコメント: ${c.comment}`, COMMENT_QUESTION),
    ),
  ];
  const [model, narrative, ...commentVerdicts] = await mapLimit(tasks, AI_CONCURRENCY, (t) => t());

  return {
    url,
    eid,
    title,
    bookmark_count: count,
    models: { clef: model as Verdict },
    ...summarize(model as Verdict, commentVerdicts, deps.minMentions),
    narrative: narrative.experience,
    comment_count: comments.length,
    total_comments: totalComments,
    comments: comments.map((c, i) => {
      const label = commentLabel(commentVerdicts[i]);
      return { ...c, label, score: commentVerdicts[i][label] ?? 0 };
    }),
  };
}

function fetchBookmarks(url: string, deps: Deps) {
  return deps.fetchText(`https://b.hatena.ne.jp/entry/jsonlite/?url=${encodeURIComponent(url)}`);
}

export async function handle(request: Request, deps: Deps): Promise<Response> {
  const cors = corsHeaders(request, deps);
  const json = (status: number, data: unknown) =>
    new Response(JSON.stringify(data), { status, headers: { "Content-Type": "application/json", ...cors } });

  if (request.method === "OPTIONS") return new Response(null, { status: 204, headers: cors });

  const { pathname, searchParams } = new URL(request.url);
  if (pathname !== "/api/judge" && pathname !== "/api/bookmarks") return json(404, { error: "not found" });

  const url = parseAnondUrl(searchParams.get("url"));
  if (!url) return json(400, { error: "anond.hatelabo.jp の記事 URL を指定してください" });

  const ip = request.headers.get("CF-Connecting-IP") ?? "unknown";

  if (pathname === "/api/bookmarks") {
    const key = `bookmarks:${url}`;
    const cached = await deps.cache.get(key);
    if (cached) return json(200, cached);
    if (!(await deps.bookmarksLimiter.limit({ key: ip })).success) {
      return json(429, { error: "混み合っています。少し待ってから試してください" });
    }
    const res = await fetchBookmarks(url, deps);
    if (res.status !== 200) return json(502, { error: "ブコメを取得できませんでした" });
    const { eid, comments } = parseBookmarks(res.text, Number.POSITIVE_INFINITY);
    const data = { eid, comments };
    await deps.cache.put(key, data, BOOKMARKS_TTL_SECONDS);
    return json(200, data);
  }

  if (searchParams.get("fresh") !== "1") {
    const cached = await deps.cache.get(url);
    if (cached) return json(200, cached);
  }

  if (!(await deps.perIp.limit({ key: ip })).success || !(await deps.global.limit({ key: "all" })).success) {
    return json(429, { error: "混み合っています。少し待ってから試してください" });
  }

  let result;
  try {
    result = await judge(url, deps);
  } catch (e) {
    console.error(e);
    return json(502, { error: "判定に失敗しました" });
  }
  if (!result) return json(404, { error: "記事が見つかりません" });

  await deps.cache.put(url, result, JUDGMENT_TTL_SECONDS);
  return json(200, result);
}
