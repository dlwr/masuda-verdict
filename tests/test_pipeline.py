from datetime import UTC, datetime, timedelta

import pytest

from masuda_verdict.deciders import CarryOver
from masuda_verdict.hatena import BookmarkComment, HotEntry
from masuda_verdict.pipeline import BODY_QUESTION, COMMENT_QUESTION, collect, due_entries, judge_due, judge_entry
from masuda_verdict.store import Store

NOW = datetime(2026, 10, 9, 12, 0, tzinfo=UTC)
URL = "https://anond.hatelabo.jp/20261008133853"


class FixedDecider:
    def __init__(self, name, probs):
        self.name = name
        self.probs = probs
        self.inputs = []

    def decide(self, text, question):
        self.inputs.append(text)
        return {k: self.probs.get(k, 0.0) for k in question.choices}


class BrokenDecider:
    name = "broken"

    def decide(self, text, question):
        raise RuntimeError("quota")


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path)


def seen_record(url=URL, bookmarked_at=NOW - timedelta(hours=49)):
    return {
        "url": url,
        "title": "嫁が出ていった",
        "bookmark_count": 150,
        "bookmarked_at": bookmarked_at.isoformat(),
        "first_seen": NOW.isoformat(),
    }


def test_collect_records_new_entry_with_first_seen(store):
    collect(store, [HotEntry(URL, "嫁が出ていった", 150, "2026-10-08T04:38:59Z")], NOW)
    assert list(store.read("seen")) == [
        {
            "url": URL,
            "title": "嫁が出ていった",
            "bookmark_count": 150,
            "bookmarked_at": "2026-10-08T04:38:59+00:00",
            "first_seen": NOW.isoformat(),
        }
    ]


def test_collect_skips_already_seen_entry(store):
    collect(store, [HotEntry(URL, "嫁が出ていった", 150, "2026-10-08T04:38:59Z")], NOW)
    collect(store, [HotEntry(URL, "嫁が出ていった", 180, "2026-10-08T04:38:59Z")], NOW + timedelta(hours=6))
    assert len(list(store.read("seen"))) == 1


def test_due_entries_waits_48_hours_after_bookmarked(store):
    store.append("seen", seen_record(url="https://anond.hatelabo.jp/old", bookmarked_at=NOW - timedelta(hours=49)), NOW)
    store.append("seen", seen_record(url="https://anond.hatelabo.jp/new", bookmarked_at=NOW - timedelta(hours=47)), NOW)
    assert [e["url"] for e in due_entries(store, NOW)] == ["https://anond.hatelabo.jp/old"]


def test_due_entries_excludes_judged(store):
    store.append("seen", seen_record(), NOW)
    store.append("judged", {"url": URL, "judged_at": NOW.isoformat()}, NOW)
    assert due_entries(store, NOW) == []


def judge(store, primary, optional=(), comments=None, body="朝起きたら置き手紙があった。"):
    comments = (
        comments
        if comments is not None
        else [
            BookmarkComment("alice", "2026/10/08 14:01", "創作乙"),
            BookmarkComment("carol", "2026/10/08 15:30", "わかる"),
        ]
    )
    judge_entry(
        store,
        seen_record(),
        fetch_body=lambda url: body,
        fetch_comments=lambda url: comments,
        primary=primary,
        optional_body_deciders=list(optional),
        now=NOW,
    )


class BodyBrokenDecider(FixedDecider):
    def decide(self, text, question):
        if question is BODY_QUESTION:
            raise KeyError("result")
        return super().decide(text, question)


def test_judge_entry_records_body_verdict_per_model(store):
    judge(store, FixedDecider("clef", {"fiction": 1.0}), optional=[FixedDecider("jev", {"fact": 1.0})])
    assert [(r["model"], r["probs"]["fiction"]) for r in store.read("body_verdicts")] == [("clef", 1.0), ("jev", 0.0)]


def test_judge_entry_records_comment_verdicts(store):
    judge(store, FixedDecider("clef", {"fiction": 0.8, "none": 0.2}))
    assert [(r["user"], r["probs"]["fiction"]) for r in store.read("comment_verdicts")] == [
        ("alice", 0.8),
        ("carol", 0.8),
    ]


def test_judge_entry_does_not_store_comment_text(store):
    judge(store, FixedDecider("clef", {"none": 1.0}))
    assert all("comment" not in r for r in store.read("comment_verdicts"))


def test_judge_entry_sends_title_with_comment(store):
    clef = FixedDecider("clef", {"none": 1.0})
    judge(store, clef)
    assert clef.inputs[1] == "記事タイトル: 嫁が出ていった\nブックマークコメント: 創作乙"


def test_judge_entry_marks_entry_judged(store):
    judge(store, FixedDecider("clef", {"none": 1.0}))
    assert [r["url"] for r in store.read("judged")] == [URL]


def test_judge_entry_skips_comments_already_judged(store):
    store.append("body_verdicts", {"url": URL, "model": "clef", "probs": {}}, NOW)
    store.append("comment_verdicts", {"url": URL, "user": "alice", "model": "clef", "probs": {}}, NOW)
    clef = FixedDecider("clef", {"none": 1.0})
    judge(store, clef)
    assert clef.inputs == ["記事タイトル: 嫁が出ていった\nブックマークコメント: わかる"]


def test_judge_entry_skips_body_already_judged(store):
    store.append("body_verdicts", {"url": URL, "model": "clef", "probs": {}}, NOW)
    clef = FixedDecider("clef", {"none": 1.0})
    judge(store, clef, comments=[])
    assert clef.inputs == []


def test_judge_entry_propagates_primary_comment_failure_without_marking_judged(store):
    with pytest.raises(RuntimeError):
        judge(store, BrokenDecider())
    assert list(store.read("judged")) == []


def test_judge_entry_propagates_primary_body_failure(store):
    with pytest.raises(KeyError):
        judge(store, BodyBrokenDecider("clef", {"none": 1.0}))


def test_judge_entry_tolerates_optional_body_decider_failure(store):
    judge(store, FixedDecider("clef", {"none": 1.0}), optional=[BrokenDecider()])
    assert [r["url"] for r in store.read("judged")] == [URL]


def test_judge_entry_skips_body_when_deleted(store):
    judge(store, FixedDecider("clef", {"fact": 1.0}), body=None)
    assert list(store.read("body_verdicts")) == []


class CarryOverDecider:
    name = "clef"

    def decide(self, text, question):
        raise CarryOver("quota")


def run_judge_due(store, primary):
    return judge_due(
        store,
        fetch_body=lambda url: "本文",
        fetch_comments=lambda url: [BookmarkComment("alice", "2026/10/08 14:01", "創作乙")],
        primary=primary,
        optional_body_deciders=[],
        now=NOW,
    )


def test_judge_due_judges_due_entries(store):
    store.append("seen", seen_record(), NOW)
    run_judge_due(store, FixedDecider("clef", {"none": 1.0}))
    assert [r["url"] for r in store.read("judged")] == [URL]


def test_judge_due_stops_quietly_on_carry_over(store):
    store.append("seen", seen_record(), NOW)
    run_judge_due(store, CarryOverDecider())
    assert list(store.read("judged")) == []


def test_judge_due_raises_other_failures(store):
    store.append("seen", seen_record(), NOW)
    with pytest.raises(RuntimeError):
        run_judge_due(store, BrokenDecider())


def test_body_question_offers_fiction_and_fact():
    assert list(BODY_QUESTION.choices) == ["fiction", "fact"]


def test_comment_question_offers_fiction_fact_and_none():
    assert list(COMMENT_QUESTION.choices) == ["fiction", "fact", "none"]
