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
    "boarding pass", "frequent flyer", "frequent flier", "travel", "traveling", "travelling",
    "traveler", "travelers", "traveller", "travellers", "getaway", "accommodation",
    "holiday accommodation", "holiday rental", "holiday booking", "holiday package", "holiday deal", "vacation", "vacations", "vacation rental", "hotel", "hotels", "resort",
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
        "accommodation", "holiday rental", "holiday accommodation",
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

# Words that show up in lots of non-travel scam alerts (a passport as proof of
# identity, "trip" in "trip you up", a romance scammer "travelling for work").
# In the title they count. In the body they only back up a core travel term.
WEAK_ANCHORS = {"trip", "trips", "tour", "tours", "travel", "traveling", "travelling", "traveler",
                "travelers", "traveller", "travellers", "accommodation",
                "passport", "passports", "real id", "visa application", "travel visa", "tsa",
                "itinerary", "holiday travel"}
# Body text needs at least this many different core travel terms (flight,
# airline, hotel, cruise...) to qualify an advisory whose title doesn't.
MIN_CORE_BODY_TERMS = 2


def classify(title: str, text: str = "") -> tuple[bool, list[str], list[str]]:
    """Return (is_travel, categories, matched_anchor_terms)."""
    title = title or ""
    body = text or ""
    full = f"{title} {body}"

    title_anchors = [t for t, p in _ANCHORS if p.search(title)]
    body_anchors = [t for t, p in _ANCHORS if p.search(body)]
    core_body = {t.rstrip("s") for t in body_anchors if t not in WEAK_ANCHORS}

    is_travel = bool(title_anchors or len(core_body) >= MIN_CORE_BODY_TERMS)
    if not is_travel:
        return False, [], []

    cats = [c for c, pats in _CATS.items() if any(p.search(full) for _, p in pats)]
    matched = sorted(set(title_anchors + body_anchors))
    return True, cats, matched
