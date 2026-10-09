from pathlib import Path

from masuda_verdict.hatena import parse_anond_body, parse_bookmarks, parse_hot_rss

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_hot_rss_returns_urls():
    entries = parse_hot_rss((FIXTURES / "hot.rss").read_text())
    assert [e.url for e in entries] == [
        "https://anond.hatelabo.jp/20261008222016",
        "https://anond.hatelabo.jp/20261008133853",
    ]


def test_parse_hot_rss_returns_titles():
    entries = parse_hot_rss((FIXTURES / "hot.rss").read_text())
    assert [e.title for e in entries] == ["若手医師の直美流入問題", "嫁が出ていった"]


def test_parse_hot_rss_returns_bookmark_counts():
    entries = parse_hot_rss((FIXTURES / "hot.rss").read_text())
    assert [e.bookmark_count for e in entries] == [203, 150]


def test_parse_bookmarks_skips_bookmarks_without_comment():
    comments = parse_bookmarks((FIXTURES / "jsonlite.json").read_text())
    assert [c.user for c in comments] == ["alice", "carol"]


def test_parse_bookmarks_returns_comment_text():
    comments = parse_bookmarks((FIXTURES / "jsonlite.json").read_text())
    assert comments[0].comment == "創作乙。設定盛りすぎ"


def test_parse_bookmarks_returns_timestamp():
    comments = parse_bookmarks((FIXTURES / "jsonlite.json").read_text())
    assert comments[0].timestamp == "2026/10/08 14:01"


def test_parse_anond_body_returns_plain_text():
    body = parse_anond_body((FIXTURES / "anond.html").read_text())
    assert body == "朝起きたら置き手紙があった。\n\t理由はわからない。&そういうこと"


def test_parse_anond_body_returns_none_without_text_meta():
    assert parse_anond_body("<html><body>削除されました</body></html>") is None


def test_parse_hot_rss_returns_bookmarked_at():
    entries = parse_hot_rss((FIXTURES / "hot.rss").read_text())
    assert entries[0].bookmarked_at == "2026-10-08T13:21:49Z"
