import tempfile
import unittest
from pathlib import Path

from travel_scam_tracker import sources as src
from travel_scam_tracker import tracker as t
from travel_scam_tracker.classify import classify

FIX = Path(__file__).parent / "fixtures"
t.PAUSE_SECONDS = 0


class ParserTests(unittest.TestCase):
    def test_ftc_alerts(self):
        items = src.parse_ftc_alerts((FIX / "ftc_alerts.html").read_text())
        self.assertEqual(len(items), 3)  # duplicate "Read more" link and pager ignored
        self.assertTrue(items[0].url.startswith("https://consumer.ftc.gov/consumer-alerts/2026/11/"))
        self.assertEqual(items[0].published, "2026-11-13")  # from <time>
        self.assertEqual(items[2].published, "2026-10")     # month from the URL

    def test_ftc_rss(self):
        items = src.parse_rss((FIX / "ftc_press.xml").read_text())
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0].published, "2026-11-11")
        self.assertIn("travel club", items[0].summary)
        self.assertNotIn("<p>", items[0].summary)

    def test_ic3(self):
        items = src.parse_ic3((FIX / "ic3.html").read_text())
        self.assertEqual(len(items), 3)
        self.assertEqual(items[0].published, "2026-11-05")
        self.assertEqual(items[0].url, "https://www.ic3.gov/PSA/2026/PSA261105")

    def test_scamwatch(self):
        items = src.parse_scamwatch((FIX / "scamwatch.html").read_text())
        self.assertEqual(len(items), 2)  # pager ignored
        self.assertEqual(items[0].published, "2026-11-12")
        self.assertIn("cancelled flights", items[0].summary)
        self.assertTrue(items[0].url.startswith("https://www.scamwatch.gov.au/about-us/news-and-alerts/"))

    def test_only_working_sources_are_scheduled(self):
        keys = [s.key for s in src.ACTIVE_SOURCES]
        self.assertEqual(keys, ["fbi_ic3", "au_scamwatch"])

    def test_empty_page_is_an_error(self):
        with self.assertRaises(src.ParseError):
            src.parse_ic3("<html><body>Maintenance</body></html>")
        with self.assertRaises(src.ParseError):
            src.parse_rss("not xml")


class ClassifyTests(unittest.TestCase):
    def test_travel_title(self):
        ok, cats, _ = classify("Flight canceled? Watch out for fake airline customer service numbers")
        self.assertTrue(ok)
        self.assertIn("Airline and ticket booking", cats)
        self.assertIn("Fake customer support", cats)
        self.assertIn("Cancellation, refund and rebooking", cats)

    def test_not_travel(self):
        ok, cats, _ = classify("What to know about new student loan rules",
                               "Contact your servicer for a refund of overpayments.")
        self.assertFalse(ok)
        self.assertEqual(cats, [])

    def test_credit_card_visa_is_not_travel(self):
        ok, _, _ = classify("Gift card scams", "Scammers ask you to pay with a Visa gift card.")
        self.assertFalse(ok)

    def test_weak_word_once_in_body_is_not_enough(self):
        ok, _, _ = classify("Imposter scams", "Don't let a scammer trip you up.")
        self.assertFalse(ok)

    def test_one_core_word_in_body_is_not_enough(self):
        ok, _, _ = classify("Imposter scams on the rise",
                            "Some callers say your hotel reservation was canceled.")
        self.assertFalse(ok)

    def test_passing_mention_of_passport_is_not_travel(self):
        ok, _, _ = classify("Spot the signs of a relationship scam",
                            "They may say they are travelling for work and ask you to pay for a passport.")
        self.assertFalse(ok)

    def test_two_core_terms_in_body_count(self):
        ok, _, _ = classify("Scam alert: fake callback numbers",
                            "Scammers pose as your airline or hotel when you search for help.")
        self.assertTrue(ok)

    def test_loyalty(self):
        ok, cats, _ = classify("Criminals Impersonating Airlines to Steal Frequent Flyer Miles")
        self.assertTrue(ok)
        self.assertIn("Loyalty miles and points", cats)


class TrackerTests(unittest.TestCase):
    def setUp(self):
        self.source = src.Source("ftc_alerts", "FTC Consumer Alerts", "FTC", src.FTC_ALERTS_URL)
        self.items = src.parse_ftc_alerts((FIX / "ftc_alerts.html").read_text())

    def test_logs_only_travel_and_remembers_everything(self):
        logged, seen = t.process_source(self.source, self.items, set(), "2026-11-14",
                                        reader=lambda url: "")
        self.assertEqual(len(seen), 3)
        self.assertEqual([r.title for r in logged],
                         ["Flight canceled? Watch out for fake airline customer service numbers",
                          "Selling your timeshare? It's probably a scam"])

    def test_already_seen_is_skipped(self):
        seen_urls = {i.url for i in self.items}
        logged, seen = t.process_source(self.source, self.items, seen_urls, "2026-11-14",
                                        reader=lambda url: "")
        self.assertEqual((logged, seen), ([], []))

    def test_body_text_can_make_it_travel(self):
        def reader(url):
            return "Scammers text about a missed flight and a hotel charge." if "student-loan" in url else ""
        logged, _ = t.process_source(self.source, self.items, set(), "2026-11-14", reader=reader)
        self.assertEqual(len(logged), 3)

    def test_bad_page_read_falls_back_to_title(self):
        def reader(url):
            raise TimeoutError
        logged, seen = t.process_source(self.source, self.items, set(), "2026-11-14", reader=reader)
        self.assertEqual(len(seen), 3)
        self.assertEqual(len(logged), 2)

    def test_readme_blocks(self):
        logged, _ = t.process_source(self.source, self.items, set(), "2026-11-14", reader=lambda u: "")
        status = [t.Status("ftc_alerts", "FTC Consumer Alerts", "FTC", "https://x", "3", "2",
                           "2026-11-14", "2026-11-14", "ok"),
                  t.Status("fbi_ic3", "FBI IC3 PSAs", "FBI", "https://y", "", "0",
                           "2026-11-14", "", "ReadTimeout")]
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "README.md"
            p.write_text("top\n<!-- STATUS:START -->\nold\n<!-- STATUS:END -->\n"
                         "<!-- LATEST:START -->\nold\n<!-- LATEST:END -->\n"
                         "<!-- CATEGORIES:START -->\nold\n<!-- CATEGORIES:END -->\nbottom\n")
            t.update_readme(status, logged, p)
            out = p.read_text()
        self.assertIn("Needs a look: ReadTimeout", out)
        self.assertIn("fake airline customer service numbers", out)
        self.assertIn("| Lodging, rentals and timeshares | 1 |", out)
        self.assertTrue(out.startswith("top") and out.rstrip().endswith("bottom"))
        self.assertNotIn("old", out)

    def test_latest_table_summary_shows_span_and_most_recent(self):
        def row(pub, title):
            return t.Logged("2026-11-14", pub, "au_scamwatch", title, f"https://x/{title}", "", "")
        rows = [row("2009-11-24", "a"), row("2026-02-09", "b"), row("2014-07-21", "c")]
        out = t.latest_table(rows, n=2)
        self.assertTrue(out.startswith("**3 travel advisories logged**, published 2009 to 2026. "
                                       "Most recent: 2026-02-09."))
        self.assertIn("Showing the 2 newest", out)
        self.assertNotIn("/a)", out)


if __name__ == "__main__":
    unittest.main()
