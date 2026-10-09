import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { extractBody, parseAnondUrl, parseBookmarks } from "../src/anond";

const fixture = (name: string) => readFileSync(new URL(`../../tests/fixtures/${name}`, import.meta.url), "utf8");

describe("parseAnondUrl", () => {
  it("normalizes an https entry URL", () => {
    expect(parseAnondUrl("https://anond.hatelabo.jp/20261008133853")).toBe("https://anond.hatelabo.jp/20261008133853");
  });

  it("accepts http", () => {
    expect(parseAnondUrl("http://anond.hatelabo.jp/20261008133853")).toBe("https://anond.hatelabo.jp/20261008133853");
  });

  it("rejects other hosts", () => {
    expect(parseAnondUrl("https://example.com/20261008133853")).toBeNull();
  });

  it("rejects extra path", () => {
    expect(parseAnondUrl("https://anond.hatelabo.jp/20261008133853/../x")).toBeNull();
  });

  it("rejects query strings", () => {
    expect(parseAnondUrl("https://anond.hatelabo.jp/20261008133853?a=1")).toBeNull();
  });

  it("rejects missing input", () => {
    expect(parseAnondUrl(null)).toBeNull();
  });
});

describe("extractBody", () => {
  it("returns the text meta content with entities decoded", () => {
    expect(extractBody(fixture("anond.html"))).toBe("朝起きたら置き手紙があった。\n\t理由はわからない。&そういうこと");
  });

  it("decodes numeric entities", () => {
    expect(extractBody('<meta itemprop="text" content="&#12354;&#x3044;&quot;&#39;&lt;&gt;" />')).toBe("あい\"'<>");
  });

  it("returns null without the text meta", () => {
    expect(extractBody("<html><body>削除されました</body></html>")).toBeNull();
  });
});

describe("parseBookmarks", () => {
  it("returns the title", () => {
    expect(parseBookmarks(fixture("jsonlite.json"), 10).title).toBe("嫁が出ていった");
  });

  it("returns the bookmark count", () => {
    expect(parseBookmarks(fixture("jsonlite.json"), 10).count).toBe(3);
  });

  it("keeps only bookmarks with comments", () => {
    expect(parseBookmarks(fixture("jsonlite.json"), 10).comments).toEqual([
      { user: "alice", comment: "創作乙。設定盛りすぎ" },
      { user: "carol", comment: "うちも同じだったのでわかる" },
    ]);
  });

  it("takes at most the given number of comments from the top", () => {
    expect(parseBookmarks(fixture("jsonlite.json"), 1).comments.map((c) => c.user)).toEqual(["alice"]);
  });

  it("returns the entry id", () => {
    expect(parseBookmarks(fixture("jsonlite.json"), 10).eid).toBe("4789012345");
  });

  it("reports how many comments exist in total", () => {
    expect(parseBookmarks(fixture("jsonlite.json"), 1).totalComments).toBe(2);
  });
});
