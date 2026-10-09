import json
import logging
from collections.abc import Callable
from datetime import datetime, timedelta
from importlib.resources import files

from .deciders import CarryOver, Decider, Question
from .hatena import BookmarkComment, HotEntry
from .store import Store

log = logging.getLogger(__name__)

SETTLE_PERIOD = timedelta(hours=48)
BODY_MAX_CHARS = 4000

_QUESTIONS = json.loads(files(__package__).joinpath("questions.json").read_text())
BODY_QUESTION = Question(**_QUESTIONS["body"])
COMMENT_QUESTION = Question(**_QUESTIONS["comment"])
NARRATIVE_QUESTION = Question(**_QUESTIONS["narrative"])


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
    narrative_done = any(r["url"] == url for r in store.read("narrative_verdicts"))
    if not pending and narrative_done:
        return
    body = fetch_body(url)
    if body is None:
        if not narrative_done:
            store.append("narrative_verdicts", {"url": url, "model": primary.name, "probs": None}, now)
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
    if not narrative_done:
        probs = primary.decide(text, NARRATIVE_QUESTION)
        store.append("narrative_verdicts", {"url": url, "model": primary.name, "probs": probs}, now)


def judge_due(
    store: Store,
    fetch_body: Callable[[str], str | None],
    fetch_comments: Callable[[str], list[BookmarkComment]],
    primary: Decider,
    optional_body_deciders: list[Decider],
    now: datetime,
) -> None:
    judged = {r["url"] for r in store.read("judged")}
    narrated = {r["url"] for r in store.read("narrative_verdicts")}
    backfill = [r for r in store.read("seen") if r["url"] in judged and r["url"] not in narrated]
    try:
        for entry in backfill:
            _judge_body(store, entry, fetch_body, primary, [], now)
        for entry in due_entries(store, now):
            judge_entry(store, entry, fetch_body, fetch_comments, primary, optional_body_deciders, now)
    except CarryOver as e:
        log.info("carrying over: %s", e)
