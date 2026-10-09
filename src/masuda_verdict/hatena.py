import json
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from html.parser import HTMLParser

NS = {
    "rss": "http://purl.org/rss/1.0/",
    "dc": "http://purl.org/dc/elements/1.1/",
    "hatena": "http://www.hatena.ne.jp/info/xmlns#",
}


@dataclass(frozen=True)
class HotEntry:
    url: str
    title: str
    bookmark_count: int
    bookmarked_at: str


def parse_hot_rss(xml: str) -> list[HotEntry]:
    root = ET.fromstring(xml)
    return [
        HotEntry(
            url=item.findtext("rss:link", namespaces=NS),
            title=item.findtext("rss:title", namespaces=NS),
            bookmark_count=int(item.findtext("hatena:bookmarkcount", namespaces=NS)),
            bookmarked_at=item.findtext("dc:date", namespaces=NS),
        )
        for item in root.findall("rss:item", NS)
    ]


@dataclass(frozen=True)
class BookmarkComment:
    user: str
    timestamp: str
    comment: str


def parse_bookmarks(raw: str) -> list[BookmarkComment]:
    return [
        BookmarkComment(user=b["user"], timestamp=b["timestamp"], comment=b["comment"])
        for b in json.loads(raw)["bookmarks"]
        if b["comment"]
    ]


class _TextMetaParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.text: str | None = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "meta" and attrs.get("itemprop") == "text" and self.text is None:
            self.text = attrs.get("content")

    handle_startendtag = handle_starttag


def parse_anond_body(html: str) -> str | None:
    parser = _TextMetaParser()
    parser.feed(html)
    return parser.text


HOT_RSS_URL = "https://b.hatena.ne.jp/site/anond.hatelabo.jp/?mode=rss&sort=recent&threshold=50"
USER_AGENT = "masuda-verdict (+https://github.com/dlwr/masuda-verdict)"


def _get(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as res:
        return res.read().decode()


def fetch_hot_entries() -> list[HotEntry]:
    return parse_hot_rss(_get(HOT_RSS_URL))


def fetch_comments(url: str) -> list[BookmarkComment]:
    return parse_bookmarks(_get("https://b.hatena.ne.jp/entry/jsonlite/?url=" + urllib.parse.quote(url, safe="")))


def fetch_body(url: str) -> str | None:
    try:
        return parse_anond_body(_get(url))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise
