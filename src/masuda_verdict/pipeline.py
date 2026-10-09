import logging
from collections.abc import Callable
from datetime import datetime, timedelta

from .deciders import Decider, Question
from .hatena import BookmarkComment, HotEntry
from .store import Store

log = logging.getLogger(__name__)

SETTLE_PERIOD = timedelta(hours=48)
BODY_MAX_CHARS = 4000

BODY_QUESTION = Question(
    name="verdict",
    instructions="はてな匿名ダイアリーへの投稿。書かれている内容は次のどれに当たるか。",
    choices={
        "fishing": "釣り：反応を集めるために意図的に煽ったり極端な主張をしている",
        "fiction": "創作：体験談や告白の体裁をとった作り話",
        "fact": "事実：書き手の実体験や本心がそのまま書かれている",
    },
)

COMMENT_QUESTION = Question(
    name="verdict",
    instructions="はてな匿名ダイアリーの記事に付いたはてなブックマークのコメント。コメント主は元記事の真偽をどう見ているか。",
    choices={
        "fishing": "釣り・炎上狙いだと見ている",
        "fiction": "創作・作り話だと見ている",
        "fact": "事実・実話として受け止めている",
        "none": "真偽には触れていない",
    },
)


def collect(store: Store, entries: list[HotEntry], now: datetime) -> None:
    seen = {r["url"] for r in store.read("seen")}
    for e in entries:
        if e.url in seen:
            continue
        store.append(
            "seen",
            {
                "url": e.url,
                "title": e.title,
                "bookmark_count": e.bookmark_count,
                "bookmarked_at": datetime.fromisoformat(e.bookmarked_at).isoformat(),
                "first_seen": now.isoformat(),
            },
            now,
        )
        seen.add(e.url)


def due_entries(store: Store, now: datetime) -> list[dict]:
    judged = {r["url"] for r in store.read("judged")}
    return [
        r
        for r in store.read("seen")
        if r["url"] not in judged and datetime.fromisoformat(r["bookmarked_at"]) + SETTLE_PERIOD <= now
    ]


def judge_entry(
    store: Store,
    entry: dict,
    fetch_body: Callable[[str], str | None],
    fetch_comments: Callable[[str], list[BookmarkComment]],
    body_deciders: list[Decider],
    comment_decider: Decider,
    now: datetime,
) -> None:
    url = entry["url"]
    _judge_body(store, entry, fetch_body, body_deciders, now)

    done_users = {r["user"] for r in store.read("comment_verdicts") if r["url"] == url}
    for c in fetch_comments(url):
        if c.user in done_users:
            continue
        probs = comment_decider.decide(
            f"記事タイトル: {entry['title']}\nブックマークコメント: {c.comment}", COMMENT_QUESTION
        )
        store.append(
            "comment_verdicts",
            {"url": url, "user": c.user, "timestamp": c.timestamp, "model": comment_decider.name, "probs": probs},
            now,
        )

    store.append("judged", {"url": url, "judged_at": now.isoformat()}, now)


def _judge_body(store, entry, fetch_body, deciders, now):
    url = entry["url"]
    done = {r["model"] for r in store.read("body_verdicts") if r["url"] == url}
    pending = [d for d in deciders if d.name not in done]
    if not pending:
        return
    body = fetch_body(url)
    if body is None:
        return
    text = f"タイトル: {entry['title']}\n\n{body[:BODY_MAX_CHARS]}"
    for d in pending:
        try:
            probs = d.decide(text, BODY_QUESTION)
        except Exception:
            log.exception("body decider %s failed for %s", d.name, url)
            continue
        store.append("body_verdicts", {"url": url, "model": d.name, "probs": probs}, now)
