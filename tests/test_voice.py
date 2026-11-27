"""The house voice gate (copy.tells, copy.plain) and the plain fixed copy. Examples are real output from queue/ on
2026-11-26 and 2026-11-27, the lines the owner meant by "everything reads as AI"."""
import json
import unittest

from aidaily import copy, desk, platforms, site


class R:
    def __init__(self, rows):
        self.returncode, self.stderr = 0, ""
        self.stdout = json.dumps({"result": json.dumps(rows)})


def row(**kw):
    base = {"id": 0, "headline": "Nscale raises $3.36B before its US IPO", "dek": "Convertible notes.", "company": "Nscale",
            "figure": "$3.36B", "x_post": "Nscale raises $3.36B", "linkedin_post": "Nscale raised $3.36B.\n\nSource: TechCrunch"}
    base.update(kw)
    return base


def run(**kw):
    s = {"title": "Nscale raises $3.36B in convertible financing", "source": "TechCrunch",
         "summary": "Ahead of its US IPO. Nscale raised $3.36B to expand. The deal raises new questions about control."}
    copy.write([s], runner=lambda *a, **k: R([row(**kw)]))
    return s


class Tells(unittest.TestCase):
    def test_real_tells_are_found(self):
        for text in ("Trump signals he is ready to escalate tariffs on Asian trading partners",
                     "Norse Atlantic suspends all flights as it faces potential collapse",
                     "The carrier is seeking urgent funding and will file for bankruptcy without a financial lifeline.",
                     "The U.S. planned a fresh tariff salvo on 14 trading partners.",
                     "Chinese shares rise as Beijing signals more support for markets",
                     "The moves came amid increased volatility in global markets.",
                     "President Trump sent a message to trading partners across Asia that he is ready to escalate tariffs.",
                     "The deal raises new questions about control.",
                     "What happens next remains to be seen.",
                     "Is this the end of the chip boom? Analysts disagree.",
                     "Shares jump!",
                     "Oil falls. Gas falls. Coal falls. Power prices follow.",
                     "Not only did sales fall, margins fell too.",
                     "Enter the chip war: Nvidia halts shipments."):
            self.assertTrue(copy.tells(text) or copy.NOT_BUT.search(text), text)

    def test_plain_news_passes(self):
        for text in ("Nvidia halts chip shipments to four Southeast Asian countries",
                     "Poland signs $300 million Palantir deal to use AI in defense",
                     "France's inflation slows to 2.9% in November as energy prices fall",
                     "Insee says consumer prices fell 0.7% in November, after rising 0.4% in October.",
                     "Bournemouth beat Celta Vigo 2-1 with 10 men for a 10th straight win",
                     "He says he felt he could \"raise questions and concerns amid change\" at OpenAI."):
            self.assertEqual(copy.tells(text), [], text)

    def test_a_quoted_statement_is_the_speakers(self):
        self.assertEqual(copy.tells('Greer said the rule would "send a message" to Beijing.'), [])

    def test_source_line_is_not_copy(self):
        self.assertEqual(copy.tells("Nscale raised $3.36B.\n\nSource: Amid Media"), [])

    def test_two_hedges_in_one_sentence_are_a_stack(self):
        self.assertTrue(copy.tells("The deal could potentially close next month."))
        self.assertEqual(copy.tells("The deal could close next month."), [])

    def test_title_case_headline(self):
        self.assertIn("title case headline", copy.tells("Nvidia Halts Chip Shipments To Four Countries", headline=True))
        self.assertEqual(copy.tells("Nvidia halts chip shipments to four countries", headline=True), [])
        self.assertEqual(copy.tells("Pablo Hernández de Cos wins race for ECB presidency", headline=True), [])

    def test_not_only_joins_the_contrast_gate(self):
        self.assertTrue(copy.NOT_BUT.search("The plan is not only costly but slow."))
        self.assertTrue(copy.NOT_BUT.search("It is more than just a chip."))


