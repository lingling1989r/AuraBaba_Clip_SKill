import unittest

from clipclipskill.ops_copy import build_structured_title
from clipclipskill.plan import build_clip_plan


class ClipPlanSchemaTests(unittest.TestCase):
    def test_build_clip_plan_contains_expected_fields(self):
        scored = [
            {
                "sequence": 1,
                "topic": "核心观点",
                "start_sec": 0.0,
                "end_sec": 45.0,
                "duration_sec": 45.0,
                "score": {"total": 0.91, "components": {"topic_completeness": 0.35}},
            }
        ]
        payload = build_clip_plan(
            job_id="job1",
            template_id="podcast_interview",
            length_policy="topic_complete",
            scored_candidates=scored,
            max_clips=1,
        )
        self.assertEqual(payload["job_id"], "job1")
        self.assertEqual(payload["clips"][0]["output_stem"], "核心观点_001")
        self.assertEqual(payload["clips"][0]["topic"], "核心观点")
        self.assertEqual(payload["clips"][0]["title"], build_structured_title("podcast_interview", "核心观点"))
        self.assertNotEqual(payload["clips"][0]["title"], payload["clips"][0]["topic"])


if __name__ == "__main__":
    unittest.main()
