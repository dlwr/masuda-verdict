const ANOND_URL = /^https?:\/\/anond\.hatelabo\.jp\/(\d{14})$/;

export function parseAnondUrl(input: string | null): string | null {
  const id = input?.match(ANOND_URL)?.[1];
  return id ? `https://anond.hatelabo.jp/${id}` : null;
}

const NAMED_ENTITIES: Record<string, string> = { amp: "&", lt: "<", gt: ">", quot: '"', apos: "'" };

function decodeEntities(s: string): string {
  return s.replace(/&(#x[0-9a-f]+|#\d+|[a-z]+);/gi, (whole, ref: string) => {
    if (ref[0] === "#") {
      const code = ref[1] === "x" || ref[1] === "X" ? parseInt(ref.slice(2), 16) : parseInt(ref.slice(1), 10);
      return String.fromCodePoint(code);
    }
    return NAMED_ENTITIES[ref.toLowerCase()] ?? whole;
  });
}

export function extractBody(html: string): string | null {
  const content = html.match(/<meta\s+itemprop="text"\s+content="([^"]*)"/)?.[1];
  return content === undefined ? null : decodeEntities(content);
}

type Jsonlite = { eid: string; title: string; count: number; bookmarks: { user: string; comment: string }[] };

export type BookmarkComment = { user: string; comment: string };

export function parseBookmarks(raw: string, limit: number) {
  const data: Jsonlite = JSON.parse(raw);
  const all: BookmarkComment[] = data.bookmarks
    .filter((b) => b.comment)
    .map((b) => ({ user: b.user, comment: b.comment }));
  return {
    eid: data.eid,
    title: data.title,
    count: data.count,
    comments: all.slice(0, limit),
    totalComments: all.length,
  };
}
