from datetime import UTC, datetime, timedelta

import pytest

from masuda_verdict.deciders import CarryOver
from masuda_verdict.hatena import BookmarkComment, HotEntry
from masuda_verdict.pipeline import (
    BACKFILL_MAX_COMMENTS,
    BACKFILL_TOP_N,
    BODY_QUESTION,
    COMMENT_QUESTION,
    NARRATIVE_QUESTION,
    collect,
    due_entries,
    judge_due,
    judge_entry,
)
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


def test_due_entries_waits_24_hours_after_bookmarked(store):
    store.append("seen", seen_record(url="https://anond.hatelabo.jp/old", bookmarked_at=NOW - timedelta(hours=25)), NOW)
    store.append("seen", seen_record(url="https://anond.hatelabo.jp/new", bookmarked_at=NOW - timedelta(hours=23)), NOW)
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
    judge(store, FixedDecider("clef", {"experience": 1.0, "fiction": 0.8, "none": 0.2}))
    assert [(r["user"], r["probs"]["fiction"]) for r in store.read("comment_verdicts")] == [
        ("alice", 0.8),
        ("carol", 0.8),
    ]


def test_judge_entry_does_not_store_comment_text(store):
    judge(store, FixedDecider("clef", {"none": 1.0}))
    assert all("comment" not in r for r in store.read("comment_verdicts"))


def test_judge_entry_sends_title_with_comment(store):
    clef = FixedDecider("clef", {"experience": 1.0, "none": 1.0})
    judge(store, clef)
    assert "記事タイトル: 嫁が出ていった\nブックマークコメント: 創作乙" in clef.inputs


def test_judge_entry_marks_entry_judged(store):
    judge(store, FixedDecider("clef", {"none": 1.0}))
    assert [r["url"] for r in store.read("judged")] == [URL]


def test_judge_entry_skips_comments_already_judged(store):
    store.append("body_verdicts", {"url": URL, "model": "clef", "probs": {}}, NOW)
    store.append("narrative_verdicts", {"url": URL, "model": "clef", "probs": {"experience": 1.0}}, NOW)
    store.append("comment_verdicts", {"url": URL, "user": "alice", "model": "clef", "probs": {}}, NOW)
    clef = FixedDecider("clef", {"none": 1.0})
    judge(store, clef)
    assert clef.inputs == ["記事タイトル: 嫁が出ていった\nブックマークコメント: わかる"]


def test_judge_entry_skips_body_already_judged(store):
    store.append("body_verdicts", {"url": URL, "model": "clef", "probs": {}}, NOW)
    store.append("narrative_verdicts", {"url": URL, "model": "clef", "probs": {}}, NOW)
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


def test_narrative_question_offers_experience_and_other():
    assert list(NARRATIVE_QUESTION.choices) == ["experience", "other"]


class QuestionAwareDecider(FixedDecider):
    def __init__(self, name):
        super().__init__(name, {})
        self.questions = []

    def decide(self, text, question):
        self.questions.append(question.name)
        if question is NARRATIVE_QUESTION:
            return {"experience": 0.9, "other": 0.1}
        return {k: (1.0 if k == "none" or k == "fact" else 0.0) for k in question.choices}


def test_judge_entry_records_narrative_verdict(store):
    judge(store, QuestionAwareDecider("clef"))
    assert [(r["model"], r["probs"]) for r in store.read("narrative_verdicts")] == [
        ("clef", {"experience": 0.9, "other": 0.1})
    ]


def test_judge_entry_skips_narrative_already_judged(store):
    store.append("narrative_verdicts", {"url": URL, "model": "clef", "probs": {}}, NOW)
    clef = QuestionAwareDecider("clef")
    judge(store, clef)
    assert "narrative" not in clef.questions


def test_judge_entry_records_null_narrative_when_deleted(store):
    judge(store, QuestionAwareDecider("clef"), body=None)
    assert [r["probs"] for r in store.read("narrative_verdicts")] == [None]


def test_judge_due_backfills_narrative_for_judged_entries(store):
    store.append("seen", seen_record(), NOW)
    store.append("judged", {"url": URL, "judged_at": NOW.isoformat()}, NOW)
    run_judge_due(store, QuestionAwareDecider("clef"))
    assert [r["url"] for r in store.read("narrative_verdicts")] == [URL]


def test_judge_due_backfill_does_not_rejudge_comments(store):
    store.append("seen", seen_record(), NOW)
    store.append("judged", {"url": URL, "judged_at": NOW.isoformat()}, NOW)
    run_judge_due(store, QuestionAwareDecider("clef"))
    assert list(store.read("comment_verdicts")) == []


def test_judge_entry_skips_comments_when_not_experience(store):
    judge(store, FixedDecider("clef", {"other": 1.0, "fiction": 1.0}))
    assert list(store.read("comment_verdicts")) == []


