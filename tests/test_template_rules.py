import unittest

from clipclipskill.templates import diarization_default, resolve_template


class TemplateRuleTests(unittest.TestCase):
    def test_template_alias_resolution(self):
        self.assertEqual(resolve_template("播客"), "podcast_interview")
        self.assertEqual(resolve_template("football"), "sports_highlights")

    def test_diarization_defaults(self):
        self.assertTrue(diarization_default("podcast_interview"))
        self.assertFalse(diarization_default("solo_course"))


if __name__ == "__main__":
    unittest.main()
