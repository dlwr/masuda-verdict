import json
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
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


class _BodyParser(HTMLParser):
    BREAKS = {"p", "br", "div", "tr", "li", "blockquote", "pre"}

    def __init__(self):
        super().__init__()
        self.meta_text: str | None = None
        self.section: list[str] = []
        self._state = "before"
        self._in_h3 = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "meta" and attrs.get("itemprop") == "text" and self.meta_text is None:
            self.meta_text = attrs.get("content")
        if self._state == "before" and tag == "div" and attrs.get("class") == "section":
            self._state = "in"
        elif self._state == "in":
            if tag == "p" and attrs.get("class") == "sectionfooter":
                self._state = "done"
            elif tag == "h3":
                self._in_h3 = True
            elif tag in self.BREAKS:
                self.section.append("\n")

    handle_startendtag = handle_starttag

    def handle_endtag(self, tag):
        if tag == "h3":
            self._in_h3 = False

    def handle_data(self, data):
        if self._state == "in" and not self._in_h3:
            self.section.append(data)

    @property
    def section_text(self) -> str | None:
        lines = [line.strip() for line in "".join(self.section).splitlines()]
        return "\n".join(line for line in lines if line) or None


def parse_anond_body(html: str) -> str | None:
    parser = _BodyParser()
    parser.feed(html)
    return parser.meta_text if parser.meta_text is not None else parser.section_text


JST = timezone(timedelta(hours=9))


class _SiteEntriesParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.entries: list[dict] = []
        self._field: str | None = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "a" and attrs.get("data-gtm-click-label") == "entry-info-title":
            self.entries.append({"url": attrs["href"], "title": attrs["title"]})
        elif tag == "a" and attrs.get("data-gtm-click-label") == "entry-info-users":
            self._field = "users"
        elif tag == "li" and attrs.get("class") == "entrylist-contents-date":
            self._field = "date"

    def handle_data(self, data):
        if self._field and data.strip() and self.entries:
            self.entries[-1][self._field] = data.strip()
            self._field = None


def parse_site_entries(html: str) -> list[HotEntry]:
    parser = _SiteEntriesParser()
    parser.feed(html)
    return [
        HotEntry(
            url=e["url"],
            title=e["title"],
            bookmark_count=int(e["users"]),
            bookmarked_at=datetime.strptime(e["date"], "%Y/%m/%d %H:%M").replace(tzinfo=JST).isoformat(),
        )
        for e in parser.entries
    ]


HOT_RSS_URL = "https://b.hatena.ne.jp/site/anond.hatelabo.jp/?mode=rss&sort=recent&threshold=30"
USER_AGENT = "masuda-verdict (+https://github.com/dlwr/masuda-verdict)"


def _get(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as res:
        return res.read().decode()


def fetch_hot_entries() -> list[HotEntry]:
    return parse_hot_rss(_get(HOT_RSS_URL))


def fetch_popular_entries(page: int) -> list[HotEntry]:
    return parse_site_entries(_get(f"https://b.hatena.ne.jp/site/anond.hatelabo.jp/?sort=count&page={page}"))


def fetch_comments(url: str) -> list[BookmarkComment]:
    return parse_bookmarks(_get("https://b.hatena.ne.jp/entry/jsonlite/?url=" + urllib.parse.quote(url, safe="")))


def fetch_body(url: str) -> str | None:
    try:
        return parse_anond_body(_get(url))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise
