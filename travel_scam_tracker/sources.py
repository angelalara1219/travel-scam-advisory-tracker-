"""Download public scam advisories and turn them into a common shape.

Sources:
  * FTC Consumer Alerts          - consumer.ftc.gov listing page (HTML)
  * FTC Consumer Protection news - ftc.gov press release RSS feed
  * FBI IC3 PSAs                 - ic3.gov Public Service Announcements (HTML)

Each source returns a list of Advisory objects. Parsers look for links by
their URL pattern rather than by page layout, so a redesign that keeps the
same URLs won't break a run. If a page parses to zero advisories, the parser
raises, and the tracker marks that source as needing a look instead of
quietly reporting "nothing new."
"""

from __future__ import annotations

import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime
from email.utils import parsedate_to_datetime
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

# Some government sites answer a plain script differently from a browser, and
# vice versa, so fetch_first() tries both before giving up.
SCRIPT_HEADERS = {"User-Agent": "travel-scam-advisory-tracker/1.0 (public-data research script)"}
BROWSER_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}
HEADERS = BROWSER_HEADERS

FTC_ALERTS_URL = "https://consumer.ftc.gov/consumer-alerts"
# Same alerts, other pages that list them, tried in order if the main one fails.
FTC_ALERTS_FALLBACKS = ["https://consumer.ftc.gov/blog", "https://www.consumer.ftc.gov/consumer-alerts"]
FTC_PRESS_RSS = "https://www.ftc.gov/feeds/press-release-consumer-protection.xml"
FTC_PRESS_FALLBACKS = ["https://www.ftc.gov/feeds/press-release.xml"]
IC3_PSA_URL = "https://www.ic3.gov/PSA"


@dataclass
class Advisory:
    url: str
    title: str
    published: str  # YYYY-MM-DD, or YYYY-MM when only the month is known
    summary: str = ""


@dataclass
class Source:
    key: str
    label: str
    publisher: str
    url: str
    fetch_and_parse: object = field(repr=False, default=None)
    reads_full_text: bool = True  # fetch each new advisory's page to match on body text


class ParseError(RuntimeError):
    """The page downloaded but didn't look like we expected."""


# ---------------------------------------------------------------- helpers

def fetch(url: str, attempts: int = 3, headers: dict | None = None) -> str:
    for attempt in range(1, attempts + 1):
        try:
            resp = requests.get(url, headers=headers or HEADERS, timeout=(30, 90))
            resp.raise_for_status()
            break
        except (requests.Timeout, requests.ConnectionError):
            if attempt == attempts:
                raise
            time.sleep(10 * attempt)
    resp.encoding = resp.encoding or "utf-8"
    return resp.text


def fetch_first(urls: list[str], parse):
    """Try each URL with browser-style and then script-style headers, and
    return the first one that downloads and parses. Raises the last error."""
    last = None
    for url in urls:
        for headers in (BROWSER_HEADERS, SCRIPT_HEADERS):
            try:
                return parse(fetch(url, attempts=2, headers=headers))
            except (requests.RequestException, ParseError) as exc:
                last = exc
    raise last


def clean(text) -> str:
    return " ".join(str(text or "").split())


def page_text(html: str, limit: int = 20000) -> str:
    """Main readable text of an advisory page, for keyword matching."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "header", "footer", "aside", "form"]):
        tag.decompose()
    main = soup.find("main") or soup.find("article") or soup.body or soup
    return clean(main.get_text(" "))[:limit]


def dedupe(items: list[Advisory]) -> list[Advisory]:
    seen, out = set(), []
    for a in items:
        if a.url not in seen:
            seen.add(a.url)
            out.append(a)
    return out


# ---------------------------------------------------------------- FTC alerts

FTC_ALERT_HREF = re.compile(r"/consumer-alerts/(\d{4})/(\d{2})/[a-z0-9-]+/?$")


def parse_ftc_alerts(html: str, base: str = FTC_ALERTS_URL) -> list[Advisory]:
    soup = BeautifulSoup(html, "html.parser")
    items = []
    for a in soup.find_all("a", href=True):
        m = FTC_ALERT_HREF.search(a["href"].split("?")[0])
        title = clean(a.get_text())
        if not m or len(title) < 8:
            continue
        published = f"{m.group(1)}-{m.group(2)}"
        # use a nearby <time datetime="..."> if the listing has one
        card = a.find_parent(["article", "li", "div"])
        t = card.find("time") if card else None
        if t and t.get("datetime", "")[:10].count("-") == 2:
            published = t["datetime"][:10]
        items.append(Advisory(url=urljoin(base, a["href"].split("?")[0]), title=title, published=published))
    items = dedupe(items)
    if not items:
        raise ParseError("no consumer alert links found on the FTC listing page")
    return items


# ---------------------------------------------------------------- FTC RSS

def parse_rss(xml_text: str) -> list[Advisory]:
    try:
        root = ET.fromstring(xml_text.encode("utf-8") if isinstance(xml_text, str) else xml_text)
    except ET.ParseError as exc:
        raise ParseError(f"feed is not valid XML: {exc}") from exc
    items = []
    for item in root.iter("item"):
        title = clean(item.findtext("title"))
        link = clean(item.findtext("link"))
        if not title or not link:
            continue
        published = ""
        raw = item.findtext("pubDate")
        if raw:
            try:
                published = parsedate_to_datetime(raw).date().isoformat()
            except (TypeError, ValueError):
                published = ""
        summary = clean(BeautifulSoup(item.findtext("description") or "", "html.parser").get_text(" "))
        items.append(Advisory(url=link, title=title, published=published, summary=summary[:2000]))
    items = dedupe(items)
    if not items:
        raise ParseError("feed had no items")
    return items


# ---------------------------------------------------------------- IC3

IC3_HREF = re.compile(r"/PSA/(\d{4})/PSA(\d{6})", re.IGNORECASE)


def parse_ic3(html: str, base: str = IC3_PSA_URL) -> list[Advisory]:
    soup = BeautifulSoup(html, "html.parser")
    items = []
    for a in soup.find_all("a", href=True):
        m = IC3_HREF.search(a["href"])
        title = clean(a.get_text())
        if not m or len(title) < 8:
            continue
        try:
            published = datetime.strptime(m.group(2), "%y%m%d").date().isoformat()
        except ValueError:
            published = m.group(1)
        items.append(Advisory(url=urljoin(base, a["href"]), title=title, published=published))
    items = dedupe(items)
    if not items:
        raise ParseError("no PSA links found on the IC3 page")
    return items


# ---------------------------------------------------------------- registry

SOURCES = [
    Source("ftc_alerts", "FTC Consumer Alerts", "Federal Trade Commission", FTC_ALERTS_URL,
           lambda: fetch_first([FTC_ALERTS_URL, *FTC_ALERTS_FALLBACKS], parse_ftc_alerts)),
    Source("ftc_press", "FTC Consumer Protection News", "Federal Trade Commission",
           "https://www.ftc.gov/news-events/news/press-releases",
           lambda: fetch_first([FTC_PRESS_RSS, *FTC_PRESS_FALLBACKS], parse_rss), reads_full_text=False),
    Source("fbi_ic3", "FBI IC3 PSAs", "FBI Internet Crime Complaint Center", IC3_PSA_URL,
           lambda: fetch_first([IC3_PSA_URL], parse_ic3)),
]