def test_judge_entry_marks_judged_when_not_experience(store):
    judge(store, FixedDecider("clef", {"other": 1.0, "fiction": 1.0}))
    assert [r["url"] for r in store.read("judged")] == [URL]


def test_judge_entry_skips_comments_when_deleted(store):
    judge(store, FixedDecider("clef", {"experience": 1.0, "fiction": 1.0}), body=None)
    assert list(store.read("comment_verdicts")) == []


def test_collect_marks_backfill_entries(store):
    collect(store, [HotEntry(URL, "嫁が出ていった", 150, "2019-10-31T08:51:00+09:00")], NOW, backfill=True)
    assert [r["backfill"] for r in store.read("seen")] == [True]


def test_due_entries_excludes_backfill(store):
    store.append("seen", {**seen_record(), "backfill": True}, NOW)
    assert due_entries(store, NOW) == []


class BackfillDecider(FixedDecider):
    def __init__(self, fiction_by_url_id, experience=0.9):
        super().__init__("clef", {})
        self.fiction_by_url_id = fiction_by_url_id
        self.experience = experience
        self.comment_inputs = []

    def decide(self, text, question):
        if question is COMMENT_QUESTION:
            self.comment_inputs.append(text)
            return {"fiction": 1.0, "fact": 0.0, "none": 0.0}
        if question is NARRATIVE_QUESTION:
            return {"experience": self.experience, "other": 1 - self.experience}
        fiction = next(v for k, v in self.fiction_by_url_id.items() if text.split("\n")[0] == f"タイトル: {k}")
        return {"fiction": fiction, "fact": 1 - fiction}


def seed_backfill(store, fictions):
    for i, _ in enumerate(fictions):
        store.append(
            "seen",
            {**seen_record(url=f"https://anond.hatelabo.jp/b{i}"), "title": f"b{i}", "backfill": True},
            NOW,
        )
    return BackfillDecider({f"b{i}": f for i, f in enumerate(fictions)})


def run_backfill(store, decider, comments=None):
    comments = comments or [BookmarkComment("alice", "2026/10/08 14:01", "創作乙")]
    judge_due(
        store,
        fetch_body=lambda url: "本文",
        fetch_comments=lambda url: comments,
        primary=decider,
        optional_body_deciders=[],
        now=NOW,
    )


def test_judge_due_judges_backfill_bodies(store):
    run_backfill(store, seed_backfill(store, [0.1, 0.2, 0.3]))
    assert len(list(store.read("body_verdicts"))) == 3


def test_judge_due_judges_comments_only_for_top_fiction_backfill(store):
    fictions = [0.1 * i for i in range(BACKFILL_TOP_N + 3)]
    run_backfill(store, seed_backfill(store, fictions))
    judged = {r["url"] for r in store.read("judged")}
    expected = {f"https://anond.hatelabo.jp/b{i}" for i in range(3, BACKFILL_TOP_N + 3)}
    assert judged == expected


def test_judge_due_skips_backfill_comments_for_non_experience(store):
    decider = seed_backfill(store, [0.9])
    decider.experience = 0.1
    run_backfill(store, decider)
    assert list(store.read("judged")) == []


def test_judge_due_caps_backfill_comments(store):
    comments = [BookmarkComment(f"u{i}", "2026/10/08 14:01", "創作乙") for i in range(BACKFILL_MAX_COMMENTS + 5)]
    decider = seed_backfill(store, [0.9])
    run_backfill(store, decider, comments=comments)
    assert len(decider.comment_inputs) == BACKFILL_MAX_COMMENTS


def test_judge_due_waits_for_all_backfill_bodies_before_comments(store):
    decider = seed_backfill(store, [0.9, 0.8])
    store.append(
        "narrative_verdicts",
        {"url": "https://anond.hatelabo.jp/b0", "model": "clef", "probs": {"experience": 0.9}},
        NOW,
    )
    store.append(
        "body_verdicts", {"url": "https://anond.hatelabo.jp/b0", "model": "clef", "probs": {"fiction": 0.9}}, NOW
    )

    class StopsOnBody(BackfillDecider):
        def decide(self, text, question):
            if question is BODY_QUESTION:
                raise CarryOver("quota")
            return super().decide(text, question)

    run_backfill(store, StopsOnBody(decider.fiction_by_url_id))
    assert list(store.read("judged")) == []


def test_judge_due_judges_live_entries_before_backfill(store):
    store.append("seen", {**seen_record(url="https://anond.hatelabo.jp/b0"), "title": "b0", "backfill": True}, NOW)
    store.append("seen", {**seen_record(), "title": "live"}, NOW)
    decider = BackfillDecider({"b0": 0.9, "live": 0.5})
    calls = []

    class Recording(BackfillDecider):
        def decide(self, text, question):
            calls.append(text.split("\n")[0])
            if len(calls) > 1:
                raise CarryOver("quota")
            return super().decide(text, question)

    run_backfill(store, Recording(decider.fiction_by_url_id))
    assert calls[0] == "タイトル: live"
