# Travel Scam Advisory Tracker

A small, self-updating log of travel-related scam warnings from the FTC and the FBI: fake airline customer service numbers, rebooking and refund scams, stolen frequent flyer miles, fake vacation rentals, timeshare resale schemes, and more.

## Why I built this

Fraud follows disruption. When flights are canceled, a storm hits, or holiday travel peaks, scammers are right behind the travelers: fake "airline support" numbers in sponsored search results, texts about a missed flight, phony refund offers, and takeovers of loyalty accounts. Government agencies warn about these schemes, but the warnings are spread across different sites and mixed in with every other kind of consumer alert.

I wanted one place that pulls out just the travel-related ones and tags what kind of scam each is. Every weekday, a GitHub Action checks each source, reads anything new, and logs the travel advisories to [`data/advisories.csv`](data/advisories.csv). The commit history doubles as a dated record.

— Angela Lara, CAMS

## Source status

<!-- STATUS:START -->
| Source | Publisher | On page | Travel advisories logged | Last new | Last checked | Status |
|---|---|---|---|---|---|---|
| [FTC Consumer Alerts](https://consumer.ftc.gov/consumer-alerts) | Federal Trade Commission | - | 0 | - | 2026-11-14 | Needs a look: HTTPError |
| [FTC Consumer Protection News](https://www.ftc.gov/news-events/news/press-releases) | Federal Trade Commission | - | 0 | - | 2026-11-14 | Needs a look: HTTPError |
| [FBI IC3 PSAs](https://www.ic3.gov/PSA) | FBI Internet Crime Complaint Center | 28 | 3 | 2026-11-14 | 2026-11-14 | OK |
<!-- STATUS:END -->

## Latest travel advisories

<!-- LATEST:START -->
| Published | Source | Advisory | Scam type |
|---|---|---|---|
| 2026-10-13 | FBI IC3 PSAs | [North Korean IT Workers Expanding Use of Facilitators, Broadening Recruitment](https://www.ic3.gov/PSA/2026/PSA261013) | Fake customer support; Documents and government services |
| 2026-09-17 | FBI IC3 PSAs | [Scammers Impersonating Law Enforcement and Government Officials in Fraud Schemes](https://www.ic3.gov/PSA/2026/PSA260917) | Fake customer support; Phishing, texts and fake websites; Documents and government services |
| 2026-06-16 | FBI IC3 PSAs | [Protect Your Property from Illegal Sales Through Parcel Owner Impersonation](https://www.ic3.gov/PSA/2026/PSA260616) | Fake customer support; Phishing, texts and fake websites |
<!-- LATEST:END -->

Full log: [`data/advisories.csv`](data/advisories.csv)

## Advisories by scam type

<!-- CATEGORIES:START -->
| Scam type | Advisories |
|---|---|
| Airline and ticket booking | 0 |
| Fake customer support | 3 |
| Cancellation, refund and rebooking | 0 |
| Loyalty miles and points | 0 |
| Lodging, rentals and timeshares | 0 |
| Phishing, texts and fake websites | 2 |
| Documents and government services | 2 |
| Travel deals and prizes | 0 |
<!-- CATEGORIES:END -->

An advisory can have more than one type. A fake-support-number warning about canceled flights counts under airline booking, fake customer support, and cancellations.

## Sources

- **FTC Consumer Alerts:** the FTC's plain-language scam warnings for consumers.
- **FTC Consumer Protection news:** FTC enforcement actions and settlements, which show what schemes regulators are actually going after.
- **FBI IC3 Public Service Announcements:** the FBI Internet Crime Complaint Center's alerts on active fraud schemes.

## How it decides what's "travel"

[`travel_scam_tracker/classify.py`](travel_scam_tracker/classify.py) uses two steps:

1. **Is it about travel?** The advisory has to mention a travel term like flight, airline, hotel, vacation rental, cruise, passport, or TSA. Generic words like "trip" or "tour" only count if they show up more than once, so "don't let a scammer trip you up" doesn't qualify.
2. **What kind of scam is it?** Travel advisories are then tagged by scam type: airline and ticket booking, fake customer support, cancellations and refunds, loyalty miles and points, lodging and timeshares, phishing and fake websites, travel documents, and travel deals and prizes.

A refund scam that has nothing to do with travel isn't logged. The keyword lists are short and readable on purpose, so it's easy to see why something was or wasn't included.

## What's in the data

`data/advisories.csv`, one row per travel-related advisory:

| Column | What it is |
|---|---|
| `first_seen` | The date this tracker picked it up |
| `published` | The publication date (month only, if that's all the source shows) |
| `source` | `ftc_alerts`, `ftc_press`, or `fbi_ic3` |
| `title` | The advisory's title |
| `url` | Link to the original |
| `categories` | Scam types, separated by semicolons |
| `matched_terms` | The travel terms that qualified it |

`data/seen.csv` lists every advisory the tracker has checked, travel or not, so nothing gets read twice.

## How it works

```
FTC Consumer Alerts page ──┐
FTC press release feed ────┼─> sources.py ─> classify.py ─> tracker.py ─> advisories.csv ─> README tables
FBI IC3 PSA page ──────────┘                                    ▲
                                                                └── GitHub Action, every weekday
```

1. [`sources.py`](travel_scam_tracker/sources.py) pulls each listing and finds advisories by their URL pattern rather than page layout, so a redesign that keeps the same links doesn't break anything.
2. For anything new, the tracker reads the full advisory page (up to 25 per source per run) so it can match on the body text, not just the headline.
3. [`.github/workflows/update.yml`](.github/workflows/update.yml) runs the tests, then the tracker, and commits the results.

## Built-in safety checks

- **One bad source doesn't stop the others.** A source that fails to download or parse is flagged in the status table, and the rest still run.
- **No silent failures.** If a page loads but no advisories are found, the tracker treats it as a layout change that needs a look, not as "nothing new today."
- **One bad page doesn't lose an advisory.** If a single advisory page won't load, it's classified on its title and summary instead.

## Run it yourself

```bash
pip install -r requirements.txt
python -m travel_scam_tracker
python -m unittest discover -s tests
```

You can also kick off a run from the **Actions** tab with **Run workflow**.

## Notes

- Public government sources only. Nothing here comes from any employer or non-public source.
- This is a monitoring convenience, not legal advice. Always read the original advisory.
- Possible next additions: the FCC's scam glossary, the BBB Scam Tracker, and the UK's Action Fraud alerts.

## Related projects

- [Airline Disruption Fraud Monitor](https://github.com/angelalara1219/airline-disruption-fraud-monitor): detecting and staffing for a loyalty-fraud spike during a ground stop
- [Sanctions List Tracker](https://github.com/angelalara1219/sanctions-list-tracker)

## License

MIT
