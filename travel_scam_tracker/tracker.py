"""Check each source for new advisories and log the travel-related ones.

For each source:
  1. download the listing (page or feed)
  2. skip anything already in data/seen.csv
  3. for new advisories, read the full page (up to a per-run cap) and
     classify it: is it about travel, and what kind of scam?
  4. log travel advisories to data/advisories.csv and remember every URL
     checked in data/seen.csv, travel or not, so nothing is re-read

Then rebuild the tables in README.md.

Safety checks: a source that fails to download or parse is skipped and
flagged in the README; the others still run. A page that parses to zero
advisories is treated as a layout change, not "nothing new."
"""

from __future__ import annotations

import csv
import sys
import time
import traceback
from collections import Counter
from dataclasses import dataclass, fields
from datetime import date
from pathlib import Path

from .classify import CATEGORIES, classify
from .sources import ACTIVE_SOURCES, SOURCES, Advisory, Source, fetch, page_text

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
ADVISORIES_PATH = DATA / "advisories.csv"
SEEN_PATH = DATA / "seen.csv"
STATUS_PATH = DATA / "status.csv"
README_PATH = ROOT / "README.md"

MAX_PAGE_READS = 25   # per source per run; the rest are classified on title and summary
PAUSE_SECONDS = 1.0   # be polite between page reads


@dataclass
class Logged:
    first_seen: str
    published: str
    source: str
    title: str
    url: str
    categories: str
    matched_terms: str


@dataclass
class Seen:
    url: str
    source: str
    first_seen: str
    is_travel: str


@dataclass
class Status:
    source: str
    label: str
    publisher: str
    url: str
    on_page: str
    travel_logged: str
    last_checked: str
    last_new: str
    result: str


# ---------------------------------------------------------------- storage

def read_csv(path: Path, cls):
    if not path.exists():
        return []
    cols = [f.name for f in fields(cls)]
    with path.open(newline="", encoding="utf-8") as f:
        return [cls(**{c: row.get(c, "") for c in cols}) for row in csv.DictReader(f)]


def write_csv(path: Path, rows, cls) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    cols = [f.name for f in fields(cls)]
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow({c: getattr(r, c) for c in cols})


# ---------------------------------------------------------------- core

def process_source(src: Source, items: list[Advisory], seen_urls: set[str], today: str,
                   reader=None) -> tuple[list[Logged], list[Seen]]:
    """Classify the advisories we haven't seen before."""
    reader = reader or (lambda url: page_text(fetch(url)))
    logged, newly_seen = [], []
    reads = 0
    for adv in items:
        if adv.url in seen_urls:
            continue
        text = adv.summary
        if src.reads_full_text and reads < MAX_PAGE_READS:
            try:
                text = f"{adv.summary} {reader(adv.url)}"
            except Exception:  # a single bad page shouldn't sink the run
                pass
            reads += 1
            if PAUSE_SECONDS:
                time.sleep(PAUSE_SECONDS)
        is_travel, cats, terms = classify(adv.title, text)
        newly_seen.append(Seen(adv.url, src.key, today, "yes" if is_travel else "no"))
        if is_travel:
            logged.append(Logged(today, adv.published, src.key, adv.title, adv.url,
                                 "; ".join(cats), "; ".join(terms)))
    return logged, newly_seen


# ---------------------------------------------------------------- README

README_STATUS = ("<!-- STATUS:START -->", "<!-- STATUS:END -->")
README_LATEST = ("<!-- LATEST:START -->", "<!-- LATEST:END -->")
README_CATEGORIES = ("<!-- CATEGORIES:START -->", "<!-- CATEGORIES:END -->")

LABELS = {s.key: s.label for s in SOURCES}


def md(text: str) -> str:
    return str(text).replace("|", "/").strip()


