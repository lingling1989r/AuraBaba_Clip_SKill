import unittest

from clipclipskill.downloader import validate_supported_url
from clipclipskill.status import build_initial_status


class InputSourceTests(unittest.TestCase):
    def test_validate_supported_youtube_url(self):
        normalized, platform = validate_supported_url("https://youtu.be/example")
        self.assertEqual(normalized, "https://youtu.be/example")
        self.assertEqual(platform, "youtube")

    def test_validate_supported_bilibili_url(self):
        normalized, platform = validate_supported_url("https://www.bilibili.com/video/BV1xx411c7mD")
        self.assertEqual(normalized, "https://www.bilibili.com/video/BV1xx411c7mD")
        self.assertEqual(platform, "bilibili")

    def test_validate_rejects_unsupported_url(self):
        with self.assertRaises(ValueError):
            validate_supported_url("https://example.com/video")

    def test_build_initial_status_for_url_source(self):
        status = build_initial_status(
            job_id="job-1",
            source_kind="url",
            input_video_path=None,
            source_sha256=None,
            origin_path=None,
            origin_url="https://youtu.be/example",
            platform="youtube",
            template_id="podcast_interview",
            length_mode="topic_complete",
            target_seconds=None,
            transcription_mode="whisper",
            diarization_mode="auto",
            language_hint="auto",
        )
        self.assertEqual(status["source"]["kind"], "url")
        self.assertEqual(status["source"]["download_status"], "pending")
        self.assertIsNone(status["source"]["input_video_path"])


if __name__ == "__main__":
    unittest.main()
