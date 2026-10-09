import logging
from collections.abc import Callable
from datetime import datetime, timedelta

from .deciders import CarryOver, Decider, Question
from .hatena import BookmarkComment, HotEntry
from .store import Store

log = logging.getLogger(__name__)

SETTLE_PERIOD = timedelta(hours=48)
BODY_MAX_CHARS = 4000

BODY_QUESTION = Question(
    name="verdict",
    instructions="はてな匿名ダイアリーへの投稿。書かれている内容は次のどれに当たるか。",
    choices={
        "fiction": "創作：作り話、または反応を集めるための釣りやネタ",
        "fact": "事実：書き手の実体験や本心がそのまま書かれている",
    },
)

COMMENT_QUESTION = Question(
    name="verdict",
    instructions="はてな匿名ダイアリーの記事に付いたはてなブックマークのコメント。コメント主は元記事の真偽をどう見ているか。",
    choices={
        "fiction": "創作・作り話・釣り・ネタだと見ている",
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
    primary: Decider,
    optional_body_deciders: list[Decider],
    now: datetime,
) -> None:
    url = entry["url"]
    _judge_body(store, entry, fetch_body, primary, optional_body_deciders, now)

    done_users = {r["user"] for r in store.read("comment_verdicts") if r["url"] == url}
    for c in fetch_comments(url):
        if c.user in done_users:
            continue
        probs = primary.decide(f"記事タイトル: {entry['title']}\nブックマークコメント: {c.comment}", COMMENT_QUESTION)
        store.append(
            "comment_verdicts",
            {"url": url, "user": c.user, "timestamp": c.timestamp, "model": primary.name, "probs": probs},
            now,
        )

    store.append("judged", {"url": url, "judged_at": now.isoformat()}, now)


def _judge_body(store, entry, fetch_body, primary, optional, now):
    url = entry["url"]
    done = {r["model"] for r in store.read("body_verdicts") if r["url"] == url}
    pending = [d for d in [primary, *optional] if d.name not in done]
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
            if d is primary:
                raise
            log.exception("optional body decider %s failed for %s", d.name, url)
            continue
        store.append("body_verdicts", {"url": url, "model": d.name, "probs": probs}, now)


def judge_due(
    store: Store,
    fetch_body: Callable[[str], str | None],
    fetch_comments: Callable[[str], list[BookmarkComment]],
    primary: Decider,
    optional_body_deciders: list[Decider],
    now: datetime,
) -> None:
    for entry in due_entries(store, now):
        try:
            judge_entry(store, entry, fetch_body, fetch_comments, primary, optional_body_deciders, now)
        except CarryOver as e:
            log.info("carrying over from %s: %s", entry["url"], e)
            return
