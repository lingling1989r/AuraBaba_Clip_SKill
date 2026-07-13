import unittest

from clipclipskill.progress import format_started_message, humanize_eta_seconds, start_step
from clipclipskill.status import build_initial_status, update_progress


class ProgressTests(unittest.TestCase):
    def test_humanize_eta_seconds(self):
        self.assertEqual(humanize_eta_seconds(12), "~12s")
        self.assertEqual(humanize_eta_seconds(65), "~1m 5s")

    def test_start_step_updates_status_progress(self):
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
        progress = start_step(
            status["progress"],
            step_id="probe",
            label="Machine check",
            eta_seconds=15,
            message=format_started_message("Machine check", 15, "checking local environment"),
            overall_percent=5,
            eta_seconds_remaining=15,
        )
        status = update_progress(status, progress)
        self.assertEqual(status["progress"]["current_step"]["id"], "probe")
        self.assertEqual(status["progress"]["current_step"]["state"], "in_progress")
        self.assertEqual(status["progress"]["overall_percent"], 5)
        self.assertIn("Started machine check", status["progress"]["current_step"]["message"])


if __name__ == "__main__":
    unittest.main()
