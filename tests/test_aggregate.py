from datetime import UTC, datetime

import pytest

from masuda_verdict.aggregate import summarize
from masuda_verdict.store import Store

NOW = datetime(2026, 10, 9, tzinfo=UTC)
URL = "https://anond.hatelabo.jp/1"


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path)
    s.append(
        "seen", {"url": URL, "title": "t", "bookmark_count": 150, "bookmarked_at": "2026-10-07T00:00:00+00:00"}, NOW
    )
    s.append("judged", {"url": URL, "judged_at": NOW.isoformat()}, NOW)
    s.append("body_verdicts", {"url": URL, "model": "clef", "probs": {"fiction": 0.0, "fact": 1.0}}, NOW)
    return s


def add_comment(store, user, **probs):
    full = {"fiction": 0.0, "fact": 0.0, "none": 0.0, **probs}
    store.append("comment_verdicts", {"url": URL, "user": user, "model": "clef", "probs": full}, NOW)


def entry(store):
    return summarize(store, primary_model="clef", min_mentions=1)["entries"][0]


def test_crowd_ignores_none_mass(store):
    add_comment(store, "a", fiction=1.0)
    add_comment(store, "b", none=1.0)
    assert entry(store)["crowd"] == {"fiction": 1.0, "fact": 0.0}


def test_crowd_averages_mentions(store):
    add_comment(store, "a", fiction=1.0)
    add_comment(store, "b", fact=0.5, none=0.5)
    assert entry(store)["crowd"] == pytest.approx({"fiction": 2 / 3, "fact": 1 / 3})


def test_mentions_counts_non_none_mass(store):
    add_comment(store, "a", fiction=1.0)
    add_comment(store, "b", fact=0.5, none=0.5)
    assert entry(store)["mentions"] == pytest.approx(1.5)


def test_comment_count(store):
    add_comment(store, "a", fiction=1.0)
    add_comment(store, "b", none=1.0)
    assert entry(store)["comment_count"] == 2


def test_gap_is_total_variation_between_primary_model_and_crowd(store):
    add_comment(store, "a", fiction=1.0)
    assert entry(store)["gap"] == pytest.approx(1.0)


def test_crowd_is_null_below_min_mentions(store):
    add_comment(store, "a", none=1.0)
    assert entry(store)["crowd"] is None


def test_gap_is_null_without_crowd(store):
    add_comment(store, "a", none=1.0)
    assert entry(store)["gap"] is None


def test_models_keyed_by_name(store):
    assert entry(store)["models"] == {"clef": {"fiction": 0.0, "fact": 1.0}}


def test_excludes_unjudged_entries(store):
    store.append(
        "seen", {"url": "u2", "title": "t", "bookmark_count": 60, "bookmarked_at": "2026-10-08T00:00:00+00:00"}, NOW
    )
    assert [e["url"] for e in summarize(store, primary_model="clef")["entries"]] == [URL]


def test_entries_ordered_by_bookmarked_at_desc(store):
    for url, ts in [("u2", "2026-10-05"), ("u3", "2026-10-08"), ("u4", "2026-10-06")]:
        store.append(
            "seen", {"url": url, "title": "t", "bookmark_count": 60, "bookmarked_at": f"{ts}T00:00:00+00:00"}, NOW
        )
        store.append("judged", {"url": url, "judged_at": NOW.isoformat()}, NOW)
    urls = [e["url"] for e in summarize(store, primary_model="clef")["entries"]]
    assert urls == ["u3", URL, "u4", "u2"]


def test_crowd_ignores_labels_outside_verdicts(store):
    add_comment(store, "a", fiction=1.0, fishing=1.0)
    assert entry(store)["crowd"] == {"fiction": 1.0, "fact": 0.0}
