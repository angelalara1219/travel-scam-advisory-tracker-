"""Decide whether an advisory is about travel, and tag what kind of scam it is.

An advisory counts as travel-related only if it mentions a travel anchor term
(flight, airline, vacation, hotel, cruise, and so on). Scam-type tags like
"refund" or "fake customer support" are then added on top, so a general
refund-scam alert doesn't get logged unless it's actually about travel.
"""

from __future__ import annotations

import re

# Terms that make an advisory travel-related.
TRAVEL_ANCHORS = [
    "airline", "airlines", "airfare", "flight", "flights", "air travel", "airport", "airports",
    "boarding pass", "frequent flyer", "frequent flier", "travel", "traveling", "travelers",
    "travellers", "vacation", "vacations", "vacation rental", "hotel", "hotels", "resort",
    "timeshare", "timeshares", "cruise", "cruises", "passport", "passports", "real id", "tsa",
    "global entry", "rental car", "car rental", "booking site", "trip", "trips", "holiday travel",
    "travel visa", "visa application", "e-visa", "evisa", "travel agent", "tour", "tours", "itinerary",
]

# Scam-type tags. A tag only applies once an advisory has passed the anchor test.
CATEGORIES = {
    "Airline and ticket booking": [
        "airline", "airlines", "flight", "flights", "airfare", "ticket", "tickets", "booking",
        "boarding pass", "reservation", "reservations", "itinerary",
    ],
    "Fake customer support": [
        "customer service", "customer support", "support number", "phone number", "help line",
        "helpline", "impersonat", "pretending to be", "sponsored", "search results", "fake agent",
    ],
    "Cancellation, refund and rebooking": [
        "refund", "refunds", "cancel", "canceled", "cancelled", "cancellation", "delay", "delayed",
        "rebook", "rebooking", "compensation", "voucher", "vouchers", "travel credit", "flight credit",
    ],
    "Loyalty miles and points": [
        "frequent flyer", "frequent flier", "miles", "mileage", "loyalty", "reward points",
        "rewards program", "airline miles",
    ],
    "Lodging, rentals and timeshares": [
        "hotel", "hotels", "vacation rental", "rental listing", "lodging", "resort", "timeshare",
        "timeshares", "airbnb", "vrbo",
    ],
    "Phishing, texts and fake websites": [
        "phishing", "smishing", "text message", "texts", "fake website", "spoofed", "spoofing",
        "lookalike", "look-alike", "qr code", "malicious link", "suspicious link", "fake email",
    ],
    "Documents and government services": [
        "passport", "real id", "tsa", "precheck", "global entry", "travel visa", "visa application",
        "e-visa", "evisa",
    ],
    "Travel deals and prizes": [
        "free vacation", "free trip", "travel club", "travel deal", "prize", "sweepstakes",
        "giveaway", "discount travel", "too good to be true",
    ],
}


def _pattern(term: str) -> re.Pattern:
    # word boundary at the start; at the end too unless the term is a stem like "impersonat"
    end = r"\b" if term[-1].isalpha() and not term.endswith("at") else ""
    return re.compile(r"\b" + re.escape(term) + end, re.IGNORECASE)


_ANCHORS = [(t, _pattern(t)) for t in TRAVEL_ANCHORS]
_CATS = {c: [(t, _pattern(t)) for t in terms] for c, terms in CATEGORIES.items()}

# Generic words that are too weak to make something travel-related on their own
# when they only appear in body text (e.g. "trip" in "trip up", "tour" of a website).
WEAK_ANCHORS = {"trip", "trips", "tour", "tours", "travel", "traveling"}
MIN_WEAK_HITS = 2


def classify(title: str, text: str = "") -> tuple[bool, list[str], list[str]]:
    """Return (is_travel, categories, matched_anchor_terms)."""
    title = title or ""
    body = text or ""
    full = f"{title} {body}"

    title_anchors = [t for t, p in _ANCHORS if p.search(title)]
    body_anchors = [t for t, p in _ANCHORS if p.search(body)]
    strong_body = [t for t in body_anchors if t not in WEAK_ANCHORS]
    weak_body_hits = sum(len(p.findall(body)) for t, p in _ANCHORS if t in WEAK_ANCHORS)

    is_travel = bool(title_anchors or strong_body or weak_body_hits >= MIN_WEAK_HITS)
    if not is_travel:
        return False, [], []

    cats = [c for c, pats in _CATS.items() if any(p.search(full) for _, p in pats)]
    matched = sorted(set(title_anchors + body_anchors))
    return True, cats, matched