def status_table(statuses: list[Status]) -> str:
    lines = ["| Source | Publisher | On page | Travel advisories logged | Last new | Last checked | Status |",
             "|---|---|---|---|---|---|---|"]
    for s in statuses:
        result = "OK" if s.result == "ok" else f"Needs a look: {md(s.result)}"
        lines.append(f"| [{s.label}]({s.url}) | {s.publisher} | {s.on_page or '-'} | "
                     f"{s.travel_logged or '0'} | {s.last_new or '-'} | {s.last_checked} | {result} |")
    return "\n".join(lines)


def latest_table(rows: list[Logged], n: int = 15) -> str:
    if not rows:
        return "_Nothing logged yet. The first scheduled run will fill this in._"
    rows = sorted(rows, key=lambda r: (r.published or r.first_seen, r.first_seen), reverse=True)[:n]
    lines = ["| Published | Source | Advisory | Scam type |", "|---|---|---|---|"]
    for r in rows:
        lines.append(f"| {r.published or '-'} | {LABELS.get(r.source, r.source)} | "
                     f"[{md(r.title)}]({r.url}) | {md(r.categories) or '-'} |")
    return "\n".join(lines)


def category_table(rows: list[Logged]) -> str:
    counts = Counter(c.strip() for r in rows for c in r.categories.split(";") if c.strip())
    lines = ["| Scam type | Advisories |", "|---|---|"]
    for cat in CATEGORIES:
        lines.append(f"| {cat} | {counts.get(cat, 0)} |")
    return "\n".join(lines)


def replace_block(text: str, markers: tuple[str, str], body: str) -> str:
    start, end = markers
    if start not in text or end not in text:
        return text
    head, rest = text.split(start, 1)
    _, tail = rest.split(end, 1)
    return f"{head}{start}\n{body}\n{end}{tail}"


def update_readme(statuses: list[Status], rows: list[Logged], path: Path = README_PATH) -> None:
    if not path.exists():
        return
    text = path.read_text(encoding="utf-8")
    text = replace_block(text, README_STATUS, status_table(statuses))
    text = replace_block(text, README_LATEST, latest_table(rows))
    text = replace_block(text, README_CATEGORIES, category_table(rows))
    path.write_text(text, encoding="utf-8")


# ---------------------------------------------------------------- run

def run() -> int:
    today = date.today().isoformat()
    logged_all = read_csv(ADVISORIES_PATH, Logged)
    seen_all = read_csv(SEEN_PATH, Seen)
    seen_urls = {s.url for s in seen_all}
    prev = {s.source: s for s in read_csv(STATUS_PATH, Status)}

    statuses, new_total, failures = [], 0, 0
    for src in ACTIVE_SOURCES:
        old = prev.get(src.key)
        try:
            items = src.fetch_and_parse()
            logged, newly_seen = process_source(src, items, seen_urls, today)
            logged_all.extend(logged)
            seen_all.extend(newly_seen)
            seen_urls.update(s.url for s in newly_seen)
            count = sum(1 for r in logged_all if r.source == src.key)
            statuses.append(Status(src.key, src.label, src.publisher, src.url, str(len(items)),
                                   str(count), today, today if logged else (old.last_new if old else ""),
                                   "ok"))
            new_total += len(logged)
            print(f"{src.label}: {len(items)} on page, {len(newly_seen)} new, {len(logged)} travel-related")
        except Exception as exc:
            failures += 1
            traceback.print_exc(file=sys.stderr)
            count = sum(1 for r in logged_all if r.source == src.key)
            statuses.append(Status(src.key, src.label, src.publisher, src.url,
                                   old.on_page if old else "", str(count), today,
                                   old.last_new if old else "", type(exc).__name__))
            print(f"{src.label}: FAILED ({type(exc).__name__}: {exc})")

    write_csv(ADVISORIES_PATH, logged_all, Logged)
    write_csv(SEEN_PATH, seen_all, Seen)
    write_csv(STATUS_PATH, statuses, Status)
    update_readme(statuses, logged_all)
    print(f"New travel advisories logged: {new_total}")
    # only fail the job if every source failed
    return 1 if failures == len(ACTIVE_SOURCES) else 0
