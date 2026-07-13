import unittest

from clipclipskill.status import build_initial_status, confirm_plan, confirm_template, next_action, transition_status


class StatusTransitionTests(unittest.TestCase):
    def test_status_transition_flow(self):
        status = build_initial_status(
            job_id="job1",
            source_kind="local",
            input_video_path="/tmp/video.mp4",
            source_sha256="abc123",
            origin_path="/tmp/video.mp4",
            origin_url=None,
            platform=None,
            template_id="solo_course",
            length_mode="topic_complete",
            target_seconds=None,
            transcription_mode="whisper",
            diarization_mode="auto",
            language_hint="auto",
        )
        self.assertEqual(status["progress"]["current_step"]["state"], "pending")
        self.assertEqual(status["preflight"]["verdict"], "pending")
        status = transition_status(status, "probed")
        status = transition_status(status, "awaiting_template_confirmation")
        status = confirm_template(
            status,
            template_id="solo_course",
            length_mode="topic_complete",
            target_seconds=None,
            transcription_mode="whisper",
            diarization_mode="off",
        )
        status = transition_status(status, "confirmed_for_transcription")
        self.assertEqual(next_action(status), "transcribe")
        status = transition_status(status, "transcribing")
        status = transition_status(status, "transcribed")
        status = transition_status(status, "analysis_ready")
        status = transition_status(status, "awaiting_plan_confirmation")
        status = transition_status(status, "approved_for_render")
        self.assertEqual(next_action(status), "render")
        status = transition_status(status, "rendering")
        status = transition_status(status, "ops_generating")
        self.assertEqual(next_action(status), "ops")
        status = transition_status(status, "validating")
        self.assertEqual(next_action(status), "validate")

    def test_confirm_plan_sets_gate(self):
        status = build_initial_status(
            job_id="job1",
            source_kind="local",
            input_video_path="/tmp/video.mp4",
            source_sha256="abc123",
            origin_path="/tmp/video.mp4",
            origin_url=None,
            platform=None,
            template_id="solo_course",
            length_mode="topic_complete",
            target_seconds=None,
            transcription_mode="whisper",
            diarization_mode="auto",
            language_hint="auto",
        )
        status = confirm_plan(status)
        self.assertTrue(status["confirmations"]["plan_gate"]["confirmed"])


if __name__ == "__main__":
    unittest.main()
