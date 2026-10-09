export type Probs = { fiction: number; fact: number };
export type CommentVerdict = { user: string; label: "fiction" | "fact" | "none"; score: number; comment?: string };
export type Entry = {
  url: string;
  eid?: string | null;
  title: string;
  bookmark_count: number;
  bookmarked_at?: string;
  models: Record<string, Probs>;
  crowd: Probs | null;
  mentions: number;
  comment_count: number;
  total_comments?: number;
  gap: number | null;
  narrative: number | null;
  suspicion: number | null;
  comments?: CommentVerdict[];
};

const PRIMARY = "clef";

const escape = (s: string) =>
  s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]!);
const pct = (v: number) => `${Math.round(v * 100)}%`;
const lean = (p: Probs) => (p.fact >= p.fiction ? `事実 ${pct(p.fact)}` : `創作 ${pct(p.fiction)}`);
const votes = (p: Probs, mentions: number) =>
  `事実 ${Math.round(p.fact * mentions)} 票・創作 ${Math.round(p.fiction * mentions)} 票`;
const date = (iso: string) =>
  new Date(iso).toLocaleDateString("ja-JP", { timeZone: "Asia/Tokyo", month: "numeric", day: "numeric" });
const entryPath = (url: string) => url.replace(/^https?:\/\//, "");

function axis(model: Probs | undefined, crowd: Probs | null, mentions: number): string {
  const marker = (who: "ai" | "crowd", label: string, p: Probs) =>
    `<span class="marker ${who}" style="left:${(p.fact * 100).toFixed(1)}%" title="${label}: ${who === "ai" ? lean(p) : votes(p, mentions)}">` +
    `<span class="marker-label">${label}</span></span>`;
  const span =
    model && crowd
      ? `<span class="span" style="left:${(Math.min(model.fact, crowd.fact) * 100).toFixed(1)}%;width:${(Math.abs(model.fact - crowd.fact) * 100).toFixed(1)}%"></span>`
      : "";
  return `
    <div class="axis" role="img" aria-label="${[model && `AI ${lean(model)}`, crowd && `ブコメ民 ${votes(crowd, mentions)}`].filter(Boolean).join("、")}">
      <span class="pole fiction">創作</span>
      <div class="track">
        <span class="mid"></span>
        ${span}
        ${model ? marker("ai", "AI", model) : ""}
        ${crowd ? marker("crowd", "ブコメ民", crowd) : ""}
      </div>
      <span class="pole fact">事実</span>
    </div>`;
}

function readout(e: Entry): string {
  const model = e.models[PRIMARY];
  const others = Object.entries(e.models).filter(([name]) => name !== PRIMARY);
  return `
    <dl class="readout">
      ${model ? `<div><dt>AI（本文だけ）</dt><dd>${lean(model)}</dd></div>` : ""}
      <div><dt>ブコメ民</dt><dd>${e.crowd ? votes(e.crowd, e.mentions) : "真偽に触れたブコメが少ない"}</dd></div>
      ${e.gap !== null ? `<div class="gap"><dt>ズレ</dt><dd>${pct(e.gap)}</dd></div>` : ""}
      ${e.suspicion !== null ? `<div><dt>疑われ度</dt><dd>${pct(e.suspicion)}</dd></div>` : ""}
      ${others.map(([name, p]) => `<div class="sub"><dt>${escape(name)}</dt><dd>${lean(p)}</dd></div>`).join("")}
    </dl>`;
}

export function renderEntry(e: Entry, options: { sampled?: boolean } = {}): string {
  const count = options.sampled
    ? `ブコメ ${e.total_comments} 件のうち新しい ${e.comment_count} 件で判定`
    : `ブコメ ${e.comment_count} 件で判定`;
  const meta = [e.bookmarked_at && date(e.bookmarked_at), `${e.bookmark_count} users`, count].filter(Boolean).join(" · ");
  return `
    <article class="entry" data-url="${escape(e.url)}">
      <h2 class="title"><a href="${escape(e.url)}">${escape(e.title)}</a></h2>
      <p class="meta">${meta} · <a href="https://b.hatena.ne.jp/entry/s/${escape(entryPath(e.url))}">はてブで見る</a></p>
      ${axis(e.models[PRIMARY], e.crowd, e.mentions)}
      ${readout(e)}
      ${e.narrative !== null && e.narrative < 0.5 ? '<p class="note">体験談ではなさそうな増田なので、真偽の判定は参考程度。</p>' : ""}
      ${
        e.comments && e.comments.length
          ? `<details class="comments"><summary>どのブコメが疑っていたか見る</summary><div class="comments-body"></div></details>`
          : ""
      }
    </article>`;
}

function commentItem(c: Required<CommentVerdict>, eid: string | null | undefined): string {
  const href = eid
    ? `https://b.hatena.ne.jp/entry/${encodeURIComponent(eid)}/comment/${encodeURIComponent(c.user)}`
    : null;
  const user = escape(c.user);
  return `
    <li>
      <img src="https://cdn.profile-image.st-hatena.com/users/${encodeURIComponent(c.user)}/profile.png" alt="" width="24" height="24" loading="lazy" />
      <div>
        <p class="comment-text">${escape(c.comment)}</p>
        <p class="comment-meta">${href ? `<a href="${href}">id:${user}</a>` : `id:${user}`} · ${pct(c.score)}</p>
      </div>
    </li>`;
}

export function renderComments(verdicts: CommentVerdict[], eid: string | null | undefined): string {
  const withText = verdicts.filter((c): c is Required<CommentVerdict> => typeof c.comment === "string");
  const pick = (label: CommentVerdict["label"]) =>
    withText.filter((c) => c.label === label).sort((a, b) => b.score - a.score);
  const fiction = pick("fiction");
  const fact = pick("fact");
  const neutral = withText.length - fiction.length - fact.length;
  const column = (kind: "fiction" | "fact", heading: string, items: Required<CommentVerdict>[]) => `
    <section class="column ${kind}">
      <h3>${heading}<span>${items.length} 件</span></h3>
      ${
        items.length
          ? `<ol>${items.map((c) => commentItem(c, eid)).join("")}</ol>`
          : '<p class="empty">なし</p>'
      }
    </section>`;
  return `
    <div class="columns">
      ${column("fiction", "創作だと疑ったブコメ", fiction)}
      ${column("fact", "事実と受け止めたブコメ", fact)}
    </div>
    <p class="neutral">真偽に触れていないブコメ ${neutral} 件${withText.length < verdicts.length ? ` · 削除・非公開になったブコメ ${verdicts.length - withText.length} 件` : ""}</p>`;
}

export function attachComments(root: HTMLElement, entry: Entry, api: string) {
  const details = root.querySelector<HTMLDetailsElement>("details.comments");
  if (!details || !entry.comments) return;
  const body = details.querySelector<HTMLElement>(".comments-body")!;
  let loaded = false;
  details.addEventListener("toggle", async () => {
    if (!details.open || loaded) return;
    loaded = true;
    if (entry.comments!.every((c) => typeof c.comment === "string")) {
      body.innerHTML = renderComments(entry.comments!, entry.eid);
      return;
    }
    body.innerHTML = '<p class="loading">ブコメを読み込み中…</p>';
    try {
      const res = await fetch(`${api}/api/bookmarks?url=${encodeURIComponent(entry.url)}`);
      if (!res.ok) throw new Error(String(res.status));
      const data: { eid: string; comments: { user: string; comment: string }[] } = await res.json();
      const text = new Map(data.comments.map((c) => [c.user, c.comment]));
      const merged = entry.comments!.map((c) => ({ ...c, comment: text.get(c.user) }));
      body.innerHTML = renderComments(merged, data.eid);
    } catch {
      loaded = false;
      body.innerHTML = '<p class="loading">ブコメを読み込めませんでした。少し待ってから開き直してください。</p>';
    }
  });
}
