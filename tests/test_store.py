from datetime import UTC, datetime

from masuda_verdict.store import Store


def test_append_partitions_by_month(tmp_path):
    Store(tmp_path).append("seen", {"url": "a"}, datetime(2026, 10, 9, tzinfo=UTC))
    assert (tmp_path / "seen" / "2026-10.jsonl").exists()


def test_read_returns_records_across_months_in_order(tmp_path):
    store = Store(tmp_path)
    store.append("seen", {"url": "b"}, datetime(2026, 11, 1, tzinfo=UTC))
    store.append("seen", {"url": "a"}, datetime(2026, 10, 9, tzinfo=UTC))
    assert [r["url"] for r in store.read("seen")] == ["a", "b"]


def test_read_returns_nothing_for_unknown_kind(tmp_path):
    assert list(Store(tmp_path).read("seen")) == []


def test_append_keeps_japanese_readable(tmp_path):
    Store(tmp_path).append("seen", {"title": "増田"}, datetime(2026, 10, 9, tzinfo=UTC))
    assert "増田" in (tmp_path / "seen" / "2026-10.jsonl").read_text()