class Plain(unittest.TestCase):
    def test_rewrites_keep_every_digit_and_name(self):
        text = "Additionally, Nvidia is really also selling 4,000 chips in order to cut a total of $3 million."
        out = copy.plain(text)
        self.assertEqual(out, "Nvidia is selling 4,000 chips to cut $3 million.")
        self.assertEqual(copy._numbers(out), copy._numbers(text))

    def test_the_source_line_is_untouched(self):
        self.assertEqual(copy.plain("Done.\n\nSource: Also Media"), "Done.\n\nSource: Also Media")

    def test_not_only_also_stays(self):
        self.assertIn("also", copy.plain("It sells chips and also software, as well as services."))


class Gate(unittest.TestCase):
    def test_write_rewrites_filler(self):
        s = run(x_post="Nscale additionally raises $3.36B in order to expand")
        self.assertEqual(s["copy_status"], "ok")
        self.assertEqual(s["x_post"], "Nscale raises $3.36B to expand")

    def test_write_holds_a_stock_phrase_in_the_headline(self):
        s = run(headline="Nscale signals it is ready to list after $3.36B raise")
        self.assertEqual(s["copy_status"], "fallback")

    def test_write_holds_a_tell_in_the_report(self):
        s = run(linkedin_post="Nscale raised $3.36B. The deal raises new questions about control.\n\nSource: TechCrunch")
        self.assertEqual(s["copy_status"], "fallback")

    def test_audit_holds_a_queued_post_with_a_tell(self):
        post = {"headlines": ["Nvidia halts chips"], "dek": "The halt is a lifeline for rivals.", "body": "", "topic": "Tech"}
        self.assertTrue(any(p.startswith("voice:") for p in desk.audit(post)))

    def test_the_writer_prompt_carries_the_voice(self):
        prompt = " ".join(copy.PROMPT.split())
        for phrase in ("short, plain, confident", "\"signals\"", "\"amid\"", "never say the headline again", "No question"):
            self.assertIn(phrase, prompt)


class Platforms(unittest.TestCase):
    def test_a_sentence_that_restates_the_headline_in_other_words_is_dropped(self):
        post = {"headlines": ["1Password reports a data breach and says user vaults are safe"],
                "dek": "The company says customers' logins and other sensitive information were not compromised in the recent breach.",
                "body": "1Password says it was hacked in a recent data breach."}
        self.assertEqual(platforms.why_it_matters(post), [post["dek"]])

    def test_a_new_fact_is_kept(self):
        post = {"headlines": ["Nvidia halts chip shipments to four countries"],
                "dek": "The halt follows a new U.S. rule requiring licenses for advanced chips.",
                "body": "Buyers of Nvidia chips have been told to rule out Chinese renters to get licenses."}
        self.assertEqual(len(platforms.why_it_matters(post)), 2)


class FixedCopy(unittest.TestCase):
    def test_fixed_copy_has_no_tells(self):
        pages = {"about": site.about_page(), "standards": site.standards_page(), "contact": site.contact_page(),
                 "notfound": site.not_found()}
        for name, html in pages.items():
            text = html.replace("&middot;", " ")
            import re
            plain = re.sub(r"<[^>]+>", " ", text)
            plain = plain.replace("Written by AI from the sources listed", "")
            self.assertEqual(copy.tells(plain), [], name)
            self.assertFalse(copy.NOT_BUT.search(plain), name)
            self.assertNotRegex(plain, "[—–]", name)

    def test_topic_intros_are_short(self):
        for topic, intro in site.TOPICS.items():
            self.assertLess(len(intro), 90, topic)
            self.assertEqual(copy.tells(intro), [], topic)

    def test_disclosure_survives(self):
        self.assertIn("Written by AI from the sources listed", site.standards_page())
        self.assertIn("Written by AI", site.about_page() + site.standards_page())

    def test_caption_lines_are_short_and_plain(self):
        for line in (desk.CONFIG["send_line"], desk.CONFIG["source_line"], *desk.CONFIG["source_replies"],
                     desk.CONFIG["send_company_line"], *(r["line"] for r in desk.CONFIG["send_prompts"])):
            self.assertLess(len(line), 60, line)
            self.assertEqual(copy.tells(line.replace("?", ".")), [], line)
        self.assertEqual(desk.CONFIG["source_keyword"], "SOURCE")
        self.assertIn("SOURCE", desk.CONFIG["source_line"])


if __name__ == "__main__":
    unittest.main()
