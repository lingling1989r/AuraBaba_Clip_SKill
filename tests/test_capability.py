import unittest

from clipclipskill.capability import select_execution_profile


class CapabilityDecisionTests(unittest.TestCase):
    def test_auto_diarization_degrades_when_requirements_missing(self):
        capabilities = {
            "tools": {"ffmpeg": True, "ffprobe": True},
            "imports": {"faster_whisper": True, "pyannote_audio": False, "torch": True},
            "torch": {"available": True, "cuda_available": False},
            "system": {
                "cpu_count": 8,
                "memory_total_bytes": 16 * 1024 * 1024 * 1024,
                "memory_available_bytes": 8 * 1024 * 1024 * 1024,
                "disk_free_bytes": 20 * 1024 * 1024 * 1024,
            },
            "auth": {"has_hf_token": False},
            "input": {"audio_present": True},
        }
        profile = select_execution_profile(
            template_id="podcast_interview",
            diarization_mode="auto",
            duration_sec=1800,
            language_hint="auto",
            capabilities=capabilities,
        )
        self.assertEqual(profile["verdict"], "degraded")
        self.assertFalse(profile["diarization_enabled"])
        self.assertTrue(profile["warnings"])

    def test_forced_diarization_blocks_when_requirements_missing(self):
        capabilities = {
            "tools": {"ffmpeg": True, "ffprobe": True},
            "imports": {"faster_whisper": True, "pyannote_audio": False, "torch": True},
            "torch": {"available": True, "cuda_available": False},
            "system": {
                "cpu_count": 8,
                "memory_total_bytes": 16 * 1024 * 1024 * 1024,
                "memory_available_bytes": 8 * 1024 * 1024 * 1024,
                "disk_free_bytes": 20 * 1024 * 1024 * 1024,
            },
            "auth": {"has_hf_token": False},
            "input": {"audio_present": True},
        }
        profile = select_execution_profile(
            template_id="podcast_interview",
            diarization_mode="on",
            duration_sec=1800,
            language_hint="auto",
            capabilities=capabilities,
        )
        self.assertEqual(profile["verdict"], "blocked")
        self.assertIn("diarization requested", profile["blocking_reasons"][0])

    def test_cpu_long_video_downgrades_model(self):
        capabilities = {
            "tools": {"ffmpeg": True, "ffprobe": True},
            "imports": {"faster_whisper": True, "pyannote_audio": True, "torch": True},
            "torch": {"available": True, "cuda_available": False},
            "system": {
                "cpu_count": 8,
                "memory_total_bytes": 8 * 1024 * 1024 * 1024,
                "memory_available_bytes": 4 * 1024 * 1024 * 1024,
                "disk_free_bytes": 20 * 1024 * 1024 * 1024,
            },
            "auth": {"has_hf_token": True},
            "input": {"audio_present": True},
        }
        profile = select_execution_profile(
            template_id="solo_course",
            diarization_mode="off",
            duration_sec=7200,
            language_hint="zh",
            capabilities=capabilities,
        )
        self.assertEqual(profile["asr_model"], "small")
        self.assertEqual(profile["device"], "cpu")


if __name__ == "__main__":
    unittest.main()
